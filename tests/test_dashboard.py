"""The dashboard must render every page without raising.

Covers both the populated database and an empty one - the empty case is what
the dashboard looks like before the first run, and it is easy to break.
"""
from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("streamlit")
from streamlit.testing.v1 import AppTest  # noqa: E402

APP = str(Path(__file__).resolve().parents[1] / "dashboard" / "app.py")
PAGES = ["Overview", "Hypotheses", "Runs", "Run detail", "Failed ideas"]


@pytest.mark.parametrize("page", PAGES)
def test_page_renders_with_data(page):
    at = AppTest.from_file(APP, default_timeout=90).run()
    assert not at.exception, at.exception
    at.sidebar.radio[0].set_value(page).run()
    assert not at.exception, at.exception


@pytest.mark.parametrize("page", PAGES)
def test_page_renders_on_empty_db(page, tmp_path, monkeypatch):
    import streamlit as st

    from proplab.db import store

    monkeypatch.setattr(store, "DB_PATH", tmp_path / "empty.db")
    st.cache_resource.clear()
    st.cache_data.clear()
    try:
        at = AppTest.from_file(APP, default_timeout=90).run()
        assert not at.exception, at.exception
        at.sidebar.radio[0].set_value(page).run()
        assert not at.exception, at.exception
    finally:
        st.cache_resource.clear()
        st.cache_data.clear()
