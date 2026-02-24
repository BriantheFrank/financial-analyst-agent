from __future__ import annotations

import hashlib
import json
import os
import tempfile
from pathlib import Path

import streamlit as st

from sec_financials import (
    SecClient,
    clear_company_cache,
    company_cache_size_bytes,
    extract_company_financials,
    prune_cache,
    resolve_company,
)
from viz.charts import CHART_ORDER, build_all_figures, build_kpi_dashboard_figures
from viz.export import export_report_pack
from viz.transform import filter_df_by_granularity, json_to_tidy_df

st.set_page_config(page_title="Financial Analyst Agent (Local)", layout="wide")
st.title("Financial Analyst Agent (Local)")


@st.cache_data(show_spinner=False)
def _cached_extract(
    company: str,
    years: int,
    user_agent: str,
    segments_mode: str,
    max_quarters: int,
    max_file_size_mb: float,
    max_total_download_mb: float,
) -> dict:
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
    return extract_company_financials(
        company=company,
        years=years,
        user_agent=user_agent,
        segments_mode=segments_mode,
        max_quarters=max_quarters,
        max_file_size_mb=max_file_size_mb,
        max_total_download_mb=max_total_download_mb,
    )


def _compute_run_id(company: str, years: int, payload: dict) -> str:
    payload_hash = hashlib.md5(json.dumps(payload, sort_keys=True, default=str).encode("utf-8")).hexdigest()[:10]
    return f"{company.lower()}_{years}y_{payload_hash}"


def render_plotly(fig, *, chart_id: str, section: str, run_id: str, **kwargs) -> None:
    key = f"{section}_{chart_id}_{run_id}"
    st.plotly_chart(fig, key=key, use_container_width=True, **kwargs)


with st.sidebar:
    company = st.text_input("Company (ticker or name)", value="AAPL")
    years = st.slider("Years", min_value=1, max_value=10, value=5)
    granularity_label = st.radio("View", options=["Quarterly", "Annual"], index=0)
    granularity = "quarterly" if granularity_label == "Quarterly" else "annual"
    max_quarters = st.slider("Max quarters (10-Q)", min_value=1, max_value=20, value=8)
    segments_mode = st.selectbox("Segment extraction mode", options=["none", "annual", "full"], index=1)
    max_file_size_mb = st.number_input("Max file size (MB)", min_value=1.0, max_value=200.0, value=25.0, step=1.0)
    max_total_download_mb = st.number_input("Max total download per run (MB)", min_value=10.0, max_value=2000.0, value=200.0, step=10.0)
    prefer_cache = st.checkbox("Prefer cached downloads", value=True)
    sec_ua = os.environ.get("SEC_USER_AGENT")
    if not sec_ua:
        sec_ua = st.text_input("SEC_USER_AGENT", value="", help="Required by SEC policy.")
    run = st.button("Extract & Visualize", type="primary")

    selected_cik = None
    if sec_ua and company.strip():
        try:
            selected_cik = resolve_company(SecClient(user_agent=sec_ua), company)["cik"]
            st.caption(f"Cache size for CIK {selected_cik}: {company_cache_size_bytes(selected_cik)/1024/1024:.2f} MB")
        except Exception:
            pass

    if st.button("Clear cache for current company") and selected_cik:
        clear_company_cache(selected_cik)
        st.success(f"Cleared cache for {selected_cik}")

    if st.button("Prune cache (30 days / 2GB)"):
        prune_cache(max_age_days=30, max_total_gb=2.0)
        st.success("Pruned SEC cache")

if run:
    if not sec_ua:
        st.error("SEC_USER_AGENT is required.")
        st.stop()

    progress = st.status("Running pipeline...", expanded=True)
    with progress:
        st.write("1) Resolve CIK")
        st.write("2) Fetch filings")
        st.write("3) Extract metrics to JSON")
        st.write("4) Build charts")

    payload = _run_extract(company, years, sec_ua, prefer_cache, segments_mode, max_quarters, max_file_size_mb, max_total_download_mb)
    st.session_state["payload"] = payload
    st.session_state["run_id"] = _compute_run_id(company, years, payload)

if "payload" in st.session_state:
    payload = st.session_state["payload"]
    run_id = st.session_state.get("run_id") or _compute_run_id(company, years, payload)
    st.session_state["run_id"] = run_id
    df, meta = json_to_tidy_df(payload)
    meta["period_payloads"] = payload.get("periods", [])
    meta["years"] = years

    df_filtered = filter_df_by_granularity(df, granularity)
    period_options = []
    selected_period_end = None
    if not df_filtered.empty:
        periods = df_filtered[["period_end", "period_label"]].drop_duplicates().sort_values("period_end")
        period_options = [(row.period_label, row.period_end) for row in periods.itertuples(index=False)]
    with st.sidebar:
        if period_options:
            labels = [x[0] for x in period_options]
            default_idx = len(labels) - 1
            selected_label = st.selectbox("Period", options=labels, index=default_idx)
            selected_period_end = next(v for l, v in period_options if l == selected_label)
        else:
            st.caption("No periods available for selected view.")

    figures = build_all_figures(df, meta, granularity=granularity, selected_period_end=selected_period_end)
    kpis = build_kpi_dashboard_figures(df_filtered, meta)

    tabs = st.tabs(["Dashboard", "Charts", "Downloads"])

    with tabs[0]:
        c1, c2, c3 = st.columns(3)
        for col, metric, label in [(c1, "revenue", "Latest Revenue"), (c2, "profit_net_income", "Latest Net Income"), (c3, "capex", "Latest CAPEX")]:
            subset = df_filtered[(df_filtered["metric"] == metric) & (df_filtered["segment"] == "Total")].sort_values("period_end")
            col.metric(label, f"{subset.iloc[-1]['value']:,.0f}" if not subset.empty else "Data unavailable")
        render_plotly(kpis["kpi_dashboard"], chart_id="01_kpi_dashboard", section="dashboard", run_id=run_id)
        for stem in ["02_revenue_trend", "03_profit_and_margin", "04_capex_trend"]:
            fig_data = next((x for x in figures if x[0] == stem), None)
            if fig_data:
                render_plotly(fig_data[1], chart_id=stem, section="dashboard", run_id=run_id)
                if not fig_data[2].get("created"):
                    st.info(f"{fig_data[2]['title']}: Data unavailable")

    with tabs[1]:
        st.subheader("All charts")
        order = [s for s, _ in CHART_ORDER]
        index = {s: (f, m) for s, f, m in figures}
        for stem in order:
            if stem not in index:
                continue
            fig, fig_meta = index[stem]
            st.markdown(f"**{stem} — {fig_meta.get('title')}**")
            render_plotly(fig, chart_id=stem, section="charts", run_id=run_id)
            if not fig_meta.get("created"):
                st.caption(f"Data unavailable: {fig_meta.get('skipped_reason')}")

        st.write("**Filings / Accessions used**")
        for a in meta.get("accessions", []):
            st.write(f"- {a}")
        if meta.get("transformations"):
            st.write("**Transformations**")
            for tr in meta.get("transformations", []):
                st.write(f"- {tr}")

    with tabs[2]:
        st.subheader("Downloads")
        json_bytes = json.dumps(payload, indent=2, sort_keys=True).encode("utf-8")
        st.download_button("Download extracted JSON", data=json_bytes, file_name="extracted_financials.json", mime="application/json")

        with tempfile.TemporaryDirectory() as td:
            zip_path = export_report_pack(Path(td), payload, figures, meta)
            st.download_button("Download report pack ZIP", data=Path(zip_path).read_bytes(), file_name="report_pack.zip", mime="application/zip")
