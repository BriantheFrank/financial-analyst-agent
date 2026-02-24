import pytest

pytest.importorskip("plotly")

from ui.theme import PALETTE
from viz.plotly_theme import build_plotly_template


def test_palette_constants_exist():
    expected = {
        "primary_teal",
        "accent_sky",
        "positive",
        "negative",
        "warning",
        "background",
        "surface",
        "heading",
        "body",
    }
    assert expected.issubset(PALETTE.keys())


def test_plotly_template_builds():
    template = build_plotly_template()
    assert template.layout.paper_bgcolor == PALETTE["background"]
