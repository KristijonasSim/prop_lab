#!/usr/bin/env python
"""Environment check. Run after any dependency change: .venv/bin/python smoke_test.py"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

OK, FAIL = "  OK  ", " FAIL "


def check(name, fn):
    try:
        detail = fn()
        print(f"[{OK}] {name}{' — ' + detail if detail else ''}")
        return True
    except Exception as e:
        print(f"[{FAIL}] {name} — {type(e).__name__}: {e}")
        return False


def _versions():
    import ccxt, nautilus_trader, numpy, pandas, vectorbt
    assert pandas.__version__ < "3", "nautilus wrangler breaks on pandas 3 (copy-on-write)"
    return (f"py{sys.version_info.major}.{sys.version_info.minor} "
            f"nautilus {nautilus_trader.__version__} vectorbt {vectorbt.__version__} "
            f"pandas {pandas.__version__} numpy {numpy.__version__} ccxt {ccxt.__version__}")


def _binance():
    import ccxt
    t = ccxt.binance().fetch_ticker("BTC/USDT")
    return f"BTC/USDT last {t['last']}"


def _data():
    from core import data
    df = data.download("BTC/USDT", since="2026-08-01")
    tfs = {tf: len(data.load("BTC/USDT", tf)) for tf in ("15m", "1h", "4h", "1d")}
    return f"15m {len(df)} bars -> {tfs}"


def _nautilus():
    from core import data, nautilus_setup as ns
    eng = ns.make_engine()
    ns.add_bars(eng, data.load("BTC/USDT", "15m"))
    eng.run()
    n = len(eng.trader.generate_account_report(ns.VENUE))
    eng.dispose()
    return f"engine ran, {n} account row(s)"


def _metrics():
    import numpy as np, pandas as pd
    from core.metrics import resolution_estimate
    np.random.seed(0)
    d, b, p = resolution_estimate(pd.Series(np.random.normal(0.003, 0.015, 200)))
    assert 5 < d < 60 and p > 0.8, (d, b, p)
    return f"days_to_target {d:.1f}, P(target first) {p:.2f}"


def _prop():
    import numpy as np, pandas as pd
    from core.prop_rules import evaluate, Outcome
    idx = pd.date_range("2026-01-01", periods=24 * 30, freq="h")
    eq = pd.Series(100_000 * np.exp(np.linspace(0, 0.10, len(idx))), index=idx)
    assert evaluate(eq, 100_000).outcome is Outcome.PASS
    blown = eq.copy(); blown.iloc[48:] = 90_000
    assert evaluate(blown, 100_000).outcome is Outcome.FAIL_DAILY
    return "PASS and FAIL_DAILY both detected"


def _mt5():
    import importlib.util
    if importlib.util.find_spec("MetaTrader5") is None:
        raise RuntimeError("not installed — Windows-only pkg; needs an mt5linux bridge. Crypto first.")
    return "installed"


checks = [
    ("versions", _versions),
    ("binance reachable", _binance),
    ("data download + resample", _data),
    ("nautilus backtest engine", _nautilus),
    ("metrics / resolution estimate", _metrics),
    ("prop rules", _prop),
]

results = [check(n, f) for n, f in checks]
check("MetaTrader5 (expected to fail on linux)", _mt5)

print()
print("READY" if all(results) else "NOT READY — fix the failures above")
sys.exit(0 if all(results) else 1)
