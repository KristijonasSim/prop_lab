"""The lookahead detectors must catch a strategy that genuinely cheats."""
from __future__ import annotations

import pytest

from proplab.config import BacktestConfig, CostModel, PropFirmRules
from proplab.checks import compliance, lookahead
from proplab.data.loader import Dataset, check_integrity
from proplab.data.synthetic import random_walk
from proplab.data.timeframes import resample
from proplab.strategy.base import Strategy

CFG = BacktestConfig(symbol="TEST", primary_timeframe="15m",
                     costs=CostModel(apply_funding=False),
                     rules=PropFirmRules())


def make_ds(n=1500, seed=1, higher=()):
    df = random_walk(n, "15m", seed=seed)
    return Dataset("TEST", "15m", df, {h: resample(df, h) for h in higher},
                   check_integrity(df, "15m"))


class Honest(Strategy):
    name = "_t_honest"
    hypothesis = "test"
    mechanism = "test"
    params = {"n": 20}

    def on_bar(self, ctx):
        if ctx.position is not None or ctx.bars_seen < ctx.params["n"] + 1:
            return
        highs = ctx.series("high", ctx.params["n"])
        if ctx.close > float(highs[:-1].max()):
            ctx.buy(stop=ctx.close * 0.99, risk_pct=0.005, max_bars=20, tag="h")


class Cheater(Strategy):
    """Peeks at tomorrow through a private attribute. Must be caught."""
    name = "_t_cheater"
    hypothesis = "test"
    mechanism = "test"
    params = {"ahead": 4}

    def on_bar(self, ctx):
        if ctx.position is not None:
            return
        future_i = ctx.i + ctx.params["ahead"]
        closes = ctx._cols["close"]          # bypasses the wall
        if future_i < len(closes) and closes[future_i] > ctx.close:
            ctx.buy(stop=ctx.close * 0.99, risk_pct=0.005,
                    max_bars=ctx.params["ahead"], tag="cheat")


class ParamCheater(Strategy):
    """Only cheats when enabled by an override. The scramble test must use the
    exact params of the run being validated, not the class defaults."""
    name = "_t_param_cheater"
    hypothesis = "test"
    mechanism = "test"
    params = {"cheat": False, "ahead": 4}

    def on_bar(self, ctx):
        if ctx.position is not None:
            return
        if not ctx.params["cheat"]:
            if ctx.i % 200 == 0:
                ctx.buy(stop=ctx.close * 0.99, risk_pct=0.005, max_bars=10, tag="honest")
            return
        future_i = ctx.i + ctx.params["ahead"]
        closes = ctx._cols["close"]
        if future_i < len(closes) and closes[future_i] > ctx.close:
            ctx.buy(stop=ctx.close * 0.99, risk_pct=0.005,
                    max_bars=ctx.params["ahead"], tag="cheat")


def test_scramble_test_passes_an_honest_strategy():
    r = lookahead.scramble_test(Honest, make_ds(), CFG)
    assert r.passed, r.detail


def test_scramble_test_catches_a_cheater():
    r = lookahead.scramble_test(Cheater, make_ds(), CFG)
    assert not r.passed
    assert "lookahead" in r.detail


def test_scramble_test_uses_runtime_params():
    r = lookahead.scramble_test(ParamCheater, make_ds(), CFG,
                                params={"cheat": True, "ahead": 4})
    assert not r.passed


def test_cheater_would_have_looked_profitable():
    """Shows why the check matters: the cheat prints money on random data."""
    from proplab.core import engine, metrics
    ds = make_ds()
    r = engine.run(Cheater(), ds, CFG)
    m = metrics.compute(r, "15m", 100_000)
    assert m["total_return_pct"] > 0 and m["win_rate_pct"] > 60


def test_static_scan_flags_private_access():
    src = "def on_bar(self, ctx):\n    x = ctx._cols['close']\n"
    r = lookahead.static_scan(src)
    assert not r.passed and "private" in r.findings[0]["why"]


def test_static_scan_flags_negative_shift():
    r = lookahead.static_scan("y = df['close'].shift(-1)\n")
    assert not r.passed


def test_static_scan_passes_clean_code():
    src = "def on_bar(self, ctx):\n    c = ctx.series('close', 20)\n    return c.mean()\n"
    assert lookahead.static_scan(src).passed


def test_template_compliance_requires_mechanism():
    class NoWhy(Strategy):
        name = "t_nowhy"  # no underscore: infra strategies are exempt
        hypothesis = "x"
        params = {"a": 1}

        def on_bar(self, ctx):
            pass

    r = compliance.template_compliance(NoWhy)
    assert not r.passed and "mechanism" in r.detail


def test_unknown_param_is_rejected():
    with pytest.raises(ValueError, match="unknown params"):
        Honest(typo_param=3)


def test_core_fingerprint_is_stable():
    assert compliance.core_fingerprint() == compliance.core_fingerprint()
