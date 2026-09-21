"""Steps 1 and 2. The look-ahead guard and the positive control are the point.

Everything else in the workflow is a statistic and no statistic catches a leak,
so `test_the_future_is_unreachable` is the test that protects every number the
factory will ever produce.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from factory.build import run
from factory.guard import LookAheadError, Window
from factory.spec import Condition, Strategy, Term
from factory.sources import invent, tradingview


@pytest.fixture
def frame():
    n = 600
    rng = np.random.default_rng(0)
    close = 100 * np.exp(np.cumsum(rng.standard_normal(n) * 0.002))
    return pd.DataFrame({"open": close, "high": close * 1.001,
                         "low": close * 0.999, "close": close,
                         "volume": np.ones(n)})


# --------------------------------------------------------------- the guard
def test_the_future_is_unreachable(frame):
    w = Window(frame, t=100)
    assert w.close[-1] == pytest.approx(frame["close"].iloc[100])
    for bad in (lambda: w.close[101],      # tomorrow, by absolute index
                lambda: w.close[0],        # any positive index
                lambda: w.close[5:200],    # a positive slice
                lambda: w.close[-5:200]):  # a slice that reaches forward
        with pytest.raises(LookAheadError):
            bad()


def test_a_window_cannot_hand_back_the_whole_frame(frame):
    w = Window(frame, t=10)
    assert len(w) == 11
    assert not hasattr(w, "full")
    assert not hasattr(w, "frame")


def test_negative_history_beyond_the_start_is_refused(frame):
    w = Window(frame, t=5)
    with pytest.raises(LookAheadError):
        w.close[-99]


# ----------------------------------------------------------------- the spec
def test_a_strategy_that_never_trades_is_refused():
    with pytest.raises(ValueError):
        Strategy(name="empty", entry=())


def test_unknown_indicators_and_comparisons_are_refused():
    with pytest.raises(ValueError):
        Strategy(name="x", entry=(Condition(Term("oracle", 5), "above", Term("price")),))
    with pytest.raises(ValueError):
        Strategy(name="x", entry=(Condition(Term("price"), "equals", Term("price")),))


def test_the_same_idea_in_different_clothes_has_one_fingerprint():
    a = Strategy(name="Golden Cross Pro v3", source="tradingview",
                 entry=(Condition(Term("sma", 50), "cross_above", Term("sma", 200)),))
    b = Strategy(name="MA Signals [FREE]", source="invent", note="different note",
                 entry=(Condition(Term("sma", 50), "cross_above", Term("sma", 200)),))
    c = Strategy(name="c", entry=(Condition(Term("sma", 20), "cross_above",
                                            Term("sma", 200)),))
    assert a.fingerprint() == b.fingerprint()
    assert a.fingerprint() != c.fingerprint()


# ------------------------------------------------- step 2 finds a real edge
def test_positive_control_a_planted_edge_is_found():
    """The test this repo did not have. A run that can only ever say no is
    indistinguishable from a broken run, so plant one and check it is found."""
    # A mean-reverting market. Price is pulled back towards a slow average, so
    # buying a dip genuinely works and an RSI rule genuinely ought to find it.
    n, rng = 4000, np.random.default_rng(1)
    close = np.empty(n); close[0] = 100.0
    anchor = 100.0
    for t in range(1, n):
        anchor = 0.999 * anchor + 0.001 * close[t-1]
        pull = 0.05 * (anchor - close[t-1]) / anchor
        close[t] = close[t-1] * np.exp(pull + rng.standard_normal() * 0.003)
    f = pd.DataFrame({"open": close, "high": close*1.003, "low": close*0.997,
                      "close": close, "volume": np.ones(n)})
    s = Strategy(name="dip buy", side="long", max_hold=24,
                 entry=(Condition(Term("rsi", 14), "below", Term("const", value=35)),))
    trades = run(s, f, cost_bps=1.0)
    assert len(trades) > 30, "the planted edge produced too few trades to judge"
    assert np.mean([t.r for t in trades]) > 0.1


def test_a_strategy_with_no_edge_makes_no_money(frame):
    s = Strategy(name="coin flip", side="long",
                 entry=(Condition(Term("sma", 5), "cross_above", Term("sma", 10)),))
    r = [t.r for t in run(s, frame, cost_bps=20.0)]
    if r:
        assert np.mean(r) < 0.25


# -------------------------------------------------------------- fill rules
def test_a_gapped_stop_fills_at_the_open_not_the_level():
    """A stop is a stop-market order. On a gap, price never walked to it."""
    # Down then up, so sma5 starts BELOW sma20 and genuinely crosses it.
    close = np.concatenate([np.linspace(110, 90, 25),
                            np.linspace(90, 115, 35),
                            np.full(20, 115.0)])
    f = pd.DataFrame({"open": close.copy(), "high": close*1.005,
                      "low": close*0.995, "close": close, "volume": np.ones(len(close))})
    f.loc[55:, ["open", "high", "low", "close"]] = 50.0   # a violent gap down
    s = Strategy(name="x", side="long", stop_atr=1.0, target_atr=99.0, max_hold=50,
                 entry=(Condition(Term("sma", 5), "cross_above", Term("sma", 20)),))
    out = run(s, f, cost_bps=0.0)
    assert out, "no trade was taken, the test proves nothing"
    stopped = [t for t in out if t.reason == "stop"]
    assert stopped and stopped[0].exit_px == pytest.approx(50.0), \
        "a gapped stop must fill at the open"


def test_dead_bars_are_never_traded(frame):
    frame = frame.copy()
    frame.loc[:, "volume"] = 0.0
    s = Strategy(name="x", entry=(Condition(Term("sma", 5), "cross_above",
                                            Term("sma", 20)),))
    assert run(s, frame, cost_bps=0.0) == []


# -------------------------------------------------------------- the sources
def test_the_pine_translator_skips_what_it_cannot_read():
    s, why = tradingview.translate("z = someCustomFn(close)", "Mystery")
    assert s is None and why


def test_the_pine_translator_does_not_guess_the_direction():
    """Reading the side off the comparison called an RSI dip-buy a SHORT."""
    s, _ = tradingview.translate(
        "longSignal = ta.crossunder(ta.rsi(close, 14), 30)", "dip")
    assert s is not None and s.side == "long"
    s2, why = tradingview.translate(
        "sig = ta.crossover(ta.sma(close,10), ta.sma(close,50))", "unlabelled")
    assert s2 is None and "which way" in why


def test_nested_calls_are_split_at_the_top_level_only():
    s, why = tradingview.translate(
        "long1 = ta.crossover(ta.sma(close, 50), ta.sma(close, 200))", "gc")
    assert s is not None, why
    assert s.label() == "long when sma50 cross_above sma200"


def test_the_inventor_never_runs_out_and_never_repeats():
    a = invent.generate(50)
    b = invent.generate(50, skip=50)
    assert len({s.fingerprint() for s in a}) == 50
    assert not ({s.fingerprint() for s in a} & {s.fingerprint() for s in b})


def test_the_inventor_fixes_direction_rather_than_searching_both():
    """Emitting both ways of one condition doubles the search and guarantees
    that one of the pair matches whatever the data says."""
    for s in invent.generate(80):
        if s.entry[0].op == "above" and s.entry[0].right.kind == "highest":
            assert s.side == "long"
        if s.entry[0].op == "below" and s.entry[0].right.kind == "lowest":
            assert s.side == "short"


# ------------------------------------------- bugs found running it for real
def test_a_breakout_excludes_the_current_bar():
    """`close > highest(n)` including this bar can never be true: the high is
    always >= the close. Every breakout rule silently made zero trades."""
    n = 200
    close = np.concatenate([np.full(100, 100.0), np.linspace(100, 130, 100)])
    f = pd.DataFrame({"open": close, "high": close * 1.001, "low": close * 0.999,
                      "close": close, "volume": np.ones(n)})
    s = Strategy(name="breakout", side="long",
                 entry=(Condition(Term("price"), "above", Term("highest", 20)),))
    assert run(s, f, cost_bps=0.0), "a rising market must break its own high"


def test_a_trade_never_outlives_its_hold_window():
    """A dead bar at the end of the window used to skip the time exit, so the
    trade fell through and closed at the END OF THE SERIES - one short scored
    -45R that way."""
    n, hold = 400, 10
    rng = np.random.default_rng(2)
    close = 100 * np.exp(np.cumsum(rng.standard_normal(n) * 0.004))
    vol = np.ones(n)
    vol[60:: 20] = 0.0                       # scattered dead bars, incl. window ends
    f = pd.DataFrame({"open": close, "high": close * 1.004, "low": close * 0.996,
                      "close": close, "volume": vol})
    s = Strategy(name="x", side="short", max_hold=hold, stop_atr=3.0, target_atr=9.0,
                 entry=(Condition(Term("price"), "below", Term("lowest", 5)),))
    out = run(s, f, cost_bps=0.0)
    assert out, "no trades, the test proves nothing"
    assert all(t.exit_bar - t.entry_bar < hold for t in out)
    assert all(abs(t.r) < 12 for t in out), "R exploded - check the exit path"


def test_a_stop_narrower_than_the_cost_is_not_traded():
    """A 0.19-point stop against a 0.74-point round trip made one trade score
    +290.9R and dragged a whole rule's mean to +8.24R."""
    n = 300
    close = np.full(n, 100.0)
    close[:50] = np.linspace(90, 100, 50)
    f = pd.DataFrame({"open": close, "high": close * 1.00001,   # near-zero range
                      "low": close * 0.99999, "close": close, "volume": np.ones(n)})
    s = Strategy(name="x", side="long",
                 entry=(Condition(Term("price"), "above", Term("highest", 10)),))
    assert run(s, f, cost_bps=50.0) == []
