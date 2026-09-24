"""SCRIPT PORTS — one TradingView script's own entry signal, as a building block.

Added 2026-09-24. Kris sent ten scripts; the translator refused six because
the grammar had no pivots, no persistent state, no volume, no supertrend, no
recursive filters. His rule: *"that's why we have AI agent in the middle it
must think and adapt"*. So each refused script's BUY and SELL condition is
ported here as it is written, and the grammar gets one term per side:

    long when smc_long above 0.5          (the SMC Engine's own long signal)

WHAT IS PORTED AND WHAT IS NOT. The ENTRY is the script's, line for line. The
EXIT is the factory's fixed stop/target/hold, as for every idea - a script's
trailing stop or TP ladder is recorded as a simplification, never faked.

WHY THIS CANNOT SEE AHEAD. Every function walks the bars forward, or uses
backward-looking windows, so the value at bar t depends on bars 0..t only.
A pivot is reported on the bar that CONFIRMS it (L bars after the pivot), as
Pine reports it. `tests/test_factory_scripts.py` pins every port against its
guard-protected per-bar reader: same float at every sampled bar.

Each port takes `cols` (the six Window columns as arrays) and returns an array
of 1.0 / 0.0, nan during warm-up.
"""
from __future__ import annotations

import numpy as np


# ------------------------------------------------------------------ helpers
def _nan(n):
    return np.full(n, np.nan)


def rma(x, n):
    """Pine ta.rma: seeded with the SMA of the first n values."""
    out = _nan(len(x))
    if len(x) < n:
        return out
    out[n - 1] = np.mean(x[:n])
    a = 1.0 / n
    for i in range(n, len(x)):
        out[i] = a * x[i] + (1 - a) * out[i - 1]
    return out


def sma(x, n):
    out = _nan(len(x))
    if len(x) >= n:
        c = np.concatenate(([0.0], np.cumsum(x)))
        out[n - 1:] = (c[n:] - c[:-n]) / n
    return out


def rsum(x, n):
    return sma(x, n) * n


def tr(h, l, c):
    pc = np.concatenate(([np.nan], c[:-1]))
    t = np.maximum(h - l, np.maximum(np.abs(h - pc), np.abs(l - pc)))
    t[0] = h[0] - l[0]
    return t


def atr(h, l, c, n):
    """Pine ta.atr = rma of true range."""
    return rma(tr(h, l, c), n)


def rolling_max(x, n):
    out = _nan(len(x))
    for i in range(n - 1, len(x)):
        out[i] = np.max(x[i - n + 1:i + 1])
    return out


def rolling_min(x, n):
    out = _nan(len(x))
    for i in range(n - 1, len(x)):
        out[i] = np.min(x[i - n + 1:i + 1])
    return out


def pivot_high(x, left, right):
    """Pine ta.pivothigh: value at the CONFIRMING bar t = pivot bar + right."""
    out = _nan(len(x))
    for t in range(left + right, len(x)):
        c = t - right
        v = x[c]
        if v > np.max(x[c - left:c]) and v >= np.max(x[c + 1:t + 1]):
            out[t] = v
    return out


def pivot_low(x, left, right):
    out = _nan(len(x))
    for t in range(left + right, len(x)):
        c = t - right
        v = x[c]
        if v < np.min(x[c - left:c]) and v <= np.min(x[c + 1:t + 1]):
            out[t] = v
    return out


def cross_over(a, b):
    out = np.zeros(len(a), dtype=bool)
    out[1:] = (a[1:] > b[1:]) & (a[:-1] <= b[:-1])
    return out


def cross_under(a, b):
    out = np.zeros(len(a), dtype=bool)
    out[1:] = (a[1:] < b[1:]) & (a[:-1] >= b[:-1])
    return out


def bars_since(cond):
    """Pine ta.barssince: bars since cond was last true; nan if never."""
    out = _nan(len(cond))
    last = -1
    for i, v in enumerate(cond):
        if v:
            last = i
        if last >= 0:
            out[i] = i - last
    return out


def _f(b, warm):
    out = b.astype(float)
    out[:warm] = np.nan
    return out


# ------------------------------------------------------------ SMC Engine v1
def smc(cols, swing_len=10):
    o, h, l, c = cols["open"], cols["high"], cols["low"], cols["close"]
    n = len(c)
    a = atr(h, l, c, 14)
    ph, pl = pivot_high(h, swing_len, swing_len), pivot_low(l, swing_len, swing_len)
    long_s, short_s = np.zeros(n, bool), np.zeros(n, bool)
    last_sh = last_sl = np.nan
    up = True
    rh, rl = rolling_max(h, 50), rolling_min(l, 50)
    for t in range(n):
        pc = c[t - 1] if t else np.nan
        bos_bull = not np.isnan(last_sh) and c[t] > last_sh and pc <= last_sh
        bos_bear = not np.isnan(last_sl) and c[t] < last_sl and pc >= last_sl
        choch_bull = (not up) and bos_bull
        choch_bear = up and bos_bear
        if bos_bull:
            up = True
        if bos_bear:
            up = False
        if not np.isnan(ph[t]):
            last_sh = ph[t]
        if not np.isnan(pl[t]):
            last_sl = pl[t]
        if t < 3 or np.isnan(a[t]) or np.isnan(rh[t]):
            continue
        bull_fvg = h[t - 2] < l[t] and (l[t] - h[t - 2]) >= a[t] * 0.1
        bear_fvg = l[t - 2] > h[t] and (l[t - 2] - h[t]) >= a[t] * 0.1
        bull_imp = all(c[t - i] > o[t - i] for i in range(3))
        bear_imp = all(c[t - i] < o[t - i] for i in range(3))
        bull_ob = bull_imp and c[t - 3] < o[t - 3]
        bear_ob = bear_imp and c[t - 3] > o[t - 3]
        eq = (rh[t] + rl[t]) / 2
        pct = (c[t] - rl[t]) / (rh[t] - rl[t] + 0.0001) * 100
        ls = (3 if choch_bull else 0) + (c[t] < eq) + (pct < 25) + bull_fvg + bull_ob + up
        ss = (3 if choch_bear else 0) + (c[t] > eq) + (pct > 75) + bear_fvg + bear_ob + (not up)
        long_s[t], short_s[t] = ls >= 5, ss >= 5
    warm = max(2 * swing_len + 1, 50)
    return _f(long_s, warm), _f(short_s, warm)


# ------------------------------------------- Neural Edge Momentum Scalper
def neural_edge(cols, _n=0):
    h, l, c, v, hr = cols["high"], cols["low"], cols["close"], cols["volume"], cols["hour"]
    n = len(c)
    # ALMA(9, 0.85, 6)
    L, m, s = 9, 0.85 * 8, 9 / 6.0
    w = np.exp(-((np.arange(L) - m) ** 2) / (2 * s * s))
    w /= w.sum()
    alma = _nan(n)
    for t in range(L - 1, n):
        alma[t] = np.dot(w, c[t - L + 1:t + 1])
    # Supertrend(2.5, 7), Pine semantics; dir -1 = bullish
    at = atr(h, l, c, 7)
    hl2 = (h + l) / 2
    up_b, dn_b = hl2 - 2.5 * at, hl2 + 2.5 * at
    fu, fd, d = _nan(n), _nan(n), np.zeros(n)
    for t in range(n):
        if np.isnan(at[t]):
            continue
        pu = fu[t - 1] if t and not np.isnan(fu[t - 1]) else up_b[t]
        pd_ = fd[t - 1] if t and not np.isnan(fd[t - 1]) else dn_b[t]
        fu[t] = up_b[t] if (up_b[t] > pu or c[t - 1] < pu) else pu
        fd[t] = dn_b[t] if (dn_b[t] < pd_ or c[t - 1] > pd_) else pd_
        prev_d = d[t - 1] if t and d[t - 1] != 0 else 1
        if prev_d == 1:        # bearish: flips bull when close breaks the upper band
            d[t] = -1 if c[t] > pd_ else 1
        else:
            d[t] = 1 if c[t] < pu else -1
    vavg = sma(v, 20)
    surge = v >= vavg * 1.5
    rng = np.maximum(h - l, 1e-12)
    delta = rsum(v * (c - l) / rng - v * (h - c) / rng, 10)
    # ta.vwap, anchored to the UTC day (the hour column wraps at midnight)
    tp = (h + l + c) / 3
    vw = _nan(n)
    pv = vv = 0.0
    for t in range(n):
        if t and hr[t] < hr[t - 1]:
            pv = vv = 0.0
        pv += tp[t] * v[t]
        vv += v[t]
        vw[t] = pv / vv if vv > 0 else tp[t]
    rising = np.concatenate(([False], alma[1:] > alma[:-1]))
    falling = np.concatenate(([False], alma[1:] < alma[:-1]))
    tl = rising & (d < 0) & (c > alma)
    ts = falling & (d > 0) & (c < alma)
    long_s = tl & surge & (delta > 0) & (c > vw)
    short_s = ts & surge & (delta < 0) & (c < vw)
    return _f(long_s, 30), _f(short_s, 30)


# ----------------------------------- Adaptive Regression Breakout (GainzAlgo)
def arbm(cols, length=50):
    c = cols["close"]
    n = len(c)
    x = np.arange(length, dtype=float)
    xm = x.mean()
    sxx = ((x - xm) ** 2).sum()
    reg, sd = _nan(n), _nan(n)
    for t in range(length - 1, n):
        y = c[t - length + 1:t + 1]
        b = ((x - xm) * (y - y.mean())).sum() / sxx
        reg[t] = y.mean() + b * (x[-1] - xm)
        sd[t] = y.std()
    up, lo = reg + 2 * sd, reg - 2 * sd
    bw = up - lo
    mn, mx = rolling_min(bw, 100), rolling_max(bw, 100)
    pct = (bw - mn) / np.maximum(mx - mn, 1e-6) * 100
    sq = pct <= 20
    ok = ~np.isnan(pct)
    bull, bear = np.zeros(n, bool), np.zeros(n, bool)
    bull[1:] = (c[1:] > up[1:]) & (c[:-1] <= up[:-1]) & sq[:-1] & ok[:-1]
    bear[1:] = (c[1:] < lo[1:]) & (c[:-1] >= lo[:-1]) & sq[:-1] & ok[:-1]
    warm = length + 100
    return _f(bull, warm), _f(bear, warm)


# ----------------------------------------------- DeMarker Pro divergences
def demarker(cols, per=13):
    h, l = cols["high"], cols["low"]
    n = len(h)
    ph_ = np.concatenate(([np.nan], h[:-1]))
    pl_ = np.concatenate(([np.nan], l[:-1]))
    dmax = np.where(h > ph_, h - ph_, 0.0)
    dmin = np.where(l < pl_, pl_ - l, 0.0)
    ma, mi = sma(dmax, per), sma(dmin, per)
    den = ma + mi
    dm = np.where(den == 0, 0.5, ma / np.where(den == 0, 1, den))
    dm[np.isnan(ma)] = np.nan
    pH = pivot_high(np.nan_to_num(dm, nan=-1e9), 2, 1)
    pL = pivot_low(np.nan_to_num(dm, nan=1e9), 2, 1)
    bull, bear = np.zeros(n, bool), np.zeros(n, bool)
    lastH = lastHb = prevH = prevHb = None
    lastL = lastLb = prevL = prevLb = None
    for t in range(n):
        if np.isnan(dm[t]):
            continue
        if not np.isnan(pH[t]) and abs(pH[t]) < 1e8:
            prevH, prevHb = lastH, lastHb
            lastH, lastHb = pH[t], t - 1
            if prevH is not None:
                gap = lastHb - prevHb
                if 3 <= gap <= 60 and h[t - 1] > h[prevHb] and lastH < prevH:
                    bear[t] = True
        if not np.isnan(pL[t]) and abs(pL[t]) < 1e8:
            prevL, prevLb = lastL, lastLb
            lastL, lastLb = pL[t], t - 1
            if prevL is not None:
                gap = lastLb - prevLb
                if 3 <= gap <= 60 and l[t - 1] < l[prevLb] and lastL > prevL:
                    bull[t] = True
    return _f(bull, per + 4), _f(bear, per + 4)


# ----------------------------------- Auto-ATR Volatility Spike (BigBeluga)
def atr_spike(cols, _n=0):
    o, h, l, c = cols["open"], cols["high"], cols["low"], cols["close"]
    n = len(c)
    a = atr(h, l, c, 14)
    body = np.abs(c - o)
    up_s, dn_s = np.zeros(n, bool), np.zeros(n, bool)
    state, trail = 0, np.nan
    for t in range(n):
        if np.isnan(a[t]):
            continue
        big_up = body[t] > a[t] * 2 and c[t] > o[t]
        big_dn = body[t] > a[t] * 2 and c[t] < o[t]
        up_s[t] = big_up and state != 1
        dn_s[t] = big_dn and state != -1
        if up_s[t] and state <= 0:
            state, trail = 1, l[t] - a[t] * 3
        if dn_s[t] and state >= 0:
            state, trail = -1, h[t] + a[t] * 3
        if state == 1:
            trail = max(trail, l[t] - a[t] * 3)
            if c[t] < trail:
                state, trail = 0, np.nan
        elif state == -1:
            trail = min(trail, h[t] + a[t] * 3)
            if c[t] > trail:
                state, trail = 0, np.nan
    return _f(up_s, 15), _f(dn_s, 15)


# ------------------------------------------------------ Boom Hunter Pro
def boom_hunter(cols, _n=0):
    c = cols["close"]
    n = len(c)
    pi = 2 * np.arcsin(1)
    a1_ = (np.cos(.707 * 2 * pi / 100) + np.sin(.707 * 2 * pi / 100) - 1) / np.cos(.707 * 2 * pi / 100)
    HP = np.zeros(n)
    for t in range(n):
        c1 = c[t - 1] if t >= 1 else 0.0
        c2 = c[t - 2] if t >= 2 else 0.0
        h1 = HP[t - 1] if t >= 1 else 0.0
        h2 = HP[t - 2] if t >= 2 else 0.0
        HP[t] = (1 - a1_ / 2) ** 2 * (c[t] - 2 * c1 + c2) + 2 * (1 - a1_) * h1 - (1 - a1_) ** 2 * h2

    def eot(lp, k):
        a = np.exp(-1.414 * pi / lp)
        cc2 = 2 * a * np.cos(1.414 * pi / lp)
        cc3 = -a * a
        cc1 = 1 - cc2 - cc3
        F, P, X = np.zeros(n), np.zeros(n), np.zeros(n)
        for t in range(n):
            hp1 = HP[t - 1] if t >= 1 else 0.0
            f1 = F[t - 1] if t >= 1 else 0.0
            f2 = F[t - 2] if t >= 2 else 0.0
            F[t] = cc1 * (HP[t] + hp1) / 2 + cc2 * f1 + cc3 * f2
            P[t] = .991 * (P[t - 1] if t >= 1 else 0.0)
            if abs(F[t]) > P[t]:
                P[t] = abs(F[t])
            X[t] = F[t] / P[t] if P[t] != 0 else 0.0
        return [(X + kk) / (kk * X + 1) for kk in k]

    Q1, _Q2 = eot(6, (0.0, 0.3))
    Q3, _Q4 = eot(27, (0.8, 0.3))
    q1 = Q1 * 60 + 50
    trig = sma(q1, 2)
    xo = cross_over(q1, trig)
    xu = cross_under(q1, trig)
    const = lambda v: np.full(n, float(v))
    warn2 = cross_over(Q1, const(-0.9))
    warn3 = cross_under(Q1, const(0.9))
    bs_w2, bs_w3 = bars_since(warn2), bars_since(warn3)
    bs_x20, bs_x80 = bars_since(cross_over(q1, const(20))), bars_since(cross_over(q1, const(80)))
    bs_5 = bars_since((q1 <= 0) & xu)
    bs_6 = bars_since((q1 <= 20) & xu)
    le = lambda a, k: np.nan_to_num(a, nan=1e9) <= k
    enter3 = (Q3 <= -0.9) & xo & le(bs_w2, 7) & (q1 <= 20) & le(bs_x20, 21)
    enter5 = le(bs_5, 5) & xo
    enter6 = le(bs_6, 11) & xo
    enter7 = (Q3 <= -0.9) & xo
    senter3 = (Q3 >= -0.9) & xu & le(bs_w3, 7) & (q1 >= 99) & le(bs_x80, 21)
    long_s = enter3 | enter5 | enter6 | enter7
    return _f(long_s, 200), _f(senter3, 200)


# ------------------------------------------ Accurate Swing Trading System
def accurate_swing(cols, no=3):
    h, l, c = cols["high"], cols["low"], cols["close"]
    n = len(c)
    res, sup = rolling_max(h, no), rolling_min(l, no)
    tsl = _nan(n)
    avn = 0
    for t in range(1, n):
        if np.isnan(res[t - 1]):
            continue
        avd = 1 if c[t] > res[t - 1] else (-1 if c[t] < sup[t - 1] else 0)
        if avd != 0:
            avn = avd
        tsl[t] = sup[t] if avn == 1 else res[t]
    buy, sell = cross_over(c, tsl), cross_under(c, tsl)
    return _f(buy, no + 2), _f(sell, no + 2)


#: kind -> (port, which side of its output). Registered into spec.INDICATORS.
PORTS = {
    "smc_long": (smc, 0), "smc_short": (smc, 1),
    "neural_long": (neural_edge, 0), "neural_short": (neural_edge, 1),
    "arbm_long": (arbm, 0), "arbm_short": (arbm, 1),
    "dem_bull": (demarker, 0), "dem_bear": (demarker, 1),
    "spike_up": (atr_spike, 0), "spike_down": (atr_spike, 1),
    "boom_long": (boom_hunter, 0), "boom_short": (boom_hunter, 1),
    "swing_buy": (accurate_swing, 0), "swing_sell": (accurate_swing, 1),
}
