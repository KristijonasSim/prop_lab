"""Orchestration: load -> check -> run -> score -> prop-check -> log.

This is the only entry point that should be used to produce a result. It
guarantees every run is fingerprinted (data, strategy code, core code) and
that the automated checks ran before the numbers are believed.
"""
from __future__ import annotations

import inspect
from dataclasses import replace

from .checks import compliance, lookahead
from .config import BacktestConfig
from .core import engine, metrics as metrics_mod, prop_rules
from .core.types import BacktestResult
from .data import loader
from .db import store
from .strategy.base import Strategy


def backtest(
    strategy_cls: type[Strategy],
    *,
    symbol: str = "BTCUSDT",
    timeframe: str = "15m",
    start: str | None = None,
    end: str | None = None,
    config: BacktestConfig | None = None,
    params: dict | None = None,
    split: str = "full",
    data: loader.Dataset | None = None,
    run_checks: bool = True,
    base_timeframe: str = "15m",
) -> BacktestResult:
    higher = tuple(getattr(strategy_cls, "higher_timeframes", ()))
    cfg = config or BacktestConfig()
    cfg = replace(cfg, symbol=symbol, primary_timeframe=timeframe,
                  higher_timeframes=higher, start=start, end=end, split=split)

    if data is None:
        data = loader.load(symbol, timeframe, higher, start, end,
                           base_timeframe=base_timeframe)

    strategy = strategy_cls(**(params or {}))
    result = engine.run(strategy, data, cfg)

    result.metrics = metrics_mod.compute(result, timeframe, cfg.rules.starting_balance)
    result.prop = prop_rules.check(result, cfg.rules)

    source = inspect.getsource(inspect.getmodule(strategy_cls))
    result.meta["strategy"] = strategy_cls.name
    result.meta["describe"] = strategy.describe()
    result.meta["code_hash"] = compliance.strategy_fingerprint(source)
    result.meta["core_hash"] = compliance.core_fingerprint()
    result.meta["split"] = split
    result.meta["source"] = source

    if run_checks:
        checks = [
            compliance.template_compliance(strategy_cls).to_dict(),
            lookahead.static_scan(source).to_dict(),
            lookahead.order_of_execution_test(result).to_dict(),
            lookahead.scramble_test(strategy_cls, data, cfg).to_dict(),
        ]
        result.meta["checks"] = checks
    return result


def in_sample_out_of_sample(
    strategy_cls: type[Strategy], *, split_at: str, **kwargs
) -> dict[str, BacktestResult]:
    """Run the same code on both sides of a date. The OOS side is the only
    one that counts as evidence; the IS side is where tuning happened."""
    symbol = kwargs.get("symbol", "BTCUSDT")
    timeframe = kwargs.get("timeframe", "15m")
    higher = tuple(getattr(strategy_cls, "higher_timeframes", ()))
    full = loader.load(symbol, timeframe, higher, kwargs.get("start"),
                       kwargs.get("end"), base_timeframe=kwargs.pop("base_timeframe", "15m"))
    is_data, oos_data = full.split(split_at)
    out = {}
    for label, ds in (("is", is_data), ("oos", oos_data)):
        out[label] = backtest(strategy_cls, data=ds, split=label,
                              run_checks=(label == "is"), **kwargs)
    return out


def cost_sensitivity(strategy_cls, *, multipliers=(1.0, 2.0, 3.0), **kwargs):
    """Re-run the same strategy at multiples of the assumed trading costs.

    The venue is not decided yet (Binance vs a prop platform on MT4 /
    Match-Trader / cTrader), and platform costs differ by more than most
    strategy parameters do. A strategy that only works at 1x assumed costs is
    not an edge, it is a fee-schedule bet.
    """
    import pandas as pd

    base = kwargs.pop("config", None) or BacktestConfig()
    rows, results = [], {}
    for m in multipliers:
        c = base.costs
        scaled = replace(c, taker_fee_bps=c.taker_fee_bps * m,
                         maker_fee_bps=c.maker_fee_bps * m,
                         slippage_bps=c.slippage_bps * m,
                         stop_slippage_bps=c.stop_slippage_bps * m)
        res = backtest(strategy_cls, config=replace(base, costs=scaled),
                       run_checks=False, **kwargs)
        results[m] = res
        mt = res.metrics
        rows.append({
            "cost_x": m,
            "taker_bps": round(scaled.taker_fee_bps, 2),
            "trades": mt.get("n_trades"),
            "return_pct": mt.get("total_return_pct"),
            "sharpe": mt.get("sharpe"),
            "profit_factor": mt.get("profit_factor"),
            "expectancy_r": mt.get("expectancy_r"),
            "max_dd_pct": mt.get("max_drawdown_pct"),
            "prop_pass": res.prop.get("passed"),
        })
    return pd.DataFrame(rows), results


def log(result: BacktestResult, variation_slug: str | None = None,
        notes: str = "", db_path=None) -> str:
    conn = store.connect(db_path)
    try:
        return store.insert_run(conn, result, variation_slug=variation_slug,
                                split=result.meta.get("split", "full"), notes=notes)
    finally:
        conn.close()


def summary_line(result: BacktestResult) -> str:
    m, p = result.metrics, result.prop
    checks = result.meta.get("checks", [])
    chk = "OK" if all(c["passed"] for c in checks) else "FAILED"
    return (
        f"{result.meta.get('strategy')} [{result.meta.get('split','full')}] "
        f"{result.meta.get('symbol')} {result.meta.get('timeframe')} "
        f"{result.meta.get('start','')[:10]}..{result.meta.get('end','')[:10]} | "
        f"trades={m.get('n_trades')} ret={m.get('total_return_pct')}% "
        f"sharpe={m.get('sharpe')} maxDD={m.get('max_drawdown_pct')}% "
        f"PF={m.get('profit_factor')} expR={m.get('expectancy_r')} | "
        f"checks={chk} prop={'PASS' if p.get('passed') else 'FAIL'}"
        + (f" ({p.get('first_breach_rule')})" if p.get("first_breach_rule") else "")
    )
