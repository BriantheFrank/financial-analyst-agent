from __future__ import annotations

import hashlib
from typing import Any, Dict, List, Sequence, Tuple

import pandas as pd
import plotly.graph_objects as go

from templates.house_style import PALETTE

CHART_ORDER: List[Tuple[str, str]] = [
    ("01_kpi_dashboard", "KPI dashboard"),
    ("02_revenue_trend", "Revenue trend (quarterly)"),
    ("03_revenue_by_segment", "Revenue by segment"),
    ("04_profit_and_margin", "Net income + margin"),
    ("05_capex_trend", "CAPEX trend"),
    ("06_capex_intensity", "CAPEX intensity"),
    ("07_snapshot_revenue_mix_latest_q", "Snapshot revenue mix (latest quarter)"),
    ("08_waterfall_revenue_yoy_change", "Revenue YoY segment change"),
    ("09_forecast_capex", "Forecast CAPEX"),
    ("10_data_coverage", "Data coverage"),
]


def _stable_color(segment: str) -> str:
    digest = hashlib.md5(segment.encode("utf-8")).hexdigest()
    return PALETTE[int(digest[:8], 16) % len(PALETTE)]


def _metric_total(df: pd.DataFrame, metric: str) -> pd.DataFrame:
    return df[(df["metric"] == metric) & (df["segment"] == "Total")].sort_values("period_end").copy()


def _metric_segments(df: pd.DataFrame, metric: str) -> pd.DataFrame:
    return df[(df["metric"] == metric) & (df["segment"] != "Total")].sort_values(["period_end", "segment"]).copy()


def _status(ok: bool, title: str, reason: str = "") -> Dict[str, Any]:
    return {"title": title, "created": ok, "skipped_reason": reason, "notes": "" if ok else "Data unavailable"}


def build_kpi_dashboard_figures(df: pd.DataFrame, meta: Dict[str, Any]) -> Dict[str, go.Figure]:
    rev = _metric_total(df, "revenue")
    ni = _metric_total(df, "profit_net_income")
    cap = _metric_total(df, "capex")
    fig = go.Figure()
    fig.update_layout(title=f"{meta.get('company_name', 'Company')} KPI Snapshot")
    if not rev.empty:
        latest_rev = float(rev.iloc[-1]["value"])
        fig.add_trace(go.Indicator(mode="number", value=latest_rev, title={"text": "Revenue (latest)"}, domain={"x": [0.0, 0.32], "y": [0, 1]}))
    if not ni.empty:
        latest_ni = float(ni.iloc[-1]["value"])
        fig.add_trace(go.Indicator(mode="number", value=latest_ni, title={"text": "Net Income (latest)"}, domain={"x": [0.34, 0.66], "y": [0, 1]}))
    if not cap.empty:
        latest_cap = float(cap.iloc[-1]["value"])
        fig.add_trace(go.Indicator(mode="number", value=latest_cap, title={"text": "CAPEX (latest)"}, domain={"x": [0.68, 1.0], "y": [0, 1]}))
    return {"kpi_dashboard": fig}


def build_all_figures(df: pd.DataFrame, meta: Dict[str, Any]) -> List[Tuple[str, go.Figure, Dict[str, Any]]]:
    out: List[Tuple[str, go.Figure, Dict[str, Any]]] = []

    # 01 KPI
    kpi_fig = build_kpi_dashboard_figures(df, meta)["kpi_dashboard"]
    out.append(("01_kpi_dashboard", kpi_fig, _status(True, "KPI dashboard")))

    # 02 Revenue trend
    rev = _metric_total(df, "revenue")
    fig = go.Figure()
    if rev.empty:
        fig.add_annotation(text="Data unavailable", showarrow=False)
        out.append(("02_revenue_trend", fig, _status(False, "Revenue trend", "Revenue totals missing.")))
    else:
        fig.add_scatter(x=rev["period_end"], y=rev["value"], mode="lines+markers", name="Revenue")
        fig.update_layout(title="Revenue trend (quarterly)")
        out.append(("02_revenue_trend", fig, _status(True, "Revenue trend")))

    # 03 Revenue by segment
    seg = _metric_segments(df, "revenue")
    fig = go.Figure()
    if seg.empty:
        fig.add_annotation(text="Data unavailable", showarrow=False)
        out.append(("03_revenue_by_segment", fig, _status(False, "Revenue by segment", "Segment revenue missing.")))
    else:
        piv = seg.pivot_table(index="period_end", columns="segment", values="value", aggfunc="sum", fill_value=0).sort_index()
        for col in piv.columns:
            fig.add_bar(x=piv.index, y=piv[col], name=col, marker_color=_stable_color(str(col)))
        fig.update_layout(title="Revenue by segment", barmode="stack")
        out.append(("03_revenue_by_segment", fig, _status(True, "Revenue by segment")))

    # 04 Profit and margin
    prof = _metric_total(df, "profit_net_income")
    fig = go.Figure()
    if prof.empty or rev.empty:
        fig.add_annotation(text="Data unavailable", showarrow=False)
        out.append(("04_profit_and_margin", fig, _status(False, "Profit and margin", "Profit or revenue missing.")))
    else:
        m = prof[["period_end", "value"]].merge(rev[["period_end", "value"]], on="period_end", suffixes=("_p", "_r"))
        m["margin"] = m["value_p"] / m["value_r"] * 100
        fig.add_bar(x=m["period_end"], y=m["value_p"], name="Net income")
        fig.add_scatter(x=m["period_end"], y=m["margin"], mode="lines+markers", name="Margin %", yaxis="y2")
        fig.update_layout(title="Net income and margin", yaxis2={"overlaying": "y", "side": "right"})
        out.append(("04_profit_and_margin", fig, _status(True, "Profit and margin")))

    # 05 CAPEX trend
    cap = _metric_total(df, "capex")
    fig = go.Figure()
    if cap.empty:
        fig.add_annotation(text="Data unavailable", showarrow=False)
        out.append(("05_capex_trend", fig, _status(False, "CAPEX trend", "CAPEX missing.")))
    else:
        cap = cap.sort_values("period_end")
        fig.add_bar(x=cap["period_end"], y=cap["value"], name="CAPEX")
        fig.update_layout(title="CAPEX trend")
        out.append(("05_capex_trend", fig, _status(True, "CAPEX trend")))

    # 06 CAPEX intensity
    fig = go.Figure()
    if cap.empty or rev.empty:
        fig.add_annotation(text="Data unavailable", showarrow=False)
        out.append(("06_capex_intensity", fig, _status(False, "CAPEX intensity", "CAPEX or revenue missing.")))
    else:
        m = cap[["period_end", "value"]].merge(rev[["period_end", "value"]], on="period_end", suffixes=("_c", "_r"))
        m["intensity"] = m["value_c"] / m["value_r"] * 100
        fig.add_scatter(x=m["period_end"], y=m["intensity"], mode="lines+markers", name="CAPEX intensity %")
        fig.update_layout(title="CAPEX intensity")
        out.append(("06_capex_intensity", fig, _status(True, "CAPEX intensity")))

    # 07 Snapshot mix
    fig = go.Figure()
    if seg.empty:
        fig.add_annotation(text="Data unavailable", showarrow=False)
        out.append(("07_snapshot_revenue_mix_latest_q", fig, _status(False, "Snapshot revenue mix", "Segment revenue missing.")))
    else:
        latest_date = seg["period_end"].max()
        latest = seg[seg["period_end"] == latest_date].groupby("segment")["value"].sum().sort_values(ascending=False)
        fig.add_pie(labels=latest.index.tolist(), values=latest.values.tolist(), hole=0.35)
        fig.update_layout(title="Snapshot revenue mix (latest quarter)")
        out.append(("07_snapshot_revenue_mix_latest_q", fig, _status(True, "Snapshot revenue mix")))

    # 08 Waterfall-ish YoY change (bar)
    fig = go.Figure()
    if seg.empty:
        fig.add_annotation(text="Data unavailable", showarrow=False)
        out.append(("08_waterfall_revenue_yoy_change", fig, _status(False, "Revenue YoY segment change", "Segment revenue missing.")))
    else:
        latest_date = seg["period_end"].max()
        prior_date = latest_date - pd.DateOffset(years=1)
        latest = seg[seg["period_end"] == latest_date].groupby("segment")["value"].sum()
        prior = seg[seg["period_end"] == prior_date].groupby("segment")["value"].sum()
        change = (latest - prior).dropna().sort_values(ascending=False)
        if change.empty:
            fig.add_annotation(text="Data unavailable", showarrow=False)
            out.append(("08_waterfall_revenue_yoy_change", fig, _status(False, "Revenue YoY segment change", "Insufficient YoY overlap.")))
        else:
            fig.add_bar(x=change.index.tolist(), y=change.values.tolist())
            fig.update_layout(title="Revenue YoY segment change")
            out.append(("08_waterfall_revenue_yoy_change", fig, _status(True, "Revenue YoY segment change")))

    # 09 Forecast CAPEX
    fc_rows = []
    for p in meta.get("period_payloads", []):
        for f in p.get("forecasted_capex", []) or []:
            fc_rows.append({"period_end": p.get("period_end"), **f})
    forecast = pd.DataFrame(fc_rows)
    fig = go.Figure()
    if cap.empty or forecast.empty:
        fig.add_annotation(text="Data unavailable", showarrow=False)
        out.append(("09_forecast_capex", fig, _status(False, "Forecast CAPEX", "No forecast CAPEX guidance.")))
    else:
        forecast["period_end"] = pd.to_datetime(forecast["period_end"], errors="coerce")
        forecast = forecast.sort_values("period_end")
        fig.add_scatter(x=cap["period_end"], y=cap["value"], mode="lines", name="Historical CAPEX")
        fig.add_scatter(x=forecast["period_end"], y=forecast["value_min"], mode="lines", name="Forecast min", line={"dash": "dot"})
        fig.add_scatter(x=forecast["period_end"], y=forecast["value_max"], mode="lines", name="Forecast max", line={"dash": "dot"})
        fig.update_layout(title="Forecast CAPEX")
        out.append(("09_forecast_capex", fig, _status(True, "Forecast CAPEX")))

    # 10 Coverage
    fig = go.Figure()
    periods = sorted([d for d in df["period_end"].dropna().unique().tolist()])
    if not periods:
        fig.add_annotation(text="Data unavailable", showarrow=False)
        out.append(("10_data_coverage", fig, _status(False, "Data coverage", "No periods available.")))
    else:
        labels = [pd.Timestamp(p).strftime("%Y-%m-%d") for p in periods]
        metrics = ["revenue", "profit_net_income", "capex", "segment_revenue"]
        matrix = []
        for metric in metrics:
            row = []
            for p in periods:
                dfx = df[df["period_end"] == p]
                if metric == "segment_revenue":
                    present = ((dfx["metric"] == "revenue") & (dfx["segment"] != "Total")).any()
                else:
                    present = ((dfx["metric"] == metric) & (dfx["segment"] == "Total")).any()
                row.append(1 if present else 0)
            matrix.append(row)
        fig.add_trace(go.Heatmap(z=matrix, x=labels, y=["Revenue", "Profit", "CAPEX", "Revenue segments"], colorscale="Greens", zmin=0, zmax=1))
        fig.update_layout(title="Data coverage")
        out.append(("10_data_coverage", fig, _status(True, "Data coverage")))

    return out
