"""ARM 3 — maximise R/day under a DRAWDOWN CAP, not divided by drawdown.

Pre-registered in `notes.md`. Three caps, stated up front, no cap added later.

WHY. Arm 1 measured that ranking on `days` gives 40.7% blown accounts against
the shipped selector's 27.6%, while looking faster. Reading `Pipeline._score`
shows why:

    return rpd / max(abs(dd), 1e-9)      # bigger = fewer days

It is a RATIO, so it is scale-free. R/day 1.0 against a -50R drawdown scores
exactly like R/day 0.1 against -5R. A fixed-percentage account with a 6%
max-loss cap does not see those as equivalent - the first breaches constantly.
The objective is structurally blind to the magnitude of the thing that ends
evaluations, and `rday` is worse still: it ignores drawdown entirely and blew
50.9%.

`rday_capped` makes drawdown a CONSTRAINT: reject any config whose train-slice
drawdown exceeds the cap, then take the fastest survivor. The shipped `2x` path
is untouched, so no board number moves.

Run: .venv/bin/python strategies/beat/capped.py
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
#: declared before the run; no fourth cap will be added to rescue a near-miss
CAPS = (5.0, 10.0, 20.0)


def main() -> int:
    span = window([s for v in UNIVERSE.values() for s in v], ["1h", "4h"])
    print(f"ARM 3 - R/day under a drawdown cap, {SYM} {TF}")
    print(f"window {span[0].date()} -> {span[1].date()}, ASH rules, "
          f"budget-linear sizing, 3 tests\n")
    print(HEADER + f"{'PF2x':>8}{'null':>8}{'tpd':>7}{'mins':>6}")

    variant = ExitVariant("wide", stops=WIDE_SIGMA)
    out, base = {}, None
    arms = [("2x", None)] + [("rday_capped", c) for c in CAPS]
    for sel, cap in arms:
        t0 = time.time()
        kw = {"floors": (30,), "topn": (5,), "select_on": sel}
        if cap is not None:
            kw["max_dd_r"] = cap
        name = "select_on=2x" if cap is None else f"capped dd<={cap:.0f}R"
        try:
            res = run_market(variant, SYM, TF, pipe_kw=kw,
                             null_seeds=1, span=span)
        except Exception as exc:                          # noqa: BLE001
            print(f"  {name:26} FAILED: {type(exc).__name__}: {exc}", flush=True)
            continue
        s = score_budget(daily_from(res))
        s.update({"pf_2x": res.get("pf_2x"), "null_pf": res.get("null_pf"),
                  "beats_null": res.get("beats_null"),
                  "trades_per_day": res.get("trades_per_day"),
                  "trades": res.get("trades"), "max_dd_r": cap})
        out[name] = s
        if cap is None:
            base = s
        print(row(name, s) +
              f"{s['pf_2x'] or 0:8.3f}{s['null_pf'] or 0:8.3f}"
              f"{s['trades_per_day'] or 0:7.2f}{(time.time() - t0) / 60:6.1f}",
              flush=True)

    print("\n" + "=" * 78)
    if base:
        bb = base["band"]
        print(f"KILL CRITERION vs the shipped selector ({base['days']:.1f} days, "
              f"band {bb['days_lo']:.0f}-{bb['days_hi']:.0f}, "
              f"blown {base['blown_pct']:.1f}%):\n")
        alive = []
        for name, s in out.items():
            if s.get("max_dd_r") is None:
                continue
            ok, why = beats(s, base)
            if not s.get("beats_null"):
                ok, why = False, why + ["loses to null"]
            # the extra condition: this arm's whole claim is about blow-ups
            if s.get("blown_pct") is not None and \
                    s["blown_pct"] > base["blown_pct"]:
                ok, why = False, why + [
                    f"blows up more ({s['blown_pct']:.1f}% vs "
                    f"{base['blown_pct']:.1f}%)"]
            print(f"  {name:26} {'BEATS IT' if ok else 'FAIL':9}"
                  + ("" if ok else " - " + ", ".join(why)))
            if ok:
                alive.append(name)
        print()
        if alive:
            print(f"  {', '.join(alive)} beats the shipped selector on every "
                  f"pre-registered condition. That is a candidate for the "
                  f"board, not a decision: switching SELECT_ON moves every "
                  f"number on the page and needs a second engine first.")
        else:
            print("  NOTHING BEATS THE SHIPPED SELECTOR. Drawdown as a "
                  "constraint fails where drawdown as a denominator failed, "
                  "and the objective question is closed for good.")

    dst = ROOT / "backtests" / "beat"
    dst.mkdir(parents=True, exist_ok=True)
    (dst / "capped.json").write_text(json.dumps(out, indent=1, default=str))
    print("\nwrote backtests/beat/capped.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
