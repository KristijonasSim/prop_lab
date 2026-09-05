"""H-022 stage 2 — the same features, but only in the tails.

Stage 1 cut quintiles and found nothing bigger than 2.5bps against an 8bps
maker round trip. A quintile averages over 20% of the sample, so a signal that
only bites in its extreme tail is diluted 10:1 by that construction. H-006 hit
exactly this: every configuration it selected sat at the EDGE of its grid
(q=0.05, later extended to q=0.02), which is the grid telling you the useful
region was outside it.

So this asks the same question at 10%, 5%, 2% and 1% tails, and reports the
FADE return - the mean forward return of the tail, signed so that positive
means the fade made money:

    tail_hi (absorbed buying)  -> fade = short -> pnl = -fwd
    tail_lo (absorbed selling) -> fade = long  -> pnl = +fwd

Both tails are also reported separately, because an edge that only exists on
one side is a different (and usually worse) object than a symmetric one.

Costs are unchanged: 14 / 28 / 9 / 8 bps. The number that matters is the
per-trade fade return against the cheapest realistic round trip, 8bps.

Run: .venv/bin/python strategies/absorb/stage2_tails.py [SYM ...]
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from strategies.orderflow import orderflow as of                 # noqa: E402
from strategies.absorb.stage1_response import features, HORIZONS, HNAME  # noqa: E402

FEEDS = ROOT / "data" / "feeds"
OUT = ROOT / "backtests" / "absorb"
OUT.mkdir(parents=True, exist_ok=True)

SYMS = ("BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT", "DOGEUSDT", "ADAUSDT")
TAILS = (0.10, 0.05, 0.02, 0.01)
NSEEDS = 5
COSTS = {"taker1x": 14.0, "taker2x": 28.0, "mixed": 9.0, "maker2x": 8.0}
# trailing quantile window: 30 days of 5m bars, shifted, so the threshold a bar
# is judged against is one a live system could have computed that morning.
BAND = 288 * 30
STEP = 288                      # thresholds recomputed once a day, not every bar


def thresholds(f: pd.Series, q: float, band: int = BAND, step: int = STEP):
    """Tail thresholds from a trailing window, recomputed once per day.

    Two reasons this is a stride and not `rolling().quantile()`. It is ~300x
    faster, which is what makes a six-coin grid finish at all - the repo hit
    this exact wall in `orderflow.thresholds`. And it is the more honest
    object: nobody recalibrates a percentile every five minutes, and the window
    ends at the anchor bar, so a threshold is built only from bars that had
    already closed when it was set. No shift is needed because no part of the
    window includes the bar being judged."""
    v = f.to_numpy(dtype=float)
    n = len(v)
    lo = np.full(n, np.nan)
    hi = np.full(n, np.nan)
    for i in range(step, n + step, step):
        w = v[max(0, i - band):i]
        w = w[~np.isnan(w)]
        if len(w) < band // 4:
            continue
        a, b = np.quantile(w, [q, 1.0 - q])
        lo[i:i + step] = a
        hi[i:i + step] = b
    return (pd.Series(lo, index=f.index, name="lo"),
            pd.Series(hi, index=f.index, name="hi"))


def tail_fade(f: pd.Series, r: pd.Series, q: float, th=None):
    """Mean fade return in bps for the two tails, on trailing thresholds.

    Trailing, not full-sample: stage 1 used full-sample cuts to ask whether
    anything was there at all, but a tail threshold is exactly the kind of
    hindsight that manufactures an edge, so from here it has to be causal."""
    lo, hi = thresholds(f, q) if th is None else th
    m = f.notna() & r.notna() & lo.notna() & hi.notna()
    if m.sum() < 5000:
        return None
    f, r, lo, hi = f[m], r[m], lo[m], hi[m]
    up, dn = f >= hi, f <= lo
    if up.sum() < 200 or dn.sum() < 200:
        return None
    # fade: short the absorbed-buying tail, long the absorbed-selling tail
    pnl = pd.concat([-r[up], r[dn]]) * 1e4
    return {
        "n_trades": int(up.sum() + dn.sum()),
        "fade_bps": float(pnl.mean()),
        "hi_bps": float(-r[up].mean() * 1e4),
        "lo_bps": float(r[dn].mean() * 1e4),
        "hit_rate": float((pnl > 0).mean()),
    }


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
        # the tails only matter for the features stage 1 said were alive
        cols = [c for c in F.columns if c.startswith(("absorbq_", "absorb_", "flow_"))]
        print(f"\n{sym}: {len(df):,} bars, {len(cols)} features x "
              f"{len(HORIZONS)} horizons x {len(TAILS)} tails")
        for name in cols:
            f = F[name]
            # thresholds depend on (feature, tail) only - never on the horizon -
            # so they are built once here and reused across all five. Same for
            # each null seed. This is the difference between a grid that
            # finishes and one that does not.
            th = {q: thresholds(f, q) for q in TAILS}
            shuf = [of.block_shuffle(f, seed=sd * 6271) for sd in range(NSEEDS)]
            th_null = [{q: thresholds(sf, q) for q in TAILS} for sf in shuf]
            for h in HORIZONS:
                r = R[f"fwd_{h}"]
                for q in TAILS:
                    res = tail_fade(f, r, q, th[q])
                    if res is None:
                        continue
                    nulls = []
                    for sf, tn in zip(shuf, th_null):
                        nres = tail_fade(sf, r, q, tn[q])
                        if nres:
                            nulls.append(nres["fade_bps"])
                    nb = max(nulls) if nulls else np.nan
                    rows.append({
                        "sym": sym, "feature": name, "horizon": HNAME[h], "tail": q,
                        **res, "null_best": nb,
                        "beats_null": bool(res["fade_bps"] > nb) if nb == nb else False,
                        **{f"clears_{k}": bool(res["fade_bps"] > v)
                           for k, v in COSTS.items()},
                    })
        print(f"  {len([x for x in rows if x['sym'] == sym])} cells")

    out = pd.DataFrame(rows)
    out.to_csv(OUT / "stage2_tails.csv", index=False)

    print(f"\n{'=' * 104}\nTOP BY FADE RETURN PER TRADE (bps). "
          f"Gates: maker2x 8 | mixed 9 | taker1x 14 | taker2x 28\n{'=' * 104}")
    print(f"{'sym':9} {'feature':16} {'hz':4} {'tail':>5} {'trades':>7} "
          f"{'fade':>7} {'hi':>6} {'lo':>6} {'hit%':>5} {'null':>7} gates")
    for _, r in out.sort_values("fade_bps", ascending=False).head(30).iterrows():
        gates = "".join(g for g, k in (("m", "clears_maker2x"), ("M", "clears_mixed"),
                                       ("T", "clears_taker1x"), ("2", "clears_taker2x"))
                        if r[k])
        star = "*" if r.beats_null else " "
        print(f"{r['sym']:9} {r.feature:16} {r.horizon:4} {r["tail"]:5.2f} "
              f"{r.n_trades:7d} {r.fade_bps:7.2f} {r.hi_bps:6.2f} {r.lo_bps:6.2f} "
              f"{100*r.hit_rate:5.1f} {r.null_best:7.2f}{star} {gates}")

    print(f"\n-- cells clearing each gate (of {len(out)}), and how many beat their null --")
    for k, v in COSTS.items():
        sub = out[out[f"clears_{k}"]]
        print(f"  {k:9} > {v:5.1f}bps : {len(sub):5d}, {int(sub.beats_null.sum()):5d} beat null")

    print("\n-- does a tighter tail help? median fade bps by tail --")
    print(out.groupby("tail").fade_bps.agg(["median", "max", "size"]).round(2).to_string())
    print(f"\nwrote {OUT / 'stage2_tails.csv'}")


if __name__ == "__main__":
    main()
