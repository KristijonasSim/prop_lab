"""The shipped rule (floor 30 / top 5, gold 1h) on the HOUSE 8/3/6 card, EVERY rung.

Kris, 2026-10-06: settle which plan is current. `core/chosen.py` was picked
at 2% on the old Thunderbolt 6/3/6 card; CLAUDE.md quotes HOUSE at 4%, and
`topn_rebuilt.json` stored only the FASTEST rung (6%) - the same
fastest-rung habit that put the factory board at 5% risk. This prints the
whole ladder so the rung is a choice, not a min().

Same walk-forward as `topn.py` (real data only, no nulls).
    .venv/bin/python strategies/vwapbreak/research/house_repick.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

import pandas as pd  # noqa: E402

from core.noiseband import band as nb_band  # noqa: E402
from core.prop_rules import HOUSE  # noqa: E402
from core.riskladder import run_accounts  # noqa: E402
from strategies.vwapbreak.research import topn  # noqa: E402

OUT = ROOT / "backtests" / "vwapbreak" / "house_repick.json"


def main() -> int:
    t = topn
    span = t.window(t.STANDARD, [t.TF])
    df = t.load("XAUUSD", t.TF)
    df = df[(df.index >= span[0]) & (df.index <= span[1])]
    c = t.COSTS["XAUUSD"]
    fee, slip = c.per_side(t.EXEC_MODE)
    pad = int(max(20, round(24 * 4 * t.TF_BPH[t.TF])) * 2)
    m = t.Market(sym="XAUUSD", tf=t.TF, df=df, fee_bps=fee, slip_bps=slip, pad_bars=pad)
    g = [dict(x) for x in t.STRATEGY.grid(t.TF)]
    for x in g:
        x["min_risk_bps"] = c.min_risk_bps
    trades = t.Pipeline(t._FixedGrid(t.STRATEGY, g), floors=t.FLOORS,
                        topn=t.TOPN).walk_forward(m).trades
    tr = trades[(trades["floor"] == 30) & (trades["topn"] == 5)]
    daily = pd.Series(tr.r.values, index=pd.DatetimeIndex(tr.exit_ts)).resample("1D").sum()
    rows = []
    for risk in t.RISKS:
        a = run_accounts(daily, risk, HOUSE)
        pr = a["pass_rate"]
        b = nb_band(daily, risk, rules=HOUSE)
        rows.append({"risk_pct": risk * 100, "pass_pct": round(pr * 100, 1),
                     "blown_pct": round((a["fail_max"] + a["fail_daily"]) * 100, 1),
                     "days": round(a["median_days"] / pr, 1) if pr else None,
                     "days_band": [b.get("days_lo"), b.get("days_hi")],
                     "accounts": round(1 / pr, 2) if pr else None})
        print(rows[-1], flush=True)
    OUT.write_text(json.dumps({"rule": "floor 30 / top 5", "spec": "HOUSE 8/3/6",
                               "span": [str(x) for x in span], "trades": int(len(tr)),
                               "ladder": rows}, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
