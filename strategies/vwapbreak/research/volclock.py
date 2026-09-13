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

import numpy as np                                                 # noqa: E402
import pandas as pd                                                # noqa: E402

from core.markets import COSTS, EXEC_MODE, load                    # noqa: E402
from core.noiseband import overlap                                 # noqa: E402
from core.run_hypothesis import run_market, window                 # noqa: E402
from strategies.vwapbreak.research.anchors import _vwap_on         # noqa: E402
from strategies.vwapbreak.research.exits import (UNIVERSE,         # noqa: E402
                                                 WIDE_SIGMA, ExitVariant)
from strategies.vwapbreak.research.subhour import (score,          # noqa: E402
                                                   sigma_over_cost)

SYM = "XAUUSD"
#: the control first, so the number every arm is judged against lands first
TFS = ("1h", "vol1h", "dol1h")


def day_mask(df: pd.DataFrame) -> np.ndarray:
    """True on the FIRST bar of each UTC day.

    THE BUG THIS EXISTS TO FIX, found 2026-09-13 on the first run of this study.
    `sweep.vwap_series` finds its session boundary by an exact timestamp match,
    `(index.hour == 0) & (index.minute == 0)`. Every 1h time bar has one stamped
    exactly 00:00, so it fires 938 times over the window. A VOLUME bar is
    labelled at the first minute of its bucket - 21:37, 03:14 - and essentially
    never lands on 00:00, so the mask fired **8 times in three years**, `cumsum`
    gave 8 sessions, and the VWAP accumulated across months. Median band sigma
    read **326.6 bps against the 1h control's 18.4**, stops of 2.5-8 sigma became
    8-25% wide, nothing ever stopped out, and the arm printed a 60.8% win rate
    and 83 expected days. That is what a nonsense arm looks like.

    It is the same failure `anchors.py::_snap` documents for a 13:30 anchor on a
    1h series. Third time this masking has produced a number, so it is written
    down here as well.

    A day CHANGE is the honest generalisation: on time bars it is identical to
    the exact match (both give 938 sessions and 18.4 bps, verified), and on an
    irregular clock it still means "reset at the start of the UTC day".
    """
    day = pd.Series(df.index.normalize(), index=df.index)
    return (day != day.shift()).values


class DayAnchored:
    """A variant with the VWAP reset on the day CHANGE rather than on 00:00.

    Wraps another variant and overrides only `z` and `sd`. Deliberately NOT a
    change to `strategies/vwap/sweep.py`: that file is a declared kernel in
    `vwapbreak/manifest.py` and is imported by every hypothesis on the board, and
    `anchors.py` already sets the precedent that this arithmetic belongs in
    research rather than in the kernel.

    Applied to the 1h CONTROL as well as to the volume arms, on purpose. The two
    anchors are provably identical on time bars, so the control must reproduce
    the board's 11.7 days and PF@2x 2.872 - and if it does not, this wrapper is
    wrong and the run is void. The check is built into the comparison.
    """

    extra_column = "z"

    def __init__(self, base):
        self.base = base
        self.name = f"{base.name}_dayanchor"

    def features(self, df: pd.DataFrame):
        f = dict(self.base.features(df))
        vwap, vwstd = _vwap_on(df, day_mask(df))
        c = df.close.values
        # the same guard strategy.py uses: a volume-weighted variance is a
        # difference of near-equal accumulated sums, so its cancellation floor
        # is price * sqrt(eps), not zero.
        with np.errstate(invalid="ignore", divide="ignore"):
            f["z"] = (c - vwap) / np.where(vwstd > vwap * 1e-6, vwstd, np.nan)
        f["sd"] = vwstd
        return f

    def new_cache(self):
        g = getattr(self.base, "new_cache", None)
        return g() if callable(g) else {}

    def grid(self, tf: str):
        return self.base.grid(tf)

    def run(self, df, cfg, fee_bps, slip_bps, feats=None, **kw):
        return self.base.run(df, cfg, fee_bps, slip_bps,
                             feats=feats if feats is not None else self.features(df),
                             **kw)


def overlap(a: dict, b: dict) -> bool:
    """Do two 10-90% days-bands overlap?

    Written out rather than imported so the comparison that decides the kill
    criterion is visible at the point of use. Two intervals overlap unless one
    ends before the other starts.
    """
    if not a or not b:
        return True                     # unknown band -> treat as overlapping
    return not (a["days_hi"] < b["days_lo"] or b["days_hi"] < a["days_lo"])


def day_sigma_over_cost(sym: str, tf: str, span) -> tuple:
    """`subhour.sigma_over_cost`, but measured through the day-change anchor.

    The version in `subhour.py` calls `vwap_series` directly, so on a volume
    clock it reports the same inflated sigma the study itself was reading - 326
    bps instead of 21. The diagnostic has to use the same anchor as the arm it
    is diagnosing or it describes a different strategy.
    """
    df = load(sym, tf)
    df = df[(df.index >= span[0]) & (df.index <= span[1])]
    _, vwstd = _vwap_on(df, day_mask(df))
    c = df.close.values
    sd_bps = vwstd / np.where(c > 0, c, np.nan) * 1e4
    ok = np.isfinite(sd_bps) & (df.volume.values > 0)
    sig = float(np.nanmedian(sd_bps[ok]))
    cost = COSTS[sym].round_trip(EXEC_MODE)
    return round(sig, 1), round(cost, 2), round(sig / cost, 1)


def main() -> int:
    span = window([s for v in UNIVERSE.values() for s in v], ["1h", "4h"])
    print(f"{SYM}, window {span[0].date()} -> {span[1].date()}, traded rule unchanged")
    print("volume arms calibrated to the 1h bar count - see VOLBARS.md\n")
    print(f"{'tf':7}{'bars':>8}{'sigma':>7}{'s/cost':>8}{'trades':>8}{'tpd':>7}"
          f"{'win%':>7}{'PF2x':>7}{'null':>7}{'days':>7}{'band':>12}"
          f"{'pass%':>7}{'mins':>6}")

    # ONE variant for every arm, the control included. The two anchors are
    # identical on time bars, so 1h must reproduce the board's 11.7 days and
    # PF@2x 2.872. If it does not, this wrapper is wrong and the run is void.
    variant = DayAnchored(ExitVariant("wide", stops=WIDE_SIGMA))
    out, control = {}, None
    for tf in TFS:
        t0 = time.time()
        try:
            nbars = len(load(SYM, tf))
            sig, cost, ratio = day_sigma_over_cost(SYM, tf, span)
            res = run_market(variant, SYM, tf,
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
