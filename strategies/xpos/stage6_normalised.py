"""H-017 stage 6 - the same gates, sized properly, and what actually sets days.

STAGE 5 WAS DISTORTED AND THIS FIXES IT.

Every variant in stage 5 came back at `risk = 0.25%`, the bottom rung of the
ladder, with drawdowns of 25 to 59R. At 0.25% risk a 59R drawdown is 14.8% of
the account - already through the 8% cap - so `riskladder.pick` found nothing
admissible and fell through to its "smallest drawdown" fallback. Every book was
being simulated at a leverage no one would choose, and the comparison collapsed
into "more trades is faster", which is why every gate looked bad.

The fix is what a trader does: **size each book so its worst drawdown exactly
fills the 8% cap**, then simulate. Concretely, scale the R series so
|maxDD_R| = 4, which puts the cap-filling risk at 2.00% - comfortably inside
the ladder - and leaves K, profit factor and every shape statistic unchanged,
because all of them are scale-invariant.

This is not a thumb on the scale. It is the same normalisation the board's own
records get by construction: a book of N legs is written with each leg at 1/N,
which is what brings H-009's raw 59R drawdown down to the -2.82R the board
shows and lets it run at 2.8% risk.

With that fixed, the honest question can finally be asked: **does gating make
the account faster or slower?** Stage 5's answer was an artefact. This one is
not.

Output: backtests/xpos/stage6_normalised.csv
"""
from __future__ import annotations

import itertools
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from core import riskladder as RL                                   # noqa: E402
from strategies.orderflow import orderflow as of                    # noqa: E402
from strategies.xpos.stage5_gatestack import (TRADES, build_signals,  # noqa: E402
                                              keep_mask, maxdd, pf, stats)

OUT = ROOT / "backtests" / "xpos"
TARGET_DD_R = 4.0        # -> cap-filling risk of 2.00%, mid-ladder


def sim_normalised(d: pd.DataFrame) -> dict:
    """Scale to fill the 8% cap, then run the project's real two-step sim."""
    r = d.r_2x.values
    dd = maxdd(r)
    if dd >= 0 or len(r) < 100:
        return {}
    r = r * (TARGET_DD_R / abs(dd))
    rows, pick = RL.from_trades(r, d.exit_ts.values)
    return {"risk": pick["risk"], "pass_rate": pick["pass_rate"],
            "killed": round(pick["fail_max"] + pick["fail_daily"], 4),
            "median_days": pick["median_days"],
            "expected_days": pick["expected_days"]}


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    t = pd.read_parquet(TRADES)
    t["entry_ts"] = pd.to_datetime(t.entry_ts, utc=True)
    t["exit_ts"] = pd.to_datetime(t.exit_ts, utc=True)
    sig = build_signals(t)
    keep = ~pd.isna(sig["sys"])
    t = t[keep].reset_index(drop=True)
    for k in sig:
        sig[k] = sig[k][keep]
    d = t.direction.values
    names = ["sys", "oi", "premium", "flowgap"]

    rows = []

    def record(label, sel, ngates):
        s = stats(sel)
        if not s:
            return None
        sm = sim_normalised(sel)
        if not sm:
            return None
        rows.append({"book": label, "n_gates": ngates, **s, **sm})
        return {**s, **sm}

    print("Sized so worst drawdown exactly fills the 8% cap "
          f"(|maxDD_R| -> {TARGET_DD_R:.0f}, risk 2.00%)\n")
    print(f"  {'book':28s} {'trades':>7s} {'t/day':>6s} {'PF2x':>6s} "
          f"{'ret/DD':>7s} {'K':>8s} {'pass':>6s} {'median':>7s} {'EXPECTED':>9s}")

    base = record("H-002 ungated", t, 0)
    if base:
        print(f"  {'H-002 ungated':28s} {base['trades']:>7d} {base['tpd']:>6.2f} "
              f"{base['pf_2x']:>6.3f} {base['ret_dd']:>7.2f} {base['K']:>8.5f} "
              f"{base['pass_rate']*100:>5.1f}% {str(base['median_days']):>7s} "
              f"{str(base['expected_days']):>9s}")
    h009 = record("H-009 (crowd gate)", t[t.gated], 1)
    if h009:
        print(f"  {'H-009 (crowd gate)':28s} {h009['trades']:>7d} {h009['tpd']:>6.2f} "
              f"{h009['pf_2x']:>6.3f} {h009['ret_dd']:>7.2f} {h009['K']:>8.5f} "
              f"{h009['pass_rate']*100:>5.1f}% {str(h009['median_days']):>7s} "
              f"{str(h009['expected_days']):>9s}")
    print()

    best = None
    for r_ in range(1, len(names) + 1):
        for sub in itertools.combinations(names, r_):
            k = np.ones(len(t), dtype=bool)
            for n in sub:
                k &= keep_mask(n, sig[n], d)
            got = record("+".join(sub), t[t.gated & k], 1 + len(sub))
            if not got:
                continue
            print(f"  {'+'.join(sub):28s} {got['trades']:>7d} {got['tpd']:>6.2f} "
                  f"{got['pf_2x']:>6.3f} {got['ret_dd']:>7.2f} {got['K']:>8.5f} "
                  f"{got['pass_rate']*100:>5.1f}% {str(got['median_days']):>7s} "
                  f"{str(got['expected_days']):>9s}")
            ed = got["expected_days"]
            if ed is not None and (best is None or ed < best[0]):
                best = (ed, sub, t[t.gated & k])

    if best:
        ed, sub, sel = best
        print(f"\nBEST: {'+'.join(sub)} -> {ed} expected days "
              f"(H-009 {h009['expected_days']}, goal 14)")

        mid = t.exit_ts.quantile(0.5)
        print("\n  held-out halves (the stack was chosen on the whole window):")
        for label, m in (("first", t.exit_ts <= mid), ("second", t.exit_ts > mid)):
            bb = record(f"H-009 [{label} half]", t[t.gated & m], 1)
            k = np.ones(len(t), dtype=bool)
            for n in sub:
                k &= keep_mask(n, sig[n], d)
            gg = record(f"{'+'.join(sub)} [{label} half]", t[t.gated & k & m],
                        1 + len(sub))
            if bb and gg:
                print(f"    {label:7s} H-009 {str(bb['expected_days']):>8s} d  "
                      f"-> gated {str(gg['expected_days']):>8s} d   "
                      f"(K {bb['K']:.5f} -> {gg['K']:.5f})")

        print("\n  null: same stack driven by BLOCK-SHUFFLED feeds, 5 seeds")
        nulls = []
        for seed in range(5):
            k = np.ones(len(t), dtype=bool)
            for n in sub:
                sh = of.block_shuffle(pd.Series(sig[n]).set_axis(t.entry_ts),
                                      seed=seed + 17, block=288).values
                k &= keep_mask(n, sh, d)
            g = stats(t[t.gated & k])
            sm = sim_normalised(t[t.gated & k])
            if g and sm and sm.get("expected_days"):
                nulls.append((g["K"], sm["expected_days"]))
        if nulls:
            kk = [x[0] for x in nulls]; dd_ = [x[1] for x in nulls]
            rk = stats(sel)["K"]
            print(f"    real K {rk:.5f} vs null {np.mean(kk):.5f} "
                  f"+/- {np.std(kk):.5f} (best seed {max(kk):.5f})")
            print(f"    real days {ed} vs null {np.mean(dd_):.1f} "
                  f"(best seed {min(dd_):.1f})")
            rows.append({"book": f"{'+'.join(sub)} [null mean]",
                         "K": round(float(np.mean(kk)), 5),
                         "expected_days": round(float(np.mean(dd_)), 1)})

    df = pd.DataFrame(rows)
    df.to_csv(OUT / "stage6_normalised.csv", index=False)

    # Does K predict days once sizing is honest? If it does, K is the right
    # thing to optimise and stage 0's arithmetic stands.
    ok = df.dropna(subset=["K", "expected_days"])
    ok = ok[ok.book.str.contains("half|null") == False]           # noqa: E712
    if len(ok) > 4:
        c = np.corrcoef(ok.K, 1.0 / ok.expected_days)[0, 1]
        print(f"\n  correlation of K with 1/expected_days across "
              f"{len(ok)} books: {c:+.3f}")
    print(f"\nwrote {OUT / 'stage6_normalised.csv'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
