"""The 2026-09-24 speed-ups must not move a single number.

Kris: *"should not affect quality of strategy and test quality"*. Two changes,
each pinned against the slow path it replaced:

  * the entry-signal cache in `check._signals` (exit-only repairs reuse it)
  * the 24-cell process fan-out in `check.check_all`
"""
from dataclasses import replace

import numpy as np

from factory import cells, check
from factory.spec import Condition, Strategy, Term

CELLS = [("XAUUSD", "4h"), ("EURUSD", "4h"), ("XAUUSD", "1d"), ("GBPUSD", "1d")]


def _idea():
    return Strategy(name="speed pin", side="long", source="test",
                    entry=(Condition(Term("price"), "cross_above", Term("sma", 20)),))


def _same(a, b):
    assert a.cell == b.cell and a.verdict == b.verdict
    assert a.n_trades == b.n_trades and a.reasons == b.reasons
    for k in a.mean_r:
        assert np.isclose(a.mean_r[k], b.mean_r[k], equal_nan=True)
    for f in ("mean_r_drop_best", "control_p90", "control_median", "pf", "win_pct"):
        assert np.isclose(getattr(a, f), getattr(b, f), equal_nan=True), f


def test_parallel_equals_serial(monkeypatch):
    monkeypatch.setenv("PROP_LAB_WORKERS", "1")
    serial = check.check_all(_idea(), CELLS, control_seeds=3)
    monkeypatch.setenv("PROP_LAB_WORKERS", "4")
    parallel = check.check_all(_idea(), CELLS, control_seeds=3)
    assert len(serial) == len(parallel) == len(CELLS)
    for a, b in zip(serial, parallel):
        _same(a, b)


def test_cached_signal_equals_fresh_signal():
    frame = cells.load("XAUUSD", "4h")
    base = _idea()
    variants = [replace(base, stop_atr=1.5), replace(base, target_atr=6.0),
                replace(base, max_hold=12), base]
    check._SIGNALS.clear()
    warm = [check.check(v, frame, market="XAUUSD", tf="4h", control_seeds=3)
            for v in variants]
    for v, w in zip(variants, warm):
        check._SIGNALS.clear()
        cold = check.check(v, frame, market="XAUUSD", tf="4h", control_seeds=3)
        _same(w, cold)


def test_a_different_entry_is_never_served_from_cache():
    frame = cells.load("XAUUSD", "4h")
    a = _idea()
    b = replace(a, entry=(Condition(Term("price"), "cross_above", Term("sma", 50)),))
    check._SIGNALS.clear()
    ca = check.check(a, frame, market="XAUUSD", tf="4h", control_seeds=2)
    cb = check.check(b, frame, market="XAUUSD", tf="4h", control_seeds=2)
    assert ca.n_trades != cb.n_trades
