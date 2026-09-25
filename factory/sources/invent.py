"""SOURCE 2 — the bot invents its own, so the queue never runs dry.

Kris: *"when we finish everything from there bot needs to generate strategies
on his own untill i will provide diferent source."*

This walks the grammar in `factory/spec.py` systematically rather than at
random, so the space is covered rather than sampled, and so a restart carries
on where it left off instead of re-rolling dice. `queue.add` refuses anything
already seen, so overlap with TradingView costs nothing.

It is deliberately dumb. The clever version - a model proposing rules with a
written mechanism - is worth building later, but a dumb enumerator that never
stops is worth more than a clever one that needs a person.
"""
from __future__ import annotations

from itertools import product

from factory.spec import LENGTHS, Condition, Strategy, Term

#: Pairs that mean something when compared. Not every combination is sensible:
#: `rsi cross_above sma50` compares an oscillator to a price and is noise.
_PRICE = ("price", "sma", "ema", "highest", "lowest")
_OSC = {"rsi": (20.0, 30.0, 50.0, 70.0, 80.0),
        "roc": (-100.0, -50.0, 50.0, 100.0)}


def _crosses():
    """Two price-scale indicators crossing. The classic TradingView shape."""
    for a, b in product(("sma", "ema"), repeat=2):
        for na, nb in product(LENGTHS, repeat=2):
            if na >= nb:
                continue
            yield (Condition(Term(a, na), "cross_above", Term(b, nb)),), "long"
            yield (Condition(Term(a, na), "cross_below", Term(b, nb)),), "short"


def _breakouts():
    """Price taking out a recent extreme. Fires rarely - the shape the old
    feed vocabulary could not express at all.

    Each carries its own SIDE: breaking the high is a long, breaking the low is
    a short. Emitting both directions of the same condition would double the
    search for nothing, which is rule 3 of `research/vocab.py`.
    """
    for n in LENGTHS:
        yield (Condition(Term("price"), "above", Term("highest", n)),), "long"
        yield (Condition(Term("price"), "below", Term("lowest", n)),), "short"


def _oscillators():
    """An oscillator crossing a level. cross_above a low level is the classic
    dip-buy (long); cross_below a high level is the classic fade (short)."""
    for name, levels in _OSC.items():
        for n in LENGTHS:
            for lv in levels:
                yield (Condition(Term(name, n), "cross_above",
                                 Term("const", value=lv)),), "long"
                yield (Condition(Term(name, n), "cross_below",
                                 Term("const", value=lv)),), "short"


def generate(limit: int = 200, *, stop_atr: float = 2.0,
             target_atr: float = 3.0, max_hold: int = 48,
             skip: int = 0) -> list[Strategy]:
    """The next `limit` ideas. Cheap - nothing is run, only described.

    `skip` carries on where a previous call stopped, so a restart does not
    re-offer the front of the list. The direction is fixed by the condition,
    never searched both ways.
    """
    out = []
    for i, (entry, side) in enumerate(_chain()):
        if i < skip:
            continue
        out.append(Strategy(
            name=" and ".join(c.label() for c in entry),
            side=side, entry=entry, source="invent",
            stop_atr=stop_atr, target_atr=target_atr, max_hold=max_hold,
            note="enumerated from the grammar; no mechanism claimed"))
        if len(out) >= limit:
            break
    return out


def _chain():
    yield from _breakouts()
    yield from _oscillators()
    yield from _crosses()


def space_size() -> int:
    return sum(1 for _ in _chain())
