"""STEP 1 with a model in it — the proposer, the Pine translator, the runner.

Kris, 2026-09-23: *"on a simple script that runs locally we wont achieve
anything without someone who can think."*

What these pin is the boundary. A model is allowed to say WHAT to test and
nothing else: it fills in a fixed form, every field is validated against the
grammar, and anything it cannot express it must NAME rather than approximate.
No test here calls a model - every one passes `text=` so the parse and the
validation are exercised without a network.
"""
from __future__ import annotations

import json

import pytest

from factory.sources import agent, tradingview
from factory.spec import INDICATORS, Strategy


def _idea(**kw) -> dict:
    d = {"side": "long",
         "entry": [{"left": {"kind": "price"}, "op": "above",
                    "right": {"kind": "sma", "length": 50}}],
         "stop_atr": 2.0, "target_atr": 3.0, "max_hold": 48,
         "name": "above the 50",
         "note": "trend followers must add once price clears the average and "
                 "cannot opt out of their own signal"}
    d.update(kw)
    return d


# ------------------------------------------------------- what it may express
def test_a_valid_proposal_becomes_a_strategy():
    s = agent.validate(_idea())
    assert isinstance(s, Strategy)
    assert s.source == "agent"
    assert s.label() == "long when price above sma50"


def test_an_unknown_indicator_is_refused_not_guessed():
    """A guessed rule occupies a test slot, is charged to the ledger, and says
    nothing about what was proposed. Silence is cheap and a guess is not."""
    bad = _idea(entry=[{"left": {"kind": "supertrend", "length": 10},
                        "op": "above", "right": {"kind": "price"}}])
    with pytest.raises(agent.ProposalError, match="unknown indicator"):
        agent.validate(bad)


def test_free_python_is_not_a_thing_the_model_can_return():
    """The safety property. The model fills a form; it never writes code, so
    `guard.Window`'s negative-only indexing still covers everything it makes."""
    with pytest.raises(agent.ProposalError):
        agent.validate({"side": "long", "entry": "close[1] > close[-1]",
                        "note": "x" * 40})


def test_the_clock_is_not_offered_to_the_generator():
    """`hour` exists for step 4's session repairs. Letting step 1 use it turns
    the idea source into a session search, which `docs/STEP4.md` keeps fixed."""
    assert "hour" in INDICATORS
    with pytest.raises(agent.ProposalError, match="step 4"):
        agent.validate(_idea(entry=[{"left": {"kind": "hour"}, "op": "above",
                                     "right": {"kind": "const", "value": 8.0}}]))


@pytest.mark.parametrize("field,value", [
    ("stop_atr", 50.0), ("target_atr", 0.0), ("max_hold", 5000),
])
def test_out_of_range_numbers_are_refused(field, value):
    with pytest.raises(agent.ProposalError, match=field):
        agent.validate(_idea(**{field: value}))


def test_a_condition_comparing_a_term_to_itself_is_refused():
    with pytest.raises(agent.ProposalError, match="same term"):
        agent.validate(_idea(entry=[{"left": {"kind": "sma", "length": 20},
                                     "op": "above",
                                     "right": {"kind": "sma", "length": 20}}]))


# ------------------------------------------------------------ the mechanism
def test_an_idea_without_a_mechanism_is_refused():
    """THE WHOLE REASON FOR USING A MODEL. `CLAUDE.md` asks for the mechanism -
    who is on the other side - to be stated before results, and an enumerator
    can never supply one. An idea with no note is an enumerated idea wearing a
    model's clothes."""
    with pytest.raises(agent.ProposalError, match="MECHANISM"):
        agent.validate(_idea(note="momentum works"))


def test_the_prompt_tells_the_model_the_binding_constraint():
    """87% of everything dies on trade count. A prompt that does not say so is
    a prompt that buys another batch of rules firing twice a year."""
    p = agent._prompt(5, [])
    assert "TRADE COUNT" in p
    assert agent.TRADE_FLOOR in p
    assert "states, not rare events" in p


def test_the_prompt_carries_what_has_already_been_tested():
    p = agent._prompt(5, ["long|price above sma50|stop2|tgt3|hold48"])
    assert "ALREADY TESTED" in p
    assert "price above sma50" in p


# ------------------------------------------------------------ batch handling
def test_a_bad_item_is_dropped_and_the_good_ones_survive():
    """An unattended loop that stops on one bad parse is not unattended."""
    text = json.dumps([_idea(), _idea(side="sideways"), _idea(name="b",
                       entry=[{"left": {"kind": "price"}, "op": "below",
                               "right": {"kind": "lowest", "length": 20}}])])
    kept, rejected = agent.propose(5, text=text, avoid=[])
    assert len(kept) == 2
    assert len(rejected) == 1


def test_duplicates_inside_one_batch_are_dropped():
    text = json.dumps([_idea(), _idea(name="same rule, different name")])
    kept, rejected = agent.propose(5, text=text, avoid=[])
    assert len(kept) == 1
    assert any("already tested" in r for r in rejected)


def test_something_already_tested_is_not_re_offered():
    s = agent.validate(_idea())
    kept, rejected = agent.propose(5, text=json.dumps([_idea()]),
                                   avoid=[s.fingerprint()])
    assert kept == []
    assert rejected


def test_output_wrapped_in_prose_still_parses():
    text = "Here are the ideas:\n```json\n" + json.dumps([_idea()]) + "\n```\nDone."
    kept, _ = agent.propose(1, text=text, avoid=[])
    assert len(kept) == 1


def test_no_json_at_all_raises_with_a_message_for_the_model():
    with pytest.raises(agent.ProposalError, match="no JSON array"):
        agent.propose(1, text="I cannot help with that.", avoid=[])


# --------------------------------------------------- the TradingView reader
_PINE_OK = '''//@version=5
strategy("x")
enter = ta.atr(14) < ta.atr(100) and close > ta.ema(close, 50)
if enter
    strategy.entry("L", strategy.long)
'''


def test_the_regex_runs_first_and_the_model_is_only_paid_for_the_rest(tmp_path):
    """The regex is free, deterministic and reproducible. Whatever it reads
    must never reach a model, or every redeploy costs tokens for nothing."""
    (tmp_path / "ma.pine").write_text(
        'strategy("m")\nlong = ta.crossover(ta.sma(close, 10), ta.sma(close, 50))\n'
        'if long\n    strategy.entry("L", strategy.long)\n')
    got, skipped = tradingview.load(tmp_path, ai=False)
    assert got and not skipped


def test_a_script_outside_the_grammar_names_the_gap_instead_of_guessing():
    """NOT a failure. The model naming the missing Pine feature is the signal
    that widens the grammar - it is the answer to the 308-rule ceiling."""
    s, why = tradingview.translate_ai(
        _PINE_OK, "x", text='{"cannot": "ta.pivothigh is not in the grammar"}')
    assert s is None
    assert why.startswith("grammar gap")
    assert "pivothigh" in why


def test_a_translated_script_is_validated_as_hard_as_a_proposal():
    s, why = tradingview.translate_ai(
        _PINE_OK, "x", text=json.dumps(_idea(entry=[
            {"left": {"kind": "ichimoku", "length": 9}, "op": "above",
             "right": {"kind": "price"}}])))
    assert s is None
    assert "invalid translation" in why


def test_a_good_translation_is_tagged_to_its_source():
    """Provenance survives into the queue, so `nightly.by_source` can say
    whether TradingView ideas outlive the enumerator's."""
    s, why = tradingview.translate_ai(_PINE_OK, "x", text=json.dumps(_idea()))
    assert why == ""
    assert s.source == "tradingview"


def test_a_model_that_returns_nothing_usable_is_a_skip_not_a_crash():
    s, why = tradingview.translate_ai(_PINE_OK, "x", text="sorry, no idea")
    assert s is None
    assert "no JSON object" in why


# ----------------------------------------------------------- the night run
def test_the_run_record_splits_survivors_by_source(tmp_path, monkeypatch):
    """THE NUMBER THAT SAYS WHETHER THE MODEL IS WORTH PAYING FOR. If it is
    not recorded from the first run it cannot be reconstructed later."""
    from factory import nightly, queue

    monkeypatch.setattr(nightly, "RUNS", tmp_path / "runs.jsonl")
    nightly.record({"by_source": {"agent": 10, "invent": 10},
                    "survivors": [{"source": "agent"}, {"source": "agent"}]})
    nightly.record({"by_source": {"agent": 10}, "survivors": []})
    tbl = nightly.by_source()
    assert tbl["agent"] == {"tested": 20, "survived": 2, "rate_pct": 10.0}
    assert tbl["invent"]["survived"] == 0
    _ = queue


def test_the_pass_still_runs_when_the_model_is_unreachable(monkeypatch):
    """The VM has no `claude` CLI at all. A pass that dies without one is a
    pass that cannot run where it is meant to run."""
    def boom(*a, **k):
        raise agent.ProposalError("the `claude` CLI is not on PATH")
    monkeypatch.setattr(agent, "_call", boom)
    res = agent.fill(5)
    assert res["added"] == 0
    assert "error" in res


def test_model_ideas_are_taken_before_enumerated_ones(tmp_path, monkeypatch):
    """A source missing from SOURCE_ORDER sorts LAST. The first nightly run
    queued eight model ideas and then tested eight enumerated ones, because
    'agent' was not in the tuple and 48 enumerated ideas were ahead of them.

    The enumerator is the FLOOR under the queue, not a peer - a floor that is
    drained first is not a floor.
    """
    from factory import queue

    monkeypatch.setattr(queue, "DIR", tmp_path)
    monkeypatch.setattr(queue, "QUEUE", tmp_path / "queue.jsonl")
    monkeypatch.setattr(queue, "TRIED", tmp_path / "tried.jsonl")

    from factory.sources import invent
    enumerated = invent.generate(limit=5)
    proposed = agent.validate(_idea())
    queue.add(enumerated + [proposed], quiet=True)
    assert queue.take().source == "agent"


def test_every_source_the_factory_has_is_ranked():
    """An unranked source is a silently deprioritised one, which is how the
    model's first batch went untested."""
    from factory import queue

    assert {"tradingview", "agent", "invent"} <= set(queue.SOURCE_ORDER)


@pytest.mark.parametrize("n", [0, 1, 2, 401])
def test_a_degenerate_lookback_is_refused(n):
    """The first live batch proposed `price above vwap1`. A one-bar average is
    the bar itself, so the condition is trivially true or false and the test
    slot is spent on nothing."""
    with pytest.raises(agent.ProposalError, match="length"):
        agent.validate(_idea(entry=[{"left": {"kind": "price"}, "op": "above",
                                     "right": {"kind": "vwap", "length": n}}]))
