"""H-049 stage 1 — does WHERE inside the bar the flow happened carry information?

THE SCOUT, NOT THE VERDICT. One market, 117 consecutive days, one regime. It can
kill the family cheaply. It cannot confirm it.

WHY THIS EXISTS, AND WHAT IS ACTUALLY NEW HERE.

A footprint chart is a bar split by PRICE LEVEL, with aggressive buy volume and
aggressive sell volume printed side by side at each level. Everything a
footprint trader reads off it is one of two things:

  1. HOW MUCH net aggression the bar carried  -> that is `delta`, and this repo
     has already measured it three times. H-006: taker aggression against 8-72h
     returns is FLAT (+10.8/+12.5/+10.7/+12.0/+12.2bps across quintiles). H-021:
     real at 5m, 5x too small. H-022: absorption, `z(flow) - z(return)`, real,
     monotone 1.00, same sign 7 of 7 years, beats every null seed, and
     **6.55bps against the cheapest realistic 8bps round trip**. Dead on cost.

  2. WHERE inside the bar's range that aggression sat -> **this has never been
     measured here, and it is the only thing a footprint adds to a feed this
     repo already owns.** `data/feeds/*_taker_5m.parquet` and the metrics feed
     give bar-level delta without tick data. The price-level resolution is the
     entire reason a footprint costs money.

So the question is not "is order flow informative" - that is answered, it is
real and too small. The question is whether the LOCATION of the flow adds
anything on top of the amount of it. If it does not, the footprint family is
priced dead here without buying a single day of data, and `docs/` says so.

MECHANISM, stated before any result. Three of the footprint patterns make a
falsifiable claim about the counterparty, and they are the three tested below:

  * ABSORPTION AT THE EXTREME. Heavy aggressive BUYING printed in the top decile
    of the bar's range, and the bar does not close there. Somebody passive stood
    at the high and took the other side of every market buy. That somebody has
    quantity and no deadline (H-022's argument), so price should fade away from
    the high. Signed so that positive = selling absorbed at the LOW = expect up.

  * UNFINISHED AUCTION. The extreme of the bar printed with BOTH aggressive buy
    and aggressive sell volume. A finished auction ends with one side alone -
    the last buyer lifted an offer and nobody sold into him. Both sides at the
    extreme means the auction was cut short by the clock, and the claim is that
    price returns to complete it.

  * STACKED IMBALANCE. Three or more consecutive price levels where one side's
    aggressive volume exceeds the other's by 3:1 on the diagonal. The single
    most-cited footprint entry trigger. The claim is continuation, not reversal.

  * POINT OF CONTROL versus the close. The price level that traded the most
    volume, relative to where the bar closed. A POC left overhead is supply the
    bar walked away from.

THE CONTROL THAT DECIDES IT. Every one of these is correlated with `delta` by
construction - a bar with heavy buying has buy volume everywhere in it. So each
feature is ALSO read inside delta terciles (`--partial`). A location feature
that only works through delta is H-022 again under a new name, and is reported
as such. The double sort is used rather than a regression residual because a
full-sample residual would leak the future into a scouting number.

KILL CRITERION, WRITTEN BEFORE THE RUN. If no location feature clears **14bps**
(the repo's standing taker round trip) on the q5-q1 spread after the delta
double sort, the answer to "should this project buy footprint data" is NO, and
the family joins H-006/H-021/H-022/H-024 in the known-dead list as real-but-
under-cost. Clearing 14bps is necessary, not sufficient - it still has to
survive the null, the thirds and the search price.

DATA. `data/ticks/BTCUSDT-aggTrades-*.zip`, Binance USDT-M, 117 days
2026-05-01 -> 2026-08-25, ~140M trades. `is_buyer_maker == true` means the
buyer was the passive side, so the AGGRESSOR was a seller.

Run:  .venv/bin/python strategies/footprint/stage1_location.py
      .venv/bin/python strategies/footprint/stage1_location.py --bar 5min
"""
from __future__ import annotations

import argparse
import glob
import os
import sys
import zipfile

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))))

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
TICKS = os.path.join(REPO, "data", "ticks")
OUT = os.path.join(REPO, "backtests", "footprint")

#: the four round trips every hypothesis here is scored against, bps
COSTS = {"taker1x": 14.0, "taker2x": 28.0, "mixed": 9.0, "maker2x": 8.0}

#: price levels inside a bar. A footprint prints one row per tick; at BTC's
#: 0.1 tick a 15m bar spans thousands of them, which is noise, not structure.
#: Deciles of the bar's own range are the same object at a readable resolution
#: and are scale-free, so the feature means the same thing at $76k and $120k.
NLEV = 10

NBUCKET = 5
NSEED = 200


# ----------------------------------------------------------------- footprint

def footprint_day(path: str, bar: str) -> pd.DataFrame:
    """One day of aggTrades -> one row per bar with the footprint features.

    Returns NaN-free rows only for bars with a non-degenerate range; a bar whose
    high equals its low has no location axis and is dropped rather than imputed.
    """
    with zipfile.ZipFile(path) as z:
        name = z.namelist()[0]
        d = pd.read_csv(z.open(name), header=0, usecols=[1, 2, 5, 6],
                        names=["id", "price", "qty", "f", "l", "ts", "maker"])

    d["ts"] = pd.to_datetime(d["ts"], unit="ms", utc=True)
    # is_buyer_maker: the BUYER was passive, so the trade was an aggressive SELL
    maker = d["maker"].astype(str).str.lower().eq("true").to_numpy()
    d["buy"] = np.where(~maker, d["qty"].to_numpy(), 0.0)
    d["sell"] = np.where(maker, d["qty"].to_numpy(), 0.0)
    d = d.set_index("ts")

    g = d.resample(bar)
    ohlc = g["price"].ohlc()
    vol = g["qty"].sum()
    buy = g["buy"].sum()
    sell = g["sell"].sum()

    out = ohlc.copy()
    out["vol"] = vol
    out["delta"] = buy - sell
    out["nt"] = g["price"].count()

    rng = (out["high"] - out["low"]).to_numpy()
    ok = np.isfinite(rng) & (rng > 0)

    # ---- per-level aggregation, vectorised over the whole day at once
    bar_id = d.index.floor(bar)
    codes, uniq = pd.factorize(bar_id, sort=True)
    lo = out["low"].reindex(uniq).to_numpy()
    hi = out["high"].reindex(uniq).to_numpy()
    span = np.where(hi > lo, hi - lo, np.nan)

    loc = (d["price"].to_numpy() - lo[codes]) / span[codes]
    lev = np.clip((loc * NLEV).astype("float64"), 0, NLEV - 1e-9)
    lev = np.where(np.isfinite(lev), lev, 0.0).astype(int)

    nb = len(uniq)
    flat = codes * NLEV + lev
    b_lev = np.bincount(flat, weights=d["buy"].to_numpy(), minlength=nb * NLEV
                        ).reshape(nb, NLEV)
    s_lev = np.bincount(flat, weights=d["sell"].to_numpy(), minlength=nb * NLEV
                        ).reshape(nb, NLEV)
    v_lev = b_lev + s_lev

    tot = v_lev.sum(axis=1)
    tot_safe = np.where(tot > 0, tot, np.nan)
    centres = (np.arange(NLEV) + 0.5) / NLEV

    # 1. DLOC - were the buyers working higher in the range than the sellers?
    bsum = b_lev.sum(axis=1)
    ssum = s_lev.sum(axis=1)
    bloc = (b_lev * centres).sum(axis=1) / np.where(bsum > 0, bsum, np.nan)
    sloc = (s_lev * centres).sum(axis=1) / np.where(ssum > 0, ssum, np.nan)
    dloc = bloc - sloc

    # 2. ABSORB - aggression at an extreme that the close walked away from.
    #    Signed so POSITIVE = selling absorbed at the LOW = the up case.
    closeloc = ((out["close"].reindex(uniq).to_numpy() - lo) / span)
    closeloc = np.clip(closeloc, 0.0, 1.0)
    hi_buy = b_lev[:, -1] / tot_safe
    lo_sell = s_lev[:, 0] / tot_safe
    absorb = (lo_sell * closeloc) - (hi_buy * (1.0 - closeloc))

    # 3. UNFIN - did the extreme print BOTH sides? A finished auction does not.
    def _bal(b, s):
        mx = np.maximum(b, s)
        return np.where(mx > 0, np.minimum(b, s) / mx, np.nan)

    unfin = _bal(b_lev[:, -1], s_lev[:, -1]) - _bal(b_lev[:, 0], s_lev[:, 0])

    # 4. STACK - longest run of consecutive levels at >=3:1 on the diagonal,
    #    signed buy-run minus sell-run. Continuation, not reversal.
    eps = 1e-12
    buy_imb = b_lev >= 3.0 * (s_lev + eps)
    sell_imb = s_lev >= 3.0 * (b_lev + eps)
    stack = _runlen(buy_imb) - _runlen(sell_imb)

    # 5. POC - the most-traded level, relative to the close
    poc = (np.argmax(v_lev, axis=1) + 0.5) / NLEV
    poc_loc = poc - closeloc

    feat = pd.DataFrame({"dloc": dloc, "absorb": absorb, "unfin": unfin,
                         "stack": stack.astype(float), "poc_loc": poc_loc,
                         "closeloc": closeloc}, index=uniq)
    out = out.join(feat)
    out = out[ok]
    return out.dropna(subset=["open", "high", "low", "close"])


def _runlen(mask: np.ndarray) -> np.ndarray:
    """Longest run of True along axis 1, per row."""
    n, k = mask.shape
    best = np.zeros(n, dtype=int)
    cur = np.zeros(n, dtype=int)
    for j in range(k):
        cur = np.where(mask[:, j], cur + 1, 0)
        best = np.maximum(best, cur)
    return best


def build(bar: str, limit: int | None = None) -> pd.DataFrame:
    files = sorted(glob.glob(os.path.join(TICKS, "BTCUSDT-aggTrades-*.zip")))
    if limit:
        files = files[:limit]
    if not files:
        raise SystemExit(f"no tick files under {TICKS}")
    rows = []
    for i, f in enumerate(files, 1):
        rows.append(footprint_day(f, bar))
        if i % 20 == 0 or i == len(files):
            print(f"  ... {i}/{len(files)} days", flush=True)
    df = pd.concat(rows).sort_index()
    return df[~df.index.duplicated(keep="first")]


# ------------------------------------------------------------------ features

def _z(s: pd.Series, win: int) -> pd.Series:
    """Trailing z-score on a SHIFTED window, so nothing is scored against
    itself. Same convention as strategies/absorb/stage1_response.py."""
    m = s.shift(1).rolling(win, min_periods=win // 2).mean()
    v = s.shift(1).rolling(win, min_periods=win // 2).std()
    return (s - m) / v.replace(0.0, np.nan)


def features(df: pd.DataFrame, win: int) -> pd.DataFrame:
    f = pd.DataFrame(index=df.index)
    ret = np.log(df["close"]).diff()

    # the CONTROLS - both already known real and both already dead on cost.
    # They are here so the new features are read against a known quantity and
    # so the run reproduces H-022 rather than asking to be trusted.
    f["delta_z"] = _z(df["delta"] / df["vol"].replace(0, np.nan), win)
    f["absorbq_h022"] = (_z(df["delta"] / df["vol"].replace(0, np.nan), win)
                         - _z(ret, win))

    # the NEW ones - location, not amount
    for c in ("dloc", "absorb", "unfin", "stack", "poc_loc"):
        f[c] = _z(df[c], win)
    return f


def forward(df: pd.DataFrame, h: int) -> pd.Series:
    """Decision at bar close, ENTRY AT THE NEXT BAR'S OPEN, exit h bars later.

    Never `close -> close`: that books a fill at a price only knowable once the
    bar it is measured from has ended. Two look-aheads of that exact class have
    already been found in this repo (H-019, H-023 stage 13)."""
    o = df["open"].shift(-1)
    return (np.log(o.shift(-h) / o) * 1e4).rename(f"fwd{h}")


# ------------------------------------------------------------------- scoring

def response(f: pd.Series, r: pd.Series, n: int = NBUCKET):
    ok = f.notna() & r.notna()
    f, r = f[ok], r[ok]
    if len(f) < n * 200:
        return np.nan, np.nan, 0
    try:
        q = pd.qcut(f, n, labels=False, duplicates="drop")
    except ValueError:
        return np.nan, np.nan, 0
    if q.nunique() < n:
        return np.nan, np.nan, 0
    means = r.groupby(q).mean()
    spread = float(means.iloc[-1] - means.iloc[0])
    d = np.diff(means.to_numpy())
    mono = float(max((d > 0).mean(), (d < 0).mean()))
    return spread, mono, len(f)


def null_best(f: pd.Series, r: pd.Series, seeds: int = NSEED) -> float:
    """Circular shift of the feature against the returns. Shifting rather than
    resampling keeps the feature's own autocorrelation intact, so the null is
    a series with the same memory and no relationship - which is the thing
    being tested against."""
    rng = np.random.default_rng(20260916)
    v = f.to_numpy()
    n = len(v)
    out = []
    for _ in range(seeds):
        k = int(rng.integers(n // 20, n - n // 20))
        s, _m, _n = response(pd.Series(np.roll(v, k), index=f.index), r)
        if s == s:
            out.append(abs(s))
    return float(max(out)) if out else np.nan


def thirds(f: pd.Series, r: pd.Series) -> str:
    """Sign agreement across three consecutive blocks of the sample. With one
    regime and no calendar years available this is the weakest possible
    stability check and is labelled as such."""
    n = len(f)
    signs = []
    for a, b in ((0, n // 3), (n // 3, 2 * n // 3), (2 * n // 3, n)):
        s, _m, _c = response(f.iloc[a:b], r.iloc[a:b])
        signs.append(0 if s != s else int(np.sign(s)))
    base = signs[0] if signs[0] else 1
    return f"{sum(1 for s in signs if s == base)}/3"


def partial(f: pd.Series, ctrl: pd.Series, r: pd.Series) -> float:
    """The q5-q1 spread AVERAGED INSIDE delta terciles.

    This is the number the hypothesis lives or dies on. Every location feature
    is correlated with delta by construction, so an unconditional spread cannot
    tell a new fact from H-022 wearing a different name. A double sort is used
    rather than a regression residual because a full-sample residual leaks the
    future into a scouting number."""
    ok = f.notna() & ctrl.notna() & r.notna()
    f, c, r = f[ok], ctrl[ok], r[ok]
    if len(f) < 3000:
        return np.nan
    try:
        t = pd.qcut(c, 3, labels=False, duplicates="drop")
    except ValueError:
        return np.nan
    vals = []
    for g in sorted(pd.unique(t)):
        m = t == g
        s, _mo, _n = response(f[m], r[m])
        if s == s:
            vals.append(s)
    return float(np.mean(vals)) if len(vals) == 3 else np.nan


# ---------------------------------------------------------------------- main

def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--bar", default="15min")
    ap.add_argument("--win", type=int, default=0, help="z window in bars")
    ap.add_argument("--days", type=int, default=None)
    ap.add_argument("--horizons", default="1,4,16")
    args = ap.parse_args()

    per_h = {"5min": 12, "15min": 4, "30min": 2, "1h": 1}[args.bar]
    win = args.win or per_h * 24 * 3          # three days of trailing context
    hs = [int(x) for x in args.horizons.split(",")]

    os.makedirs(OUT, exist_ok=True)
    cache = os.path.join(OUT, f"BTCUSDT_footprint_{args.bar}.parquet")
    if os.path.exists(cache) and not args.days:
        df = pd.read_parquet(cache)
        print(f"footprint bars from cache: {cache}")
    else:
        print(f"building {args.bar} footprint bars from aggTrades ...")
        df = build(args.bar, args.days)
        if not args.days:
            df.to_parquet(cache)

    print(f"\nbars {len(df):,}  {df.index.min()} -> {df.index.max()}  "
          f"trades {int(df['nt'].sum()):,}  levels/bar {NLEV}")

    f = features(df, win)
    fwd = {h: forward(df, h) for h in hs}
    newf = ["dloc", "absorb", "unfin", "stack", "poc_loc"]
    ctrl = ["delta_z", "absorbq_h022"]

    rows = []
    for name in ctrl + newf:
        for h in hs:
            s, mono, n = response(f[name], fwd[h])
            if s != s:
                continue
            nb = null_best(f[name], fwd[h])
            rows.append({
                "feature": name, "new": name in newf,
                "h_bars": h, "h_hours": round(h / per_h, 2), "n": n,
                "spread": s, "monotone": mono, "null_best": nb,
                "beats_null": bool(abs(s) > nb),
                "thirds": thirds(f[name], fwd[h]),
                "partial_delta": partial(f[name], f["delta_z"], fwd[h]),
                **{f"clears_{k}": bool(abs(s) > v) for k, v in COSTS.items()},
            })
    res = pd.DataFrame(rows)
    res.to_csv(os.path.join(OUT, f"stage1_location_{args.bar}.csv"), index=False)

    print(f"\n{'=' * 104}\nq5-q1 forward return in bps, entry at the NEXT bar's "
          f"open.  cost bar: " + "  ".join(f"{k} {v}" for k, v in COSTS.items()))
    print("=" * 104)
    print(f"{'feature':16} {'h':>7} {'n':>7} {'q5-q1':>8} {'|partial':>9} "
          f"{'mono':>5} {'null':>7} {'3rds':>5}  clears")
    for _, r in res.iterrows():
        gates = ",".join(k for k in COSTS if r[f"clears_{k}"]) or "-"
        star = "*" if r.beats_null else " "
        tag = "" if r["new"] else "  (control)"
        p = f"{r.partial_delta:9.2f}" if r.partial_delta == r.partial_delta else "        -"
        print(f"{r.feature:16} {r.h_hours:6.1f}h {r.n:7d} {r.spread:8.2f} {p} "
              f"{r.monotone:5.2f} {r.null_best:7.2f}{star} {r.thirds:>5}  {gates}{tag}")

    new = res[res["new"]]
    print(f"\n-- the kill criterion --")
    live = new[new["partial_delta"].abs() > COSTS["taker1x"]]
    print(f"location features clearing 14bps on the DELTA-CONTROLLED spread: "
          f"{len(live)} of {len(new)}")
    print(f"location features clearing 14bps unconditionally:               "
          f"{int((new['spread'].abs() > COSTS['taker1x']).sum())} of {len(new)}")
    print(f"location features beating their own null:                       "
          f"{int(new['beats_null'].sum())} of {len(new)}")

    try:
        from core.search_cost import verdict
        print("\n-- the price of the search --")
        print(verdict(len(res), 95.0, NSEED))
    except Exception as e:                                    # pragma: no cover
        print(f"(search_cost unavailable: {e})")

    print(f"\nwritten: {os.path.join(OUT, f'stage1_location_{args.bar}.csv')}")


if __name__ == "__main__":
    main()
