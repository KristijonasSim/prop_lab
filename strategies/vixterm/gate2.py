"""H-043 gate 2 — the Fear Curve, backtested with stops and costs.

Pre-registration: VIXTERM.md. Nothing here selects on the blind half.

Run: .venv/bin/python strategies/vixterm/gate2.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from core.markets import COSTS                                      # noqa: E402
from core.prop_rules import HOUSE, best_day_share                   # noqa: E402
from core.riskladder import run_accounts                            # noqa: E402

DATA = ROOT / "data"
END = pd.Timestamp("2026-08-31", tz="UTC")
BUCKETS, HOLDS, STOPS = (1, 2), (3, 5, 10), (1.5, 3.0)
SPLIT = 0.60
SEEDS = 25
MARKETS = {"XAUUSD": 5, "BTCUSDT": 5, "SPX500": 3, "NAS100": 3, "US30": 3,
           "XAGUSD": 3, "EURUSD": 3, "GBPUSD": 3, "USDJPY": 3}
SOURCE = {"XAUUSD": "XAUUSD10Y_dukascopy_1h.parquet",
          "BTCUSDT": "BTCUSDT_spot_15m.parquet"}


def vix_ratio() -> pd.Series:
    def rd(n):
        d = pd.read_csv(ROOT / "data" / "vix" / f"{n}.csv")
        d["DATE"] = pd.to_datetime(d["DATE"], format="%m/%d/%Y", utc=True)
        return d.set_index("DATE")["CLOSE"].rename(n)
    v, v3 = rd("VIX"), rd("VIX3M")
    r = (v3 / v).dropna().sort_index()
    return r.shift(1).dropna()          # closes 16:15 ET; usable next session


def ohlc(sym: str) -> pd.DataFrame:
    stem = SOURCE.get(sym)
    cands = [stem] if stem else [f"{sym}_dukascopy_1D.parquet",
                                 f"{sym}_dukascopy_1h.parquet"]
    for c in cands:
        p = DATA / c
        if p.exists():
            d = pd.read_parquet(p, columns=["open", "high", "low", "close"]).sort_index()
            g = d.resample("1D").agg({"open": "first", "high": "max",
                                      "low": "min", "close": "last"}).dropna()
            return g
    raise FileNotFoundError(sym)


def atr(df: pd.DataFrame, n: int = 14) -> pd.Series:
    pc = df.close.shift(1)
    tr = pd.concat([df.high - df.low, (df.high - pc).abs(),
                    (df.low - pc).abs()], axis=1).max(axis=1)
    return tr.rolling(n, min_periods=n // 2).mean()


def trades(df: pd.DataFrame, sig: pd.Series, bucket: int, hold: int,
           stop_mult: float) -> pd.DataFrame:
    """Long the stressed bucket. Entry next open, exit at hold or stop touch."""
    j = df.join(sig.rename("sig"), how="inner").dropna(subset=["sig"])
    j["atr"] = atr(j)
    j = j.dropna()
    if len(j) < 120:
        return pd.DataFrame()
    cut = j["sig"].quantile(bucket / 5.0)
    o, h, l = j.open.values, j.high.values, j.low.values
    a, s = j.atr.values, j.sig.values
    idx, out, i = j.index, [], 0
    n = len(j)
    while i < n - hold - 1:
        if s[i] <= cut:
            e = o[i + 1]
            risk = stop_mult * a[i]
            if risk <= 0:
                i += 1
                continue
            stop = e - risk
            exit_px, k = o[min(i + 1 + hold, n - 1)], hold
            for t in range(1, hold + 1):
                if i + 1 + t >= n:
                    break
                if l[i + 1 + t] <= stop:
                    exit_px, k = stop, t      # stop-market: gap fills worse,
                    break                      # but a daily low touch is a fill
            out.append({"entry_ts": idx[i + 1], "exit_ts": idx[min(i + 1 + k, n - 1)],
                        "entry": e, "exit": exit_px, "risk": risk,
                        "r": (exit_px - e) / risk})
            i += 1 + k
        else:
            i += 1
    return pd.DataFrame(out)


def score(tr: pd.DataFrame, sym: str, mult: float) -> dict:
    if not len(tr):
        return {"pf": None, "n": 0}
    c = COSTS[sym]
    bps = 2.0 * (c.taker_fee + c.half_spread) * mult
    cost_r = (tr.entry * bps / 1e4) / tr.risk
    r = tr.r - cost_r
    pos, neg = r[r > 0].sum(), -r[r < 0].sum()
    return {"pf": round(float(pos / neg), 3) if neg > 0 else None,
            "n": int(len(r)), "avg_r": round(float(r.mean()), 4),
            "_r": r.values, "_ts": tr.exit_ts.values}


def main() -> int:
    sig = vix_ratio()
    print("H-043 gate 2. Blind half is the last 40% of each window.\n")
    hdr = (f"{'market':9}{'yrs':>4}{'cell':>14}{'IS n':>6}{'IS PF2x':>9}"
           f"{'OOS n':>7}{'OOS PF1x':>10}{'OOS PF2x':>10}{'OOS PF3x':>10}{'avgR2x':>9}")
    print(hdr); print("-" * len(hdr))
    rows = {}
    for sym, yrs in MARKETS.items():
        try:
            df = ohlc(sym)
        except FileNotFoundError:
            print(f"{sym:9} no cache"); continue
        df = df.loc[END - pd.DateOffset(years=yrs):END]
        cut = int(len(df) * SPLIT)
        is_df, oos_df = df.iloc[:cut], df.iloc[cut:]
        best, bestcell = None, None
        for b in BUCKETS:
            for h in HOLDS:
                for st in STOPS:
                    t = trades(is_df, sig, b, h, st)
                    s = score(t, sym, 2.0)
                    if s["pf"] and s["n"] >= 8 and (best is None or s["pf"] > best["pf"]):
                        best, bestcell = s, (b, h, st)
        if bestcell is None:
            print(f"{sym:9}{yrs:>4}   no cell with >= 8 in-sample trades"); continue
        b, h, st = bestcell
        to = trades(oos_df, sig, b, h, st)
        so = {m: score(to, sym, m) for m in (1.0, 2.0, 3.0)}
        rows[sym] = {"yrs": yrs, "cell": {"bucket": b, "hold": h, "stop_atr": st},
                     "is": {k: v for k, v in best.items() if not k.startswith("_")},
                     "oos": {str(m): {k: v for k, v in so[m].items()
                                      if not k.startswith("_")} for m in so}}
        if so[2.0]["n"]:
            r2 = pd.Series(so[2.0]["_r"], index=pd.DatetimeIndex(so[2.0]["_ts"]))
            yr = r2.groupby(r2.index.year).sum()
            rows[sym]["oos_year_r"] = {int(k): round(float(v), 2) for k, v in yr.items()}
            rows[sym]["same_sign_years"] = bool(len(set(np.sign(yr.values))) == 1)
        print(f"{sym:9}{yrs:>4}{f'q{b} h{h} s{st}':>14}{best['n']:>6}"
              f"{(best['pf'] or 0):>9.3f}{so[2.0]['n']:>7}"
              f"{(so[1.0]['pf'] or 0):>10.3f}{(so[2.0]['pf'] or 0):>10.3f}"
              f"{(so[3.0]['pf'] or 0):>10.3f}{(so[2.0].get('avg_r') or 0):>9.4f}",
              flush=True)

    dest = ROOT / "backtests" / "vixterm"
    dest.mkdir(parents=True, exist_ok=True)
    (dest / "gate2.json").write_text(json.dumps(rows, indent=1, default=str))
    ok = [s for s, v in rows.items()
          if (v["oos"]["2.0"]["pf"] or 0) > 1.0 and v["oos"]["2.0"]["n"] >= 5]
    print(f"\npositive at 2x out of sample: {len(ok)} of {len(rows)}  -> {ok}")
    gold = rows.get("XAUUSD", {}).get("oos", {}).get("2.0", {})
    print(f"gold OOS PF@2x = {gold.get('pf')} on {gold.get('n')} trades "
          f"(condition 1 needs >= 1.20)")
    print(f"\nwrote backtests/vixterm/gate2.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
