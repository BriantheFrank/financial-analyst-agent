import pytest

pytest.importorskip("pandas")
pytest.importorskip("plotly")

import json
from pathlib import Path

from viz.charts import build_all_figures, build_revenue_segment_sankey, has_valid_forecast_capex
from viz.transform import json_to_tidy_df


def test_build_all_figures_smoke():
    payload = json.loads(Path("tests/data/sample_out.json").read_text())
    df, meta = json_to_tidy_df(payload)
    meta["period_payloads"] = payload.get("periods", [])
    figs = build_all_figures(df, meta, granularity="quarterly")

    assert figs
    assert all(stem and fig is not None and isinstance(info, dict) for stem, fig, info in figs)


def test_sankey_none_when_segment_missing_for_selected_period():
    payload = json.loads(Path("tests/data/sample_out.json").read_text())
    payload["periods"][-1]["revenue_by_segment"] = []
    df, meta = json_to_tidy_df(payload)

    latest_period = max(df["period_end"])
    fig = build_revenue_segment_sankey(df, meta, selected_period_end=latest_period)
    assert fig is None


def test_sankey_returns_figure_with_data():
    payload = json.loads(Path("tests/data/sample_out.json").read_text())
    df, meta = json_to_tidy_df(payload)

    fig = build_revenue_segment_sankey(df, meta)
    assert fig is not None
    assert fig.data[0]["orientation"] == "h"


def test_forecast_chart_omitted_when_invalid_forecast_data():
    payload = json.loads(Path("tests/data/sample_out.json").read_text())
    payload["periods"][-1]["forecasted_capex"] = [{"value_min": None, "value_max": None, "timeframe": None}]
    df, meta = json_to_tidy_df(payload)
    meta["period_payloads"] = payload.get("periods", [])

    assert has_valid_forecast_capex(meta) is False
    stems = [s for s, _, _ in build_all_figures(df, meta)]
    assert "09_forecast_capex" not in stems
