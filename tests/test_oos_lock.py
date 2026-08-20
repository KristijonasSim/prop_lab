"""Out-of-sample data is a one-shot resource. These tests hold the tooling to
that rule, so it does not depend on anyone remembering it."""
from __future__ import annotations

import pytest

from proplab.config import BacktestConfig, CostModel
from proplab.data.loader import Dataset, check_integrity
from proplab.data.synthetic import random_walk
from proplab.db import store
from proplab.strategy.library._infra_smoke import InfraSmoke
from proplab import runner


@pytest.fixture
def conn(tmp_path):
    c = store.connect(tmp_path / "oos.db")
    store.upsert_hypothesis(c, "h", "H", "d", "m")
    store.upsert_variation(c, "h", "v1", "V1")
    yield c
    c.close()


@pytest.fixture
def result():
    p = random_walk(2000, "15m", seed=5)
    ds = Dataset("SYNTH", "15m", p, {}, check_integrity(p, "15m"))
    return runner.backtest(InfraSmoke, symbol="SYNTH", timeframe="15m", data=ds,
                           config=BacktestConfig(costs=CostModel(apply_funding=False)),
                           run_checks=False)


def test_first_oos_look_is_allowed(conn):
    store.assert_oos_available(conn, "v1")      # must not raise


def test_second_oos_look_is_refused(conn, result):
    store.insert_run(conn, result, variation_slug="v1", split="oos")
    with pytest.raises(store.OOSAlreadyUsed) as e:
        store.assert_oos_available(conn, "v1")
    assert "already used its out-of-sample look" in str(e.value)


def test_in_sample_runs_do_not_consume_the_look(conn, result):
    """Tuning in-sample must stay unlimited - that is what in-sample is for."""
    for _ in range(5):
        store.insert_run(conn, result, variation_slug="v1", split="is")
    store.assert_oos_available(conn, "v1")      # still available
    assert store.oos_looks(conn, "v1").empty


def test_full_split_runs_do_not_consume_the_look(conn, result):
    store.insert_run(conn, result, variation_slug="v1", split="full")
    store.assert_oos_available(conn, "v1")


def test_burning_the_look_is_allowed_but_recorded(conn, result):
    store.insert_run(conn, result, variation_slug="v1", split="oos")
    store.assert_oos_available(conn, "v1", burn_reason="stop logic had a bug")
    events = conn.execute(
        "SELECT event, detail FROM events WHERE event='oos_burned'").fetchall()
    assert len(events) == 1
    assert "stop logic had a bug" in events[0]["detail"]


def test_a_new_variation_gets_its_own_look(conn, result):
    """The sanctioned escape hatch: changed the strategy? It is a new variation,
    which keeps the trial count honest."""
    store.insert_run(conn, result, variation_slug="v1", split="oos")
    store.upsert_variation(conn, "h", "v2", "V2")
    store.assert_oos_available(conn, "v2")


def test_ledger_reports_who_has_spent_their_look(conn, result):
    store.upsert_variation(conn, "h", "v2", "V2")
    store.insert_run(conn, result, variation_slug="v1", split="oos")
    led = store.oos_ledger(conn).set_index("variation")
    assert led.loc["v1", "oos_looks"] == 1
    assert led.loc["v2", "oos_looks"] == 0
