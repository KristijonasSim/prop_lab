"""The demo bot's exit path, with the exchange mocked out.

Two bugs found 2026-09-11 in `live/bybit_demo.py`, neither yet triggered live:

  * an armed exit was traded TWICE - reduce-only, then again inside the net
    order - so the last leg's exit would have opened an unbooked position the
    other way;
  * exits only ran on a pass that also had a signal, and never on weekends, so a
    touched stop waited for an unrelated bar to fire.
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
    monkeypatch.setattr(m, "positions", lambda host: [])
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
