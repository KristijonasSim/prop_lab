"""THE FACTORY FLOOR — the heartbeat, and the state the page draws from.

Kris, 2026-09-23: *"i would love to see live what is happening... i want to
launch that page and understand everything what is going on there."*

What these pin is the difference between a dashboard and a decoration: the
uptime must mean "without interruption", a half-written beat must never be
read, and the page must never be able to start a run.
"""
from __future__ import annotations

import json
import time

import pytest

from factory import dashboard, live
from factory.spec import Condition, Strategy, Term


@pytest.fixture
def beatfile(tmp_path):
    return tmp_path / "live.json"


# ------------------------------------------------------------- the heartbeat
def test_a_missing_beat_reads_as_idle_not_as_a_crash(beatfile):
    b = live.read(beatfile)
    assert b.step == 0 and b.label == "idle"
    assert not live.is_live(b)


def test_a_corrupt_beat_reads_as_idle(beatfile):
    """The dashboard polls this file on a timer while another process writes
    it. Garbage must degrade to 'idle', never to a stack trace on the page."""
    beatfile.write_text("{not json")
    assert live.read(beatfile).label == "idle"


def test_the_beat_is_written_atomically(beatfile):
    """A reader on a 2s timer will eventually hit a write. os.replace makes
    that impossible to observe, so there is no torn read to handle."""
    live.beat(3, "quick check", path=beatfile)
    assert json.loads(beatfile.read_text())["step"] == 3
    assert not list(beatfile.parent.glob("*.tmp"))


def test_uptime_is_carried_forward_across_steps(beatfile):
    first = live.beat(1, "ideas", path=beatfile)
    time.sleep(0.05)
    later = live.beat(4, "repair", path=beatfile)
    assert later.started == first.started
    assert live.uptime(later) > 0


def test_uptime_restarts_after_a_long_gap(beatfile, monkeypatch):
    """KRIS ASKED FOR THE UNBROKEN STRETCH. A factory that was down for a day
    and came back has not been running for a week, and a counter that says it
    has is worse than no counter at all."""
    live.beat(1, "ideas", path=beatfile)
    d = json.loads(beatfile.read_text())
    d["updated"] = time.time() - (live.STALE_AFTER + 60)
    d["started"] = d["updated"] - 100_000
    beatfile.write_text(json.dumps(d))
    fresh = live.beat(2, "build", path=beatfile)
    assert fresh.started > d["started"]
    assert live.uptime(fresh) < 5


def test_a_stale_beat_is_not_live(beatfile):
    live.beat(3, "quick check", path=beatfile)
    d = json.loads(beatfile.read_text())
    d["updated"] = time.time() - (live.STALE_AFTER + 1)
    beatfile.write_text(json.dumps(d))
    assert not live.is_live(live.read(beatfile))
    assert live.uptime(live.read(beatfile)) == 0.0


def test_counts_accumulate_across_beats(beatfile):
    """Step 3 reports its tally, then step 5 reports another. A beat that
    replaced the whole dict would blank the line every time it moved on."""
    live.beat(3, "quick check", counts={"step3_pass": 2}, path=beatfile)
    b = live.beat(5, "luck check", counts={"step4_repaired": 1}, path=beatfile)
    assert b.counts == {"step3_pass": 2, "step4_repaired": 1}


def test_a_beat_with_no_counts_keeps_the_ones_already_there(beatfile):
    live.beat(3, "quick check", counts={"step3_pass": 2}, path=beatfile)
    assert live.beat(4, "repair", path=beatfile).counts == {"step3_pass": 2}


def test_every_step_in_the_workflow_has_a_station():
    """The page draws one station per entry and the diagram has seven."""
    assert [n for n, _, _ in live.STEPS] == [1, 2, 3, 4, 5, 6, 7]


# ------------------------------------------------------------------ the state
def test_the_state_has_everything_the_page_draws():
    s = dashboard.state()
    assert {"live", "uptime_s", "beat", "steps", "queue", "funnel", "gates",
            "by_source", "survivors", "candidates", "runs", "passes"} <= set(s)
    assert len(s["steps"]) == 7


def test_the_state_is_json_serialisable():
    """It is served straight over HTTP; a stray numpy float would 500 the page
    rather than show a number."""
    json.dumps(dashboard.state())


def test_the_gate_breakdown_names_every_gate_step_3_can_fail():
    from factory import repair

    g = dashboard._gates()
    assert set(g) == {"trades", "cost", "concentration", "drift", "other"}
    assert all(isinstance(v, int) for v in g.values())
    _ = repair


def test_the_funnel_never_reports_more_survivors_than_ideas():
    f = dashboard._funnel()
    assert f["step6_pass"] <= f["ideas"]
    assert f["step7"] <= f["ideas"]


def test_the_dashboard_has_no_route_that_starts_a_run():
    """A dashboard that can launch a pass is one that launches by accident, on
    a box that also runs a live bot. It watches and does nothing else."""
    src = (dashboard.ROOT / "factory" / "dashboard.py").read_text()
    assert "do_POST" not in src
    assert "run_once" not in src


def test_the_server_binds_to_localhost_only():
    assert dashboard.HOST == "127.0.0.1"


# --------------------------------------------------------- the source layer
def test_every_catalogue_source_appears_even_with_nothing_against_it():
    """Kris, 2026-09-23: he picks a source, then reads its numbers. A source
    missing from the page is indistinguishable from one that found nothing,
    and the catalogue exists to say which is which."""
    from factory.sources import catalogue

    keys = {r["key"] for r in dashboard.per_source()}
    assert {c.key for c in catalogue.CATALOGUE} <= keys


def test_a_source_that_is_not_ready_carries_the_reason():
    """A source showing 0 found and no explanation reads as 'this found
    nothing' when it means 'this has not been run'."""
    rows = {r["key"]: r for r in dashboard.per_source()}
    assert rows["quantpedia"]["status"] != "ready"
    assert len(rows["quantpedia"]["note"]) > 20
    assert rows["tradingview"]["note"]


def test_the_drain_order_cannot_disagree_with_the_catalogue():
    """SOURCE_ORDER used to be hand-written and an unlisted source sorted last,
    which is how the agent's first batch went untested."""
    from factory import queue
    from factory.sources import catalogue

    assert queue.SOURCE_ORDER == catalogue.ORDER
    assert catalogue.ORDER[0] == "tradingview"


def test_a_source_row_adds_up():
    for r in dashboard.per_source():
        assert r["found"] == r["waiting"] + r["tested"]
        assert r["failed"] <= r["tested"]
        assert r["scored7"] <= r["passed3"]


def test_an_unregistered_source_still_gets_a_row():
    from factory.sources import catalogue

    s = catalogue.get("nowhere")
    assert s.key == "nowhere" and s.label == "nowhere"


# ------------------------------------------------------------- clearing it
def test_reset_archives_rather_than_deletes(tmp_path, monkeypatch):
    """CLAUDE.md: the failures are the denominator, and core/searchcost.py
    charges every trial. A trial does not become uncharged because the page
    stopped showing it."""
    from factory import queue, reset

    monkeypatch.setattr(queue, "DIR", tmp_path)
    monkeypatch.setattr(queue, "TRIED", tmp_path / "tried.jsonl")
    monkeypatch.setattr(queue, "QUEUE", tmp_path / "queue.jsonl")
    monkeypatch.setattr(queue, "SURVIVORS", tmp_path / "survivors.jsonl")
    monkeypatch.setattr(reset, "ARCHIVE", tmp_path / "archive")

    s = Strategy(name="x", side="long",
                 entry=(Condition(Term("price"), "above", Term("sma", 50)),),
                 source="tradingview")
    queue.mark_tried(s, "FAIL", "died on trades", step=3, gate="trades")
    out = reset.reset()

    archived = list((tmp_path / "archive").rglob("tried.jsonl"))
    assert archived, "nothing was archived"
    assert out["archived"]["tried.jsonl"] == 1


def test_reset_keeps_the_dedupe_but_not_the_counts(tmp_path, monkeypatch):
    """THE TWO THINGS THAT MUST BOTH BE TRUE after clearing the board: the idea
    is never re-tested, and the cleared board reports zero. A first version
    carried the rows forward unflagged and a freshly cleared board reported 158
    tested ideas."""
    from factory import queue, reset

    monkeypatch.setattr(queue, "DIR", tmp_path)
    monkeypatch.setattr(queue, "TRIED", tmp_path / "tried.jsonl")
    monkeypatch.setattr(queue, "QUEUE", tmp_path / "queue.jsonl")
    monkeypatch.setattr(queue, "SURVIVORS", tmp_path / "survivors.jsonl")
    monkeypatch.setattr(reset, "ARCHIVE", tmp_path / "archive")

    s = Strategy(name="x", side="long",
                 entry=(Condition(Term("price"), "above", Term("sma", 50)),),
                 source="tradingview")
    queue.mark_tried(s, "FAIL", "died on trades", step=3, gate="trades")
    reset.reset()

    assert s.fingerprint() in queue.fingerprints()          # never re-tested
    kept = queue.rows(queue.TRIED)
    assert len(kept) == 1 and kept[0]["carried"] == 1
    assert "verdict" not in kept[0] and "died_at" not in kept[0]


def test_forget_drops_the_fingerprints(tmp_path, monkeypatch):
    from factory import queue, reset

    monkeypatch.setattr(queue, "DIR", tmp_path)
    monkeypatch.setattr(queue, "TRIED", tmp_path / "tried.jsonl")
    monkeypatch.setattr(queue, "QUEUE", tmp_path / "queue.jsonl")
    monkeypatch.setattr(queue, "SURVIVORS", tmp_path / "survivors.jsonl")
    monkeypatch.setattr(reset, "ARCHIVE", tmp_path / "archive")

    s = Strategy(name="x", side="long",
                 entry=(Condition(Term("price"), "above", Term("sma", 50)),),
                 source="tradingview")
    queue.mark_tried(s, "FAIL", "", step=3, gate="trades")
    out = reset.reset(forget=True)
    assert out["dedupe_kept"] == 0
    assert s.fingerprint() not in queue.fingerprints()


def test_an_idle_beat_is_not_a_running_factory(tmp_path):
    """`factory.reset` used to write one to clear the board and the header
    showed RUNNING with a two-second uptime on an empty board."""
    f = tmp_path / "live.json"
    live.beat(0, "idle", path=f)
    assert not live.is_live(live.read(f))
    live.beat(0, "resting", path=f)
    assert live.is_live(live.read(f))        # between passes IS running


# -------------------------------------------------------- the grammar gaps
def test_a_refused_translation_is_kept_not_printed(tmp_path):
    """A named gap is the most actionable thing the factory produces - it is a
    term that multiplies the 308 rules the enumerator can build. They were
    going to a terminal and being lost."""
    from factory.sources import tradingview

    f = tmp_path / "skipped.jsonl"
    n = tradingview.record_skips(
        [("squeeze", "grammar gap: composite bands"),
         ("other", "no JSON object in output")], path=f)
    assert n == 2
    rows = [json.loads(l) for l in f.read_text().splitlines()]
    assert [r["gap"] for r in rows] == [True, False]


def test_the_same_script_is_not_recorded_twice(tmp_path):
    from factory.sources import tradingview

    f = tmp_path / "skipped.jsonl"
    tradingview.record_skips([("squeeze", "grammar gap: bands")], path=f)
    assert tradingview.record_skips([("squeeze", "grammar gap: bands")], path=f) == 0


def test_one_idea_counts_once_even_when_it_is_in_two_files():
    """An idea that passes step 3 and then fails step 6 is written by BOTH
    `keep` and `mark_tried`. Summing the files reported Kris's single
    translated script as two tested ideas."""
    rows = {r["key"]: r for r in dashboard.per_source()}
    for r in rows.values():
        assert r["tested"] >= r["passed3"]
        assert r["tested"] >= r["failed"]
        assert r["read"] == r["waiting"] + r["tested"] + r["refused"]


def test_the_fingerprint_matches_the_strategy_it_came_from():
    """`_fingerprint` reads a stored dict rather than rebuilding a Strategy,
    so two records of the SAME idea must collapse whatever file they came
    from - one carries `reached`, the other `died_at`."""
    from dataclasses import asdict

    s = Strategy(name="x", side="long",
                 entry=(Condition(Term("wpr", 21), "above",
                                  Term("const", value=-20.0), hold=2),))
    a = {**asdict(s), "reached": 3}
    b = {**asdict(s), "died_at": 6, "gate": "holdout"}
    assert dashboard._fingerprint(a) == dashboard._fingerprint(b)

    other = Strategy(name="y", side="long",
                     entry=(Condition(Term("wpr", 21), "above",
                                      Term("const", value=-20.0), hold=5),))
    assert dashboard._fingerprint(asdict(other)) != dashboard._fingerprint(a)


def test_a_finished_pass_is_not_counted_twice(tmp_path, monkeypatch):
    """The FINAL beat of a pass is `resting`, which is still "live", and its
    counts are the same ones already written to the run record. Adding both
    reported Kris's single script as 46 cell-tests out of a possible 24."""
    from factory import nightly

    monkeypatch.setattr(nightly, "RUNS", tmp_path / "runs.jsonl")
    monkeypatch.setattr(live, "STATE", tmp_path / "live.json")
    nightly.record({"gates": {"trades": 17, "cost": 6}})
    live.beat(0, "resting", counts={"gates": {"trades": 17, "cost": 6}},
              path=tmp_path / "live.json")
    assert dashboard._gates()["trades"] == 17


def test_a_pass_in_flight_still_shows_its_running_tally(tmp_path, monkeypatch):
    """The other half: without the in-flight beat the panel that explains the
    bottleneck sits empty for the whole of the first pass."""
    from factory import nightly

    monkeypatch.setattr(nightly, "RUNS", tmp_path / "runs.jsonl")
    monkeypatch.setattr(live, "STATE", tmp_path / "live.json")
    live.beat(3, "quick check", counts={"gates": {"trades": 9}},
              path=tmp_path / "live.json")
    assert dashboard._gates()["trades"] == 9


def test_every_source_carries_its_own_numbers():
    """Kris, 2026-09-23: *"when i go to quantpedia tab i see same stats... we
    didint test nothing in quantpedia."* Only the header was filtered - the
    funnel, the stop breakdown, the luck check and the run list were global,
    so an empty source displayed another source's work."""
    rows = {r["key"]: r for r in dashboard.per_source()}
    for key, r in rows.items():
        assert {"funnel", "runs", "step5", "survivors", "candidates",
                "stopped"} <= set(r)
        assert r["funnel"]["ideas"] == r["tested"]
        if r["tested"] == 0:
            assert r["funnel"]["step3_pass"] == 0
            assert r["runs"] == []
            assert r["step5"] is None
            assert r["survivors"] == [] and r["candidates"] == []
            assert r["stopped"] == {}


def test_a_source_only_sees_runs_its_ideas_were_in():
    for r in dashboard.per_source():
        for run in r["runs"]:
            assert r["key"] in (run.get("by_source") or {})


def test_a_mixed_batch_says_so_on_the_luck_check():
    """The null scores a BATCH, not a source. When a batch mixed sources the
    page has to say that rather than present p as this source's number."""
    for r in dashboard.per_source():
        if r["step5"]:
            assert "only_source" in r["step5"] and "batch" in r["step5"]


def test_every_idea_is_counted_once_at_the_point_it_stopped():
    """One row per idea, not per cell-test - counting cells is what made a
    single script look like 46 tests."""
    for r in dashboard.per_source():
        assert sum(r["stopped"].values()) == r["tested"]
