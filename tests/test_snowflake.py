import pytest

pytest.importorskip("pandas")
pytest.importorskip("plotly")

import json
from pathlib import Path

from ui.snowflake import SNOWFLAKE_AXES, compute_snowflake_scores
from viz.transform import json_to_tidy_df


def test_compute_snowflake_scores_range_or_none():
    payload = json.loads(Path("tests/data/sample_out.json").read_text())
    df, meta = json_to_tidy_df(payload)
    scores = compute_snowflake_scores(df, meta, "quarterly")

    assert set(scores.keys()) == set(SNOWFLAKE_AXES)
    assert all((value is None) or (0 <= value <= 6) for value in scores.values())
