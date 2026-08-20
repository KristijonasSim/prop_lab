"""Hand-verified engine arithmetic. These assert exact numbers, not vibes."""
from __future__ import annotations

import pandas as pd
import pytest

from proplab.config import BacktestConfig, CostModel, PropFirmRules
from proplab.core import engine
from proplab.data.loader import Dataset, check_integrity
from proplab.data.synthetic import from_closes
from proplab.data.timeframes import resample
from proplab.strategy.base import Strategy

NO_COST = CostModel(taker_fee_bps=0, maker_fee_bps=0, slippage_bps=0,
                    stop_slippage_bps=0, apply_funding=False)


def ds(df, tf="1h", higher=()):
    return Dataset("TEST", tf, df, {h: resample(df, h) for h in higher},
                   check_integrity(df, tf))


def cfg(**kw):
    base = dict(symbol="TEST", primary_timeframe="1h", costs=NO_COST,
                rules=PropFirmRules(starting_balance=100_000.0))
    base.update(kw)
    return BacktestConfig(**base)


class EnterOnBar(Strategy):
    """Enters long once, on the close of bar `at`."""
    name = "_t_enter"
    mechanism = "test"
    hypothesis = "test"
    params = {"at": 1, "stop": None, "target": None, "risk_pct": None,
              "notional_pct": 0.5, "max_bars": None, "short": False}

    def on_bar(self, ctx):
        if ctx.i != ctx.params["at"] or ctx.position is not None:
            return
        p = ctx.params
        fn = ctx.sell if p["short"] else ctx.buy
        fn(stop=p["stop"], target=p["target"], risk_pct=p["risk_pct"],
           notional_pct=p["notional_pct"], max_bars=p["max_bars"], tag="t")


def test_entry_fills_at_next_bar_open_not_signal_close():
    # closes: signal fires on bar 1 (close=110); bar 2 opens at 110.
    df = from_closes([100, 110, 120, 130])
    r = engine.run(EnterOnBar(at=1, notional_pct=1.0), ds(df), cfg())
    assert len(r.trades) == 1
    t = r.trades[0]
    assert t.entry_price == pytest.approx(df["open"].iloc[2])
    assert t.entry_time == df.index[2]


def test_no_same_bar_close_entry():
    """A strategy cannot enter at the close it made the decision on.

    Uses a gapped next bar so the signal close (110) and the fill open (130)
    are distinguishable - otherwise the assert would pass trivially.
    """
    df = from_closes([100, 110, 120])
    df.loc[df.index[2], ["open", "high", "low", "close"]] = [130.0, 135.0, 129.0, 132.0]
    r = engine.run(EnterOnBar(at=1, notional_pct=1.0), ds(df), cfg())
    t = r.trades[0]
    assert t.entry_price == pytest.approx(130.0)   # next bar OPEN
    assert t.entry_price != pytest.approx(110.0)   # not the signal close


def test_exact_pnl_no_costs():
    # enter at open of bar 2 = 110, forced flat at final close 130
    df = from_closes([100, 110, 120, 130])
    r = engine.run(EnterOnBar(at=1, notional_pct=1.0), ds(df), cfg())
    t = r.trades[0]
    qty = 100_000 / 110
    assert t.qty == pytest.approx(qty)
    assert t.net_pnl == pytest.approx((130 - 110) * qty)
    assert r.equity.iloc[-1] == pytest.approx(100_000 + (130 - 110) * qty)


def test_risk_sizing_loses_exactly_risk_pct_at_stop():
    df = from_closes([100, 100, 100, 90, 90])   # stop at 95 hit on bar 3
    r = engine.run(EnterOnBar(at=1, stop=95.0, risk_pct=0.01, notional_pct=None),
                   ds(df), cfg())
    t = r.trades[0]
    assert t.exit_reason == "stop"
    # gapped through the stop (bar 3 opens at 100 -> low 90): fills at low? no:
    # bar3 open=100 which is above the stop, so fill is at the stop price 95.
    assert t.exit_price == pytest.approx(95.0)
    assert t.net_pnl == pytest.approx(-1000.0)          # exactly 1% of 100k
    assert t.r_multiple == pytest.approx(-1.0)


def test_gap_through_stop_fills_at_open_worse_than_stop():
    df = from_closes([100, 100, 100, 80, 80])   # bar 3 opens at 100? build a gap
    df.loc[df.index[3], ["open", "high"]] = [90.0, 90.0]   # opens below the stop
    r = engine.run(EnterOnBar(at=1, stop=95.0, risk_pct=0.01, notional_pct=None),
                   ds(df), cfg())
    t = r.trades[0]
    assert t.exit_price == pytest.approx(90.0)   # the gap, not the 95 stop
    assert t.net_pnl < -1000.0                   # worse than the intended 1%


def test_stop_wins_when_one_bar_contains_both_stop_and_target():
    df = from_closes([100, 100, 100, 100])
    i = df.index[2]
    df.loc[i, ["open", "high", "low", "close"]] = [100.0, 120.0, 90.0, 100.0]
    r = engine.run(EnterOnBar(at=0, stop=95.0, target=110.0, risk_pct=0.01,
                              notional_pct=None), ds(df), cfg())
    assert r.trades[0].exit_reason == "stop"


def test_costs_make_a_flat_market_lose_money():
    df = from_closes([100] * 20)
    costed = BacktestConfig(symbol="TEST", primary_timeframe="1h",
                            costs=CostModel(apply_funding=False))
    r = engine.run(EnterOnBar(at=1, notional_pct=1.0), ds(df), costed)
    assert r.equity.iloc[-1] < 100_000


def test_leverage_cap_binds():
    df = from_closes([100, 100, 100, 100])
    r = engine.run(EnterOnBar(at=1, notional_pct=10.0), ds(df),
                   cfg(max_leverage=2.0))
    t = r.trades[0]
    assert t.qty * t.entry_price == pytest.approx(200_000)


def test_short_pnl_sign():
    df = from_closes([100, 100, 90, 90])
    r = engine.run(EnterOnBar(at=0, notional_pct=1.0, short=True), ds(df), cfg())
    assert r.trades[0].net_pnl > 0


def test_time_stop_closes_position():
    df = from_closes([100] * 10)
    r = engine.run(EnterOnBar(at=0, notional_pct=0.5, max_bars=3), ds(df), cfg())
    t = r.trades[0]
    assert t.exit_reason == "time_stop" and t.bars_held == 3


def test_unsized_entry_is_rejected():
    class Bad(EnterOnBar):
        name = "_t_bad"
    with pytest.raises(ValueError, match="risk_pct"):
        engine.run(Bad(at=0, notional_pct=None), ds(from_closes([100] * 5)), cfg())


def test_stop_on_wrong_side_is_refused():
    df = from_closes([100] * 5)
    r = engine.run(EnterOnBar(at=0, stop=105.0, risk_pct=0.01, notional_pct=None),
                   ds(df), cfg())
    assert r.trades == []


def test_funding_charged_only_at_settlement_hours():
    idx = pd.date_range("2024-01-01", periods=24, freq="h", tz="UTC")
    df = pd.DataFrame({"open": 100.0, "high": 100.0, "low": 100.0, "close": 100.0,
                       "volume": 1.0}, index=idx)
    c = BacktestConfig(symbol="TEST", primary_timeframe="1h",
                       costs=CostModel(taker_fee_bps=0, slippage_bps=0,
                                       stop_slippage_bps=0, funding_bps_per_8h=10,
                                       apply_funding=True))
    r = engine.run(EnterOnBar(at=0, notional_pct=1.0), ds(df), c)
    t = r.trades[0]
    # entered at 01:00, held to 23:00 -> settlements at 08:00 and 16:00 only
    assert t.funding == pytest.approx(2 * 0.001 * t.qty * 100)


def test_profit_concentration_is_reported():
    """One huge winner is the normal shape of a trend result. The metrics must
    say so out loud, because it means the effective sample size is ~1."""
    from proplab.core import metrics

    df = from_closes([100, 100, 100, 100, 100, 100])
    r = engine.run(EnterOnBar(at=0, notional_pct=1.0), ds(df), cfg())
    m = metrics.compute(r, "1h", 100_000)
    assert "best_trade_pct_of_profit" in m
    assert "net_profit_excluding_best" in m


def test_trades_carry_the_risk_they_were_sized_to():
    df = from_closes([100, 100, 100, 90, 90])
    r = engine.run(EnterOnBar(at=1, stop=95.0, risk_pct=0.01, notional_pct=None),
                   ds(df), cfg())
    t = r.trades[0]
    assert t.initial_risk == pytest.approx(1000.0)   # 1% of 100k
