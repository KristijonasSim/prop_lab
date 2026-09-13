"""ARM 1 — the fold selector, scored under the sizing rule adopted after it.

Pre-registered in `notes.md`. Three tests, stated up front.

THE CLAIM BEING TESTED. On 2026-09-09 the selector objective was compared at 2%
FLAT risk on XAUUSD 1h:

    ranked on profit factor @2x   15.2 expected days, 65.8% pass   <- shipped
    ranked on R per day           11.1 days, 44.9% pass
    ranked on days                10.9 days, 54.9% pass

Ranking on `days` was 4.3 days faster and was not adopted because the pass rate
fell and the bands overlapped. **Budget-linear sizing was adopted the NEXT DAY**,
and its whole effect is on that weakness: blown 29.5% -> 16.9%, pass 65.8% ->
77.0%. The two have never been run together - verified by grep, zero rows mention
both.

If the sizing rule repairs the days-selector's pass rate while keeping its speed,
that is a real improvement to the traded rule, with no new data and no new
mechanism. If it does not, the objective question is closed for good.

Run: .venv/bin/python strategies/beat/objective.py
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from core.run_hypothesis import run_market, window                 # noqa: E402
from strategies.beat.scoring import (HEADER, beats, daily_from,    # noqa: E402
                                     row, score_budget)
from strategies.vwapbreak.research.exits import (UNIVERSE,         # noqa: E402
                                                 WIDE_SIGMA, ExitVariant)

SYM, TF = "XAUUSD", "1h"
#: the shipped selector first, so the number to beat lands first
ARMS = ("2x", "rday", "days")


def main() -> int:
    span = window([s for v in UNIVERSE.values() for s in v], ["1h", "4h"])
    print(f"ARM 1 - fold selector under BUDGET-LINEAR sizing, {SYM} {TF}")
    print(f"window {span[0].date()} -> {span[1].date()}, ASH rules, "
          f"3 tests\n")
    print(HEADER + f"{'PF2x':>8}{'null':>8}{'tpd':>7}{'mins':>6}")

    out, base = {}, None
    for sel in ARMS:
        t0 = time.time()
        try:
            res = run_market(ExitVariant("wide", stops=WIDE_SIGMA), SYM, TF,
                             pipe_kw={"floors": (30,), "topn": (5,),
                                      "select_on": sel},
                             null_seeds=1, span=span)
        except Exception as exc:                          # noqa: BLE001
            print(f"  {sel:26} FAILED: {type(exc).__name__}: {exc}", flush=True)
            continue
        s = score_budget(daily_from(res))
        s.update({"pf_2x": res.get("pf_2x"), "null_pf": res.get("null_pf"),
                  "beats_null": res.get("beats_null"),
                  "trades_per_day": res.get("trades_per_day"),
                  "trades": res.get("trades")})
        out[sel] = s
        if sel == "2x":
            base = s
        print(row(f"select_on={sel}", s) +
              f"{s['pf_2x'] or 0:8.3f}{s['null_pf'] or 0:8.3f}"
              f"{s['trades_per_day'] or 0:7.2f}{(time.time() - t0) / 60:6.1f}",
              flush=True)

    print("\n" + "=" * 78)
    if base:
        print(f"KILL CRITERION vs the shipped selector "
              f"({base['days']:.1f} days, band "
              f"{base['band']['days_lo']:.0f}-{base['band']['days_hi']:.0f}):\n")
        alive = []
        for sel, s in out.items():
            if sel == "2x":
                continue
            ok, why = beats(s, base)
            ok = ok and bool(s.get("beats_null"))
            if not s.get("beats_null"):
                why.append("loses to null")
            print(f"  select_on={sel:6} {'BEATS IT' if ok else 'FAIL':9} "
                  + ("" if ok else "- " + ", ".join(why)))
            if ok:
                alive.append(sel)
        print()
        if alive:
            print(f"  {', '.join(alive)} beats the shipped selector. "
                  f"A survivor is a candidate for the board, not a decision - "
                  f"switching SELECT_ON moves every number on the page.")
        else:
            print("  NOTHING BEATS THE SHIPPED SELECTOR under budget-linear "
                  "sizing. The objective question is closed.")

    dst = ROOT / "backtests" / "beat"
    dst.mkdir(parents=True, exist_ok=True)
    (dst / "objective.json").write_text(json.dumps(out, indent=1, default=str))
    print("\nwrote backtests/beat/objective.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
