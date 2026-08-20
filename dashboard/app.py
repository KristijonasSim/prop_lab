"""Streamlit dashboard: the research record.

Three levels of drill-down:
    Hypotheses  ->  one hypothesis  ->  one variation's runs

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

from proplab.db import store                      # noqa: E402
from proplab.research import multiple_testing     # noqa: E402

st.set_page_config(page_title="prop_lab", layout="wide")

STATUS_ICON = {
    "queued": "⚪", "researching": "🔵", "ready_to_code": "🟣", "coding": "🟠",
    "testing": "🟡", "tested": "🟤", "rejected": "🔴", "passed": "🟢",
}


@st.cache_resource
def conn():
    return store.connect()


def refresh():
    st.cache_data.clear()


@st.cache_data(ttl=5)
def hypotheses():
    return store.hypotheses_list(conn())


@st.cache_data(ttl=5)
def variations(slug: str):
    return store.variations_for(conn(), slug)


@st.cache_data(ttl=5)
def runs_of(slug: str):
    return store.runs_for_variation(conn(), slug)


@st.cache_data(ttl=5)
def all_runs():
    return store.runs_table(conn())


@st.cache_data(ttl=5)
def failed():
    return store.failed_ideas(conn())


# ---------------------------------------------------------------- navigation
def go_to(page: str, hyp: str | None = None, var: str | None = None):
    st.session_state["page"] = page
    if hyp is not None:
        st.session_state["hyp"] = hyp
    if var is not None:
        st.session_state["var"] = var


st.session_state.setdefault("page", "Hypotheses")
st.session_state.setdefault("hyp", None)
st.session_state.setdefault("var", None)

# ?hyp=<slug> still opens a hypothesis directly, so a link to one can be
# shared or bookmarked. Honoured once per distinct slug: re-applying it on
# every rerun would pin the user to the detail page and make the sidebar
# unusable.
_qp_hyp = st.query_params.get("hyp")
if _qp_hyp and st.session_state.get("_seen_qp_hyp") != _qp_hyp:
    st.session_state["_seen_qp_hyp"] = _qp_hyp
    go_to("hypothesis_detail", _qp_hyp)

NAV = ["Hypotheses", "Overview", "All runs", "Failed ideas"]
NAV_STATUSES = list(STATUS_ICON)
DETAIL_PAGES = {"hypothesis_detail": "Hypotheses", "variation_detail": "Hypotheses"}

st.sidebar.title("prop_lab")

# Buttons, not a radio. A radio only fires when its value CHANGES, so from a
# drill-down (reached from Hypotheses, with the radio still reading
# "Hypotheses") clicking Hypotheses did nothing at all and the sidebar became
# a dead end. A button fires on every click.
_section = DETAIL_PAGES.get(st.session_state["page"], st.session_state["page"])
for _label in NAV:
    st.sidebar.button(
        _label, key=f"nav_{_label}", width="stretch",
        type="primary" if _label == _section else "tertiary",
        on_click=go_to, args=(_label,))

st.sidebar.divider()
st.sidebar.button("Refresh", on_click=refresh, width="stretch")

page = st.session_state["page"]
hyps = hypotheses()
st.sidebar.caption(f"{len(hyps)} hypotheses · {len(all_runs())} runs logged")


def fmt(v, suffix="", dash="—"):
    return dash if v is None or (isinstance(v, float) and pd.isna(v)) else f"{v}{suffix}"


def txt(v) -> str:
    """Empty string for None/NaN.

    Necessary because pandas turns a missing text column into float NaN, and
    `if nan:` is TRUE in Python - so a bare truthiness check happily falls
    through and then crashes on string operations.
    """
    return "" if v is None or (isinstance(v, float) and pd.isna(v)) else str(v)


# ============================================================ HYPOTHESIS LIST
if page == "Hypotheses":
    st.header("Hypothesis library")
    st.caption("Everything we have ever tried. Select a row to open it and see "
               "the strategies built under it.")

    if hyps.empty:
        st.info("No hypotheses yet. Create one:\n\n"
                "`python -m proplab.cli hypothesis --slug orb "
                "--title \"Opening range breakout\" --status researching`")
    else:
        f1, f2, f3 = st.columns([2, 2, 1])
        query = f1.text_input("Search", placeholder="title, slug or idea…",
                              label_visibility="collapsed")
        statuses = f2.multiselect("Status", NAV_STATUSES, default=[],
                                  placeholder="any status",
                                  label_visibility="collapsed")
        sort_by = f3.selectbox("Sort", ["Recent", "Best OOS Sharpe", "Most runs", "Name"],
                               label_visibility="collapsed")

        view = hyps
        if query:
            q = query.lower()
            view = view[view.apply(
                lambda r: q in f"{txt(r['title'])} {txt(r['slug'])} "
                             f"{txt(r['description'])}".lower(), axis=1)]
        if statuses:
            view = view[view["status"].isin(statuses)]
        view = {
            "Recent": view.sort_values("last_run", ascending=False, na_position="last"),
            "Best OOS Sharpe": view.sort_values("best_oos_sharpe", ascending=False,
                                                na_position="last"),
            "Most runs": view.sort_values("n_runs", ascending=False),
            "Name": view.sort_values("title"),
        }[sort_by]

        if view.empty:
            st.info("Nothing matches that filter.")
        else:
            # Laid out as columns with a borderless button in the name cell,
            # rather than st.dataframe. Row selection there forces a checkbox
            # gutter that cannot be disabled, and a LinkColumn always opens in
            # a new tab. A button is a callback, so it navigates in place.
            widths = [0.3, 3.2, 1.1, 1.0, 0.9, 0.8, 0.9, 1.1, 1.0, 0.9, 1.1]
            head = st.columns(widths, vertical_alignment="bottom")
            for col, label in zip(head, [
                    "", "Hypothesis", "Status", "Symbol", "Strats", "Runs",
                    "Rejected", "OOS Sharpe", "OOS ret %", "OOS pass", "Last run"]):
                col.markdown(
                    f"<div style='font-size:0.72rem;opacity:0.6;"
                    f"text-transform:uppercase;letter-spacing:0.03em'>{label}</div>",
                    unsafe_allow_html=True)
            st.markdown("<hr style='margin:0.1rem 0 0 0;opacity:0.25'>",
                        unsafe_allow_html=True)

            def cell(col, value, dim=False):
                col.markdown(
                    f"<div style='font-size:0.85rem;padding-top:0.45rem;"
                    f"{'opacity:0.65;' if dim else ''}'>{value}</div>",
                    unsafe_allow_html=True)

            for h in view.to_dict("records"):
                c = st.columns(widths, vertical_alignment="center")
                cell(c[0], STATUS_ICON.get(h["status"], ""))
                c[1].button(txt(h["title"]), key=f"open_{h['slug']}",
                            type="tertiary", width="stretch",
                            help=txt(h["description"])[:300] or None,
                            on_click=go_to, args=("hypothesis_detail", h["slug"]))
                cell(c[2], h["status"], dim=True)
                cell(c[3], txt(h["symbol"]) or "—", dim=True)
                cell(c[4], int(h["n_variations"]))
                cell(c[5], int(h["n_runs"]))
                cell(c[6], int(h["n_rejected"]))
                cell(c[7], fmt(round(h["best_oos_sharpe"], 2)
                               if pd.notna(h["best_oos_sharpe"]) else None))
                cell(c[8], fmt(round(h["best_oos_return"], 1)
                               if pd.notna(h["best_oos_return"]) else None))
                cell(c[9], int(h["n_prop_passes"]))
                cell(c[10], txt(h["last_run"])[:10] or "never", dim=True)
                st.markdown("<hr style='margin:0;opacity:0.15'>",
                            unsafe_allow_html=True)

            st.caption(f"{len(view)} of {len(hyps)} hypotheses · click a "
                       "hypothesis name to open it")

# ========================================================== HYPOTHESIS DETAIL
elif page == "hypothesis_detail":
    slug = st.session_state["hyp"]
    detail = store.hypothesis_detail(conn(), slug) if slug else None
    if not detail:
        st.warning("Hypothesis not found.")
        st.button("← Back", on_click=go_to, args=("Hypotheses",))
    else:
        st.button("← All hypotheses", on_click=go_to, args=("Hypotheses",))
        st.header(f"{STATUS_ICON.get(detail['status'], '')} {detail['title']}")
        st.caption(f"`{slug}` · status **{detail['status']}** · "
                   f"{detail['symbol'] or detail['asset_class'] or '—'}")

        st.subheader("The idea")
        st.write(txt(detail["description"]) or "—")
        st.subheader("Mechanism — why this should work")
        st.write(txt(detail["mechanism"]) or "—")
        if txt(detail["research"]):
            with st.expander("Research notes: how this is normally traded"):
                st.markdown(txt(detail["research"]))

        st.divider()
        vs = variations(slug)
        st.subheader(f"Strategies built from this hypothesis ({len(vs)})")
        if vs.empty:
            st.info("No variations coded yet.")
        else:
            # Only render columns the query actually returned. A dashboard
            # process holds imported modules from when it started, so after
            # proplab changes it can be running an older store.py than the
            # database - and a hard column lookup turns that into a crash
            # instead of a slightly thinner table.
            COLUMNS = [
                ("slug", "variation", None),
                ("status", "status", None),
                ("n_runs", "runs", None),
                ("is_sharpe", "IS Sharpe", "%.2f"),
                ("oos_sharpe", "OOS Sharpe", "%.2f"),
                ("oos_return", "OOS ret %", "%.2f"),
                ("oos_profit_factor", "PF", "%.2f"),
                ("oos_win_rate", "Win %", "%.1f"),
                ("oos_expectancy_r", "Avg R", "%.3f"),
                ("oos_trades", "Trades", None),
                ("oos_trades_per_day", "Trades/day", "%.2f"),
                ("oos_trades_per_week", "Trades/wk", "%.2f"),
                ("oos_hold_hours", "Hold (h)", "%.1f"),
                ("oos_max_dd", "Max DD %", "%.2f"),
                ("oos_days_to_resolve", "Days to resolve", "%.0f"),
                ("oos_p_target_first", "P(target first)", "%.2f"),
                ("any_prop_pass", "prop pass", None),
            ]
            present = [(c, label, f) for c, label, f in COLUMNS if c in vs.columns]
            missing = [label for c, label, _ in COLUMNS if c not in vs.columns]

            table = vs[[c for c, _, _ in present]].copy()
            table.columns = [label for _, label, _ in present]
            st.dataframe(
                table, width="stretch", hide_index=True,
                column_config={label: st.column_config.NumberColumn(format=f)
                               for _, label, f in present if f})
            if missing:
                st.warning(
                    "Not showing " + ", ".join(missing) + ". The dashboard "
                    "process is running older code than the database — restart "
                    "it with `./runs/stop_dashboard.sh && ./runs/start_dashboard.sh`.")
            st.caption(
                "Stats are the most recent run of each split; out-of-sample is the "
                "only column that counts as evidence. **Days to resolve** estimates "
                "the trading days until the account hits the profit target or "
                "breaches the drawdown limit, from that run's daily P&L — the "
                "figure that decides whether a strategy can clear an evaluation "
                "in a reasonable time.")

            for _, v in vs.iterrows():
                icon = STATUS_ICON.get(v["status"], "")
                with st.expander(f"{icon} {v['title']}  ·  `{v['slug']}`  ·  "
                                 f"{v['status']}"):
                    if txt(v["rationale"]):
                        st.write(f"**Why test this variation:** {txt(v['rationale'])}")
                    if txt(v["details"]):
                        st.write(f"**Rules:** {txt(v['details'])}")
                    if txt(v["verdict_note"]):
                        st.info(f"**Verdict:** {txt(v['verdict_note'])}")

                    c = st.columns(6)
                    c[0].metric("Runs", int(v["n_runs"]))
                    c[1].metric("IS Sharpe", fmt(v["is_sharpe"]))
                    c[2].metric("OOS Sharpe", fmt(v["oos_sharpe"]))
                    c[3].metric("OOS return", fmt(v["oos_return"], "%"))
                    c[4].metric("OOS trades", fmt(v["oos_trades"]))
                    c[5].metric("Prop", "PASS" if v["any_prop_pass"] else "FAIL")

                    if pd.notna(v["is_sharpe"]) and pd.notna(v["oos_sharpe"]):
                        if v["is_sharpe"] > 0:
                            decay = 1 - (v["oos_sharpe"] / v["is_sharpe"])
                            st.caption(f"Sharpe decay IS→OOS: {decay:.0%}"
                                       + ("  ⚠️ likely overfit" if decay > 0.5 else ""))
                        else:
                            st.caption("Sharpe decay: n/a — in-sample Sharpe was "
                                       "not positive")

                    if txt(v["params_json"]):
                        st.write("**Params**")
                        st.json(json.loads(txt(v["params_json"])), expanded=False)

                    if int(v["n_runs"] or 0):
                        st.button("See all runs →", key=f"runs_{v['slug']}",
                                  on_click=go_to,
                                  args=("variation_detail", slug, v["slug"]))
                    else:
                        st.caption("Coded but never run.")

                    code_path = txt(v["code_path"])
                    if code_path and Path(code_path).exists():
                        with st.expander("Strategy code"):
                            st.code(Path(code_path).read_text(), language="python")

# =========================================================== VARIATION DETAIL
elif page == "variation_detail":
    vslug = st.session_state["var"]
    hslug = st.session_state["hyp"]
    st.button("← Back to hypothesis", on_click=go_to,
              args=("hypothesis_detail", hslug))
    rows = runs_of(vslug) if vslug else pd.DataFrame()
    st.header(f"Runs · `{vslug}`")

    if rows.empty:
        st.info("No runs for this variation.")
    else:
        summary = rows[["created_at", "split", "symbol", "timeframe", "period_start",
                        "period_end", "n_trades", "total_return_pct", "sharpe",
                        "max_dd_pct", "profit_factor", "expectancy_r",
                        "prop_passed", "first_breach_rule"]]
        st.dataframe(summary, width="stretch", hide_index=True)

        pick = st.selectbox(
            "Inspect run", options=list(rows["run_uuid"]),
            format_func=lambda u: (
                f"{rows.loc[rows['run_uuid'] == u, 'created_at'].iloc[0][:16]} · "
                f"{rows.loc[rows['run_uuid'] == u, 'split'].iloc[0]} · "
                f"{rows.loc[rows['run_uuid'] == u, 'timeframe'].iloc[0]} · "
                f"ret {rows.loc[rows['run_uuid'] == u, 'total_return_pct'].iloc[0]}%"))
        r = rows[rows["run_uuid"] == pick].iloc[0]

        c = st.columns(6)
        c[0].metric("Return", fmt(r["total_return_pct"], "%"))
        c[1].metric("Sharpe", fmt(r["sharpe"]))
        c[2].metric("Max DD", fmt(r["max_dd_pct"], "%"))
        c[3].metric("Trades", fmt(r["n_trades"]))
        c[4].metric("Expectancy", fmt(r["expectancy_r"], " R"))
        c[5].metric("Prop firm", "PASS" if r["prop_passed"] else "FAIL")

        eq = pd.read_sql_query(
            "SELECT ts, equity, equity_low FROM equity_curve WHERE run_id=? ORDER BY ts",
            conn(), params=(int(r["id"]),))
        prop = json.loads(r["prop_json"] or "{}")
        if len(eq):
            eq["ts"] = pd.to_datetime(eq["ts"])
            start = json.loads(r["config_json"] or "{}").get("rules", {}).get(
                "starting_balance", eq["equity"].iloc[0])
            fig = go.Figure()
            fig.add_trace(go.Scatter(x=eq["ts"], y=eq["equity"], name="equity"))
            fig.add_trace(go.Scatter(x=eq["ts"], y=eq["equity_low"],
                                     name="intraday low", line=dict(dash="dot")))
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

        t1, t2, t3, t4 = st.tabs(["Prop rules", "Checks", "Metrics", "Trades"])
        with t1:
            for name, ch in prop.get("checks", {}).items():
                st.write(f"{'✅' if ch['passed'] else '❌'} **{name}** "
                         f"({'HARD' if ch['hard'] else 'qualification'})")
                if not ch["passed"] and ch.get("note"):
                    st.caption(ch["note"])
                st.json(ch, expanded=False)
            if prop.get("first_breach_rule"):
                st.error(f"Account would have been closed at "
                         f"{prop['first_breach_time']} "
                         f"({prop['first_breach_rule']}). Everything after that "
                         f"point is fiction.")
        with t2:
            for ch in json.loads(r["checks_json"] or "[]"):
                st.write(f"{'✅' if ch['passed'] else '❌'} **{ch['name']}** — "
                         f"{ch['detail']}")
                if ch.get("findings"):
                    st.json(ch["findings"], expanded=False)
        with t3:
            st.json(json.loads(r["metrics_json"] or "{}"))
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

# ==================================================================== OVERVIEW
elif page == "Overview":
    st.header("Pipeline overview")
    runs = all_runs()
    if runs.empty:
        st.info("No runs logged yet. "
                "Run: `python -m proplab.cli run --strategy … --log`")
    else:
        real = runs[~runs["strategy_name"].str.startswith("_")]
        best = real["sharpe"].max() if len(real) else float("nan")
        c = st.columns(5)
        c[0].metric("Hypotheses", len(hyps))
        c[1].metric("Runs logged", len(runs))
        c[2].metric("Research trials", len(real))
        c[3].metric("Prop-firm passes", int(runs["prop_passed"].fillna(0).sum()))
        c[4].metric("Best Sharpe", f"{best:.2f}" if pd.notna(best) else "—")

        st.subheader("Multiple-testing reality check")
        n_trials = max(len(real), 1)
        years = st.slider("Typical test length (years)", 0.5, 8.0, 3.0, 0.5)
        bar = multiple_testing.expected_max_sharpe(n_trials, years)
        if len(real) < len(runs):
            st.caption(f"{len(runs) - len(real)} infrastructure run(s) excluded "
                       "from the trial count.")
        st.write(f"With **{n_trials}** logged research trials over ~{years} years, "
                 f"pure noise is expected to produce a best Sharpe of about "
                 f"**{bar:.2f}**. A result below that line is not evidence.")
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
        st.dataframe(store.overview(conn()), width="stretch", hide_index=True)

# ==================================================================== ALL RUNS
elif page == "All runs":
    st.header("All runs")
    runs = all_runs()
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

        cols = ["created_at", "hypothesis_slug", "variation_slug", "strategy_name",
                "symbol", "timeframe", "split", "n_trades", "total_return_pct",
                "sharpe", "max_dd_pct", "profit_factor", "expectancy_r",
                "prop_passed", "first_breach_rule", "run_uuid"]
        st.dataframe(f[cols].sort_values("created_at", ascending=False),
                     width="stretch", hide_index=True)
        st.caption("`prop_passed=0` with a good return means profitable but not "
                   "tradeable on an evaluation account.")

# ================================================================ FAILED IDEAS
elif page == "Failed ideas":
    st.header("Rejected — do not re-test these")
    f = failed()
    if f.empty:
        st.info("Nothing rejected yet.")
    else:
        st.dataframe(f, width="stretch", hide_index=True)
        st.caption("Every row here is part of the multiple-testing denominator.")
