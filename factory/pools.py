"""POOLS — several finished strategies traded side by side on one evaluation.

Kris, 2026-10-07: *"make couple pools ... POOL 1 POOL 2 and POOL 3 ... different
combination of strategies to pass evaluation faster and safer"*.

HOW A POOL TRADES. Every leg risks the same fixed amount per trade (the
`riskladder.pick` rung, 2% floor) and the pool's day is the SUM of its legs'
days. Legs are NOT shrunk to share one budget: `CLAUDE.md` (H-012) measured
that equal-weighting divides R by the leg count and makes a book slower. The
price of summing is that several legs can lose on the same day, and the
simulation books that against the 3% daily cap like any other loss.

HONEST BY CONSTRUCTION. The 3-year window is split in half by date. Legs are
CHOSEN on the first half only; every headline number is the SECOND half, which
the chooser never saw. And the chooser is itself luck-checked: the same number
of legs drawn at random from the same candidates, 300 times, on the same
held-out half. A pool that does no better than a random pool was not chosen,
it was drawn.

    POOL 1  FAST    greedy, fewest expected days on the first half
    POOL 2  SAFE    greedy, highest pass rate (fewest accounts burned)
    POOL 3  SPREAD  one leg per market, best pass rate each: not all gold

    python -m factory.pools            # writes backtests/factory/pools.json
"""
from __future__ import annotations

import ast
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core import noiseband, riskladder                                 # noqa: E402
from factory import build, cells, queue                               # noqa: E402

OUT = queue.DIR / "pools.json"
MAX_LEGS = 5
RANDOM_POOLS = 300
#: Shipped H-027 rule on the HOUSE card at 2%, from README's NOW block.
BENCH = {"name": "H-027 VWAP breakout (shipped)", "eval_days": 23.8,
         "band": "19-33", "pass_pct": 54.7, "accounts": 1.83}


def _score(x: dict) -> dict | None:
    s = x.get("score")
    try:
        s = ast.literal_eval(s) if isinstance(s, str) else s
    except (ValueError, SyntaxError):
        return None
    return s or None


def candidates() -> list[dict]:
    """Every idea scored at step 7 whose exact rule is on file, on its
    headline cell. Repaired variants are not rebuildable from the records yet
    and are left out - the count is reported."""
    ideas = queue.rows(queue.DIR / "ideas.jsonl")
    surv = {}
    for line in (queue.SURVIVORS.read_text().splitlines()):
        if not line.strip():
            continue
        r = json.loads(line)
        if not r.get("carried"):
            surv[r["name"]] = line
    out, skipped = {}, set()
    for x in ideas:
        if not str(x.get("outcome", "")).startswith("scored"):
            continue
        s = _score(x)
        if not s or x["name"] not in surv:
            skipped.add(x["name"])
            continue
        out[x["name"]] = {"name": x["name"], "source": x.get("source"),
                          "idea": x.get("idea"), "side": x.get("side"),
                          "cell": s["cell"], "market": s["market"], "tf": s["tf"],
                          "strategy": queue._from_json(surv[x["name"]])}
    return list(out.values()), sorted(skipped - set(out))


def daily_series(c: dict, index: pd.DatetimeIndex) -> tuple[pd.Series, pd.Series]:
    """(R per day, trades per day) on a calendar-day index."""
    frame = cells.load(c["market"], c["tf"])
    trades = build.run(c["strategy"], frame.reset_index(drop=True),
                       cost_bps=cells.cost_bps(c["market"]))
    if not trades:
        z = pd.Series(0.0, index=index)
        return z, z
    r = np.array([t.r for t in trades], dtype=float)
    ts = pd.DatetimeIndex(frame.index[[t.exit_bar for t in trades]])
    s = pd.Series(r, index=ts)
    d = s.resample("1D").sum().reindex(index, fill_value=0.0)
    n = s.resample("1D").count().reindex(index, fill_value=0).astype(float)
    return d, n


def sim(daily: pd.Series, risk: float = riskladder.MIN_RISK) -> dict:
    """One evaluation sim at the 2% floor - the rung `riskladder.pick` lands
    on for every board number (it takes the LOWEST rung at or above the floor).
    Running the whole twelve-rung ladder inside a greedy search was 24x the
    work for the same answer."""
    one = riskladder.run_accounts(daily, risk)
    pr = one["pass_rate"]
    eq = daily.cumsum()
    return {"risk_pct": round(risk * 100, 2),
            "pass_pct": round(pr * 100, 1),
            "blown_pct": round((one["fail_max"] + one["fail_daily"]) * 100, 1),
            "eval_days": riskladder._expected(one),
            "median_days": one["median_days"],
            "accounts": round(1 / pr, 2) if pr else None,
            "max_dd_pct": round(float(np.min(eq - eq.cummax())) * risk * 100, 1),
            "_risk": risk}


def _days(m: dict) -> float:
    return m["eval_days"] if m["eval_days"] else 1e9


#: Per-leg risk a pool may choose. Capped at the 2% single-strategy floor: five
#: legs at 2% each is 10% on the table against a 3% daily cap, and the first run
#: of this file (2026-10-07) showed what that buys - 2.8 "expected days" with
#: 64.5% of accounts blown. Speed bought with blown accounts is the top-N lesson.
LEG_RISK = (0.0025, 0.005, 0.0075, 0.01, 0.0125, 0.015, 0.02)

#: The two goals. FAST: fewest expected days, but only if at least half the
#: accounts pass. SAFE: most accounts passing, as long as the median pass comes
#: inside 30 days. Each returns a sort key, lower is better.
def k_fast(m):
    return (0 if m["pass_pct"] >= 50 else 1, _days(m))


def k_safe(m):
    ok = m["median_days"] is not None and m["median_days"] <= 30
    return (0 if ok else 1, -m["pass_pct"], _days(m))


def best_risk(daily: pd.Series, key) -> dict:
    return min((sim(daily, r) for r in LEG_RISK), key=key)


def greedy(names, D, key) -> tuple[list[str], float]:
    chosen, best, risk = [], None, LEG_RISK[-1]
    while len(chosen) < MAX_LEGS:
        trial = []
        for n in names:
            if n not in chosen:
                m = best_risk(D[chosen + [n]].sum(axis=1), key)
                trial.append((key(m), n, m["_risk"]))
        if not trial:
            break
        k, n, r = min(trial)
        if best is not None and k >= best:
            break
        chosen.append(n); best = k; risk = r
    return chosen, risk


def spread(names, D, meta, key) -> tuple[list[str], float]:
    """Best single leg per market, then the best MAX_LEGS markets together."""
    per = {}
    for n in names:
        k = key(best_risk(D[n], key))
        mk = meta[n]["market"]
        if mk not in per or k < per[mk][0]:
            per[mk] = (k, n)
    legs = [n for _, n in sorted(per.values())[:MAX_LEGS]]
    return legs, best_risk(D[legs].sum(axis=1), key)["_risk"]


#: Trades per day per leg, filled in by `main`. Kept beside D rather than in it
#: so every selection step reads R and nothing else.
N: pd.DataFrame | None = None
#: Gross wins / gross losses per leg per day, for the pool's profit factor.
WIN: pd.DataFrame | None = None
LOSS: pd.DataFrame | None = None


def stats(D: pd.DataFrame, legs: list[str], risk: float) -> dict:
    d = D[legs].sum(axis=1)
    m = sim(d, risk)
    span = D.index
    if N is not None:
        m["trades"] = int(N.loc[span, legs].values.sum())
        m["trades_per_day"] = round(m["trades"] / len(span), 2)
        gw, gl = WIN.loc[span, legs].values.sum(), LOSS.loc[span, legs].values.sum()
        m["pf"] = round(gw / gl, 3) if gl else None
    eq = d.cumsum()
    m["r_per_day"] = round(float(d.mean()), 4)
    m["max_dd_r"] = round(float((eq - eq.cummax()).min()), 1)
    m["active_days_pct"] = round(100 * float((d != 0).mean()), 1)
    b = noiseband.band(d, risk)
    m["band"] = (f'{b["days_lo"]}-{b["days_hi"]}' if b and b.get("days_lo")
                 else None)
    return {k: v for k, v in m.items() if k[0] != "_"}


def main() -> int:
    cands, skipped = candidates()
    lo, hi = cells.common_window()
    idx = pd.date_range(lo.normalize(), hi.normalize(), freq="1D", tz="UTC")
    global N, WIN, LOSS
    ser = {c["name"]: daily_series(c, idx) for c in cands}
    D = pd.DataFrame({k: v[0] for k, v in ser.items()})
    N = pd.DataFrame({k: v[1] for k, v in ser.items()})
    # Day-level wins and losses: a pool's PF from daily sums understates
    # gross on days with both a winner and a loser, so it reads slightly low.
    WIN, LOSS = D.clip(lower=0), (-D).clip(lower=0)
    meta = {c["name"]: c for c in cands}
    mid = idx[len(idx) // 2]
    A, B = D[D.index < mid], D[D.index >= mid]
    # A leg must at least make money on the half it is chosen on.
    names = [n for n in D if A[n].sum() > 0]
    print(f"{len(cands)} candidates, {len(names)} positive on the first half, "
          f"{len(skipped)} repaired variants not rebuildable")

    pools = {
        "POOL 1": ("FAST", k_fast, *greedy(names, A, k_fast)),
        "POOL 2": ("SAFE", k_safe, *greedy(names, A, k_safe)),
        "POOL 3": ("SPREAD", k_safe, *spread(names, A, meta, k_safe)),
    }
    rng = np.random.default_rng(7)
    out = {"bench": BENCH, "split": str(mid.date()),
           "window": [str(lo.date()), str(hi.date())],
           "candidates": len(cands), "positive_first_half": len(names),
           "skipped_repaired": len(skipped), "pools": []}
    for pid, (kind, key, legs, risk) in pools.items():
        if not legs:
            continue
        held = stats(B, legs, risk)
        # LUCK CHECK: same leg count, random legs, risk chosen the same way on
        # the first half, scored on the same held-out half.
        rand = []
        for _ in range(RANDOM_POOLS):
            pick = list(rng.choice(names, size=len(legs), replace=False))
            r = best_risk(A[pick].sum(axis=1), key)["_risk"]
            rand.append(sim(B[pick].sum(axis=1), r))
        rd = np.array([_days(m) for m in rand])
        rp = np.array([m["pass_pct"] for m in rand])
        hd = held["eval_days"] or 1e9
        out["pools"].append({
            "id": pid, "kind": kind, "leg_risk_pct": round(risk * 100, 2),
            "legs": [{"name": n, "cell": meta[n]["cell"], "side": meta[n]["side"],
                      "idea": meta[n]["idea"], "source": meta[n]["source"],
                      "held_out": stats(B, [n], risk)} for n in legs],
            "chosen_on": stats(A, legs, risk),
            "held_out": held,
            "full": stats(D, legs, risk),
            "luck": {"random_pools": RANDOM_POOLS,
                     "random_days_median": (float(np.median(rd[rd < 1e9]))
                                            if (rd < 1e9).any() else None),
                     "random_pass_median": float(np.median(rp)),
                     "beats_random_days_pct": round(float((rd > hd).mean() * 100), 1),
                     "beats_random_pass_pct": round(float((rp < held["pass_pct"]).mean() * 100), 1)},
        })
        h, L = held, out["pools"][-1]["luck"]
        print(f"{pid} {kind:6s} {len(legs)} legs @ {risk*100:.2f}%  held-out {h['eval_days']}d "
              f"band {h['band']} pass {h['pass_pct']}% blown {h['blown_pct']}% "
              f"acc {h['accounts']} | beats random: days {L['beats_random_days_pct']:.0f}% "
              f"pass {L['beats_random_pass_pct']:.0f}%")
    OUT.write_text(json.dumps(out, indent=1, default=str))
    print("wrote", OUT)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
