import pytest

pytest.importorskip("pandas")
pytest.importorskip("plotly")

import json
from pathlib import Path

from viz.transform import json_to_tidy_df


def test_json_to_tidy_df_fixture():
    payload = json.loads(Path("tests/data/sample_out.json").read_text())
    df, meta = json_to_tidy_df(payload)

    assert not df.empty
    assert {"period_end", "metric", "segment", "value"}.issubset(df.columns)
    assert meta["company_name"] == "Example Corp"
    assert isinstance(meta["accessions"], list)
