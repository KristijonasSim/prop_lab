"""H-025 stage 2 — is the DVOL result real, or is it two artifacts?

Stage 1 found the first cells in this project to clear a cost gate:

    ETHUSDT  dvolz     4h   +9.9 bps  monotone 0.75  5/6 years  clears mixed+maker
    ETHUSDT  ddvol_1d  4h   +9.0 bps  monotone 1.00  5/6 years  clears maker
    BTCUSDT  dvolz     4h   +8.9 bps  monotone 1.00  5/6 years  clears maker

High implied vol, higher forward return. Before that is believed it has to
survive two specific objections, and neither is optional.

OBJECTION 1 — THE NULL IS TOO EASY.
`block_shuffle` cuts the feature into ONE-DAY blocks and reorders them. That is
the right null for a feature that turns over within a day, which is what every
previous study here measured. `dvolz` does not: it is a z-score of a slow index
against a one-WEEK baseline, so it stays on the same side for weeks at a time.
Day-blocking destroys exactly the persistence that makes the real feature what it
is, so the null is drawn from an easier distribution than the signal. The honest
null has to preserve the autocorrelation, which means longer blocks. Run at one
day, one week and one month; if the edge only beats the day-block null, it is an
artifact of the null, not a finding.

OBJECTION 2 — IT MAY BE REALISED VOL WEARING A COSTUME.
"Returns are higher in volatile regimes" is a statement about realised
volatility and needs no option market at all. If `dvolz` is a laggy proxy for
trailing realised vol then nothing has been discovered. The test is the one H-013
used: bucket by the feature INSIDE realised-vol buckets. If the spread survives
within every realised-vol bucket, the option market's forecast carries something
its own history does not.

A third check, cheap and worth having: the effective sample. Forward 4h returns
on 5m bars overlap 48-fold, and a feature that persists for weeks has far fewer
independent observations than its row count suggests. The number of distinct
week-long regimes is reported so nobody reads 500,000 rows as 500,000 facts.

Run: .venv/bin/python strategies/dvol/stage2_nulls.py
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from strategies.orderflow import orderflow as of                    # noqa: E402
from strategies.depth.stage1_response import response               # noqa: E402
from strategies.dvol.stage1_response import load, features, HNAME   # noqa: E402

OUT = ROOT / "backtests" / "dvol"
OUT.mkdir(parents=True, exist_ok=True)

PAIRS = (("BTCUSDT", "BTC"), ("ETHUSDT", "ETH"))
CELLS = ("dvolz", "ddvol_1d", "vrpz")
HORIZONS = (24, 48)                       # 2h and 4h, where stage 1 found it
BLOCKS = {"1d": 288, "1w": 288 * 7, "1mo": 288 * 30}
NSEEDS = 20                               # one seed is a sample of size one
RV_WIN = 288 * 30
BARS_PER_YEAR = 288 * 365
NBUCKET = 5


def realised(df: pd.DataFrame) -> pd.Series:
    """Trailing 30-day realised vol, annualised, shifted off its own bar."""
    lr = np.log(df.close / df.close.shift(1))
    return (lr.rolling(RV_WIN, min_periods=RV_WIN // 2).std(ddof=0).shift(1)
            * np.sqrt(BARS_PER_YEAR) * 100.0)


def within_rv(f: pd.Series, r: pd.Series, rv: pd.Series, n: int = NBUCKET):
    """Feature spread measured INSIDE each realised-vol bucket.

    If `dvolz` is only ranking returns because it tracks realised vol, then
    holding realised vol roughly fixed removes the spread. If the spread is
    still there in every bucket, the forecast is adding something its own
    history does not."""
    m = f.notna() & r.notna() & rv.notna()
    if m.sum() < 5000:
        return []
    d = pd.DataFrame({"f": f[m], "r": r[m], "rv": rv[m]})
    try:
        d["rvb"] = pd.qcut(d.rv, n, labels=False, duplicates="drop")
    except ValueError:
        return []
    out = []
    for b, chunk in d.groupby("rvb"):
        _, sp, mono, cnt = response(chunk.f, chunk.r)
        out.append((int(b), sp, mono, cnt))
    return out


def main():
    rows, detail = [], []
    for sym, cur in PAIRS:
        try:
            df = load(sym, cur)
        except FileNotFoundError as e:
            print(f"{sym}: {e}")
            continue
        df = df[df.dvol.notna()]
        F = features(df)
        R = of.forward_returns(df, HORIZONS)
        rv = realised(df)
        print(f"\n{sym}: {len(df):,} bars  {df.index[0]:%Y-%m-%d} -> "
              f"{df.index[-1]:%Y-%m-%d}", flush=True)

        for name in CELLS:
            if name not in F.columns:
                continue
            f = F[name]
            # How many independent week-long regimes are actually behind this?
            valid = f.notna()
            weeks = int(valid.groupby(pd.Grouper(freq="W")).any().sum())
            for h in HORIZONS:
                r = R[f"fwd_{h}"]
                _, spread, mono, n = response(f, r)
                if spread != spread:
                    continue
                row = {"sym": sym, "feature": name, "horizon": HNAME[h],
                       "n": n, "weeks": weeks, "spread": spread,
                       "monotone": mono}
                for bname, blk in BLOCKS.items():
                    nulls = []
                    for s in range(NSEEDS):
                        _, ns, _, _ = response(
                            of.block_shuffle(f, seed=s * 7919 + h, block=blk), r)
                        if ns == ns:
                            nulls.append(abs(ns))
                    if nulls:
                        a = np.asarray(nulls)
                        row[f"null_{bname}_med"] = float(np.median(a))
                        row[f"null_{bname}_max"] = float(a.max())
                        row[f"beats_{bname}"] = bool(abs(spread) > a.max())
                        # share of null seeds the real spread exceeds: a p-value
                        # read the honest way round
                        row[f"pct_{bname}"] = float((abs(spread) > a).mean())
                rows.append(row)

                for b, sp, mo, cnt in within_rv(f, r, rv):
                    detail.append({"sym": sym, "feature": name,
                                   "horizon": HNAME[h], "rv_bucket": b,
                                   "spread": sp, "monotone": mo, "n": cnt})

    if not rows:
        print("nothing measured")
        return
    out = pd.DataFrame(rows)
    out.to_csv(OUT / "stage2_nulls.csv", index=False)
    det = pd.DataFrame(detail)
    det.to_csv(OUT / "stage2_within_rv.csv", index=False)

    print(f"\n{'=' * 108}\nNULL STRENGTH BY BLOCK LENGTH "
          f"({NSEEDS} seeds each). 'beats' = real |spread| > the null's MAX."
          f"\n{'=' * 108}")
    print(f"{'sym':9} {'feature':10} {'hz':4} {'spread':>7} {'wks':>4}  "
          f"{'null1d':>7} {'>1d':>5}  {'null1w':>7} {'>1w':>5}  "
          f"{'null1mo':>7} {'>1mo':>5}")
    for _, r in out.iterrows():
        print(f"{r['sym']:9} {r.feature:10} {r.horizon:4} {r.spread:7.1f} "
              f"{r.weeks:4d}  "
              f"{r.get('null_1d_max', np.nan):7.1f} "
              f"{str(r.get('beats_1d')):>5}  "
              f"{r.get('null_1w_max', np.nan):7.1f} "
              f"{str(r.get('beats_1w')):>5}  "
              f"{r.get('null_1mo_max', np.nan):7.1f} "
              f"{str(r.get('beats_1mo')):>5}")

    print("\n-- CONFOUND: spread inside each realised-vol bucket "
          "(if it only works in one bucket, it is realised vol) --")
    if len(det):
        piv = det.pivot_table(index=["sym", "feature", "horizon"],
                              columns="rv_bucket", values="spread")
        piv["same_sign"] = piv.apply(
            lambda s: int((np.sign(s.dropna()) == np.sign(s.dropna()).iloc[0]).sum()),
            axis=1)
        piv["buckets"] = piv.drop(columns="same_sign").notna().sum(axis=1)
        print(piv.round(2).to_string())

    print(f"\nwrote {OUT / 'stage2_nulls.csv'} and {OUT / 'stage2_within_rv.csv'}")


if __name__ == "__main__":
    main()
