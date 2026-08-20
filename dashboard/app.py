"""Streamlit dashboard: what has been tested, what survived, what failed.

    python -m proplab.cli dashboard      (or: streamlit run dashboard/app.py)
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from proplab.db import store            # noqa: E402
from proplab.research import multiple_testing  # noqa: E402

st.set_page_config(page_title="prop_lab", layout="wide")

STATUS_COLOR = {
    "queued": "⚪", "researching": "🔵", "ready_to_code": "🟣", "coding": "🟠",
    "testing": "🟡", "tested": "🟤", "rejected": "🔴", "passed": "🟢",
}


@st.cache_resource
def conn():
    return store.connect()


def refresh():
    st.cache_data.clear()


@st.cache_data(ttl=5)
def load_runs(only_passed: bool = False) -> pd.DataFrame:
    return store.runs_table(conn(), only_passed=only_passed)


@st.cache_data(ttl=5)
def load_overview() -> pd.DataFrame:
    return store.overview(conn())


@st.cache_data(ttl=5)
def load_failed() -> pd.DataFrame:
    return store.failed_ideas(conn())


runs = load_runs()
overview = load_overview()

st.sidebar.title("prop_lab")
page = st.sidebar.radio("View", ["Overview", "Hypotheses", "Runs", "Run detail",
                                 "Failed ideas"])
st.sidebar.button("Refresh", on_click=refresh)
st.sidebar.caption(f"{len(runs)} runs logged")

# --------------------------------------------------------------- Overview
if page == "Overview":
    st.header("Research pipeline")
    if runs.empty:
        st.info("No runs logged yet. Run:  python -m proplab.cli run --strategy … --log")
    else:
        c = st.columns(5)
        c[0].metric("Runs logged", len(runs))
        c[1].metric("Variations", int(runs["variation_id"].nunique()))
        c[2].metric("Prop-firm passes", int(runs["prop_passed"].fillna(0).sum()))
        c[3].metric("Check failures", int((runs["checks_passed"] == 0).sum()))
        best = runs[~runs["strategy_name"].str.startswith("_")]["sharpe"].max()
        c[4].metric("Best Sharpe", f"{best:.2f}" if pd.notna(best) else "-")

        st.subheader("Multiple-testing reality check")
        real = runs[~runs["strategy_name"].str.startswith("_")]
        n_trials = max(len(real), 1)
        years = st.slider("Typical test length (years)", 0.5, 8.0, 3.0, 0.5)
        bar = multiple_testing.expected_max_sharpe(n_trials, years)
        if len(real) < len(runs):
            st.caption(f"{len(runs) - len(real)} infrastructure run(s) excluded from "
                       "the trial count.")
        st.write(
            f"With **{n_trials}** logged research trials over ~{years} years, pure noise is "
            f"expected to produce a best Sharpe of about **{bar:.2f}**. "
            "A result below that line is not evidence of anything."
        )
        if pd.notna(best):
            if best > 0:
                st.progress(max(0.0, min(float(best) / max(bar * 2, 0.01), 1.0)))
                st.caption(f"best observed {best:.2f} vs noise benchmark {bar:.2f}"
                           + ("  — clears the noise bar" if best > bar
                              else "  — below the noise bar, not evidence"))
            else:
                st.caption(f"best observed Sharpe is {best:.2f} — nothing positive "
                           f"to compare against the noise benchmark of {bar:.2f}")

        st.subheader("Status board")
        st.dataframe(overview, width="stretch")

# ------------------------------------------------------------- Hypotheses
elif page == "Hypotheses":
    st.header("Hypotheses and variations")
    if overview.empty:
        st.info("Nothing recorded yet.")
    else:
        for hyp, grp in overview.groupby("hypothesis", dropna=False):
            row = grp.iloc[0]
            st.markdown(f"### {STATUS_COLOR.get(row['hyp_status'], '')} {row['title']}  "
                        f"`{hyp}`")
            det = pd.read_sql_query(
                "SELECT description, mechanism, research, symbol, asset_class "
                "FROM hypotheses WHERE slug=?", conn(), params=(hyp,))
            if len(det):
                d = det.iloc[0]
                st.write(f"**Idea:** {d['description'] or '-'}")
                st.write(f"**Mechanism:** {d['mechanism'] or '-'}")
                with st.expander("Research notes"):
                    st.write(d["research"] or "-")
            show = grp[["variation", "var_title", "var_status", "runs",
                        "best_sharpe", "prop_passes", "last_run"]]
            st.dataframe(show, width="stretch", hide_index=True)

# ------------------------------------------------------------------- Runs
elif page == "Runs":
    st.header("All runs")
    if runs.empty:
        st.info("Nothing logged yet.")
    else:
        c = st.columns(4)
        only_pass = c[0].checkbox("Prop-firm passes only")
        only_clean = c[1].checkbox("Passed automated checks only", value=True)
        split = c[2].selectbox("Split", ["all", "full", "is", "oos"])
        min_trades = c[3].number_input("Min trades", 0, 10_000, 30)

        f = runs.copy()
        if only_pass:
            f = f[f["prop_passed"] == 1]
        if only_clean:
            f = f[f["checks_passed"] != 0]
        if split != "all":
            f = f[f["split"] == split]
        f = f[f["n_trades"].fillna(0) >= min_trades]

        cols = ["created_at", "strategy_name", "variation_slug", "symbol", "timeframe",
                "split", "n_trades", "total_return_pct", "sharpe", "max_dd_pct",
                "profit_factor", "expectancy_r", "t_stat", "prop_passed",
                "first_breach_rule", "run_uuid"]
        st.dataframe(f[cols].sort_values("created_at", ascending=False),
                     width="stretch", hide_index=True)
        st.caption("Sort by any column. `prop_passed=0` with a good return means "
                   "profitable but not tradeable on an evaluation account.")

# ------------------------------------------------------------- Run detail
elif page == "Run detail":
    st.header("Run detail")
    if runs.empty:
        st.info("Nothing logged yet.")
    else:
        label = runs.apply(
            lambda r: f"{r['created_at'][:16]} · {r['strategy_name']} · {r['split']} "
                      f"· ret {r['total_return_pct']}% · {r['run_uuid'][:8]}", axis=1)
        pick = st.selectbox("Run", options=list(runs["run_uuid"]),
                            format_func=lambda u: label[runs["run_uuid"] == u].iloc[0])
        r = runs[runs["run_uuid"] == pick].iloc[0]

        c = st.columns(6)
        c[0].metric("Return", f"{r['total_return_pct']}%")
        c[1].metric("Sharpe", r["sharpe"])
        c[2].metric("Max DD", f"{r['max_dd_pct']}%")
        c[3].metric("Trades", r["n_trades"])
        c[4].metric("Expectancy", f"{r['expectancy_r']} R" if pd.notna(r["expectancy_r"]) else "-")
        c[5].metric("Prop firm", "PASS" if r["prop_passed"] else "FAIL")

        eq = pd.read_sql_query(
            "SELECT ts, equity, equity_low FROM equity_curve WHERE run_id=? ORDER BY ts",
            conn(), params=(int(r["id"]),))
        if len(eq):
            eq["ts"] = pd.to_datetime(eq["ts"])
            prop = json.loads(r["prop_json"] or "{}")
            start = json.loads(r["config_json"] or "{}").get("rules", {}).get(
                "starting_balance", eq["equity"].iloc[0])
            fig = go.Figure()
            fig.add_trace(go.Scatter(x=eq["ts"], y=eq["equity"], name="equity"))
            fig.add_trace(go.Scatter(x=eq["ts"], y=eq["equity_low"], name="intraday low",
                                     line=dict(dash="dot")))
            checks = prop.get("checks", {})
            if "max_drawdown_static" in checks:
                fig.add_hline(y=checks["max_drawdown_static"]["floor"],
                              line_dash="dash", annotation_text="max DD floor")
            fig.add_hline(y=start, line_dash="dot", annotation_text="start")
            if prop.get("first_breach_time"):
                fig.add_vline(x=pd.Timestamp(prop["first_breach_time"]),
                              line_color="red",
                              annotation_text=f"breach: {prop['first_breach_rule']}")
            fig.update_layout(height=380, margin=dict(t=20, b=20))
            st.plotly_chart(fig, width="stretch")

        t1, t2, t3, t4, t5 = st.tabs(["Prop rules", "Checks", "Metrics", "Trades", "Code"])
        with t1:
            prop = json.loads(r["prop_json"] or "{}")
            for name, ch in prop.get("checks", {}).items():
                icon = "✅" if ch["passed"] else "❌"
                kind = "HARD" if ch["hard"] else "qualification"
                st.write(f"{icon} **{name}** ({kind})")
                st.json(ch, expanded=False)
            if prop.get("first_breach_rule"):
                st.error(f"Account would have been closed at {prop['first_breach_time']} "
                         f"({prop['first_breach_rule']}). Everything after that is fiction.")
        with t2:
            for ch in json.loads(r["checks_json"] or "[]"):
                st.write(f"{'✅' if ch['passed'] else '❌'} **{ch['name']}** — {ch['detail']}")
                if ch.get("findings"):
                    st.json(ch["findings"], expanded=False)
        with t3:
            st.json(json.loads(r["metrics_json"] or "{}"))
            st.write("**Params**")
            st.json(json.loads(r["params_json"] or "{}"))
        with t4:
            tr = pd.read_sql_query(
                "SELECT * FROM trades WHERE run_id=? ORDER BY seq", conn(),
                params=(int(r["id"]),))
            if len(tr):
                st.dataframe(tr.drop(columns=["id", "run_id"]), width="stretch",
                             hide_index=True)
                st.bar_chart(tr["r_multiple"].dropna())
            else:
                st.write("no trades")
        with t5:
            var = pd.read_sql_query(
                "SELECT code_path, details, rationale FROM variations WHERE id=?",
                conn(), params=(int(r["variation_id"]),)) if pd.notna(r["variation_id"]) \
                else pd.DataFrame()
            if len(var):
                st.write(f"**Rationale:** {var.iloc[0]['rationale']}")
                st.write(f"**Rules:** {var.iloc[0]['details']}")
                p = Path(var.iloc[0]["code_path"] or "")
                if p.exists():
                    st.code(p.read_text(), language="python")
            else:
                st.info("Run was not logged against a variation.")

# ------------------------------------------------------------ Failed ideas
elif page == "Failed ideas":
    st.header("Rejected — do not re-test these")
    failed = load_failed()
    if failed.empty:
        st.info("Nothing rejected yet.")
    else:
        st.dataframe(failed, width="stretch", hide_index=True)
        st.caption("Every row here is part of the multiple-testing denominator.")
