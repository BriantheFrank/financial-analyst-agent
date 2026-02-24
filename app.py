from __future__ import annotations

import hashlib
import json
import os
import tempfile
from datetime import datetime
from pathlib import Path

import pandas as pd
import streamlit as st

from sec_financials import (
    SecClient,
    clear_company_cache,
    extract_company_financials,
    prune_cache,
    resolve_company,
)
from ui.components import card, metric_card, status_pill
from ui.snowflake import build_snowflake_figure, compute_snowflake_scores
from ui.theme import build_app_css
from viz.charts import build_all_figures, build_revenue_segment_sankey
from viz.export import export_report_pack
from viz.transform import filter_df_by_granularity, json_to_tidy_df

st.set_page_config(page_title="Financial Analyst Agent (Premium)", page_icon="📊", layout="wide")
st.markdown(build_app_css(), unsafe_allow_html=True)
st.title("Financial Analyst Agent")
st.caption("Simply Wall St–style premium view")


@st.cache_data(show_spinner=False)
def _cached_extract(company: str, years: int, user_agent: str, segments_mode: str, max_quarters: int, max_file_size_mb: float, max_total_download_mb: float) -> dict:
    return extract_company_financials(
        company=company,
        years=years,
        user_agent=user_agent,
        segments_mode=segments_mode,
        max_quarters=max_quarters,
        max_file_size_mb=max_file_size_mb,
        max_total_download_mb=max_total_download_mb,
    )


def _run_extract(company: str, years: int, user_agent: str, prefer_cache: bool, segments_mode: str, max_quarters: int, max_file_size_mb: float, max_total_download_mb: float) -> dict:
    if prefer_cache:
        return _cached_extract(company, years, user_agent, segments_mode, max_quarters, max_file_size_mb, max_total_download_mb)
    _cached_extract.clear()
    return extract_company_financials(company=company, years=years, user_agent=user_agent, segments_mode=segments_mode, max_quarters=max_quarters, max_file_size_mb=max_file_size_mb, max_total_download_mb=max_total_download_mb)


def _compute_run_id(company: str, years: int, payload: dict) -> str:
    payload_hash = hashlib.md5(json.dumps(payload, sort_keys=True, default=str).encode("utf-8")).hexdigest()[:10]
    return f"{company.lower()}_{years}y_{payload_hash}"


def render_plotly(fig, *, chart_id: str, section: str, run_id: str) -> None:
    st.plotly_chart(fig, key=f"{section}_{chart_id}_{run_id}", use_container_width=True)


def _fmt_currency(v: float | None) -> str:
    return "N/A" if v is None else f"${v:,.0f}"


def _latest_metric(df: pd.DataFrame, metric: str) -> float | None:
    subset = df[(df["metric"] == metric) & (df["segment"] == "Total")].sort_values("period_end")
    return None if subset.empty else float(subset.iloc[-1]["value"])


status = st.session_state.get("status", "Ready")
with card("Header / Controls"):
    c1, c2, c3, c4 = st.columns([2.2, 1, 1, 1])
    company = c1.text_input("Company (ticker or name)", value="AAPL")
    years = c2.slider("Years", min_value=1, max_value=10, value=5)
    granularity_label = c3.radio("View", options=["Annual", "Quarterly"], index=1, horizontal=True)
    granularity = "annual" if granularity_label == "Annual" else "quarterly"
    sec_ua = os.environ.get("SEC_USER_AGENT") or c4.text_input("SEC_USER_AGENT", value="", help="Required by SEC policy")

    d1, d2, d3, d4, d5 = st.columns(5)
    segments_mode = d1.selectbox("segments_mode", options=["none", "annual", "full"], index=1)
    max_quarters = d2.slider("max_quarters", min_value=1, max_value=20, value=8)
    max_file_size_mb = d3.number_input("Max file MB", min_value=1.0, max_value=200.0, value=25.0)
    max_total_download_mb = d4.number_input("Max total MB", min_value=10.0, max_value=2000.0, value=200.0, step=10.0)
    prefer_cache = d5.checkbox("Prefer cache", value=True)

    r1, r2, r3, r4 = st.columns([1, 1, 1, 2])
    run = r1.button("Run", type="primary")
    if r2.button("Clear company cache") and sec_ua and company.strip():
        try:
            cik = resolve_company(SecClient(user_agent=sec_ua), company)["cik"]
            clear_company_cache(cik)
            st.success(f"Cleared cache for {cik}")
        except Exception:
            st.warning("Could not clear cache for company")
    if r3.button("Prune cache"):
        prune_cache(max_age_days=30, max_total_gb=2.0)
        st.success("Pruned SEC cache")
    with r4:
        status_pill(status)

if run:
    if not sec_ua:
        st.session_state["status"] = "Error"
        st.error("SEC_USER_AGENT is required.")
        st.stop()
    st.session_state["status"] = "Fetching"
    payload = _run_extract(company, years, sec_ua, prefer_cache, segments_mode, max_quarters, max_file_size_mb, max_total_download_mb)
    st.session_state["payload"] = payload
    st.session_state["run_id"] = _compute_run_id(company, years, payload)
    st.session_state["status"] = "Complete"

if "payload" in st.session_state:
    payload = st.session_state["payload"]
    run_id = st.session_state.get("run_id") or _compute_run_id(company, years, payload)
    df, meta = json_to_tidy_df(payload)
    meta["period_payloads"] = payload.get("periods", [])

    dfg = filter_df_by_granularity(df, granularity)
    period_options = []
    if not dfg.empty:
        periods = dfg[["period_end", "period_label"]].drop_duplicates().sort_values("period_end")
        period_options = [(r.period_label, r.period_end) for r in periods.itertuples(index=False)]

    selected_period_end = period_options[-1][1] if period_options else None
    with card("KPI Overview"):
        if period_options:
            selected_label = st.selectbox("Period", [x[0] for x in period_options], index=len(period_options) - 1)
            selected_period_end = next(v for l, v in period_options if l == selected_label)

        rev = _latest_metric(dfg, "revenue")
        ni = _latest_metric(dfg, "profit_net_income")
        cap = _latest_metric(dfg, "capex")
        rev_df = dfg[(dfg["metric"] == "revenue") & (dfg["segment"] == "Total")].sort_values("period_end")
        yoy = None
        if len(rev_df) > 1:
            yoy = (float(rev_df.iloc[-1]["value"]) / float(rev_df.iloc[-2]["value"]) - 1) * 100
        margin = None
        if rev is not None and ni is not None and rev != 0:
            margin = ni / rev * 100
        cap_intensity = None
        if cap is not None and rev is not None and rev != 0:
            cap_intensity = cap / rev * 100

        cols = st.columns(6)
        with cols[0]:
            metric_card("Revenue", _fmt_currency(rev), delta=f"{yoy:.1f}%" if yoy is not None else None, delta_color="normal", icon="📈")
        with cols[1]:
            metric_card("YoY Revenue Growth", f"{yoy:.1f}%" if yoy is not None else "N/A", delta_color="normal")
        with cols[2]:
            metric_card("Net Income", _fmt_currency(ni), icon="💰")
        with cols[3]:
            metric_card("Net Margin", f"{margin:.1f}%" if margin is not None else "N/A")
        with cols[4]:
            metric_card("CAPEX", _fmt_currency(cap), icon="🏗️")
        with cols[5]:
            metric_card("CAPEX Intensity", f"{cap_intensity:.1f}%" if cap_intensity is not None else "N/A")

    figures = build_all_figures(df, meta, granularity=granularity, selected_period_end=selected_period_end)

    c_left, c_right = st.columns(2)
    with c_left:
        with card("Snowflake"):
            scores = compute_snowflake_scores(df, meta, granularity)
            if all(v is None for v in scores.values()):
                st.caption("Insufficient data")
            render_plotly(build_snowflake_figure(scores), chart_id="snowflake", section="overview", run_id=run_id)
            st.caption("Valuation and Dividend are N/A from filing-only extraction.")
    with c_right:
        with card("Revenue by Segment Sankey"):
            sankey = build_revenue_segment_sankey(dfg, meta, selected_period_end=selected_period_end)
            if sankey is None:
                st.caption("Insufficient data")
            else:
                render_plotly(sankey, chart_id="07_revenue_segment_sankey", section="overview", run_id=run_id)

    trend_tab, seg_tab, capex_tab, export_tab = st.tabs(["📈 Trends", "🧩 Segments", "🏗️ CAPEX", "🧾 Export"])
    lookup = {stem: (fig, m) for stem, fig, m in figures}

    with trend_tab:
        for stem in ["02_revenue_trend", "03_profit_and_margin"]:
            if stem in lookup:
                with card(lookup[stem][1]["title"]):
                    render_plotly(lookup[stem][0], chart_id=stem, section="trends", run_id=run_id)

    with seg_tab:
        for stem in ["06_snapshot_revenue_mix", "07_revenue_segment_sankey", "08_waterfall_revenue_yoy_change"]:
            if stem in lookup:
                with card(lookup[stem][1]["title"]):
                    render_plotly(lookup[stem][0], chart_id=stem, section="segments", run_id=run_id)

    with capex_tab:
        for stem in ["04_capex_trend", "05_capex_intensity", "09_forecast_capex"]:
            if stem in lookup:
                with card(lookup[stem][1]["title"]):
                    render_plotly(lookup[stem][0], chart_id=stem, section="capex", run_id=run_id)

    with export_tab:
        with card("Export"):
            json_bytes = json.dumps(payload, indent=2, sort_keys=True).encode("utf-8")
            st.download_button("Download JSON", data=json_bytes, file_name="extracted_financials.json", mime="application/json")
            with tempfile.TemporaryDirectory() as td:
                zip_path = export_report_pack(Path(td), payload, figures, meta)
                zip_bytes = Path(zip_path).read_bytes()
                st.download_button("Download Report Pack", data=zip_bytes, file_name="report_pack.zip", mime="application/zip")
                st.caption(f"Size: {len(zip_bytes)/1024:.1f} KB • Generated: {datetime.utcnow().isoformat(timespec='seconds')}Z")
