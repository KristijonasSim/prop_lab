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


# ----------------------------------------------------------- refresh / nav
def test_refresh_does_not_crash(seeded):
    at = AppTest.from_file(APP, default_timeout=90).run()
    [b for b in at.sidebar.button if b.label == "Refresh"][0].click().run()
    assert not at.exception, at.exception


def test_no_widget_callback_reads_widget_state():
    """Regression: the sidebar used an on_change callback that READ
    st.session_state["nav"]. Callbacks run before the script body, so after a
    browser reconnect - or any rerun that never reached the widget - that key
    is absent and every interaction dies with KeyError. It reproduced in the
    browser but not in AppTest, so this is enforced statically instead:
    callbacks may write session state, never read a widget key from it."""
    import ast

    src = Path(APP).read_text()
    tree = ast.parse(src)

    callbacks = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            for kw in node.keywords:
                if kw.arg in ("on_click", "on_change") and isinstance(kw.value, ast.Name):
                    callbacks.add(kw.value.id)

    funcs = {n.name: n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)}
    offenders = []
    for name in callbacks:
        fn = funcs.get(name)
        if fn is None:
            continue
        for node in ast.walk(fn):
            # a read looks like  x = st.session_state[...]  (Load context)
            if (isinstance(node, ast.Subscript)
                    and isinstance(node.ctx, ast.Load)
                    and ast.unparse(node.value).endswith("session_state")):
                offenders.append(f"{name}: {ast.unparse(node)}")
    assert not offenders, (
        "widget callbacks must not read session state: " + "; ".join(offenders))


def test_hypothesis_with_no_runs_renders(tmp_path, monkeypatch):
    """Regression: `last_run` is NaN for a hypothesis that was never run, and
    NaN is TRUTHY in Python - so the guard passed and slicing it crashed the
    whole library page. Mixing run and never-run hypotheses must be fine."""
    _fresh(monkeypatch, tmp_path, "mixed.db")
    c = store.connect(store.DB_PATH)
    store.upsert_hypothesis(c, "never_run", "Never run idea",
                            description="queued, no runs yet", mechanism="m",
                            status="queued")
    c.close()
    try:
        at = AppTest.from_file(APP, default_timeout=90).run()
        assert not at.exception, at.exception
        body = " ".join(m.value for m in at.markdown)
        assert "Never run idea" in body
        assert "never run" in " ".join(cap.value for cap in at.caption)
    finally:
        st.cache_resource.clear()
        st.cache_data.clear()


def test_refresh_from_a_drill_down_stays_put(seeded):
    at = AppTest.from_file(APP, default_timeout=90).run()
    [b for b in at.button if b.label.startswith("Open")][0].click().run()
    assert at.session_state["page"] == "hypothesis_detail"
    [b for b in at.sidebar.button if b.label == "Refresh"][0].click().run()
    assert not at.exception, at.exception
    assert at.session_state["page"] == "hypothesis_detail"


def test_refresh_picks_up_new_rows(seeded):
    """Refresh exists to clear the 5s data cache - it must actually show a
    hypothesis added after the page was loaded."""
    at = AppTest.from_file(APP, default_timeout=90).run()
    assert "Overnight gap fade" not in " ".join(m.value for m in at.markdown)

    c = store.connect(store.DB_PATH)
    store.upsert_hypothesis(c, "gap_fade", "Overnight gap fade",
                            description="x", mechanism="y", status="queued")
    c.close()

    [b for b in at.sidebar.button if b.label == "Refresh"][0].click().run()
    assert not at.exception, at.exception
    assert "Overnight gap fade" in " ".join(m.value for m in at.markdown)


# --------------------------------------------------- hypothesis library grid
@pytest.fixture
def many(tmp_path, monkeypatch):
    """Twelve hypotheses - the list is meant to grow, so it must stay usable."""
    _fresh(monkeypatch, tmp_path, "many.db")
    c = store.connect(store.DB_PATH)
    for i in range(12):
        store.upsert_hypothesis(
            c, f"h{i:02}", f"Idea number {i:02}", description=f"desc {i}",
            mechanism="m", symbol="BTCUSDT",
            status="rejected" if i % 3 == 0 else "queued")
    c.close()
    yield
    st.cache_resource.clear()
    st.cache_data.clear()


def test_all_hypotheses_render_in_the_grid(many):
    at = AppTest.from_file(APP, default_timeout=90).run()
    assert not at.exception, at.exception
    opens = [b for b in at.button if b.label.startswith("Open")]
    assert len(opens) == 12


def test_search_filters_the_library(many):
    at = AppTest.from_file(APP, default_timeout=90).run()
    at.text_input[0].set_value("number 07").run()
    assert not at.exception, at.exception
    assert len([b for b in at.button if b.label.startswith("Open")]) == 1


def test_status_filter_narrows_the_library(many):
    at = AppTest.from_file(APP, default_timeout=90).run()
    at.multiselect[0].set_value(["rejected"]).run()
    assert not at.exception, at.exception
    assert len([b for b in at.button if b.label.startswith("Open")]) == 4  # i%3==0


def test_sorting_does_not_break_with_never_run_hypotheses(many):
    """Every hypothesis here has last_run = NaN; sorting must survive that."""
    at = AppTest.from_file(APP, default_timeout=90).run()
    for option in ["Best OOS Sharpe", "Most runs", "Name"]:
        at.selectbox[0].set_value(option).run()
        assert not at.exception, at.exception


def test_filtering_to_nothing_is_handled(many):
    at = AppTest.from_file(APP, default_timeout=90).run()
    at.text_input[0].set_value("zzzz-no-such-thing").run()
    assert not at.exception, at.exception
    assert not [b for b in at.button if b.label.startswith("Open")]


def test_open_still_works_from_the_grid(many):
    at = AppTest.from_file(APP, default_timeout=90).run()
    [b for b in at.button if b.label.startswith("Open")][0].click().run()
    assert at.session_state["page"] == "hypothesis_detail"
    assert not at.exception, at.exception


def test_only_out_of_sample_prop_passes_are_counted(tmp_path, monkeypatch, seeded_runs=None):
    """Regression: the card summed prop_passed across ALL splits, so in-sample
    tuning passes were displayed as if strategies had succeeded."""
    from proplab.config import BacktestConfig, CostModel
    from proplab.data.loader import Dataset, check_integrity
    from proplab.data.synthetic import random_walk
    from proplab.strategy.library._infra_smoke import InfraSmoke
    from proplab import runner

    _fresh(monkeypatch, tmp_path, "splits.db")
    c = store.connect(store.DB_PATH)
    store.upsert_hypothesis(c, "h", "H", "d", "m")
    store.upsert_variation(c, "h", "v", "V")
    p = random_walk(1500, "15m", seed=2)
    ds = Dataset("X", "15m", p, {}, check_integrity(p, "15m"))
    res = runner.backtest(InfraSmoke, symbol="X", timeframe="15m", data=ds,
                          config=BacktestConfig(costs=CostModel(apply_funding=False)),
                          run_checks=False)
    res.prop["passed"] = True                    # pretend the rules were met
    for split in ("is", "is", "full"):
        store.insert_run(c, res, variation_slug="v", split=split)
    row = store.hypotheses_list(c).iloc[0]
    c.close()
    st.cache_resource.clear()
    st.cache_data.clear()

    assert row["n_prop_passes"] == 0             # none of them were OOS
    assert row["n_prop_passes_any_split"] == 3
