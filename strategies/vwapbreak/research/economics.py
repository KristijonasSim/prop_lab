"""Is a higher profit factor worth the days it costs? Kris's question, priced.

THE QUESTION. Every filter tried on 2026-09-08 raised profit factor and slowed
the book down. Kris asked whether that trade is ever worth taking, and asked for
the answer at a risk of AT LEAST 2% per trade rather than the 0.25% the board's
scorer keeps choosing.

WHAT DECIDES IT. Not profit factor. The firm pays for a funded account, and what
it costs is time and euros:

    expected_days     = median_days_of_a_PASSING_account / pass_rate
    accounts_bought   = 1 / pass_rate
    EUR per funded    = accounts_bought x FEE

`expected_days` divides by pass rate on purpose: median days counts only the
accounts that passed, which flatters a strategy that blows most of them up. A
book that passes 20% of the time in 10 days is not a 10-day book, it is a 50-day
book that costs five account fees.

WHY 0.25% KEEPS WINNING THE SCORER AND WHY IT MAY STILL BE WRONG. At a low risk
almost nothing breaches, so the pass rate looks high - but the account creeps
towards a 6% target it may not reach inside any horizon, and `still_open` is
where the accounts go. Raising risk converts unresolved accounts into resolved
ones, some passed and some dead. Whether that is a good trade is arithmetic, and
this file does the arithmetic instead of arguing about it.

Run: .venv/bin/python strategies/vwapbreak/research/economics.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

#: Thunderbolt, the chosen firm. CLAUDE.md.
FEE_EUR = 21.89
#: The risk Kris asked to be shown, and the neighbours that bracket it.
FOCUS_RISK = 2.0
BRACKET = (1.0, 1.5, 2.0, 2.5, 3.0)

SOURCES = {
    "H-027 gold, board record": ("backtests/vwapbreak/hypothesis.json", "board"),
    "MA200 gate off/on": ("backtests/vwapbreak/ma_gate.json", "flat"),
    "selector 1x vs 2x": ("backtests/vwapbreak/select_cost.json", "flat"),
    "shuffled-gate control": ("backtests/vwapbreak/gate_null.json", "flat"),
}


def economics(rung: dict) -> dict:
    """Time and money to ONE funded account at this risk level."""
    p = (rung.get("pass_pct") or 0.0) / 100.0
    med = rung.get("median_days")
    if p <= 0 or not med:
        return {"exp_days": None, "accounts": None, "eur": None}
    return {"exp_days": med / p, "accounts": 1.0 / p,
            "eur": FEE_EUR / p}


def load_arms() -> dict[str, dict]:
    """{label: {'pf_2x':…, 'ladder':[…]}} across every study saved today."""
    arms: dict[str, dict] = {}
    for name, (rel, kind) in SOURCES.items():
        p = ROOT / rel
        if not p.exists():
            print(f"  (skipped {rel} — not on disk)")
            continue
        d = json.loads(p.read_text())
        if kind == "board":
            for c in d.get("cells", []):
                if c.get("sym") != "XAUUSD":
                    continue
                arms[f"board {c['sym']} {c['tf']}"] = {
                    "pf_2x": c.get("pf_2x"), "ladder": c.get("ladder", [])}
        else:
            for k, v in d.items():
                if not isinstance(v, dict) or not v.get("ladder"):
                    continue
                arms[k] = {"pf_2x": v.get("pf_2x"), "ladder": v["ladder"]}
    return arms


def rung_at(ladder: list[dict], risk: float) -> dict | None:
    for r in ladder:
        if abs(r.get("risk_pct", -1) - risk) < 1e-9:
            return r
    return None


def main() -> int:
    arms = load_arms()
    if not arms:
        print("nothing to price yet — run ma_gate.py / select_cost.py first")
        return 1

    print(f"Thunderbolt: 6% target, 3% daily, 6% max. "
          f"EUR {FEE_EUR:.2f} an account.\n")

    # ---- 1. what raising risk to 2% actually does --------------------------
    print("=" * 92)
    print("1. THE RISK LADDER — what 2% per trade costs and buys")
    print("=" * 92)
    for label, a in arms.items():
        lad = a["ladder"]
        if not lad:
            continue
        print(f"\n{label}   (PF@2x {a['pf_2x']})")
        print(f"  {'risk':>5s} {'pass%':>6s} {'blown%':>7s} {'open%':>6s} "
              f"{'medDays':>8s} {'expDays':>8s} {'accts':>6s} {'EUR':>7s}")
        for r in lad:
            if r["risk_pct"] not in BRACKET:
                continue
            e = economics(r)
            blown = (r.get("fail_max_pct") or 0) + (r.get("fail_daily_pct") or 0)
            ed = f"{e['exp_days']:.1f}" if e["exp_days"] else "—"
            ac = f"{e['accounts']:.1f}" if e["accounts"] else "—"
            eu = f"{e['eur']:.0f}" if e["eur"] else "—"
            md = f"{r['median_days']:.0f}" if r.get("median_days") else "—"
            mark = "  <-- 2%" if r["risk_pct"] == FOCUS_RISK else ""
            print(f"  {r['risk_pct']:5.2f} {r['pass_pct']:6.1f} {blown:7.1f} "
                  f"{(r.get('still_open_pct') or 0):6.1f} {md:>8s} {ed:>8s} "
                  f"{ac:>6s} {eu:>7s}{mark}")

    # ---- 2. the actual question: does profit factor buy days? --------------
    print("\n" + "=" * 92)
    print(f"2. DOES PROFIT FACTOR BUY DAYS? every arm above, at {FOCUS_RISK}% risk")
    print("=" * 92)
    pts = []
    for label, a in arms.items():
        r = rung_at(a["ladder"], FOCUS_RISK)
        if not r or not a.get("pf_2x"):
            continue
        e = economics(r)
        if not e["exp_days"]:
            continue
        pts.append((label, float(a["pf_2x"]), e["exp_days"], r["pass_pct"],
                    e["eur"]))
    pts.sort(key=lambda x: x[2])
    print(f"  {'arm':38s} {'PF@2x':>6s} {'expDays':>8s} {'pass%':>6s} {'EUR':>7s}")
    for label, pf2, ed, pp, eu in pts:
        print(f"  {label[:38]:38s} {pf2:6.3f} {ed:8.1f} {pp:6.1f} {eu:7.0f}")

    if len(pts) >= 4:
        pf2 = np.array([p[1] for p in pts])
        ed = np.array([p[2] for p in pts])
        c = float(np.corrcoef(pf2, ed)[0, 1])
        b = float(np.polyfit(pf2, ed, 1)[0])
        print(f"\n  correlation(PF@2x, expected days) = {c:+.3f} over {len(pts)} arms")
        print(f"  slope: +0.1 profit factor is worth {b * 0.1:+.1f} expected days")
        if c > -0.5:
            print("  READ: profit factor does NOT reliably buy days. A filter that "
                  "lifts PF\n        and cuts R per day makes the evaluation "
                  "slower, and PF alone cannot\n        tell you which happened.")

    # ---- 3. the noise floor ------------------------------------------------
    shuffled = {k: v for k, v in arms.items() if "shuffled" in k.lower()}
    if len(shuffled) >= 2:
        print("\n" + "=" * 92)
        print("3. THE NOISE FLOOR — what a gate carrying NO information scores")
        print("=" * 92)
        vals = []
        for label, a in shuffled.items():
            r = rung_at(a["ladder"], FOCUS_RISK)
            if not r:
                continue
            e = economics(r)
            if e["exp_days"]:
                vals.append((label, float(a["pf_2x"] or np.nan), e["exp_days"]))
        for label, pf2, ed in sorted(vals, key=lambda x: x[2]):
            print(f"  {label[:38]:38s} PF@2x {pf2:6.3f}  expDays {ed:8.1f}")
        if len(vals) >= 2:
            eds = np.array([v[2] for v in vals])
            pfs = np.array([v[1] for v in vals])
            print(f"\n  meaningless gates span {eds.min():.1f} to {eds.max():.1f} "
                  f"expected days and {pfs.min():.3f} to {pfs.max():.3f} PF@2x.")
            print("  ANY improvement smaller than that spread is not evidence of "
                  "anything.")

    print("\nHOW TO USE THIS. Compare two candidates on expDays and EUR, never on "
          "profit\nfactor. Then check the gap against section 3: if it is inside "
          "the noise floor,\nthe two candidates are the same candidate.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
