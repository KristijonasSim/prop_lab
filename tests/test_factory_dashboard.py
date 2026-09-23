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
