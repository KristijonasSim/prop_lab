"""STEPS 5, 6 and 7 — the luck check, the holdout re-check and the evaluation.

The designs are in `docs/STEP5.md`, `STEP6.md` and `STEP7.md`. What these pin
is what each step is FOR, because all three are easy to build as something
weaker that looks the same from outside:

* step 5 has to scramble the market while keeping its drift, its calendar and
  its dead bars - a null that flattens gold's 123% rise is one every long rule
  beats for the wrong reason;
* step 6 has to test bars the idea has NOT been selected on, not re-read the
  three years it already passed;
* step 7 has to report accounts-consumed beside expected days, which is the
  method debt the withdrawn top-N result left behind.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from factory import cells, check, evaluate, null, recheck
from factory.spec import Condition, Strategy, Term


def _bars(n=3000, *, drift=0.0004, seed=7, start="2024-01-01", dead_every=0):
    rng = np.random.default_rng(seed)
    close = 100 * np.exp(np.cumsum(rng.standard_normal(n) * 0.002 + drift))
    idx = pd.date_range(start, periods=n, freq="1h", tz="UTC")
    df = pd.DataFrame({"open": close, "high": close * 1.002,
                       "low": close * 0.998, "close": close,
                       "volume": np.ones(n), "hour": idx.hour.astype(float)},
                      index=idx)
    if dead_every:
        dead = np.zeros(n, bool)
        dead[::dead_every] = True
        df.loc[dead, "volume"] = 0.0
        frozen = df["close"].where(~dead).ffill().bfill()
        for col in ("open", "high", "low", "close"):
            df.loc[dead, col] = frozen[dead]
    return df


def _simple(side="long", **kw) -> Strategy:
    return Strategy(name="s", side=side,
                    entry=(Condition(Term("price"), "above",
                                     Term("const", value=0.0)),), **kw)


# =============================================================== STEP 5
def test_the_scramble_keeps_the_calendar_exactly():
    """Timestamps, the clock and the volume column never move.

    An hour-concentrated event compared against a population drawn from every
    hour is gifted the difference between them - `core/probe.py` was caught
    doing exactly this on 2026-09-13. Scrambling by ROW rather than by time is
    what makes this null hour-matched, so it is pinned.
    """
    f = _bars(2000, dead_every=17)
    s = null.scramble(f, seed=3, block=24)
    assert s.index.equals(f.index)
    assert (s["hour"].values == f["hour"].values).all()
    assert (s["volume"].values == f["volume"].values).all()


def test_the_scramble_keeps_the_market_closed_where_it_was_closed():
    """21.5% of the gold series is padded weekend at a frozen price. A null
    that trades through it is testing a market that does not exist."""
    f = _bars(2000, dead_every=11)
    s = null.scramble(f, seed=5, block=24)
    dead = f["volume"].values == 0
    assert dead.any()
    o, h, l, c = (s[k].values for k in ("open", "high", "low", "close"))
    assert np.allclose(o[dead], c[dead])
    assert np.allclose(h[dead], c[dead])
    assert np.allclose(l[dead], c[dead])


def test_the_scramble_keeps_the_drift_and_the_volatility():
    """THE POINT OF THE WHOLE FILE. Gold rose 123% over the cached window; a
    null without that rise is beaten by every long rule for a reason that has
    nothing to do with edge. Averaged over seeds the null's total return has to
    land on the real one, and its bar-to-bar volatility has to match."""
    f = _bars(4000, drift=0.0006)
    real = f["close"].iloc[-1] / f["close"].iloc[0]
    rets, vols = [], []
    for seed in range(12):
        s = null.scramble(f, seed=seed, block=24)
        rets.append(s["close"].iloc[-1] / s["close"].iloc[0])
        vols.append(np.diff(np.log(s["close"].values)).std())
    assert real * 0.7 < float(np.mean(rets)) < real * 1.4
    real_vol = np.diff(np.log(f["close"].values)).std()
    assert real_vol * 0.9 < float(np.mean(vols)) < real_vol * 1.1


def test_the_scramble_actually_destroys_the_bar_order():
    """It has to be a different path, not a re-labelled one."""
    f = _bars(2000)
    s = null.scramble(f, seed=1, block=24)
    assert not np.allclose(s["close"].values, f["close"].values)


def test_the_scramble_produces_sane_bars():
    f = _bars(2000, dead_every=13)
    s = null.scramble(f, seed=2, block=24)
    assert (s["high"] >= s[["open", "close"]].max(axis=1) - 1e-9).all()
    assert (s["low"] <= s[["open", "close"]].min(axis=1) + 1e-9).all()
    assert (s[["open", "high", "low", "close"]] > 0).values.all()


def test_a_series_too_short_to_block_resample_returns_nothing():
    """Better an empty cell that `check_all` skips than a null built from three
    blocks pretending to be a market."""
    assert not len(null.scramble(_bars(40), seed=0, block=24))


def test_the_loader_is_a_drop_in_for_cells_load():
    """`check_all(loader=...)` is the whole injection point of step 5. If the
    loader does not match `cells.load`'s shape the null runs a different
    pipeline from the real one and the counts are not comparable."""
    ld = null.loader(0)
    real, fake = cells.load("XAUUSD", "1h"), ld("XAUUSD", "1h")
    assert list(fake.columns) == list(real.columns)
    assert len(fake) == len(real)
    assert fake is ld("XAUUSD", "1h")             # cached within a seed


def test_the_pipeline_counts_both_stages_of_survivor():
    """A repaired survivor counts, and it counts separately - step 4 is only
    earning its place if repaired ideas do not die at step 6 more often."""
    t = null.Tally(label="x", ideas=10, passed_step3=2, repaired=1)
    assert t.survivors == 3


def test_the_p_value_cannot_claim_more_than_the_seeds_support():
    """With ten seeds the smallest reportable value is 1/11. Quoting a smaller
    number than the seed count supports is how this repo has been wrong."""
    ideas = [_simple()]
    res = null.compare(ideas, seeds=2, cell_list=[("XAUUSD", "4h")],
                       control_seeds=3, do_repair=False)
    assert res["p_value"] >= 1 / 3
    assert res["seeds"] == 2


# =============================================================== STEP 6
def test_the_holdout_does_not_overlap_the_window_the_idea_was_selected_on():
    """THE CORRECTION THE STEP NEEDED. A five-year window contains the three
    years the idea already passed, so two thirds of that test is a re-read of
    the exam paper."""
    lo, _ = cells.common_window()
    h = cells.holdout("XAUUSD", "1h")
    assert len(h)
    assert h.index[-1] < lo


def test_the_holdout_stops_where_the_step_3_window_starts():
    lo, _ = cells.common_window()
    h = cells.holdout("BTCUSDT", "1h")
    m = cells.load("BTCUSDT", "1h")
    assert h.index[-1] < m.index[0]
    assert h.index[0] >= lo - pd.DateOffset(years=cells.RECHECK_YEARS - 3)


def test_a_cell_with_no_holdout_is_no_data_and_is_not_a_pass():
    """Treating a missing test as a passed one is how a pipeline quietly stops
    testing. It has to be its own verdict."""
    r = recheck.Recheck(idea="x", market="XAGUSD", tf="1h")
    assert r.verdict == "NO DATA"
    assert r.verdict != "PASS"


def test_coverage_reports_every_cell_and_marks_the_unusable_ones():
    df = recheck.coverage()
    assert len(df) == len(cells.all_cells())
    assert set(df.columns) >= {"market", "tf", "days", "usable"}
    assert df.usable.dtype == bool


def test_the_recheck_runs_the_same_gates_as_step_3():
    """Same four questions, different bars. If step 6 invented its own gates a
    survivor could die for a reason step 3 would never have raised."""
    s = _simple()
    r = recheck.recheck(s, "XAUUSD", "4h", control_seeds=3)
    assert r.verdict in ("PASS", "FAIL", "NO DATA")
    if r.holdout is not None:
        assert r.full is not None
        assert r.holdout_days >= recheck.MIN_HOLDOUT_DAYS


# =============================================================== STEP 7
def test_accounts_consumed_is_one_over_the_pass_rate():
    """THE METHOD DEBT FROM 2026-09-17. `expected_days = median_days /
    pass_rate` treats a blown account as free, so any lever that raises trade
    frequency buys speed by spending evaluation fees. 39.3% pass is 2.5
    accounts per funded seat and the board never said so."""
    row = {"risk": 0.02, "pass_rate": 0.4, "median_days": 10.0,
           "expected_days": 25.0, "max_dd": -0.05, "fail_daily": 0.2,
           "fail_max": 0.4}
    r = evaluate._rung(row, pd.Series(dtype=float), resamples=10)
    assert r.accounts == pytest.approx(2.5)


def test_a_rung_that_never_funds_reports_no_accounts_rather_than_infinity():
    row = {"risk": 0.02, "pass_rate": 0.0, "median_days": None,
           "expected_days": None, "max_dd": -0.05, "fail_daily": 0.5,
           "fail_max": 0.5}
    r = evaluate._rung(row, pd.Series(dtype=float), resamples=10)
    assert r.accounts is None
    assert "-" in str(r)


def test_the_evaluation_returns_a_curve_and_refuses_to_pick_a_rung():
    """Kris, 2026-09-21: pass % and days pull against each other through risk,
    so a candidate has a curve. Step 7 prints it; the choice is his."""
    s = Strategy(name="b", side="long",
                 entry=(Condition(Term("price"), "cross_above",
                                  Term("highest", 20)),))
    ev = evaluate.evaluate(s, "XAUUSD", "4h", resamples=20)
    assert len(ev.rungs) > 1
    assert {r.risk for r in ev.rungs} == set(evaluate.riskladder.RISK_LADDER)
    assert ev.n_trades > 0


def test_the_evaluation_says_when_a_candidate_misses_the_pace_target():
    """5-14 days is the phase constraint. A candidate outside it has to say so
    on its own line rather than leave the reader to compare."""
    s = Strategy(name="b", side="long",
                 entry=(Condition(Term("price"), "cross_above",
                                  Term("highest", 200)),))
    ev = evaluate.evaluate(s, "XAUUSD", "4h", resamples=20)
    assert ev.note
    assert ("pace target" in ev.note or "TOO SLOW" in ev.note
            or "funds no account" in ev.note or ev.note == "no trades")


def test_the_five_year_frame_is_the_holdout_then_the_window_in_order():
    df = evaluate.five_year_frame("XAUUSD", "1h")
    assert df.index.is_monotonic_increasing
    assert not df.index.has_duplicates
    assert len(df) > len(cells.load("XAUUSD", "1h"))


def test_an_empty_cell_evaluates_to_a_note_and_not_a_crash():
    ev = evaluate.evaluate(_simple(), "XAUUSD", "1h",
                           frame=cells.load("XAUUSD", "1h").iloc[0:0])
    assert ev.note == "no data"
    assert ev.rungs == []


# =============================================================== the queue bug
def test_a_tried_row_can_be_read_back(tmp_path, monkeypatch):
    """THE DEDUPE DEPENDS ON THIS. `mark_tried` writes `verdict` and
    `note_result` beside the strategy and `fingerprints()` reads that file, so
    a parse error there stops the queue noticing it has seen an idea before -
    which is the queue's only job. Found 2026-09-23 when step 5 first called
    `take()`.
    """
    from factory import queue

    monkeypatch.setattr(queue, "DIR", tmp_path)
    monkeypatch.setattr(queue, "QUEUE", tmp_path / "queue.jsonl")
    monkeypatch.setattr(queue, "TRIED", tmp_path / "tried.jsonl")
    monkeypatch.setattr(queue, "SURVIVORS", tmp_path / "survivors.jsonl")

    s = _simple()
    queue.mark_tried(s, "FAIL", "died on trade count")
    queue.keep(s, "repaired")
    assert queue._read(queue.TRIED)[0].fingerprint() == s.fingerprint()
    assert queue._read(queue.SURVIVORS)[0].fingerprint() == s.fingerprint()
    assert s.fingerprint() in queue.fingerprints()


# =============================================================== the runner
def test_the_runner_records_every_idea_it_takes(tmp_path, monkeypatch):
    """Pass or fail, an idea that has been through the pipeline is written down
    - the failures are the denominator, and the queue must never re-offer it."""
    from factory import queue, run

    monkeypatch.setattr(queue, "DIR", tmp_path)
    monkeypatch.setattr(queue, "QUEUE", tmp_path / "queue.jsonl")
    monkeypatch.setattr(queue, "TRIED", tmp_path / "tried.jsonl")
    monkeypatch.setattr(queue, "SURVIVORS", tmp_path / "survivors.jsonl")

    ideas = [Strategy(name="a", side="long",
                      entry=(Condition(Term("price"), "cross_above",
                                       Term("highest", 200)),)),
             Strategy(name="b", side="long",
                      entry=(Condition(Term("price"), "cross_above",
                                       Term("highest", 100)),))]
    survivors, rows = run._survivors(ideas, [("XAUUSD", "4h")], control_seeds=3)
    assert len(rows) == len(ideas)
    assert len(queue._read(queue.TRIED)) + len(queue._read(queue.SURVIVORS)) == len(ideas)
    for s, m, tf, repaired in survivors:
        assert (m, tf) == ("XAUUSD", "4h")
        assert isinstance(repaired, bool)
