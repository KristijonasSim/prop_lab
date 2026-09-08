"""The kernel against an independent event-driven engine, run automatically.

THIS IS THE CHECK THAT HAS ACTUALLY FOUND BUGS. Not the unit tests - this one.
Porting the vwap kernel to NautilusTrader and comparing trade by trade is what
exposed the volatility-guard defect and the dead weekend bars on 2026-09-07,
and it is what proved gold survived the 2026-09-06 look-ahead fix (24 of 25
configurations bar for bar, and the 25th disagreement was the kernel's).

It had been run exactly twice, by hand, both times because someone chose to.
That is the gap this file closes: an event-driven engine is handed one bar at a
time and holds no array it could index into, so it cannot reproduce a
look-ahead even by accident. Agreement between the two is the strongest
evidence this repo can produce about a kernel.

RIBBON HAS NEVER BEEN THROUGH A SECOND ENGINE. That is recorded here as a
skip with a reason rather than left as an absence, so `core/verification.py`
can read it and cap H-016's score for it.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

MATCH = 0.9999          # entry bars must agree exactly; this is float slack only


def _stage17():
    try:
        from strategies.vwap import stage17_goldnautilus as S17
    except Exception as exc:                                   # noqa: BLE001
        pytest.skip(f"nautilus cross-check unavailable: "
                    f"{type(exc).__name__}: {exc}")
    return S17


def _check_tf(S17, tf: str):
    cfgs = S17.gold_configs((tf,))
    if tf not in cfgs:
        pytest.skip(f"no walk-forward configuration recorded for {tf}")
    df = S17.load_tf(S17.SYM, tf)
    feats = S17.features(df)
    bad = []
    for cfg in cfgs[tf]:
        r = S17.one(df, feats, cfg, S17.TFS[tf])
        if r["entry_match"] < MATCH:
            bad.append((cfg, r))
    assert not bad, (
        f"{len(bad)} of {len(cfgs[tf])} {tf} configurations disagree with the "
        f"independent engine on ENTRY BARS. An entry-bar disagreement is a "
        f"causality bug, not a fill assumption. First: "
        f"kernel {bad[0][1]['kernel_trades']} trades, "
        f"stream {bad[0][1]['stream_trades']}, "
        f"match {bad[0][1]['entry_match']:.4f}")


def test_vwap_matches_nautilus_on_4h():
    """The cheap slice of the cross-check, in the default run: every 4h
    configuration the gold walk-forward chose. Around fifteen seconds."""
    _check_tf(_stage17(), "4h")


@pytest.mark.slow
@pytest.mark.parametrize("tf", ["1h", "30m", "15m", "5m"])
def test_vwap_matches_nautilus_on_every_timeframe(tf):
    """The full cross-check. Minutes, not seconds - CI runs it nightly."""
    _check_tf(_stage17(), tf)


@pytest.mark.skip(reason="H-016's ribbon kernel has never been ported to a "
                         "second engine. This is a real gap in the evidence, "
                         "not a missing test file: core/verification.py reads "
                         "it and caps H-016's board score for it.")
def test_ribbon_matches_a_second_engine():
    raise AssertionError("not implemented")
