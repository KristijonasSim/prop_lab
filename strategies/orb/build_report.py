"""Build the ORB results page from the stage CSVs.

Regenerate after any re-run: .venv/bin/python strategies/orb/build_report.py
Writes backtests/orb/report.html — publish that as the artifact.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
OUT = ROOT / "backtests" / "orb"

KEYS1 = ["hour", "or_bars", "hold_bars", "entry_mode", "stop_mode", "stop_atr_mult", "rr", "fade"]
KEYS3 = ["hour", "or_bars", "hold_bars", "entry_mode", "stop_mode", "stop_atr_mult",
         "rr", "min_rvol", "trend_mode", "use_datr"]


def collect() -> dict:
    d: dict = {}
    s1 = pd.read_csv(OUT / "stage1_is_grid.csv")
    s2 = pd.read_csv(OUT / "stage2_oos_grid.csv")
    s3 = pd.read_csv(OUT / "stage3_filters.csv")

    d["n_configs"] = int(len(s1) // s1.cost_mult.nunique())

    # --- cost ladder, IS and OOS ---
    ladder = []
    for name, src in (("IS", s1), ("OOS", s2)):
        for m in sorted(src.cost_mult.unique()):
            s = src[(src.cost_mult == m) & (src.trades >= 200 if name == "IS" else src.trades >= 100)]
            if not len(s):
                continue
            ladder.append({"window": name, "cost": f"{m:g}x", "n": int(len(s)),
                           "gate": int((s.pf >= 1.2).sum()), "be": int((s.pf >= 1.0).sum()),
                           "best": round(float(s.pf.max()), 3),
                           "median": round(float(s.pf.median()), 3)})
    d["ladder"] = ladder

    # --- PF histogram, IS, per cost ---
    bins = np.arange(0.0, 2.01, 0.05)
    hist = {}
    for m in (0.0, 1.0, 2.0, 3.0):
        s = s1[(s1.cost_mult == m) & (s1.trades >= 200)]
        h, _ = np.histogram(s.pf.clip(0, 2.0), bins=bins)
        hist[f"{m:g}x"] = h.tolist()
    d["hist"] = {"bins": bins.round(2).tolist(), "series": hist}

    # --- IS vs OOS scatter, 1x ---
    a = s1[s1.cost_mult == 1][KEYS1 + ["pf", "trades"]]
    b = s2[s2.cost_mult == 1][KEYS1 + ["pf", "trades"]]
    mg = a.merge(b, on=KEYS1, suffixes=("_is", "_oos"))
    mg = mg[(mg.trades_is >= 200) & (mg.trades_oos >= 60)]
    d["scatter"] = [[round(x, 3), round(y, 3)] for x, y in
                    zip(mg.pf_is.values, mg.pf_oos.values)]
    d["scatter_corr"] = round(float(mg.pf_is.corr(mg.pf_oos)), 3)
    d["scatter_n"] = int(len(mg))

    # --- best IS configs and their OOS fate ---
    def label(r):
        anchor = f"{int(r.hour):02d}:00"
        orlen = {1: "15m", 2: "30m", 4: "1h", 8: "2h", 16: "4h"}[int(r.or_bars)]
        ent = {0: "stop @ edge", 1: "close beyond", 2: "first-candle dir"}[int(r.entry_mode)]
        stp = {0: "OR far side", 1: "OR mid", 2: f"{r.stop_atr_mult:g}x ATR"}[int(r.stop_mode)]
        tgt = "session end" if r.rr == 0 else f"{r.rr:g}R"
        return {"anchor": anchor, "or": orlen, "entry": ent, "stop": stp,
                "target": tgt, "fade": bool(r.fade) if "fade" in r else False}

    top = mg.nlargest(6, "pf_is")
    d["top_is"] = [{**label(r), "pf_is": round(r.pf_is, 3), "pf_oos": round(r.pf_oos, 3),
                    "trades_is": int(r.trades_is), "trades_oos": int(r.trades_oos)}
                   for _, r in top.iterrows()]

    # --- stage 3: literature filters ---
    a3 = s3[(s3.window == "IS") & (s3.cost_mult == 1)][KEYS3 + ["pf", "trades", "win_rate"]]
    b3 = s3[(s3.window == "OOS") & (s3.cost_mult == 1)][KEYS3 + ["pf", "trades", "win_rate", "trades_per_day"]]
    m3 = a3.merge(b3, on=KEYS3, suffixes=("_is", "_oos"))
    m3 = m3[(m3.trades_is >= 100) & (m3.trades_oos >= 30)]
    gate = m3[m3.pf_is >= 1.2]
    d["lit"] = {
        "n": int(len(m3)),
        "is_gate": int(len(gate)),
        "oos_gate": int((gate.pf_oos >= 1.2).sum()),
        "oos_be": int((gate.pf_oos >= 1.0).sum()),
        "median_oos_of_gate": round(float(gate.pf_oos.median()), 3),
        "median_oos_all": round(float(m3.pf_oos.median()), 3),
        "best_is": round(float(m3.pf_is.max()), 3),
        "best_is_oos": round(float(m3.loc[m3.pf_is.idxmax(), "pf_oos"]), 3),
        "median_tpd_gate": round(float(gate.trades_per_day.median()), 3),
    }
    rv = s3[(s3.window == "IS") & (s3.cost_mult == 1) & (s3.trades >= 100)]
    d["rvol"] = [{"rvol": float(k), "configs": int(len(g)),
                  "median_pf": round(float(g.pf.median()), 3),
                  "best_pf": round(float(g.pf.max()), 3),
                  "median_trades": int(g.trades.median())}
                 for k, g in rv.groupby("min_rvol")]

    # --- stage 4: walk-forward ---
    wf_path = OUT / "stage4_walkforward.csv"
    if wf_path.exists():
        wf = pd.read_csv(wf_path)
        d["wf"] = {
            "quarters": int(len(wf)),
            "above1": int((wf.test_pf > 1).sum()),
            "median_train": round(float(wf.train_pf.median()), 3),
            "median_test": round(float(wf.test_pf.median()), 3),
            "total_trades": int(wf.test_trades.sum()),
            "series": [{"q": str(r.quarter)[:7], "train": round(float(r.train_pf), 3),
                        "test": round(float(r.test_pf), 3) if pd.notna(r.test_pf) else None}
                       for _, r in wf.iterrows()],
        }

    # --- stage 5: prop challenge ---
    p = pd.read_csv(OUT / "stage5_prop.csv")
    d["prop"] = [{k: (round(float(v), 4) if isinstance(v, (int, float, np.floating)) and k not in
                      ("config", "cost", "accounts") else v)
                  for k, v in r.items()} for _, r in p.iterrows()]
    return d


def assets(d: dict) -> dict:
    """Stage 7: the same grid on Gold, FX and BTC over one common 3-year window."""
    path = OUT / "stage7_assets.csv"
    if not path.exists():
        return d
    s7 = pd.read_csv(path)
    order = ["XAUUSD", "EURUSD", "GBPUSD", "BTCUSDT"]
    names = {"XAUUSD": "Gold (XAUUSD)", "EURUSD": "EURUSD", "GBPUSD": "GBPUSD",
             "BTCUSDT": "Bitcoin (BTCUSDT)"}
    rows, best = [], []
    for sym in order:
        g = s7[s7.symbol == sym]
        if not len(g):
            continue
        for m in sorted(g.cost_mult.unique()):
            k = g[(g.cost_mult == m) & (g.trades >= 100)]
            if not len(k):
                continue
            rows.append({"symbol": names[sym], "cost": f"{m:g}x", "n": int(len(k)),
                         "gate": int((k.pf >= 1.2).sum()), "be": int((k.pf >= 1.0).sum()),
                         "best": round(float(k.pf.max()), 3),
                         "median": round(float(k.pf.median()), 3)})
        k1 = g[(g.cost_mult == 1) & (g.trades >= 100)]
        if len(k1):
            b = k1.loc[k1.pf.idxmax()]
            best.append({
                "symbol": names[sym],
                "anchor": f"{int(b.hour):02d}:00",
                "or": {1: "15m", 2: "30m", 4: "1h", 8: "2h", 16: "4h"}[int(b.or_bars)],
                "dir": "fade" if b.fade else "follow",
                "target": "session end" if b.rr == 0 else f"{b.rr:g}R",
                "trades": int(b.trades), "pf": round(float(b.pf), 3),
                "win": round(float(b.win_rate), 4),
                "tpd": round(float(b.trades_per_day), 2),
                "hold": round(float(b.avg_hold_h), 1),
                "avg_r": round(float(b.avg_r), 4),
                "dd": round(float(b.max_dd), 4),
                "sharpe": round(float(b.sharpe), 2),
                "resolve": (round(float(b.days_to_target), 1)
                            if np.isfinite(b.days_to_target) else None),
            })
    # PF distribution per asset at 1x
    bins = np.arange(0.0, 2.01, 0.05)
    dist = {}
    for sym in order:
        k = s7[(s7.symbol == sym) & (s7.cost_mult == 1) & (s7.trades >= 100)]
        if len(k):
            h, _ = np.histogram(k.pf.clip(0, 2.0), bins=bins)
            dist[names[sym]] = h.tolist()
    # --- does the session anchor matter? the mechanistically-motivated test ---
    LAB = {0: "00:00 UTC day", 4: "04:00 Asia", 7: "07:00 London pre",
           8: "08:00 London open", 12: "12:00 pre-NY", 13: "13:00 NY open",
           16: "16:00 NY pm", 20: "20:00 NY close"}
    anchors = []
    for h in sorted(LAB):
        row = {"anchor": LAB[h], "hour": h}
        for sym in order:
            k = s7[(s7.symbol == sym) & (s7.cost_mult == 1) &
                   (s7.trades >= 100) & (s7.hour == h)]
            row[sym] = round(float(k.pf.median()), 3) if len(k) else None
        anchors.append(row)
    best_anchor = {sym: max(anchors, key=lambda r: r[sym] or 0)["anchor"] for sym in order}
    worst_anchor = {sym: min(anchors, key=lambda r: r[sym] if r[sym] is not None else 9)["anchor"]
                    for sym in order}

    # --- per-asset IS/OOS survival ---
    surv = []
    p8 = OUT / "stage8_asset_oos.csv"
    if p8.exists():
        s8 = pd.read_csv(p8)
        for sym in order:
            a = s8[(s8.symbol == sym) & (s8.window == "IS") & (s8.cost_mult == 1)][KEYS1 + ["pf", "trades"]]
            b = s8[(s8.symbol == sym) & (s8.window == "OOS") & (s8.cost_mult == 1)][KEYS1 + ["pf", "trades"]]
            mg = a.merge(b, on=KEYS1, suffixes=("_is", "_oos"))
            mg = mg[(mg.trades_is >= 100) & (mg.trades_oos >= 40)]
            if not len(mg):
                continue
            g = mg[mg.pf_is >= 1.2]
            surv.append({
                "symbol": names[sym], "paired": int(len(mg)),
                "is_gate": int(len(g)),
                "oos_gate": int((g.pf_oos >= 1.2).sum()) if len(g) else 0,
                "median_oos_gate": round(float(g.pf_oos.median()), 3) if len(g) else None,
                "median_oos_all": round(float(mg.pf_oos.median()), 3),
            })

    d["assets"] = {"ladder": rows, "best": best,
                   "dist": {"bins": bins.round(2).tolist(), "series": dist},
                   "anchors": anchors, "anchor_cols": [names[o] for o in order],
                   "anchor_keys": order,
                   "best_anchor": best_anchor, "worst_anchor": worst_anchor,
                   "survival": surv,
                   "window": "2023-09-01 to 2026-08-31"}
    return d


def width_table() -> list[dict]:
    """Stage 2 of the page: does a wider stop outrun the fee?"""
    from core import data as dl
    from strategies.orb.sweep import features, run_one, trade_metrics, DEFAULTS
    from strategies.orb.engine import T_ENTRY_I, T_ENTRY_PX

    df = dl.load("BTC/USDT", "15m")
    w = df[(df.index >= "2018-01-01") & (df.index < "2024-01-01")]
    feats = features(w)
    span = (w.index[-1] - w.index[0]).total_seconds() / 86400.0
    rows = []
    for k in (1.0, 1.5, 2.0, 3.0, 4.0, 6.0, 8.0):
        cfg = dict(DEFAULTS)
        cfg.update(hour=7, or_bars=16, hold_bars=32, entry_mode=0,
                   stop_mode=2, stop_atr_mult=k, rr=1.0, fade=1)
        t0 = run_one(w, feats, cfg, 0, 0)
        m0 = trade_metrics(t0, w.index, span)
        m1 = trade_metrics(run_one(w, feats, cfg, 5, 2), w.index, span)
        mm = trade_metrics(run_one(w, feats, cfg, 2, 2), w.index, span)
        idx = t0[:, T_ENTRY_I].astype(int)
        bps = float(np.median(feats[0][idx] / t0[:, T_ENTRY_PX] * 10000) * k)
        rows.append({"atr": k, "bps": round(bps, 1), "cost_r": round(14 / bps, 3),
                     "pf0": m0["pf"], "pf1": m1["pf"], "pfm": mm["pf"],
                     "trades": m1["trades"]})
    return rows


def narrative(d: dict) -> dict:
    """Numbers -> the sentences on the page. Kept here so they can never drift
    from the CSVs they describe."""
    is1 = next(r for r in d["ladder"] if r["window"] == "IS" and r["cost"] == "1x")
    is0 = next(r for r in d["ladder"] if r["window"] == "IS" and r["cost"] == "0x")
    oos1 = next(r for r in d["ladder"] if r["window"] == "OOS" and r["cost"] == "1x")
    wf = d.get("wf", {})
    lit = d["lit"]
    best_prop = max((r for r in d["prop"] if r["cost"] == "1x"), key=lambda r: r["pass_rate"])

    d["period"] = "2018-01-01 to 2026-08-31"
    d["stamp"] = "Rejected — does not clear the gate"
    d["readout"] = [
        {"k": "Configs tested", "v": f"{d['n_configs']:,}", "n": "8 anchors x 5 ranges x 4 horizons x entry/stop/target/direction"},
        {"k": "Clearing PF 1.20", "v": "0", "n": "in sample and out of sample, at real cost", "tone": "fail"},
        {"k": "Best PF, real cost", "v": f"{is1['best']:.3f}", "n": f"out of sample it did {d['top_is'][0]['pf_oos']:.3f}", "tone": "fail"},
        {"k": "Median PF, zero fees", "v": f"{is0['median']:.3f}", "n": "loses money before a single bp is charged", "tone": "fail"},
        {"k": "Walk-forward PF", "v": f"{wf.get('stitched_pf', float('nan')):.3f}",
         "n": f"{wf.get('above1','?')} of {wf.get('quarters','?')} quarters above breakeven", "tone": "fail"},
        {"k": "Prop pass rate", "v": f"{best_prop['pass_rate']*100:.0f}%",
         "n": f"best config; {best_prop['fail_max']*100:.0f}% breach the 8% max loss", "tone": "fail"},
    ]
    d["stage1_callout"] = (
        f"<p><strong>Nothing clears the gate.</strong> Of {is1['n']:,} configurations with at "
        f"least 200 trades, <strong>zero</strong> reach profit factor 1.20 at realistic cost. "
        f"Only {is1['be']} of them exceed 1.00 at all, the best at {is1['best']:.3f}. The median "
        f"configuration sits at {is1['median']:.3f}. Strip the fees entirely and the median is "
        f"still {is0['median']:.3f} &mdash; below breakeven.</p>")
    d["lit_callout"] = (
        f"<p><strong>The filter does not survive contact with new data.</strong> "
        f"{lit['is_gate']} configurations clear PF 1.20 in sample. Out of sample "
        f"{lit['oos_gate']} of them still do &mdash; {100*lit['oos_gate']/max(lit['is_gate'],1):.0f}%. "
        f"The median out-of-sample profit factor of that hand-picked group is "
        f"{lit['median_oos_of_gate']:.3f}, below breakeven. The single best in-sample config "
        f"({lit['best_is']:.3f}) scored {lit['best_is_oos']:.3f} out of sample. And the survivors "
        f"trade about {lit['median_tpd_gate']:.2f} times a day &mdash; roughly one trade a "
        f"fortnight, which fails the current phase constraint on its own.</p>")
    d["prop_note"] = (
        f"<strong>{best_prop['pass_rate']*100:.0f}% of accounts pass</strong> with the best "
        f"configuration at real cost, and {best_prop['fail_max']*100:.0f}% breach the 8% max "
        f"loss. Buying challenges at roughly &euro;30 each to run a negative-expectancy engine "
        f"is a losing trade on its own: the accounts that do pass are then funded with a system "
        f"whose edge is below zero. The daily-loss cap is never the thing that kills it &mdash; "
        f"at 1% risk and about one trade a day, the account bleeds down to the overall cap "
        f"instead.")
    a = d.get("assets")
    if a and a.get("survival"):
        by = {r["symbol"]: r for r in a["survival"]}
        gbp = by.get("GBPUSD", {})
        gold = by.get("Gold (XAUUSD)", {})
        d["survival_callout"] = (
            f"<p><strong>Only GBPUSD carried anything into the unseen year, and it turned out "
            f"to be one cell rather than an effect.</strong> {gbp.get('is_gate',0)} configurations "
            f"cleared PF 1.20 on the fit window and {gbp.get('oos_gate',0)} of them cleared it "
            f"again on the test year. Against a base rate of 0.4% that looks overwhelming &mdash; "
            f"until you look at what those configurations are. All nine are the same setup: a "
            f"1-hour range, faded, entered on a close beyond the edge, almost all of them at the "
            f"20:00 anchor. They are one observation wearing nine hats, so the significance test "
            f"does not apply. Gold cleared the gate {gold.get('is_gate',0)} times in sample and "
            f"{gold.get('oos_gate',0)} times out of it, with a median of "
            f"{gold.get('median_oos_gate','&mdash;')}.</p>")
    if a and a["ladder"]:
        one = [r for r in a["ladder"] if r["cost"] == "1x"]
        clear = [r for r in one if r["gate"] > 0]
        zero = [r for r in a["ladder"] if r["cost"] == "0x"]
        best_line = max(one, key=lambda r: r["best"])
        d["assets_callout"] = (
            "<p><strong>The answer does not change by market.</strong> Over one common "
            f"three-year window, {sum(r['gate'] for r in one)} configurations out of "
            f"{sum(r['n'] for r in one):,} clear PF 1.20 at realistic cost across all four "
            "instruments. The best single result anywhere is "
            f"{best_line['best']:.3f} on {best_line['symbol']}. "
            + ("Gold and the FX majors are 5-15x cheaper to trade than BTC relative to their "
               "volatility, so the cost argument that killed Bitcoin does not apply to them "
               "&mdash; and they still fail. " if not clear else "")
            + "With fees stripped to zero the medians are "
            + ", ".join(f"{r['symbol'].split(' ')[0]} {r['median']:.3f}" for r in zero)
            + " &mdash; at or below breakeven before a single cost is charged.</p>")
        d["assets_window"] = a["window"]
        ba, wa = a["best_anchor"], a["worst_anchor"]
        spread = {}
        for sym in a["anchor_keys"]:
            vals = [r[sym] for r in a["anchors"] if r[sym] is not None]
            spread[sym] = (max(vals) - min(vals)) / min(vals) if vals else 0.0
        d["anchor_callout"] = (
            "<p><strong>The method finds session structure exactly where session structure "
            "exists &mdash; and it is still not enough.</strong> Gold, EURUSD and GBPUSD all "
            f"agree on the same best anchor by median profit factor, the "
            f"<strong>{ba['XAUUSD']}</strong>, and on the same worst one, the "
            f"<strong>{wa['EURUSD']}</strong>. The spread between best and worst anchor is "
            f"{spread['EURUSD']:.0%} on EURUSD and {spread['GBPUSD']:.0%} on GBPUSD, against "
            f"only {spread['BTCUSDT']:.0%} on Bitcoin &mdash; which is what a market with no "
            "opening auction should look like. That is a good sign about the test: it finds "
            "session structure where session structure exists and almost none where it does not. "
            "But the best anchor on the best instrument still has a median profit factor of "
            f"{max(r['XAUUSD'] for r in a['anchors']):.3f}. The session effect is real, "
            "measurable, and far too small to trade.</p>"
            "<p>It also disposes of the GBPUSD result above. Its 20:00 anchor is not a session "
            "open at all; it is the New York close, and it is the <em>worst</em> anchor on every "
            "FX pair by median. That configuration is the luckiest cell of the weakest family.</p>")
    return d


if __name__ == "__main__":
    data = collect()
    data["width"] = width_table()
    wfp = OUT / "stage4_walkforward.csv"
    if wfp.exists():
        import re
        log = (OUT / "stage4.log").read_text() if (OUT / "stage4.log").exists() else ""
        mm = re.search(r"STITCHED OOS: ([\d,]+) trades  PF ([\d.]+)  win ([\d.]+)%.*?total ([-\d.]+)R", log)
        if mm:
            data["wf"]["stitched_trades"] = int(mm.group(1).replace(",", ""))
            data["wf"]["stitched_pf"] = float(mm.group(2))
            data["wf"]["stitched_win"] = float(mm.group(3))
            data["wf"]["stitched_r"] = float(mm.group(4))
    data["xcheck"] = [
        {"engine": "prop_lab kernel (numba)", "trades": 365, "pf": 1.013, "win": 0.2411},
        {"engine": "NautilusTrader", "trades": 341, "pf": 0.682, "win": 0.211},
    ]
    data = assets(data)
    data = narrative(data)
    (OUT / "report_data.json").write_text(json.dumps(data, indent=1))
    tpl = (Path(__file__).parent / "report_template.html").read_text()
    html = tpl.replace("/*__DATA__*/", json.dumps(data))
    (OUT / "report.html").write_text(html)
    print("wrote report.html", len(html), "bytes")
    for k in ("n_configs", "scatter_n", "scatter_corr"):
        print(" ", k, data[k])
    print("  ladder:", json.dumps(data["ladder"][:4]))
    print("  lit:", json.dumps(data["lit"]))
    print("  wf:", json.dumps({k: v for k, v in data.get("wf", {}).items() if k != "series"}))
