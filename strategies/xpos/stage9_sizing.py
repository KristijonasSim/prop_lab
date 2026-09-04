"""H-017 stage 9 - is the project sizing every book more conservatively than
the prop rules actually require?

`riskladder.pick` admits a risk level only if THREE things hold: the max-loss
breach rate is under 5%, the daily-loss breach rate is under 5%, AND the whole
equity curve's peak drawdown fits inside the 8% cap at that risk.

The third one is a second, stricter test of the same thing, and it is measured
over the FULL history - six years for the crypto legs. An evaluation account
lives about fifty days. The probability that a given fifty-day window contains
a breach is exactly what `fail_max` and `fail_daily` already measure, account
by account, and the global-drawdown test then demands additionally that the
worst stretch in six years would also have fitted. Almost no account ever meets
that stretch.

The ladder's own docstring defends this, and the defence is real: a low breach
rate on short-lived accounts is not proof the drawdown fits. But it is a choice,
and it has never been priced. This prices it.

Reported both ways for every book, at every risk level, so the cost of the
conservative rule is visible rather than assumed. **Nothing here recommends
dropping it** - a funded account runs indefinitely and then the global drawdown
is exactly what matters. It answers how much of the 48.7 days is strategy and
how much is sizing policy.

Output: backtests/xpos/stage9_sizing.csv
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from core import riskladder as RL                                   # noqa: E402
from strategies.xpos.stage5_gatestack import TRADES, maxdd          # noqa: E402

OUT = ROOT / "backtests" / "xpos"
BT = ROOT / "backtests"


def best_row(rows, respect_dd_cap: bool):
    ok = [x for x in rows
          if x["fail_max"] <= RL.MAX_BREACH and x["fail_daily"] <= RL.MAX_BREACH
          and x["expected_days"] is not None
          and (abs(x["max_dd"]) <= RL.DD_CAP or not respect_dd_cap)]
    return min(ok, key=lambda x: x["expected_days"]) if ok else None


def report(label: str, r: np.ndarray, exit_ts, rows_out: list):
    rows, _ = RL.from_trades(r, exit_ts)
    strict = best_row(rows, True)
    loose = best_row(rows, False)
    if not strict:
        print(f"  {label:34s}  no admissible risk level")
        return
    s_days, l_days = strict["expected_days"], loose["expected_days"]
    gain = (s_days - l_days) / s_days * 100 if s_days else 0.0
    print(f"  {label:34s} strict {strict['risk']*100:>5.2f}% -> "
          f"{s_days:>7.1f} d   |   breach-only {loose['risk']*100:>5.2f}% -> "
          f"{l_days:>7.1f} d  ({gain:+.0f}%)   "
          f"[curve DD {abs(loose['max_dd'])*100:.1f}% at that risk]")
    rows_out.append({
        "book": label,
        "strict_risk": strict["risk"], "strict_days": s_days,
        "strict_pass": strict["pass_rate"],
        "loose_risk": loose["risk"], "loose_days": l_days,
        "loose_pass": loose["pass_rate"],
        "loose_curve_dd": round(abs(loose["max_dd"]), 4),
        "loose_fail_max": loose["fail_max"], "loose_fail_daily": loose["fail_daily"],
        "gain_pct": round(gain, 1)})


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    out: list = []
    print("Expected days: the ladder's rule vs the breach-rate test alone\n")

    for p in sorted(BT.glob("*/board.json")):
        b = json.loads(p.read_text())
        rows = b.get("ladder") or []
        strict = best_row(rows, True)
        loose = best_row(rows, False)
        if not strict or not loose:
            continue
        s_days, l_days = strict["expected_days"], loose["expected_days"]
        gain = (s_days - l_days) / s_days * 100 if s_days else 0.0
        print(f"  {b['hid']} {b['name'][:26]:26s} strict "
              f"{strict['risk']*100:>5.2f}% -> {s_days:>7.1f} d   |   "
              f"breach-only {loose['risk']*100:>5.2f}% -> {l_days:>7.1f} d  "
              f"({gain:+.0f}%)   [curve DD "
              f"{abs(loose['max_dd'])*100:.1f}%]")
        out.append({"book": f"{b['hid']} {b['name']}",
                    "strict_risk": strict["risk"], "strict_days": s_days,
                    "loose_risk": loose["risk"], "loose_days": l_days,
                    "loose_curve_dd": round(abs(loose["max_dd"]), 4),
                    "gain_pct": round(gain, 1)})

    print()
    t = pd.read_parquet(TRADES)
    t["exit_ts"] = pd.to_datetime(t.exit_ts, utc=True)
    g = t[t.gated].sort_values("exit_ts")
    dd = maxdd(g.r_2x.values)
    report("H-009 book (normalised)", g.r_2x.values * (4.0 / abs(dd)),
           g.exit_ts.values, out)

    pd.DataFrame(out).to_csv(OUT / "stage9_sizing.csv", index=False)
    if out:
        med = np.median([x["gain_pct"] for x in out])
        print(f"\n  Median speed-up from dropping the global-drawdown test: "
              f"{med:+.0f}%")
        print("  Read it as the PRICE of the conservative rule, not as a "
              "recommendation:")
        print("  a funded account runs indefinitely and then the curve's own "
              "drawdown is\n  exactly the thing that matters.")
    print(f"\nwrote {OUT / 'stage9_sizing.csv'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
