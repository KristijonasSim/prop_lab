"""ARM 2 — the Asian range break, on every market. It has only ever run on gold.

Pre-registered in `notes.md`. 18 tests plus 2 reference cells, stated up front.

THE GAP. The Asian range break is the one genuinely new signal this project
found: 0.114 correlated with the VWAP break, second-engine clean 10 of 10, and
over eleven years the most robust arm ever measured here - 71.4% pass, lowest
quarter concentration, smallest best-day share. Every row that mentions it is
XAUUSD. H-027 got a nineteen-cell cross-market screen; its sibling never did.

`VolumeVariant(name, "asia")` is market-agnostic - `asia_range` reads only the
bar's hour, high and low - so this is a screen, not a rewrite.

THE HONEST PROBLEM, written before the run. A 00:00-07:00 UTC window is a real
low-liquidity overnight session on gold and FX. On crypto it is nothing in
particular, because crypto has no session. **A hit on BTC/ETH/SOL is therefore
more likely to be noise than a hit on FX or silver**, and that expectation is
recorded now rather than invented afterwards to explain whatever turns up.

THE SEARCH IS PRICED. 18 tests means roughly one apparent winner from noise
alone at a conventional threshold. So one market clearing is NOT a result: it
must repeat on a RELATED market - another FX major, or the other metal - before
anything is claimed. That correction exists because a screen run this morning
produced 7 passes from 96 tests against 4.8 expected, and the gate had priced
only the per-test null.

Run: .venv/bin/python strategies/beat/asia_markets.py
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
from strategies.vwapbreak.research.exits import UNIVERSE           # noqa: E402
from strategies.vwapbreak.research.volume import VolumeVariant     # noqa: E402

REFERENCE = "XAUUSD"
#: grouped so the report can say WHERE a hit landed, which is the whole point
GROUPS = {
    "FX": ("EURUSD", "GBPUSD", "USDJPY", "AUDUSD"),
    "Metals/Energy": ("XAGUSD", "WTI"),
    "Crypto": ("BTCUSDT", "ETHUSDT", "SOLUSDT"),
}
TFS = ("1h", "4h")
RELATED = {"EURUSD": "FX", "GBPUSD": "FX", "USDJPY": "FX", "AUDUSD": "FX",
           "XAGUSD": "Metals/Energy", "WTI": "Metals/Energy",
           "BTCUSDT": "Crypto", "ETHUSDT": "Crypto", "SOLUSDT": "Crypto"}


def main() -> int:
    span = window([s for v in UNIVERSE.values() for s in v], ["1h", "4h"])
    variant = VolumeVariant("asian range break", "asia")
    print("ARM 2 - the Asian range break on every market, budget-linear sizing")
    print(f"window {span[0].date()} -> {span[1].date()}, ASH rules, "
          f"18 tests + 2 reference\n")

    out, ref = {}, {}
    for tf in TFS:
        print(f"--- {tf} ---")
        print(HEADER + f"{'PF2x':>8}{'null':>8}{'tpd':>7}{'mins':>6}")
        for group, syms in (("reference", (REFERENCE,)), *GROUPS.items()):
            for sym in syms:
                t0 = time.time()
                try:
                    res = run_market(variant, sym, tf,
                                     pipe_kw={"floors": (30,), "topn": (5,)},
                                     null_seeds=1, span=span)
                except Exception as exc:                  # noqa: BLE001
                    print(f"  {sym+' '+tf:26} FAILED: "
                          f"{type(exc).__name__}: {exc}", flush=True)
                    continue
                s = score_budget(daily_from(res))
                s.update({"pf_2x": res.get("pf_2x"), "null_pf": res.get("null_pf"),
                          "beats_null": res.get("beats_null"),
                          "trades_per_day": res.get("trades_per_day"),
                          "group": group, "sym": sym, "tf": tf})
                key = f"{sym}|{tf}"
                out[key] = s
                if sym == REFERENCE:
                    ref[tf] = s
                print(row(f"{sym} {tf}", s) +
                      f"{s['pf_2x'] or 0:8.3f}{s['null_pf'] or 0:8.3f}"
                      f"{s['trades_per_day'] or 0:7.2f}"
                      f"{(time.time() - t0) / 60:6.1f}", flush=True)
        print()

    print("=" * 78)
    print("KILL CRITERION vs gold on the same timeframe: faster, band disjoint,")
    print("beats its own null - and then it must REPEAT on a related market.\n")
    hits = []
    for key, s in out.items():
        if s["sym"] == REFERENCE:
            continue
        base = ref.get(s["tf"])
        if not base:
            continue
        ok, why = beats(s, base)
        if not s.get("beats_null"):
            ok, why = False, why + ["loses to null"]
        if ok:
            hits.append(s)
            print(f"  CLEARS  {key:16} {s['days']:.1f}d vs gold "
                  f"{base['days']:.1f}d  ({s['group']})")
    if not hits:
        print("  Nothing clears on any market. The Asian range does not travel; "
              "it is a gold signal.")
    else:
        groups = {}
        for s in hits:
            groups.setdefault(RELATED.get(s["sym"], "?"), []).append(s["sym"])
        print()
        confirmed = {g: v for g, v in groups.items() if len(set(v)) >= 2}
        if confirmed:
            print(f"  REPEATS within a group -> {confirmed}. "
                  f"That is a candidate worth gate 3.")
        else:
            print(f"  {len(hits)} isolated hit(s) in {list(groups)}, none "
                  f"repeating within its group. With 18 tests roughly one is "
                  f"expected from noise, so this is NOT a result.")

    dst = ROOT / "backtests" / "beat"
    dst.mkdir(parents=True, exist_ok=True)
    (dst / "asia_markets.json").write_text(json.dumps(out, indent=1, default=str))
    print("\nwrote backtests/beat/asia_markets.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
