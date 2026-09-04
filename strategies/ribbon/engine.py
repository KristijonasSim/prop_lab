"""H-016 trade engine - one numba kernel, four entry modes (A/B/C/D).

Conventions match `strategies/vwap/engine.py` so results are comparable:
  * signals are read on CLOSED bars, entries fill at the NEXT bar's open;
  * if a bar contains both the stop and the target, the STOP fills first -
    the bar hides the intrabar path and this is the pessimistic read;
  * fees and slippage are charged both sides in bps of notional;
  * R is fixed-fractional against the INITIAL stop distance, so an R multiple
    means the same thing on every trade and across every market.

The exit that matters here is the TRAILING STOP, because that is the exit Kris
reports having traded on gold. Two forms, because they are different objects
and the literature conflates them:

  TRAIL_FIXED   the stop follows the running extreme at a distance frozen at
                entry. Volatility expanding in your favour does not widen it,
                so it locks in more of a fast move.
  TRAIL_CHAND   chandelier: the distance is `k * ATR(now)`, recomputed every
                bar. Widens in a violent trend, so it holds a runner longer
                and gives back more at the turn.

A trailing stop is the one exit that cannot be tested honestly on a resting
limit, so there is no limit-fill mode here at all - every fill is a stop or
market order at a price that traded.

MINIMUM STOP DISTANCE. `min_risk_bps` floors the initial risk. Without it a
stop placed at a level price has already grazed divides by ~0 and manufactures
25R winners. This repo has hit that bug before; it is the single most common
way a trailing-stop backtest lies.
"""
from __future__ import annotations

import numpy as np
from numba import njit

T_ENTRY_I, T_EXIT_I, T_DIR, T_ENTRY_PX, T_EXIT_PX, T_R, T_REASON, T_MFE = range(8)
N_COLS = 8

R_TRAIL, R_TARGET, R_TIME, R_FLIP, R_EOD = 0, 1, 2, 3, 4

#: Entry modes - the four variations Kris asked to be tried.
MODE_AGREE, MODE_EXTREME, MODE_SQUEEZE, MODE_GATED = 0, 1, 2, 3
TRAIL_FIXED, TRAIL_CHAND = 0, 1
DIR_BOTH, DIR_LONG, DIR_SHORT = 0, 1, 2


@njit(cache=True)
def simulate(
    o, h, l, c, atr,
    agree,            # mean sign of the 20 trend scores, in [-1, +1]
    prev_agree,       # the same series one bar back, for the flip test
    nflat,            # how many of the 20 lengths have not moved a full channel
    strength,         # mean SIGNED score - magnitude, not just direction
    gate,             # external per-bar gate: +1 long-ok, -1 short-ok, 0 none,
                      # 2 = both ok. Variation D feeds the crowd read in here.
    mode,
    entry_thr,        # |agree| must reach this to enter
    require_flip,     # 1 = only on the bar agreement FIRST reaches the level
    squeeze_n,        # MODE_SQUEEZE: prior bar needed >= this many flat lengths
    min_strength,     # |strength| floor, 0 disables
    trail_mode,
    trail_k,          # trailing distance in ATR multiples
    stop_k,           # INITIAL stop in ATR multiples (0 = same as trail_k)
    trail_start_r,    # only START trailing once the trade is this many R in
                      # profit. 0 = trail from entry. These are DIFFERENT
                      # rules and traders mean both by "trailing TP": trailing
                      # from entry converts a hard stop into a moving one,
                      # while trailing from +1R leaves the initial stop alone
                      # and only protects a winner.
    rr,               # fixed target in R, 0 = none (pure trailing exit)
    max_hold_bars,    # 0 = no time stop
    flip_exit,        # 1 = also exit when agreement crosses back through zero
    dir_mode,
    side_override,    # per-bar +1/-1 forcing the trade's side; 0 = use the
                      # ribbon's own reading. This is the honest form of the
                      # direction control: entry TIMING still comes from the
                      # ribbon, but the side does not, and the exit is then
                      # simulated for real. Negating a trailing-stop trade's R
                      # would NOT be the same thing - the stop would have sat
                      # somewhere else and the trade would have ended on a
                      # different bar.
    use_side_override,
    use_gate,         # 1 = require the external gate to permit the direction
    fee_bps, slip_bps, min_risk_bps,
):
    n = o.shape[0]
    out = np.zeros((n, N_COLS), dtype=np.float64)
    k = 0
    cost = (fee_bps + slip_bps) / 10000.0
    if stop_k <= 0.0:
        stop_k = trail_k

    i = 1
    while i < n - 1:
        a = agree[i]
        pa = prev_agree[i]
        st = strength[i]
        at = atr[i]
        if np.isnan(a) or np.isnan(at) or at <= 0.0 or np.isnan(st):
            i += 1
            continue

        side = 0
        if mode == MODE_SQUEEZE:
            # The ribbon was COMPRESSED and has just fanned out. A different
            # object from plain agreement: it requires the flat state first.
            if nflat[i - 1] >= squeeze_n and a >= entry_thr:
                side = 1
            elif nflat[i - 1] >= squeeze_n and a <= -entry_thr:
                side = -1
        else:
            if a >= entry_thr and (require_flip == 0 or pa < entry_thr):
                side = 1
            elif a <= -entry_thr and (require_flip == 0 or pa > -entry_thr):
                side = -1

        if side == 0:
            i += 1
            continue
        if min_strength > 0.0 and abs(st) < min_strength:
            i += 1
            continue
        if use_side_override == 1:
            so = side_override[i]
            if so == 0.0:
                i += 1
                continue
            side = 1 if so > 0.0 else -1

        if dir_mode == DIR_LONG and side < 0:
            i += 1
            continue
        if dir_mode == DIR_SHORT and side > 0:
            i += 1
            continue
        if use_gate == 1:
            g = gate[i]
            if np.isnan(g):
                i += 1
                continue
            # 2 means "both directions permitted"; otherwise the gate must
            # name this side.
            if g != 2.0 and g != side:
                i += 1
                continue

        # ---- entry at the NEXT bar's open ----
        e = i + 1
        entry = o[e]
        if entry <= 0.0:
            i += 1
            continue

        risk = stop_k * at
        floor = entry * min_risk_bps / 10000.0
        if risk < floor:
            risk = floor
        if risk <= 0.0:
            i += 1
            continue

        if side == 1:
            stop = entry - risk
            target = entry + rr * risk if rr > 0.0 else 0.0
            extreme = entry
        else:
            stop = entry + risk
            target = entry - rr * risk if rr > 0.0 else 0.0
            extreme = entry
        # `extreme` starts at the entry price, so a trade that never goes in
        # favour can only ever be stopped at its initial stop - the trail
        # cannot tighten past it.

        exit_px = 0.0
        exit_i = -1
        reason = R_TIME
        mfe = 0.0

        j = e
        while j < n:
            hi = h[j]
            lo = l[j]

            # 1. stop first, always. The bar's path is unknown and this is the
            #    pessimistic reading.
            if side == 1 and lo <= stop:
                exit_px = stop
                exit_i = j
                reason = R_TRAIL
                break
            if side == -1 and hi >= stop:
                exit_px = stop
                exit_i = j
                reason = R_TRAIL
                break

            # 2. fixed target, if one is set
            if rr > 0.0:
                if side == 1 and hi >= target:
                    exit_px = target
                    exit_i = j
                    reason = R_TARGET
                    break
                if side == -1 and lo <= target:
                    exit_px = target
                    exit_i = j
                    reason = R_TARGET
                    break

            # 3. advance the trail on this bar's extreme
            if side == 1:
                if hi > extreme:
                    extreme = hi
                m = (extreme - entry) / risk
                if m > mfe:
                    mfe = m
                if mfe >= trail_start_r:
                    d = trail_k * at
                    if trail_mode == TRAIL_CHAND:
                        d = trail_k * atr[j]
                    if not np.isnan(d) and d > 0.0:
                        ns = extreme - d
                        if ns > stop:
                            stop = ns      # a trailing stop never retreats
            else:
                if lo < extreme:
                    extreme = lo
                m = (entry - extreme) / risk
                if m > mfe:
                    mfe = m
                if mfe >= trail_start_r:
                    d = trail_k * at
                    if trail_mode == TRAIL_CHAND:
                        d = trail_k * atr[j]
                    if not np.isnan(d) and d > 0.0:
                        ns = extreme + d
                        if ns < stop:
                            stop = ns

            # 4. ribbon flip, read on the close of this bar, filled next open
            if flip_exit == 1 and j + 1 < n:
                af = agree[j]
                if not np.isnan(af):
                    if (side == 1 and af <= 0.0) or (side == -1 and af >= 0.0):
                        exit_px = o[j + 1]
                        exit_i = j + 1
                        reason = R_FLIP
                        break

            # 5. time stop
            if max_hold_bars > 0 and (j - e) >= max_hold_bars:
                exit_px = c[j]
                exit_i = j
                reason = R_TIME
                break

            j += 1

        if exit_i < 0:
            exit_px = c[n - 1]
            exit_i = n - 1
            reason = R_EOD

        gross = (exit_px - entry) if side == 1 else (entry - exit_px)
        fees = (entry + exit_px) * cost
        r = (gross - fees) / risk

        out[k, T_ENTRY_I] = e
        out[k, T_EXIT_I] = exit_i
        out[k, T_DIR] = side
        out[k, T_ENTRY_PX] = entry
        out[k, T_EXIT_PX] = exit_px
        out[k, T_R] = r
        out[k, T_REASON] = reason
        out[k, T_MFE] = mfe
        k += 1

        # No pyramiding and no overlapping positions: resume scanning after the
        # exit. A ribbon stays green for long stretches, so without this the
        # same trend would be entered on every bar and the book would be a
        # leveraged hold, not a strategy.
        i = exit_i if exit_i > i else i + 1

    return out[:k]


def atr_wilder(h, l, c, n=14):
    """Wilder ATR, seeded from an SMA of the first `n` true ranges, as Pine does."""
    h = np.asarray(h, float); l = np.asarray(l, float); c = np.asarray(c, float)
    pc = np.empty_like(c); pc[0] = c[0]; pc[1:] = c[:-1]
    tr = np.maximum(h - l, np.maximum(np.abs(h - pc), np.abs(l - pc)))
    out = np.full(tr.size, np.nan)
    if tr.size <= n:
        return out
    prev = float(np.mean(tr[1:n + 1]))
    out[n] = prev
    a = 1.0 / n
    for i in range(n + 1, tr.size):
        prev = a * tr[i] + (1.0 - a) * prev
        out[i] = prev
    return out
