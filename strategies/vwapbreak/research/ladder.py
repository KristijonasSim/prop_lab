"""H-044 - does the guard's survival buy speed? Pre-registration: LADDER.md.

H-041, H-042 and H-043 all capped the risk ladder at 3% - a local tuple written
once and inherited twice without being looked at - while core/riskladder
RISK_LADDER runs to 5%. Drawdown headroom is the guard's whole product and
headroom is what a bigger position spends, so "the guard is slower" has so far
been a statement about one rung.

CLAUDE.md exempts this from the noise floor: re-simulating a fixed trade series
at a different position size selects nothing and searches nothing. Two series,
twelve rungs, no arms.

THE INTERACTION TO WATCH. The guard's threshold is in ACCOUNT percent, so it
bites harder at a bigger position: -0.50% is 0.17R at 3% risk and 2R at 0.25%.
Trade counts are therefore per-rung and are in the table.

Run: .venv/bin/python strategies/vwapbreak/research/ladder.py
"""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

from core.riskladder import MIN_RISK, RISK_LADDER                    # noqa: E402
from core.run_hypothesis import run_market, window                   # noqa: E402
from strategies.vwapbreak.strategy import STRATEGY                   # noqa: E402

_spec = importlib.util.spec_from_file_location(
    "guardsweep", Path(__file__).with_name("guardsweep.py"))
_gs = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_gs)
apply_guard, daily, day_grid = _gs.apply_guard, _gs.daily, _gs.day_grid
stats, bands, CELLS = _gs.stats, _gs.bands, _gs.CELLS

#: The plateau of H-043. -0.15/-0.25/-0.35% reproduce it exactly.
GUARD = 0.0050


def max_dd(tr: pd.DataFrame, risk: float) -> float:
    """Peak drawdown of the CONTINUOUS equity curve at this size, as
    `riskladder.ladder` computes it. Not what one challenge account loses - an
    account is dead at 6% and stops - so a deep number here is not a breach
    rate. It is in the table to stop a high rung being read as safe."""
    eq = np.concatenate(([0.0], np.cumsum(tr.r.values)))
    return round(float((eq - np.maximum.accumulate(eq)).min()) * risk * 100, 1)


def main() -> int:
    span = window(["XAUUSD"], ["1h", "4h"])
    out: dict[str, dict] = {}
    for sym, tf in CELLS:
        res = run_market(STRATEGY, sym, tf,
                         pipe_kw={"floors": (30,), "topn": (5,)},
                         null_seeds=0, span=span)
        tr = res["_trades"].copy()
        tr["entry_ts"] = pd.to_datetime(tr.entry_ts, utc=True)
        tr["exit_ts"] = pd.to_datetime(tr.exit_ts, utc=True)
        tr = tr.sort_values("entry_ts").reset_index(drop=True)
        grid = day_grid(tr)
        print(f"\n=== {sym} {tf}  ({len(tr)} blind trades, {len(grid)} days) "
              + "=" * 30, flush=True)
        for label, g in (("none", None), (f"-{GUARD*100:.2f}%", GUARD)):
            print(f"\n  arm: {label}", flush=True)
            hdr = (f"{'risk%':>7}{'trades':>8}{'tpd':>6}{'days':>7}{'band':>13}"
                   f"{'pass%':>7}{'blown%':>8}{'band':>13}{'maxDD%':>9}"
                   f"{'failMax%':>10}{'failDay%':>10}")
            print("  " + hdr); print("  " + "-" * len(hdr), flush=True)
            for risk in RISK_LADDER:
                kept = apply_guard(tr, risk, g)
                d = daily(kept, grid)
                s = stats(d, risk)
                if not s:
                    print(f"  {risk*100:>7.2f}   no passing account", flush=True)
                    continue
                s |= bands(d, risk)
                s["trades"] = len(kept)
                s["tpd"] = round(len(kept) / len(grid), 2)
                s["max_dd_pct"] = max_dd(kept, risk)
                s["at_floor"] = bool(risk >= MIN_RISK - 1e-12)
                out[f"{sym}|{tf}|{label}|{risk*100:.2f}"] = s
                print(f"  {s['risk_pct']:>7.2f}{s['trades']:>8}{s['tpd']:>6.2f}"
                      f"{s['days']:>7.1f}"
                      f"{('%.1f-%.1f' % (s.get('days_lo', 0), s.get('days_hi', 0))):>13}"
                      f"{s['pass_pct']:>7.1f}{s['blown_pct']:>8.1f}"
                      f"{('%.1f-%.1f' % (s['blown_lo'], s['blown_hi'])):>13}"
                      f"{s['max_dd_pct']:>9.1f}{s['fail_max_pct']:>10.1f}"
                      f"{s['fail_daily_pct']:>10.1f}", flush=True)

    dest = ROOT / "backtests" / "vwapbreak" / "ladder.json"
    dest.write_text(json.dumps({"guard": GUARD, "ladder": list(RISK_LADDER),
                                "min_risk": MIN_RISK, "rows": out},
                               indent=1, default=str))
    print(f"\nwrote {dest.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
