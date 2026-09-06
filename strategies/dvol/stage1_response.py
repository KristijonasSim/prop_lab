"""H-025 stage 1 — does the option market's forecast rank forward returns?

DVOL is the first forward-looking feed in this project. Everything else here
describes what has already happened; this is what somebody is being paid to be
right about.

WHAT IS BEING ASKED, in order of how much I believe it:

  1. LEVEL as a regime. Is implied vol high or low against its own recent
     normal? Not directional on its own — high implied vol does not mean down —
     but it should change what every other signal is worth. This is the gate
     shape, and the gate shape is the only thing that has ever worked here.

  2. VARIANCE RISK PREMIUM. Implied minus realised. When the option market
     charges more for movement than arrives, somebody is being overpaid to carry
     risk, and that is a real economic imbalance with a named counterparty —
     the dealer who is short gamma and wants compensation. In equities the VRP
     is one of the most durable known premia. Whether it says anything
     DIRECTIONAL about spot at 15m-4h is a different and much weaker claim, and
     that is exactly what this measures.

  3. CHANGE. Implied vol repricing upward is fear arriving. Fear arriving has a
     direction; fear already priced does not.

  4. THE INTERACTION WITH DEPTH. This is the one worth the run. H-024 found
     resting-book imbalance carries a real but small signal on BTC (best cell
     4.6bps, monotone, beats its null, stable across years — and under every
     cost gate). If that signal is bigger when implied vol is high, the two
     feeds are complements and the combination is a new object. If it is flat
     across vol regimes, they are not, and H-024's smallness is structural.

NO LOOKAHEAD, and this is the easy place to leak it. DVOL bars are hourly and
stamped at the START of the hour, so a bar stamped T does not FINISH until
T + 1h. Reading it at T would be look-ahead of exactly the kind that was found in
the VWAP kernel yesterday. Every join here is `merge_asof` BACKWARD with a full
hour added to the DVOL timestamp first, so a 5-minute bar only ever sees an
hourly bar that had already closed.

Realised vol is computed on a trailing window and shifted, so no bar is inside
its own baseline.

Reported in bps against the repo's four round trips:
    taker 1x 14   taker 2x 28   mixed 9   maker 2x 8

Run: .venv/bin/python strategies/dvol/stage1_response.py
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from strategies.orderflow import orderflow as of                  # noqa: E402
from strategies.depth.stage1_response import (response, year_signs,  # noqa: E402
                                              features as depth_features,
                                              _z, MIN_SNAP)

FEEDS = ROOT / "data" / "feeds"
OUT = ROOT / "backtests" / "dvol"
OUT.mkdir(parents=True, exist_ok=True)

PAIRS = (("BTCUSDT", "BTC"), ("ETHUSDT", "ETH"))
HORIZONS = (3, 6, 12, 24, 48)
HNAME = {3: "15m", 6: "30m", 12: "1h", 24: "2h", 48: "4h"}
ZWIN = 288 * 7                 # a week of 5m bars: DVOL moves slowly
RV_WIN = 288 * 30              # 30 days, to match DVOL's 30-day horizon
BARS_PER_YEAR = 288 * 365
NSEEDS = 5
COSTS = {"taker1x": 14.0, "taker2x": 28.0, "mixed": 9.0, "maker2x": 8.0}


def load(sym: str, cur: str, with_depth: bool = True) -> pd.DataFrame:
    """Perp bars, DVOL as of the last CLOSED hourly bar, and depth if present."""
    px = pd.read_parquet(FEEDS / f"{sym}_perp_5m.parquet")
    dv = pd.read_parquet(FEEDS / f"{cur}_dvol_3600s.parquet")

    # The hour stamped T closes at T+1h. Add the bar's own duration before the
    # as-of merge so nothing is read before it existed.
    obs = pd.DataFrame({"ts": dv.index + pd.Timedelta(hours=1),
                        "dvol": dv.dvol_close.to_numpy(float)}).sort_values("ts")
    left = pd.DataFrame({"i": np.arange(len(px)),
                         "t": px.index}).sort_values("t")
    j = pd.merge_asof(left, obs, left_on="t", right_on="ts", direction="backward",
                      tolerance=pd.Timedelta(hours=6))
    px = px.copy()
    px["dvol"] = j.sort_values("i").dvol.to_numpy()

    if with_depth:
        p = FEEDS / f"{sym}_depth_5m.parquet"
        if p.exists():
            dp = pd.read_parquet(p)
            px = px.join(dp[dp.n_snap >= MIN_SNAP], how="left")
    return px[~px.index.duplicated(keep="last")].sort_index()


def features(df: pd.DataFrame) -> pd.DataFrame:
    """DVOL level, its change, the variance risk premium, and the depth cross."""
    f = pd.DataFrame(index=df.index)
    dvol = df.dvol

    f["dvolz"] = _z(dvol, ZWIN)

    # Change, at the horizons a session actually turns over.
    for k, name in ((12, "1h"), (48, "4h"), (288, "1d")):
        f[f"ddvol_{name}"] = _z(dvol - dvol.shift(k), ZWIN)

    # VARIANCE RISK PREMIUM. DVOL is annualised volatility in points; realised
    # is put in the same units before subtracting, otherwise the difference is
    # meaningless. Shifted, so the bar is not inside its own baseline.
    lr = np.log(df.close / df.close.shift(1))
    rv = lr.rolling(RV_WIN, min_periods=RV_WIN // 2).std(ddof=0).shift(1) \
         * np.sqrt(BARS_PER_YEAR) * 100.0
    f["vrp"] = dvol - rv
    f["vrpz"] = _z(f["vrp"], ZWIN)

    # THE INTERACTION. Depth imbalance, scaled by how dear implied vol is.
    if "imb_1" in df.columns:
        d = depth_features(df)
        for c in ("imbz_1", "imbz_5"):
            if c in d.columns:
                f[c] = d[c]
                f[f"{c}_x_dvol"] = d[c] * f["dvolz"]
    return f


def main():
    rows = []
    for sym, cur in PAIRS:
        try:
            df = load(sym, cur)
        except FileNotFoundError as e:
            print(f"{sym}: {e}")
            continue
        df = df[df.dvol.notna()]
        if len(df) < 10000:
            print(f"{sym}: only {len(df)} bars with DVOL, skipped")
            continue
        F = features(df)
        R = of.forward_returns(df, HORIZONS)
        have_depth = "imbz_1" in F.columns
        print(f"\n{sym}/{cur}: {len(df):,} bars  {df.index[0]:%Y-%m-%d} -> "
              f"{df.index[-1]:%Y-%m-%d}  ({len(F.columns)} features, "
              f"depth {'joined' if have_depth else 'ABSENT'})", flush=True)

        for name in F.columns:
            f = F[name]
            for h in HORIZONS:
                r = R[f"fwd_{h}"]
                vals, spread, mono, n = response(f, r)
                if not n or spread != spread:
                    continue
                nulls = []
                for s in range(NSEEDS):
                    _, ns, _, _ = response(of.block_shuffle(f, seed=s * 7919 + h), r)
                    if ns == ns:
                        nulls.append(abs(ns))
                nb = max(nulls) if nulls else np.nan
                ok, tot = year_signs(f, r)
                rows.append({
                    "sym": sym, "feature": name, "horizon": HNAME[h], "n": n,
                    "q1": vals[0], "q3": vals[2], "q5": vals[-1],
                    "spread": spread, "abs_spread": abs(spread),
                    "monotone": mono, "null_best": nb,
                    "beats_null": bool(abs(spread) > nb) if nb == nb else False,
                    "years_same_sign": ok, "years": tot,
                    **{f"clears_{k}": bool(abs(spread) > v) for k, v in COSTS.items()},
                })

    if not rows:
        print("nothing measured")
        return
    out = pd.DataFrame(rows)
    out.to_csv(OUT / "stage1_response.csv", index=False)

    print(f"\n{'=' * 104}\nTOP CELLS BY |SPREAD| (bps)\n{'=' * 104}")
    print(f"{'sym':9} {'feature':18} {'hz':4} {'q1':>7} {'q5':>7} {'spread':>8} "
          f"{'mono':>5} {'null':>7} {'yrs':>5}  gates")
    for _, r in out.sort_values("abs_spread", ascending=False).head(25).iterrows():
        gates = "".join(g for g, k in (("T", "clears_taker1x"), ("2", "clears_taker2x"),
                                       ("M", "clears_mixed"), ("m", "clears_maker2x"))
                        if r[k])
        star = "*" if r.beats_null else " "
        print(f"{r['sym']:9} {r.feature:18} {r.horizon:4} {r.q1:7.1f} {r.q5:7.1f} "
              f"{r.spread:8.1f} {r.monotone:5.2f} {r.null_best:7.1f}{star} "
              f"{r.years_same_sign:2d}/{r.years:<2d}  {gates}")

    print(f"\n-- how many cells clear each gate (of {len(out)}) --")
    for k, v in COSTS.items():
        sub = out[out[f"clears_{k}"]]
        print(f"  {k:9} > {v:5.1f}bps : {len(sub):5d} cells, "
              f"{int(sub.beats_null.sum()):5d} beat null")

    print("\n-- does the depth signal get bigger when implied vol is dear? --")
    for base, cross in (("imbz_1", "imbz_1_x_dvol"), ("imbz_5", "imbz_5_x_dvol")):
        b = out[out.feature == base].set_index(["sym", "horizon"]).abs_spread
        c = out[out.feature == cross].set_index(["sym", "horizon"]).abs_spread
        both = pd.concat([b.rename("plain"), c.rename("x_dvol")], axis=1).dropna()
        if len(both):
            lift = (both.x_dvol - both.plain)
            print(f"  {base:10} -> {cross:16} median lift "
                  f"{lift.median():+6.2f} bps, better in "
                  f"{int((lift > 0).sum())}/{len(lift)} cells")
    print(f"\nwrote {OUT / 'stage1_response.csv'}")


if __name__ == "__main__":
    main()
