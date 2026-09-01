"""H-003 EMA x VWAP cross — one numba kernel, four exit rules.

Entry is fixed by the hypothesis: the EMA crossing the VWAP. Long when the EMA
crosses up through it, short when it crosses down. Signals are read on CLOSED
bars and filled at the next bar's open, so there is no look-ahead.

The four exits are what is actually being tested:

  EXIT_CROSS    the EMA crosses back through VWAP        (A - stop and reverse)
  EXIT_EMA      price closes back through the EMA        (B - much earlier exit)
  EXIT_RR       a fixed R multiple                       (C - measures payoff shape)
  EXIT_SESSION  the session ends, flat overnight         (D - how it is really traded)

`slope_filter` is variant E, and it is deliberately NOT an exit: it runs as a
paired flag over the identical configuration set so its effect can be scored as
a lift on the median, which is the only honest way to judge a filter. Scoring a
filter by whether it produced a new best just means the sample shrank.

Every trade carries a protective stop, including the "cross exit" variants. A
wide stop (6x ATR) is the honest way to express "no stop" - it keeps R defined,
and without it the drawdown of a stop-and-reverse system is unbounded and no
prop rule can be simulated against it.
"""
from __future__ import annotations

import numpy as np
from numba import njit

T_ENTRY_I, T_EXIT_I, T_DIR, T_ENTRY_PX, T_EXIT_PX, T_R, T_REASON, T_SESS = range(8)
N_COLS = 8

R_STOP, R_TARGET, R_CROSS, R_EMA, R_SESSION, R_TIME = range(6)

EXIT_CROSS, EXIT_EMA, EXIT_RR, EXIT_SESSION = 0, 1, 2, 3


@njit(cache=True)
def simulate(
    o, h, l, c, atr, ema, vwap, sess_id, rvol, hour,
    exit_mode,
    stop_atr,          # protective stop, in ATR multiples
    rr,                # R multiple target, used by EXIT_RR
    max_hold_bars,     # 0 = no time cap
    warmup_bars,       # skip the first N bars of a session: VWAP is meaningless
                       # until some volume has accumulated behind it
    slope_len,         # variant E: bars used for the EMA slope. 0 = filter off
    min_rvol,          # participation filter. The only filter family that has
                       # lifted a median anywhere in this project - twice on
                       # H-001, and the fold chose it in 22 of 30 H-002 folds.
    hour_lo, hour_hi,  # trade only inside [lo, hi) UTC. lo == hi disables it.
    dir_mode,          # 0 both, 1 long only, 2 short only
    reverse,           # 1 = flip straight into the opposite trade on a cross
    fee_bps, slip_bps, min_risk_bps,
):
    n = o.shape[0]
    # One trade per bar is the hard ceiling. Sizing this by session count
    # segfaulted on a stop-and-reverse in H-002 - it can flip many times a day.
    out = np.zeros((n, N_COLS), dtype=np.float64)
    k = 0
    cost = (fee_bps + slip_bps) / 10000.0

    i = warmup_bars + 1
    while i < n - 1:
        if k >= n:
            break
        if ema[i] <= 0.0 or vwap[i] <= 0.0 or ema[i - 1] <= 0.0 or vwap[i - 1] <= 0.0:
            i += 1
            continue

        up = (ema[i] > vwap[i]) and (ema[i - 1] <= vwap[i - 1])
        dn = (ema[i] < vwap[i]) and (ema[i - 1] >= vwap[i - 1])
        if not (up or dn):
            i += 1
            continue

        side = 1 if up else -1
        if dir_mode == 1 and side != 1:
            i += 1
            continue
        if dir_mode == 2 and side != -1:
            i += 1
            continue

        if min_rvol > 0.0 and rvol[i] < min_rvol:
            i += 1
            continue
        if hour_lo != hour_hi:
            hh = hour[i]
            inside = (hour_lo <= hh < hour_hi) if hour_lo < hour_hi \
                else (hh >= hour_lo or hh < hour_hi)          # window wraps midnight
            if not inside:
                i += 1
                continue

        # ---- variant E: the EMA must already be sloping the way it just crossed.
        # A cross that happens while the EMA is flat is chop, not a regime change.
        if slope_len > 0:
            j0 = i - slope_len
            if j0 < 0:
                i += 1
                continue
            slope = ema[i] - ema[j0]
            if side == 1 and slope <= 0.0:
                i += 1
                continue
            if side == -1 and slope >= 0.0:
                i += 1
                continue

        entry_i = i + 1
        entry = o[entry_i]
        a = atr[entry_i]
        if a <= 0.0:
            i += 1
            continue
        risk = stop_atr * a
        if risk <= 0.0 or risk < entry * min_risk_bps / 10000.0:
            i += 1
            continue
        stop = entry - risk if side == 1 else entry + risk
        target = 0.0
        if exit_mode == EXIT_RR and rr > 0.0:
            target = entry + rr * risk if side == 1 else entry - rr * risk

        horizon = n - 1
        if max_hold_bars > 0 and entry_i + max_hold_bars < horizon:
            horizon = entry_i + max_hold_bars

        exit_px = 0.0
        exit_i = entry_i
        reason = R_TIME
        j = entry_i
        while j < horizon:
            if side == 1:
                hit_stop = l[j] <= stop
                hit_tgt = target > 0.0 and h[j] >= target
            else:
                hit_stop = h[j] >= stop
                hit_tgt = target > 0.0 and l[j] <= target

            if hit_stop:                       # stop wins ties - pessimistic
                exit_px = stop; exit_i = j; reason = R_STOP
                break
            if hit_tgt:
                exit_px = target; exit_i = j; reason = R_TARGET
                break

            if j > entry_i:
                if exit_mode == EXIT_CROSS:
                    back = (ema[j] < vwap[j]) if side == 1 else (ema[j] > vwap[j])
                    if back:
                        exit_px = c[j]; exit_i = j; reason = R_CROSS
                        break
                elif exit_mode == EXIT_EMA:
                    back = (c[j] < ema[j]) if side == 1 else (c[j] > ema[j])
                    if back:
                        exit_px = c[j]; exit_i = j; reason = R_EMA
                        break
                if exit_mode == EXIT_SESSION and sess_id[j] != sess_id[entry_i]:
                    exit_px = o[j]; exit_i = j; reason = R_SESSION
                    break
            j += 1

        if reason == R_TIME:
            exit_i = horizon - 1 if j >= horizon else j
            if exit_i <= entry_i:
                exit_i = entry_i
            exit_px = c[exit_i]

        gross = (exit_px - entry) if side == 1 else (entry - exit_px)
        fees = (entry + exit_px) * cost
        out[k, T_ENTRY_I] = entry_i
        out[k, T_EXIT_I] = exit_i
        out[k, T_DIR] = side
        out[k, T_ENTRY_PX] = entry
        out[k, T_EXIT_PX] = exit_px
        out[k, T_R] = (gross - fees) / risk
        out[k, T_REASON] = reason
        out[k, T_SESS] = sess_id[entry_i]
        k += 1

        # `reverse` keeps the system always-in-market: the next cross is taken
        # from the bar this trade closed on. Otherwise wait for a fresh cross.
        i = exit_i if reverse == 1 else exit_i + 1
        if i <= entry_i:
            i = entry_i + 1

    return out[:k]
