# H-017 was taken off the board on 2026-09-07

`board.json` is renamed, not deleted — `core/build_scoreboard.py` globs
`backtests/*/board.json`, so the rename removes it from the page while the
record stays readable at `board.json.dead-2026-09-07`.

**Why.** H-017's whole thesis is a wide crypto book on the VWAP kernel. Three
look-aheads were removed from `strategies/vwap/engine.py` on 2026-09-06 and the
rebuild clears **1 of 132 legs**, which trades 0.31/day. The board's 28.5-day
two-step and 9.7-day one-step numbers came from the bug. See
`SESSION_2026-09-06.md` and the known-dead list in `CLAUDE.md`.

Restore by renaming back, but only with a number that is not from the buggy
kernel.
