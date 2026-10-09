"""STEP 8 - IMPROVEMENTS. Can a scored idea be made better, honestly?

Kris, 2026-10-09: *"try all your backtesting tricks to make them better again,
changing market filters, adding vwaps, emas, timeframes, time of the day
everything, and then after it again walk to each of them with the help of AI"*.
The 27 ideas are `backtests/factory/step8_list.json` (20 picked by pass rate
with PF >= 1.15 and <= 50 days, plus Kris's 7).

PRE-REGISTERED 2026-10-09, before the first run. Nothing below is changed
after seeing a number.

THE SEARCH, in three stages, each picked on the OLDER half of the 3-year
window only (highest profit factor at 1x cost, among choices with >= 30
older-half trades and >= 0.1 trades/day):
    A. timeframe   15m / 1h / 4h, the hold scaled to the same wall-clock time
    B. one filter  `FILTERS` below - trend EMAs/SMAs, rolling VWAP, the higher-
                   timeframe candle, ADX, RSI, volatility, volume, six UTC
                   session windows - or none. Must keep >= 30% of the trades.
    C. exits       stop x target x hold grid, or unchanged
    D. AI          a model sees the rule and the OLDER-half table only and
                   proposes up to 6 variants; they compete with C's pick on
                   the same older-half rule.

HOW IT IS JUDGED - on the NEWER half, which played no part in any pick:
    lift = newer-half mean R (improved) - newer-half mean R (original)

THE LUCK CHECK. The identical A-B-C(-D) procedure is run with the rule's
entries moved to random live bars (same count per timeframe), `SEEDS` times.
Gold rose a lot in this window, so a trend filter or a wide target helps ANY
long-gold entry; the question is whether it helps THIS one more than that.

AN IMPROVEMENT IS REAL only if all three hold:
    1. newer-half lift > 0
    2. lift above the random-entry lifts' 95th percentile (27 ideas at 95%
       expect ~1.4 false passes - said here so nobody reads one as a find)
    3. full-window pass rate's band not below the original's

    python -m factory.improve grid      # stages A-C, real entries
    python -m factory.improve ai        # stage D, one model call per idea
    python -m factory.improve null      # the luck check, both procedures
    python -m factory.improve table     # the left/right table
"""
from __future__ import annotations

import hashlib
import json
import sys
from concurrent.futures import ProcessPoolExecutor
from dataclasses import replace
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from factory import build, cells, check, queue                       # noqa: E402
from factory.rescore import _specs, _term, from_record                # noqa: E402
from factory.spec import Condition, Strategy                          # noqa: E402
from factory.tweak import _pace, _stats                               # noqa: E402

LIST = queue.DIR / "step8_list.json"
OUT = queue.DIR / "improve.json"
CACHE = queue.DIR / "improve_cache"
TFS = ("15m", "1h", "4h")
PER_HOUR = {"15m": 4.0, "1h": 1.0, "4h": 0.25}
MIN_OLD, MIN_TPD, MIN_KEEP = 30, 0.1, 0.30
STOPS = (1.0, 1.5, 2.0, 3.0, 5.0)
TARGETS = (1.5, 2.0, 3.0, 4.0, 6.0, 10.0)
HOLDS = (0.5, 1.0, 2.0)
SEEDS = 40
#: Wall-clock cap on a trade's life, in hours. None = the original search.
#: Kris, 2026-10-09: "maximum 24h hold" - a 259h average hold is investing.
MAX_HOURS: float | None = None
TABLE = queue.DIR / "IMPROVE.md"


def capbars(tf: str, bars: int) -> int:
    b = int(min(480, max(4, round(bars))))
    return b if MAX_HOURS is None else int(min(b, MAX_HOURS * PER_HOUR[tf]))

#: Written for a LONG. `_mirror` flips above/below for a short (hours stay).
FILTERS = {
    "above EMA50":            ["price above ema50"],
    "below EMA50 (pullback)": ["price below ema50"],
    "above EMA200":           ["price above ema200"],
    "above SMA200":           ["price above sma200"],
    "EMA50 over EMA200":      ["ema50 above ema200"],
    "EMA50 rising":           ["ema50 above ema50[10]"],
    "SMA200 rising":          ["sma200 above sma200[20]"],
    "above VWAP24":           ["price above vwap24"],
    "below VWAP24 (pullback)": ["price below vwap24"],
    "above VWAP96":           ["price above vwap96"],
    "VWAP24 rising":          ["vwap24 above vwap24[6]"],
    "4h candle green":        ["htf_closex4 above htf_openx4"],
    "daily candle green":     ["htf_closex24 above htf_openx24"],
    "RSI14 over 50":          ["rsi14 above 50"],
    "ADX14 over 20":          ["adx14 above 20"],
    "ADX14 over 25":          ["adx14 above 25"],
    "ADX14 under 20":         ["adx14 below 20"],
    "vol expanding":          ["atr14 above atr100"],
    "vol quiet":              ["atr14 below atr100"],
    "volume over avg":        ["rvol20 above 1"],
    "volume 1.5x":            ["rvol20 above 1.5"],
    "Asia 00-07":             ["hour below 6.5"],
    "London 07-12":           ["hour above 6.5", "hour below 11.5"],
    "New York 12-17":         ["hour above 11.5", "hour below 16.5"],
    "London+NY 07-17":        ["hour above 6.5", "hour below 16.5"],
    "not Asia 07-21":         ["hour above 6.5", "hour below 20.5"],
    "late 17-24":             ["hour above 16.5"],
}
_FLIP = {"above": "below", "below": "above",
         "cross_above": "cross_below", "cross_below": "cross_above"}


def cond(text: str) -> Condition:
    left, op, right = text.split(" ")
    return Condition(_term(left), op, _term(right))


def _mirror(c: Condition, side: str) -> Condition:
    if side == "long" or c.left.kind == "hour":
        return c
    return replace(c, op=_FLIP[c.op])


def filter_conds(name: str, side: str) -> tuple[Condition, ...]:
    return tuple(_mirror(cond(t), side) for t in FILTERS[name])


# --------------------------------------------------------------------------
# Signals and masks, cached on disk so the luck-check workers share them.
# --------------------------------------------------------------------------
def _key(*parts) -> str:
    return hashlib.sha1("|".join(map(str, parts)).encode()).hexdigest()[:16]


def _frame(market: str, tf: str):
    return cells.load(market, tf).reset_index(drop=True)


def mask(market: str, tf: str, conds: tuple[Condition, ...]) -> np.ndarray:
    """Bars where all `conds` hold. Built through `build.series`, so it reads
    nothing a strategy could not."""
    if not conds:
        return np.ones(len(_frame(market, tf)), bool)
    p = CACHE / f"m_{market}_{tf}_{_key(*[c.label() for c in conds])}.npy"
    if p.exists():
        return np.load(p)
    fire, _ = build.series(Strategy(name="filter", side="long", entry=conds),
                           _frame(market, tf))
    CACHE.mkdir(parents=True, exist_ok=True)
    np.save(p, fire)
    return fire


def signals(s: Strategy, market: str, tf: str) -> tuple[np.ndarray, np.ndarray]:
    p = CACHE / f"s_{market}_{tf}_{_key(s.label())}.npz"
    if p.exists():
        z = np.load(p)
        return z["fire"], z["atr"]
    fire, atr = build.series(s, _frame(market, tf))
    CACHE.mkdir(parents=True, exist_ok=True)
    np.savez(p, fire=fire, atr=atr)
    return fire, atr


def _job_mask(a):
    mask(*a)
    return 1


def _job_sig(a):
    signals(*a)
    return 1


# --------------------------------------------------------------------------
# One search. `fires` is {tf: (fire, atr)} - the real rule's, or random.
# --------------------------------------------------------------------------
class Ctx:
    def __init__(self, s: Strategy, market: str, tf0: str):
        self.s, self.market, self.tf0 = s, market, tf0
        self.cost = cells.cost_bps(market)
        self.frames = {tf: _frame(market, tf) for tf in TFS}
        self.mid = {tf: len(f) // 2 for tf, f in self.frames.items()}
        self.old_days = {tf: check.trading_days(cells.load(market, tf)) / 2 for tf in TFS}

    def hold_for(self, tf: str) -> int:
        return capbars(tf, self.s.max_hold * PER_HOUR[tf] / PER_HOUR[self.tf0])

    def run(self, v: Strategy, tf: str, fire, atr) -> dict:
        tr = build.run(v, self.frames[tf], cost_bps=self.cost, signals=(fire, atr))
        r = np.array([t.r for t in tr], dtype=float)
        e = np.array([t.entry_bar for t in tr], dtype=int)
        old, new = _stats(r[e < self.mid[tf]]), _stats(r[e >= self.mid[tf]])
        old["tpd"] = old["n"] / self.old_days[tf]
        return {"old": old, "new": new, "trades": tr}

    @staticmethod
    def ok(x: dict, floor: int = 0) -> bool:
        o = x["old"]
        return (o["n"] >= max(MIN_OLD, floor) and o["tpd"] >= MIN_TPD
                and o["pf"] is not None)


def _best(rows: list[dict], fallback: dict, floor: int = 0) -> dict:
    ok = [x for x in rows if Ctx.ok(x, floor)]
    return max(ok, key=lambda x: x["old"]["pf"]) if ok else fallback


def search(ctx: Ctx, fires: dict, ai: list[dict] | None = None) -> dict:
    """Stages A-C, then D if `ai` variants are given. Returns base, grid, final."""
    s = ctx.s
    base_v = replace(s, max_hold=capbars(ctx.tf0, s.max_hold))
    base = {**ctx.run(base_v, ctx.tf0, *fires[ctx.tf0]),
            "tf": ctx.tf0, "filter": "none", "exits": "original", "v": base_v}
    # A. timeframe
    rows = [base]
    for tf in TFS:
        if tf == ctx.tf0:
            continue
        v = replace(s, max_hold=ctx.hold_for(tf))
        rows.append({**ctx.run(v, tf, *fires[tf]), "tf": tf, "filter": "none",
                     "exits": "original", "v": v})
    a = _best(rows, base)
    tf, va = a["tf"], a["v"]
    fire, atr = fires[tf]
    # B. one filter
    rows = [a]
    for name in FILTERS:
        fc = filter_conds(name, s.side)
        m = mask(ctx.market, tf, fc)
        rows.append({**ctx.run(va, tf, fire & m, atr), "tf": tf, "filter": name,
                     "exits": "original", "v": replace(va, entry=va.entry + fc),
                     "_fire": fire & m})
    b = _best(rows, a, floor=int(MIN_KEEP * a["old"]["n"]))
    bfire = b.get("_fire", fire)
    # C. exits
    rows = [b]
    for st in STOPS:
        for tg in TARGETS:
            for h in HOLDS:
                mh = capbars(tf, b["v"].max_hold * h)
                v = replace(b["v"], stop_atr=st, target_atr=tg, max_hold=mh)
                rows.append({**ctx.run(v, tf, bfire, atr), "tf": tf,
                             "filter": b["filter"], "exits": f"stop{st:g} tgt{tg:g} hold{mh}",
                             "v": v})
    grid = _best(rows, b)
    final = grid
    # D. the model's variants, on the same older-half rule
    if ai:
        rows = [grid]
        for k, x in enumerate(ai):
            t = x["tf"]
            m = mask(ctx.market, t, x["add"])
            f, at = fires[t]
            v = replace(s, entry=s.entry + x["add"], stop_atr=x["stop_atr"],
                        target_atr=x["target_atr"], max_hold=capbars(t, x["max_hold"]))
            rows.append({**ctx.run(v, t, f & m, at), "tf": t, "filter": f"AI {k+1}: {x['why'][:60]}",
                         "exits": f"stop{x['stop_atr']:g} tgt{x['target_atr']:g} hold{x['max_hold']}",
                         "v": v})
        final = _best(rows, grid)
    return {"base": base, "grid": grid, "final": final}


def _lift(res: dict, key: str) -> float:
    a, b = res["base"]["new"]["mean"], res[key]["new"]["mean"]
    return np.nan if a is None or b is None else b - a


# --------------------------------------------------------------------------
def load() -> list[tuple[dict, Strategy, str, str]]:
    rows = {r["name"]: r for r in queue.rows(queue.DIR / "ideas.jsonl")}
    specs = _specs()
    out = []
    for x in json.loads(LIST.read_text()):
        r = rows.get(x["name"]) or x
        s = specs.get((x["name"], x["idea"])) or from_record({**r, "idea": x["idea"]})
        m, tf = x["cell"].split()
        out.append((x, s, m, tf))
    return out


def warm(items) -> None:
    jobs_m = {(m, tf, filter_conds(n, s.side)) for _, s, m, _ in items
              for tf in TFS for n in FILTERS}
    jobs_s = [(s, m, tf) for _, s, m, _ in items for tf in TFS]
    with ProcessPoolExecutor(max_workers=check.workers()) as pool:
        list(pool.map(_job_mask, sorted(jobs_m, key=str)))
        list(pool.map(_job_sig, jobs_s))


def _summ(x: dict, dated) -> dict:
    full = _stats(np.array([t.r for t in x["trades"]], dtype=float))
    return {"tf": x["tf"], "filter": x["filter"], "exits": x["exits"],
            "rule": x["v"].label(), "stop_atr": x["v"].stop_atr,
            "target_atr": x["v"].target_atr, "max_hold": x["v"].max_hold,
            "old": x["old"], "new": x["new"], "full": full,
            "tpd": round(len(x["trades"]) / check.trading_days(dated), 3),
            "pace": _pace(x["trades"], dated)}


def _real(item, ai=None) -> dict:
    x, s, m, tf0 = item
    ctx = Ctx(s, m, tf0)
    fires = {tf: signals(s, m, tf) for tf in TFS}
    res = search(ctx, fires, ai)
    out = {"name": x["name"], "by": x["by"], "market": m}
    for k in ("base", "grid", "final"):
        out[k] = _summ(res[k], cells.load(m, res[k]["tf"]))
    out["lift_grid"], out["lift_final"] = _lift(res, "grid"), _lift(res, "final")
    out["top_old"] = []                    # what the model is shown: OLDER half only
    return out


def _null(a):
    item, ai, seed = a
    x, s, m, tf0 = item
    ctx = Ctx(s, m, tf0)
    rng = np.random.default_rng(seed)
    fires = {}
    for tf in TFS:
        f, atr = signals(s, m, tf)
        live = np.flatnonzero(ctx.frames[tf]["volume"].values > 0)
        r = np.zeros_like(f)
        r[rng.choice(live, size=min(int(f.sum()), len(live)), replace=False)] = True
        fires[tf] = (r, atr)
    res = search(ctx, fires, ai)
    return _lift(res, "grid"), _lift(res, "final")


# --------------------------------------------------------------------------
def cmd_grid() -> None:
    items = load()
    warm(items)
    with ProcessPoolExecutor(max_workers=check.workers()) as pool:
        res = list(pool.map(_real, items))
    OUT.write_text(json.dumps(res, indent=1, default=str))
    for r in res:
        print(f"{r['name'][:44]:44} {r['base']['tf']:>3}->{r['grid']['tf']:3} "
              f"{r['grid']['filter'][:22]:22} {r['grid']['exits']:24} "
              f"lift {r['lift_grid']:+.3f}", flush=True)


AI_PROMPT = """You are improving ONE trading rule. You may only use the grammar below.

RULE: {rule}
MARKET: {market}, timeframe {tf}, exits stop {stop} ATR, target {tgt} ATR, max hold {hold} bars.
WHAT IT IS MEANT TO CAPTURE: {note}

RESULTS ON THE OLDER HALF OF THE DATA (the newer half is hidden from you on
purpose; profit factor after costs, n = trades, mean = average R per trade):
{table}

Propose up to 6 variants that could make THIS rule better for a prop-firm
evaluation (pass an 8% target before a 6% drawdown, 3% daily cap) - fewer bad
trades, better exits, a better timeframe or session. Each variant ADDS 1-2
conditions to the rule (the rule's own conditions always stay) and may change
the exits and timeframe. Prefer reasons rooted in why the rule works over
fitting the table.

GRAMMAR
{grammar}
  hour = UTC hour of the bar, 0-23 (use with above/below, e.g. hour above 6.5)

Reply with a JSON array only, each item:
{{"tf": "15m"|"1h"|"4h",
  "add": [{{"left": {{"kind": "ema", "length": 200}}, "op": "above"|"below"|"cross_above"|"cross_below",
           "right": {{"kind": "const", "value": 50}}, "hold": 1}}],
  "stop_atr": 0.5-5, "target_atr": 0.5-10, "max_hold": 4-480,
  "why": "one sentence"}}"""


def _ai_one(r: dict, s: Strategy) -> tuple[list[dict], list[str]]:
    from factory.sources import agent
    tab = "\n".join(f"  {x['label']:70} PF {x['pf']} n {x['n']} mean {x['mean']}"
                    for x in r["top_old"])
    prompt = AI_PROMPT.format(rule=s.label(), market=r["market"], tf=r["base"]["tf"],
                              stop=s.stop_atr, tgt=s.target_atr, hold=s.max_hold,
                              note=(s.note or r["name"])[:300], table=tab,
                              grammar=agent._grammar())
    out = agent._call(prompt, agent.CLI_MODEL, agent.TIMEOUT)
    good, bad = [], []
    for k, it in enumerate(agent.parse(out)[:6]):
        try:
            if it.get("tf") not in TFS:
                raise ValueError(f"tf {it.get('tf')!r}")
            add = []
            for c in it.get("add") or []:
                left = (_hour() if (c.get("left") or {}).get("kind") == "hour"
                        else agent._term(c.get("left"), "left"))
                right = agent._term(c.get("right"), "right")
                add.append(Condition(left, c["op"], right, hold=int(c.get("hold", 1) or 1)))
            if not 1 <= len(add) <= 2:
                raise ValueError("add must be 1-2 conditions")
            st, tg, mh = float(it["stop_atr"]), float(it["target_atr"]), int(it["max_hold"])
            if not (0.5 <= st <= 5 and 0.5 <= tg <= 10 and 4 <= mh <= 480):
                raise ValueError("exits out of range")
            good.append({"tf": it["tf"], "add": tuple(add), "stop_atr": st,
                         "target_atr": tg, "max_hold": mh, "why": str(it.get("why", ""))})
        except Exception as exc:                       # noqa: BLE001
            bad.append(f"variant {k+1}: {exc}")
    return good, bad


def _hour():
    from factory.spec import Term
    return Term("hour")


def _ai_to_json(v: dict) -> dict:
    return {**v, "add": [c.label() for c in v["add"]]}


def _ai_from_json(v: dict) -> dict:
    return {**v, "add": tuple(cond(t) for t in v["add"])}


def _top_old(item) -> list[dict]:
    """The grid's older-half table for one idea - all the model is shown."""
    x, s, m, tf0 = item
    ctx = Ctx(s, m, tf0)
    fires = {tf: signals(s, m, tf) for tf in TFS}
    rows = []
    for tf in TFS:
        v = replace(s, max_hold=ctx.hold_for(tf))
        o = ctx.run(v, tf, *fires[tf])["old"]
        rows.append({"label": f"[{tf}] as is", **o})
        for name in FILTERS:
            fc = filter_conds(name, s.side)
            o = ctx.run(v, tf, fires[tf][0] & mask(m, tf, fc), fires[tf][1])["old"]
            rows.append({"label": f"[{tf}] + {name}", **o})
    rows = [r for r in rows if r["n"] >= MIN_OLD and r["pf"] is not None]
    rows.sort(key=lambda r: -r["pf"])
    return [{"label": r["label"], "pf": round(r["pf"], 2), "n": r["n"],
             "mean": round(r["mean"], 3)} for r in rows[:15]]


def cmd_ai() -> None:
    items = load()
    res = json.loads(OUT.read_text())
    with ProcessPoolExecutor(max_workers=check.workers()) as pool:
        tops = list(pool.map(_top_old, items))
    ai_all = {}
    for item, r, top in zip(items, res, tops):
        r["top_old"] = top
        try:
            good, bad = _ai_one(r, item[1])
        except Exception as exc:                       # noqa: BLE001
            good, bad = [], [f"call failed: {exc}"]
        ai_all[r["name"]] = [_ai_to_json(v) for v in good]
        r["ai_rejected"] = bad
        print(f"{r['name'][:44]:44} AI variants {len(good)} rejected {len(bad)}", flush=True)
    with ProcessPoolExecutor(max_workers=check.workers()) as pool:
        finals = list(pool.map(_real, items,
                               [[_ai_from_json(v) for v in ai_all[x["name"]]] for x, *_ in items]))
    for r, f in zip(res, finals):
        r["final"], r["lift_final"] = f["final"], f["lift_final"]
        r["ai"] = ai_all[r["name"]]
    OUT.write_text(json.dumps(res, indent=1, default=str))


def cmd_null() -> None:
    items = load()
    res = json.loads(OUT.read_text())
    jobs = [(item, [_ai_from_json(v) for v in r.get("ai", [])], seed)
            for item, r in zip(items, res) for seed in range(SEEDS)]
    with ProcessPoolExecutor(max_workers=check.workers()) as pool:
        out = list(pool.map(_null, jobs, chunksize=2))
    for i, r in enumerate(res):
        g = np.array([o[0] for o in out[i * SEEDS:(i + 1) * SEEDS]], dtype=float)
        f = np.array([o[1] for o in out[i * SEEDS:(i + 1) * SEEDS]], dtype=float)
        for key, arr in (("grid", g), ("final", f)):
            lift = r[f"lift_{key}"]
            p95 = float(np.nanpercentile(arr, 95))
            bp, tp = r["base"]["pace"], r[key]["pace"]
            c3 = (not bp.get("band") or not tp.get("band")
                  or tp["band"].get("pass_hi", 1) >= bp["band"].get("pass_lo", 0))
            r[f"null_{key}"] = {"p95": p95, "median": float(np.nanmedian(arr)),
                                "p": float(np.mean(arr >= lift)) if lift == lift else None,
                                "checks": [bool(lift > 0), bool(lift > p95), bool(c3)],
                                "real": bool(lift > 0 and lift > p95 and c3)}
        print(f"{r['name'][:44]:44} grid {r['lift_grid']:+.3f} (p95 {r['null_grid']['p95']:+.3f}) "
              f"final {r['lift_final']:+.3f} (p95 {r['null_final']['p95']:+.3f}) "
              f"real={r['null_final']['real']}", flush=True)
    OUT.write_text(json.dumps(res, indent=1, default=str))


def cmd_table() -> None:
    """Left: the idea as it is. Right: the improved version and whether the
    improvement beat the random-entry search. Written to IMPROVE.md."""
    res = json.loads(OUT.read_text())

    def side(x):
        p = x["pace"] or {}
        return (f"{p.get('pass_pct', '-')}% | {p.get('days', '-')} | "
                f"{p.get('accounts', '-')} | {x['full']['pf'] or 0:.2f} | {x['tpd']:.2f}")
    lines = ["| # | strategy | cell | pass | days | accts | PF | tpd || change | "
             "pass | days | accts | PF | tpd | luck check |",
             "|---|---|---|---|---|---|---|---||---|---|---|---|---|---|---|"]
    for i, r in enumerate(res, 1):
        b, f, n = r["base"], r["final"], r.get("null_final", {})
        ch = []
        if f["tf"] != b["tf"]:
            ch.append(f"tf {f['tf']}")
        if f["filter"] != "none":
            ch.append(f["filter"])
        if f["exits"] != "original":
            ch.append(f["exits"])
        verdict = ("REAL" if n.get("real") else
                   f"luck (p={n['p']:.2f})" if n.get("p") is not None else "-")
        lines.append(f"| {i} | {r['name'][:40]}{' (K)' if r['by'] == 'kris' else ''} | "
                     f"{r['market']} {b['tf']} | {side(b)} || {'; '.join(ch) or 'none'} | "
                     f"{side(f)} | {verdict} |")
    text = "\n".join(lines)
    TABLE.write_text(
        "# Step 8 - improvements (factory/improve.py)\n\nLeft: as it is. Right: best "
        "version found (picked on older half). Luck check: same search on random "
        "entries; REAL = newer-half gain beats 95% of random.\n\n" + text + "\n")
    print(text)


def main(argv=None) -> int:
    cmd = (argv or sys.argv[1:] or ["grid"])[0]
    {"grid": cmd_grid, "ai": cmd_ai, "null": cmd_null, "table": cmd_table}[cmd]()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
