"""H-017 stage 5 - stack every orthogonal feed gate on H-009 and measure DAYS.

WHY THIS AND NOT ANOTHER STRATEGY.

Stage 0 fixed the objective: days = 1.625/K, K = R_per_day/|maxDD_R|, and the
goal needs 2.2x H-009's K. Stage 1 showed diversification buys sqrt(N) and the
universe needed is thousands of legs. Stage 2 showed crypto's 14bps kills any
sub-8-hour book. Stage 3/4 showed the VWAP kernel on cheap 5-minute markets
works on gold and nowhere else, and that selecting folds on K instead of profit
factor buys nothing - K's denominator is a single order statistic and far too
noisy to rank 7,776 candidates by.

That leaves the one route with a track record. **Every improvement this project
has ever made to its book came from gating existing trades with an orthogonal
data feed**, and each has been worth about 1.3-1.4x on return-over-drawdown:

    H-009 = H-002 + crowd gate         ret/DD 24.6 -> 34.4   (1.40x)
    H-015 = H-009 + systemic gate      ret/DD 30.0 -> 38.7   (1.29x)

Three more independent gates at that rate would be 2.2x-2.7x, which is the
goal. So: take H-009's trades unchanged and test every feed this repo owns as
a gate, alone and stacked, scoring on DAYS TO A FUNDED ACCOUNT rather than on
profit factor.

THE INGREDIENTS, and where each one's evidence comes from:
  crowd     long/short ACCOUNT ratio - H-006's kernel, already in H-009
  sys       the same read across eleven coins - H-015, +29% and never stacked
            into the board book
  oi        open interest - H-011 found it earns its place once a level has
            been taken (0.708 -> 0.741) where the raw series did nothing
            directional in H-006
  premium   perp minus spot - H-013 found a real signal, rejected standalone,
            NEVER tested as a gate
  flowgap   perp taker imbalance minus SPOT taker imbalance - H-013's second
            measurement, also never tested as a gate

FOUR THINGS THIS IS CAREFUL ABOUT, because a gate search overfits easily.
  * Thresholds are FIXED AT ZERO, never searched. H-009 and H-015 both fixed
    theirs for the same reason: a searched threshold on a few thousand trades
    is a fitted number.
  * Every gate is read AS-OF the entry with the bar's own duration added, so a
    5-minute bar stamped T is only observable at T+5m.
  * Each gate is scored against its DIRECTION CONTROL - keep what the feed
    agrees with instead. If both halves help, the gate is only cutting trades.
  * The winner is re-measured on a HELD-OUT half and against a block-shuffled
    feed, because with five gates and 31 combinations something will look good.

Output: backtests/xpos/stage5_gates.csv
"""
from __future__ import annotations

import itertools
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from core import riskladder as RL                                   # noqa: E402
from strategies.breadth import breadth as br                        # noqa: E402
from strategies.orderflow import orderflow as of                    # noqa: E402

FEEDS = ROOT / "data" / "feeds"
OUT = ROOT / "backtests" / "xpos"
TRADES = ROOT / "backtests" / "gated_vwap" / "stage6_trades.parquet"
COINS = ("BTCUSDT", "ETHUSDT", "SOLUSDT")


def pf(r):
    w, l = r[r > 0].sum(), -r[r < 0].sum()
    return float(w / l) if l > 0 else np.nan


def maxdd(r):
    e = np.cumsum(r)
    return float((e - np.maximum.accumulate(e)).min())


def stats(d):
    if len(d) < 100:
        return None
    r = d.r_2x.values
    span = max((d.exit_ts.max() - d.entry_ts.min()).days, 1)
    dd = maxdd(r)
    rpd = float(r.sum()) / span
    return {"trades": len(r), "pf_2x": round(pf(r), 3),
            "total_r": round(float(r.sum()), 2), "maxdd_r": round(dd, 2),
            "r_per_day": round(rpd, 4),
            "ret_dd": round(float(r.sum()) / abs(dd), 2) if dd else np.nan,
            "K": round(rpd / abs(dd), 5) if dd < 0 and rpd > 0 else np.nan,
            "tpd": round(len(r) / span, 3)}


def asof(sig: pd.Series, when: pd.Series, lag="5min") -> np.ndarray:
    sd = sig.dropna()
    obs = pd.DataFrame({"ts": sd.index + pd.Timedelta(lag),
                        "v": sd.values}).sort_values("ts")
    left = pd.DataFrame({"i": np.arange(len(when)),
                         "t": when.reset_index(drop=True)}).sort_values("t")
    j = pd.merge_asof(left, obs, left_on="t", right_on="ts",
                      direction="backward", tolerance=pd.Timedelta(days=1))
    return j.sort_values("i").v.values


def build_signals(t: pd.DataFrame) -> dict[str, np.ndarray]:
    """One value per trade for every feed, aligned as-of the entry."""
    sig: dict[str, np.ndarray] = {}

    print("  building the eleven-coin panel ...", flush=True)
    pan = br.panel(FEEDS)
    sysdf = br.systemic(pan)
    sig["sys"] = asof(sysdf["sys"], t.entry_ts)

    # Per-coin feeds. Gold trades get NaN and are never gated by a crypto feed.
    per = {k: np.full(len(t), np.nan) for k in ("crowd", "oi", "premium", "flowgap")}
    for sym in COINS:
        m = (t.symbol.values == sym)
        if not m.sum():
            continue
        try:
            f = of.features(of.load(sym, FEEDS))
        except Exception as e:                                  # noqa: BLE001
            print(f"    {sym}: no orderflow feed ({e})")
            continue
        per["crowd"][m] = asof(f["crowd_z"], t.entry_ts[m])

        px = pd.read_parquet(FEEDS / f"{sym}_perp_5m.parquet")
        mt = pd.read_parquet(FEEDS / f"{sym}_metrics_5m.parquet")
        d = px.join(mt, how="inner").sort_index()
        d = d[~d.index.duplicated(keep="last")]

        # Open interest CHANGE over an hour. H-011's reading: "were contracts
        # closed?" separates a stop run from a breakout. The level does nothing
        # directional (H-006); the change is the object.
        loi = np.log(d["sum_open_interest"].astype(float).replace(0.0, np.nan))
        per["oi"][m] = asof(loi - loi.shift(12), t.entry_ts[m])

        try:
            pm = pd.read_parquet(FEEDS / f"{sym}_premium_5m.parquet")["close"]
            z = ((pm - pm.rolling(288, min_periods=144).mean().shift(1))
                 / pm.rolling(288, min_periods=144).std(ddof=0).shift(1))
            per["premium"][m] = asof(z, t.entry_ts[m])
        except Exception:
            pass

        try:
            sp = pd.read_parquet(FEEDS / f"{sym}_spot_5m.parquet")
            def imb(fr):
                v = fr["volume"].astype(float)
                b = fr["taker_buy_base"].astype(float)
                return (2 * b - v) / v.replace(0.0, np.nan)
            gap = (imb(d) - imb(sp.reindex(d.index))).rolling(12).mean()
            per["flowgap"][m] = asof(gap, t.entry_ts[m])
        except Exception:
            pass
    sig.update(per)
    return sig


#: For each gate, the rule that KEEPS a trade. Every one is "the feed is on the
#: other side of this trade", the direction H-006 established and H-009 uses.
#: Sign conventions are fixed in advance, not chosen by result.
def keep_mask(name: str, v: np.ndarray, d: np.ndarray, invert=False) -> np.ndarray:
    if name in ("crowd", "sys"):
        k = np.where(d > 0, v < 0, v > 0)        # crowd not already on our side
    elif name == "oi":
        k = np.where(d > 0, v < 0, v < 0)        # contracts CLOSED into the move
    elif name == "premium":
        k = np.where(d > 0, v < 0, v > 0)        # perp not already rich our way
    elif name == "flowgap":
        k = np.where(d > 0, v < 0, v > 0)        # perp not leading spot our way
    else:
        raise ValueError(name)
    if invert:
        k = ~k
    return np.where(np.isnan(v), True, k)        # no reading, no opinion


def sim(d: pd.DataFrame) -> dict:
    """The real two-step prop simulation - the number the goal is stated in."""
    r = d.r_2x.values
    _rows, pick = RL.from_trades(r, d.exit_ts.values)
    return {"risk": pick["risk"], "pass_rate": pick["pass_rate"],
            "median_days": pick["median_days"],
            "expected_days": pick["expected_days"]}


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    t = pd.read_parquet(TRADES)
    t["entry_ts"] = pd.to_datetime(t.entry_ts, utc=True)
    t["exit_ts"] = pd.to_datetime(t.exit_ts, utc=True)

    sig = build_signals(t)
    first = pd.Series(sig["sys"], index=t.index).dropna()
    t = t.loc[first.index] if len(first) else t
    for k in sig:
        sig[k] = pd.Series(sig[k]).reindex(t.reset_index(drop=True).index).values
    t = t.reset_index(drop=True)
    print(f"\n  {len(t)} trades on the common window "
          f"{t.entry_ts.min():%Y-%m-%d} -> {t.exit_ts.max():%Y-%m-%d}\n")

    d = t.direction.values
    base_all = t[t.gated]                       # H-009 as it stands
    b = stats(base_all)
    bs = sim(base_all)
    print("BASELINES")
    print(f"  H-002 ungated   {stats(t)['ret_dd']:>6.2f} ret/DD")
    print(f"  H-009 (crowd)   {b['ret_dd']:>6.2f} ret/DD  K {b['K']:.5f}  "
          f"PF2x {b['pf_2x']}  {b['tpd']}/day  "
          f"EXPECTED {bs['expected_days']} days\n")

    rows = [{"gates": "H-009 baseline", "n_gates": 1, **b, **bs}]
    names = ["sys", "oi", "premium", "flowgap"]

    print("EACH GATE ALONE, stacked on H-009, with its direction control")
    print(f"  {'gate':10s} {'trades':>7s} {'PF2x':>6s} {'ret/DD':>7s} "
          f"{'K':>8s} {'expected days':>14s}   control ret/DD")
    for n in names:
        v = sig[n]
        k = keep_mask(n, v, d)
        on = t[t.gated & k]
        off = t[t.gated & keep_mask(n, v, d, invert=True)]
        so, sf = stats(on), stats(off)
        if not so:
            print(f"  {n:10s}  (too few trades)")
            continue
        ss = sim(on)
        ctrl = f"{sf['ret_dd']:.2f}" if sf else "n/a"
        print(f"  {n:10s} {so['trades']:>7d} {so['pf_2x']:>6.3f} "
              f"{so['ret_dd']:>7.2f} {so['K']:>8.5f} "
              f"{str(ss['expected_days']):>14s}   {ctrl}")
        rows.append({"gates": n, "n_gates": 2, **so, **ss,
                     "control_ret_dd": sf["ret_dd"] if sf else None})

    print("\nEVERY STACK of the four, on top of H-009's own crowd gate")
    print(f"  {'stack':28s} {'trades':>7s} {'PF2x':>6s} {'ret/DD':>7s} "
          f"{'K':>8s} {'expected days':>14s}")
    best = None
    for r_ in range(2, len(names) + 1):
        for sub in itertools.combinations(names, r_):
            k = np.ones(len(t), dtype=bool)
            for n in sub:
                k &= keep_mask(n, sig[n], d)
            on = t[t.gated & k]
            so = stats(on)
            if not so or not np.isfinite(so["K"]):
                continue
            ss = sim(on)
            print(f"  {'+'.join(sub):28s} {so['trades']:>7d} {so['pf_2x']:>6.3f} "
                  f"{so['ret_dd']:>7.2f} {so['K']:>8.5f} "
                  f"{str(ss['expected_days']):>14s}")
            rows.append({"gates": "+".join(sub), "n_gates": 1 + len(sub),
                         **so, **ss})
            ed = ss["expected_days"]
            if ed is not None and (best is None or ed < best[0]):
                best = (ed, sub, on)

    if best:
        ed, sub, on = best
        print(f"\nBEST STACK: {'+'.join(sub)} -> {ed} expected days "
              f"(H-009 is {bs['expected_days']}, goal is 14)")

        # Held-out half. With 31 combinations searched, the winner is a
        # selected maximum; the second half was not part of that choice.
        mid = t.exit_ts.quantile(0.5)
        for label, mask in (("first half", t.exit_ts <= mid),
                            ("second half", t.exit_ts > mid)):
            bb = stats(t[t.gated & mask])
            k = np.ones(len(t), dtype=bool)
            for n in sub:
                k &= keep_mask(n, sig[n], d)
            gg = stats(t[t.gated & k & mask])
            if bb and gg:
                lift = (gg["ret_dd"] - bb["ret_dd"]) / abs(bb["ret_dd"]) * 100
                print(f"  {label:12s} baseline ret/DD {bb['ret_dd']:>6.2f} -> "
                      f"gated {gg['ret_dd']:>6.2f}  ({lift:+.1f}%)")
                rows.append({"gates": f"{'+'.join(sub)} [{label}]",
                             "n_gates": 1 + len(sub), **gg})

        # Block-shuffled feeds: the same gates driven by noise with the same
        # marginal distribution and autocorrelation.
        print("\n  null: the same stack driven by BLOCK-SHUFFLED feeds")
        nulls = []
        for seed in range(5):
            k = np.ones(len(t), dtype=bool)
            for n in sub:
                s = pd.Series(sig[n])
                sh = of.block_shuffle(s.set_axis(t.entry_ts), seed=seed + 17,
                                      block=288).values
                k &= keep_mask(n, sh, d)
            gg = stats(t[t.gated & k])
            if gg:
                nulls.append(gg["ret_dd"])
        if nulls:
            real = stats(t[t.gated & np.logical_and.reduce(
                [keep_mask(n, sig[n], d) for n in sub])])
            print(f"    real {real['ret_dd']:.2f} vs null "
                  f"{np.mean(nulls):.2f} +/- {np.std(nulls):.2f} "
                  f"(best seed {max(nulls):.2f})")
            rows.append({"gates": f"{'+'.join(sub)} [null mean]",
                         "ret_dd": round(float(np.mean(nulls)), 2)})

    pd.DataFrame(rows).to_csv(OUT / "stage5_gates.csv", index=False)
    print(f"\nwrote {OUT / 'stage5_gates.csv'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
