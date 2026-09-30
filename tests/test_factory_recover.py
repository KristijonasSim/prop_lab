"""A run killed mid-batch must not lose the ideas it took (2026-09-28 shutdown)."""
from factory import queue
from factory.spec import Condition, Strategy, Term


def _q(tmp_path, monkeypatch):
    for name, f in (("DIR", ""), ("QUEUE", "queue.jsonl"), ("TRIED", "tried.jsonl"),
                    ("SURVIVORS", "survivors.jsonl"),
                    ):
        monkeypatch.setattr(queue, name, tmp_path / f if f else tmp_path)


def _s(n):
    return Strategy(name=f"s{n}", source="tradingview",
                    entry=(Condition(Term("sma", 10 + n), "above", Term("price")),))


def test_killed_run_gives_its_ideas_back(tmp_path, monkeypatch):
    _q(tmp_path, monkeypatch)
    queue.add([_s(1), _s(2), _s(3)], quiet=True)
    a, b = queue.take("tradingview"), queue.take("tradingview")
    queue.mark_tried(a, "FAIL", "done before the kill")
    # killed here - no finish()
    assert queue.status()["waiting"] == 1
    assert queue.recover() == 1                  # b back, a already tried
    assert queue.status()["waiting"] == 2
    assert queue.recover() == 0


def test_finished_run_leaves_nothing_to_recover(tmp_path, monkeypatch):
    _q(tmp_path, monkeypatch)
    queue.add([_s(1)], quiet=True)
    queue.take()
    queue.finish()
    assert queue.recover() == 0 and queue.status()["waiting"] == 0


def test_an_idea_that_kills_the_run_twice_is_retired(tmp_path, monkeypatch):
    _q(tmp_path, monkeypatch)
    queue.add([_s(1)], quiet=True)
    queue.take()
    assert queue.recover() == 1
    queue.take()
    assert queue.recover() == 0
    assert queue.status() == {"waiting": 0, "tried": 1, "waiting_by_source": {}}
