from __future__ import annotations

import hashlib
from typing import Any, Dict, List, Literal, Tuple

import pandas as pd
import plotly.graph_objects as go

from ui.theme import PALETTE
from viz.plotly_theme import apply_figure_theme
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
    colors = [PALETTE["primary_teal"], PALETTE["accent_sky"], PALETTE["positive"], PALETTE["warning"], PALETTE["negative"]]
    digest = hashlib.md5(segment.encode("utf-8")).hexdigest()
    return colors[int(digest[:8], 16) % len(colors)]


def _metric_total(df: pd.DataFrame, metric: str) -> pd.DataFrame:
    return df[(df["metric"] == metric) & (df["segment"] == "Total")].sort_values("period_end").copy()


def _metric_segments(df: pd.DataFrame, metric: str) -> pd.DataFrame:
    return df[(df["metric"] == metric) & (df["segment"] != "Total")].sort_values(["period_end", "segment"]).copy()


def _status(ok: bool, title: str, reason: str = "") -> Dict[str, Any]:
    return {"title": title, "created": ok, "skipped_reason": reason, "notes": "" if ok else "Data unavailable"}


def _empty_figure(message: str) -> go.Figure:
    fig = go.Figure()
    fig.add_annotation(text=message, showarrow=False, font={"color": PALETTE["body"], "size": 14})
    fig.update_xaxes(visible=False)
    fig.update_yaxes(visible=False)
    return apply_figure_theme(fig)


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
        fig.add_trace(go.Indicator(mode="number", value=float(rev.iloc[-1]["value"]), title={"text": "Revenue (latest)"}, domain={"x": [0.0, 0.32], "y": [0, 1]}))
    if not ni.empty:
        fig.add_trace(go.Indicator(mode="number", value=float(ni.iloc[-1]["value"]), title={"text": "Net Income (latest)"}, domain={"x": [0.34, 0.66], "y": [0, 1]}))
    if not cap.empty:
        fig.add_trace(go.Indicator(mode="number", value=float(cap.iloc[-1]["value"]), title={"text": "CAPEX (latest)"}, domain={"x": [0.68, 1.0], "y": [0, 1]}))
    return {"kpi_dashboard": apply_figure_theme(fig)}


def build_revenue_segment_sankey(df_filtered: pd.DataFrame, meta: Dict[str, Any], selected_period_end: pd.Timestamp | None = None) -> go.Figure | None:
    seg = _metric_segments(df_filtered, "revenue")
    if seg.empty:
        return None
    period_end = pd.Timestamp(selected_period_end) if selected_period_end is not None else seg["period_end"].max()
    period_seg = seg[seg["period_end"] == period_end]
    totals = _metric_total(df_filtered, "revenue")
    period_total = totals[totals["period_end"] == period_end]
    if period_seg.empty or period_total.empty:
        return None

    segment_values = period_seg.groupby("segment", as_index=False)["value"].sum().sort_values("value", ascending=False)
    if segment_values.empty:
        return None

    total_value = float(period_total["value"].sum())
    fig = go.Figure(
        data=[
            go.Sankey(
                arrangement="snap",
                orientation="h",
                node={
                    "pad": 22,
                    "thickness": 22,
                    "line": {"color": "rgba(15,23,42,0.15)", "width": 0.5},
                    "label": ["Total Revenue"] + segment_values["segment"].tolist(),
                    "color": [PALETTE["heading"]] + [_stable_color(str(s)) for s in segment_values["segment"].tolist()],
                    "x": [0.02] + [0.9] * len(segment_values),
                },
                link={
                    "source": [0] * len(segment_values),
                    "target": list(range(1, len(segment_values) + 1)),
                    "value": segment_values["value"].astype(float).tolist(),
                    "color": [_stable_color(str(s)) for s in segment_values["segment"].tolist()],
                    "label": [
                        f"{seg_name}: {val:,.0f} ({(val / total_value * 100) if total_value else 0.0:.1f}%)"
                        for seg_name, val in zip(segment_values["segment"], segment_values["value"])
                    ],
                },
            )
        ]
    )
    label = period_seg.iloc[0].get("period_label") or period_end.strftime("%Y-%m-%d")
    fig.update_layout(title=f"Revenue by Segment Sankey ({label})")
    return apply_figure_theme(fig)


def build_all_figures(df: pd.DataFrame, meta: Dict[str, Any], granularity: Literal["quarterly", "annual"] = "quarterly", selected_period_end: pd.Timestamp | None = None) -> List[Tuple[str, go.Figure, Dict[str, Any]]]:
    out: List[Tuple[str, go.Figure, Dict[str, Any]]] = []
    dfg = filter_df_by_granularity(df, granularity)
    out.append(("01_kpi_dashboard", build_kpi_dashboard_figures(dfg, meta)["kpi_dashboard"], _status(True, "KPI dashboard")))

    rev = _metric_total(dfg, "revenue")
    if rev.empty:
        out.append(("02_revenue_trend", _empty_figure("Data unavailable"), _status(False, "Revenue trend", "Revenue missing.")))
    else:
        fig = go.Figure()
        fig.add_scatter(x=rev["period_end"], y=rev["value"], mode="lines+markers", name="Revenue", line={"color": PALETTE["primary_teal"]})
        fig.update_layout(title="Revenue trend")
        out.append(("02_revenue_trend", apply_figure_theme(fig), _status(True, "Revenue trend")))

    ni = _metric_total(dfg, "profit_net_income")
    if ni.empty or rev.empty:
        out.append(("03_profit_and_margin", _empty_figure("Data unavailable"), _status(False, "Profit and margin", "Revenue or net income missing.")))
    else:
        m = ni[["period_end", "value"]].merge(rev[["period_end", "value"]], on="period_end", suffixes=("_ni", "_rev"))
        m["margin"] = m["value_ni"] / m["value_rev"] * 100
        fig = go.Figure()
        fig.add_bar(x=m["period_end"], y=m["value_ni"], name="Net income", marker={"color": PALETTE["accent_sky"]})
        fig.add_scatter(x=m["period_end"], y=m["margin"], mode="lines+markers", name="Margin %", yaxis="y2", line={"color": PALETTE["positive"]})
        fig.update_layout(title="Net income and margin", yaxis2={"overlaying": "y", "side": "right", "title": "Margin %"})
        out.append(("03_profit_and_margin", apply_figure_theme(fig), _status(True, "Profit and margin")))

    cap = _metric_total(dfg, "capex")
    if cap.empty:
        out.append(("04_capex_trend", _empty_figure("Data unavailable"), _status(False, "CAPEX trend", "CAPEX missing.")))
    else:
        fig = go.Figure()
        fig.add_bar(x=cap["period_end"], y=cap["value"], name="CAPEX", marker={"color": PALETTE["warning"]})
        fig.update_layout(title="CAPEX trend")
        out.append(("04_capex_trend", apply_figure_theme(fig), _status(True, "CAPEX trend")))

    if cap.empty or rev.empty:
        out.append(("05_capex_intensity", _empty_figure("Data unavailable"), _status(False, "CAPEX intensity", "CAPEX or revenue missing.")))
    else:
        m = cap[["period_end", "value"]].merge(rev[["period_end", "value"]], on="period_end", suffixes=("_c", "_r"))
        m["intensity"] = m["value_c"] / m["value_r"] * 100
        fig = go.Figure()
        fig.add_scatter(x=m["period_end"], y=m["intensity"], mode="lines+markers", name="CAPEX intensity %", line={"color": PALETTE["warning"]})
        fig.update_layout(title="CAPEX intensity")
        out.append(("05_capex_intensity", apply_figure_theme(fig), _status(True, "CAPEX intensity")))

    seg = _metric_segments(dfg, "revenue")
    selected_end = pd.Timestamp(selected_period_end) if selected_period_end is not None else (seg["period_end"].max() if not seg.empty else None)
    if seg.empty or selected_end is None:
        out.append(("06_snapshot_revenue_mix", _empty_figure("Segment revenue not available"), _status(False, "Snapshot revenue mix", "Segment revenue missing.")))
    else:
        latest = seg[seg["period_end"] == selected_end].groupby("segment")["value"].sum().sort_values(ascending=False)
        if latest.empty:
            out.append(("06_snapshot_revenue_mix", _empty_figure("Segment revenue not available"), _status(False, "Snapshot revenue mix", "Segment revenue missing.")))
        else:
            fig = go.Figure(go.Pie(labels=latest.index.tolist(), values=latest.values.tolist(), hole=0.5))
            fig.update_layout(title="Snapshot revenue mix")
            out.append(("06_snapshot_revenue_mix", apply_figure_theme(fig), _status(True, "Snapshot revenue mix")))

    sankey = build_revenue_segment_sankey(dfg, meta, selected_period_end=selected_end)
    out.append(("07_revenue_segment_sankey", sankey if sankey is not None else _empty_figure("Segment revenue not available"), _status(sankey is not None, "Revenue by segment Sankey", "Segment revenue not available." if sankey is None else "")))

    if seg.empty or selected_end is None:
        out.append(("08_waterfall_revenue_yoy_change", _empty_figure("Data unavailable"), _status(False, "Revenue YoY segment change", "Segment revenue missing.")))
    else:
        prior_date = selected_end - pd.DateOffset(years=1)
        latest = seg[seg["period_end"] == selected_end].groupby("segment")["value"].sum()
        prior = seg[seg["period_end"] == prior_date].groupby("segment")["value"].sum()
        change = (latest - prior).dropna().sort_values(ascending=False)
        if change.empty:
            out.append(("08_waterfall_revenue_yoy_change", _empty_figure("Data unavailable"), _status(False, "Revenue YoY segment change", "Insufficient YoY overlap.")))
        else:
            fig = go.Figure(go.Bar(x=change.index.tolist(), y=change.values.tolist(), marker={"color": PALETTE["primary_teal"]}))
            fig.update_layout(title="Revenue YoY segment change")
            out.append(("08_waterfall_revenue_yoy_change", apply_figure_theme(fig), _status(True, "Revenue YoY segment change")))

    if has_valid_forecast_capex(meta):
        fc_rows = []
        for p in meta.get("period_payloads", []):
            for f in p.get("forecasted_capex", []) or []:
                has_value = any(f.get(k) is not None for k in ("value", "value_min", "value_max"))
                if has_value and f.get("timeframe"):
                    fc_rows.append({"period_end": p.get("period_end"), **f})
        forecast = pd.DataFrame(fc_rows)
        if cap.empty or forecast.empty:
            out.append(("09_forecast_capex", _empty_figure("Data unavailable"), _status(False, "Forecast CAPEX", "No forecast CAPEX guidance.")))
        else:
            forecast["period_end"] = pd.to_datetime(forecast["period_end"], errors="coerce")
            forecast = forecast.sort_values("period_end")
            fig = go.Figure()
            fig.add_scatter(x=cap["period_end"], y=cap["value"], mode="lines", name="Historical CAPEX", line={"color": PALETTE["accent_sky"]})
            if "value" in forecast.columns and forecast["value"].notna().any():
                fig.add_scatter(x=forecast["period_end"], y=forecast["value"], mode="lines+markers", name="Forecast", line={"color": PALETTE["positive"]})
            if "value_min" in forecast.columns and forecast["value_min"].notna().any():
                fig.add_scatter(x=forecast["period_end"], y=forecast["value_min"], mode="lines", name="Forecast min", line={"dash": "dot", "color": PALETTE["warning"]})
            if "value_max" in forecast.columns and forecast["value_max"].notna().any():
                fig.add_scatter(x=forecast["period_end"], y=forecast["value_max"], mode="lines", name="Forecast max", line={"dash": "dot", "color": PALETTE["warning"]})
            fig.update_layout(title="Forecast CAPEX")
            out.append(("09_forecast_capex", apply_figure_theme(fig), _status(True, "Forecast CAPEX")))

    return out
