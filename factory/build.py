"""STEP 2 — run a `Strategy` over bars and produce TRADES.

Trades, not signals. Step 3 judges trades (Kris, 2026-09-21: the unit is a
trade, not a bar) and step 7 counts money, so the currency is the same all the
way along and nothing is lost between steps.

THE FOUR FILL RULES, ALL LEARNED EXPENSIVELY AND ALL IN `CLAUDE.md`:

1. **Decide on a closed bar, fill at the NEXT bar's open.** The decision at bar
   t can only use bars <= t, which `guard.Window` enforces by shape.
2. **Never decide or fill on a dead bar.** Dukascopy pads the closed FX weekend
   with zero-volume bars at a frozen price - 21.5% of the gold series. Before
   this was fixed, one H-016 leg took 25.19R of 54.25R from them.
3. **A stop the bar GAPPED PAST fills at the open, not at the level.** A stop is
   a stop-market order; on a gap price never walked to it. Ignoring this is what
   made H-016's pace headline rest on a fill nobody could have got.
4. **A target keeps its level.** It is a limit order, and a gap through it fills
   better. Taking that bonus would be optimism in the other direction, so it is
   not taken.

COSTS are charged once, as a full round trip, at entry. Reported at 1x/2x/3x
upstream by simply passing a different `cost_bps`.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from factory.guard import Window
from factory.spec import Strategy

ATR_LEN = 14


@dataclass(frozen=True)
class Trade:
    entry_bar: int
    exit_bar: int
    entry_px: float
    exit_px: float
    side: str
    r: float            # result in R, net of the round trip
    reason: str         # stop | target | time | end
    risk: float         # the 1R denominator, in price. Kept so a trade can be
                        # RE-PRICED at another cost multiple without re-running:
                        # cost enters R linearly, so r(m) = r - (m-1)*cost/risk.


def series(strategy: Strategy, frame: pd.DataFrame) -> tuple[np.ndarray, np.ndarray]:
    """Entry flags and ATR at every bar, each computed through the guard.

    One Window per bar. A condition that needs history it does not have returns
    nan, and nan never satisfies a comparison, so the warm-up handles itself.

    PUBLIC, and separate from `run`, for two reasons. It is the expensive half -
    a Python loop over every bar - so step 3 computes it once and re-prices the
    same signals at 1x/2x/3x cost. And the random-entry control needs the REAL
    `atr` with a DIFFERENT `fire`, which is only expressible if the two can be
    handed to `run` from outside.
    """
    n = len(frame)
    fire = np.zeros(n, dtype=bool)
    atr = np.full(n, np.nan)
    prev = {}
    for t in range(n):
        w = Window(frame, t)
        atr[t] = _atr_at(w)
        ok = True
        for i, c in enumerate(strategy.entry):
            lv, rv = c.left.at(w), c.right.at(w)
            pl, pr = prev.get(i, (np.nan, np.nan))
            prev[i] = (lv, rv)
            if np.isnan(lv) or np.isnan(rv):
                ok = False; continue
            if c.op == "above":        hit = lv > rv
            elif c.op == "below":      hit = lv < rv
            elif c.op == "cross_above":
                hit = (not np.isnan(pl) and not np.isnan(pr)
                       and pl <= pr and lv > rv)
            else:                                        # cross_below
                hit = (not np.isnan(pl) and not np.isnan(pr)
                       and pl >= pr and lv < rv)
            ok = ok and hit
        fire[t] = ok
    return fire, atr


def _atr_at(w) -> float:
    if len(w) < ATR_LEN + 1:
        return np.nan
    h = np.asarray(w.high[-ATR_LEN:], dtype=float)
    l = np.asarray(w.low[-ATR_LEN:], dtype=float)
    c = np.asarray(w.close[-(ATR_LEN+1):-1], dtype=float)
    return float(np.mean(np.maximum(h - l, np.maximum(abs(h - c), abs(l - c)))))


def run(strategy: Strategy, frame: pd.DataFrame, cost_bps: float,
        signals: tuple[np.ndarray, np.ndarray] | None = None) -> list[Trade]:
    """Every trade the strategy would have taken. One position at a time.

    `signals` overrides the computed `(fire, atr)`. Nothing in the trading rules
    changes - the same fill rules, the same stop, the same hold - so a control
    built this way differs from the real run in the ENTRY BARS and in nothing
    else, which is what makes the comparison a paired one.
    """
    need = {"open", "high", "low", "close"}
    if not need <= set(frame.columns):
        raise ValueError(f"frame needs {sorted(need)}")
    frame = frame.reset_index(drop=True)
    live = (frame["volume"].values > 0) if "volume" in frame else np.ones(len(frame), bool)

    fire, atr = series(strategy, frame) if signals is None else signals
    o, h, l, c = (frame[k].values for k in ("open", "high", "low", "close"))
    long_ = strategy.side == "long"
    sgn = 1.0 if long_ else -1.0
    trades: list[Trade] = []
    n = len(frame)
    t = 0
    while t < n - 1:
        # rule 1: decide on bar t, fill at t+1's open.  rule 2: both must be live.
        if not (fire[t] and live[t] and live[t + 1]) or np.isnan(atr[t]) or atr[t] <= 0:
            t += 1; continue
        e = t + 1
        px = o[e]
        risk = strategy.stop_atr * atr[t]
        # rule 5: a stop narrower than the cost of trading is not a position.
        #
        # Found 2026-09-21 running the queue on gold. One trade of 35 fired in a
        # dead-quiet hour where ATR was 4e-5 of price - a 0.19-point stop against
        # a 0.74-point round trip. R is (move / risk), so a near-zero risk makes
        # R explode: that single trade scored +290.9R and dragged the rule's mean
        # from about zero to +8.24R. Sizing to it would mean a position hundreds
        # of times normal, which no account survives and no broker fills.
        #
        # CLAUDE.md already carries this lesson in another costume - "a
        # volatility guard needs a tolerance in price terms, not <= 0.0". The
        # tolerance that means something here is the cost itself.
        if risk < 2.0 * px * cost_bps / 1e4:
            t += 1; continue
        stop = px - sgn * risk
        target = px + sgn * strategy.target_atr * atr[t]
        # rule 6: the time exit books at the last bar that actually traded.
        #
        # A first version set the fallback to the END OF THE SERIES and let a
        # `continue` on a dead bar skip the time exit. When the last bar of the
        # hold window was a padded weekend bar, the trade fell through and was
        # closed years later at the final close - one short scored -45R and
        # dragged its rule's mean from roughly zero to -45.4R. Seeding the
        # fallback with the entry bar and moving it forward over live bars only
        # means a trade can never outlive its own hold window.
        last_live = e
        exit_bar, exit_px, why = e, o[e], "time"
        for k in range(e, min(e + strategy.max_hold, n)):
            if not live[k]:
                continue
            last_live = k
            exit_bar, exit_px, why = k, c[k], "time"
            if long_:
                gapped = o[k] <= stop
                hit_stop, hit_tgt = l[k] <= stop, h[k] >= target
            else:
                gapped = o[k] >= stop
                hit_stop, hit_tgt = h[k] >= stop, l[k] <= target
            if hit_stop:
                # rule 3: a gap past the stop fills at the open, not the level
                exit_bar, exit_px, why = k, (o[k] if gapped else stop), "stop"
                break
            if hit_tgt:
                # rule 4: a target keeps its level even on a gap through it
                exit_bar, exit_px, why = k, target, "target"
                break
            if k == e + strategy.max_hold - 1:
                break
        gross = sgn * (exit_px - px)
        cost = px * cost_bps / 1e4
        trades.append(Trade(e, exit_bar, float(px), float(exit_px), strategy.side,
                            float((gross - cost) / risk), why, float(risk)))
        t = exit_bar + 1          # one position at a time, no pyramiding
    return trades


def _demo(argv=None) -> int:
    """Take ideas off the queue, run them on gold, show what step 3 will judge.

    This is steps 1 and 2 joined up and nothing more. It prints trades, not a
    verdict, because step 3 does not exist yet and a number without a gate in
    front of it is the thing this repo keeps having to retract.
    """
    import argparse

    from factory import queue

    ap = argparse.ArgumentParser(description=_demo.__doc__)
    ap.add_argument("-n", "--count", type=int, default=5)
    ap.add_argument("--market", default="XAUUSD_dukascopy_1h")
    ap.add_argument("--cost", type=float, default=1.64, help="round trip, bps")
    a = ap.parse_args(argv)

    from pathlib import Path
    root = Path(__file__).resolve().parents[1]
    px = pd.read_parquet(root / "data" / f"{a.market}.parquet").reset_index(drop=True)
    years = len(px) / (24 * 365)
    print(f"{a.market}: {len(px):,} bars, ~{years:.1f} years, "
          f"round trip {a.cost} bps\n")
    print(f"{'idea':46}{'trades':>8}{'tpd':>7}{'mean R':>9}{'median R':>10}")
    print("-" * 80)
    for _ in range(a.count):
        s = queue.take()
        if s is None:
            print("queue empty - run `python -m factory.fill`")
            break
        tr = run(s, px, cost_bps=a.cost)
        if tr:
            r = np.array([t.r for t in tr])
            print(f"{s.label()[:44]:46}{len(tr):>8}{len(tr)/(years*365):>7.2f}"
                  f"{r.mean():>+9.3f}{np.median(r):>+10.3f}")
        else:
            print(f"{s.label()[:44]:46}{0:>8}{'':>7}{'':>9}{'':>10}")
        queue.mark_tried(s, verdict="ran", note=f"{len(tr)} trades on {a.market}")
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(_demo())
