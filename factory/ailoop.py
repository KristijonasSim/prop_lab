"""THE AI LOOP - the model proposes ideas, the tester tests them, every hour.

Kris, 2026-10-09: *"lets do AI agent"*, after TradingView was exhausted.

WHAT IT IS STEERED TO FIND - written before the first call, from what step 8
measured: every rule that survived its luck check so far is a LONG GOLD rule
that rides the 2023-26 uptrend and is flat on the older years. More of those
add nothing. So the model is told to find what the pool lacks.

TOKEN BUDGET: one call of 20 ideas an hour (~10k tokens), stopping at the first
usage-limit message. The TradingView loop made ~14 calls a minute.

The ideas join the normal queue; `factory/testloop.sh` (steps 3-7) tests them.
Survivors still go through step 8's hunt and luck check by hand.

    python -m factory.ailoop              # run forever, one batch an hour
    python -m factory.ailoop --once       # one batch
"""
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from factory.sources import agent  # noqa: E402

BATCH, EVERY = 20, 600
# 2026-10-09: Kris - "only 14% is used out 5h window so use little bit more".
# One call every 10 minutes (6 an hour) - Kris asked for more again the same day.
LIMIT_WAIT = 30 * 60
agent.FOCUS = """WHAT THIS RUN NEEDS - read this first.
Every rule that has survived so far is a LONG GOLD trend rule (buy dips or
breakouts while gold is above its EMA200). They work in 2023-26 because gold
rose, and they are flat in the years before. Do NOT propose more of those.
Propose rules that would still work if gold went sideways or down:
  * SHORT rules, and rules for EURUSD, GBPUSD, USDJPY, silver or BTC
  * mean reversion inside ranges, fades of exhausted moves, session behaviour
  * no rule whose edge is just "price above a long moving average"
FADES DIE ON COSTS: of the first 59 ideas, most range fades with small targets
lost to spread and fees. Prefer setups with room to move - target_atr 3 or
more - such as breakouts from quiet ranges on FX and silver, session-open
moves, and shorts after failed rallies.
Every trade must close within 24 hours: max_hold at most 24 bars, and think
of 1h and 15m charts first. Aim for 0.5-2 trades per day.

"""


def once() -> dict:
    r = agent.fill(BATCH)
    print(f"{datetime.now(timezone.utc):%Y-%m-%d %H:%M} UTC  {r}", flush=True)
    return r


def main() -> int:
    if "--once" in sys.argv:
        once()
        return 0
    while True:
        r = once()
        err = str(r.get("error", "")).lower()
        time.sleep(LIMIT_WAIT if any(k in err for k in ("limit", "usage")) else EVERY)


if __name__ == "__main__":
    raise SystemExit(main())
