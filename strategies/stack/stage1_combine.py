"""TASK 3 — are the weak signals independent enough to add up past 14bps?

THE SITUATION. Five feeds have now been measured here and every one lands in the
same band, individually dead against a 14bps taker round trip:

    DVOL level (H-025)          8.9 bps  @4h, survives 1d/1w/1mo block nulls
    depth imbalance (H-024)     7.9 bps  @4h, best honest cell of 935
    absorption (H-022)          6.55 bps @4h
    quarter-hour (H-021)        2.67 bps
    perp premium (H-013)        real, ~10.9bps quintile spread, dead in a grid

Nobody has asked whether they are the SAME signal. If their correlations are
low, an equal-weighted combination of five 7bps edges is not a 7bps edge — the
signal adds linearly and the noise adds in quadrature, so five independent
signals of equal size give sqrt(5) ~ 2.24x, which is 15-20bps and clears taker.
If they are all reading the same underlying crowding variable, the combination
is worth barely more than the best one and this whole direction is finished.

That is the entire question, and the data to answer it is already on disk.

HOW IT IS KEPT HONEST. Three rules, because a combination study is the easiest
place in quant research to fool yourself:

  1. **Weights and signs are fitted on the FIRST half only** and never refitted.
     A sign chosen on the full sample is hindsight, and with a dozen features it
     is enough hindsight to manufacture any result you like.
  2. **The benchmark is the best SINGLE feature measured on the same test half**,
     not the best single feature from the papers or from an earlier study on a
     different window. A combination that cannot beat its own best ingredient
     out of sample has discovered nothing.
  3. **The null is block-shuffled**, at a block long enough for the slowest
     ingredient (DVOL persists for weeks), as stage 2 of H-025 had to learn.

TWO UNIVERSES, because the feeds start at different times and forcing them onto
one window throws away years:

    all       everything including depth   2023-01 onward
    no_depth  everything else              2021-04 onward (DVOL is the binding start)

Run: .venv/bin/python strategies/stack/stage1_combine.py
     .venv/bin/python strategies/stack/stage1_combine.py BTCUSDT
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from strategies.orderflow import orderflow as of                     # noqa: E402
from strategies.absorb import stage1_response as absorb              # noqa: E402
from strategies.depth import stage1_response as depth                # noqa: E402
from strategies.dvol import stage1_response as dvol                  # noqa: E402

FEEDS = ROOT / "data" / "feeds"
OUT = ROOT / "backtests" / "stack"
OUT.mkdir(parents=True, exist_ok=True)

SYMS = ("BTCUSDT", "ETHUSDT")
CUR = {"BTCUSDT": "BTC", "ETHUSDT": "ETH"}
HORIZONS = (12, 24, 48)                  # 1h, 2h, 4h — where every edge lives
HNAME = {12: "1h", 24: "2h", 48: "4h"}
COSTS = {"taker1x": 14.0, "taker2x": 28.0, "mixed": 9.0, "maker2x": 8.0}
NBUCKET = 5
NSEEDS = 20
NULL_BLOCK = 288 * 7                     # a week: long enough for DVOL
TOPK = (3, 5, 8)
MIN_SNAP = 5


def build(sym: str) -> pd.DataFrame:
    """Every measured feed on one 5-minute clock, each at its own honest lag."""
    px = pd.read_parquet(FEEDS / f"{sym}_perp_5m.parquet").sort_index()
    px = px[~px.index.duplicated(keep="last")]
    mx = pd.read_parquet(FEEDS / f"{sym}_metrics_5m.parquet")
    df = px.join(mx, how="inner").sort_index()

    F = of.features(df)                                  # H-006 crowd / OI / flow
    A = absorb.features(df)                              # H-022 absorption
    keep = pd.DataFrame(index=df.index)
    for c in ("crowd_z", "size_z", "disagree", "taker_z", "cvd_z",
              "quad_1h", "quad_4h", "dcrowd_4h"):
        if c in F:
            keep[c] = F[c]
    for c in ("absorbq_1h", "absorbq_4h"):
        if c in A:
            keep[c] = A[c]

    # H-013 perp premium — dead standalone, kept because this study is about
    # whether dead-alone signals are dead together.
    pp = FEEDS / f"{sym}_premium_5m.parquet"
    if pp.exists():
        prem = pd.read_parquet(pp)["close"].reindex(df.index)
        keep["prem_z"] = absorb._z(prem, 288)

    # H-021 quarter-hour: the clock phase, as a pair of continuous terms so it
    # can enter a linear score at all.
    minute = df.index.minute.to_numpy()
    phase = 2 * np.pi * (minute % 60) / 60.0
    keep["qh_sin"], keep["qh_cos"] = np.sin(phase), np.cos(phase)

    # H-025 DVOL
    cur = CUR.get(sym)
    vp = FEEDS / f"{cur}_dvol_3600s.parquet" if cur else None
    if vp is not None and vp.exists():
        dv = pd.read_parquet(vp)
        obs = pd.DataFrame({"ts": dv.index + pd.Timedelta(hours=1),
                            "dvol": dv.dvol_close.to_numpy(float)}).sort_values("ts")
        left = pd.DataFrame({"i": np.arange(len(df)), "t": df.index}).sort_values("t")
        j = pd.merge_asof(left, obs, left_on="t", right_on="ts",
                          direction="backward", tolerance=pd.Timedelta(hours=6))
        df["dvol"] = j.sort_values("i").dvol.to_numpy()
        D = dvol.features(df)
        for c in ("dvolz", "ddvol_1d", "vrpz"):
            if c in D:
                keep[c] = D[c]

    # H-024 book depth
    dp = FEEDS / f"{sym}_depth_5m.parquet"
    if dp.exists():
        d = pd.read_parquet(dp)
        d = d[d.n_snap >= MIN_SNAP]
        joined = df.join(d, how="left")
        DD = depth.features(joined)
        for c in ("imbz_1", "imbz_2", "imbz_5", "imbxthin_1", "hollowz", "depz_1"):
            if c in DD:
                keep[c] = DD[c]

    R = of.forward_returns(df, HORIZONS)
    for h in HORIZONS:
        keep[f"fwd_{h}"] = R[f"fwd_{h}"]
    return keep


def spread_bps(f: pd.Series, r: pd.Series, n: int = NBUCKET) -> float:
    m = f.notna() & r.notna()
    if m.sum() < 2000:
        return np.nan
    try:
        b = pd.qcut(f[m], n, labels=False, duplicates="drop")
    except ValueError:
        return np.nan
    g = (r[m] * 1e4).groupby(b).mean()
    return float(g.iloc[-1] - g.iloc[0])


def run(sym: str, cols: list[str], label: str, rows: list, corr_out: dict):
    df = build(sym)
    sub = df[cols + [f"fwd_{h}" for h in HORIZONS]].dropna(subset=cols)
    if len(sub) < 20000:
        print(f"  {sym}/{label}: only {len(sub):,} complete rows, skipped")
        return
    half = sub.index[len(sub) // 2]
    tr, te = sub[sub.index < half], sub[sub.index >= half]
    print(f"\n  {sym}/{label}: {len(sub):,} rows  {sub.index[0]:%Y-%m-%d} -> "
          f"{sub.index[-1]:%Y-%m-%d}   train<{half:%Y-%m-%d}  "
          f"({len(tr):,} / {len(te):,})", flush=True)

    # correlation between the ingredients, on TRAIN only
    c = tr[cols].corr().abs()
    iu = np.triu_indices_from(c.to_numpy(), k=1)
    pair = c.to_numpy()[iu]
    corr_out[f"{sym}/{label}"] = {
        "median_abs_corr": float(np.median(pair)),
        "max_abs_corr": float(np.max(pair)),
        "n_features": len(cols),
    }
    print(f"    pairwise |corr| on train: median {np.median(pair):.3f}  "
          f"max {np.max(pair):.3f}")

    for h in HORIZONS:
        rtr, rte = tr[f"fwd_{h}"], te[f"fwd_{h}"]
        # sign and strength of each ingredient, fitted on TRAIN ONLY
        ic = {}
        for col in cols:
            m = tr[col].notna() & rtr.notna()
            if m.sum() < 2000:
                continue
            ic[col] = float(np.corrcoef(tr[col][m], rtr[m])[0, 1])
        if not ic:
            continue
        # the benchmark: best single ingredient on the TEST half, sign from train
        singles = {col: spread_bps(te[col] * np.sign(v), rte)
                   for col, v in ic.items()}
        best_col = max(singles, key=lambda k: abs(singles[k]))
        best_single = singles[best_col]

        z = te[cols].apply(lambda s: (s - tr[s.name].mean()) / tr[s.name].std())
        combos = {}
        signs = {c_: np.sign(ic.get(c_, 0.0)) for c_ in cols}
        combos["equal_all"] = sum(z[c_] * signs[c_] for c_ in cols if c_ in ic)
        combos["ic_weighted"] = sum(z[c_] * ic[c_] for c_ in cols if c_ in ic)
        order = sorted(ic, key=lambda k: -abs(ic[k]))
        for k in TOPK:
            if k <= len(order):
                combos[f"equal_top{k}"] = sum(z[c_] * signs[c_] for c_ in order[:k])

        for cname, s in combos.items():
            sp = spread_bps(s, rte)
            nulls = []
            for seed in range(NSEEDS):
                ns = spread_bps(of.block_shuffle(s, seed=seed * 7919 + h,
                                                 block=NULL_BLOCK), rte)
                if ns == ns:
                    nulls.append(abs(ns))
            nb = max(nulls) if nulls else np.nan
            rows.append({
                "sym": sym, "universe": label, "horizon": HNAME[h],
                "combo": cname, "n_test": len(te), "n_feat": len(cols),
                "spread": sp, "abs_spread": abs(sp) if sp == sp else np.nan,
                "best_single": best_single, "best_single_feature": best_col,
                "lift_vs_best": (abs(sp) - abs(best_single))
                                if sp == sp else np.nan,
                "null_max": nb,
                "beats_null": bool(abs(sp) > nb) if (nb == nb and sp == sp) else False,
                **{f"clears_{k}": bool(abs(sp) > v) if sp == sp else False
                   for k, v in COSTS.items()},
            })


def main():
    syms = sys.argv[1:] or list(SYMS)
    rows, corr_out = [], {}
    no_depth = ["crowd_z", "size_z", "disagree", "taker_z", "cvd_z", "quad_1h",
                "quad_4h", "dcrowd_4h", "absorbq_1h", "absorbq_4h", "prem_z",
                "qh_sin", "qh_cos", "dvolz", "ddvol_1d", "vrpz"]
    with_depth = no_depth + ["imbz_1", "imbz_2", "imbz_5", "imbxthin_1",
                             "hollowz", "depz_1"]
    for sym in syms:
        for label, cols in (("no_depth", no_depth), ("all", with_depth)):
            try:
                run(sym, cols, label, rows, corr_out)
            except FileNotFoundError as e:
                print(f"  {sym}/{label}: {e}")

    if not rows:
        print("nothing measured")
        return
    out = pd.DataFrame(rows)
    out.to_csv(OUT / "stage1_combine.csv", index=False)

    print(f"\n{'=' * 110}\nDOES STACKING BEAT ITS OWN BEST INGREDIENT, "
          f"OUT OF SAMPLE?\n{'=' * 110}")
    print(f"{'sym':9} {'universe':9} {'hz':4} {'combo':12} {'spread':>8} "
          f"{'best1':>8} {'lift':>7} {'null':>7}  {'gates':6} best single")
    for _, r in out.sort_values("abs_spread", ascending=False).head(30).iterrows():
        gates = "".join(g for g, k in (("T", "clears_taker1x"), ("2", "clears_taker2x"),
                                       ("M", "clears_mixed"), ("m", "clears_maker2x"))
                        if r[k])
        star = "*" if r.beats_null else " "
        print(f"{r['sym']:9} {r.universe:9} {r.horizon:4} {r.combo:12} "
              f"{r.spread:8.1f} {r.best_single:8.1f} {r.lift_vs_best:7.1f} "
              f"{r.null_max:7.1f}{star} {gates:6} {r.best_single_feature}")

    print(f"\n-- correlation between the ingredients (train half) --")
    for k, v in corr_out.items():
        print(f"  {k:22} {v['n_features']:2d} features   "
              f"median |corr| {v['median_abs_corr']:.3f}   "
              f"max {v['max_abs_corr']:.3f}")

    print(f"\n-- gates cleared, of {len(out)} combination cells --")
    for k, v in COSTS.items():
        sub = out[out[f"clears_{k}"]]
        print(f"  {k:9} > {v:5.1f}bps : {len(sub):4d} cells, "
              f"{int(sub.beats_null.sum()):4d} beat null")

    print(f"\n-- does stacking add anything at all? --")
    print(f"  combinations beating their own best ingredient: "
          f"{int((out.lift_vs_best > 0).sum())} of {len(out)}")
    print(f"  median lift over best single: {out.lift_vs_best.median():+.2f} bps")
    print(f"\nwrote {OUT / 'stage1_combine.csv'}")


if __name__ == "__main__":
    main()
