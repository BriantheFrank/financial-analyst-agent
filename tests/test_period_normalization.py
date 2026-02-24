import pytest

pytest.importorskip("pandas")

from viz.transform import normalize_fiscal_period


def test_normalize_fiscal_period_variants():
    assert normalize_fiscal_period("FY2025") == "FY"
    assert normalize_fiscal_period("Y") == "FY"
    assert normalize_fiscal_period("Q01") == "Q1"
    assert normalize_fiscal_period("q3") == "Q3"
