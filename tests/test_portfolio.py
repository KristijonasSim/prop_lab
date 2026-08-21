"""Book-level combination: the concurrency cap and shared-equity sizing."""
import pandas as pd
import pytest

from proplab.research import portfolio


def _trades(rows):
    return pd.DataFrame(
        [{"leg": leg, "entry_time": pd.Timestamp(a, tz="UTC"),
          "exit_time": pd.Timestamp(b, tz="UTC"), "r_multiple": r}
         for leg, a, b, r in rows]
    ).sort_values("entry_time").reset_index(drop=True)


def test_concurrency_cap_drops_overlapping_trades():
    # three trades all open at once; a cap of two must refuse the third
    t = _trades([("a", "2024-01-01 00:00", "2024-01-05", 1.0),
                 ("b", "2024-01-01 01:00", "2024-01-05", 1.0),
                 ("c", "2024-01-01 02:00", "2024-01-05", 1.0)])
    bt, _, dropped = portfolio.simulate(t, max_concurrent=2)
    assert len(bt) == 2
    assert dropped == 1


def test_slot_frees_once_the_trade_has_closed():
    t = _trades([("a", "2024-01-01", "2024-01-02", 1.0),
                 ("b", "2024-01-03", "2024-01-04", 1.0)])
    bt, _, dropped = portfolio.simulate(t, max_concurrent=1)
    assert len(bt) == 2 and dropped == 0


def test_fixed_risk_is_the_default_because_an_evaluation_does_not_compound():
    t = _trades([("a", "2024-01-01", "2024-01-02", 1.0),
                 ("b", "2024-01-03", "2024-01-04", 1.0)])
    bt, _, _ = portfolio.simulate(t, risk_pct=0.01, max_concurrent=1,
                                  starting_balance=100_000)
    assert bt.iloc[0]["risk"] == pytest.approx(1000.0)
    assert bt.iloc[1]["risk"] == pytest.approx(1000.0)


def test_compounding_sizes_off_the_grown_book_when_asked_for():
    # after a +1R win at 1% risk, the next trade risks 1% of the LARGER book
    t = _trades([("a", "2024-01-01", "2024-01-02", 1.0),
                 ("b", "2024-01-03", "2024-01-04", 1.0)])
    bt, _, _ = portfolio.simulate(t, risk_pct=0.01, max_concurrent=1,
                                  starting_balance=100_000, compound=True)
    assert bt.iloc[0]["risk"] == pytest.approx(1000.0)
    assert bt.iloc[1]["risk"] == pytest.approx(1010.0)


def test_equity_curve_is_ordered_by_exit_not_entry():
    # b is entered later but closes FIRST, so its P&L lands first
    t = _trades([("a", "2024-01-01", "2024-01-10", 1.0),
                 ("b", "2024-01-02", "2024-01-03", -1.0)])
    bt, curve, _ = portfolio.simulate(t, max_concurrent=2)
    assert list(bt["leg"]) == ["b", "a"]
    assert curve.index.is_monotonic_increasing


def test_metrics_report_the_drawdown_and_a_target_estimate():
    t = _trades([("a", f"2024-01-{d:02d}", f"2024-01-{d + 1:02d}", r)
                 for d, r in zip(range(1, 21), [1.0, -1.0] * 10)])
    bt, curve, _ = portfolio.simulate(t, max_concurrent=1)
    m = portfolio.metrics(bt, curve)
    assert m["n_trades"] == 20
    assert m["max_dd_pct"] >= 0
    assert m["win_rate_pct"] == pytest.approx(50.0)


def test_trades_without_a_defined_risk_are_excluded():
    class _T:
        def __init__(self, r, risk):
            self.r_multiple, self.initial_risk = r, risk
            self.entry_time = pd.Timestamp("2024-01-01", tz="UTC")
            self.exit_time = pd.Timestamp("2024-01-02", tz="UTC")
            self.bars_held, self.exit_reason = 1, "stop"

    class _Res:
        trades = [_T(1.0, 100.0), _T(float("nan"), 100.0), _T(1.0, 0.0)]

    out = portfolio.collect({"leg": _Res()})
    assert len(out) == 1        # only the one with a real R and real risk
