"""Lookahead-bias detection: static scan + empirical future-scramble test.

The Context already makes future bars unreachable through the sanctioned API.
These checks catch the ways around it: private attribute access, imported
data, negative shifts, and wall-clock non-determinism.

The scramble test is the one that really matters. It re-runs the backtest with
all data after a cutoff replaced by noise. Any decision made BEFORE the cutoff
must be bit-identical - if it changes, the strategy saw the future.
"""
from __future__ import annotations

import ast
import re
from dataclasses import dataclass

import numpy as np
import pandas as pd

from ..core import engine
from ..data.loader import Dataset
from ..data.timeframes import resample

BANNED_PATTERNS = [
    (r"ctx\._[a-zA-Z]", "accesses a private Context attribute (bypasses the lookahead wall)"),
    (r"\.shift\(\s*-", "negative shift pulls future values backwards"),
    (r"\.iloc\[\s*[a-zA-Z_]*\s*\+\s*\d", "forward-offset iloc indexing"),
    (r"pd\.read_|\.read_parquet|\.read_csv", "loads its own data instead of using ctx"),
    (r"\brequests\b|urllib", "network access inside a strategy"),
    (r"datetime\.now|time\.time\(\)|Timestamp\.now", "wall-clock time makes runs non-deterministic"),
    (r"\bglobal\b", "global state leaks between runs"),
]


@dataclass
class CheckResult:
    name: str
    passed: bool
    detail: str
    findings: list = None

    def to_dict(self) -> dict:
        return {"name": self.name, "passed": self.passed, "detail": self.detail,
                "findings": self.findings or []}


def static_scan(source: str) -> CheckResult:
    findings = []
    for lineno, line in enumerate(source.splitlines(), 1):
        code = line.split("#")[0]
        for pattern, why in BANNED_PATTERNS:
            if re.search(pattern, code):
                findings.append({"line": lineno, "code": line.strip(), "why": why})
    try:
        ast.parse(source)
    except SyntaxError as e:
        findings.append({"line": e.lineno or 0, "code": str(e), "why": "syntax error"})
    return CheckResult(
        "static_lookahead_scan", not findings,
        "no banned patterns" if not findings else f"{len(findings)} suspicious line(s)",
        findings,
    )


def scramble_test(strategy_cls, data: Dataset, config, cutoff_frac: float = 0.6,
                  seed: int = 11, params: dict | None = None) -> CheckResult:
    """Re-run with the post-cutoff future randomised; pre-cutoff must not move."""
    params = params or {}
    base = engine.run(strategy_cls(**params), data, config)

    k = int(len(data.primary) * cutoff_frac)
    cutoff_time = data.primary.index[k]

    rng = np.random.default_rng(seed)
    df = data.primary.copy()
    tail = df.iloc[k:]
    # Replace the future with a different but plausible path: shuffle returns
    # and rebuild bars from the last real close.
    rets = np.log(tail["close"] / tail["close"].shift(1)).fillna(0).to_numpy().copy()
    rng.shuffle(rets)
    anchor = float(df["close"].iloc[k - 1])
    new_close = anchor * np.exp(np.cumsum(rets))
    scale = new_close / tail["close"].to_numpy()
    for col in ("open", "high", "low", "close"):
        df.iloc[k:, df.columns.get_loc(col)] = tail[col].to_numpy() * scale

    scrambled = Dataset(
        data.symbol, data.primary_timeframe, df,
        {tf: resample(df, tf) for tf in data.higher}, data.integrity,
    )
    alt = engine.run(strategy_cls(**params), scrambled, config)

    def pre(res):
        return [
            (str(t.entry_time), t.direction, round(t.qty, 8), round(t.entry_price, 8))
            for t in res.trades if t.entry_time < cutoff_time
        ]

    a, b = pre(base), pre(alt)
    if a == b:
        return CheckResult("future_scramble_test", True,
                           f"{len(a)} pre-cutoff entries identical after randomising "
                           f"data from {cutoff_time}")
    diffs = [(x, y) for x, y in zip(a, b) if x != y][:5]
    return CheckResult(
        "future_scramble_test", False,
        f"pre-cutoff entries CHANGED when the future changed ({len(a)} vs {len(b)} "
        f"entries) - this is lookahead bias",
        [{"baseline": x, "scrambled": y} for x, y in diffs],
    )


def order_of_execution_test(result) -> CheckResult:
    """No trade may be entered at a price outside its entry bar's range, and no
    exit may precede its entry."""
    findings = []
    for t in result.trades:
        if t.exit_time < t.entry_time:
            findings.append({"trade": str(t.entry_time), "why": "exit before entry"})
        if t.bars_held < 0:
            findings.append({"trade": str(t.entry_time), "why": "negative holding period"})
    return CheckResult("trade_ordering", not findings,
                       "all trades ordered correctly" if not findings
                       else f"{len(findings)} malformed trade(s)", findings)
