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

Ribbon was ported on 2026-09-08 (`strategies/ribbon/stage12_nautilus.py`) and
this file now checks both kernels. Until then the gap was recorded here as a
skip with a reason rather than left as an absence, and `core/verification.py`
read that skip and capped H-016's score at 3.0 for it.
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


def _stage12():
    try:
        from strategies.ribbon import stage12_nautilus as S12
    except Exception as exc:                                   # noqa: BLE001
        pytest.skip(f"ribbon cross-check unavailable: "
                    f"{type(exc).__name__}: {exc}")
    return S12


def _check_ribbon(S12, tf: str, limit: int | None):
    cfgs = S12.covering_configs(tf)
    if limit:
        # The board's own rule is appended last by covering_configs, so keep the
        # tail: a fast check that skipped the configuration actually traded
        # would be checking the wrong thing.
        cfgs = cfgs[-limit:]
    df = S12.load_tf(S12.SYM, tf)
    inp = S12.ribbon_inputs(df)
    bad = []
    for cfg in cfgs:
        r = S12.one(df, inp, cfg, S12.BAR_SPEC[tf])
        if r["entry_match"] < MATCH or r.get("max_r_diff", 0.0) > 1e-9:
            bad.append(r)
    assert not bad, (
        f"{len(bad)} of {len(cfgs)} ribbon rule shapes on {tf} disagree with "
        f"the independent engine. First: kernel {bad[0]['kernel_trades']} "
        f"trades, stream {bad[0]['stream_trades']}, "
        f"entry match {bad[0]['entry_match']:.4f}, "
        f"max |dR| {bad[0].get('max_r_diff', float('nan')):.3e}")


def test_ribbon_matches_nautilus_on_4h():
    """The board's own rule plus the shapes around it, on the cheapest
    timeframe. `covering_configs` picks one configuration per distinct CODE
    PATH - entry mode, flip requirement, trail form, fixed target, trailing
    start - because a cross-check is about branches, not about tuning."""
    _check_ribbon(_stage12(), "4h", limit=6)


@pytest.mark.slow
@pytest.mark.parametrize("tf", ["1h", "30m", "15m"])
def test_ribbon_matches_nautilus_on_every_board_timeframe(tf):
    """Every rule shape on every timeframe H-016 actually trades."""
    _check_ribbon(_stage12(), tf, limit=None)
