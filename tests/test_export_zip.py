import pytest

pytest.importorskip("pandas")
pytest.importorskip("plotly")

import json
from pathlib import Path
from zipfile import ZipFile

from viz.charts import build_all_figures
from viz.export import export_report_pack
from viz.transform import json_to_tidy_df


def test_export_report_pack_zip_created(tmp_path: Path):
    payload = json.loads(Path("tests/data/sample_out.json").read_text())
    df, meta = json_to_tidy_df(payload)
    meta["period_payloads"] = payload.get("periods", [])
    figures = build_all_figures(df, meta)

    zip_path = export_report_pack(tmp_path, payload, figures, meta)
    assert zip_path.exists()

    with ZipFile(zip_path) as zf:
        names = set(zf.namelist())
        assert "extracted_financials.json" in names
        assert "run_summary.txt" in names
        assert "01_kpi_dashboard.html" in names
        assert "10_data_coverage.html" not in names


def test_export_skips_forecast_when_missing(tmp_path: Path):
    payload = json.loads(Path("tests/data/sample_out.json").read_text())
    payload["periods"][-1]["forecasted_capex"] = []
    df, meta = json_to_tidy_df(payload)
    meta["period_payloads"] = payload.get("periods", [])
    figures = build_all_figures(df, meta)

    zip_path = export_report_pack(tmp_path, payload, figures, meta)
    with ZipFile(zip_path) as zf:
        names = set(zf.namelist())
        assert "09_forecast_capex.html" not in names
        assert "09_forecast_capex.png" not in names
