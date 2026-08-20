"""Database round-trip: a run must be reconstructable from the DB alone."""
from __future__ import annotations

import json

import pytest

from proplab.config import BacktestConfig, CostModel
from proplab.data.loader import Dataset, check_integrity
from proplab.data.synthetic import random_walk
from proplab.db import store
from proplab.strategy.library._infra_smoke import InfraSmoke
from proplab import runner


@pytest.fixture
def conn(tmp_path):
    c = store.connect(tmp_path / "t.db")
    yield c
    c.close()


@pytest.fixture
def result():
    p = random_walk(2000, "15m", seed=9)
    ds = Dataset("SYNTH", "15m", p, {}, check_integrity(p, "15m"))
    return runner.backtest(InfraSmoke, symbol="SYNTH", timeframe="15m", data=ds,
                           config=BacktestConfig(symbol="SYNTH",
                                                 costs=CostModel(apply_funding=False)),
                           run_checks=False)


def test_full_round_trip(conn, result):
    store.upsert_hypothesis(conn, "h1", "Test hypothesis", "idea", "mechanism")
    store.upsert_variation(conn, "h1", "h1_v1", "Variation 1", "because",
                           "rules", strategy_name="_infra_smoke")
    uid = store.insert_run(conn, result, variation_slug="h1_v1", split="full")

    runs = store.runs_table(conn)
    assert len(runs) == 1
    r = runs.iloc[0]
    assert r["run_uuid"] == uid
    assert r["hypothesis_slug"] == "h1" and r["variation_slug"] == "h1_v1"
    assert r["n_trades"] == result.metrics["n_trades"]
    assert json.loads(r["metrics_json"])["sharpe"] == result.metrics["sharpe"]

    trades = conn.execute("SELECT COUNT(*) n FROM trades WHERE run_id=?",
                          (int(r["id"]),)).fetchone()["n"]
    assert trades == len(result.trades)
    eq = conn.execute("SELECT COUNT(*) n FROM equity_curve WHERE run_id=?",
                      (int(r["id"]),)).fetchone()["n"]
    assert eq > 0


def test_failed_ideas_list_is_the_denominator(conn, result):
    store.upsert_hypothesis(conn, "h1", "T", "", "")
    store.upsert_variation(conn, "h1", "v1", "V1")
    store.upsert_variation(conn, "h1", "v2", "V2")
    store.set_status(conn, "variation", "v1", "rejected", "expectancy negative OOS")
    failed = store.failed_ideas(conn)
    assert list(failed["variation"]) == ["v1"]
    assert "expectancy" in failed.iloc[0]["verdict_note"]


def test_infra_runs_do_not_count_as_research_trials(conn, result):
    """`_infra_smoke` exercises the plumbing; it must not inflate the
    multiple-testing denominator that real results are judged against."""
    store.upsert_hypothesis(conn, "h1", "T", "", "")
    store.upsert_variation(conn, "h1", "v1", "V1")
    for _ in range(3):
        store.insert_run(conn, result, variation_slug="v1")   # _infra_smoke
    tc = store.trial_count(conn)
    assert tc["runs_all_hypotheses"] == 0
    assert tc["infra_runs_excluded"] == 3


def test_real_runs_count_as_trials(conn, result):
    store.upsert_hypothesis(conn, "h1", "T", "", "")
    store.upsert_variation(conn, "h1", "v1", "V1")
    result.meta["strategy"] = "orb_v1"          # a real research strategy
    for _ in range(3):
        store.insert_run(conn, result, variation_slug="v1")
    tc = store.trial_count(conn)
    assert tc["runs_all_hypotheses"] == 3 and tc["variations"] == 1


def test_bad_status_rejected(conn):
    store.upsert_hypothesis(conn, "h1", "T", "", "")
    with pytest.raises(ValueError, match="Bad status"):
        store.set_status(conn, "hypothesis", "h1", "definitely_works")


def test_variation_requires_existing_hypothesis(conn):
    with pytest.raises(KeyError):
        store.upsert_variation(conn, "nope", "v", "V")


def test_run_requires_existing_variation(conn, result):
    with pytest.raises(KeyError):
        store.insert_run(conn, result, variation_slug="ghost")
