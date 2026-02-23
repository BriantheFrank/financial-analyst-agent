from __future__ import annotations

import io
import json
import os
import tempfile
from pathlib import Path

import streamlit as st

from sec_financials import extract_company_financials
from viz.charts import CHART_ORDER, build_all_figures, build_kpi_dashboard_figures
from viz.export import export_report_pack
from viz.transform import json_to_tidy_df


st.set_page_config(page_title="Financial Analyst Agent (Local)", layout="wide")
st.title("Financial Analyst Agent (Local)")


@st.cache_data(show_spinner=False)
def _cached_extract(company: str, years: int, user_agent: str) -> dict:
    return extract_company_financials(company=company, years=years, user_agent=user_agent)


def _run_extract(company: str, years: int, user_agent: str, prefer_cache: bool) -> dict:
    if prefer_cache:
        return _cached_extract(company, years, user_agent)
    _cached_extract.clear()
    return extract_company_financials(company=company, years=years, user_agent=user_agent)


with st.sidebar:
    company = st.text_input("Company (ticker or name)", value="AAPL")
    years = st.slider("Years", min_value=1, max_value=10, value=5)
    prefer_cache = st.checkbox("Prefer cached downloads", value=True)
    sec_ua = os.environ.get("SEC_USER_AGENT")
    if not sec_ua:
        sec_ua = st.text_input("SEC_USER_AGENT", value="", help="Required by SEC policy.")
    run = st.button("Extract & Visualize", type="primary")

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

    payload = _run_extract(company, years, sec_ua, prefer_cache)
    st.session_state["payload"] = payload

if "payload" in st.session_state:
    payload = st.session_state["payload"]
    df, meta = json_to_tidy_df(payload)
    meta["period_payloads"] = payload.get("periods", [])
    meta["years"] = years
    figures = build_all_figures(df, meta)
    kpis = build_kpi_dashboard_figures(df, meta)

    tabs = st.tabs(["Dashboard", "Charts", "Data & Coverage", "Downloads"])

    with tabs[0]:
        c1, c2, c3 = st.columns(3)
        for col, metric, label in [(c1, "revenue", "Latest Revenue"), (c2, "profit_net_income", "Latest Net Income"), (c3, "capex", "Latest CAPEX")]:
            subset = df[(df["metric"] == metric) & (df["segment"] == "Total")].sort_values("period_end")
            col.metric(label, f"{subset.iloc[-1]['value']:,.0f}" if not subset.empty else "Data unavailable")
        st.plotly_chart(kpis["kpi_dashboard"], use_container_width=True)
        for stem in ["02_revenue_trend", "04_profit_and_margin", "05_capex_trend"]:
            fig_data = next((x for x in figures if x[0] == stem), None)
            if fig_data:
                st.plotly_chart(fig_data[1], use_container_width=True)
                if not fig_data[2].get("created"):
                    st.info(f"{fig_data[2]['title']}: Data unavailable")

    with tabs[1]:
        st.subheader("All charts")
        order = [s for s, _ in CHART_ORDER]
        index = {s: (f, m) for s, f, m in figures}
        for stem in order:
            fig, fig_meta = index[stem]
            st.markdown(f"**{stem} — {fig_meta.get('title')}**")
            st.plotly_chart(fig, use_container_width=True)
            if not fig_meta.get("created"):
                st.caption(f"Data unavailable: {fig_meta.get('skipped_reason')}")

    with tabs[2]:
        st.subheader("Coverage")
        coverage = next((x for x in figures if x[0] == "10_data_coverage"), None)
        if coverage:
            st.plotly_chart(coverage[1], use_container_width=True)
        st.write("**Filings / Accessions used**")
        for a in meta.get("accessions", []):
            st.write(f"- {a}")
        st.write("**Transformations**")
        for tr in meta.get("transformations", []):
            st.write(f"- {tr}")

    with tabs[3]:
        st.subheader("Downloads")
        json_bytes = json.dumps(payload, indent=2, sort_keys=True).encode("utf-8")
        st.download_button("Download extracted JSON", data=json_bytes, file_name="extracted_financials.json", mime="application/json")

        with tempfile.TemporaryDirectory() as td:
            zip_path = export_report_pack(Path(td), payload, figures, meta)
            st.download_button("Download report pack ZIP", data=Path(zip_path).read_bytes(), file_name="report_pack.zip", mime="application/zip")
