"""VWAP model families — one numba kernel, five entry modes.

Conventions match strategies/orb/engine.py so results are comparable:
* signals are computed on CLOSED bars only, entries fill on the next bar;
* if a bar contains both the stop and the target, the STOP is assumed to fill
  first — 15m bars hide the intrabar path and this is the pessimistic read;
* fees and slippage are charged both sides in bps of notional;
* risk is fixed-fractional, so an R multiple means the same thing every trade.

The one thing that needs care here is FILL REALISM on the band families. A
resting limit at the band is the natural way to trade a fade, and it is exactly
how the previous repo produced a strategy that backtested at PF 3.0 and traded
live at 0.7 — a wick touch is not a fill unless you were at the front of the
queue. So `fill_mode` runs the same rules two ways: a limit fill at the band
(optimistic, unverifiable) or a close beyond the band with entry at the next
open (honest). The gap between them is the finding.
"""

from __future__ import annotations

import numpy as np
from numba import njit

T_ENTRY_I, T_EXIT_I, T_DIR, T_ENTRY_PX, T_EXIT_PX, T_R, T_REASON, T_SESS = range(8)
N_COLS = 8

R_STOP, R_TARGET, R_TIME, R_FLIP, R_VWAP = 0, 1, 2, 3, 4

MODE_TREND, MODE_FADE, MODE_BREAK, MODE_RECLAIM, MODE_PULLBACK = 0, 1, 2, 3, 4
FILL_LIMIT, FILL_CLOSE = 0, 1
TGT_SESSION, TGT_VWAP, TGT_OPPOSITE, TGT_RR = 0, 1, 2, 3


@njit(cache=True)
def simulate(
    o, h, l, c, atr, vwap, vwstd, rvol, atr_rank,
    sess_start,          # bar index where each session begins
    mode,
    fill_mode,
    band_k,              # entry band, in volume-weighted sigmas
    stop_mode,           # 0 = k_stop sigmas beyond entry, 1 = ATR multiple
    stop_k,              # sigmas or ATR multiples, depending on stop_mode
    target_mode,
    rr,
    max_hold_bars,       # 0 = hold to the session horizon
    warmup_bars,         # skip the first N bars of a session: VWAP is meaningless
                         # until enough volume has accumulated behind it
    one_trade,
    min_rvol,
    min_atr_rank,
    max_atr_rank,
    dir_mode,            # 0 both, 1 long only, 2 short only
    ema,                 # EMA of close, for the regime filter below
    ema_regime,          # 0 off; 1 = only trade with EMA on the same side of
                         # VWAP as the trade; 2 = only against it.
                         # This is H-003's mechanic used the way the literature
                         # actually uses it - as confirmation, not as a trigger.
                         # H-003 tested only the trigger form and it failed.
    hour,                # UTC hour of each bar
    hour_lo, hour_hi,    # trade only inside [lo, hi). lo == hi disables it.
                         # H-001 established the NY cash open as the only anchor
                         # that carries anything and Asia as the worst region;
                         # this is the axis that tests whether that transfers.
    fee_bps,
    slip_bps,
    min_risk_bps,
):
    n = o.shape[0]
    n_sess = sess_start.shape[0]
    # One trade per bar is the hard ceiling: `i` always advances past the exit.
    # Sizing this by session count segfaulted - stop-and-reverse can flip far
    # more than a handful of times in one session.
    out = np.zeros((n, N_COLS), dtype=np.float64)
    k = 0
    cost = (fee_bps + slip_bps) / 10000.0

    for s in range(n_sess):
        start = sess_start[s]
        stop_bar = n - 1 if s + 1 >= n_sess else sess_start[s + 1]
        if stop_bar > n - 1:
            stop_bar = n - 1
        begin = start + warmup_bars
        if begin >= stop_bar:
            continue

        taken = 0
        i = begin
        prev_side = 0
        # Running flags for MODE_RECLAIM. Rescanning the session on every bar
        # made this O(bars^2) and dominated the whole sweep; carrying the state
        # forward is the same logic at O(bars).
        stretched_up = 0
        stretched_dn = 0

        while i < stop_bar:
            if one_trade == 1 and taken == 1:
                break
            if k >= n:
                break

            v = vwap[i]
            sd = vwstd[i]
            if v <= 0.0 or sd <= 0.0:
                i += 1
                continue

            upper = v + band_k * sd
            lower = v - band_k * sd

            if h[i] >= upper:
                stretched_up = 1
            if l[i] <= lower:
                stretched_dn = 1

            side = 0
            entry = 0.0
            entry_i = i

            # ---------------- entry rules ----------------
            if mode == MODE_TREND:
                # long above VWAP, short below, evaluated on the closed bar
                want = 1 if c[i] > v else (-1 if c[i] < v else 0)
                if want != 0 and want != prev_side and i + 1 < stop_bar:
                    side = want
                    entry = o[i + 1]
                    entry_i = i + 1

            elif mode == MODE_FADE:
                if fill_mode == FILL_LIMIT:
                    # Resting limit AT the band. The band level is computed on
                    # CLOSED bar i, so the order can only work during bar i+1 -
                    # it fills if THAT bar reaches it, never bar i.
                    #
                    # This used to read h[i]/l[i] and leave entry_i at i, which
                    # booked the fill on the same bar whose extreme decided it
                    # and then ran the stop/target scan over that same bar: a
                    # same-bar look-ahead that let a trade enter at a price only
                    # knowable once the bar had closed. It inflated exactly the
                    # short-hold configs (PF 27-95, Sharpe 15, max drawdown
                    # 1.17R over 1,660 trades - not believable numbers).
                    # No board result was affected: every fold config on the
                    # board is fill_mode=1. Fixed 2026-09-05.
                    if i + 1 < stop_bar:
                        if h[i + 1] >= upper:
                            side = -1
                            # a gap through the limit fills at the open, which
                            # for a resting sell is a better price, not worse
                            entry = upper if o[i + 1] < upper else o[i + 1]
                            entry_i = i + 1
                        elif l[i + 1] <= lower:
                            side = 1
                            entry = lower if o[i + 1] > lower else o[i + 1]
                            entry_i = i + 1
                else:
                    if c[i] > upper and i + 1 < stop_bar:
                        side = -1
                        entry = o[i + 1]
                        entry_i = i + 1
                    elif c[i] < lower and i + 1 < stop_bar:
                        side = 1
                        entry = o[i + 1]
                        entry_i = i + 1

            elif mode == MODE_BREAK:
                if fill_mode == FILL_LIMIT:
                    # A breakout entry is a STOP order above the market, not a
                    # resting limit - it has to cross the spread, so this mode
                    # can never be a maker fill. It is kept as the falsification
                    # control for stage 13 and carries the same i+1 correction:
                    # the level comes off closed bar i, the order works bar i+1.
                    if i + 1 < stop_bar:
                        if h[i + 1] >= upper:
                            side = 1
                            # gapping through a buy stop fills WORSE, at the open
                            entry = upper if o[i + 1] < upper else o[i + 1]
                            entry_i = i + 1
                        elif l[i + 1] <= lower:
                            side = -1
                            entry = lower if o[i + 1] > lower else o[i + 1]
                            entry_i = i + 1
                else:
                    if c[i] > upper and i + 1 < stop_bar:
                        side = 1
                        entry = o[i + 1]
                        entry_i = i + 1
                    elif c[i] < lower and i + 1 < stop_bar:
                        side = -1
                        entry = o[i + 1]
                        entry_i = i + 1

            elif mode == MODE_RECLAIM:
                # was beyond a band earlier in the session, now closes back through VWAP
                if i > begin and i + 1 < stop_bar:
                    if stretched_up == 1 and c[i] < v and c[i - 1] >= vwap[i - 1]:
                        side = -1
                        entry = o[i + 1]
                        entry_i = i + 1
                    elif stretched_dn == 1 and c[i] > v and c[i - 1] <= vwap[i - 1]:
                        side = 1
                        entry = o[i + 1]
                        entry_i = i + 1

            elif mode == MODE_PULLBACK:
                # session is trending away from VWAP; take the first touch back to it
                if i > begin and i + 1 < stop_bar:
                    if c[i - 1] > vwap[i - 1] and l[i] <= v and c[i] > v:
                        side = 1
                        entry = o[i + 1]
                        entry_i = i + 1
                    elif c[i - 1] < vwap[i - 1] and h[i] >= v and c[i] < v:
                        side = -1
                        entry = o[i + 1]
                        entry_i = i + 1

            if side == 0:
                i += 1
                continue
            if dir_mode == 1 and side != 1:
                i += 1
                continue
            if dir_mode == 2 and side != -1:
                i += 1
                continue

            # ---------------- filters ----------------
            # READ AT `i`, NOT `entry_i`. The decision is made at the close of
            # bar i and the order fills at the open of bar i+1, so a filter is
            # only allowed to see bar i. Reading rvol/atr/ema at entry_i asked
            # the entry bar's own completed volume, range and close - none of
            # which exist when the order is placed. On the board's most-selected
            # BTCUSDT 4h config that inflated PF at 2x cost from 0.627 to 2.765
            # under rvol>2.5, and it manufactured the monotone "participation
            # lifts it" pattern in CLAUDE.md: a tighter threshold selects harder
            # for bars that turned out to be busy, and busy bars are the ones
            # that moved. `atr_rank` was already correct - it is built with an
            # explicit .shift(1) - and is left as it was. Fixed 2026-09-05.
            if ema_regime != 0:
                e = ema[i]
                if e <= 0.0:
                    i += 1
                    continue
                with_trend = (e > v) if side == 1 else (e < v)
                if ema_regime == 1 and not with_trend:
                    i += 1
                    continue
                if ema_regime == 2 and with_trend:
                    i += 1
                    continue
            if hour_lo != hour_hi:
                hh = hour[entry_i]
                inside = (hour_lo <= hh < hour_hi) if hour_lo < hour_hi \
                    else (hh >= hour_lo or hh < hour_hi)      # window wraps midnight
                if not inside:
                    i += 1
                    continue
            if min_rvol > 0.0 and rvol[i] < min_rvol:
                i += 1
                continue
            ar = atr_rank[entry_i]      # already .shift(1)ed at construction
            if min_atr_rank > 0.0 and ar < min_atr_rank:
                i += 1
                continue
            if max_atr_rank > 0.0 and ar > max_atr_rank:
                i += 1
                continue

            # ---------------- stop ----------------
            if stop_mode == 0:
                d = stop_k * sd
            else:
                a = atr[i]              # the stop is sized when the order is placed
                d = stop_k * (a if a > 0.0 else sd)
            stop = entry - d if side == 1 else entry + d
            risk = d
            if risk <= 0.0 or risk < entry * min_risk_bps / 10000.0:
                i += 1
                continue

            # ---------------- target ----------------
            target = 0.0
            has_target = 0
            if target_mode == TGT_RR and rr > 0.0:
                target = entry + rr * risk if side == 1 else entry - rr * risk
                has_target = 1
            elif target_mode == TGT_OPPOSITE:
                target = lower if side == -1 else upper
                has_target = 1

            horizon = stop_bar
            if max_hold_bars > 0 and entry_i + max_hold_bars < stop_bar:
                horizon = entry_i + max_hold_bars

            # ---------------- walk to the exit ----------------
            exit_px = 0.0
            exit_i = entry_i
            reason = R_TIME
            j = entry_i
            while j < horizon:
                if side == 1:
                    hit_stop = l[j] <= stop
                    hit_tgt = has_target == 1 and h[j] >= target
                    hit_vwap = target_mode == TGT_VWAP and h[j] >= vwap[j]
                    flip = mode == MODE_TREND and c[j] < vwap[j]
                else:
                    hit_stop = h[j] >= stop
                    hit_tgt = has_target == 1 and l[j] <= target
                    hit_vwap = target_mode == TGT_VWAP and l[j] <= vwap[j]
                    flip = mode == MODE_TREND and c[j] > vwap[j]

                if hit_stop:                      # stop wins ties - pessimistic
                    exit_px = stop
                    exit_i = j
                    reason = R_STOP
                    break
                if hit_tgt:
                    exit_px = target
                    exit_i = j
                    reason = R_TARGET
                    break
                if hit_vwap and j > entry_i:
                    exit_px = vwap[j]
                    exit_i = j
                    reason = R_VWAP
                    break
                if flip and j > entry_i:
                    exit_px = c[j]
                    exit_i = j
                    reason = R_FLIP
                    break
                j += 1
            if reason == R_TIME:
                exit_i = horizon - 1 if j >= horizon else j
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
            prev_side = side
            i = exit_i + 1

    return out[:k]
