"""H-005 liquidity sweep / stop-run fade — numba kernel.

Mechanism, stated before results. Stops cluster just beyond obvious swing highs
and lows. When price pushes through one, those stops fire as MARKET orders -
forced, price-insensitive flow. Whoever absorbs it is filled at a level nobody
chose to trade at voluntarily. If the push was only the stop run and not new
information, price returns inside the range. The counterparty is named and
compelled, which is the same property that made funding worth testing and is
absent from every pure price pattern this project has rejected.

This is deliberately the INVERSE of breakout-retest, which failed on BTC at
every timeframe in the prior repo while its inverse (`liquidity_sweep`) worked.
That prior is the reason this is being tested at all.

Entry: price takes out the extreme of the last `lookback` bars by at least
`pierce_atr` ATRs, then CLOSES back inside the range on the same bar. Fill at the
next bar's open - the sweep bar's close is a signal, not a fill.

`require_wick` demands the rejection be a wick rather than a body, which is the
form the setup is usually described in. `min_range_atr` refuses ranges too narrow
to hold meaningful stops.
"""
from __future__ import annotations

import numpy as np
from numba import njit

T_ENTRY_I, T_EXIT_I, T_DIR, T_ENTRY_PX, T_EXIT_PX, T_R, T_REASON, T_SPARE = range(8)
N_COLS = 8
R_STOP, R_TARGET, R_TIME, R_MID = range(4)

TGT_RR, TGT_MID, TGT_OPPOSITE = 0, 1, 2


@njit(cache=True)
def simulate(
    o, h, l, c, atr, rvol, hour,
    lookback,          # bars defining the liquidity pool (the range extreme)
    pierce_atr,        # how far beyond the extreme price must go, in ATR
    require_wick,      # 1 = the bar must close back inside, wick beyond
    min_range_atr,     # ignore ranges narrower than this many ATR
    stop_mode,         # 0 = beyond the sweep extreme, 1 = ATR multiple
    stop_k,
    target_mode,       # 0 = R multiple, 1 = range midpoint, 2 = opposite extreme
    rr,
    max_hold_bars,
    min_rvol,          # participation filter - the only one that has ever worked here
    hour_lo, hour_hi,
    dir_mode,
    fee_bps, slip_bps, min_risk_bps,
):
    n = o.shape[0]
    out = np.zeros((n, N_COLS), dtype=np.float64)
    k = 0
    cost = (fee_bps + slip_bps) / 10000.0

    i = lookback + 1
    while i < n - 1:
        if k >= n:
            break
        a = atr[i]
        if a <= 0.0:
            i += 1
            continue

        # the pool: extremes of the window ENDING on the previous bar
        hi = -1e18
        lo = 1e18
        for j in range(i - lookback, i):
            if h[j] > hi:
                hi = h[j]
            if l[j] < lo:
                lo = l[j]
        rng = hi - lo
        if rng < min_range_atr * a:
            i += 1
            continue

        side = 0
        swept = 0.0
        # swept the highs -> trapped longs above -> fade short
        if h[i] > hi + pierce_atr * a:
            if require_wick == 0 or c[i] < hi:
                side = -1
                swept = h[i]
        elif l[i] < lo - pierce_atr * a:
            if require_wick == 0 or c[i] > lo:
                side = 1
                swept = l[i]

        if side == 0:
            i += 1
            continue
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
                else (hh >= hour_lo or hh < hour_hi)
            if not inside:
                i += 1
                continue

        entry_i = i + 1
        entry = o[entry_i]
        if stop_mode == 0:
            # beyond the wick that did the sweeping - where the trade is wrong
            stop = swept + stop_k * a if side == -1 else swept - stop_k * a
            risk = abs(entry - stop)
        else:
            risk = stop_k * a
            stop = entry - risk if side == 1 else entry + risk
        if risk <= 0.0 or risk < entry * min_risk_bps / 10000.0:
            i += 1
            continue

        target = 0.0
        if target_mode == TGT_RR and rr > 0.0:
            target = entry + rr * risk if side == 1 else entry - rr * risk
        elif target_mode == TGT_MID:
            target = (hi + lo) * 0.5
        elif target_mode == TGT_OPPOSITE:
            target = lo if side == -1 else hi

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
            if hit_stop:
                exit_px = stop; exit_i = j; reason = R_STOP
                break
            if hit_tgt:
                exit_px = target; exit_i = j
                reason = R_TARGET if target_mode == TGT_RR else R_MID
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
        k += 1
        i = exit_i + 1

    return out[:k]
