from __future__ import annotations

import hashlib
from typing import Any, Dict, List, Literal, Tuple

import pandas as pd
import plotly.graph_objects as go

from templates.house_style import PALETTE
from viz.transform import filter_df_by_granularity

CHART_ORDER: List[Tuple[str, str]] = [
    ("01_kpi_dashboard", "KPI dashboard"),
    ("02_revenue_trend", "Revenue trend"),
    ("03_profit_and_margin", "Net income + margin"),
    ("04_capex_trend", "CAPEX trend"),
    ("05_capex_intensity", "CAPEX intensity"),
    ("06_snapshot_revenue_mix", "Snapshot revenue mix"),
    ("07_revenue_segment_sankey", "Revenue by segment Sankey"),
    ("08_waterfall_revenue_yoy_change", "Revenue YoY segment change"),
    ("09_forecast_capex", "Forecast CAPEX"),
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


def has_valid_forecast_capex(meta: Dict[str, Any]) -> bool:
    for p in meta.get("period_payloads", []):
        for f in p.get("forecasted_capex", []) or []:
            has_value = any(f.get(k) is not None for k in ("value", "value_min", "value_max"))
            if has_value and f.get("timeframe"):
                return True
    return False


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


def build_revenue_segment_sankey(
    df_filtered: pd.DataFrame,
    meta: Dict[str, Any],
    selected_period_end: pd.Timestamp | None = None,
) -> go.Figure | None:
    seg = _metric_segments(df_filtered, "revenue")
    if seg.empty:
        return None

    period_end = pd.Timestamp(selected_period_end) if selected_period_end is not None else seg["period_end"].max()
    period_seg = seg[seg["period_end"] == period_end]
    if period_seg.empty:
        return None

    totals = _metric_total(df_filtered, "revenue")
    period_total = totals[totals["period_end"] == period_end]
    if period_total.empty:
        return None

    segment_values = period_seg.groupby("segment", as_index=False)["value"].sum().sort_values("value", ascending=False)
    if segment_values.empty:
        return None

    total_value = float(period_total["value"].sum())
    node_labels = ["Total Revenue"] + segment_values["segment"].tolist()
    node_colors = ["#3A3A3A"] + [_stable_color(str(s)) for s in segment_values["segment"].tolist()]

    sources = [0] * len(segment_values)
    targets = list(range(1, len(segment_values) + 1))
    values = segment_values["value"].astype(float).tolist()
    shares = [(v / total_value * 100) if total_value else 0.0 for v in values]
    link_labels = [f"{seg}: {val:,.0f} ({share:.1f}%)" for seg, val, share in zip(segment_values["segment"], values, shares)]

    fig = go.Figure(
        data=[
            go.Sankey(
                arrangement="snap",
                orientation="h",
                node={
                    "pad": 25,
                    "thickness": 24,
                    "line": {"color": "rgba(0,0,0,0.15)", "width": 0.5},
                    "label": node_labels,
                    "color": node_colors,
                    "x": [0.03] + [0.9] * len(segment_values),
                },
                link={
                    "source": sources,
                    "target": targets,
                    "value": values,
                    "color": [_stable_color(str(s)) for s in segment_values["segment"].tolist()],
                    "label": link_labels,
                },
            )
        ]
    )
    label = period_seg.iloc[0].get("period_label") or period_end.strftime("%Y-%m-%d")
    fig.update_layout(title=f"Revenue by Segment Sankey ({label})")
    return fig


def build_all_figures(
    df: pd.DataFrame,
    meta: Dict[str, Any],
    granularity: Literal["quarterly", "annual"] = "quarterly",
    selected_period_end: pd.Timestamp | None = None,
) -> List[Tuple[str, go.Figure, Dict[str, Any]]]:
    out: List[Tuple[str, go.Figure, Dict[str, Any]]] = []
    dfg = filter_df_by_granularity(df, granularity)

    kpi_fig = build_kpi_dashboard_figures(dfg, meta)["kpi_dashboard"]
    out.append(("01_kpi_dashboard", kpi_fig, _status(True, "KPI dashboard")))

    rev = _metric_total(dfg, "revenue")
    fig = go.Figure()
    if rev.empty:
        fig.add_annotation(text="Data unavailable", showarrow=False)
        out.append(("02_revenue_trend", fig, _status(False, "Revenue trend", "Revenue totals missing.")))
    else:
        fig.add_scatter(x=rev["period_end"], y=rev["value"], mode="lines+markers", name="Revenue")
        fig.update_layout(title=f"Revenue trend ({granularity})")
        out.append(("02_revenue_trend", fig, _status(True, "Revenue trend")))

    prof = _metric_total(dfg, "profit_net_income")
    fig = go.Figure()
    if prof.empty or rev.empty:
        fig.add_annotation(text="Data unavailable", showarrow=False)
        out.append(("03_profit_and_margin", fig, _status(False, "Profit and margin", "Profit or revenue missing.")))
    else:
        m = prof[["period_end", "value"]].merge(rev[["period_end", "value"]], on="period_end", suffixes=("_p", "_r"))
        m["margin"] = m["value_p"] / m["value_r"] * 100
        fig.add_bar(x=m["period_end"], y=m["value_p"], name="Net income")
        fig.add_scatter(x=m["period_end"], y=m["margin"], mode="lines+markers", name="Margin %", yaxis="y2")
        fig.update_layout(title="Net income and margin", yaxis2={"overlaying": "y", "side": "right"})
        out.append(("03_profit_and_margin", fig, _status(True, "Profit and margin")))

    cap = _metric_total(dfg, "capex")
    fig = go.Figure()
    if cap.empty:
        fig.add_annotation(text="Data unavailable", showarrow=False)
        out.append(("04_capex_trend", fig, _status(False, "CAPEX trend", "CAPEX missing.")))
    else:
        fig.add_bar(x=cap["period_end"], y=cap["value"], name="CAPEX")
        fig.update_layout(title="CAPEX trend")
        out.append(("04_capex_trend", fig, _status(True, "CAPEX trend")))

    fig = go.Figure()
    if cap.empty or rev.empty:
        fig.add_annotation(text="Data unavailable", showarrow=False)
        out.append(("05_capex_intensity", fig, _status(False, "CAPEX intensity", "CAPEX or revenue missing.")))
    else:
        m = cap[["period_end", "value"]].merge(rev[["period_end", "value"]], on="period_end", suffixes=("_c", "_r"))
        m["intensity"] = m["value_c"] / m["value_r"] * 100
        fig.add_scatter(x=m["period_end"], y=m["intensity"], mode="lines+markers", name="CAPEX intensity %")
        fig.update_layout(title="CAPEX intensity")
        out.append(("05_capex_intensity", fig, _status(True, "CAPEX intensity")))

    seg = _metric_segments(dfg, "revenue")
    selected_end = pd.Timestamp(selected_period_end) if selected_period_end is not None else (seg["period_end"].max() if not seg.empty else None)

    fig = go.Figure()
    if seg.empty or selected_end is None:
        fig.add_annotation(text="Segment revenue not available", showarrow=False)
        out.append(("06_snapshot_revenue_mix", fig, _status(False, "Snapshot revenue mix", "Segment revenue missing.")))
    else:
        latest = seg[seg["period_end"] == selected_end].groupby("segment")["value"].sum().sort_values(ascending=False)
        if latest.empty:
            fig.add_annotation(text="Segment revenue not available", showarrow=False)
            out.append(("06_snapshot_revenue_mix", fig, _status(False, "Snapshot revenue mix", "Segment revenue missing.")))
        else:
            fig.add_pie(labels=latest.index.tolist(), values=latest.values.tolist(), hole=0.35)
            label = seg[seg["period_end"] == selected_end]["period_label"].iloc[0]
            fig.update_layout(title=f"Snapshot revenue mix ({label})")
            out.append(("06_snapshot_revenue_mix", fig, _status(True, "Snapshot revenue mix")))

    sankey = build_revenue_segment_sankey(dfg, meta, selected_period_end=selected_end)
    if sankey is None:
        fig = go.Figure()
        fig.add_annotation(text="Segment revenue not available", showarrow=False)
        out.append(("07_revenue_segment_sankey", fig, _status(False, "Revenue by segment Sankey", "Segment revenue not available.")))
    else:
        out.append(("07_revenue_segment_sankey", sankey, _status(True, "Revenue by segment Sankey")))

    fig = go.Figure()
    if seg.empty or selected_end is None:
        fig.add_annotation(text="Data unavailable", showarrow=False)
        out.append(("08_waterfall_revenue_yoy_change", fig, _status(False, "Revenue YoY segment change", "Segment revenue missing.")))
    else:
        prior_date = selected_end - pd.DateOffset(years=1)
        latest = seg[seg["period_end"] == selected_end].groupby("segment")["value"].sum()
        prior = seg[seg["period_end"] == prior_date].groupby("segment")["value"].sum()
        change = (latest - prior).dropna().sort_values(ascending=False)
        if change.empty:
            fig.add_annotation(text="Data unavailable", showarrow=False)
            out.append(("08_waterfall_revenue_yoy_change", fig, _status(False, "Revenue YoY segment change", "Insufficient YoY overlap.")))
        else:
            fig.add_bar(x=change.index.tolist(), y=change.values.tolist())
            fig.update_layout(title="Revenue YoY segment change")
            out.append(("08_waterfall_revenue_yoy_change", fig, _status(True, "Revenue YoY segment change")))

    if has_valid_forecast_capex(meta):
        fc_rows = []
        for p in meta.get("period_payloads", []):
            for f in p.get("forecasted_capex", []) or []:
                has_value = any(f.get(k) is not None for k in ("value", "value_min", "value_max"))
                if has_value and f.get("timeframe"):
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
            if "value" in forecast.columns and forecast["value"].notna().any():
                fig.add_scatter(x=forecast["period_end"], y=forecast["value"], mode="lines+markers", name="Forecast")
            if "value_min" in forecast.columns and forecast["value_min"].notna().any():
                fig.add_scatter(x=forecast["period_end"], y=forecast["value_min"], mode="lines", name="Forecast min", line={"dash": "dot"})
            if "value_max" in forecast.columns and forecast["value_max"].notna().any():
                fig.add_scatter(x=forecast["period_end"], y=forecast["value_max"], mode="lines", name="Forecast max", line={"dash": "dot"})
            fig.update_layout(title="Forecast CAPEX")
            out.append(("09_forecast_capex", fig, _status(True, "Forecast CAPEX")))

    return out
