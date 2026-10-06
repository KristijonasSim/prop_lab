"""The TradingView fetcher and the single-source queue. Offline - no network."""
from __future__ import annotations

from dataclasses import replace

from factory import queue
from factory.sources import invent, tvfetch


_PAGE = ('{"chart_url":"https://www.tradingview.com/script/AbC123-My-Strat/",'
         '"is_public":true,"script_type":"strategy","script_access":1,'
         '"script_id_part":"PUB;0123abcd"}'
         '{"chart_url":"https://www.tradingview.com/script/XyZ9-Other/",'
         '"script_type":"indicator","script_access":1,'
         '"script_id_part":"PUB;ffff0000"}')


def test_listing_reads_every_card(monkeypatch):
    monkeypatch.setattr(tvfetch, "_get", lambda url, timeout=30: (200, _PAGE.encode()))
    cards = tvfetch.listing("strategies", 1)
    assert [c["id"] for c in cards] == ["PUB;0123abcd", "PUB;ffff0000"]
    assert cards[0]["kind"] == "strategy"


def test_protected_scripts_are_recorded_not_saved(tmp_path, monkeypatch):
    """A script with no source is marked seen, so it is never asked for again."""
    monkeypatch.setattr(tvfetch, "SEEN", tmp_path / "seen.jsonl")
    monkeypatch.setattr(tvfetch, "listing",
                        lambda kind, page: [] if page > 1 else
                        [{"id": "PUB;1", "url": "https://x/script/a-B/", "kind": "strategy"},
                         {"id": "PUB;2", "url": "https://x/script/c-D/", "kind": "strategy"}])
    monkeypatch.setattr(tvfetch, "source", lambda pid: (
        {"source": "//@version=6\nstrategy('x')", "scriptAccess": "open_no_auth",
         "scriptName": "open one"} if pid == "PUB;1" else
        {"scriptAccess": "protected", "scriptName": "closed one"}))
    got = tvfetch.fetch(5, kinds=("strategies",), folder=tmp_path, log=lambda *_: None)
    assert [p.name for p in got] == ["tv_a_b.pine"]
    assert set(tvfetch.seen()) == {"PUB;1", "PUB;2"}
    assert tvfetch.fetch(5, kinds=("strategies",), folder=tmp_path,
                         log=lambda *_: None) == []


def test_take_by_source_leaves_the_rest_of_the_queue(tmp_path, monkeypatch):
    monkeypatch.setattr(queue, "DIR", tmp_path)
    monkeypatch.setattr(queue, "QUEUE", tmp_path / "queue.jsonl")
    monkeypatch.setattr(queue, "TRIED", tmp_path / "tried.jsonl")
    a, b, c = invent.generate(limit=3)
    queue.add([a, replace(b, source="tradingview"), c], quiet=True)
    assert queue.take("tradingview").source == "tradingview"
    assert queue.take("tradingview") is None
    assert queue.status()["waiting"] == 2
