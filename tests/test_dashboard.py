"""The dashboard must render every page, and the hypothesis drill-down must
actually navigate: library -> one hypothesis -> one variation's runs.

Covers both a populated database and an empty one - the empty case is what the
dashboard looks like before the first run, and it is easy to break.
"""
from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("streamlit")
import streamlit as st                       # noqa: E402
from streamlit.testing.v1 import AppTest     # noqa: E402

from proplab.db import store                 # noqa: E402

APP = str(Path(__file__).resolve().parents[1] / "dashboard" / "app.py")
PAGES = ["Hypotheses", "Overview", "All runs", "Failed ideas"]


@pytest.fixture
def seeded(tmp_path, monkeypatch):
    """A DB with a hypothesis, two variations and runs on one of them."""
    from proplab.config import BacktestConfig, CostModel
    from proplab.data.loader import Dataset, check_integrity
    from proplab.data.synthetic import random_walk
    from proplab.strategy.library._infra_smoke import InfraSmoke
    from proplab import runner

    db = tmp_path / "seed.db"
    c = store.connect(db)
    store.upsert_hypothesis(
        c, "trend_swing", "Trend following swing trading",
        description="Ride established multi-day trends on BTC.",
        mechanism="Slow diffusion of information keeps trends going.",
        research="Normally traded with a moving-average filter.",
        symbol="BTCUSDT", status="tested")
    store.upsert_variation(c, "trend_swing", "trend_swing_v1", "MA cross, 4h",
                           rationale="Baseline.", details="Long above MA200.",
                           status="tested")
    store.upsert_variation(c, "trend_swing", "trend_swing_v2", "MA cross + ATR stop",
                           rationale="Test stop placement.", details="ATR 2x stop.",
                           status="rejected", verdict_note="negative expectancy OOS")

    p = random_walk(2000, "15m", seed=9)
    ds = Dataset("BTCUSDT", "15m", p, {}, check_integrity(p, "15m"))
    res = runner.backtest(InfraSmoke, symbol="BTCUSDT", timeframe="15m", data=ds,
                          config=BacktestConfig(costs=CostModel(apply_funding=False)),
                          run_checks=False)
    for split in ("is", "oos"):
        res.meta["split"] = split
        store.insert_run(c, res, variation_slug="trend_swing_v1", split=split)
    c.close()

    monkeypatch.setattr(store, "DB_PATH", db)
    st.cache_resource.clear()
    st.cache_data.clear()
    yield
    st.cache_resource.clear()
    st.cache_data.clear()


def _fresh(monkeypatch, tmp_path, name="empty.db"):
    monkeypatch.setattr(store, "DB_PATH", tmp_path / name)
    st.cache_resource.clear()
    st.cache_data.clear()


@pytest.mark.parametrize("page", PAGES)
def test_page_renders_with_data(page, seeded):
    at = AppTest.from_file(APP, default_timeout=90).run()
    assert not at.exception, at.exception
    at.sidebar.radio[0].set_value(page).run()
    assert not at.exception, at.exception


@pytest.mark.parametrize("page", PAGES)
def test_page_renders_on_empty_db(page, tmp_path, monkeypatch):
    _fresh(monkeypatch, tmp_path)
    try:
        at = AppTest.from_file(APP, default_timeout=90).run()
        assert not at.exception, at.exception
        at.sidebar.radio[0].set_value(page).run()
        assert not at.exception, at.exception
    finally:
        st.cache_resource.clear()
        st.cache_data.clear()


def test_hypothesis_library_lists_the_hypothesis(seeded):
    at = AppTest.from_file(APP, default_timeout=90).run()
    text = " ".join(m.value for m in at.markdown)
    assert "Trend following swing trading" in text


def test_clicking_open_drills_into_the_hypothesis(seeded):
    """The whole point: press a hypothesis, see the strategies under it."""
    at = AppTest.from_file(APP, default_timeout=90).run()
    opens = [b for b in at.button if b.label.startswith("Open")]
    assert opens, "no Open button rendered for the hypothesis"
    opens[0].click().run()
    assert not at.exception, at.exception
    assert at.session_state["page"] == "hypothesis_detail"
    assert at.session_state["hyp"] == "trend_swing"

    body = " ".join(m.value for m in at.markdown)
    # the mechanism and both variations must be visible
    assert "Slow diffusion of information" in body
    labels = " ".join(e.label for e in at.expander)
    assert "MA cross, 4h" in labels and "MA cross + ATR stop" in labels


def test_drilling_into_a_variation_shows_its_runs(seeded):
    at = AppTest.from_file(APP, default_timeout=90).run()
    [b for b in at.button if b.label.startswith("Open")][0].click().run()
    see_runs = [b for b in at.button if "See all runs" in b.label]
    assert see_runs, "variation with runs had no drill-down button"
    see_runs[0].click().run()
    assert not at.exception, at.exception
    assert at.session_state["page"] == "variation_detail"
    assert at.session_state["var"] == "trend_swing_v1"
    assert len(at.dataframe) >= 1          # the runs table


def test_back_button_returns_to_the_library(seeded):
    at = AppTest.from_file(APP, default_timeout=90).run()
    [b for b in at.button if b.label.startswith("Open")][0].click().run()
    back = [b for b in at.button if "All hypotheses" in b.label]
    assert back
    back[0].click().run()
    assert at.session_state["page"] == "Hypotheses"
    assert not at.exception, at.exception


def test_sidebar_nav_leaves_a_drill_down(seeded):
    at = AppTest.from_file(APP, default_timeout=90).run()
    [b for b in at.button if b.label.startswith("Open")][0].click().run()
    assert at.session_state["page"] == "hypothesis_detail"
    at.sidebar.radio[0].set_value("Overview").run()
    assert at.session_state["page"] == "Overview"
    assert not at.exception, at.exception
