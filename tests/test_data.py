"""Timeframe alignment - the usual source of silent multi-timeframe lookahead."""
from __future__ import annotations

import pandas as pd
import pytest

from proplab.core.context import Context
from proplab.data.loader import check_integrity
from proplab.data.synthetic import random_walk
from proplab.data.timeframes import is_multiple_of, parse_timeframe, resample


def test_resample_preserves_ohlc():
    df = random_walk(400, "15m", seed=5)
    h1 = resample(df, "1h")
    first = df.iloc[:4]
    assert h1["open"].iloc[0] == pytest.approx(first["open"].iloc[0])
    assert h1["close"].iloc[0] == pytest.approx(first["close"].iloc[-1])
    assert h1["high"].iloc[0] == pytest.approx(first["high"].max())
    assert h1["low"].iloc[0] == pytest.approx(first["low"].min())
    assert h1["volume"].iloc[0] == pytest.approx(first["volume"].sum())


def test_partial_trailing_bar_is_dropped():
    """A half-formed 4h bar would leak the future of an unfinished period."""
    df = random_walk(10, "1h", seed=1)          # 10h = 2 full 4h bars + 2h
    h4 = resample(df, "4h")
    assert len(h4) == 2
    assert h4.index[-1] + parse_timeframe("4h") <= df.index[-1] + parse_timeframe("1h")


def test_higher_timeframe_visible_only_after_it_closes():
    p = random_walk(400, "15m", seed=2)
    ctx = Context(p, {"4h": resample(p, "4h")}, "15m", {})
    v = ctx.tf("4h")
    # bar 14 closes at 03:45 -> the 00:00-04:00 bar is NOT closed yet
    ctx._advance(14, 0, 0, None)
    assert v.n_closed == 0
    # bar 15 closes at exactly 04:00 -> the first 4h bar is now known
    ctx._advance(15, 0, 0, None)
    assert v.n_closed == 1
    assert v.bar(0).time == p.index[0]


def test_higher_timeframe_values_match_the_source_bars():
    p = random_walk(400, "15m", seed=2)
    h4 = resample(p, "4h")
    ctx = Context(p, {"4h": h4}, "15m", {})
    ctx._advance(63, 0, 0, None)                 # closes at 16:00 -> 4 bars closed
    v = ctx.tf("4h")
    assert v.n_closed == 4
    assert v.last("close") == pytest.approx(h4["close"].iloc[3])
    assert v.last("close", offset=1) == pytest.approx(h4["close"].iloc[2])


def test_context_series_never_includes_the_future():
    p = random_walk(100, "15m", seed=4)
    ctx = Context(p, {}, "15m", {})
    for i in (0, 5, 50, 99):
        ctx._advance(i, 0, 0, None)
        s = ctx.series("close")
        assert len(s) == i + 1
        assert s[-1] == pytest.approx(p["close"].iloc[i])


def test_context_frame_is_a_copy():
    p = random_walk(50, "15m", seed=4)
    ctx = Context(p, {}, "15m", {})
    ctx._advance(20, 0, 0, None)
    f = ctx.frame(10)
    f.iloc[0, 0] = -999
    assert p["open"].iloc[11] != -999


def test_undeclared_timeframe_raises():
    p = random_walk(50, "15m", seed=4)
    ctx = Context(p, {}, "15m", {})
    ctx._advance(10, 0, 0, None)
    with pytest.raises(KeyError, match="not loaded"):
        ctx.tf("4h")


def test_non_multiple_timeframes_rejected():
    assert is_multiple_of("4h", "15m")
    assert is_multiple_of("1h", "15m")
    assert not is_multiple_of("1h", "45m")


def test_integrity_flags_missing_bars():
    df = random_walk(200, "15m", seed=6)
    holed = pd.concat([df.iloc[:50], df.iloc[60:]])
    rep = check_integrity(holed, "15m")
    assert rep["missing_bars"] == 10


def test_integrity_flags_bad_ohlc():
    df = random_walk(50, "15m", seed=6)
    df.iloc[10, df.columns.get_loc("high")] = df["low"].iloc[10] - 1
    assert check_integrity(df, "15m")["bad_ohlc_bars"] >= 1
