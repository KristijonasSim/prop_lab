"""STEPS 1 TO 3 of the workflow Kris and Claude agreed on 2026-09-21.

    docs/WORKFLOW.drawio  is the picture. Read it first.

    step 1  queue.py    ideas arrive by themselves, 24/7, deduped by BEHAVIOUR
    step 2  spec.py     the grammar an idea is allowed to be expressed in
            guard.py    a strategy physically cannot read a bar it has not reached
            build.py    run it, produce TRADES
    step 3  cells.py    the 24 (market, timeframe) pairs and their costs
            check.py    four questions about those trades, seconds, any no = dead

Steps 4-7 are not here yet.

STEP 3 DOES NOT USE `core/screen.py`, and that is deliberate rather than an
oversight. That screen reads a SIGNAL against forward BAR returns and its third
gate asks for the median to move; a trade with a stop at 1R has a median of
about -1R whenever the win rate is under 50%, so the gate would reject 39 of 40
generated ideas and H-027's own family with them. `core/screen.py` is still the
right tool for a signal. `factory/check.py` is the one for a trade.
"""
