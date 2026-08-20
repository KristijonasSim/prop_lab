"""SQLite persistence for hypotheses, variations, runs and trades."""
from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

DB_PATH = Path(__file__).resolve().parents[2] / "proplab.db"
SCHEMA = Path(__file__).with_name("schema.sql")

STATUSES = ("queued", "researching", "ready_to_code", "coding", "testing",
            "tested", "rejected", "passed")


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def connect(path: str | Path | None = None) -> sqlite3.Connection:
    # check_same_thread=False: Streamlit reruns the script on a different thread
    # than the one that built the cached connection. Writes stay serialised by
    # SQLite itself, and WAL mode (set in schema.sql) lets the dashboard read
    # while the CLI is writing.
    conn = sqlite3.connect(str(path or DB_PATH), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA.read_text())
    return conn


# ---------------------------------------------------------------- hypotheses
def upsert_hypothesis(conn, slug: str, title: str, description: str = "",
                      mechanism: str = "", research: str = "",
                      asset_class: str = "crypto", symbol: str = "",
                      status: str = "queued") -> int:
    _validate_status(status)
    cur = conn.execute("SELECT id FROM hypotheses WHERE slug = ?", (slug,))
    row = cur.fetchone()
    if row:
        conn.execute(
            """UPDATE hypotheses SET title=?, description=?, mechanism=?, research=?,
               asset_class=?, symbol=?, status=?, updated_at=? WHERE id=?""",
            (title, description, mechanism, research, asset_class, symbol, status,
             now(), row["id"]),
        )
        hid = row["id"]
    else:
        cur = conn.execute(
            """INSERT INTO hypotheses (slug,title,description,mechanism,research,
               asset_class,symbol,status,created_at,updated_at)
               VALUES (?,?,?,?,?,?,?,?,?,?)""",
            (slug, title, description, mechanism, research, asset_class, symbol,
             status, now(), now()),
        )
        hid = cur.lastrowid
    _event(conn, "hypothesis", hid, "upsert", status)
    conn.commit()
    return hid


# ---------------------------------------------------------------- variations
def upsert_variation(conn, hypothesis_slug: str, slug: str, title: str,
                     rationale: str = "", details: str = "",
                     strategy_name: str = "", code_path: str = "",
                     code_hash: str = "", params: dict | None = None,
                     status: str = "queued", verdict_note: str = "") -> int:
    _validate_status(status)
    hyp = conn.execute("SELECT id FROM hypotheses WHERE slug=?", (hypothesis_slug,)).fetchone()
    if not hyp:
        raise KeyError(f"No hypothesis {hypothesis_slug!r} - create it first.")
    params_json = json.dumps(params or {}, default=str)
    row = conn.execute("SELECT id FROM variations WHERE slug=?", (slug,)).fetchone()
    if row:
        conn.execute(
            """UPDATE variations SET hypothesis_id=?, title=?, rationale=?, details=?,
               strategy_name=?, code_path=?, code_hash=?, params_json=?, status=?,
               verdict_note=?, updated_at=? WHERE id=?""",
            (hyp["id"], title, rationale, details, strategy_name, code_path, code_hash,
             params_json, status, verdict_note, now(), row["id"]),
        )
        vid = row["id"]
    else:
        cur = conn.execute(
            """INSERT INTO variations (hypothesis_id,slug,title,rationale,details,
               strategy_name,code_path,code_hash,params_json,status,verdict_note,
               created_at,updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (hyp["id"], slug, title, rationale, details, strategy_name, code_path,
             code_hash, params_json, status, verdict_note, now(), now()),
        )
        vid = cur.lastrowid
    _event(conn, "variation", vid, "upsert", status)
    conn.commit()
    return vid


def set_status(conn, entity: str, slug: str, status: str, note: str = "") -> None:
    _validate_status(status)
    table = {"hypothesis": "hypotheses", "variation": "variations"}[entity]
    row = conn.execute(f"SELECT id FROM {table} WHERE slug=?", (slug,)).fetchone()
    if not row:
        raise KeyError(f"No {entity} {slug!r}")
    if entity == "variation":
        conn.execute("UPDATE variations SET status=?, verdict_note=?, updated_at=? WHERE id=?",
                     (status, note, now(), row["id"]))
    else:
        conn.execute("UPDATE hypotheses SET status=?, updated_at=? WHERE id=?",
                     (status, now(), row["id"]))
    _event(conn, entity, row["id"], "status", f"{status}: {note}")
    conn.commit()


# --------------------------------------------------------------------- runs
def insert_run(conn, result, variation_slug: str | None = None,
               split: str = "full", notes: str = "", store_trades: bool = True,
               store_equity: str = "daily") -> str:
    """Persist a completed run. Returns run_uuid."""
    meta, metrics, prop = result.meta, result.metrics, result.prop
    checks = meta.get("checks", [])
    vid = None
    if variation_slug:
        row = conn.execute("SELECT id FROM variations WHERE slug=?", (variation_slug,)).fetchone()
        if not row:
            raise KeyError(f"No variation {variation_slug!r} - create it first.")
        vid = row["id"]

    run_uuid = str(uuid.uuid4())
    cur = conn.execute(
        """INSERT INTO runs (run_uuid,variation_id,strategy_name,symbol,timeframe,
           higher_tfs,period_start,period_end,split,n_bars,data_hash,code_hash,
           core_hash,config_json,params_json,metrics_json,prop_json,checks_json,
           checks_passed,prop_passed,net_profit,total_return_pct,cagr_pct,sharpe,
           sortino,max_dd_pct,n_trades,win_rate_pct,profit_factor,expectancy_r,
           t_stat,trades_per_week,exposure_pct,first_breach_rule,notes,created_at)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (
            run_uuid, vid, meta.get("strategy", ""), meta.get("symbol", ""),
            meta.get("timeframe", ""), json.dumps(meta.get("higher_timeframes", [])),
            meta.get("start"), meta.get("end"), split, meta.get("bars"),
            meta.get("data_hash"), meta.get("code_hash"), meta.get("core_hash"),
            json.dumps(meta.get("config", {}), default=str),
            json.dumps(meta.get("params", {}), default=str),
            json.dumps(metrics, default=str), json.dumps(prop, default=str),
            json.dumps(checks, default=str),
            int(all(c.get("passed") for c in checks)) if checks else None,
            int(bool(prop.get("passed"))),
            metrics.get("net_profit"), metrics.get("total_return_pct"),
            metrics.get("cagr_pct"), metrics.get("sharpe"), metrics.get("sortino"),
            metrics.get("max_drawdown_pct"), metrics.get("n_trades"),
            metrics.get("win_rate_pct"), _finite(metrics.get("profit_factor")),
            metrics.get("expectancy_r"), metrics.get("t_stat"),
            metrics.get("trades_per_week"), metrics.get("exposure_pct"),
            prop.get("first_breach_rule"), notes, now(),
        ),
    )
    run_id = cur.lastrowid

    if store_trades and result.trades:
        conn.executemany(
            """INSERT INTO trades (run_id,seq,entry_time,exit_time,side,qty,entry_price,
               exit_price,gross_pnl,fees,funding,net_pnl,r_multiple,bars_held,
               exit_reason,tag,mae,mfe,equity_after)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            [
                (run_id, i, str(t.entry_time), str(t.exit_time),
                 "long" if t.direction == 1 else "short", t.qty, t.entry_price,
                 t.exit_price, t.gross_pnl, t.fees, t.funding, t.net_pnl,
                 None if pd.isna(t.r_multiple) else t.r_multiple, t.bars_held,
                 t.exit_reason, t.tag, t.mae, t.mfe, t.equity_after)
                for i, t in enumerate(result.trades)
            ],
        )

    if store_equity and len(result.equity):
        eq = result.equity
        lo = result.equity_low
        if store_equity == "daily":
            eq = eq.resample("1D").last().dropna()
            lo = lo.resample("1D").min().dropna() if len(lo) else eq
        conn.executemany(
            "INSERT OR REPLACE INTO equity_curve (run_id,ts,equity,equity_low) VALUES (?,?,?,?)",
            [(run_id, str(ts), float(v), float(lo.get(ts, v))) for ts, v in eq.items()],
        )

    _event(conn, "run", run_id, "insert",
           f"{meta.get('strategy')} {split} prop_passed={bool(prop.get('passed'))}")
    conn.commit()
    return run_uuid


# ------------------------------------------------------------------ queries
# Strategies whose name starts with "_" are infrastructure tests, not research
# trials. They must not inflate the multiple-testing denominator.
_REAL_RUNS = r"strategy_name NOT LIKE '\_%' ESCAPE '\'"


def _real_runs(alias: str = "") -> str:
    """The same predicate, table-qualified. `variations` also has a
    strategy_name column, so joins must say which one they mean."""
    prefix = f"{alias}." if alias else ""
    return _REAL_RUNS.replace("strategy_name", f"{prefix}strategy_name", 1)


def trial_count(conn, hypothesis_slug: str | None = None) -> dict:
    """How many genuine research tests have been run. Feeds the multiple-testing
    correction - a Sharpe of 1.5 means much less as the 40th try than the 1st."""
    q = f"SELECT COUNT(*) n, COUNT(DISTINCT variation_id) v FROM runs WHERE {_REAL_RUNS}"
    args: tuple = ()
    if hypothesis_slug:
        q += """ AND variation_id IN (SELECT v.id FROM variations v
                 JOIN hypotheses h ON h.id=v.hypothesis_id WHERE h.slug=?)"""
        args = (hypothesis_slug,)
    row = conn.execute(q, args).fetchone()
    total = conn.execute(f"SELECT COUNT(*) n FROM runs WHERE {_REAL_RUNS}").fetchone()["n"]
    infra = conn.execute(f"SELECT COUNT(*) n FROM runs WHERE NOT {_REAL_RUNS}").fetchone()["n"]
    return {"runs": row["n"], "variations": row["v"], "runs_all_hypotheses": total,
            "infra_runs_excluded": infra}


def overview(conn) -> pd.DataFrame:
    return pd.read_sql_query(
        """SELECT h.slug AS hypothesis, h.title, h.status AS hyp_status,
                  v.slug AS variation, v.title AS var_title, v.status AS var_status,
                  COUNT(r.id) AS runs,
                  MAX(r.created_at) AS last_run,
                  MAX(r.sharpe) AS best_sharpe,
                  SUM(r.prop_passed) AS prop_passes
           FROM hypotheses h
           LEFT JOIN variations v ON v.hypothesis_id = h.id
           LEFT JOIN runs r ON r.variation_id = v.id
           GROUP BY h.id, v.id ORDER BY h.created_at DESC, v.created_at DESC""",
        conn,
    )


def runs_table(conn, only_passed: bool = False) -> pd.DataFrame:
    q = """SELECT r.*, v.slug AS variation_slug, v.title AS variation_title,
                  h.slug AS hypothesis_slug
           FROM runs r LEFT JOIN variations v ON v.id = r.variation_id
           LEFT JOIN hypotheses h ON h.id = v.hypothesis_id"""
    if only_passed:
        q += " WHERE r.prop_passed = 1"
    q += " ORDER BY r.created_at DESC"
    return pd.read_sql_query(q, conn)


def failed_ideas(conn) -> pd.DataFrame:
    return pd.read_sql_query(
        """SELECT h.slug AS hypothesis, v.slug AS variation, v.title, v.details,
                  v.verdict_note, v.updated_at
           FROM variations v JOIN hypotheses h ON h.id = v.hypothesis_id
           WHERE v.status = 'rejected' ORDER BY v.updated_at DESC""",
        conn,
    )


def _event(conn, entity: str, entity_id: int, event: str, detail: str = "") -> None:
    conn.execute(
        "INSERT INTO events (entity,entity_id,event,detail,created_at) VALUES (?,?,?,?,?)",
        (entity, entity_id, event, detail, now()),
    )


def _validate_status(status: str) -> None:
    if status not in STATUSES:
        raise ValueError(f"Bad status {status!r}. One of: {STATUSES}")


def _finite(x):
    try:
        return None if x is None or not pd.notna(x) or x in (float("inf"), float("-inf")) else float(x)
    except (TypeError, ValueError):
        return None


# ------------------------------------------------- drill-down queries
def hypotheses_list(conn) -> pd.DataFrame:
    """One row per hypothesis, with aggregate results across all its variations.

    This is the top level of the dashboard: what have we ever tried, and did
    anything come of it. Counts everything, including infrastructure runs -
    display should be a complete record. Only `trial_count`, which feeds the
    multiple-testing correction, filters those out.
    """
    return pd.read_sql_query(
        """
        SELECT h.id, h.slug, h.title, h.status, h.description, h.mechanism,
               h.research, h.symbol, h.asset_class, h.created_at, h.updated_at,
               COUNT(DISTINCT v.id)                                   AS n_variations,
               COUNT(DISTINCT CASE WHEN v.status='rejected' THEN v.id END) AS n_rejected,
               COUNT(DISTINCT CASE WHEN v.status='passed'   THEN v.id END) AS n_passed,
               COUNT(r.id)                                            AS n_runs,
               COALESCE(SUM(r.prop_passed), 0)                        AS n_prop_passes,
               MAX(CASE WHEN r.split='oos' THEN r.sharpe END)         AS best_oos_sharpe,
               MAX(CASE WHEN r.split='oos' THEN r.total_return_pct END) AS best_oos_return,
               MAX(r.sharpe)                                          AS best_sharpe,
               MAX(r.created_at)                                      AS last_run
        FROM hypotheses h
        LEFT JOIN variations v ON v.hypothesis_id = h.id
        LEFT JOIN runs r ON r.variation_id = v.id
        GROUP BY h.id
        ORDER BY COALESCE(MAX(r.created_at), h.updated_at) DESC
        """,
        conn,
    )


def variations_for(conn, hypothesis_slug: str) -> pd.DataFrame:
    """Every strategy built under one hypothesis, with its headline stats.

    Stats are taken from the LATEST run of each split, so a variation shows
    its in-sample and out-of-sample numbers side by side. Variations that were
    never run still appear - "coded but never tested" is information too.
    """
    return pd.read_sql_query(
        """
        WITH ranked AS (
            SELECT r.*, ROW_NUMBER() OVER (
                       PARTITION BY r.variation_id, r.split
                       ORDER BY r.created_at DESC) AS rn
            FROM runs r
        )
        SELECT v.id, v.slug, v.title, v.status, v.rationale, v.details,
               v.verdict_note, v.params_json, v.code_path, v.strategy_name,
               v.updated_at,
               COUNT(k.id)                                            AS n_runs,
               MAX(CASE WHEN k.split='full' AND k.rn=1 THEN k.total_return_pct END) AS full_return,
               MAX(CASE WHEN k.split='full' AND k.rn=1 THEN k.sharpe END)           AS full_sharpe,
               MAX(CASE WHEN k.split='full' AND k.rn=1 THEN k.n_trades END)         AS full_trades,
               MAX(CASE WHEN k.split='is'  AND k.rn=1 THEN k.sharpe END)            AS is_sharpe,
               MAX(CASE WHEN k.split='is'  AND k.rn=1 THEN k.total_return_pct END)  AS is_return,
               MAX(CASE WHEN k.split='oos' AND k.rn=1 THEN k.sharpe END)            AS oos_sharpe,
               MAX(CASE WHEN k.split='oos' AND k.rn=1 THEN k.total_return_pct END)  AS oos_return,
               MAX(CASE WHEN k.split='oos' AND k.rn=1 THEN k.expectancy_r END)      AS oos_expectancy_r,
               MAX(CASE WHEN k.split='oos' AND k.rn=1 THEN k.n_trades END)          AS oos_trades,
               MAX(CASE WHEN k.split='oos' AND k.rn=1 THEN k.max_dd_pct END)        AS oos_max_dd,
               COALESCE(MAX(k.prop_passed), 0)                        AS any_prop_pass,
               MIN(COALESCE(k.checks_passed, 1))                      AS all_checks_passed,
               MAX(k.created_at)                                      AS last_run
        FROM variations v
        JOIN hypotheses h ON h.id = v.hypothesis_id
        LEFT JOIN ranked k ON k.variation_id = v.id
        WHERE h.slug = ?
        GROUP BY v.id
        ORDER BY v.created_at
        """,
        conn, params=(hypothesis_slug,),
    )


def runs_for_variation(conn, variation_slug: str) -> pd.DataFrame:
    return pd.read_sql_query(
        """SELECT r.* FROM runs r JOIN variations v ON v.id = r.variation_id
           WHERE v.slug = ? ORDER BY r.created_at DESC""",
        conn, params=(variation_slug,),
    )


def hypothesis_detail(conn, slug: str) -> dict | None:
    row = conn.execute("SELECT * FROM hypotheses WHERE slug=?", (slug,)).fetchone()
    return dict(row) if row else None
