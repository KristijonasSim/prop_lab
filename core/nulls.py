"""Phase-randomised markets — the control every result in this project is read against.

Moved out of `strategies/vwap/stage3_timeframes.py` on 2026-09-08. Nothing in
here is about VWAP: it takes a bar frame and returns a bar frame. It lived
inside one hypothesis only because that hypothesis happened to need it first,
and every later hypothesis then imported across from vwap to get at it.

WHY A NULL AT ALL. Any search over thousands of configurations will produce
winners on pure noise. The only way to read a survivor is against the SAME search
run on data with the edge destroyed and everything else kept. Twelve hypotheses
have died to this and one of them (H-005) cleared the gate 1,702 times against
its null's 19,062.
"""
from __future__ import annotations

import zlib

import numpy as np
import pandas as pd


def null_seed(*parts) -> int:
    """A reproducible seed for a null draw.

    Every null in this project used to be seeded with `hash((sym, tf, tag))`.
    Python randomises string hashing per process unless PYTHONHASHSEED is set, so
    those seeds differed on every run: no null result could be reproduced, and a
    marginal verdict flipped between two runs of identical code — H-007's
    `beats_null` went True, then False, on the same data. CRC32 over the joined
    parts is stable across processes and machines.
    """
    return zlib.crc32("|".join(str(x) for x in parts).encode()) % (2 ** 31)


def shuffle_market(df: pd.DataFrame, seed: int) -> pd.DataFrame:
    """Keep every return, destroy their order.

    Bars are rebuilt around the new path so highs and lows stay consistent with
    it. Volume is permuted INDEPENDENTLY of returns, which is the right null for
    a pure price pattern and the wrong one for anything that reads volume — see
    `shuffle_market_paired`.
    """
    rng = np.random.default_rng(seed)
    c = df.close.values
    ret = np.diff(np.log(c))
    rng.shuffle(ret)
    new_c = c[0] * np.exp(np.concatenate(([0.0], np.cumsum(ret))))
    scale = new_c / c
    out = pd.DataFrame({
        "open": df.open.values * scale, "high": df.high.values * scale,
        "low": df.low.values * scale, "close": new_c,
        "volume": rng.permutation(df.volume.values)}, index=df.index)
    out["high"] = out[["open", "high", "close"]].max(axis=1)
    out["low"] = out[["open", "low", "close"]].min(axis=1)
    return out


def shuffle_market_paired(df: pd.DataFrame, seed: int) -> pd.DataFrame:
    """The stricter null, and the default for anything that reads volume.

    `shuffle_market` permutes volume independently of returns, so on that null a
    bar's volume tells you nothing about its own move. That quietly hands any
    participation filter a free win: it has a real contemporaneous volume/return
    relationship to work with on the live data and none at all on the null, so it
    looks predictive even if all it captures is "high-volume bars are bigger
    bars".

    This permutes (return, volume) as PAIRS. Each bar keeps its own volume, so
    the contemporaneous relationship survives and only the SEQUENCE is destroyed.
    A filter that still beats this is finding something about regime and ordering.
    """
    rng = np.random.default_rng(seed)
    c = df.close.values
    v = df.volume.values
    ret = np.diff(np.log(c))
    perm = rng.permutation(len(ret))
    ret = ret[perm]
    # volume[i+1] is the volume of the bar that produced ret[i]
    vol = np.concatenate(([v[0]], v[1:][perm]))

    new_c = c[0] * np.exp(np.concatenate(([0.0], np.cumsum(ret))))
    scale = new_c / c
    out = pd.DataFrame({
        "open": df.open.values * scale, "high": df.high.values * scale,
        "low": df.low.values * scale, "close": new_c, "volume": vol},
        index=df.index)
    out["high"] = out[["open", "high", "close"]].max(axis=1)
    out["low"] = out[["open", "low", "close"]].min(axis=1)
    return out


#: name -> generator. `paired` is the default; use `plain` only for a strategy
#: that provably never reads volume.
NULLS = {"paired": shuffle_market_paired, "plain": shuffle_market}
