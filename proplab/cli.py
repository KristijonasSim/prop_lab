"""Command line: fetch data, run backtests, log results, inspect the DB.

    python -m proplab.cli fetch   --symbol BTCUSDT --timeframe 15m --start 2020-01-01
    python -m proplab.cli list
    python -m proplab.cli run     --strategy orb_v1 --timeframe 1h --log
    python -m proplab.cli oos     --strategy orb_v1 --split-at 2024-01-01
    python -m proplab.cli status
    python -m proplab.cli failed
    python -m proplab.cli dashboard
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

import pandas as pd

from . import runner
from .config import BacktestConfig, CostModel, PropFirmRules
from .db import store
from .research import acceptance, multiple_testing
from .strategy import registry

ROOT = Path(__file__).resolve().parents[1]


def _print_result(res, conn=None) -> None:
    m, p = res.metrics, res.prop
    print("\n" + "=" * 78)
    print(runner.summary_line(res))
    print("=" * 78)

    checks = res.meta.get("checks", [])
    if checks:
        print("\nAUTOMATED CHECKS")
        for c in checks:
            print(f"  [{'PASS' if c['passed'] else 'FAIL'}] {c['name']:26} {c['detail']}")
            for f in (c.get("findings") or [])[:3]:
                print(f"         - {f}")

    print("\nHEADLINE")
    hold = m.get("avg_hold_hours")
    hold_s = (f"{hold:.1f}h ({hold/24:.1f}d)" if hold else "-")
    print(f"  profit factor        {m.get('profit_factor')}")
    print(f"  win rate             {m.get('win_rate_pct')}%")
    print(f"  average R multiple   {m.get('avg_r')}")
    print(f"  trades/day           {m.get('trades_per_day')}   "
          f"(per week {m.get('trades_per_week')})")
    print(f"  average hold time    {hold_s}   "
          f"(median {m.get('median_hold_hours')}h, max {m.get('max_hold_days')}d)")
    resolution = m.get("resolution") or {}
    if resolution:
        print("\n  TIME TO RESOLVE (target vs drawdown, from this run's daily P&L)")
        print(f"    daily P&L          mean {resolution.get('daily_pnl_mean')} "
              f"sd {resolution.get('daily_pnl_std')}")
        print(f"    days to target     {resolution.get('days_to_target_at_current_rate')} "
              f"(at the observed rate)")
        print(f"    days to breach     {resolution.get('days_to_breach_at_current_rate')}")
        print(f"    P(target first)    {resolution.get('p_target_before_breach')}")
        print(f"    expected days      {resolution.get('expected_days_to_resolution')}")
        print(f"    -> {resolution.get('verdict')}")

    print("\nPERFORMANCE (raw)")
    for k in ("n_trades", "win_rate_pct", "profit_factor", "expectancy_r", "t_stat",
              "total_return_pct", "cagr_pct", "sharpe", "sortino", "max_drawdown_pct",
              "trades_per_week", "exposure_pct", "total_fees", "total_funding",
              "total_costs", "cost_pct_of_gross_profit", "cost_pct_of_start_balance",
              "max_consecutive_losses"):
        if k in m:
            print(f"  {k:26} {m[k]}")
    if m.get("exit_reasons"):
        print(f"  {'exit_reasons':26} {m['exit_reasons']}")

    print(f"\nPROP FIRM: {'PASS' if p['passed'] else 'FAIL'}")
    for name, c in p["checks"].items():
        kind = "HARD" if c["hard"] else "qual"
        detail = {k: v for k, v in c.items() if k not in ("hard", "passed", "note")}
        print(f"  [{'ok ' if c['passed'] else 'FAIL'}][{kind}] {name:22} {detail}")
        if not c["passed"] and c.get("note"):
            print(f"         note: {c['note']}")
    if p.get("first_breach_rule"):
        print(f"  !! account dead at {p['first_breach_time']} via {p['first_breach_rule']}"
              f" (survived {p['days_survived_before_breach']} days)")

    if conn is not None and m.get("n_trades", 0) > 0 and res.meta.get("split") == "oos":
        n_trials = store.trial_count(conn)["runs_all_hypotheses"] + 1
        card = acceptance.score(res, n_trials=n_trials)
        print("\nACCEPTANCE SCORECARD")
        print(f"  profile: {card['profile']}")
        titles = {1: "TIER 1 - validity (is the result real?)",
                  2: "TIER 2 - viability (can it clear an evaluation?)",
                  3: "TIER 3 - robustness (advisory; does not block)"}
        for tier in (1, 2, 3):
            print(f"\n  {titles[tier]}")
            for g in [x for x in card["gates"] if x["tier"] == tier]:
                arrow = ">=" if g["direction"] == "min" else "<="
                mark = "ok  " if g["passed"] else ("FLAG" if tier == 3 else "FAIL")
                print(f"    [{mark}] {g['gate']:24} {str(g['value']):>10}  "
                      f"{arrow} {g['threshold']}")
        d = card["diagnostics"]
        print("\n  diagnostics (no thresholds - these trade off against each other)")
        print(f"    PF {d.get('profit_factor')} · avg R {d.get('avg_r')} · "
              f"win {d.get('win_rate_pct')}% · {d.get('trades_per_day')}/day · "
              f"hold {d.get('avg_hold_hours')}h · CAGR {d.get('cagr_pct')}%")
        print(f"\n  -> {card['verdict']}")

    if conn is not None and m.get("n_trades", 0) > 0:
        tc = store.trial_count(conn)
        n_trials = tc["runs_all_hypotheses"] + 1      # counting this one
        years = m.get("days_tested", 0) / 365
        dsr = multiple_testing.deflated_sharpe(
            m.get("sharpe", 0), n_trials, max(years, 1e-6), res.meta.get("bars", 0))
        print(f"\nMULTIPLE TESTING (this is trial #{n_trials} overall)")
        print(f"  noise would produce a Sharpe of ~{dsr['benchmark_sharpe']} "
              f"across {n_trials} tries")
        print(f"  deflated Sharpe p = {dsr['deflated_sharpe']} -> {dsr['verdict']}")
    print()


def cmd_fetch(a):
    from .data.binance import download
    path = download(a.symbol, a.timeframe, a.start, a.end, a.market, force=a.force)
    df = pd.read_parquet(path)
    print(f"{path}  bars={len(df)}  {df.index[0]} .. {df.index[-1]}")


def cmd_list(a):
    reg = registry.discover()
    if not reg:
        print("No strategies yet. Copy proplab/strategy/TEMPLATE.py into "
              "proplab/strategy/library/<slug>.py")
        return
    for name, cls in sorted(reg.items()):
        print(f"{name:24} {cls.__module__}")
        print(f"    variation: {cls.variation or '-'}")
        print(f"    tfs: {cls.higher_timeframes or '-'}  params: {cls.params}")


def _config(a) -> BacktestConfig:
    return BacktestConfig(
        symbol=a.symbol, primary_timeframe=a.timeframe,
        max_leverage=a.max_leverage, allow_shorts=not a.no_shorts,
        costs=CostModel(taker_fee_bps=a.fee_bps, slippage_bps=a.slippage_bps),
        rules=PropFirmRules(starting_balance=a.balance,
                            daily_loss_limit_pct=a.daily_loss_pct,
                            max_drawdown_pct=a.max_dd_pct,
                            trailing_drawdown_pct=a.trailing_dd_pct,
                            profit_target_pct=a.profit_target_pct,
                            min_trading_days=a.min_days),
    )


def cmd_run(a):
    cls = registry.get(a.strategy)
    params = json.loads(a.params) if a.params else None
    renko = _renko(a)

    # ---- out-of-sample is a one-shot resource -------------------------------
    if a.split == "oos":
        if not a.variation:
            raise SystemExit(
                "An out-of-sample run must name --variation: the one-look rule "
                "is tracked per variation, and an untracked look is exactly the "
                "thing it exists to prevent.")
        guard = store.connect()
        try:
            store.assert_oos_available(guard, a.variation, a.burn_oos or "")
        except store.OOSAlreadyUsed as e:
            raise SystemExit(f"\nREFUSED: {e}\n") from None
        finally:
            guard.close()
        if not a.log:
            a.log = True
            print("note: forcing --log. An out-of-sample look that is not "
                  "recorded is a free peek, which defeats the rule.\n")

    res = runner.backtest(cls, symbol=a.symbol, timeframe=a.timeframe, start=a.start,
                          end=a.end, config=_config(a), params=params, split=a.split,
                          base_timeframe=a.base_timeframe, run_checks=not a.skip_checks,
                          renko=renko)
    conn = store.connect()
    try:
        _print_result(res, conn)
        if a.cost_sweep:
            table, _ = runner.cost_sensitivity(
                cls, symbol=a.symbol, timeframe=a.timeframe, start=a.start,
                end=a.end, config=_config(a), params=params, split=a.split,
                base_timeframe=a.base_timeframe, renko=renko)
            print("COST SENSITIVITY (venue not yet chosen - costs are an assumption)")
            print(table.to_string(index=False))
            survives = table[table["cost_x"] >= 2.0]["return_pct"]
            if len(survives) and (survives <= 0).any():
                print("  -> dies at 2x costs: treat any 1x result as a fee-schedule bet\n")
            else:
                print()
        if a.log:
            uid = store.insert_run(conn, res, variation_slug=a.variation,
                                   split=a.split, notes=a.notes or "")
            print(f"logged run {uid}")
        else:
            print("NOT logged (pass --log to record this run in the database)")
    finally:
        conn.close()


def _renko(a):
    """Brick settings for renko strategies, so a renko run is reproducible from
    the command line instead of an ad-hoc script. Omitting it leaves the loader
    on its ATR-sized default, which is a different dataset - hence the echo."""
    raw = getattr(a, "renko", None)
    if not raw:
        return None
    cfg = json.loads(raw)
    print(f"renko bricks: {cfg}")
    return cfg


def _no_sweep(a):
    return getattr(a, "cost_sweep", False)


def cmd_oos(a):
    cls = registry.get(a.strategy)
    if a.variation:
        guard = store.connect()
        try:
            store.assert_oos_available(guard, a.variation, a.burn_oos or "")
        except store.OOSAlreadyUsed as e:
            raise SystemExit(f"\nREFUSED: {e}\n") from None
        finally:
            guard.close()
    out = runner.in_sample_out_of_sample(
        cls, split_at=a.split_at, symbol=a.symbol, timeframe=a.timeframe,
        start=a.start, end=a.end, config=_config(a), base_timeframe=a.base_timeframe,
        renko=_renko(a))
    conn = store.connect()
    try:
        for label in ("is", "oos"):
            print(f"\n########## {label.upper()} ##########")
            _print_result(out[label], conn)
            if a.log:
                uid = store.insert_run(conn, out[label], variation_slug=a.variation,
                                       split=label, notes=a.notes or "")
                print(f"logged {label} run {uid}")
        i, o = out["is"].metrics, out["oos"].metrics
        print("\nIN-SAMPLE vs OUT-OF-SAMPLE")
        for k in ("n_trades", "total_return_pct", "sharpe", "profit_factor",
                  "expectancy_r", "max_drawdown_pct", "win_rate_pct"):
            print(f"  {k:20} IS={i.get(k)!s:>12}   OOS={o.get(k)!s:>12}")
        _print_decay(i.get("sharpe"), o.get("sharpe"))
    finally:
        conn.close()


def cmd_hypothesis(a):
    conn = store.connect()
    try:
        hid = store.upsert_hypothesis(
            conn, a.slug, a.title, _text(a.description), _text(a.mechanism),
            _text(a.research), a.asset_class, a.symbol, a.status)
        print(f"hypothesis #{hid} {a.slug} -> {a.status}")
    finally:
        conn.close()


def cmd_variation(a):
    conn = store.connect()
    try:
        code_path, code_hash = "", ""
        if a.strategy:
            cls = registry.get(a.strategy)
            src = registry.source_of(cls)
            code_path = str(Path(sys.modules[cls.__module__].__file__))
            code_hash = __import__("proplab.checks.compliance", fromlist=["x"]) \
                .strategy_fingerprint(src)
        vid = store.upsert_variation(
            conn, a.hypothesis, a.slug, a.title, _text(a.rationale), _text(a.details),
            a.strategy or "", code_path, code_hash,
            json.loads(a.params) if a.params else None, a.status, _text(a.note))
        print(f"variation #{vid} {a.slug} -> {a.status}")
    finally:
        conn.close()


def cmd_set_status(a):
    conn = store.connect()
    try:
        store.set_status(conn, a.entity, a.slug, a.status, _text(a.note))
        print(f"{a.entity} {a.slug} -> {a.status}")
    finally:
        conn.close()


def _text(value: str | None) -> str:
    """Accept either literal text or @path/to/file for long prose."""
    if not value:
        return ""
    if value.startswith("@"):
        return Path(value[1:]).read_text()
    return value


def _print_decay(is_sharpe, oos_sharpe):
    """Sharpe decay only means something when the in-sample Sharpe is positive."""
    if is_sharpe is None or oos_sharpe is None:
        return
    if is_sharpe <= 0:
        print(f"  sharpe decay: n/a - in-sample Sharpe is {is_sharpe}, so there was "
              f"nothing to decay from (OOS {oos_sharpe})")
        return
    decay = 1 - (oos_sharpe / is_sharpe)
    verdict = ("OOS edge vanished or reversed - assume overfit" if decay > 0.75 else
               "large decay - treat with suspicion" if decay > 0.5 else
               "moderate decay - normal for a real edge" if decay > 0.2 else
               "held up out of sample")
    print(f"  sharpe decay IS->OOS: {decay:.1%} ({verdict})")


def cmd_status(a):
    conn = store.connect()
    try:
        ov = store.overview(conn)
        print(ov.to_string(index=False) if len(ov) else "no hypotheses recorded yet")
        tc = store.trial_count(conn)
        print(f"\ntotal runs logged: {tc['runs_all_hypotheses']} "
              f"across {tc['variations']} variations")
    finally:
        conn.close()


def cmd_failed(a):
    conn = store.connect()
    try:
        df = store.failed_ideas(conn)
        print(df.to_string(index=False) if len(df) else "no rejected variations yet")
    finally:
        conn.close()


def cmd_oos_ledger(a):
    conn = store.connect()
    try:
        df = store.oos_ledger(conn)
        print(df.to_string(index=False) if len(df) else "nothing recorded yet")
        spent = int((df["oos_looks"] > 0).sum()) if len(df) else 0
        print(f"\n{spent} variation(s) have spent their out-of-sample look.")
    finally:
        conn.close()


def cmd_dashboard(a):
    subprocess.run([sys.executable, "-m", "streamlit", "run",
                    str(ROOT / "dashboard" / "app.py")], check=False)


def build_parser():
    ap = argparse.ArgumentParser(prog="proplab")
    sub = ap.add_subparsers(dest="cmd", required=True)

    f = sub.add_parser("fetch", help="download OHLCV from Binance")
    f.add_argument("--symbol", default="BTCUSDT")
    f.add_argument("--timeframe", default="15m")
    f.add_argument("--start", default="2020-01-01")
    f.add_argument("--end", default=None)
    f.add_argument("--market", default="futures", choices=["futures", "spot"])
    f.add_argument("--force", action="store_true")
    f.set_defaults(func=cmd_fetch)

    hy = sub.add_parser("hypothesis", help="create/update a hypothesis")
    hy.add_argument("--slug", required=True)
    hy.add_argument("--title", required=True)
    hy.add_argument("--description", default="", help="text, or @file")
    hy.add_argument("--mechanism", default="", help="text, or @file")
    hy.add_argument("--research", default="", help="text, or @file")
    hy.add_argument("--asset-class", default="crypto")
    hy.add_argument("--symbol", default="")
    hy.add_argument("--status", default="queued", choices=store.STATUSES)
    hy.set_defaults(func=cmd_hypothesis)

    va = sub.add_parser("variation", help="create/update a variation")
    va.add_argument("--hypothesis", required=True, help="hypothesis slug")
    va.add_argument("--slug", required=True)
    va.add_argument("--title", required=True)
    va.add_argument("--rationale", default="", help="why THIS variation is worth testing")
    va.add_argument("--details", default="", help="concrete rule differences")
    va.add_argument("--strategy", default=None, help="registry slug once coded")
    va.add_argument("--params", default=None, help="JSON")
    va.add_argument("--note", default="")
    va.add_argument("--status", default="queued", choices=store.STATUSES)
    va.set_defaults(func=cmd_variation)

    ss = sub.add_parser("set-status", help="move something through the pipeline")
    ss.add_argument("--entity", required=True, choices=["hypothesis", "variation"])
    ss.add_argument("--slug", required=True)
    ss.add_argument("--status", required=True, choices=store.STATUSES)
    ss.add_argument("--note", default="")
    ss.set_defaults(func=cmd_set_status)

    sub.add_parser("list", help="list registered strategies").set_defaults(func=cmd_list)
    sub.add_parser("status", help="hypothesis/variation overview").set_defaults(func=cmd_status)
    sub.add_parser("failed", help="rejected variations, so we don't repeat them").set_defaults(func=cmd_failed)
    sub.add_parser("oos-ledger", help="which variations have spent their out-of-sample look").set_defaults(func=cmd_oos_ledger)
    sub.add_parser("dashboard", help="launch the Streamlit dashboard").set_defaults(func=cmd_dashboard)

    for name, fn in (("run", cmd_run), ("oos", cmd_oos)):
        r = sub.add_parser(name)
        r.add_argument("--strategy", required=True)
        r.add_argument("--symbol", default="BTCUSDT")
        r.add_argument("--timeframe", default="15m")
        r.add_argument("--base-timeframe", default="15m")
        r.add_argument("--start", default=None)
        r.add_argument("--end", default=None)
        r.add_argument("--params", default=None, help='JSON, e.g. \'{"lookback":30}\'')
        r.add_argument("--variation", default=None, help="variation slug to log against")
        r.add_argument("--notes", default=None)
        r.add_argument("--log", action="store_true")
        r.add_argument("--balance", type=float, default=100_000.0)
        r.add_argument("--daily-loss-pct", type=float, default=4.0)
        r.add_argument("--max-dd-pct", type=float, default=8.0)
        r.add_argument("--trailing-dd-pct", type=float, default=8.0)
        r.add_argument("--profit-target-pct", type=float, default=8.0)
        r.add_argument("--min-days", type=int, default=5)
        r.add_argument("--fee-bps", type=float, default=4.5)
        r.add_argument("--slippage-bps", type=float, default=2.0)
        r.add_argument("--max-leverage", type=float, default=3.0)
        r.add_argument("--no-shorts", action="store_true")
        r.add_argument("--renko", default=None, metavar="JSON",
                       help='brick settings for renko strategies, e.g. '
                            '\'{"brick_size": 250}\' or \'{"atr_len": 14}\'')
        if name == "run":
            r.add_argument("--split", default="full", choices=["full", "is", "oos"])
            r.add_argument("--burn-oos", default=None, metavar="REASON",
                           help="deliberately spend a second out-of-sample look; "
                                "the reason is recorded permanently")
            r.add_argument("--skip-checks", action="store_true")
            r.add_argument("--cost-sweep", action="store_true",
                           help="also report results at 2x and 3x assumed costs")
        else:
            r.add_argument("--split-at", required=True)
            r.add_argument("--burn-oos", default=None, metavar="REASON",
                           help="deliberately spend a second out-of-sample look")
        r.set_defaults(func=fn)
    return ap


def main(argv=None):
    args = build_parser().parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main()
