"""H-030 screen — CFTC positioning as a gate on the traded H-027 rule.

Pre-registered in `notes.md` before this was run: seven gates plus one control,
each scored against the ungated rule, against 50 block-shuffled copies of
itself, and against the baseline's noise band. A gate only REMOVES trades from
the rule's own blind walk-forward; nothing else about the rule moves.

Run: .venv/bin/python strategies/goldfeed/baseline.py   (once, ~2 min)
     .venv/bin/python strategies/goldfeed/gates.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from core.markets import load as load_bars                         # noqa: E402
from core.noiseband import band, overlap                           # noqa: E402
from core.prop_rules import THUNDERBOLT                            # noqa: E402
from core.riskladder import run_accounts                           # noqa: E402
from strategies.goldfeed import cot                                # noqa: E402
from strategies.liqflush.stage1_drawdown import accounts           # noqa: E402
from strategies.vwapbreak.strategy import STRATEGY                 # noqa: E402

TRADES = ROOT / "backtests" / "goldfeed" / "baseline_trades.parquet"
OUT = ROOT / "backtests" / "goldfeed" / "gates.json"
RISK = 0.02
SEEDS = 50


def with_direction(tr: pd.DataFrame) -> pd.DataFrame:
    """The kernel fills at bar i+1's open on bar i's z, so the side is the sign
    of z one bar before `entry_ts`. Checked: every trade's |z| there is at least
    0.5, the smallest threshold in the grid."""
    df = load_bars("XAUUSD", "1h")
    z = pd.Series(np.asarray(STRATEGY.features(df)["z"], float), index=df.index)
    zz = z.reindex(pd.DatetimeIndex(tr.entry_ts) - pd.Timedelta(hours=1)).values
    assert np.isfinite(zz).all() and (np.abs(zz) >= 0.5 - 1e-9).all()
    return tr.assign(d=np.sign(zz).astype(int))


# name -> (feature, rule(value, direction) -> keep)
GATES = {
    "G1 crowd-fade":  ("mm_pct", lambda v, d: ~(((d > 0) & (v >= 0.8)) | ((d < 0) & (v <= 0.2)))),
    "G2 crowd-follow": ("mm_pct", lambda v, d: ~(((d > 0) & (v <= 0.2)) | ((d < 0) & (v >= 0.8)))),
    "G3 flow-1w":     ("mm_d1", lambda v, d: np.sign(v) == d),
    "G4 against-1w":  ("mm_d1", lambda v, d: np.sign(v) == -d),
    "G5 flow-4w":     ("mm_d4", lambda v, d: np.sign(v) == d),
    "G6 against-4w":  ("mm_d4", lambda v, d: np.sign(v) == -d),
    "G7 OI rising":   ("oi_d4", lambda v, d: v > 0),
    "G7' OI falling": ("oi_d4", lambda v, d: v < 0),
}


def state(col: str, v: np.ndarray) -> np.ndarray:
    """What the gate reads off the weekly series, for the block length."""
    if col == "mm_pct":
        return np.where(v >= 0.8, 2, np.where(v <= 0.2, 0, 1))
    return np.sign(v)


def median_run(s: np.ndarray) -> int:
    change = np.flatnonzero(np.diff(s)) + 1
    runs = np.diff(np.r_[0, change, len(s)])
    return int(max(2, np.median(runs))) if len(runs) else 2


def shuffled(feat: pd.DataFrame, col: str, span, seed: int) -> pd.DataFrame:
    """The weekly values inside the trading span, cut into blocks at the gate
    state's own median run length and reordered. Duty cycle and persistence
    survive; alignment with price does not."""
    f = feat.copy()
    inside = (f.known_at >= span[0] - pd.Timedelta(days=14)) & (f.known_at <= span[1])
    v = f.loc[inside, col].values
    b = median_run(state(col, v))
    nb = int(np.ceil(len(v) / b))
    blocks = np.concatenate([v, v[: nb * b - len(v)]]).reshape(nb, b)
    np.random.default_rng(seed).shuffle(blocks, axis=0)
    f.loc[inside, col] = blocks.reshape(-1)[: len(v)]
    return f


def score(tr: pd.DataFrame, keep: np.ndarray, days_idx: pd.DatetimeIndex,
          full: bool = True) -> dict:
    sub = tr[keep]
    daily = (pd.Series(sub.r.values, index=pd.DatetimeIndex(sub.exit_ts))
             .resample("1D").sum().reindex(days_idx, fill_value=0.0))
    a = accounts(daily.values, RISK, False)
    out = {"trades": int(len(sub)), "days": a["days"], "pass_pct": a["pass_pct"],
           "blown_pct": a["blown_pct"]}
    if not full:
        return out
    r, r2 = sub.r.values, sub.r_2x.values
    eq = np.concatenate(([0.0], np.cumsum(r)))
    dd = float((eq - np.maximum.accumulate(eq)).min())
    rpd = float(r.sum()) / len(days_idx)
    lo = -r2[r2 < 0].sum()
    out.update({
        "kept_pct": round(len(sub) / len(tr) * 100, 1),
        "trades_per_day": round(len(sub) / len(days_idx), 2),
        "pf_2x": round(float(r2[r2 > 0].sum() / lo), 3) if lo > 0 else None,
        "win_pct": round(float((r > 0).mean()) * 100, 1),
        "avg_r": round(float(r.mean()), 3),
        "r_per_day": round(rpd, 4),
        "max_dd_r": round(dd, 2),
        "days_proxy": round(abs(dd) / rpd, 1) if rpd > 0 else None,
        "sized": accounts(daily.values, RISK, True),
        "band": band(daily, RISK, rules=THUNDERBOLT),
        "longs": int((sub.d > 0).sum()), "shorts": int((sub.d < 0).sum()),
    })
    return out


def main() -> int:
    tr = with_direction(pd.read_parquet(TRADES)).sort_values("entry_ts").reset_index(drop=True)
    feat = cot.load()
    ts = pd.DatetimeIndex(tr.entry_ts)
    span = (ts.min(), pd.DatetimeIndex(tr.exit_ts).max())
    days_idx = pd.date_range(span[0].normalize(), span[1].normalize(), freq="1D", tz="UTC")
    d = tr.d.values

    base = score(tr, np.ones(len(tr), bool), days_idx)
    # this simulator must be the board's: pin it on the baseline
    ref = run_accounts(pd.Series(tr.r.values, index=pd.DatetimeIndex(tr.exit_ts))
                       .resample("1D").sum().reindex(days_idx, fill_value=0.0),
                       RISK, THUNDERBOLT)
    assert abs(base["pass_pct"] - ref["pass_rate"] * 100) < 0.05, (base, ref)
    print(f"{len(tr)} OOS trades {span[0].date()} -> {span[1].date()}  "
          f"({(d > 0).sum()} long / {(d < 0).sum()} short)")
    print(f"baseline: days {base['days']} band {base['band']['days_lo']}-"
          f"{base['band']['days_hi']}  pass {base['pass_pct']}%  PF@2x {base['pf_2x']}  "
          f"tpd {base['trades_per_day']}  sized {base['sized']['days']}\n")

    res = {"baseline": base, "span": [str(span[0]), str(span[1])], "gates": {}}
    print(f"{'gate':16}{'kept%':>6}{'tpd':>6}{'PF@2x':>7}{'R/day':>8}{'DD R':>7}"
          f"{'days':>7}{'band':>13}{'null p10':>9}{'null med':>9}{'sized':>7}  verdict")
    for name, (col, rule) in GATES.items():
        v = cot.asof(feat, ts, col)
        g = score(tr, np.asarray(rule(v, d)) & np.isfinite(v), days_idx)
        nulls = []
        for s in range(SEEDS):
            vs = cot.asof(shuffled(feat, col, span, 7000 + s), ts, col)
            n = score(tr, np.asarray(rule(vs, d)) & np.isfinite(vs), days_idx, full=False)
            nulls.append(n["days"] if n["days"] is not None else np.inf)
        p10, med = float(np.percentile(nulls, 10)), float(np.median(nulls))
        c1 = g["days"] is not None and g["days"] < base["days"]
        c2 = g["days"] is not None and g["days"] < p10
        c3 = not overlap(g["band"], base["band"])
        g.update({"null_days_p10": round(p10, 1), "null_days_med": round(med, 1),
                  "c1_beats_base": c1, "c2_beats_null": c2, "c3_band_clear": c3,
                  "survives": bool(c1 and c2 and c3)})
        res["gates"][name] = g
        b = g["band"] or {}
        print(f"{name:16}{g['kept_pct']:6.1f}{g['trades_per_day']:6.2f}{g['pf_2x'] or 0:7.3f}"
              f"{g['r_per_day']:8.4f}{g['max_dd_r']:7.1f}{g['days'] or float('nan'):7.1f}"
              f"{str(b.get('days_lo')) + '-' + str(b.get('days_hi')):>13}{p10:9.1f}{med:9.1f}"
              f"{g['sized']['days'] or float('nan'):7.1f}  "
              f"{'SURVIVES' if g['survives'] else 'fails ' + ''.join('123'[i] for i, c in enumerate((c1, c2, c3)) if not c)}")
    res["alive"] = any(g["survives"] for g in res["gates"].values())
    OUT.write_text(json.dumps(res, indent=1, default=str))
    print(f"\nALIVE: {res['alive']}  -> {OUT.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
