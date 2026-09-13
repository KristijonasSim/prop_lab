"""The demo bot's exit path and its reconciliation against the exchange.

Two bugs found 2026-09-11 in `live/bybit_demo.py`, neither yet triggered live:

  * an armed exit was traded TWICE - reduce-only, then again inside the net
    order - so the last leg's exit would have opened an unbooked position the
    other way;
  * exits only ran on a pass that also had a signal, and never on weekends, so a
    touched stop waited for an unrelated bar to fire.

A third, found 2026-09-13, and this one DID happen. Kris closed the six-leg
short by hand from the Bybit UI on 2026-09-12 12:41 UTC at +$136.51. The local
book still listed all six legs, so every subsequent signal was skipped as
"already open for this leg" and the bot could not open another trade. Nothing
would have cleared it: a reduce-only exit against a flat account is rejected,
and a rejected exit leaves the leg in the book, so it would have sat dead until
the 384h horizon on 2026-09-26. Only the weekend hid it - the close landed on a
Saturday and no signal was due until Monday.
"""
from __future__ import annotations

import importlib.util
from argparse import Namespace
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def bot(tmp_path, monkeypatch):
    spec = importlib.util.spec_from_file_location("bybit_demo", ROOT / "live" / "bybit_demo.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    monkeypatch.setattr(m, "STATE", tmp_path / "state.json")
    orders: list[dict] = []
    monkeypatch.setattr(m, "equity", lambda host: 10_000.0)
    # THE MOCKED EXCHANGE HOLDS WHAT THE BOOK SAYS IT HOLDS. This used to be a
    # bare `[]` while the tests wrote a book with a leg in it - a state the bot
    # now treats as a position closed behind its back, because on 2026-09-12
    # that is exactly what happened. `_short_leg` sets both sides together;
    # a test that wants them to disagree says so explicitly.
    m._live = []
    monkeypatch.setattr(m, "positions", lambda host: m._live)
    monkeypatch.setattr(m, "set_backstop", lambda host, level: None)
    monkeypatch.setattr(m, "market", lambda host, side, qty, tag, reduce_only=False:
                        orders.append({"side": side, "qty": qty, "tag": tag,
                                       "reduce_only": reduce_only}) or {"retCode": 0, "result": {}})
    m.orders = orders
    return m


def _bars(last: str, high: float) -> pd.DataFrame:
    idx = pd.date_range(end=pd.Timestamp(last, tz="UTC"), periods=5, freq="1h")
    df = pd.DataFrame({"open": 100.0, "high": 100.5, "low": 99.5, "close": 100.0,
                       "volume": 1.0}, index=idx)
    df.iloc[-1, df.columns.get_loc("high")] = high
    return df


def _short_leg(bot, at: str, stop: float = 101.0, qty: float = 0.5) -> None:
    bot.save_state({"open": {"vwap1": {"at": at, "side": "Sell", "qty": qty, "stop": stop,
                                       "hold_h": 384, "entry_ref": 100.0}},
                    "peak": 10_000.0, "started": at})
    bot._live = [{"size": str(qty), "side": "Sell", "avgPrice": "100.0",
                  "stopLoss": str(stop), "unrealisedPnl": "0"}]


@pytest.mark.parametrize("last", ["2026-09-10 14:00",      # Thursday
                                  "2026-09-12 14:00"])     # Saturday
def test_touched_stop_exits_once_with_no_signal(bot, monkeypatch, last):
    monkeypatch.setattr(bot, "bars", lambda: _bars(last, high=101.5))
    monkeypatch.setattr(bot, "vwap_signals", lambda df, cold=False: [])
    monkeypatch.setattr(bot, "asia_signal", lambda df, cold=False: [])
    _short_leg(bot, at=str(pd.Timestamp(last, tz="UTC") - pd.Timedelta(hours=4)))

    bot.once(Namespace(arm=True, weekends=False))

    assert bot.orders == [{"side": "Buy", "qty": 0.5, "tag": bot.orders[0]["tag"],
                           "reduce_only": True}]
    assert bot.load_state()["open"] == {}


def test_exit_is_not_repeated_in_the_net_order(bot, monkeypatch):
    last = "2026-09-10 14:00"
    monkeypatch.setattr(bot, "bars", lambda: _bars(last, high=101.5))
    # a fresh signal on a different leg, so the net order does fire
    monkeypatch.setattr(bot, "vwap_signals", lambda df, cold=False: [
        {"tag": "vwap2", "signal": "VWAP band break", "side": -1, "z": -2.1,
         "risk_px": 1.0, "stop": 101.0, "ref": 100.0, "risk_pct": 0.002, "max_hold_h": 384}])
    monkeypatch.setattr(bot, "asia_signal", lambda df, cold=False: [])
    _short_leg(bot, at=str(pd.Timestamp(last, tz="UTC") - pd.Timedelta(hours=4)))

    bot.once(Namespace(arm=True, weekends=False))

    exit_, net = bot.orders
    assert exit_["reduce_only"] and exit_["side"] == "Buy" and exit_["qty"] == 0.5
    # the net order opens vwap2 (20 XAU short) and nothing else
    assert not net["reduce_only"] and net["side"] == "Sell" and net["qty"] == pytest.approx(20.0)
    assert set(bot.load_state()["open"]) == {"vwap2"}


# --------------------------------------------------------------------------- #
# reconciliation - the 2026-09-12 hand-close
# --------------------------------------------------------------------------- #
def test_a_book_with_no_position_behind_it_is_dropped(bot, monkeypatch):
    """The live failure: flat exchange, six legs in the book, and it stays that
    way forever. The book is dropped, and nothing is sent - there is nothing to
    reduce."""
    last = "2026-09-10 14:00"
    monkeypatch.setattr(bot, "bars", lambda: _bars(last, high=100.5))
    monkeypatch.setattr(bot, "vwap_signals", lambda df, cold=False: [])
    monkeypatch.setattr(bot, "asia_signal", lambda df, cold=False: [])
    _short_leg(bot, at=str(pd.Timestamp(last, tz="UTC") - pd.Timedelta(hours=4)))
    bot._live = []                       # closed by hand, outside the bot

    bot.once(Namespace(arm=True, weekends=False))

    assert bot.orders == []
    st = bot.load_state()
    assert st["open"] == {}
    # persisted on THIS pass: the early return below it must not lose the repair
    assert "started" not in st


def test_the_pass_that_drops_the_book_is_a_cold_start(bot, monkeypatch):
    """Waking into a move it did not enter is the same problem a first-ever run
    has, so the same guard applies: only a fresh cross is taken."""
    last = "2026-09-10 14:00"
    seen: list[bool] = []
    monkeypatch.setattr(bot, "bars", lambda: _bars(last, high=100.5))
    monkeypatch.setattr(bot, "vwap_signals",
                        lambda df, cold=False: seen.append(cold) or [])
    monkeypatch.setattr(bot, "asia_signal", lambda df, cold=False: [])
    _short_leg(bot, at=str(pd.Timestamp(last, tz="UTC") - pd.Timedelta(hours=4)))
    bot._live = []

    bot.once(Namespace(arm=True, weekends=False))

    assert seen == [True]


def test_a_partial_mismatch_blocks_new_legs_but_still_exits(bot, monkeypatch):
    """A fill in flight or a hand-sized trim is not unambiguous, so it is never
    auto-resolved: no new legs that pass, but a touched stop is still enforced
    because a reduce-only order cannot grow a position."""
    last = "2026-09-10 14:00"
    monkeypatch.setattr(bot, "bars", lambda: _bars(last, high=101.5))
    monkeypatch.setattr(bot, "vwap_signals", lambda df, cold=False: [
        {"tag": "vwap2", "signal": "VWAP band break", "side": -1, "z": -2.1,
         "risk_px": 1.0, "stop": 101.0, "ref": 100.0, "risk_pct": 0.002,
         "max_hold_h": 384}])
    monkeypatch.setattr(bot, "asia_signal", lambda df, cold=False: [])
    _short_leg(bot, at=str(pd.Timestamp(last, tz="UTC") - pd.Timedelta(hours=4)))
    bot._live = [{"size": "2.0", "side": "Sell", "avgPrice": "100.0",
                  "stopLoss": "101.0", "unrealisedPnl": "0"}]   # book says 0.5

    bot.once(Namespace(arm=True, weekends=False))

    assert bot.orders == [{"side": "Buy", "qty": 0.5, "tag": bot.orders[0]["tag"],
                           "reduce_only": True}]
    assert bot.load_state()["open"] == {}
