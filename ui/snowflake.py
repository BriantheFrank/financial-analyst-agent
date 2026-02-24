from __future__ import annotations

from typing import Any

import pandas as pd
import plotly.graph_objects as go

from ui.theme import PALETTE
from viz.plotly_theme import apply_figure_theme

SNOWFLAKE_AXES = ["Valuation", "Future Growth", "Past Performance", "Financial Health", "Dividend"]


def _score_from_ratio(value: float, thresholds: list[float]) -> int:
    for idx, t in enumerate(thresholds):
        if value < t:
            return idx
    return 6


def compute_snowflake_scores(df: pd.DataFrame, meta: dict[str, Any], granularity: str) -> dict[str, int | None]:
    """Heuristic v1 scores from extracted series only; no external valuation/dividend feeds."""
    dfg = df[df["period_type"] == granularity].copy() if not df.empty else df
    rev = dfg[(dfg["metric"] == "revenue") & (dfg["segment"] == "Total")].sort_values("period_end")
    ni = dfg[(dfg["metric"] == "profit_net_income") & (dfg["segment"] == "Total")].sort_values("period_end")
    cap = dfg[(dfg["metric"] == "capex") & (dfg["segment"] == "Total")].sort_values("period_end")

    scores: dict[str, int | None] = {axis: None for axis in SNOWFLAKE_AXES}
    scores["Valuation"] = None
    scores["Dividend"] = None

    if len(rev) >= 2:
        rev_growth = rev["value"].pct_change().dropna() * 100
        if not rev_growth.empty:
            avg_growth = float(rev_growth.tail(4).mean())
            cap_signal = 1 if not cap.empty else 0
            scores["Future Growth"] = min(6, max(0, _score_from_ratio(avg_growth, [-10, -2, 2, 6, 12, 20]) + cap_signal))

            ni_merge = rev[["period_end", "value"]].merge(
                ni[["period_end", "value"]], on="period_end", suffixes=("_rev", "_ni")
            )
            if not ni_merge.empty:
                ni_merge["margin"] = (ni_merge["value_ni"] / ni_merge["value_rev"]).replace([pd.NA], 0) * 100
                margin_std = float(ni_merge["margin"].tail(6).std() or 0)
                growth_component = _score_from_ratio(avg_growth, [-20, -5, 0, 5, 10, 20])
                stability_bonus = 2 if margin_std < 3 else (1 if margin_std < 8 else 0)
                scores["Past Performance"] = min(6, max(0, growth_component + stability_bonus))

    if not rev.empty and not ni.empty and not cap.empty:
        recent = rev[["period_end", "value"]].merge(
            cap[["period_end", "value"]], on="period_end", suffixes=("_rev", "_cap")
        ).merge(ni[["period_end", "value"]], on="period_end")
        recent = recent.tail(6)
        if not recent.empty:
            recent["cap_intensity"] = recent["value_cap"] / recent["value_rev"] * 100
            cap_score = 2 if recent["cap_intensity"].mean() < 15 else (1 if recent["cap_intensity"].mean() < 30 else 0)
            profit_score = 4 if (recent["value"] > 0).all() else 1
            scores["Financial Health"] = min(6, cap_score + profit_score)

    return scores


def _interpolate_color(score: float) -> str:
    if score <= 3:
        return PALETTE["warning"] if score > 2 else PALETTE["negative"]
    return PALETTE["positive"]


def build_snowflake_figure(scores: dict[str, int | None]) -> go.Figure:
    values = [scores.get(axis) for axis in SNOWFLAKE_AXES]
    numeric_values = [v if v is not None else 0 for v in values]
    closed_theta = SNOWFLAKE_AXES + [SNOWFLAKE_AXES[0]]
    closed_vals = numeric_values + [numeric_values[0]]
    available = [v for v in values if v is not None]
    overall = sum(available) / len(available) if available else 0
    fill_color = _interpolate_color(overall)

    fig = go.Figure()
    fig.add_trace(
        go.Scatterpolar(
            r=closed_vals,
            theta=closed_theta,
            fill="toself",
            fillcolor=fill_color,
            line={"color": fill_color, "width": 2},
            opacity=0.5,
            hovertemplate="%{theta}: %{r}/6<extra></extra>",
        )
    )
    fig.update_layout(
        title="Simply Wall St–Style Snowflake",
        polar={
            "bgcolor": "#FFFFFF",
            "radialaxis": {"visible": True, "range": [0, 6], "gridcolor": "#E2E8F0", "tickfont": {"color": PALETTE["body"]}},
            "angularaxis": {"gridcolor": "#E2E8F0", "tickfont": {"color": PALETTE["heading"], "size": 13}},
        },
        showlegend=False,
    )
    apply_figure_theme(fig)
    return fig
