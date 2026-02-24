import pytest

pytest.importorskip("pandas")
pytest.importorskip("plotly")

import json
from pathlib import Path

import plotly.graph_objects as go

from ui.snowflake import build_snowflake_figure, compute_snowflake_scores
from viz.charts import build_all_figures
from viz.transform import json_to_tidy_df


def test_figures_build_without_error():
    payload = json.loads(Path("tests/data/sample_out.json").read_text())
    df, meta = json_to_tidy_df(payload)
    meta["period_payloads"] = payload.get("periods", [])

    figures = build_all_figures(df, meta, granularity="quarterly")
    assert figures
    assert all(isinstance(fig, go.Figure) for _, fig, _ in figures)

    scores = compute_snowflake_scores(df, meta, "quarterly")
    snowflake = build_snowflake_figure(scores)
    assert isinstance(snowflake, go.Figure)
