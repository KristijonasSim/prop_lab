"""ORB stage 6 — cross-check the fast engine against NautilusTrader.

Nothing survived stage 1, so the job here is not to validate a winner. It is to
prove the null result is not an artefact of my own kernel: run the same config
through an independent event-driven matching engine with real order objects and
check the two agree on trade count and profit factor.
"""
from __future__ import annotations

import sys
from decimal import Decimal
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from nautilus_trader.common.enums import LogColor          # noqa: E402
from nautilus_trader.model.data import BarType             # noqa: E402
from nautilus_trader.model.enums import OrderSide, OrderType, TimeInForce  # noqa: E402
from nautilus_trader.model.objects import Quantity         # noqa: E402
from nautilus_trader.trading.strategy import Strategy      # noqa: E402


class ORBStrategy(Strategy):
    """Session opening-range breakout, bracket-ordered.

    Mirrors strategies/orb/engine.py: range from the first `or_bars` closed bars
    after `hour`:00 UTC, stop-market entry beyond the edge, ATR or range stop,
    optional R-multiple target, forced flat at the session horizon.
    """

    def __init__(self, config):
        super().__init__(config)
        self.instrument_id = config.instrument_id
        self.bar_type = BarType.from_str(config.bar_type)
        self.hour = config.hour
        self.or_bars = config.or_bars
        self.hold_bars = config.hold_bars
        self.rr = config.rr
        self.stop_atr_mult = config.stop_atr_mult
        self.trade_qty = Decimal(str(config.trade_qty))

        self.instrument = None
        self._bars: list = []
        self._sess_bars = 0
        self._or_hi = self._or_lo = None
        self._armed = False
        self._entry_order = None
        self._bars_since_or = 0
        self._entries: list = []
        self._risk = 0.0
        self.n_entries = 0

    def on_start(self):
        self.instrument = self.cache.instrument(self.instrument_id)
        self.subscribe_bars(self.bar_type)

    def _atr(self, n=14):
        if len(self._bars) < n + 1:
            return None
        trs = []
        for i in range(-n, 0):
            b, p = self._bars[i], self._bars[i - 1]
            h, l, c = float(b.high), float(b.low), float(p.close)
            trs.append(max(h - l, abs(h - c), abs(l - c)))
        return sum(trs) / n

    def on_bar(self, bar):
        self._bars.append(bar)
        if len(self._bars) > 400:
            self._bars.pop(0)

        ts = pd.Timestamp(bar.ts_event, unit="ns", tz="UTC")
        new_session = ts.hour == self.hour and ts.minute == 0

        if new_session:
            self._sess_bars = 0
            self._or_hi = self._or_lo = None
            self._armed = False
            self._bars_since_or = 0
            self._flatten()

        self._sess_bars += 1

        if self._sess_bars <= self.or_bars:
            h, l = float(bar.high), float(bar.low)
            self._or_hi = h if self._or_hi is None else max(self._or_hi, h)
            self._or_lo = l if self._or_lo is None else min(self._or_lo, l)
            if self._sess_bars == self.or_bars:
                self._armed = True
            return

        if not self._armed:
            return

        self._bars_since_or += 1
        if self._bars_since_or > self.hold_bars:
            self._armed = False
            self._flatten()
            return

        if self.portfolio.is_flat(self.instrument_id) and self._entry_order is None:
            self._arm_brackets()
            self.n_entries += 1

    def _arm_brackets(self):
        atr = self._atr()
        if atr is None or self._or_hi is None:
            return
        risk = self.stop_atr_mult * atr if self.stop_atr_mult > 0 else (self._or_hi - self._or_lo)
        if risk <= 0:
            return
        self._risk = risk
        px = self.instrument.make_price
        qty = Quantity(self.trade_qty, self.instrument.size_precision)

        # Two resting stop-market entries, one each side of the range. The
        # bracket factory has no STOP_MARKET entry and its MARKET_IF_TOUCHED
        # substitute triggers on the WRONG side for a breakout, so the OUO pair
        # is managed by hand here instead.
        self._entries = []
        for side, trigger in ((OrderSide.BUY, self._or_hi), (OrderSide.SELL, self._or_lo)):
            o = self.order_factory.stop_market(
                instrument_id=self.instrument_id,
                order_side=side,
                quantity=qty,
                trigger_price=px(trigger),
                time_in_force=TimeInForce.GTC,
            )
            self._entries.append(o.client_order_id)
            self.submit_order(o)
        self._entry_order = True

    def on_order_filled(self, event):
        if event.client_order_id in self._entries:
            # one side filled -> kill the other, then attach the exits
            for cid in self._entries:
                if cid != event.client_order_id:
                    o = self.cache.order(cid)
                    if o is not None and o.is_open:
                        self.cancel_order(o)
            self._entries = []
            self._attach_exits(event)

    def _attach_exits(self, event):
        px = self.instrument.make_price
        entry = float(event.last_px)
        long = event.order_side == OrderSide.BUY
        stop = entry - self._risk if long else entry + self._risk
        exit_side = OrderSide.SELL if long else OrderSide.BUY
        qty = event.last_qty

        sl = self.order_factory.stop_market(
            instrument_id=self.instrument_id, order_side=exit_side, quantity=qty,
            trigger_price=px(stop), time_in_force=TimeInForce.GTC, reduce_only=True,
        )
        self.submit_order(sl)
        if self.rr > 0:
            tp_px = entry + self.rr * self._risk if long else entry - self.rr * self._risk
            tp = self.order_factory.limit(
                instrument_id=self.instrument_id, order_side=exit_side, quantity=qty,
                price=px(tp_px), time_in_force=TimeInForce.GTC, reduce_only=True,
                post_only=False,
            )
            self.submit_order(tp)

    def _flatten(self):
        self.cancel_all_orders(self.instrument_id)
        if not self.portfolio.is_flat(self.instrument_id):
            self.close_all_positions(self.instrument_id)
        self._entry_order = None

    def on_stop(self):
        self._flatten()
        self.log.info(f"entries armed: {self.n_entries}", color=LogColor.YELLOW)


# ---------------------------------------------------------------- runner
def main():
    from nautilus_trader.config import StrategyConfig
    from nautilus_trader.model.identifiers import InstrumentId

    from core import data, nautilus_setup as ns
    from strategies.orb.sweep import features, run_one, trade_metrics, DEFAULTS

    # The config that topped the 1x-cost IS ranking. Small window: an
    # event-driven engine with real order objects is ~1000x slower than the kernel.
    LO, HI = "2022-01-01", "2023-01-01"
    CFG = dict(DEFAULTS)
    CFG.update(hour=0, or_bars=4, hold_bars=96, entry_mode=0,
               stop_mode=2, stop_atr_mult=2.0, rr=0.0, fade=0)

    df = data.load("BTC/USDT", "15m")
    w = df[(df.index >= LO) & (df.index < HI)]

    # --- fast kernel ---
    feats = features(w)
    tr = run_one(w, feats, CFG, ns.TAKER_FEE * 10000 / 2, 0.0)
    span = (w.index[-1] - w.index[0]).total_seconds() / 86400.0
    fast = trade_metrics(tr, w.index, span)

    # --- nautilus ---
    engine = ns.make_engine(starting_equity=1_000_000)
    instrument, bar_type = ns.add_bars(engine, w)

    class Cfg(StrategyConfig, frozen=True):
        instrument_id: InstrumentId
        bar_type: str
        hour: int
        or_bars: int
        hold_bars: int
        rr: float
        stop_atr_mult: float
        trade_qty: float

    engine.add_strategy(ORBStrategy(Cfg(
        instrument_id=instrument.id, bar_type=str(bar_type),
        hour=CFG["hour"], or_bars=CFG["or_bars"], hold_bars=CFG["hold_bars"],
        rr=CFG["rr"], stop_atr_mult=CFG["stop_atr_mult"], trade_qty=0.1,
    )))
    engine.run()

    fills = engine.trader.generate_order_fills_report()
    positions = engine.trader.generate_positions_report()
    print("\n--- cross-check ---")
    print(f"fast kernel : {fast['trades']} trades, PF {fast['pf']}, win {fast['win_rate']}")
    print(f"nautilus    : {len(positions)} positions, {len(fills)} fills")
    if len(positions):
        pnl = pd.to_numeric(positions["realized_pnl"].astype(str).str.replace(
            r"[^0-9.\-]", "", regex=True), errors="coerce").dropna()
        wins, losses = pnl[pnl > 0].sum(), -pnl[pnl < 0].sum()
        print(f"nautilus PF : {wins / losses if losses else float('inf'):.3f}  "
              f"win {(pnl > 0).mean():.3f}  net {pnl.sum():.0f} USDT")
    engine.dispose()


if __name__ == "__main__":
    main()
