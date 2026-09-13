"""H-027 ON THE VOLUME CLOCK — tier 1 item 2, the last one left.

Pre-registered in `strategies/vwapbreak/research/VOLBARS.md` BEFORE this ran,
kill criterion and all. Read that first; this file only executes it.

THE DESIGN POINT. Sub-hour (`subhour.py`) died because more bars did not mean
more trades — `floor 30 / top 5` plus an hours-based horizon holds the trade
count roughly fixed however the bar is sliced. So the volume arms here are
CALIBRATED TO THE SAME BAR COUNT as the 1h control. Same bars, same horizon
arithmetic, different clock: any difference is the clock and not the sample size.

Run: .venv/bin/python strategies/vwapbreak/research/volclock.py
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

from core.markets import load                                      # noqa: E402
from core.noiseband import overlap                                 # noqa: E402
from core.run_hypothesis import run_market, window                 # noqa: E402
from strategies.vwapbreak.research.exits import (UNIVERSE,         # noqa: E402
                                                 WIDE_SIGMA, ExitVariant)
from strategies.vwapbreak.research.subhour import (score,          # noqa: E402
                                                   sigma_over_cost)

SYM = "XAUUSD"
#: the control first, so the number every arm is judged against lands first
TFS = ("1h", "vol1h", "dol1h")


def overlap(a: dict, b: dict) -> bool:
    """Do two 10-90% days-bands overlap?

    Written out rather than imported so the comparison that decides the kill
    criterion is visible at the point of use. Two intervals overlap unless one
    ends before the other starts.
    """
    if not a or not b:
        return True                     # unknown band -> treat as overlapping
    return not (a["days_hi"] < b["days_lo"] or b["days_hi"] < a["days_lo"])


def main() -> int:
    span = window([s for v in UNIVERSE.values() for s in v], ["1h", "4h"])
    print(f"{SYM}, window {span[0].date()} -> {span[1].date()}, traded rule unchanged")
    print("volume arms calibrated to the 1h bar count - see VOLBARS.md\n")
    print(f"{'tf':7}{'bars':>8}{'sigma':>7}{'s/cost':>8}{'trades':>8}{'tpd':>7}"
          f"{'win%':>7}{'PF2x':>7}{'null':>7}{'days':>7}{'band':>12}"
          f"{'pass%':>7}{'mins':>6}")

    out, control = {}, None
    for tf in TFS:
        t0 = time.time()
        try:
            nbars = len(load(SYM, tf))
            sig, cost, ratio = sigma_over_cost(SYM, tf, span)
            res = run_market(ExitVariant("wide", stops=WIDE_SIGMA), SYM, tf,
                             pipe_kw={"floors": (30,), "topn": (5,)},
                             null_seeds=1, span=span)
        except Exception as exc:                          # noqa: BLE001
            print(f"{tf:7} FAILED: {type(exc).__name__}: {exc}", flush=True)
            continue
        s = score(res)
        s.update({"sigma_bps": sig, "cost_rt_bps": cost,
                  "sigma_over_cost": ratio, "bars": nbars})
        if tf == "1h":
            control = s
        out[tf] = s
        b = s.get("band") or {}
        print(f"{tf:7}{nbars:8}{sig:7.1f}{ratio:8.1f}{s['trades'] or 0:8}"
              f"{(s['trades_per_day'] or 0):7.2f}{(s['win_pct'] or 0):7.1f}"
              f"{(s['pf_2x'] or 0):7.3f}{(s['null_pf'] or 0):7.3f}"
              f"{(s['days'] or 0):7.1f}"
              f"{('%.0f-%.0f' % (b.get('days_lo', 0), b.get('days_hi', 0))):>12}"
              f"{(s['pass_pct'] or 0):7.1f}{(time.time() - t0) / 60:6.1f}",
              flush=True)
        (ROOT / "backtests" / "vwapbreak" / "volclock.json").write_text(
            json.dumps({"sym": SYM, "rows": out}, indent=1, default=str))

    # ---- the pre-registered kill criterion, applied out loud ------------- #
    if control and control.get("days"):
        print(f"\nKILL CRITERION vs the 1h control "
              f"({control['days']:.1f} days, band "
              f"{control['band']['days_lo']:.0f}-{control['band']['days_hi']:.0f}):")
        for tf, s in out.items():
            if tf == "1h" or not s.get("days"):
                continue
            faster = s["days"] < control["days"]
            disjoint = not overlap(s.get("band"), control.get("band"))
            beats = bool(s.get("beats_null"))
            verdict = "SURVIVES" if (faster and disjoint and beats) else "FAIL"
            fails = [n for n, ok in (("1 faster", faster),
                                     ("2 band disjoint", disjoint),
                                     ("3 beats null", beats)) if not ok]
            print(f"  {tf:7} {verdict:9} " +
                  ("all three hold" if not fails else "fails " + ", ".join(fails)))

    print("\nwrote backtests/vwapbreak/volclock.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
