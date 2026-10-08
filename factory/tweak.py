"""TWEAK THE BEST FEW - can a small change make a board leader better?

Kris, 2026-10-08: *"pick 5-8 best candidates ... try to tweak them a little bit
to make them even better"*.

PRE-REGISTERED BEFORE THE FIRST RUN (2026-10-08). Nothing below was changed
after seeing a number.

CANDIDATES. The board's top seven by `dashboard.score10`, plus the best
non-gold rule (EURUSD short wpr5), because seven of the top seven are gold
longs and a tweak that only works on gold longs may just be the gold uptrend.

THE TWEAKS, per candidate, on its own headline market and timeframe:
    stop   1.0 1.5 2.0 2.5 3.0 ATR
    target 1.5 2.0 3.0 4.0 6.0 ATR
    hold   half, same, double the original bars
    = 75 exit variants, plus every indicator length x0.75 and x1.25 at the
    original exits = 77 variants. The original is one of them.

HOW A WINNER IS PICKED - on the OLDER half of the 3-year window only:
    highest profit factor at 1x cost, among variants with at least 30 trades
    and at least 70% of the original's trade count (so a tweak cannot win by
    trading less).

HOW IT IS JUDGED - on the NEWER half, which played no part in the pick:
    lift = newer-half mean R (tweak) - newer-half mean R (original).

THE LUCK CHECK. The same pick-on-old / judge-on-new procedure is run on the
SAME rule with its entries moved to random bars (same side, same count,
`check.control_means`'s construction), 20 seeds. That asks: does tweaking
the exits help THIS signal, or does it help any long-gold entry? (Wider
targets on gold longs help random entries too - gold rose 123%.)

A TWEAK IS KEPT only if all three hold:
    1. newer-half lift > 0
    2. lift above the random-entry lift's 90th percentile
    3. full 3-year profit factor >= the original's, and pass-rate band not
       below the original's (overlapping is fine - it must not be worse)

    python -m factory.tweak            # all eight, writes factory/runs/tweak.json
"""
from __future__ import annotations

import json
import sys
from concurrent.futures import ProcessPoolExecutor
from dataclasses import replace
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core import noiseband, riskladder                                # noqa: E402
from factory import build, cells, check, dashboard, queue             # noqa: E402
from factory.rescore import _specs, from_record                       # noqa: E402
from factory.spec import Strategy                                     # noqa: E402

CANDIDATES = (
    "EMA50/200 trend + breadth proxy",
    "Hemant gold liquidity sweep long",
    "Adaptive ATR dual-trend long",
    "50-bar breakout in uptrend",
    "Neural Edge Scalper",
    "3H sweep then swing-high break (long)",
    "Triaxial consensus long (trend stack + RSI momentum)",
    "short wpr5 top of range in downtrend",
)
STOPS = (1.0, 1.5, 2.0, 2.5, 3.0)
TARGETS = (1.5, 2.0, 3.0, 4.0, 6.0)
HOLDS = (0.5, 1.0, 2.0)
SCALES = (0.75, 1.25)
MIN_TRADES, MIN_SHARE = 30, 0.70
NULL_SEEDS = 20
OUT = queue.DIR / "tweak.json"


def _scaled(s: Strategy, k: float) -> Strategy:
    def t(term):
        return replace(term, length=max(2, round(term.length * k))) if term.length else term
    entry = tuple(replace(c, left=t(c.left), right=t(c.right)) for c in s.entry)
    return replace(s, entry=entry)


def variants(s: Strategy) -> list[tuple[str, Strategy]]:
    out = []
    for st in STOPS:
        for tg in TARGETS:
            for h in HOLDS:
                out.append((f"stop{st:g} tgt{tg:g} hold{max(1, round(s.max_hold*h))}",
                            replace(s, stop_atr=st, target_atr=tg,
                                    max_hold=max(1, round(s.max_hold * h)))))
    out += [(f"lengths x{k:g}", _scaled(s, k)) for k in SCALES]
    out.append(("original", s))
    return out


def _stats(r: np.ndarray) -> dict:
    if len(r) == 0:
        return {"n": 0, "pf": None, "mean": None}
    w, l = r[r > 0].sum(), -r[r <= 0].sum()
    return {"n": int(len(r)), "pf": float(w / l) if l else None, "mean": float(r.mean())}


def _halves(trades, mid: int) -> tuple[np.ndarray, np.ndarray]:
    r = np.array([t.r for t in trades], dtype=float)
    e = np.array([t.entry_bar for t in trades], dtype=int)
    return r[e < mid], r[e >= mid]


def _pick(rows: list[dict], base_n_old: int) -> dict:
    ok = [x for x in rows if x["old"]["n"] >= max(MIN_TRADES, MIN_SHARE * base_n_old)
          and x["old"]["pf"] is not None]
    return max(ok, key=lambda x: x["old"]["pf"]) if ok else next(
        x for x in rows if x["name"] == "original")


def _grid(vs, frame, cost, mid, signals=None) -> list[dict]:
    rows = []
    sig_cache = {}
    for name, v in vs:
        if signals is not None and name.startswith("lengths"):
            continue                      # random entries have no lengths to scale
        if signals is None:
            key = v.entry
            if key not in sig_cache:
                sig_cache[key] = build.series(v, frame)
            sig = sig_cache[key]
        else:
            sig = signals
        tr = build.run(v, frame, cost_bps=cost, signals=sig)
        old, new = _halves(tr, mid)
        rows.append({"name": name, "old": _stats(old), "new": _stats(new),
                     "strategy": v, "trades": tr})
    return rows


def _null_job(args):
    s, market, tf, seed = args
    frame = cells.load(market, tf).reset_index(drop=True)
    cost, mid = cells.cost_bps(market), len(frame) // 2
    fire, atr = build.series(s, frame)
    rng = np.random.default_rng(seed)
    sh = np.zeros_like(fire)
    sh[rng.choice(len(fire), size=int(fire.sum()), replace=False)] = True
    rows = _grid(variants(s), frame, cost, mid, signals=(sh, atr))
    base = next(x for x in rows if x["name"] == "original")
    pick = _pick(rows, base["old"]["n"])
    if base["new"]["mean"] is None or pick["new"]["mean"] is None:
        return np.nan
    return pick["new"]["mean"] - base["new"]["mean"]


def _pace(trades, frame) -> dict:
    if len(trades) < 2:
        return {}
    r = np.array([t.r for t in trades], dtype=float)
    ts = pd.DatetimeIndex(frame.index[[t.exit_bar for t in trades]])
    daily = pd.Series(r, index=ts).resample("1D").sum()
    rows = riskladder.ladder(daily, r)
    best = riskladder.pick(rows) if rows else None
    if not best or not best.get("expected_days"):
        return {}
    b = noiseband.band(daily, best["risk"]) or {}
    return {"risk_pct": round(best["risk"] * 100, 2),
            "pass_pct": round(best["pass_rate"] * 100, 1),
            "days": round(best["expected_days"], 1),
            "accounts": round(1 / best["pass_rate"], 2),
            "band": b}


def _full(trades) -> dict:
    return _stats(np.array([t.r for t in trades], dtype=float))


def study(s: Strategy, market: str, tf: str, pool) -> dict:
    dated = cells.load(market, tf)
    frame = dated.reset_index(drop=True)
    cost, mid = cells.cost_bps(market), len(frame) // 2
    rows = _grid(variants(s), frame, cost, mid)
    base = next(x for x in rows if x["name"] == "original")
    pick = _pick(rows, base["old"]["n"])
    lift = (pick["new"]["mean"] or 0) - (base["new"]["mean"] or 0)
    nulls = np.array(list(pool.map(_null_job,
                                   [(s, market, tf, seed) for seed in range(NULL_SEEDS)])))
    p90 = float(np.nanpercentile(nulls, 90))
    bp, tp = _pace(base["trades"], dated), _pace(pick["trades"], dated)
    bf, tf_ = _full(base["trades"]), _full(pick["trades"])
    c1 = lift > 0
    c2 = lift > p90
    c3 = (tf_["pf"] or 0) >= (bf["pf"] or 0) and (
        not bp.get("band") or not tp.get("band")
        or tp["band"].get("pass_hi", 1) >= bp["band"].get("pass_lo", 0))
    return {"market": market, "tf": tf, "idea": s.label(),
            "original": {"exits": f"stop{s.stop_atr:g} tgt{s.target_atr:g} hold{s.max_hold}",
                         "old": base["old"], "new": base["new"], "full": bf, "pace": bp},
            "pick": {"name": pick["name"], "idea": pick["strategy"].label(),
                     "old": pick["old"], "new": pick["new"], "full": tf_, "pace": tp},
            "lift_new": lift, "null_lifts": [None if np.isnan(x) else float(x) for x in nulls],
            "null_p90": p90, "checks": [bool(c1), bool(c2), bool(c3)],
            "kept": bool(c1 and c2 and c3),
            "per_day": round(len(pick["trades"]) / check.trading_days(dated), 3)}


def _load() -> list[tuple[str, Strategy, str, str]]:
    rows = [json.loads(l) for l in (queue.DIR / "ideas.jsonl").read_text().splitlines()
            if l.strip()]
    view = {x["script"]: x for x in dashboard.scripts_view(rows)}
    specs = _specs()
    out = []
    for name in CANDIDATES:
        x = view[name]
        s = specs.get((x["name"], x["idea"])) or from_record(x)
        k = x["score"]
        out.append((name, s, k["market"], k["tf"]))
    return out


def main() -> int:
    res = []
    with ProcessPoolExecutor(max_workers=min(NULL_SEEDS, check.workers())) as pool:
        for name, s, m, tf in _load():
            r = study(s, m, tf, pool)
            r["script"] = name
            res.append(r)
            o, p = r["original"], r["pick"]
            print(f"{name[:40]:40} {m} {tf:4} pick={p['name']:24} "
                  f"newhalf {o['new']['mean']:+.3f}->{p['new']['mean']:+.3f} "
                  f"lift {r['lift_new']:+.3f} null90 {r['null_p90']:+.3f} "
                  f"checks {r['checks']} KEPT={r['kept']}", flush=True)
            OUT.write_text(json.dumps(res, indent=1, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


# --------------------------------------------------------------------------
# CONFIRMATION, pre-registered 2026-10-08 after the main run and before this
# was run. Only for a candidate that was KEPT. One kept of eight is what a
# 90th-percentile check gives by luck (0.8 expected), so it has to travel:
#   A. the same tweak beats the original's mean R on >= 4 of the 6 standard
#      markets, same timeframe            (kills it if not)
#   B. on gold's older years (the 5-year holdout before the 3-year window)
#      the tweak still beats the original  (a note only - Kris, 2026-10-06)
# --------------------------------------------------------------------------
def confirm(script: str) -> dict:
    from core import universe
    r = next(x for x in json.loads(OUT.read_text()) if x["script"] == script)
    name, s, m, tf = next(c for c in _load() if c[0] == script)
    t = dict(variants(s))[r["pick"]["name"]]
    rows = []
    for mk in universe.STANDARD:
        f = cells.load(mk, tf).reset_index(drop=True)
        cost = cells.cost_bps(mk)
        a = _full(build.run(s, f, cost_bps=cost))
        b = _full(build.run(t, f, cost_bps=cost))
        rows.append({"market": mk, "original": a, "tweak": b,
                     "better": (b["mean"] or -9) > (a["mean"] or -9)})
    old = cells.holdout(m, tf)
    old = old[old.index < cells.load(m, tf).index[0]].reset_index(drop=True)
    cost = cells.cost_bps(m)
    oa, ob = _full(build.run(s, old, cost_bps=cost)), _full(build.run(t, old, cost_bps=cost))
    wins = sum(x["better"] for x in rows)
    return {"script": script, "tweak": r["pick"]["name"], "markets": rows,
            "markets_better": wins, "A_pass": wins >= 4,
            "older_years": {"original": oa, "tweak": ob,
                            "better": (ob["mean"] or -9) > (oa["mean"] or -9)}}
