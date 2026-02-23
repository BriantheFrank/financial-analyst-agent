import pytest

pytest.importorskip("pandas")
pytest.importorskip("plotly")

import json
from pathlib import Path

from viz.charts import build_all_figures
from viz.transform import json_to_tidy_df


def test_build_all_figures_chart_ids_unique():
    payload = json.loads(Path("tests/data/sample_out.json").read_text())
    df, meta = json_to_tidy_df(payload)
    meta["period_payloads"] = payload.get("periods", [])

    chart_ids = [chart_id for chart_id, _, _ in build_all_figures(df, meta)]
    assert len(chart_ids) == len(set(chart_ids))
