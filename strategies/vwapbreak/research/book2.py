"""H-050 — the shipped rule on five markets, with the weighting H-012 never solved.

THE POINT. H-027 is traded on gold alone. The same rule, same folds, same costs
already scores on five markets: gold 15.3 expected days, silver 22.1, EURUSD
25.4, USDJPY 26.8, GBPUSD 43.9. Every one is positive. Trading one of them is a
choice nobody has tested against trading several.

WHY THIS IS NOT H-012. That study added legs to a book and got SLOWER - in-window
15.9 days, held out 130.7 - and its own conclusion names the reason and the gap:

    "Cause is DILUTION not correlation: the median leg has R/day -0.0013, and
    equal weighting divides the book's R by the leg count... Do not propose a
    wider universe as a cure for drawdown without solving the weighting first."

**Nobody solved the weighting.** H-012 weighted every leg equally, on a crypto
book whose median leg lost money. Here the legs are five markets that each make
money on their own, and the weights are chosen from TRAILING data only.

THE FOUR SCHEMES, fixed before any number:

  gold_only   the baseline. What Kris trades today.
  equal       H-012's scheme, included so the comparison is like for like.
  invvol      weight 1/sigma of the leg's trailing daily R. Risk parity.
  edge        weight by trailing R per day, negative legs dropped. The direct
              answer to H-012's dilution finding.

NO LOOK-AHEAD IN THE WEIGHTS. They are recomputed every quarter from the
**previous 12 months only**, the same train/test split the walk-forward already
uses. A weight computed on the whole sample would be the mistake H-012's own
write-up warns about one level up.

RISK IS HELD CONSTANT. Weights sum to 1, so one unit of book R means the same
account fraction as one unit of gold R. A book that looks better only because it
risks more is not better.

Run: .venv/bin/python strategies/vwapbreak/research/book2.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

from core.gates import judge                                       # noqa: E402
from core.markets import COSTS, EXEC_MODE, load                    # noqa: E402
from core.noiseband import band as nb_band                         # noqa: E402
from core.pipeline import Market, Pipeline                         # noqa: E402
from core.prop_rules import HOUSE                                  # noqa: E402
from core.riskladder import run_accounts                           # noqa: E402
from core.run_hypothesis import TF_BPH, _FixedGrid, window         # noqa: E402
from core.universe import STANDARD                                 # noqa: E402
from strategies.vwapbreak.strategy import STRATEGY                 # noqa: E402

TF = "1h"
LEGS = ["XAUUSD", "XAGUSD", "EURUSD", "GBPUSD", "USDJPY"]
RISKS = (0.01, 0.015, 0.02, 0.03, 0.04, 0.05, 0.06)
TRAIN_D = 365          # days of trailing history the weights see
STEP = "QE"            # weights refreshed quarterly


def leg_daily(sym: str, span) -> pd.Series:
    """Daily R for one market under the shipped floor-30 / top-5 rule."""
    df = load(sym, TF)
    df = df[(df.index >= span[0]) & (df.index <= span[1])]
    c = COSTS[sym]
    fee, slip = c.per_side(EXEC_MODE)
    pad = int(max(20, round(24 * 4 * TF_BPH[TF])) * 2)
    m = Market(sym=sym, tf=TF, df=df, fee_bps=fee, slip_bps=slip, pad_bars=pad)
    g = [dict(x) for x in STRATEGY.grid(TF)]
    for x in g:
        x["min_risk_bps"] = c.min_risk_bps
    tr = Pipeline(_FixedGrid(STRATEGY, g), floors=(30,), topn=(5,)).walk_forward(m).trades
    if not len(tr):
        return pd.Series(dtype=float), tr
    s = pd.Series(tr.r.values, index=pd.DatetimeIndex(tr.exit_ts)).resample("1D").sum()
    return s, tr


def weights(hist: pd.DataFrame, scheme: str) -> pd.Series:
    """Weights from TRAILING data only. Always sum to 1."""
    cols = hist.columns
    if scheme == "equal":
        w = pd.Series(1.0, index=cols)
    elif scheme == "invvol":
        sd = hist.std()
        w = 1.0 / sd.replace(0, np.nan)
        w = w.fillna(0.0)
    elif scheme == "edge":
        rpd = hist.mean()                      # R per day over the trailing window
        w = rpd.clip(lower=0.0)                # drop the legs that lost money
        if w.sum() <= 0:                       # nothing earned: fall back to equal
            w = pd.Series(1.0, index=cols)
    else:
        raise ValueError(scheme)
    t = w.sum()
    return w / t if t > 0 else pd.Series(1.0 / len(cols), index=cols)


def build(daily: pd.DataFrame, scheme: str) -> pd.Series:
    """Book R per day, weights refreshed quarterly from the prior 365 days."""
    out = []
    ends = pd.date_range(daily.index[0], daily.index[-1], freq=STEP, tz="UTC")
    for i, q_end in enumerate(ends):
        q_start = ends[i - 1] if i else daily.index[0]
        test = daily[(daily.index > q_start) & (daily.index <= q_end)]
        hist = daily[(daily.index <= q_start)
                     & (daily.index > q_start - pd.Timedelta(days=TRAIN_D))]
        if not len(test):
            continue
        if len(hist) < 60:                     # not enough history to weight on
            continue
        w = weights(hist, scheme)
        out.append((test * w).sum(axis=1))
    return pd.concat(out).sort_index() if out else pd.Series(dtype=float)


def score(daily: pd.Series, tag: str) -> dict:
    best = None
    for risk in RISKS:
        a = run_accounts(daily, risk, HOUSE)
        if not a["pass_rate"]:
            continue
        e = a["median_days"] / a["pass_rate"]
        if best is None or e < best["days"]:
            best = {"risk": risk * 100, "days": e,
                    "pass": a["pass_rate"] * 100,
                    "blown": (a["fail_max"] + a["fail_daily"]) * 100,
                    "band": nb_band(daily, risk, rules=HOUSE)}
    if best is None:
        return {"tag": tag, "days": None}
    b = best["band"] or {}
    return {"tag": tag, **best, "lo": b.get("days_lo"), "hi": b.get("days_hi"),
            "rday": float(daily.mean()), "sd": float(daily.std())}


def main() -> int:
    span = window(STANDARD, [TF])
    print(f"H-050 — the shipped rule on five markets. window {span[0].date()} "
          f"-> {span[1].date()}, HOUSE 8/3/6\n")
    daily, trades = {}, {}
    for sym in LEGS:
        s, tr = leg_daily(sym, span)
        if len(s):
            daily[sym], trades[sym] = s, tr
        print(f"  {sym}  {len(tr):5d} trades", flush=True)
    d = pd.DataFrame(daily).fillna(0.0).sort_index()

    print(f"\ncorrelation of daily R between legs (why a book could help):")
    print(d.corr().round(2).to_string())

    rows = []
    gold = d["XAUUSD"]
    rows.append(score(gold, "gold_only"))
    for scheme in ("equal", "invvol", "edge"):
        rows.append(score(build(d, scheme), scheme))

    print(f"\n{'scheme':11}{'risk':>7}{'days':>8}{'band':>12}{'pass%':>8}"
          f"{'blown%':>8}{'R/day':>9}")
    print("-" * 63)
    for r in rows:
        if not r.get("days"):
            print(f"{r['tag']:11}  no result"); continue
        bs = "%.0f-%.0f" % (r.get("lo") or 0, r.get("hi") or 0)
        print(f"{r['tag']:11}{r['risk']:>6.1f}%{r['days']:>8.1f}"
              f"{bs:>12}{r['pass']:>8.1f}"
              f"{r['blown']:>8.1f}{r['rday']:>9.4f}", flush=True)

    print(f"\nagainst Kris's gates:")
    for sym in LEGS:
        print(f"  {sym:9} {judge(trades[sym])}")

    (ROOT / "backtests" / "vwapbreak" / "book2.json").write_text(
        json.dumps({"legs": LEGS, "rows": rows}, indent=1, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
