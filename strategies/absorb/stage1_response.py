"""H-022 stage 1 — is aggressive flow that FAILS TO MOVE PRICE informative?

The H-008 killer test, asked of a feature nobody here has measured yet.

Why this gap exists. H-006 measured taker aggression against 8-72h forward
returns and found it FLAT: +10.8/+12.5/+10.7/+12.0/+12.2 bps across quintiles,
a signal that says nothing. H-021 measured 5m taker imbalance by clock phase
against 4-12h returns and found something real but 5x too small to pay for.
Neither looked at the 15m-4h band, and neither built the feature this file is
about.

Because "how much flow" is the wrong question. Aggression is not directional on
its own - H-006 proved that. What should carry information is aggression
MEASURED AGAINST THE PRICE RESPONSE IT PRODUCED:

  * heavy buying that lifts price      -> the buyer is paying for liquidity and
                                          getting it. Nothing to fade.
  * heavy buying that does NOT lift it -> somebody passive is absorbing every
                                          market order. That somebody has size
                                          and is not in a hurry.

MECHANISM, stated before any result. The counterparty is an institution working
a large order who wants the fill and not the tick, and who is therefore
price-INSENSITIVE in the opposite way to the aggressor: the aggressor has a
deadline, the absorber has a quantity. When the aggressor is done, the passive
side is still there, and price drifts back toward where the absorber was
trading. That is the same class of counterparty argument that made H-009 work -
somebody trading for a reason other than expected return - and it is the third
of the three candidate edges H-006's notes listed and never tested.

FEATURE. Both terms are z-scored on a shifted trailing window, so neither the
flow nor the return is scored against itself:

    absorb_k = z(signed taker flow over k) - z(log return over k)

Large positive = far more buying than the price move justifies (absorbed
buying, expected to FADE). Large negative = absorbed selling. If the mechanism
is real the response is DOWNWARD sloping and monotone.

Everything is reported in basis points against four round trips, because cost
is what has killed the last four hypotheses here:

    taker 1x  14bps   the repo's standing assumption (5bps taker + 2bps slip)
    taker 2x  28bps   the stress case every board number is quoted at
    mixed      9bps   maker in (2bps), taker out (5bps), 2bps slip
    maker 2x   8bps   both sides passive at 2bps, doubled for stress

The mixed and maker columns are new here. The repo's own notes name maker
entries as the one untried lever on H-006 and never priced one. This does not
assume those fills are achievable - stage 2 has to earn that with a queue
check - it only asks whether the edge would be worth the trouble if they were.

Run: .venv/bin/python strategies/absorb/stage1_response.py
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
OUT = ROOT / "backtests" / "absorb"
OUT.mkdir(parents=True, exist_ok=True)

SYMS = ("BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT", "DOGEUSDT", "ADAUSDT")
# the untested band: 15m to 4h, in 5-minute bars
HORIZONS = (3, 6, 12, 24, 48)
HNAME = {3: "15m", 6: "30m", 12: "1h", 24: "2h", 48: "4h"}
WINDOWS = ((3, "15m"), (6, "30m"), (12, "1h"), (24, "2h"), (48, "4h"))
NSEEDS = 5
NBUCKET = 5
COSTS = {"taker1x": 14.0, "taker2x": 28.0, "mixed": 9.0, "maker2x": 8.0}


def _z(s: pd.Series, win: int) -> pd.Series:
    """Trailing z-score, baseline shifted one bar so nothing scores itself."""
    m = s.rolling(win, min_periods=win // 2).mean().shift(1)
    v = s.rolling(win, min_periods=win // 2).std(ddof=0).shift(1)
    return (s - m) / v.replace(0.0, np.nan)


def features(df: pd.DataFrame, win: int = 288) -> pd.DataFrame:
    """Absorption, and the two terms it is built from, at five windows.

    `flow` and `ret` are carried separately on purpose: if `absorb` ranks
    returns but neither ingredient does, the interaction is doing the work,
    which is the claim. If `flow` alone does it, this is just H-006's aggression
    feature at a shorter horizon and should be reported as that instead."""
    f = pd.DataFrame(index=df.index)
    px = df.close
    buy = df.taker_buy_base
    sell = (df.volume - buy).clip(lower=0.0)
    signed = buy - sell
    vol = df.volume.replace(0.0, np.nan)

    for k, name in WINDOWS:
        flow = signed.rolling(k).sum() / vol.rolling(k).sum().replace(0.0, np.nan)
        ret = np.log(px / px.shift(k))
        fz, rz = _z(flow, win), _z(ret, win)
        f[f"flow_{name}"] = fz
        f[f"ret_{name}"] = rz
        # THE FEATURE: flow the price did not pay attention to.
        f[f"absorb_{name}"] = fz - rz
        # the same thing, but only where there was real aggression to absorb.
        # Absorption is meaningless on a quiet bar: a flat tape with no flow
        # scores absorb ~ 0 either way, which dilutes the buckets with noise.
        f[f"absorbq_{name}"] = (fz - rz).where(fz.abs() > 1.0)
    return f


def response(f: pd.Series, r: pd.Series, n: int = NBUCKET):
    """Mean forward return per feature bucket, in bps. Full-sample quantiles:
    hindsight about the distribution, not about the returns."""
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

    24h returns on 5m bars overlap heavily, so a t-statistic on 600k rows is a
    lie. Year-by-year sign agreement and the block null are the real defence."""
    m = f.notna() & r.notna()
    if m.sum() < 2000:
        return 0, 0
    d = pd.DataFrame({"f": f[m], "r": r[m]})
    full = np.nan
    signs = []
    try:
        d["b"] = pd.qcut(d.f, NBUCKET, labels=False, duplicates="drop")
    except ValueError:
        return 0, 0
    g = d.groupby("b").r.mean()
    full = np.sign(g.iloc[-1] - g.iloc[0])
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
            df = of.load(sym, FEEDS)
        except FileNotFoundError as e:
            print(f"{sym}: {e}")
            continue
        F = features(df)
        R = of.forward_returns(df, HORIZONS)
        print(f"\n{sym}: {len(df):,} bars  {df.index[0]:%Y-%m-%d} -> "
              f"{df.index[-1]:%Y-%m-%d}  ({len(F.columns)} features)")

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

    out = pd.DataFrame(rows)
    out.to_csv(OUT / "stage1_response.csv", index=False)

    print(f"\n{'=' * 100}\nTOP CELLS BY |SPREAD| (bps). Cost gates: "
          f"taker1x {COSTS['taker1x']}  taker2x {COSTS['taker2x']}  "
          f"mixed {COSTS['mixed']}  maker2x {COSTS['maker2x']}\n{'=' * 100}")
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
    out["family"] = out.feature.str.replace(r"_[0-9]+[mh]$", "", regex=True)
    fam = out.groupby("family").agg(cells=("spread", "size"),
                                    med_abs=("abs_spread", "median"),
                                    max_abs=("abs_spread", "max"),
                                    beat=("beats_null", "mean"))
    print(fam.sort_values("med_abs", ascending=False).round(3).to_string())
    print(f"\nwrote {OUT / 'stage1_response.csv'}")


if __name__ == "__main__":
    main()
