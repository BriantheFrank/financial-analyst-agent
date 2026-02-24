import pytest

pytest.importorskip("pandas")

from viz.transform import json_to_tidy_df


def test_transform_keeps_rows_with_null_values_when_periods_exist():
    payload = {
        "company": {"name": "Demo"},
        "periods": [
            {
                "fiscal_year": 2024,
                "fiscal_period": "FY2024",
                "period_end": "2024-12-31",
                "revenue": {"value": None, "unit": "USD"},
                "profit_net_income": {"value": 10, "unit": "USD"},
            }
        ],
    }

    df, meta = json_to_tidy_df(payload)

    assert not df.empty
    assert "fiscal_period_raw" in df.columns
    assert "fiscal_period_norm" in df.columns
    assert (df["metric"] == "revenue").any()
    assert meta["missing_data_summary"]["revenue"] >= 1
