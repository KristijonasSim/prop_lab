"""The prop-firm shortlist, and the data the comparison page runs on.

WHY THIS IS A SCRIPT AND NOT A MARKDOWN TABLE. The ranking depends on running
OUR book under THEIR rules - a firm with a generous drawdown cap lets us size up
and finish sooner, and one with a 3% cap does not - so the interesting column,
expected days to a funded account, cannot be looked up. It has to be simulated,
and it has to be re-simulated whenever the book changes or a firm changes its
rules. This writes both halves the page needs: the firm records, and H-009's
daily R series so the page can re-run the simulation itself when a rule is
edited.

Every price and rule here was gathered on 2026-09-02 and each carries its own
`checked` date and `confidence`. Prop firms change terms often and marketing
pages disagree with rules pages - RebelsFunding's own blog claims algo support
while its rules page bans EAs - so nothing here should be trusted past its date
without re-checking.

Run: .venv/bin/python core/prop_firms.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

OUT = ROOT / "backtests" / "propfirms"
OUT.mkdir(parents=True, exist_ok=True)
GV = ROOT / "backtests" / "gated_vwap"

FULL = [("BTCUSDT", "4h"), ("ETHUSDT", "1h"), ("ETHUSDT", "30m"),
        ("SOLUSDT", "4h"), ("XAUUSD", "5m")]
CRYPTO = FULL[:4]
CHECKED = "2026-09-02"

# bot: "open"  = real API or bots explicitly allowed
#      "limited" = allowed only on a platform we cannot use, or as risk tools only
#      "unknown" = listed but unverified
#      "banned" = automation not permitted
FIRMS = [
 dict(firm="Velotrade 2-Step", price=32, gold=True, bot="open",
      platform="own platform, full REST + WebSocket API on every account",
      phases=[[0.08, 0.05, 0.10, 0], [0.05, 0.05, 0.10, 0]], trailing=False,
      split="80% (90% paid add-on)", confidence="medium",
      note="Cheapest firm found that permits a real bot. Static drawdown lets us "
           "size up. The algo-friendly claim is self-published - verify the API "
           "on a live account before scaling."),
 dict(firm="Velotrade 1-Step Classic", price=32, gold=True, bot="open",
      platform="own platform, full REST + WebSocket API",
      phases=[[0.10, 0.04, 0.07, 0]], trailing=False, split="80%",
      confidence="medium", note="Same API, one phase, but a 10% target on a 7% "
           "cap means a lower pass rate than their 2-step."),
 dict(firm="Upcomers Ash", price=54, gold=True, bot="unknown",
      platform="cTrader listed (Open API UNVERIFIED); their own platform is a "
               "Hyperliquid front-end with no API for us",
      phases=[[0.02, 0.03, 0.06, 0]], trailing=True, split="90%",
      confidence="high", note="By far the best rule set in the table - a 2% "
           "target is why. Everything hinges on whether cTrader Open API is "
           "permitted on a challenge account. Price shown is the $25K tier; "
           "check the $5K tier, which may fall under budget."),
 dict(firm="Upcomers Thunderbolt", price=40, gold=True, bot="unknown",
      platform="cTrader listed (UNVERIFIED); in-house platform has no API",
      phases=[[0.05, 0.03, 0.06, 0]], trailing=True, split="90%",
      confidence="high", note="The account already bought. Same API question."),
 dict(firm="Breakout", price=45, gold=False, bot="open",
      platform="own platform, Kraken liquidity", phases=[[0.10, 0.04, 0.06, 0]],
      trailing=False, split="80-95%", confidence="medium",
      note="Crypto only, so the gold leg is lost and the book's drawdown goes "
           "2.82R to 4.23R - that is what costs the days, not the rules."),
 dict(firm="HyroTrader", price=59, gold=False, bot="open",
      platform="real Bybit API on your own sub-account",
      phases=[[0.10, 0.04, 0.06, 5]], trailing=True, split="up to 90%",
      confidence="high", note="Cleanest execution of any of them - a real "
           "exchange API, not a CFD wrapper. Crypto only, and over budget."),
 dict(firm="Propr", price=100, gold=True, bot="open",
      platform="Hyperliquid onchain, open API, third-party bots explicit",
      phases=[[0.08, 0.05, 0.10, 0]], trailing=False, split="80%",
      confidence="low", note="Best platform in the table: 150+ perp markets "
           "including commodity perps, no consistency rule, no minimum days, "
           "USDC payouts. Three times over budget and its rule numbers here are "
           "assumed, not confirmed."),
 dict(firm="FundedNext", price=33, gold=True, bot="limited",
      platform="EAs allowed on MT4/MT5 ONLY - not cTrader, not Match-Trader",
      phases=[[0.08, 0.05, 0.10, 0], [0.05, 0.05, 0.10, 0]], trailing=False,
      split="up to 95%", confidence="medium",
      note="MT5's Python package is Windows-only and this box has no bridge, so "
           "the bot would have to be rewritten as an MQL5 EA. Plus a $25 "
           "non-refundable platform fee on cTrader."),
 dict(firm="Velotrade 1-Step Pro", price=35, gold=True, bot="open",
      platform="own platform, full API", phases=[[0.10, 0.03, 0.03, 0]],
      trailing=False, split="80%", confidence="medium",
      note="A 3% static cap forces us down to 1.00% risk, which is what makes "
           "it slow. Cheap and API-open, but the wrong shape for this book."),
 dict(firm="FundingPips", price=23, gold=True, bot="banned",
      platform="MT5 / cTrader / Match-Trader",
      phases=[[0.08, 0.05, 0.10, 0], [0.05, 0.05, 0.10, 0]], trailing=False,
      split="up to 90%", confidence="high",
      note="DISQUALIFIED. Third-party EAs are permitted only as trade or risk "
           "management tools; a strategy bot is not. On rules alone it would "
           "have tied for the top spot."),
 dict(firm="RebelsFunding", price=25, gold=True, bot="banned",
      platform="own RF-Trader platform, no MT4/MT5",
      phases=[[0.08, 0.05, 0.10, 0], [0.05, 0.05, 0.10, 0]], trailing=False,
      split="up to 90%", confidence="low",
      note="DISQUALIFIED - EAs and bots not permitted per their rules page, "
           "even though their own marketing claims algo support. Rule numbers "
           "here are assumed beyond the 5% first target."),
 dict(firm="Maven Trading", price=17, gold=True, bot="banned",
      platform="MT5", phases=[[0.08, 0.04, 0.08, 0], [0.05, 0.04, 0.08, 0]],
      trailing=False, split="up to 90%", confidence="high",
      note="DISQUALIFIED. Cheapest evaluation in the market and it bans "
           "automation outright."),
]


def daily_series(legs):
    tr = pd.read_parquet(GV / "stage6_trades.parquet")
    tr["exit_ts"] = pd.to_datetime(tr.exit_ts, utc=True)
    t = tr[tr.gated & [(a, b) in legs for a, b in zip(tr.symbol, tr.tf)]]
    t = t[t.exit_ts >= "2024-09-01"].sort_values("exit_ts")
    r = t.r.values / len(legs)
    eq = np.concatenate(([0.0], np.cumsum(r)))
    dd = abs(float((eq - np.maximum.accumulate(eq)).min()))
    d = pd.Series(r, index=t.exit_ts).resample("1D").sum()
    return [round(float(x), 6) for x in d.values], dd, len(t)


def main():
    full, dd_full, n_full = daily_series(FULL)
    cry, dd_cry, n_cry = daily_series(CRYPTO)
    data = {
        "checked": CHECKED,
        "book": {
            "name": "H-009 — VWAP gated by crowd positioning",
            "with_gold": {"daily": full, "maxdd_r": round(dd_full, 3), "trades": n_full,
                          "legs": [f"{a} {b}" for a, b in FULL]},
            "crypto_only": {"daily": cry, "maxdd_r": round(dd_cry, 3), "trades": n_cry,
                            "legs": [f"{a} {b}" for a, b in CRYPTO]},
        },
        "risk_ladder": [0.005, 0.0075, 0.01, 0.0125, 0.015, 0.0175, 0.02,
                        0.025, 0.03, 0.035, 0.04],
        "firms": [{**f, "checked": CHECKED} for f in FIRMS],
    }
    p = OUT / "data.json"
    p.write_text(json.dumps(data))
    print(f"wrote {p}  ({len(FIRMS)} firms, {len(full)} days with gold "
          f"maxDD {dd_full:.2f}R, {len(cry)} crypto-only maxDD {dd_cry:.2f}R)")


if __name__ == "__main__":
    main()
