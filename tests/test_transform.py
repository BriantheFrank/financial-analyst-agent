import pytest

pytest.importorskip("pandas")
pytest.importorskip("plotly")

import json
from pathlib import Path

from viz.transform import filter_df_by_granularity, json_to_tidy_df


def test_json_to_tidy_df_fixture():
    payload = json.loads(Path("tests/data/sample_out.json").read_text())
    df, meta = json_to_tidy_df(payload)

    assert not df.empty
    assert {"period_end", "metric", "segment", "value", "period_type", "period_label"}.issubset(df.columns)
    assert meta["company_name"] == "Example Corp"
    assert isinstance(meta["accessions"], list)


def test_granularity_filter_excludes_period_types():
    payload = {
        "company": {"name": "X"},
        "periods": [
            {"fiscal_year": 2024, "fiscal_period": "Q4", "period_end": "2024-12-31", "revenue": {"value": 10}},
            {"fiscal_year": 2024, "fiscal_period": "FY", "period_end": "2024-12-31", "revenue": {"value": 40}},
        ],
    }
    df, _ = json_to_tidy_df(payload)
    q = filter_df_by_granularity(df, "quarterly")
    a = filter_df_by_granularity(df, "annual")

    assert set(q["fiscal_period"].unique()) == {"Q4"}
    assert set(a["fiscal_period"].unique()) == {"FY"}
