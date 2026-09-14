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
    # THE EQUITY LOG IS A REAL FILE AND THE TESTS ARM THE BOT. Without this the
    # suite appends to live/paper/equity.jsonl on every run - a test writing
    # into the live bot's own record of the account it is trading.
    monkeypatch.setattr(m, "EQUITY_LOG", tmp_path / "equity.jsonl")
    orders: list[dict] = []
    monkeypatch.setattr(m, "equity", lambda host: 10_000.0)
    # THE MOCKED EXCHANGE HOLDS WHAT THE BOOK SAYS IT HOLDS. This used to be a
    # bare `[]` while the tests wrote a book with a leg in it - a state the bot
    # now treats as a position closed behind its back, because on 2026-09-12
    # that is exactly what happened. `_short_leg` sets both sides together;
    # a test that wants them to disagree says so explicitly.
    m._live = []
    monkeypatch.setattr(m, "positions", lambda host: m._live)
    # THE MOCK ANSWERS LIKE THE EXCHANGE DOES. It used to return None, which the
    # caller could not tell from a rejection - and the caller did not look.
    m._backstops: list[float] = []
    monkeypatch.setattr(m, "set_backstop", lambda host, level:
                        m._backstops.append(level) or {"retCode": 0})
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


# --------------------------------------------------------------------------- #
# The backstop. Two bugs found 2026-09-14 by reading the VM's log after a
# stop-out: the level was read off the wrong side of a mixed book, and the
# exchange's answer was never looked at.
# --------------------------------------------------------------------------- #
def _leg(side: str, qty: float, stop: float) -> dict:
    return {"at": "2026-09-14 02:00:00+00:00", "side": side, "qty": qty,
            "stop": stop, "hold_h": 384, "entry_ref": 100.0}


def test_backstop_on_a_short_book_is_the_highest_stop(bot):
    """Price rising reaches 101.0 first and 102.0 last, so the backstop is 102.0
    - every leg's own stop is touched before the exchange's is."""
    legs = {"a": _leg("Sell", 1.0, 101.0), "b": _leg("Sell", 1.0, 102.0)}
    assert bot.backstop_level(legs) == 102.0


def test_backstop_on_a_long_book_is_the_lowest_stop(bot):
    legs = {"a": _leg("Buy", 1.0, 99.0), "b": _leg("Buy", 1.0, 98.0)}
    assert bot.backstop_level(legs) == 98.0


def test_a_mixed_book_is_priced_off_the_side_it_nets_to(bot):
    """THE BUG. Five short legs and one long leg net SHORT, so the stop belongs
    ABOVE the price. The old code took the minimum over the long legs and
    handed Bybit 99.0 - below a short position, which it rejects."""
    legs = {"v1": _leg("Sell", 1.0, 101.0), "v2": _leg("Sell", 1.0, 102.0),
            "asia": _leg("Buy", 0.5, 99.0)}
    assert bot.backstop_level(legs) == 102.0

    legs = {"v1": _leg("Buy", 1.0, 99.0), "v2": _leg("Buy", 1.0, 98.0),
            "asia": _leg("Sell", 0.5, 101.0)}
    assert bot.backstop_level(legs) == 98.0


def test_a_book_that_nets_flat_gets_no_backstop(bot):
    """Nothing is open on the exchange, so no single level means anything."""
    legs = {"a": _leg("Sell", 1.0, 101.0), "b": _leg("Buy", 1.0, 99.0)}
    assert bot.backstop_level(legs) is None


def test_a_rejected_backstop_is_reported_as_rejected(bot, monkeypatch, capsys):
    """The log must never claim a stop the exchange refused. Before this, the
    return was discarded and the line read 'backstop stop-loss set at' either
    way - so an unprotected book looked identical to a protected one."""
    last = "2026-09-14 14:00"
    _short_leg(bot, at=str(pd.Timestamp(last, tz="UTC") - pd.Timedelta(hours=4)))
    monkeypatch.setattr(bot, "set_backstop", lambda host, level:
                        {"retCode": 10001, "retMsg": "stop loss price invalid"})
    monkeypatch.setattr(bot, "bars", lambda: _bars(last, high=100.5))
    monkeypatch.setattr(bot, "vwap_signals", lambda df, cold=False: [])
    monkeypatch.setattr(bot, "asia_signal", lambda df, cold=False: [])
    bot.once(Namespace(arm=True, weekends=False))
    out = capsys.readouterr().out
    assert "BACKSTOP REJECTED" in out
    assert "backstop stop-loss set at" not in out


# --------------------------------------------------------------------------- #
# The daily frame and the equity path, added 2026-09-14 after H-039 showed the
# backtest never marks open positions to market and the bot had no idea what a
# day was.
# --------------------------------------------------------------------------- #
def test_the_day_frame_opens_once_and_then_holds(bot):
    st = {}
    open_eq, dd = bot.day_frame(st, 10_000.0)
    assert open_eq == 10_000.0 and dd == 0.0
    # a later pass the same day keeps the opening equity and measures from it
    open_eq, dd = bot.day_frame(st, 9_700.0)
    assert open_eq == 10_000.0
    assert dd == pytest.approx(-3.0)


def test_a_new_utc_day_reopens_the_frame(bot):
    st = {"day": "1999-01-01", "day_open": 5_000.0}
    open_eq, dd = bot.day_frame(st, 10_000.0)
    assert open_eq == 10_000.0 and dd == 0.0
    assert st["day"] != "1999-01-01"


def test_the_equity_path_is_written_once_per_armed_pass(bot, monkeypatch):
    """H-039's whole point: Bybit's equity INCLUDES unrealised, so this file is
    the mark-to-market series the backtest does not have."""
    import json
    _short_leg(bot, at="2026-09-14 02:00:00+00:00")
    monkeypatch.setattr(bot, "bars", lambda: _bars("2026-09-14 14:00", high=100.5))
    monkeypatch.setattr(bot, "vwap_signals", lambda df, cold=False: [])
    monkeypatch.setattr(bot, "asia_signal", lambda df, cold=False: [])
    bot.once(Namespace(arm=True, weekends=False))
    rows = [json.loads(x) for x in bot.EQUITY_LOG.read_text().splitlines()]
    assert len(rows) == 1
    assert rows[0]["equity"] == 10_000.0
    assert set(rows[0]) >= {"ts", "equity", "peak", "day_open", "day_dd_pct",
                            "unrealised", "legs", "net_qty"}


def test_a_dry_run_writes_no_equity_line(bot, monkeypatch):
    """Same rule the book already follows: a dry run must remember nothing."""
    _short_leg(bot, at="2026-09-14 02:00:00+00:00")
    monkeypatch.setattr(bot, "bars", lambda: _bars("2026-09-14 14:00", high=100.5))
    monkeypatch.setattr(bot, "vwap_signals", lambda df, cold=False: [])
    monkeypatch.setattr(bot, "asia_signal", lambda df, cold=False: [])
    bot.once(Namespace(arm=False, weekends=False))
    assert not bot.EQUITY_LOG.exists()
