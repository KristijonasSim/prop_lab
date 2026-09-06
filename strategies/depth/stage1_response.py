"""H-024 stage 1 — does RESTING liquidity rank forward returns?

The first hypothesis in this project built on the order book itself.

WHY THIS GAP EXISTS. Every feed used here so far describes something that has
already happened. Open interest says who ended up positioned (H-006). Taker ratio
says who crossed the spread (H-006, H-021, H-022). The premium says what leverage
paid (H-013). None of them says what is STANDING IN THE WAY of the next order.

`bookDepth` does, and the archive has published it since 2023-01-01 without
anyone here downloading it: resting notional at +/-0.2, 1, 2, 3, 4 and 5 percent
from the mid, every thirty seconds, for every coin the metrics archive covers.

MECHANISM, stated before any result. Depth is inventory that somebody has
committed to at a price. Two distinct claims follow and they must not be
conflated:

  * IMBALANCE is directional. If twice as much notional rests on the bid within
    1% as on the ask, then the same market order moves price further up than
    down. The counterparty is whoever has to trade NOW against the thin side.
    The microstructure literature ranks top-of-book imbalance as its single most
    informative feature — but it measures it at 3-second horizons, which nothing
    here can trade. Whether the asymmetry PERSISTS out to 15m-4h is the question,
    and it is genuinely open.

  * DEPTH LEVEL is not directional. It is a regime. A thin book is one where any
    given order moves price further, so every other signal in the repo should
    mean something different in it. That makes it a candidate GATE, which is the
    only shape that has ever worked in this project.

The honest counter-argument, recorded up front: quoted depth is not committed
depth. Limit orders are cancelled, and layering to create a false impression of
depth is a known practice. If imbalance is mostly spoof, the response is flat and
this dies at stage 1 like the ten price hypotheses before it. The 30-second
cadence also means the book is seen in slow motion — real queue dynamics happen
faster than that.

FEATURES. Every one is z-scored on a trailing window shifted a bar, so nothing is
scored against itself, and every level term needs it twice over: BTC's book has
grown by an order of magnitude since 2023 and a raw depth number is not
comparable across years.

    imbz_b     z(bid-vs-ask imbalance within b percent)      directional
    dimb_b     change in that imbalance over k bars          directional
    hollowz    z(depth within 1% / depth within 5%)          book shape
    depz_b     z(total resting notional within b percent)    regime, NOT directional
    imbxthin_b imbz_b * (-depz_1)                            the interaction:
               imbalance should matter MORE when the book is thin, because the
               same asymmetry is then a larger fraction of what has to be eaten

The interaction is the one that would be new even if plain imbalance is known.

Reported in basis points against the same four round trips the rest of the repo
uses, because cost has killed the last five hypotheses here:

    taker 1x  14bps      taker 2x  28bps      mixed  9bps      maker 2x  8bps

Run: .venv/bin/python strategies/depth/stage1_response.py
     .venv/bin/python strategies/depth/stage1_response.py BTCUSDT
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from strategies.orderflow import orderflow as of        # noqa: E402

FEEDS = ROOT / "data" / "feeds"
OUT = ROOT / "backtests" / "depth"
OUT.mkdir(parents=True, exist_ok=True)

SYMS = ("BTCUSDT", "ETHUSDT", "SOLUSDT")
HORIZONS = (3, 6, 12, 24, 48)                 # 15m .. 4h, in 5-minute bars
HNAME = {3: "15m", 6: "30m", 12: "1h", 24: "2h", 48: "4h"}
BANDS = ("0.2", "1", "2", "5")
LOOKS = ((3, "15m"), (12, "1h"), (48, "4h"))  # windows for the CHANGE features
ZWIN = 288                                    # one day of 5m bars
NSEEDS = 5
NBUCKET = 5
MIN_SNAP = 5                                  # a 5m bar should hold ~10 snapshots
COSTS = {"taker1x": 14.0, "taker2x": 28.0, "mixed": 9.0, "maker2x": 8.0}


def load(sym: str) -> pd.DataFrame:
    """Perp bars joined to the depth feed on one 5-minute clock.

    Inner join, no forward fill. A depth reading carried forward is a book that
    was never on the screen, and the archive has real gaps. Bars built from
    fewer than MIN_SNAP snapshots are dropped: an exchange outage leaves one
    snapshot in a bar and its imbalance is not the bar's imbalance.
    """
    px = pd.read_parquet(FEEDS / f"{sym}_perp_5m.parquet")
    dp = pd.read_parquet(FEEDS / f"{sym}_depth_5m.parquet")
    dp = dp[dp.n_snap >= MIN_SNAP]
    df = px.join(dp, how="inner").sort_index()
    return df[~df.index.duplicated(keep="last")]


def _z(s: pd.Series, win: int = ZWIN) -> pd.Series:
    """Trailing z-score, baseline shifted one bar so nothing scores itself."""
    m = s.rolling(win, min_periods=win // 2).mean().shift(1)
    v = s.rolling(win, min_periods=win // 2).std(ddof=0).shift(1)
    return (s - m) / v.replace(0.0, np.nan)


def features(df: pd.DataFrame) -> pd.DataFrame:
    """The depth features, all point-in-time."""
    f = pd.DataFrame(index=df.index)

    for b in BANDS:
        ic, dc = f"imb_{b}", f"dep_{b}"
        if ic not in df.columns or dc not in df.columns:
            continue
        # Directional: how lopsided the resting book is, against its own recent
        # normal. The raw level is useless - BTC's book sits at a persistent
        # positive imbalance at wide bands - so only the deviation can be read.
        f[f"imbz_{b}"] = _z(df[ic])
        # Regime: how much is resting at all.
        f[f"depz_{b}"] = _z(np.log(df[dc].replace(0.0, np.nan)))

    if "hollow" in df.columns:
        f["hollowz"] = _z(df.hollow)

    # CHANGE in imbalance. A book that is becoming lopsided is a different
    # object from one that has been lopsided all day: the first is somebody
    # arriving, the second is somebody who has already been seen.
    for b in ("0.2", "1"):
        ic = f"imb_{b}"
        if ic not in df.columns:
            continue
        for k, name in LOOKS:
            f[f"dimb_{b}_{name}"] = _z(df[ic] - df[ic].shift(k))

    # THE INTERACTION. Imbalance should pay more when there is less book behind
    # it. Written as a product of two z-scores so neither term's scale decides
    # the answer.
    if "imbz_1" in f and "depz_1" in f:
        f["imbxthin_1"] = f["imbz_1"] * (-f["depz_1"])
    if "imbz_0.2" in f and "depz_1" in f:
        f["imbxthin_0.2"] = f["imbz_0.2"] * (-f["depz_1"])

    return f


def response(f: pd.Series, r: pd.Series, n: int = NBUCKET):
    """Mean forward return per feature bucket, in bps."""
    m = f.notna() & r.notna()
    if m.sum() < 2000:
        return [np.nan] * n, np.nan, np.nan, 0
    try:
        b = pd.qcut(f[m], n, labels=False, duplicates="drop")
    except ValueError:
        return [np.nan] * n, np.nan, np.nan, 0
    g = (r[m] * 1e4).groupby(b).mean()
    vals = [float(g.get(i, np.nan)) for i in range(n)]
    spread = vals[-1] - vals[0]
    d = np.diff([v for v in vals if v == v])
    mono = float(np.mean(d > 0)) if len(d) else np.nan
    return vals, spread, max(mono, 1 - mono), int(m.sum())


def year_signs(f: pd.Series, r: pd.Series) -> tuple[int, int]:
    """How many calendar years carry the same sign as the full sample.

    Forward returns on 5m bars overlap heavily, so a t-statistic on hundreds of
    thousands of rows is a lie. Year-by-year agreement and the block null are
    the real defence."""
    m = f.notna() & r.notna()
    if m.sum() < 2000:
        return 0, 0
    d = pd.DataFrame({"f": f[m], "r": r[m]})
    try:
        d["b"] = pd.qcut(d.f, NBUCKET, labels=False, duplicates="drop")
    except ValueError:
        return 0, 0
    g = d.groupby("b").r.mean()
    full = np.sign(g.iloc[-1] - g.iloc[0])
    signs = []
    for _, chunk in d.groupby(d.index.year):
        if len(chunk) < 2000:
            continue
        try:
            cb = pd.qcut(chunk.f, NBUCKET, labels=False, duplicates="drop")
        except ValueError:
            continue
        cg = chunk.r.groupby(cb).mean()
        signs.append(np.sign(cg.iloc[-1] - cg.iloc[0]) == full)
    return int(sum(signs)), len(signs)


def main():
    syms = sys.argv[1:] or list(SYMS)
    rows = []
    for sym in syms:
        try:
            df = load(sym)
        except FileNotFoundError as e:
            print(f"{sym}: {e}")
            continue
        if len(df) < 10000:
            print(f"{sym}: only {len(df)} joined bars, skipped")
            continue
        F = features(df)
        R = of.forward_returns(df, HORIZONS)
        print(f"\n{sym}: {len(df):,} bars  {df.index[0]:%Y-%m-%d} -> "
              f"{df.index[-1]:%Y-%m-%d}  ({len(F.columns)} features)", flush=True)

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
        print(f"  {len([r for r in rows if r['sym'] == sym])} feature x horizon cells")

    if not rows:
        print("nothing measured")
        return
    out = pd.DataFrame(rows)
    out.to_csv(OUT / "stage1_response.csv", index=False)

    print(f"\n{'=' * 104}\nTOP CELLS BY |SPREAD| (bps). Cost gates: "
          f"taker1x {COSTS['taker1x']}  taker2x {COSTS['taker2x']}  "
          f"mixed {COSTS['mixed']}  maker2x {COSTS['maker2x']}\n{'=' * 104}")
    top = out.sort_values("abs_spread", ascending=False).head(25)
    print(f"{'sym':9} {'feature':16} {'hz':4} {'q1':>7} {'q5':>7} {'spread':>8} "
          f"{'mono':>5} {'null':>7} {'yrs':>5}  gates")
    for _, r in top.iterrows():
        gates = "".join(g for g, k in (("T", "clears_taker1x"), ("2", "clears_taker2x"),
                                       ("M", "clears_mixed"), ("m", "clears_maker2x"))
                        if r[k])
        star = "*" if r.beats_null else " "
        print(f"{r['sym']:9} {r.feature:16} {r.horizon:4} {r.q1:7.1f} {r.q5:7.1f} "
              f"{r.spread:8.1f} {r.monotone:5.2f} {r.null_best:7.1f}{star} "
              f"{r.years_same_sign:2d}/{r.years:<2d}  {gates}")

    print(f"\n-- how many cells clear each gate (of {len(out)}), "
          f"and how many of those also beat their null --")
    for k, v in COSTS.items():
        sub = out[out[f"clears_{k}"]]
        print(f"  {k:9} > {v:5.1f}bps : {len(sub):5d} cells, "
              f"{int(sub.beats_null.sum()):5d} beat null")

    print("\n-- by feature family, median |spread| and share beating null --")
    out["family"] = out.feature.str.replace(r"_[0-9.]+(_[0-9]+[mh])?$", "", regex=True)
    fam = out.groupby("family").agg(cells=("spread", "size"),
                                    med_abs=("abs_spread", "median"),
                                    max_abs=("abs_spread", "max"),
                                    beat=("beats_null", "mean"))
    print(fam.sort_values("med_abs", ascending=False).round(3).to_string())
    print(f"\nwrote {OUT / 'stage1_response.csv'}")


if __name__ == "__main__":
    main()
