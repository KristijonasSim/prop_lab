"""Engine 2 — one runner from a Strategy to a scored board record.

THE PROBLEM THIS EXISTS TO SOLVE. `strategies/` held **101 hand-written Python
files** across 12 hypotheses — 25 for vwap, 28 for xpos, 19 for ribbon — and
every one of them re-implemented the SAME six steps:

    response test -> grid sweep -> walk-forward -> paired null -> board -> verdict

That is why 26 hypotheses took months, and it is why the project could test a
strategy well but had no way to produce one. `core/strategy.py` gave the kernels
a shared interface; this gives the PIPELINE one.

WHAT A NEW HYPOTHESIS COSTS NOW. Three functions and a manifest:

    features(df)             what the strategy can see. Backward-looking only.
    grid(tf)                 every configuration worth testing.
    run(df, cfg, fee, slip)  the trade logic, returning the (n, 8) array.

Hand those to `Pipeline` with a list of markets and it produces the stitched
walk-forward series, the paired null it has to beat, and the board record —
fingerprinted and gated by `core/verification.py` like everything else.

THE ONE RULE THIS FILE ENFORCES ABOVE ALL OTHERS. **The configuration is chosen
on the TRAIN slice and never on the test slice.** Every number this project ever
had to retract came from selection touching data it was later scored on. It is
the reason the walk-forward exists at all, and it is why `_fold` computes profit
factors on `train` before it so much as looks at `test`.
"""
from __future__ import annotations

import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core.nulls import NULLS, null_seed                        # noqa: E402
from core.strategy import T_ENTRY_I, T_EXIT_I, T_R, conforms   # noqa: E402

#: Defaults carried over from H-002's walk-forward, which is the only test in
#: the project with no hindsight in it. Changing them changes what "blind" means,
#: so they are named here rather than buried in a stage script.
TRAIN_MONTHS = 12
TEST_MONTHS = 3
#: Minimum train trades before a configuration is eligible. BOTH are reported:
#: 100 excludes exactly the low-frequency configurations that H-002's grid found,
#: and 30 keeps them at the cost of noisier selection. Neither is obviously
#: right, so neither is chosen in advance.
FLOORS = (30, 100)
#: Single best train config vs the top ten equally weighted. Taking the single
#: highest train PF is the highest-variance choice available; the top ten is the
#: same information with the selection noise averaged down. If top-ten holds and
#: single-best does not, the edge was in the family and not in the winner.
TOPN = (1, 10)


def pf(r: np.ndarray) -> float:
    w, l = r[r > 0].sum(), -r[r < 0].sum()
    return float(w / l) if l > 0 else (np.inf if w > 0 else np.nan)


@dataclass
class Market:
    """One market x timeframe, with the cost it is charged."""
    sym: str
    tf: str
    df: pd.DataFrame
    fee_bps: float
    slip_bps: float
    #: bars of warm-up to prepend to every fold slice so indicators are hot at
    #: the boundary. Trades entered inside the pad are dropped.
    pad_bars: int = 200

    def __post_init__(self):
        if not self.df.index.is_monotonic_increasing:
            raise ValueError(f"{self.sym} {self.tf}: bars are not sorted")


@dataclass
class FoldResult:
    folds: pd.DataFrame
    trades: pd.DataFrame


class Pipeline:
    """Walk-forward, paired null and board assembly for any `Strategy`.

    `strategy` needs `features(df)`, `grid(tf)` and
    `run(df, cfg, fee_bps, slip_bps, feats=...)`. See `core/strategy.py`.
    """

    def __init__(self, strategy, *, train_months: int = TRAIN_MONTHS,
                 test_months: int = TEST_MONTHS, floors=FLOORS, topn=TOPN,
                 first_test: str | None = None, last_test: str | None = None,
                 null_kind: str = "paired"):
        self.s = strategy
        self.train_months = train_months
        self.test_months = test_months
        self.floors = tuple(floors)
        self.topn = tuple(topn)
        self.first_test = first_test
        self.last_test = last_test
        self.null_kind = null_kind

    # -- helpers ----------------------------------------------------------- #
    def _cache(self) -> dict:
        """Extra kwargs handed to `run` for every config on one slice. A strategy
        that has something expensive and config-independent to reuse declares
        `new_cache()`; everything else gets an empty dict and pays nothing."""
        new = getattr(self.s, "new_cache", None)
        return new() if callable(new) else {}
    def _slice(self, df, feats, lo, hi, pad):
        """(padded frame, padded features, n_pad). The pad is taken from bars
        BEFORE the fold, never after — that is what keeps it honest."""
        idx = df.index
        i_lo = int(idx.searchsorted(lo))
        i_hi = int(idx.searchsorted(hi))
        i_pad = max(0, i_lo - pad)
        sub = df.iloc[i_pad:i_hi]
        if isinstance(feats, tuple):
            sub_f = tuple(f[i_pad:i_hi] for f in feats)
        elif isinstance(feats, dict):
            sub_f = {k: (v[i_pad:i_hi] if hasattr(v, "__len__") else v)
                     for k, v in feats.items()}
        else:
            sub_f = feats
        return sub, sub_f, i_lo - i_pad

    def _trades(self, df, feats, n_pad, cfg, m: Market, cache):
        """Trades entered at or after the pad boundary."""
        tr = self.s.run(df, cfg, m.fee_bps, m.slip_bps, feats=feats, **cache)
        bad = conforms(tr, len(df))
        if bad:
            raise ValueError(f"{m.sym} {m.tf}: kernel broke the contract: {bad}")
        if len(tr) == 0:
            e = np.empty(0)
            return e, e.astype(int), e.astype(int), e
        tr = tr[tr[:, T_ENTRY_I] >= n_pad]
        if len(tr) == 0:
            e = np.empty(0)
            return e, e.astype(int), e.astype(int), e
        # 2x cost on the SAME trades, never a re-run: re-running would move
        # every stop and conflate "costs doubled" with "a different strategy".
        tr2 = self.s.run(df, cfg, m.fee_bps * 2, m.slip_bps * 2, feats=feats, **cache)
        tr2 = tr2[tr2[:, T_ENTRY_I] >= n_pad] if len(tr2) else tr2
        r2 = tr2[:, T_R] if len(tr2) == len(tr) else np.full(len(tr), np.nan)
        return (tr[:, T_R], tr[:, T_EXIT_I].astype(int),
                tr[:, T_ENTRY_I].astype(int), r2)

    # -- the walk-forward -------------------------------------------------- #
    def walk_forward(self, m: Market, shuffled: str | None = None,
                     tag: str = "") -> FoldResult:
        """Quarterly, config re-chosen blind inside each train window.

        `shuffled` runs the identical procedure on a phase-randomised copy. The
        walk-forward is itself a search, so its survivor count needs a null of
        its own — exactly as the grid does.
        """
        df = m.df
        if shuffled:
            df = NULLS[shuffled](df, null_seed(m.sym, m.tf, tag or "wf"))

        cfgs = self.s.grid(m.tf)
        feats = self.s.features(df)
        pad = m.pad_bars

        lo0 = df.index[0] + pd.DateOffset(months=self.train_months)
        first = pd.Timestamp(self.first_test, tz="UTC") if self.first_test else lo0
        last = (pd.Timestamp(self.last_test, tz="UTC") if self.last_test
                else df.index[-1])
        starts = pd.date_range(max(first, lo0), last,
                               freq=f"{self.test_months}MS", tz="UTC")

        fold_rows, trade_rows = [], []
        for t0 in starts:
            tr_lo = t0 - pd.DateOffset(months=self.train_months)
            te_hi = t0 + pd.DateOffset(months=self.test_months)
            if te_hi > df.index[-1] + pd.Timedelta(1, unit="D"):
                continue
            train, f_tr, pad_tr = self._slice(df, feats, tr_lo, t0, pad)
            test, f_te, pad_te = self._slice(df, feats, t0, te_hi, pad)
            if len(train) < 1000 or len(test) - pad_te < 200:
                continue

            # ---- SELECTION. Train slice only. Nothing below reads `test`. ----
            # A per-slice cache the strategy may reuse across configurations.
            # vwap's anchored VWAP is shared by every config on the same bars and
            # rebuilding it 12,960 times would dominate the runtime.
            cache_tr = self._cache()
            pfs = np.full(len(cfgs), np.nan)
            cnts = np.zeros(len(cfgs), dtype=int)
            for ci, cfg in enumerate(cfgs):
                r, _, _, _ = self._trades(train, f_tr, pad_tr, cfg, m, cache_tr)
                cnts[ci] = len(r)
                if len(r):
                    pfs[ci] = pf(r)

            span = (test.index[-1] - test.index[pad_te]).total_seconds() / 86400.0
            cache_te = self._cache()
            seen: dict[int, tuple] = {}
            for floor in self.floors:
                elig = np.flatnonzero((cnts >= floor) & np.isfinite(pfs))
                if elig.size == 0:
                    continue
                order = elig[np.argsort(-pfs[elig])]
                for n in self.topn:
                    pickd = order[:n]
                    if pickd.size == 0:
                        continue
                    rs, ex, en, rs2 = [], [], [], []
                    for ci in pickd:
                        if ci not in seen:
                            seen[ci] = self._trades(test, f_te, pad_te,
                                                    cfgs[ci], m, cache_te)
                        r1, e1, n1, r2 = seen[ci]
                        # equal weight, so a book of N is comparable to one config
                        rs.append(r1 / n); ex.append(e1); en.append(n1)
                        rs2.append(r2 / n)
                    r_all = np.concatenate(rs) if rs else np.empty(0)
                    e_all = np.concatenate(ex) if ex else np.empty(0, dtype=int)
                    n_all = np.concatenate(en) if en else np.empty(0, dtype=int)
                    r2_all = np.concatenate(rs2) if rs2 else np.empty(0)
                    o = np.argsort(e_all, kind="stable")
                    r_all, e_all, n_all, r2_all = (r_all[o], e_all[o],
                                                   n_all[o], r2_all[o])

                    fold_rows.append({
                        "sym": m.sym, "tf": m.tf, "quarter": str(t0.date()),
                        "floor": floor, "topn": n,
                        "train_pf": round(float(pfs[pickd[0]]), 3),
                        "train_trades": int(cnts[pickd[0]]),
                        "n_eligible": int(elig.size),
                        "test_trades": int(len(r_all)),
                        "test_pf": round(pf(r_all), 3) if len(r_all) else np.nan,
                        "test_pf_2x": (round(pf(r2_all), 3)
                                       if len(r2_all) and np.isfinite(r2_all).all()
                                       else np.nan),
                        "test_total_r": round(float(r_all.sum()), 3),
                        "test_tpd": round(len(r_all) / max(span, 1e-9), 3),
                        # the winning config, so a fold row is reproducible on
                        # its own. Never overwrite a column the row already has.
                        **{k: v for k, v in cfgs[pickd[0]].items()
                           if k not in ("sym", "tf", "quarter", "floor", "topn")},
                    })
                    if len(r_all):
                        trade_rows.append(pd.DataFrame({
                            "sym": m.sym, "tf": m.tf, "quarter": str(t0.date()),
                            "floor": floor, "topn": n,
                            "entry_ts": test.index[n_all],
                            "exit_ts": test.index[e_all],
                            "r": r_all, "r_2x": r2_all}))

        return FoldResult(
            folds=pd.DataFrame(fold_rows),
            trades=(pd.concat(trade_rows, ignore_index=True)
                    if trade_rows else pd.DataFrame()))

    # -- the whole thing --------------------------------------------------- #
    def run(self, markets: list[Market], *, null_seeds: int = 1,
            progress: Callable[[str], None] = print) -> dict:
        """Every market, real and null. Returns the stitched frames.

        The null is not optional and not an afterthought. A survivor that has
        not been read against the same search on phase-randomised data is not a
        result, it is a draw from a search.
        """
        real, nulls = [], []
        for m in markets:
            progress(f"  {m.sym} {m.tf}: walk-forward on {len(m.df):,} bars")
            real.append(self.walk_forward(m))
            for s in range(null_seeds):
                progress(f"  {m.sym} {m.tf}: null seed {s}")
                nulls.append(self.walk_forward(m, shuffled=self.null_kind,
                                               tag=f"wf{s}"))

        def cat(parts, attr):
            fs = [getattr(p, attr) for p in parts if len(getattr(p, attr))]
            return pd.concat(fs, ignore_index=True) if fs else pd.DataFrame()

        return {
            "folds": cat(real, "folds"), "trades": cat(real, "trades"),
            "null_folds": cat(nulls, "folds"), "null_trades": cat(nulls, "trades"),
        }


def gate_counts(folds: pd.DataFrame, gate: float = 1.20) -> tuple[int, int]:
    """How many cells clear the gate at 2x cost, and out of how many.

    Reported as a pair because the count alone means nothing — the whole point
    is to compare it with the null's count over the same number of cells.
    """
    if not len(folds):
        return 0, 0
    cells = folds.groupby(["sym", "tf", "floor", "topn"]).test_pf_2x.median()
    return int((cells >= gate).sum()), int(len(cells))
