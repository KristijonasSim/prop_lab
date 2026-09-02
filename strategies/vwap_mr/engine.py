"""H-010 VWAP band rejection — one numba kernel.

The idea comes from a published TradingView indicator: anchored VWAP with three
standard-deviation bands, and a signal when a bar touches a band and then closes
back against the move, confirmed by volume delta. The indicator draws arrows and
stops there. This turns it into something that can be priced, and changes four
things on purpose.

WHAT IS DIFFERENT FROM THE INDICATOR, and why each change is not cosmetic:

1. **Honest fills.** Entry is at the NEXT BAR'S OPEN after a closed rejection
   bar. Never a resting limit at the band. The prior repo's `VWAP std-band fade`
   backtested at profit factor 3.0 and traded at 0.7, and the cause was a
   backtest that filled a resting limit on any wick touch. This family is the
   one that burned them, so it is rebuilt with market fills only.

2. **Real signed flow.** The indicator estimates delta as `volume * sign(close -
   open)`, which is a guess about a bar it can already see. Binance publishes
   `taker_buy_base_asset_volume` on every kline, so the true taker buy/sell
   split is known and is used instead.

3. **Exits.** The indicator has none, which means it has no result. Three are
   tested - revert to the VWAP, a fixed R multiple, or time - always with a stop
   beyond the band, so R is bounded and a drawdown in R means something.

4. **The crowd gate**, optional, from this repo's own H-009 finding: take the
   trade only when the long/short account ratio is on the other side of it.

INTRABAR ORDERING. When a bar could have hit both the stop and the target, the
STOP is taken. That is the conservative assumption and it is the same one the
rest of this repo makes.
"""

from __future__ import annotations

import numpy as np
from numba import njit

T_ENTRY_I, T_EXIT_I, T_DIR, T_ENTRY_PX, T_EXIT_PX, T_R, T_REASON, T_LEVEL, T_RISK = range(9)
N_COLS = 9

R_STOP, R_TARGET, R_TIME, R_ANCHOR = 0, 1, 2, 3
TGT_VWAP, TGT_RR, TGT_TIME = 0, 1, 2


@njit(cache=True)
def simulate(o, h, l, c, vwap, sd, atr, cvd, crowd, anchor_new,
             sd1, sd2, sd3,
             entry_level,      # 1, 2 or 3: the shallowest band that may signal
             allow_vwap,       # also signal on a touch of the VWAP itself
             flow_mode,        # 0 off, 1 delta must agree
             flow_thr,         # delta share, -1..1
             crowd_mode,       # 0 off, 1 require the crowd on the other side
             range_mult,       # 0 off; bar range must be >= mult x ATR
             clean,            # escalation and neutral-zone state machine
             cooldown,
             revert,           # 1 fade the move back to the VWAP, 0 go with it
             stop_k,           # stop this many sigmas beyond the entry band
             target_mode, rr, max_hold, exit_on_anchor,
             fee_bps, slip_bps, min_risk_bps):

    n = len(o)
    out = np.zeros((n, N_COLS), dtype=np.float64)
    k = 0
    cost = (fee_bps + slip_bps) * 2.0 / 1e4

    last_sig = -10 ** 9
    last_dir = 0
    last_lvl = 0
    neutral = True
    i = 1
    while i < n - 1:
        if not (sd[i] > 0.0) or not (vwap[i] > 0.0):
            i += 1
            continue

        u1 = vwap[i] + sd1 * sd[i]
        u2 = vwap[i] + sd2 * sd[i]
        u3 = vwap[i] + sd3 * sd[i]
        d1 = vwap[i] - sd1 * sd[i]
        d2 = vwap[i] - sd2 * sd[i]
        d3 = vwap[i] - sd3 * sd[i]

        # how deep the bar reached, 0 = no band touched
        up_lvl = 3 if h[i] >= u3 else (2 if h[i] >= u2 else (1 if h[i] >= u1 else 0))
        dn_lvl = 3 if l[i] <= d3 else (2 if l[i] <= d2 else (1 if l[i] <= d1 else 0))
        vw_touch = (l[i] <= vwap[i]) and (h[i] >= vwap[i])

        # the neutral zone is inside the first band; reaching it re-arms the
        # state machine, which is what stops a run of signals down one leg
        if (l[i] <= u1) and (h[i] >= d1):
            neutral = True

        if i - last_sig < cooldown:
            i += 1
            continue

        rng_ok = True
        if range_mult > 0.0:
            rng_ok = (h[i] - l[i]) >= range_mult * atr[i]
        if not rng_ok:
            i += 1
            continue

        # a rejection is a bar that reached out and closed back the other way
        long_touch = (dn_lvl >= entry_level) or (allow_vwap == 1 and vw_touch)
        short_touch = (up_lvl >= entry_level) or (allow_vwap == 1 and vw_touch)
        long_sig = (c[i] > o[i]) and long_touch
        short_sig = (c[i] < o[i]) and short_touch

        if flow_mode == 1:
            long_sig = long_sig and (cvd[i] > flow_thr)
            short_sig = short_sig and (cvd[i] < -flow_thr)
        if crowd_mode == 1:
            # H-009: only when retail is positioned the other way
            long_sig = long_sig and (crowd[i] <= 0.0)
            short_sig = short_sig and (crowd[i] >= 0.0)

        if clean == 1:
            lvl_l = dn_lvl if dn_lvl > 0 else 0
            lvl_s = up_lvl if up_lvl > 0 else 0
            if last_dir == 1 and not neutral and lvl_l <= last_lvl:
                long_sig = False
            if last_dir == -1 and not neutral and lvl_s <= last_lvl:
                short_sig = False

        if not (long_sig or short_sig):
            i += 1
            continue

        side = 1 if long_sig else -1
        lvl = dn_lvl if side == 1 else up_lvl
        # THE CONTROL. The same setups, taken the other way. If continuation
        # pays where reversion does not, that is a result about this family and
        # not a failure to find a parameter - and it would agree with H-002,
        # whose own blind fold choices land on trend and break, never on fade.
        if revert == 0:
            side = -side
        entry = o[i + 1]
        if not (entry > 0.0):
            i += 1
            continue

        # A mean-reversion trade needs somewhere to revert TO. If the rejection
        # bar has already closed back through the VWAP, a long entered above it
        # has no room and its "target" sits BEHIND the entry - which is how the
        # first run of this booked 2,096 target hits and still averaged -0.8R.
        if target_mode == TGT_VWAP and revert == 1:
            if side == 1 and entry >= vwap[i]:
                i += 1
                continue
            if side == -1 and entry <= vwap[i]:
                i += 1
                continue

        stop = entry - side * stop_k * sd[i]
        risk = abs(entry - stop)
        if risk < entry * min_risk_bps / 1e4:
            i += 1
            continue

        exit_px = 0.0
        exit_i = i + 1
        reason = R_TIME
        j = i + 1
        held = 0
        while j < n:
            held += 1
            # stop first: when a bar could have done both, assume the worse
            if side == 1 and l[j] <= stop:
                exit_px = stop; exit_i = j; reason = R_STOP; break
            if side == -1 and h[j] >= stop:
                exit_px = stop; exit_i = j; reason = R_STOP; break

            if target_mode == TGT_VWAP:
                # the VWAP moves while the trade is open, so the target is only
                # a target while it is still on the profitable side of the entry
                if side == 1 and vwap[j] > entry and h[j] >= vwap[j]:
                    exit_px = vwap[j]; exit_i = j; reason = R_TARGET; break
                if side == -1 and vwap[j] < entry and l[j] <= vwap[j]:
                    exit_px = vwap[j]; exit_i = j; reason = R_TARGET; break
            elif target_mode == TGT_RR and rr > 0.0:
                tgt = entry + side * rr * risk
                if side == 1 and h[j] >= tgt:
                    exit_px = tgt; exit_i = j; reason = R_TARGET; break
                if side == -1 and l[j] <= tgt:
                    exit_px = tgt; exit_i = j; reason = R_TARGET; break

            if exit_on_anchor == 1 and anchor_new[j] == 1:
                exit_px = c[j]; exit_i = j; reason = R_ANCHOR; break
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
        out[k, T_LEVEL] = lvl
        # the risk in PRICE, so a different cost assumption can be repriced
        # exactly rather than reverse-engineered from the R multiple
        out[k, T_RISK] = risk
        k += 1

        last_sig = i
        last_dir = side
        last_lvl = lvl
        neutral = False
        i = exit_i               # flat before the next signal
    return out[:k]
