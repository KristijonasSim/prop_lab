"""Do the flow feeds predict anything at SHORT horizons? The gating question.

Stage 1 settled the shape of the goal: K scales like sqrt(trades per day) with
an exponent measured at 0.441, and per-leg K on the incumbent book is ~0.003.
No universe wide enough exists to close a 2.2x gap that way. The only remaining
route is a book that trades several times a day per leg with a real per-trade
edge.

H-006 established that crowd positioning pays - but ONLY at 8 to 24 hours; it
measured nothing shorter. H-011 found open interest earns its place once a
level has been taken. H-013 found the perp premium is a real signal. None of
these has ever been measured at 5 to 60 minutes, which is the horizon a fast
book would have to live on.

So: bucket forward return by every feed feature this project has, at horizons
of 1 to 24 five-minute bars, across all eleven coins, at ZERO cost first and
then against the real 14bps round trip. Two forms of every feature:

  raw    the coin's own reading
  xs     cross-sectionally demeaned - the coin's reading minus the complex
         mean at the same instant. This is what a dollar-neutral book trades,
         and it is the form H-015 called `idio` and found WEAKEST at 8h. At
         short horizons it has never been looked at.

The bar to clear is explicit and harsh: a quintile spread has to exceed
**28bps** for a long-short pair to survive its own costs, or 14bps for a
directional trade. Anything under that is a signal that cannot be traded, which
is exactly how H-007 died.

Output: backtests/xpos/stage2_shorthorizon.csv
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

FEEDS = ROOT / "data" / "feeds"
OUT = ROOT / "backtests" / "xpos"
ROUND_TRIP_BPS = 14.0

COINS = ["ADAUSDT", "AVAXUSDT", "BNBUSDT", "BTCUSDT", "DOGEUSDT", "DOTUSDT",
         "ETHUSDT", "LINKUSDT", "LTCUSDT", "SOLUSDT", "XRPUSDT"]
HORIZONS = [1, 3, 6, 12, 24]          # 5m, 15m, 30m, 1h, 2h
ZWIN = 288                            # one day of 5m bars


def _z(s: pd.Series, win: int = ZWIN) -> pd.Series:
    """Rolling z-score, shifted so a bar is never part of its own baseline."""
    m = s.rolling(win, min_periods=win // 2).mean().shift(1)
    v = s.rolling(win, min_periods=win // 2).std(ddof=0).shift(1)
    return (s - m) / v.replace(0.0, np.nan)


def coin_frame(sym: str) -> pd.DataFrame | None:
    """Perp bars joined to the metrics feed and the premium, on one 5m clock."""
    try:
        px = pd.read_parquet(FEEDS / f"{sym}_perp_5m.parquet")
        mt = pd.read_parquet(FEEDS / f"{sym}_metrics_5m.parquet")
    except Exception:
        return None
    df = px.join(mt, how="inner").sort_index()
    df = df[~df.index.duplicated(keep="last")]
    try:
        pm = pd.read_parquet(FEEDS / f"{sym}_premium_5m.parquet")[["close"]]
        pm.columns = ["premium"]
        df = df.join(pm, how="left")
    except Exception:
        df["premium"] = np.nan

    f = pd.DataFrame(index=df.index)
    c = df["close"].astype(float)

    # --- aggression: who is hitting the book right now ---
    vol = df["volume"].astype(float)
    buy = df["taker_buy_base"].astype(float)
    imb = (2 * buy - vol) / vol.replace(0.0, np.nan)
    f["imb"] = imb
    f["imb_z"] = _z(imb)
    f["taker_ratio_z"] = _z(np.log(
        df["sum_taker_long_short_vol_ratio"].astype(float).replace(0.0, np.nan)))

    # --- positioning: where the crowd and the big accounts are standing ---
    crowd = np.log(df["count_long_short_ratio"].astype(float).replace(0.0, np.nan))
    topsz = np.log(df["sum_toptrader_long_short_ratio"].astype(float).replace(0.0, np.nan))
    f["crowd_z"] = _z(crowd)
    f["top_z"] = _z(topsz)
    # H-006's finding: the crowd and size disagreeing is the tradeable state.
    f["disagree"] = f["top_z"] - f["crowd_z"]
    for k, name in ((3, "15m"), (12, "1h"), (72, "6h")):
        f[f"dcrowd_{name}"] = crowd - crowd.shift(k)

    # --- leverage: is the move being built or unwound ---
    oi = df["sum_open_interest"].astype(float).replace(0.0, np.nan)
    loi = np.log(oi)
    ret1 = np.log(c).diff()
    f["doi_1h"] = loi - loi.shift(12)
    f["doi_z"] = _z(loi.diff(12))
    # The classic tape read, never tested here: price up on RISING open
    # interest is new money; price up on FALLING open interest is short
    # covering, and only one of those is supposed to continue.
    f["oi_price"] = np.sign(ret1.rolling(12).sum()) * f["doi_1h"]

    # --- pricing: what the crowded side is being charged ---
    f["premium_z"] = _z(df["premium"].astype(float))

    f["close"] = c
    f["open"] = df["open"].astype(float)
    return f


FEATURES = ["imb", "imb_z", "taker_ratio_z", "crowd_z", "top_z", "disagree",
            "dcrowd_15m", "dcrowd_1h", "dcrowd_6h", "doi_1h", "doi_z",
            "oi_price", "premium_z"]


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    frames = {}
    for s in COINS:
        f = coin_frame(s)
        if f is not None and len(f) > 50_000:
            frames[s] = f
            print(f"  loaded {s}: {len(f):,} bars "
                  f"{f.index[0]:%Y-%m} -> {f.index[-1]:%Y-%m}", flush=True)
    if len(frames) < 6:
        print("not enough coins")
        return 1

    # One panel per feature, coins as columns, so the cross-sectional demean is
    # taken at the same instant across coins rather than across time.
    idx = sorted(set().union(*[f.index for f in frames.values()]))
    idx = pd.DatetimeIndex(idx)
    panels = {k: pd.DataFrame({s: f[k].reindex(idx) for s, f in frames.items()})
              for k in FEATURES}
    close = pd.DataFrame({s: f["close"].reindex(idx) for s, f in frames.items()})
    opn = pd.DataFrame({s: f["open"].reindex(idx) for s, f in frames.items()})

    rows = []
    print(f"\n{'feature':14s} {'form':4s} {'h':>4s} {'IC':>8s} "
          f"{'Q5-Q1 bps':>10s} {'net of 28bps':>13s} {'n':>10s}")
    for h in HORIZONS:
        # Entry at the next bar's OPEN, exit h bars later at the close. The
        # signal is read on the close of bar t, so nothing here is observable
        # before it happened.
        fwd = (close.shift(-h) / opn.shift(-1) - 1.0) * 1e4
        for name in FEATURES:
            p = panels[name]
            for form in ("raw", "xs"):
                # `xs` subtracts the complex mean at that instant: what a
                # dollar-neutral book actually trades.
                v = p if form == "raw" else p.sub(p.mean(axis=1), axis=0)
                # Thin to hourly so overlapping 5m bars do not inflate n by 12x
                # and make every t-stat meaningless.
                m = (v.index.minute == 0)
                x, y = v[m], fwd[m]
                ok = x.notna() & y.notna()
                xs_, ys_ = x.values[ok.values], y.values[ok.values]
                if len(xs_) < 20_000:
                    continue
                ic = float(np.corrcoef(xs_, ys_)[0, 1])
                q = pd.qcut(pd.Series(xs_), 5, labels=False, duplicates="drop")
                gq = pd.Series(ys_).groupby(q).mean()
                spread = float(gq.iloc[-1] - gq.iloc[0]) if len(gq) == 5 else np.nan
                rows.append({"feature": name, "form": form, "horizon_bars": h,
                             "horizon_min": h * 5, "ic": round(ic, 5),
                             "spread_bps": round(spread, 2),
                             "net_bps": round(abs(spread) - 2 * ROUND_TRIP_BPS, 2),
                             "n": int(len(xs_))})

    df = pd.DataFrame(rows)
    df.to_csv(OUT / "stage2_shorthorizon.csv", index=False)

    top = df.reindex(df.spread_bps.abs().sort_values(ascending=False).index)
    for _, r in top.head(25).iterrows():
        mark = "  <-- clears cost" if r.net_bps > 0 else ""
        print(f"{r.feature:14s} {r.form:4s} {r.horizon_bars:>4d} {r.ic:>8.4f} "
              f"{r.spread_bps:>10.2f} {r.net_bps:>13.2f} {r.n:>10,}{mark}")

    print(f"\nfeatures clearing a 28bps long-short round trip: "
          f"{(df.net_bps > 0).sum()} of {len(df)}")
    print(f"clearing a 14bps directional round trip: "
          f"{(df.spread_bps.abs() > ROUND_TRIP_BPS).sum()} of {len(df)}")
    print(f"\nwrote {OUT / 'stage2_shorthorizon.csv'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
