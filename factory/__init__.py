"""STEPS 1 AND 2 of the workflow Kris and Claude agreed on 2026-09-21.

    docs/WORKFLOW.drawio  is the picture. Read it first.

    step 1  queue.py    ideas arrive by themselves, 24/7, deduped by BEHAVIOUR
    step 2  spec.py     the grammar an idea is allowed to be expressed in
            guard.py    a strategy physically cannot read a bar it has not reached
            build.py    run it, produce TRADES

Steps 3-7 are not here yet. Step 3 (the quick check) is being designed; the
current `core/screen.py` is measured broken for this kind of idea - see
`research/poscontrol.py`.
"""
