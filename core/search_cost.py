"""What a search costs: how many of its passes are expected to be false.

WHY THIS FILE EXISTS. `NEXT.md` item D2, owed since 2026-09-13: *"The search is
not priced. 96 tests at a 95th percentile expect 4.8 false passes. This
correction was written down for H-028 and rebuilt without it three days later."*

THE ARITHMETIC IS TRIVIAL AND THAT IS THE POINT - nobody skips it because it is
hard. A test that promotes an arm at the 95th percentile of its own null lets
through 5% of arms that carry no information. Run 96 of them and about 4.8 arms
with nothing in them are promoted, which is more than this project has ever
promoted on purpose. The number that has to appear next to a screen's winner is
not its percentile, it is HOW MANY WINNERS A SCREEN THAT SIZE PRODUCES BY
CONSTRUCTION.

WHAT THIS IS NOT. It is not a replacement for the paired null in
`core/pipeline.py` or for `core/noiseband.py`. The null says whether ONE arm
beats chance; the band says whether two numbers are distinguishable; this says
how much of the whole DAY's output is chance. All three, or none of them mean
much - H-042 cleared a null on one cell in sixteen and closing that axis rested
on `expected_false` being 1.6, not on the null itself.

THE HONEST USE IS A KILL CRITERION, NOT A CORRECTION. Raising the bar to a
Sidak-corrected percentile is arithmetically right and practically useless at
this sample size: it demands a percentile the data cannot resolve. The usable
form is the one H-043 used - *one arm clearing the bar is what this many arms
produce anyway, so only a monotone FAMILY of arms counts.*
"""
from __future__ import annotations


def expected_false(n_tests: int, pctile: float = 95.0) -> float:
    """How many information-free arms a screen of `n_tests` promotes anyway.

    >>> expected_false(96, 95.0)
    4.8
    >>> expected_false(16, 90.0)
    1.6
    """
    if n_tests < 0:
        raise ValueError("n_tests must be >= 0")
    if not 0.0 <= pctile <= 100.0:
        raise ValueError("pctile is a percentile, 0-100")
    return round(n_tests * (1.0 - pctile / 100.0), 2)


def sidak_pctile(n_tests: int, family_alpha: float = 0.05) -> float:
    """The per-test percentile that holds the FAMILY-wide false-pass rate at
    `family_alpha`.

    Sidak rather than Bonferroni because the tests here are not independent -
    the arms of a sweep share a trade series - and Sidak is the exact form under
    independence and the less punitive of the two everywhere else. It is still
    an upper bound on what the arms of one sweep really cost.

    >>> sidak_pctile(16)
    99.68
    >>> sidak_pctile(96)
    99.95

    READ IT AS A PRICE TAG, NOT A TARGET. A 200-resample null cannot resolve a
    99.95th percentile at all - the top resample IS the 99.5th - so a screen
    this wide cannot be rescued by raising its bar. It has to be made narrower,
    or its winner has to be confirmed out of sample.
    """
    if n_tests < 1:
        raise ValueError("n_tests must be >= 1")
    if not 0.0 < family_alpha < 1.0:
        raise ValueError("family_alpha must be in (0, 1)")
    return round((1.0 - family_alpha) ** (1.0 / n_tests) * 100.0, 2)


def resolvable(n_tests: int, n_resamples: int, family_alpha: float = 0.05) -> bool:
    """Can a null of `n_resamples` even express the corrected percentile?

    A null of 200 draws has a finest resolvable percentile of 100 - 100/200 =
    99.5. Asking it for 99.95 is asking a question it cannot answer, and an arm
    reported as clearing that bar is reporting the resolution of its own null.
    """
    if n_resamples < 1:
        raise ValueError("n_resamples must be >= 1")
    return sidak_pctile(n_tests, family_alpha) <= 100.0 - 100.0 / n_resamples


def verdict(n_tests: int, pctile: float = 95.0, n_resamples: int = 200,
            family_alpha: float = 0.05) -> str:
    """One line for the top of a screen's result. Report it or do not report the
    screen."""
    ef = expected_false(n_tests, pctile)
    sp = sidak_pctile(n_tests, family_alpha)
    tail = ("" if resolvable(n_tests, n_resamples, family_alpha) else
            f", which {n_resamples} resamples cannot resolve")
    return (f"{n_tests} tests at the {pctile:g}th percentile expect "
            f"{ef:g} false passes; holding the family at {family_alpha:g} "
            f"needs the {sp:g}th{tail}.")
