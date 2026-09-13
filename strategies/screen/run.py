"""Four candidates, one gate-2 screen. Pre-registered in `notes.md`.

H-035 on-chain exchange flows | H-036 the funding settlement as an event
H-037 the variance risk premium | H-038 fair value gaps

Everything - event definitions, directions, horizons, hurdle, kill criterion -
was fixed in `notes.md` and committed before this ran.

TWO THINGS ABOUT THE CONTROLS, because they are not the same kind of object.

  * F/P/V pairs are DIFFERENT events - the top decile and the bottom decile of
    the same series. Both clearing means the market is being measured rather
    than the mechanism, and both die. That is a real control.

  * FVG continuation and FVG fade are the SAME event with the direction flipped,
    so one is the exact negation of the other and exactly one is positive by
    construction. That is a direction test, NOT a control, and it is not
    reported as one. For FVG the checks that bite are the shuffled-date null and
    the year split.

Run: .venv/bin/python strategies/screen/run.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from core.probe import by_year, probe                              # noqa: E402

FEEDS = ROOT / "data" / "feeds"
MARKETS = ("BTCUSDT", "ETHUSDT")
BASE_ASSET = {"BTCUSDT": "BTC", "ETHUSDT": "ETH"}
HORIZONS = [4, 12, 24, 72]
HURDLE = 14.0
MIN_PCTILE = 95.0
MIN_YEARS = 4
WIN_H = 24 * 90        # trailing 90 days, hourly
MINP_H = 24 * 30
FVG_MIN_BPS = 10.0     # the second FVG arm, declared in notes.md before the run

#: label -> (direction, family). Families pair for the control test; FVG does not.
DIRECTION = {
    "F+ inflow": -1, "F- outflow": +1,
    "P+ longs pay": -1, "P- shorts pay": +1,
    "V+ vrp wide": +1, "V- vrp thin": -1,
    "G^ bull cont": +1, "Gv bear cont": -1,
    "G^ bull fade": -1, "Gv bear fade": +1,
    "G^ bull cont 10bps": +1, "Gv bear cont 10bps": -1,
}
PAIRS = (("F+ inflow", "F- outflow"),
         ("P+ longs pay", "P- shorts pay"),
         ("V+ vrp wide", "V- vrp thin"))


def crosses(state: pd.Series) -> np.ndarray:
    """Fresh entries into a state - never every bar inside it."""
    st = state.fillna(False).astype(bool)
    return (st & ~st.shift(1, fill_value=False)).values


def _decile_states(series: pd.Series, idx: pd.DatetimeIndex,
                   win: int, minp: int) -> tuple[pd.Series, pd.Series]:
    """Top/bottom decile of a trailing window, thresholds SHIFTED by one so a
    bar is never judged against a window containing itself."""
    hi = series.rolling(win, min_periods=minp).quantile(0.90).shift(1)
    lo = series.rolling(win, min_periods=minp).quantile(0.10).shift(1)
    top = (series >= hi).reindex(idx, method="ffill")
    bot = (series <= lo).reindex(idx, method="ffill")
    return top.fillna(False), bot.fillna(False)


def events_for(sym: str, bars: pd.DataFrame) -> dict[str, np.ndarray]:
    idx = bars.index
    out: dict[str, np.ndarray] = {}
    asset = BASE_ASSET[sym]

    # ---- H-035 on-chain exchange flows (daily, stamped when knowable) ---- #
    p = FEEDS / f"{asset}_onchain_1d.parquet"
    if p.exists():
        oc = pd.read_parquet(p).sort_index()
        top, bot = _decile_states(oc.net_ntv, idx, win=90, minp=30)
        out["F+ inflow"] = crosses(top)
        out["F- outflow"] = crosses(bot)

    # ---- H-036 the funding settlement as an event ------------------------ #
    p = FEEDS / f"{sym}_funding.parquet"
    if p.exists():
        f = pd.read_parquet(p).sort_index()
        fr = f.last_funding_rate
        # trailing 90 days = 270 eight-hourly settlements
        hi = fr.rolling(270, min_periods=90).quantile(0.90).shift(1)
        lo = fr.rolling(270, min_periods=90).quantile(0.10).shift(1)
        # the settlement lands on the hourly bar that contains it
        hrs = fr.index.floor("1h")
        ev_hi = pd.Series(False, index=idx)
        ev_lo = pd.Series(False, index=idx)
        ev_hi.loc[ev_hi.index.intersection(hrs[(fr >= hi).values])] = True
        ev_lo.loc[ev_lo.index.intersection(hrs[(fr <= lo).values])] = True
        out["P+ longs pay"] = ev_hi.values
        out["P- shorts pay"] = ev_lo.values

    # ---- H-037 the variance risk premium --------------------------------- #
    p = FEEDS / f"{asset}_dvol_3600s.parquet"
    if p.exists():
        dv = pd.read_parquet(p).sort_index().dvol_close
        r = np.log(bars.close).diff()
        # annualised realised vol in POINTS, to match DVOL's units
        rv = r.rolling(24 * 30, min_periods=24 * 10).std() * np.sqrt(24 * 365) * 100
        vrp = (dv.reindex(idx, method="ffill") - rv).dropna()
        top, bot = _decile_states(vrp, idx, WIN_H, MINP_H)
        out["V+ vrp wide"] = crosses(top)
        out["V- vrp thin"] = crosses(bot)

    # ---- H-038 fair value gaps ------------------------------------------- #
    hi2 = bars.high.shift(2)
    lo2 = bars.low.shift(2)
    bull = (bars.low > hi2)
    bear = (bars.high < lo2)
    gap_bull = (bars.low - hi2) / bars.close * 1e4
    gap_bear = (lo2 - bars.high) / bars.close * 1e4
    out["G^ bull cont"] = bull.fillna(False).values
    out["Gv bear cont"] = bear.fillna(False).values
    out["G^ bull fade"] = bull.fillna(False).values      # same event, flipped side
    out["Gv bear fade"] = bear.fillna(False).values
    out["G^ bull cont 10bps"] = (bull & (gap_bull >= FVG_MIN_BPS)).fillna(False).values
    out["Gv bear cont 10bps"] = (bear & (gap_bear >= FVG_MIN_BPS)).fillna(False).values
    return out


def main() -> int:
    frames, per_market = [], {}
    for sym in MARKETS:
        p = FEEDS / f"{sym}_perpbars_1h.parquet"
        if not p.exists():
            print(f"{sym}: no {p.name}")
            continue
        bars = pd.read_parquet(p).sort_index()
        ev = events_for(sym, bars)
        per_market[sym] = (bars, ev)
        print(f"\n=== {sym} === {len(bars):,} hourly bars "
              f"{bars.index[0]:%Y-%m-%d} -> {bars.index[-1]:%Y-%m-%d}")
        print(f"  {'reading':22}{'h':>4}{'events':>8}{'edge_bps':>10}"
              f"{'null_p95':>10}{'pct':>7}  gate")
        for name, e in ev.items():
            n_ev = int(np.asarray(e).sum())
            if n_ev < 30:
                print(f"  {name:22}{'':>4}{n_ev:8}   too few events - skipped")
                continue
            side = np.full(len(bars), DIRECTION[name], dtype=float)
            r = probe(bars, e, HORIZONS, sym, name, side=side, n_null=400)
            r["market"] = sym
            frames.append(r)
            for _, row in r.iterrows():
                ok = row.beats_hurdle and np.isfinite(row.pctile) and row.pctile >= MIN_PCTILE
                print(f"  {name:22}{int(row.h_bars):4}{int(row.events):8}"
                      f"{row.edge_bps:10.2f}{row.null_p95:10.2f}"
                      f"{row.pctile:7.1f}  {'PASS' if ok else '.'}")

    if not frames:
        print("nothing ran")
        return 1
    allr = pd.concat(frames, ignore_index=True)

    print("\n" + "=" * 74)
    print("GATE: edge > 14bps, pctile >= 95, same sign in >= 4 of available "
          "years,\n      and for F/P/V the opposite reading must NOT also clear.\n")
    survivors = []
    for sym, (bars, ev) in per_market.items():
        sub = allr[allr.market == sym]
        for name in ev:
            rows = sub[sub.mechanism == name]
            hit = rows[(rows.beats_hurdle) & (rows.pctile >= MIN_PCTILE)]
            if not len(hit):
                continue
            best = hit.loc[hit.edge_bps.idxmax()]
            side = np.full(len(bars), DIRECTION[name], dtype=float)
            yr = by_year(bars, ev[name], int(best.h_bars), side=side)
            pos = int((yr > 0).sum())
            same = max(pos, len(yr) - pos)
            print(f"  {sym} {name:22} h={int(best.h_bars):3} "
                  f"edge {best.edge_bps:8.2f}  pct {best.pctile:5.1f}  "
                  f"years {same}/{len(yr)}")
            if same >= MIN_YEARS:
                survivors.append((sym, name, float(best.edge_bps), int(best.h_bars)))

    names = {n for _, n, _, _ in survivors}
    for a, b in PAIRS:
        if a in names and b in names:
            print(f"\n  CONTROL FAILURE: {a} and {b} both clear -> both die.")
            survivors = [s for s in survivors if s[1] not in (a, b)]

    print()
    if survivors:
        for sym, name, e, h in survivors:
            print(f"  SURVIVES -> {sym} {name} h={h} edge {e:.2f}bps")
        print("\n  A survivor is a maybe for gate 3, not a result.")
    else:
        print("  NOTHING SURVIVES. All four are closed by measurement, "
              "exactly as pre-registered.")

    dst = ROOT / "backtests" / "screen"
    dst.mkdir(parents=True, exist_ok=True)
    allr.to_json(dst / "gate2.json", orient="records", indent=1)
    print("\nwrote backtests/screen/gate2.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
