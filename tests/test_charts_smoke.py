import pytest

pytest.importorskip("pandas")
pytest.importorskip("plotly")

import json
from pathlib import Path

from viz.charts import build_all_figures
from viz.transform import json_to_tidy_df


def test_build_all_figures_smoke():
    payload = json.loads(Path("tests/data/sample_out.json").read_text())
    df, meta = json_to_tidy_df(payload)
    meta["period_payloads"] = payload.get("periods", [])
    figs = build_all_figures(df, meta)

    assert figs
    assert all(stem and fig is not None and isinstance(info, dict) for stem, fig, info in figs)


def test_missing_segment_data_does_not_crash():
    payload = json.loads(Path("tests/data/sample_out.json").read_text())
    for p in payload["periods"]:
        p["revenue_by_segment"] = []
    df, meta = json_to_tidy_df(payload)
    meta["period_payloads"] = payload.get("periods", [])

    figs = build_all_figures(df, meta)
    status = {stem: info for stem, _, info in figs}
    assert status["03_revenue_by_segment"]["created"] is False
