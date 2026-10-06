"""The grammar terms of 2026-10-06 (`factory/terms.py`) cannot see ahead.

Same check every script port carries: the whole-series value at bar t equals
the per-bar reader run on the guarded history 0..t, and truncating the data
after t does not change the value at t.
"""
import numpy as np
import pandas as pd
import pytest

from factory import build, guard, spec
from factory.terms import MULT, TERMS


def _frame(n=400, seed=3):
    rng = np.random.default_rng(seed)
    c = 100 + np.cumsum(rng.normal(0, 0.5, n))
    o = c + rng.normal(0, 0.2, n)
    h = np.maximum(o, c) + rng.random(n)
    l = np.minimum(o, c) - rng.random(n)
    return pd.DataFrame({"open": o, "high": h, "low": l, "close": c,
                         "volume": rng.integers(1, 100, n).astype(float),
                         "hour": (np.arange(n) % 24).astype(float)})


def _args(kind):
    n = 7 if kind in ("range_high", "range_low") else 14
    m = 4.0 if kind in ("range_high", "range_low") else (2.5 if kind in MULT else 0.0)
    return n, m


@pytest.mark.parametrize("kind", sorted(TERMS))
def test_no_lookahead(kind):
    f = _frame()
    cols = guard.columns(f)
    n, m = _args(kind)
    full = spec.SERIES[kind](cols, n, m)
    for t in (60, 150, 299, 399):
        short = guard.columns(f.iloc[:t + 1])
        part = spec.SERIES[kind](short, n, m)
        a, b = full[t], part[t]
        assert (np.isnan(a) and np.isnan(b)) or a == pytest.approx(b), (kind, t)
        w = guard.Window(cols, t)
        r = spec.Term(kind, n, m).at(w)
        assert (np.isnan(a) and np.isnan(r)) or a == pytest.approx(r), (kind, t)


@pytest.mark.parametrize("kind", sorted(TERMS))
def test_produces_values(kind):
    n, m = _args(kind)
    v = spec.SERIES[kind](guard.columns(_frame()), n, m)
    assert np.isfinite(v[200:]).any(), kind


def test_supertrend_flips_and_runs_in_a_strategy():
    f = _frame(1500)
    s = spec.Strategy("st", "long", (spec.Condition(
        spec.Term("supertrend", 10, 3.0), "cross_above", spec.Term("const", 0, 0.0)),))
    fire, _ = build.series(s, f)
    assert 5 < fire.sum() < 200
    assert "supertrend10x3" in s.label()


def test_translator_accepts_new_terms():
    from factory.sources import agent
    s = agent.validate({"side": "long", "entry": [
        {"left": {"kind": "price"}, "op": "cross_above",
         "right": {"kind": "bb_upper", "length": 20, "value": 2}},
        {"left": {"kind": "price"}, "op": "above",
         "right": {"kind": "range_high", "length": 0, "value": 7}}],
        "note": "breakout of the upper band above the Asia range high"})
    assert "bb_upper20x2" in s.label() and "range_high0x7" in s.label()
