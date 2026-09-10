"""Can the payoff be RESHAPED - more winners, smaller best day - without losing it?

Kris, 2026-09-10: "how to improve it, how to make it better, how to increase maybe
win % so we could take our profits because this 20% rule will kill us".

Two separate problems, one lever. The strategy wins 20% of the time and makes 42%
of its net profit on a single day (85% on ETH), so a firm capping the best day at
20% of a withdrawal never pays it (`bestday.py`, 0 payable withdrawals in 20 of 20
cells). Both symptoms come from the same source: no target, a wide stop, and a
fortnight horizon, so the payoff is one enormous winner in five.

WHAT HAS ALREADY BEEN MEASURED, so it is not re-run here. `research/shape.py`
swept reward:risk 1 to 8 and average R rose monotonically to the edge of the grid
every time - a FIXED target destroys this edge, which is why the shipped kernel
has no target axis. That result is about a full exit at a fixed multiple. It says
nothing about the three shapes below, none of which has ever been run on H-027:

    partial     take HALF off at +m x risk, let the rest run to stop or horizon.
                Half the trade books a winner, half keeps the tail. This is the
                arm aimed straight at the 20% rule: it moves profit off the one
                huge day and onto the many small ones.
    trail       once the trade is +1R up, trail the stop k x risk behind the best
                price seen. Caps the give-back without capping the run.
    recross     exit when price closes back through its own session VWAP - the
                signal that made the trade is gone. A logical exit, never tested.

HOW THE PAYOFF IS SCORED. Win rate and profit factor are not the target here.
The four numbers that decide it:

    expected days   the pace, with its band. If this gets worse the arm is dead.
    best-day share  the single largest day as a share of net profit - the 20%
                    rule's own test.
    payable         withdrawals a 20% cap would actually pay, out of those the
                    series affords.
    win %           what Kris asked for, and the least important of the four.

THE KERNEL IS COPIED, NOT IMPORTED, and the copy is deliberate: the shipped
kernel has no exit axis and the whole board's fingerprint depends on it not
gaining one. Every convention it carries is carried here - signal on a closed
bar, fill at the next open, stop wins every tie, a stop the bar gapped past
fills at the OPEN, a target keeps its level, no decision or fill or exit on a
bar that never traded, costs charged on every fill including the partial.

Run: .venv/bin/python strategies/vwapbreak/research/exitshape.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

from core.noiseband import band                                    # noqa: E402
from core.prop_rules import PropRules                              # noqa: E402
from core.riskladder import run_accounts                           # noqa: E402
from core.run_hypothesis import run_market, window                 # noqa: E402
from core.strategy import N_COLS, T_DIR, T_ENTRY_I, T_ENTRY_PX     # noqa: E402
from core.strategy import T_EXIT_I, T_EXIT_PX, T_R, T_REASON       # noqa: E402
from strategies.vwapbreak.strategy import STRATEGY, grid_for       # noqa: E402
from strategies.vwapbreak.research.exits import UNIVERSE, WIDE_SIGMA  # noqa: E402

ASH = PropRules(profit_target=0.02, daily_loss=0.03, max_loss=0.06,
                min_trading_days=0)
RISKS = (0.01, 0.015, 0.02, 0.03)
CAP, PAYOUT_MIN = 0.20, 0.01
CELLS = (("XAUUSD", "1h"), ("ETHUSDT", "1h"))

R_STOP, R_HORIZON, R_TRAIL, R_RECROSS, R_TARGET = 0, 1, 2, 3, 4


class ShapedExit:
    """H-027's entries exactly; the exit reshaped. One shape per instance.

    partial_r  take half off at +partial_r x risk (0 = off)
    trail_r    after +1R, trail the stop trail_r x risk behind the best price
    recross    exit on the first close back through the session VWAP
    """

    extra_column = "z"

    def __init__(self, name: str, partial_r: float = 0.0, trail_r: float = 0.0,
                 recross: bool = False, target_r: float = 0.0):
        self.name = name
        self.partial_r, self.trail_r, self.recross = partial_r, trail_r, recross
        #: a FULL exit at +target_r x risk. 0 = no target, which is the shipped
        #: behaviour. Added 2026-09-10 for the reward:risk sweep Kris asked for
        #: ("test all these scenarios with R:R being from 1 to 12").
        self.target_r = target_r

    def features(self, df: pd.DataFrame):
        return STRATEGY.features(df)

    def new_cache(self):
        g = getattr(STRATEGY, "new_cache", None)
        return g() if callable(g) else {}

    def grid(self, tf: str):
        from core.markets import TF_BPH
        base, seen, out = grid_for(TF_BPH[tf]), set(), []
        for cfg in base:
            for s in WIDE_SIGMA:
                c = dict(cfg)
                c["stop_sig"] = s
                key = tuple(sorted(c.items()))
                if key not in seen:
                    seen.add(key)
                    out.append(c)
        return out

    # ------------------------------------------------------------------ #
    def run(self, df, cfg, fee_bps, slip_bps, feats=None, **kw) -> np.ndarray:
        f = feats if feats is not None else self.features(df)
        z, sd, live = f["z"], f["sd"], f["live"]
        rvol, hour = f["rvol"], f["hour"]
        h_lo, h_hi = int(cfg.get("hour_lo", 0)), int(cfg.get("hour_hi", 0))
        min_rvol = float(cfg.get("min_rvol", 0.0))
        o, h, l, c = (df.open.values, df.high.values,
                      df.low.values, df.close.values)
        n = len(c)
        cost = (fee_bps + slip_bps) / 1e4
        thr, ssig = float(cfg["thr"]), float(cfg["stop_sig"])
        mh, minr = int(cfg["max_hold"]), float(cfg.get("min_risk_bps", 3.0))
        pr, tr_mult, tgt = self.partial_r, self.trail_r, self.target_r

        out = np.zeros((n, N_COLS))
        k, i = 0, 1
        while i < n - 1:
            if not (np.isfinite(z[i]) and live[i]):
                i += 1
                continue
            side = 1 if z[i] >= thr else (-1 if z[i] <= -thr else 0)
            if side == 0:
                i += 1
                continue
            if h_lo != h_hi:
                hh = hour[i]
                inside = (h_lo <= hh < h_hi) if h_lo < h_hi else (hh >= h_lo or hh < h_hi)
                if not inside:
                    i += 1
                    continue
            if min_rvol > 0.0 and rvol[i] < min_rvol:
                i += 1
                continue
            e = i + 1
            if not live[e]:
                i += 1
                continue
            entry = o[e]
            risk = ssig * sd[i]
            if not np.isfinite(risk) or entry <= 0:
                i += 1
                continue
            risk = max(risk, entry * minr / 1e4)
            stop = entry - side * risk
            last = min(e + mh, n - 1)

            # --- walk the trade ------------------------------------------ #
            part_done, part_r = False, 0.0
            best = entry                       # best price seen, for the trail
            exit_px, exit_i, reason = c[last], last, R_HORIZON
            j = e
            while j <= last:
                if not live[j]:
                    j += 1
                    continue
                # 1. THE STOP FIRST - it wins every tie, and a gap through it
                #    fills at the open because it is a market order.
                if side == 1 and l[j] <= stop:
                    exit_px = stop if o[j] > stop else o[j]
                    exit_i, reason = j, (R_TRAIL if part_done or stop != entry - side * risk
                                         else R_STOP)
                    break
                if side == -1 and h[j] >= stop:
                    exit_px = stop if o[j] < stop else o[j]
                    exit_i, reason = j, (R_TRAIL if part_done or stop != entry - side * risk
                                         else R_STOP)
                    break
                # 2. the partial. A limit order at a known level: it fills at the
                #    level, and a gap through it fills BETTER, which would be
                #    optimism, so the level is kept either way.
                if pr > 0.0 and not part_done:
                    lvl = entry + side * pr * risk
                    if (side == 1 and h[j] >= lvl) or (side == -1 and l[j] <= lvl):
                        part_r = ((lvl - entry) * side - (entry + lvl) * cost / 2) / risk
                        part_done = True
                # 3. the trail, armed only once the trade is +1R up. Measured on
                #    the CLOSE of a completed bar, never on the extreme, so it
                #    cannot use a price the bar only touched intrabar.
                if tr_mult > 0.0:
                    best = max(best, c[j]) if side == 1 else min(best, c[j])
                    if (best - entry) * side >= risk:
                        cand = best - side * tr_mult * risk
                        stop = max(stop, cand) if side == 1 else min(stop, cand)
                # 3b. the TARGET. A limit order like the partial: it fills at its
                #     level, and a gap through it would fill better, which would be
                #     optimism, so the level is kept. The stop above wins any bar
                #     that contains both.
                if tgt > 0.0:
                    lvl = entry + side * tgt * risk
                    if (side == 1 and h[j] >= lvl) or (side == -1 and l[j] <= lvl):
                        exit_px, exit_i, reason = lvl, j, R_TARGET
                        break
                # 4. the VWAP recross, on a closed bar.
                if self.recross and np.isfinite(z[j]) and side * z[j] <= 0.0:
                    exit_px, exit_i, reason = c[j], j, R_RECROSS
                    break
                j += 1
            if reason == R_HORIZON:
                while exit_i > e and not live[exit_i]:
                    exit_i -= 1
                exit_px = c[exit_i]

            # --- book it -------------------------------------------------- #
            w = 0.5 if part_done else 1.0      # remaining size
            gross = (exit_px - entry) * side
            fees = (entry + exit_px) * cost / 2
            r_rest = (gross - fees) / risk
            r_total = part_r * 0.5 + r_rest * w if part_done else r_rest

            out[k, T_ENTRY_I] = e
            out[k, T_EXIT_I] = exit_i
            out[k, T_DIR] = side
            out[k, T_ENTRY_PX] = entry
            out[k, T_EXIT_PX] = exit_px
            out[k, T_R] = r_total
            out[k, T_REASON] = reason
            out[k, 7] = z[i]
            k += 1
            i = exit_i if exit_i > i else i + 1
        return out[:k]


ARMS = [
    ("baseline", ShapedExit("vwapbreak")),
    ("partial 1R", ShapedExit("vwapbreak_p1", partial_r=1.0)),
    ("partial 2R", ShapedExit("vwapbreak_p2", partial_r=2.0)),
    ("trail 2R", ShapedExit("vwapbreak_t2", trail_r=2.0)),
    ("partial 1R + trail 3R", ShapedExit("vwapbreak_pt", partial_r=1.0, trail_r=3.0)),
    ("VWAP recross", ShapedExit("vwapbreak_rx", recross=True)),
]


def payout_stats(pct: np.ndarray) -> dict:
    acc, best, wins, payable = 0.0, 0.0, 0, 0
    for step in pct:
        acc += step
        best = max(best, step)
        if acc < PAYOUT_MIN:
            continue
        wins += 1
        if best / acc <= CAP:
            payable += 1
        acc, best = 0.0, 0.0
    total = float(pct.sum())
    return {"windows": wins, "windows_payable": payable,
            "best_day_share_net": round(float(pct.max() / total), 3) if total > 0 else None}


def score(res: dict) -> dict:
    tr = res["_trades"]
    daily = pd.Series(tr.r.values,
                      index=pd.DatetimeIndex(tr.exit_ts)).resample("1D").sum()
    best = None
    for risk in RISKS:
        a = run_accounts(daily, risk, ASH)
        if not a["pass_rate"]:
            continue
        exp = a["median_days"] / a["pass_rate"]
        line = {"risk_pct": risk * 100, "pass_pct": round(a["pass_rate"] * 100, 1),
                "blown_pct": round((a["fail_max"] + a["fail_daily"]) * 100, 1),
                "days": round(exp, 1), "band": band(daily, risk, rules=ASH)}
        if best is None or exp < best["days"]:
            best = line
    out = {**(best or {"days": None}), **payout_stats(daily.values * 0.02),
           "trades": res.get("trades"), "win_pct": res.get("win_pct"),
           "pf": res.get("pf"), "pf_2x": res.get("pf_2x"),
           "avg_r": res.get("avg_r"), "trades_per_day": res.get("trades_per_day"),
           "beats_null": res.get("beats_null"), "null_pf": res.get("null_pf")}
    return out


def main() -> int:
    syms = [s for v in UNIVERSE.values() for s in v]
    span = window(syms, ["1h", "4h"])
    out = {}
    for sym, tf in CELLS:
        print(f"\n=== {sym} {tf} " + "=" * 40)
        print(f"{'arm':24}{'trades':>7}{'win%':>7}{'PF2x':>7}{'days':>7}"
              f"{'band':>13}{'pass%':>7}{'bestday':>9}{'payable':>9}")
        for tag, arm in ARMS:
            res = run_market(arm, sym, tf, pipe_kw={"floors": (30,), "topn": (5,)},
                             null_seeds=1, span=span)
            s = score(res)
            out[f"{sym}|{tf}|{tag}"] = s
            b = s.get("band") or {}
            print(f"{tag:24}{s['trades'] or 0:7}{s['win_pct'] or 0:7.1f}"
                  f"{s['pf_2x'] or 0:7.3f}{s['days'] or 0:7.1f}"
                  f"{('%.0f-%.0f' % (b.get('days_lo', 0), b.get('days_hi', 0))):>13}"
                  f"{s['pass_pct'] or 0:7.1f}"
                  f"{(s['best_day_share_net'] or 0):9.3f}"
                  f"{('%d/%d' % (s['windows_payable'], s['windows'])):>9}", flush=True)

    dest = ROOT / "backtests" / "vwapbreak" / "exitshape.json"
    dest.write_text(json.dumps({"cap": CAP, "cells": [list(c) for c in CELLS],
                                "rows": out}, indent=1, default=str))
    print(f"\nwrote {dest.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
