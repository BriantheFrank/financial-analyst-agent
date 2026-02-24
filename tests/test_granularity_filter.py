import pytest

pytest.importorskip("pandas")

import pandas as pd

from viz.transform import filter_df_by_granularity


def test_filter_df_by_granularity_uses_normalized_periods():
    df = pd.DataFrame(
        [
            {"fiscal_period_norm": "FY", "value": 1},
            {"fiscal_period_norm": "Q1", "value": 2},
            {"fiscal_period_norm": "Q4", "value": 3},
            {"fiscal_period_norm": "UNKNOWN", "value": 4},
        ]
    )

    annual = filter_df_by_granularity(df, "annual")
    quarterly = filter_df_by_granularity(df, "quarterly")

    assert set(annual["fiscal_period_norm"]) == {"FY"}
    assert set(quarterly["fiscal_period_norm"]) == {"Q1", "Q4"}
