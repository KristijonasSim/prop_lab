"""ORB (Opening Range Breakout) — vectorised sweep engine.

One numba kernel simulates one config over the whole history. Conventions that
keep it honest:

* The opening range is only known once its last bar has CLOSED. Entries are
  allowed from the following bar. No look-ahead.
* Stop-order (touch) entries fill at the trigger price, or at the bar OPEN when
  the bar gaps through it — never better.
* If a bar's range contains both the stop and the target, the STOP is assumed
  to fill first. 15m bars hide the intrabar path; this is the pessimistic read.
* Fees and slippage are charged on both sides, in bps of notional.
* Risk is fixed-fractional: every trade risks the same fraction of the STARTING
  equity, so an R multiple means the same thing in every trade and no
  budget-shrinking creeps in (CLAUDE.md).
"""

from __future__ import annotations

import numpy as np
from numba import njit

# trade record columns
T_ENTRY_I, T_EXIT_I, T_DIR, T_ENTRY_PX, T_EXIT_PX, T_R, T_REASON, T_SESS = range(8)
N_COLS = 8

# exit reasons
R_STOP, R_TARGET, R_TIME = 0, 1, 2

DIR_BOTH, DIR_LONG, DIR_SHORT = 0, 1, 2
ENTRY_TOUCH, ENTRY_CLOSE, ENTRY_FIRST_CANDLE, ENTRY_RETEST = 0, 1, 2, 3
STOP_OR_OPPOSITE, STOP_OR_MID, STOP_ATR = 0, 1, 2
TREND_NONE, TREND_WITH, TREND_AGAINST = 0, 1, 2


@njit(cache=True)
def simulate(
    o, h, l, c, atr, ema, rvol, datr, ema_fast, atr_rank, dtrend,
    sess_start,          # int array: bar index where each session starts
    or_bars,             # int: bars in the opening range
    max_hold_bars,       # int: bars after OR end before a forced exit
    dir_mode,
    entry_mode,
    stop_mode,
    stop_atr_mult,
    rr,                  # target = rr * risk; 0 disables the target
    buffer_bps,          # entry trigger placed this far beyond the OR edge
    fee_bps,
    slip_bps,
    one_trade,           # 1 = at most one trade per session
    min_or_atr,          # OR range / ATR floor  (0 disables)
    max_or_atr,          # OR range / ATR ceiling (0 disables)
    trend_mode,
    fade,                # 1 = take the opposite side of the break
    min_risk_bps,        # reject a setup whose stop sits closer than this to the
                         # entry. Without it, a stop a hair away from the fill
                         # divides by ~0 and manufactures 25R "winners" that no
                         # exchange would ever fill.
    min_rvol,            # opening-range relative volume floor (0 disables).
                         # This is the filter the ORB literature says IS the edge.
    use_datr,            # 1 = size the ATR stop off DAILY ATR (the papers' 10%-of-ADR
                         # stop), 0 = off the 15m ATR
    min_break_rvol,      # volume on the BREAKOUT bar vs its trailing mean (0 = off).
                         # Distinct from min_rvol, which gates on the opening range.
    max_entry_bars,      # only arm for this many bars after the range closes (0 = off).
                         # A break six hours after the open is not an opening-range break.
    be_at_r,             # move the stop to entry once price reaches this many R (0 = off)
    min_atr_rank,        # volatility regime: percentile rank of ATR (0 = off)
    max_atr_rank,        # 0 = off
    dtrend_mode,         # 0 off, 1 only with the daily trend, 2 only against it
    fast_trend_mode,     # same, against a fast EMA instead of the slow one
    retest_bars,         # ENTRY_RETEST: bars allowed for the pullback (0 = no limit)
):
    n = o.shape[0]
    n_sess = sess_start.shape[0]
    out = np.zeros((n_sess * 2, N_COLS), dtype=np.float64)
    k = 0

    cost = (fee_bps + slip_bps) / 10000.0
    buf = buffer_bps / 10000.0

    for s in range(n_sess):
        start = sess_start[s]
        or_end = start + or_bars                    # first bar AFTER the range
        if or_end >= n:
            break
        stop_bar = or_end + max_hold_bars
        if s + 1 < n_sess and sess_start[s + 1] < stop_bar:
            stop_bar = sess_start[s + 1]            # never overlap the next session
        if stop_bar > n - 1:
            stop_bar = n - 1
        if or_end >= stop_bar:
            continue

        # ---- opening range (closed bars only) ----
        or_hi = h[start]
        or_lo = l[start]
        for i in range(start + 1, or_end):
            if h[i] > or_hi:
                or_hi = h[i]
            if l[i] < or_lo:
                or_lo = l[i]
        or_rng = or_hi - or_lo
        if or_rng <= 0.0:
            continue

        # ---- range-size filter, measured against ATR at the OR close ----
        a = atr[or_end - 1]
        if a > 0.0:
            ratio = or_rng / a
            if min_or_atr > 0.0 and ratio < min_or_atr:
                continue
            if max_or_atr > 0.0 and ratio > max_or_atr:
                continue

        if min_rvol > 0.0 and rvol[or_end - 1] < min_rvol:
            continue
        ar = atr_rank[or_end - 1]
        if min_atr_rank > 0.0 and ar < min_atr_rank:
            continue
        if max_atr_rank > 0.0 and ar > max_atr_rank:
            continue

        trig_hi = or_hi * (1.0 + buf)
        trig_lo = or_lo * (1.0 - buf)

        last_entry_bar = stop_bar
        if max_entry_bars > 0 and or_end + max_entry_bars < stop_bar:
            last_entry_bar = or_end + max_entry_bars

        taken = 0
        i = or_end
        while i < stop_bar:
            if i >= last_entry_bar and taken == 0:
                break
            if one_trade == 1 and taken == 1:
                break

            side = 0          # +1 long, -1 short
            entry = 0.0
            entry_i = i

            if entry_mode == ENTRY_TOUCH:
                up = h[i] >= trig_hi
                dn = l[i] <= trig_lo
                if up and dn:
                    # both edges in one bar: take whichever the open was nearer
                    if abs(o[i] - trig_hi) <= abs(o[i] - trig_lo):
                        dn = False
                    else:
                        up = False
                if up:
                    side = 1
                    entry = o[i] if o[i] > trig_hi else trig_hi
                elif dn:
                    side = -1
                    entry = o[i] if o[i] < trig_lo else trig_lo
            elif entry_mode == ENTRY_FIRST_CANDLE:
                # Zarattini/Aziz QQQ variant: no breakout wait. Take the direction
                # of the opening range itself at the first bar after it closes.
                if i > or_end:
                    break
                if c[or_end - 1] > o[start]:
                    side = 1
                elif c[or_end - 1] < o[start]:
                    side = -1
                entry = o[i]
            elif entry_mode == ENTRY_RETEST:
                # Wait for a close beyond the edge, then require price to come
                # back and touch the level again before taking it.
                if c[i] > trig_hi or c[i] < trig_lo:
                    up_break = c[i] > trig_hi
                    lvl = trig_hi if up_break else trig_lo
                    limit = i + retest_bars if retest_bars > 0 else last_entry_bar
                    if limit > last_entry_bar:
                        limit = last_entry_bar
                    j2 = i + 1
                    while j2 < limit:
                        if up_break and l[j2] <= lvl:
                            side = 1
                            entry = lvl
                            entry_i = j2
                            break
                        if (not up_break) and h[j2] >= lvl:
                            side = -1
                            entry = lvl
                            entry_i = j2
                            break
                        # a stop-out of the idea: it ran away without retesting
                        j2 += 1
                    if side == 0:
                        i = j2 if j2 > i else i + 1
                        continue
            else:  # close-beyond confirmation, fill at the next bar's open
                if i + 1 >= stop_bar:
                    break
                if c[i] > trig_hi:
                    side = 1
                    entry = o[i + 1]
                    entry_i = i + 1
                elif c[i] < trig_lo:
                    side = -1
                    entry = o[i + 1]
                    entry_i = i + 1

            if side == 0:
                i += 1
                continue

            if fade == 1:
                side = -side

            if dir_mode == DIR_LONG and side != 1:
                i += 1
                continue
            if dir_mode == DIR_SHORT and side != -1:
                i += 1
                continue

            if min_break_rvol > 0.0 and rvol[entry_i] < min_break_rvol:
                i += 1
                continue

            if dtrend_mode != TREND_NONE:
                dt = dtrend[entry_i]
                with_d = (side == 1 and dt > 0) or (side == -1 and dt < 0)
                if dtrend_mode == TREND_WITH and not with_d:
                    i += 1
                    continue
                if dtrend_mode == TREND_AGAINST and with_d:
                    i += 1
                    continue

            if fast_trend_mode != TREND_NONE:
                ef = ema_fast[entry_i]
                with_f = (side == 1 and entry > ef) or (side == -1 and entry < ef)
                if fast_trend_mode == TREND_WITH and not with_f:
                    i += 1
                    continue
                if fast_trend_mode == TREND_AGAINST and with_f:
                    i += 1
                    continue

            if trend_mode != TREND_NONE:
                e = ema[entry_i]
                with_trend = (side == 1 and entry > e) or (side == -1 and entry < e)
                if trend_mode == TREND_WITH and not with_trend:
                    i += 1
                    continue
                if trend_mode == TREND_AGAINST and with_trend:
                    i += 1
                    continue

            # ---- stop placement ----
            if stop_mode == STOP_OR_OPPOSITE:
                stop = or_lo if side == 1 else or_hi
            elif stop_mode == STOP_OR_MID:
                stop = (or_hi + or_lo) * 0.5
            else:
                base = datr[or_end - 1] if use_datr == 1 else a
                d = stop_atr_mult * (base if base > 0.0 else or_rng)
                stop = entry - d if side == 1 else entry + d

            risk = (entry - stop) if side == 1 else (stop - entry)
            if risk <= 0.0 or risk < entry * min_risk_bps / 10000.0:
                i += 1
                continue

            target = 0.0
            if rr > 0.0:
                target = entry + rr * risk if side == 1 else entry - rr * risk

            # ---- walk forward to the exit ----
            exit_px = 0.0
            exit_i = entry_i
            reason = R_TIME
            be_armed = False
            be_level = entry + risk * be_at_r if side == 1 else entry - risk * be_at_r
            j = entry_i
            while j < stop_bar:
                if side == 1:
                    hit_stop = l[j] <= stop
                    hit_tgt = rr > 0.0 and h[j] >= target
                else:
                    hit_stop = h[j] >= stop
                    hit_tgt = rr > 0.0 and l[j] <= target
                if hit_stop:                      # stop wins ties — pessimistic
                    exit_px = stop
                    exit_i = j
                    reason = R_STOP
                    break
                if hit_tgt:
                    exit_px = target
                    exit_i = j
                    reason = R_TARGET
                    break
                # Arm the breakeven only at the END of the bar. Arming mid-bar
                # would let the same bar both trigger and honour the new stop,
                # which the 15m data cannot support.
                if be_at_r > 0.0 and not be_armed:
                    if (side == 1 and h[j] >= be_level) or (side == -1 and l[j] <= be_level):
                        stop = entry
                        be_armed = True
                j += 1
            if reason == R_TIME:
                exit_i = stop_bar - 1 if j >= stop_bar else j
                exit_px = c[exit_i]

            gross = (exit_px - entry) if side == 1 else (entry - exit_px)
            fees = (entry + exit_px) * cost
            r_mult = (gross - fees) / risk

            out[k, T_ENTRY_I] = entry_i
            out[k, T_EXIT_I] = exit_i
            out[k, T_DIR] = side
            out[k, T_ENTRY_PX] = entry
            out[k, T_EXIT_PX] = exit_px
            out[k, T_R] = r_mult
            out[k, T_REASON] = reason
            out[k, T_SESS] = s
            k += 1
            taken = 1
            i = exit_i + 1

    return out[:k]
