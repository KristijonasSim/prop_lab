"""GRAMMAR TERMS ADDED 2026-10-06 — the features refused scripts asked for.

Kris: *"i want to take care of all this back log ... we need to finish it"*,
on 165 TradingView scripts the translator refused as "grammar gap". Counted
over those refusals, the missing pieces were, most common first: a Supertrend
or ATR trailing line (~20), session/clock ranges (~20), pivots (~15),
Bollinger/Keltner bands - which need arithmetic the grammar lacks (~12),
candle shapes and previous-bar values (~12), ADX/DMI (~11), MACD (~9),
stochastic and stoch-RSI (~6), relative volume, MA slope, Hull MA.

What is NOT here and stays refused: other symbols and other timeframes
(`request.security`), machine-learning models, grid ladders, and scripts that
are a multi-bar state machine with no single trigger. Those need a port in
`factory/scripts.py`, written by hand, one script at a time.

EACH TERM IS A WHOLE-SERIES FUNCTION `fn(cols, n, mult) -> array`, walked
forward over bars 0..t only, so the value at t never depends on a later bar.
`spec.py` registers it twice: in `SERIES` for speed and as a per-bar reader
that runs the same function on the guarded history and takes the last value.
`tests/test_factory_terms.py` pins the two equal at sampled bars - the same
check every script port carries.

`mult` is a band width or a Supertrend factor, carried in `Term.value`, and
only the kinds in `MULT` read it. Pine's own defaults are used when it is 0.
"""
from __future__ import annotations

import numpy as np

from factory.scripts import (_nan, atr, pivot_high, pivot_low, rma,
                             rolling_max, rolling_min, sma)


def _ema(x, n):
    """Pine ta.ema: seeded with the SMA of the first n values."""
    out = _nan(len(x))
    if len(x) < n:
        return out
    out[n - 1] = np.mean(x[:n])
    a = 2.0 / (n + 1.0)
    for i in range(n, len(x)):
        out[i] = a * x[i] + (1 - a) * out[i - 1]
    return out


def _ema_nan(x, n):
    """EMA of a series that starts with nans (an indicator of an indicator)."""
    out = _nan(len(x))
    ok = np.flatnonzero(~np.isnan(x))
    if len(ok):
        out[ok[0]:] = _ema(x[ok[0]:], n)
    return out


def _sma_nan(x, n):
    out = _nan(len(x))
    ok = np.flatnonzero(~np.isnan(x))
    if len(ok):
        out[ok[0]:] = sma(x[ok[0]:], n)
    return out


def _stdev(x, n):
    """Pine ta.stdev: population standard deviation."""
    out = _nan(len(x))
    for i in range(n - 1, len(x)):
        out[i] = np.std(x[i - n + 1:i + 1])
    return out


def _wma(x, n):
    out = _nan(len(x))
    w = np.arange(1, n + 1, dtype=float)
    for i in range(n - 1, len(x)):
        seg = x[i - n + 1:i + 1]
        out[i] = np.nan if np.isnan(seg).any() else float(seg @ w / w.sum())
    return out


def _shift(x, k=1):
    out = _nan(len(x))
    out[k:] = x[:-k]
    return out


def _hlc(cols):
    return (np.asarray(cols["open"], float), np.asarray(cols["high"], float),
            np.asarray(cols["low"], float), np.asarray(cols["close"], float))


# ----------------------------------------------------------- bar values
def t_open(cols, n=0, m=0.0):        return _hlc(cols)[0].copy()
def t_high(cols, n=0, m=0.0):        return _hlc(cols)[1].copy()
def t_low(cols, n=0, m=0.0):         return _hlc(cols)[2].copy()
def t_prev_open(cols, n=0, m=0.0):   return _shift(_hlc(cols)[0])
def t_prev_high(cols, n=0, m=0.0):   return _shift(_hlc(cols)[1])
def t_prev_low(cols, n=0, m=0.0):    return _shift(_hlc(cols)[2])
def t_prev_close(cols, n=0, m=0.0):  return _shift(_hlc(cols)[3])


# ----------------------------------------------------------- candle shapes
def t_bull_engulf(cols, n=0, m=0.0):
    """1 when this bar is up and its body covers the previous down bar's body."""
    o, _, _, c = _hlc(cols)
    po, pc = _shift(o), _shift(c)
    out = ((c > o) & (pc < po) & (c >= po) & (o <= pc)).astype(float)
    out[0] = np.nan
    return out


def t_bear_engulf(cols, n=0, m=0.0):
    o, _, _, c = _hlc(cols)
    po, pc = _shift(o), _shift(c)
    out = ((c < o) & (pc > po) & (c <= po) & (o >= pc)).astype(float)
    out[0] = np.nan
    return out


def t_inside_bar(cols, n=0, m=0.0):
    _, h, l, _ = _hlc(cols)
    out = ((h < _shift(h)) & (l > _shift(l))).astype(float)
    out[0] = np.nan
    return out


def t_body_pct(cols, n=0, m=0.0):
    """Body as a percent of the bar's range, signed: +80 is a strong up bar."""
    o, h, l, c = _hlc(cols)
    rng = h - l
    with np.errstate(divide="ignore", invalid="ignore"):
        return np.where(rng > 0, 100.0 * (c - o) / rng, np.nan)


# ----------------------------------------------------------- moving averages
def t_wma(cols, n, m=0.0):  return _wma(_hlc(cols)[3], n)


def t_hma(cols, n, m=0.0):
    c = _hlc(cols)[3]
    raw = 2 * _wma(c, max(n // 2, 1)) - _wma(c, n)
    return _wma(raw, max(int(np.sqrt(n)), 1))


def t_ema_slope(cols, n, m=0.0):
    """EMA(n) change over one bar, in basis points of price (like `roc`)."""
    e = _ema(_hlc(cols)[3], n)
    pe = _shift(e)
    with np.errstate(divide="ignore", invalid="ignore"):
        return (e - pe) / pe * 1e4


def _rma_plain(x, n):
    return rma(x, n)


def t_rma(cols, n, m=0.0):  return _rma_plain(_hlc(cols)[3], n)


def t_dema(cols, n, m=0.0):
    e = _ema(_hlc(cols)[3], n)
    return 2 * e - _ema_nan(e, n)


def t_tema(cols, n, m=0.0):
    e1 = _ema(_hlc(cols)[3], n)
    e2 = _ema_nan(e1, n)
    return 3 * e1 - 3 * e2 + _ema_nan(e2, n)


def t_vwma(cols, n, m=0.0):
    c = _hlc(cols)[3]
    v = np.asarray(cols["volume"], float)
    num, den = sma(c * v, n), sma(v, n)
    with np.errstate(divide="ignore", invalid="ignore"):
        return np.where(den > 0, num / den, sma(c, n))


def t_alma(cols, n, m=0.0):
    """Pine ta.alma(close, n, offset=0.85, sigma=6); `value` overrides offset."""
    c = _hlc(cols)[3]
    off = m or 0.85
    mu, sig = off * (n - 1), n / 6.0
    w = np.exp(-((np.arange(n) - mu) ** 2) / (2 * sig * sig))
    w /= w.sum()
    out = _nan(len(c))
    for i in range(n - 1, len(c)):
        out[i] = float(c[i - n + 1:i + 1] @ w)
    return out


def t_kama(cols, n, m=0.0):
    """Kaufman adaptive MA, efficiency over n bars, fast 2 / slow 30."""
    c = _hlc(cols)[3]
    fast, slow = 2 / 3, 2 / 31
    out = _nan(len(c))
    if len(c) <= n:
        return out
    out[n] = c[n]
    for i in range(n + 1, len(c)):
        ch = abs(c[i] - c[i - n])
        vol = np.sum(np.abs(np.diff(c[i - n:i + 1])))
        er = ch / vol if vol > 0 else 0.0
        sc = (er * (fast - slow) + slow) ** 2
        out[i] = out[i - 1] + sc * (c[i] - out[i - 1])
    return out


def t_volume(cols, n=0, m=0.0):    return np.asarray(cols["volume"], float).copy()
def t_vol_sma(cols, n, m=0.0):     return sma(np.asarray(cols["volume"], float), n)


# ----------------------------------------------------------- bands
def t_bb_upper(cols, n, m=0.0):
    c = _hlc(cols)[3]
    return sma(c, n) + (m or 2.0) * _stdev(c, n)


def t_bb_lower(cols, n, m=0.0):
    c = _hlc(cols)[3]
    return sma(c, n) - (m or 2.0) * _stdev(c, n)


def t_kc_upper(cols, n, m=0.0):
    _, h, l, c = _hlc(cols)
    return _ema(c, n) + (m or 2.0) * atr(h, l, c, n)


def t_kc_lower(cols, n, m=0.0):
    _, h, l, c = _hlc(cols)
    return _ema(c, n) - (m or 2.0) * atr(h, l, c, n)


# ----------------------------------------------------------- oscillators
def _macd(cols):
    c = _hlc(cols)[3]
    line = _ema(c, 12) - _ema(c, 26)
    sig = _ema_nan(line, 9)
    return line, sig


def t_macd(cols, n=0, m=0.0):         return _macd(cols)[0]
def t_macd_signal(cols, n=0, m=0.0):  return _macd(cols)[1]
def t_macd_hist(cols, n=0, m=0.0):
    line, sig = _macd(cols)
    return line - sig


def _dmi(cols, n):
    """Pine ta.dmi(n, n): (+DI, -DI, ADX)."""
    _, h, l, c = _hlc(cols)
    up, dn = np.diff(h, prepend=np.nan), -np.diff(l, prepend=np.nan)
    plus = np.where((up > dn) & (up > 0), up, 0.0)
    minus = np.where((dn > up) & (dn > 0), dn, 0.0)
    plus[0] = minus[0] = 0.0
    tr_ = atr(h, l, c, n)
    with np.errstate(divide="ignore", invalid="ignore"):
        pdi = 100 * rma(plus, n) / tr_
        mdi = 100 * rma(minus, n) / tr_
        dx = 100 * np.abs(pdi - mdi) / (pdi + mdi)
    return pdi, mdi, _rma_nan(dx, n)


def _rma_nan(x, n):
    out = _nan(len(x))
    ok = np.flatnonzero(~np.isnan(x))
    if len(ok):
        out[ok[0]:] = rma(np.nan_to_num(x[ok[0]:]), n)
    return out


def t_adx(cols, n, m=0.0):       return _dmi(cols, n)[2]
def t_di_plus(cols, n, m=0.0):   return _dmi(cols, n)[0]
def t_di_minus(cols, n, m=0.0):  return _dmi(cols, n)[1]


def _stoch(src, h, l, n):
    hi, lo = rolling_max(h, n), rolling_min(l, n)
    with np.errstate(divide="ignore", invalid="ignore"):
        return np.where(hi > lo, 100 * (src - lo) / (hi - lo), np.nan)


def t_stoch_k(cols, n, m=0.0):
    """Pine: sma(stoch(close, high, low, n), 3)."""
    _, h, l, c = _hlc(cols)
    return _sma_nan(_stoch(c, h, l, n), 3)


def t_stoch_d(cols, n, m=0.0):
    return _sma_nan(t_stoch_k(cols, n), 3)


def _rsi_series(c, n):
    d = np.diff(c, prepend=np.nan)
    d[0] = 0.0
    up, dn = rma(np.clip(d, 0, None), n), rma(np.clip(-d, 0, None), n)
    with np.errstate(divide="ignore", invalid="ignore"):
        return np.where(dn == 0, 100.0, 100 - 100 / (1 + up / dn))


def t_stochrsi_k(cols, n, m=0.0):
    """Stoch RSI: RSI(n), its stochastic over n, smoothed by 3."""
    r = _rsi_series(_hlc(cols)[3], n)
    r[:n] = np.nan
    hi, lo = rolling_max(r, n), rolling_min(r, n)
    with np.errstate(divide="ignore", invalid="ignore"):
        k = np.where(hi > lo, 100 * (r - lo) / (hi - lo), np.nan)
    return _sma_nan(k, 3)


def t_cci(cols, n, m=0.0):
    _, h, l, c = _hlc(cols)
    tp = (h + l + c) / 3
    mean = sma(tp, n)
    out = _nan(len(tp))
    for i in range(n - 1, len(tp)):
        md = np.mean(np.abs(tp[i - n + 1:i + 1] - mean[i]))
        out[i] = (tp[i] - mean[i]) / (0.015 * md) if md > 0 else np.nan
    return out


def t_rvol(cols, n, m=0.0):
    """This bar's volume over the mean of the n bars BEFORE it."""
    v = np.asarray(cols["volume"], float)
    base = _shift(sma(v, n))
    with np.errstate(divide="ignore", invalid="ignore"):
        return np.where(base > 0, v / base, np.nan)


# ----------------------------------------------------------- supertrend
def _supertrend(cols, n, m):
    """Pine ta.supertrend(factor=m, atrPeriod=n): (line, direction +1 up/-1 down).

    Pine's own `direction` is -1 for UP; here +1 is up, so a long flip reads
    `supertrend cross_above 0`.
    """
    _, h, l, c = _hlc(cols)
    a = atr(h, l, c, n)
    hl2 = (h + l) / 2
    f = m or 3.0
    N = len(c)
    line, d = _nan(N), _nan(N)
    up_p = dn_p = np.nan
    dir_p = 1.0
    for i in range(N):
        if np.isnan(a[i]):
            continue
        up, dn = hl2[i] - f * a[i], hl2[i] + f * a[i]
        pc = c[i - 1] if i else np.nan
        if not np.isnan(up_p) and pc > up_p:
            up = max(up, up_p)
        if not np.isnan(dn_p) and pc < dn_p:
            dn = min(dn, dn_p)
        if np.isnan(up_p):
            di = 1.0
        elif dir_p > 0 and c[i] < up_p:
            di = -1.0
        elif dir_p < 0 and c[i] > dn_p:
            di = 1.0
        else:
            di = dir_p
        line[i], d[i] = (up if di > 0 else dn), di
        up_p, dn_p, dir_p = up, dn, di
    return line, d


def t_supertrend(cols, n, m=0.0):       return _supertrend(cols, n, m)[1]
def t_supertrend_line(cols, n, m=0.0):  return _supertrend(cols, n, m)[0]


# ----------------------------------------------------------- pivots
def _carry(x):
    out = x.copy()
    for i in range(1, len(out)):
        if np.isnan(out[i]):
            out[i] = out[i - 1]
    return out


def t_pivot_high(cols, n, m=0.0):
    """The last CONFIRMED pivot high (n bars each side), held until the next.
    Known only n bars after the pivot bar, as in Pine."""
    return _carry(pivot_high(_hlc(cols)[1], n, n))


def t_pivot_low(cols, n, m=0.0):
    return _carry(pivot_low(_hlc(cols)[2], n, n))


# ----------------------------------------------------------- clock ranges
def _new_day(hour):
    nd = np.ones(len(hour), dtype=bool)
    nd[1:] = hour[1:] <= hour[:-1]
    return nd


def _range(cols, start, hours, hi_side):
    """High (or low) of today's UTC window [start, start+hours), known only
    once the window has closed; nan before that and on days it never ran."""
    _, h, l, _ = _hlc(cols)
    hr = np.asarray(cols["hour"], float)
    dur = int(hours) or 1
    nd = _new_day(hr)
    out = _nan(len(h))
    cur, done = np.nan, False
    for i in range(len(h)):
        if nd[i]:
            cur, done = np.nan, False
        inside = start <= hr[i] < start + dur
        if inside and not done:
            v = h[i] if hi_side else l[i]
            cur = v if np.isnan(cur) else (max(cur, v) if hi_side else min(cur, v))
        elif not inside and not np.isnan(cur) and hr[i] >= start + dur:
            done = True
        if done:
            out[i] = cur
    return out


def t_range_high(cols, n, m=0.0):  return _range(cols, n, m, True)
def t_range_low(cols, n, m=0.0):   return _range(cols, n, m, False)


def _day_hl(cols, prev):
    _, h, l, _ = _hlc(cols)
    nd = _new_day(np.asarray(cols["hour"], float))
    hi_o, lo_o = _nan(len(h)), _nan(len(h))
    dh = dl = ph = pl = np.nan
    for i in range(len(h)):
        if nd[i]:
            ph, pl = dh, dl
            dh = dl = np.nan
        if prev:
            hi_o[i], lo_o[i] = ph, pl
        else:                       # today so far, EXCLUDING this bar
            hi_o[i], lo_o[i] = dh, dl
        dh = h[i] if np.isnan(dh) else max(dh, h[i])
        dl = l[i] if np.isnan(dl) else min(dl, l[i])
    return hi_o, lo_o


def t_day_high(cols, n=0, m=0.0):       return _day_hl(cols, False)[0]
def t_day_low(cols, n=0, m=0.0):        return _day_hl(cols, False)[1]
def t_prev_day_high(cols, n=0, m=0.0):  return _day_hl(cols, True)[0]
def t_prev_day_low(cols, n=0, m=0.0):   return _day_hl(cols, True)[1]


#: name -> (function, needs a length?, help line for the translator)
TERMS = {
    "open":       (t_open, False, "this bar's open"),
    "high":       (t_high, False, "this bar's high"),
    "low":        (t_low, False, "this bar's low"),
    "prev_open":  (t_prev_open, False, "previous bar's open (Pine open[1])"),
    "prev_high":  (t_prev_high, False, "previous bar's high (high[1])"),
    "prev_low":   (t_prev_low, False, "previous bar's low (low[1])"),
    "prev_close": (t_prev_close, False, "previous bar's close (close[1])"),
    "bull_engulf": (t_bull_engulf, False, "1 on a bullish engulfing bar, else 0"),
    "bear_engulf": (t_bear_engulf, False, "1 on a bearish engulfing bar, else 0"),
    "inside_bar": (t_inside_bar, False, "1 when high<high[1] and low>low[1]"),
    "body_pct":   (t_body_pct, False, "(close-open)/(high-low)*100, signed, -100..100"),
    "wma":        (t_wma, True, "weighted MA of close"),
    "hma":        (t_hma, True, "Hull MA of close"),
    "rma":        (t_rma, True, "Wilder MA / SMMA of close (Pine ta.rma)"),
    "dema":       (t_dema, True, "double EMA of close"),
    "tema":       (t_tema, True, "triple EMA of close"),
    "vwma":       (t_vwma, True, "volume-weighted MA of close"),
    "alma":       (t_alma, True, "ALMA of close, sigma 6; value = offset (default 0.85)"),
    "kama":       (t_kama, True, "Kaufman adaptive MA, efficiency length n, fast 2 slow 30"),
    "volume":     (t_volume, False, "this bar's volume"),
    "vol_sma":    (t_vol_sma, True, "mean volume over n bars including this one"),
    "ema_slope":  (t_ema_slope, True, "one-bar change of EMA(n) in basis points; >0 rising"),
    "bb_upper":   (t_bb_upper, True, "Bollinger upper: sma(n) + value*stdev(n), value default 2"),
    "bb_lower":   (t_bb_lower, True, "Bollinger lower: sma(n) - value*stdev(n)"),
    "kc_upper":   (t_kc_upper, True, "Keltner upper: ema(n) + value*atr(n), value default 2. "
                                     "Also any 'ema + k*atr' line"),
    "kc_lower":   (t_kc_lower, True, "Keltner lower: ema(n) - value*atr(n)"),
    "macd":       (t_macd, False, "MACD line, ema12-ema26 (fixed 12/26/9)"),
    "macd_signal": (t_macd_signal, False, "MACD signal line, ema9 of macd"),
    "macd_hist":  (t_macd_hist, False, "MACD histogram, macd - signal"),
    "adx":        (t_adx, True, "ADX(n)"),
    "di_plus":    (t_di_plus, True, "+DI(n)"),
    "di_minus":   (t_di_minus, True, "-DI(n)"),
    "stoch_k":    (t_stoch_k, True, "stochastic %K(n), smoothed 3, 0-100"),
    "stoch_d":    (t_stoch_d, True, "stochastic %D: sma3 of stoch_k"),
    "stochrsi_k": (t_stochrsi_k, True, "Stoch RSI %K: rsi(n) through stoch(n), smoothed 3, 0-100"),
    "cci":        (t_cci, True, "CCI(n)"),
    "rvol":       (t_rvol, True, "volume / mean volume of the n bars before; 2 = double"),
    "supertrend": (t_supertrend, True, "Supertrend direction, ATR length n, factor=value "
                                       "(default 3): +1 up, -1 down. A flip to up is "
                                       "'supertrend cross_above 0'. Also use for any "
                                       "ATR trailing-stop / UT Bot / HalfTrend flip"),
    "supertrend_line": (t_supertrend_line, True, "the Supertrend line itself"),
    "pivot_high": (t_pivot_high, True, "last confirmed pivot high, n bars each side, "
                                       "known n bars after the pivot"),
    "pivot_low":  (t_pivot_low, True, "last confirmed pivot low, n bars each side"),
    "range_high": (t_range_high, True, "high of today's UTC clock window: length = start "
                                       "hour UTC (0-23), value = window hours. Known once "
                                       "the window closes. Opening ranges, Asia ranges, "
                                       "initial balance - convert the script's timezone to UTC"),
    "range_low":  (t_range_low, True, "low of that window"),
    "day_high":   (t_day_high, False, "today's UTC high so far, before this bar"),
    "day_low":    (t_day_low, False, "today's UTC low so far, before this bar"),
    "prev_day_high": (t_prev_day_high, False, "yesterday's UTC high"),
    "prev_day_low":  (t_prev_day_low, False, "yesterday's UTC low"),
}

#: Kinds that read `Term.value` as a multiplier / factor / window length.
MULT = {"alma", "bb_upper", "bb_lower", "kc_upper", "kc_lower", "supertrend",
        "supertrend_line", "range_high", "range_low"}
#: Kinds whose `length` may be 0 (an hour of day).
ZERO_LENGTH_OK = {"range_high", "range_low"}
