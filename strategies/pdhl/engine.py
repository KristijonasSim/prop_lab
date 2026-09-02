"""H-011 previous-day high/low reversal — one numba kernel.

Entry: a bar takes out the previous day's high (or low) by at least `min_pen`
ATR and closes back inside it. That is a sweep. The trade is taken against the
sweep, with the stop beyond the wick that made it - which is the only stop
placement that makes sense here, because the wick IS the event.

The sweep depth is bounded at both ends on purpose. Too shallow and nothing was
taken out; too deep and it is not a sweep at all, it is a breakout that kept
going, and fading it is the trade that killed the whole breakout-fade family.
`max_pen` is what separates the two, and it is swept rather than assumed.

CONFIRMATIONS, each optional so the grid can say whether it earns its place:
  oi_mode    open interest must have FALLEN across the sweep - contracts closed,
             which is stops being run rather than new positions being opened
  flow_mode  taker aggression must agree with the fade
  crowd_mode the H-009 gate: the crowd must be on the other side

INTRABAR ORDERING: when a bar could have hit both the stop and the target, the
stop is taken. Fills are the next bar's OPEN, never a resting order at the
level - that assumption is what made the prior repo's band fade backtest 3.0 and
trade 0.7.
"""
from __future__ import annotations

import numpy as np
from numba import njit

T_ENTRY_I, T_EXIT_I, T_DIR, T_ENTRY_PX, T_EXIT_PX, T_R, T_REASON, T_RISK = range(8)
N_COLS = 8
R_STOP, R_TARGET, R_TIME = 0, 1, 2
TGT_MID, TGT_RR, TGT_TIME, TGT_OPPOSITE = 0, 1, 2, 3


@njit(cache=True)
def simulate(o, h, l, c, atr, hi_lvl, lo_lvl, mid, opp_hi, opp_lo,
             doi, cvd, crowd, day_i,
             min_pen, max_pen, close_frac,
             oi_mode, oi_thr, flow_mode, crowd_mode,
             once_per_day, revert,
             stop_buf, target_mode, rr, max_hold,
             fee_bps, slip_bps, min_risk_bps):

    n = len(o)
    out = np.zeros((n, N_COLS), dtype=np.float64)
    k = 0
    cost = (fee_bps + slip_bps) * 2.0 / 1e4
    last_day_hi = -1
    last_day_lo = -1

    i = 2
    while i < n - 1:
        a = atr[i]
        if not (a > 0.0):
            i += 1
            continue
        rng = h[i] - l[i]
        if not (rng > 0.0):
            i += 1
            continue

        side = 0
        lvl = 0.0
        swept_px = 0.0

        # --- the previous day's HIGH was taken and given back -> fade short ---
        H = hi_lvl[i]
        if H == H and h[i] >= H + min_pen * a and c[i] < H:
            if max_pen <= 0.0 or h[i] <= H + max_pen * a:
                # the close has to sit in the lower part of the bar: a bar that
                # pokes through and closes on its high is not a rejection
                if (c[i] - l[i]) / rng <= close_frac:
                    if not (once_per_day == 1 and last_day_hi == day_i[i]):
                        side = -1
                        lvl = H
                        swept_px = h[i]

        # --- the previous day's LOW was taken and given back -> fade long ---
        if side == 0:
            L = lo_lvl[i]
            if L == L and l[i] <= L - min_pen * a and c[i] > L:
                if max_pen <= 0.0 or l[i] >= L - max_pen * a:
                    if (h[i] - c[i]) / rng <= close_frac:
                        if not (once_per_day == 1 and last_day_lo == day_i[i]):
                            side = 1
                            lvl = L
                            swept_px = l[i]

        if side == 0:
            i += 1
            continue

        # --- the confirmations -------------------------------------------
        if oi_mode == 1:
            d = doi[i]
            if not (d == d and d <= oi_thr):     # contracts must have CLOSED
                i += 1
                continue
        if flow_mode == 1:
            f = cvd[i]
            if not (f == f):
                i += 1
                continue
            if side == 1 and f <= 0.0:
                i += 1
                continue
            if side == -1 and f >= 0.0:
                i += 1
                continue
        if crowd_mode == 1:
            g = crowd[i]
            if not (g == g):
                i += 1
                continue
            if side == 1 and g > 0.0:
                i += 1
                continue
            if side == -1 and g < 0.0:
                i += 1
                continue

        if revert == 0:
            side = -side                          # the control

        entry = o[i + 1]
        if not (entry > 0.0):
            i += 1
            continue

        # The stop sits beyond the wick that made the sweep, plus a buffer: the
        # wick IS the event, so a trade against it is wrong the moment the wick
        # is exceeded. The risk is measured from that placement and then applied
        # to whichever side is being taken, so the control risks exactly what
        # the hypothesis risks and the two are comparable.
        if revert == 1:
            fade_side = side
        else:
            fade_side = -side
        wick_stop = swept_px - fade_side * stop_buf * a
        risk = abs(entry - wick_stop)
        stop = entry - side * risk
        if risk < entry * min_risk_bps / 1e4:
            i += 1
            continue

        if side == -1:
            last_day_hi = day_i[i]
        else:
            last_day_lo = day_i[i]

        exit_px = 0.0
        exit_i = i + 1
        reason = R_TIME
        j = i + 1
        held = 0
        while j < n:
            held += 1
            if side == 1 and l[j] <= stop:
                exit_px = stop; exit_i = j; reason = R_STOP; break
            if side == -1 and h[j] >= stop:
                exit_px = stop; exit_i = j; reason = R_STOP; break

            if target_mode == TGT_MID:
                t = mid[j]
                if t == t:
                    if side == 1 and t > entry and h[j] >= t:
                        exit_px = t; exit_i = j; reason = R_TARGET; break
                    if side == -1 and t < entry and l[j] <= t:
                        exit_px = t; exit_i = j; reason = R_TARGET; break
            elif target_mode == TGT_OPPOSITE:
                t = opp_lo[j] if side == -1 else opp_hi[j]
                if t == t:
                    if side == 1 and t > entry and h[j] >= t:
                        exit_px = t; exit_i = j; reason = R_TARGET; break
                    if side == -1 and t < entry and l[j] <= t:
                        exit_px = t; exit_i = j; reason = R_TARGET; break
            elif target_mode == TGT_RR and rr > 0.0:
                t = entry + side * rr * risk
                if side == 1 and h[j] >= t:
                    exit_px = t; exit_i = j; reason = R_TARGET; break
                if side == -1 and l[j] <= t:
                    exit_px = t; exit_i = j; reason = R_TARGET; break

            if max_hold > 0 and held >= max_hold:
                exit_px = c[j]; exit_i = j; reason = R_TIME; break
            j += 1
        if exit_px <= 0.0:
            break

        gross = side * (exit_px - entry) - entry * cost
        out[k, T_ENTRY_I] = i + 1
        out[k, T_EXIT_I] = exit_i
        out[k, T_DIR] = side
        out[k, T_ENTRY_PX] = entry
        out[k, T_EXIT_PX] = exit_px
        out[k, T_R] = gross / risk
        out[k, T_REASON] = reason
        out[k, T_RISK] = risk
        k += 1
        i = exit_i
    return out[:k]
