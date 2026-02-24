import json
from pathlib import Path

import pytest

pytest.importorskip("matplotlib")
pytest.importorskip("pandas")
pytest.importorskip("numpy")
pytest.importorskip("plotly")

from viz.reporting import CHART_ORDER, ReportGenerator, load_payload


def test_chart_outputs_created(tmp_path: Path):
    payload = load_payload(Path("tests/data/sample_out.json"))
    outdir = tmp_path / "report"
    rg = ReportGenerator(payload, outdir, ["png"])
    results = rg.generate()

    created = {r.name for r in results if r.generated}
    assert "01_kpi_dashboard" in created
    assert (outdir / "01_kpi_dashboard.png").exists()
    assert (outdir / "07_revenue_segment_sankey.png").exists()


def test_deterministic_order(tmp_path: Path):
    payload = load_payload(Path("tests/data/sample_out.json"))
    rg = ReportGenerator(payload, tmp_path / "r", ["png"])
    results = rg.generate()
    assert [r.name for r in results] == [name for name, _ in CHART_ORDER]


def test_missing_segment_graceful_skip(tmp_path: Path):
    payload = json.loads(Path("tests/data/sample_out.json").read_text())
    for p in payload["periods"]:
        p["revenue_by_segment"] = []
    rg = ReportGenerator(payload, tmp_path / "r2", ["png"])
    results = {r.name: r for r in rg.generate()}
    assert not results["07_revenue_segment_sankey"].generated
    assert "available" in results["07_revenue_segment_sankey"].reason.lower()
