from __future__ import annotations

import plotly.graph_objects as go
import plotly.io as pio

from ui.theme import FONT_FAMILY, PALETTE


def build_plotly_template() -> go.layout.Template:
    return go.layout.Template(
        layout={
            "paper_bgcolor": PALETTE["background"],
            "plot_bgcolor": PALETTE["surface"],
            "font": {"family": FONT_FAMILY, "color": PALETTE["body"]},
            "title": {"font": {"color": PALETTE["heading"], "size": 20}},
            "xaxis": {"gridcolor": "#E2E8F0", "linecolor": "#E2E8F0", "zerolinecolor": "#E2E8F0", "tickfont": {"color": PALETTE["body"]}},
            "yaxis": {"gridcolor": "#E2E8F0", "linecolor": "#E2E8F0", "zerolinecolor": "#E2E8F0", "tickfont": {"color": PALETTE["body"]}},
            "hoverlabel": {"bgcolor": "#FFFFFF", "font": {"family": FONT_FAMILY, "color": PALETTE["heading"]}},
            "colorway": [
                PALETTE["primary_teal"],
                PALETTE["accent_sky"],
                PALETTE["positive"],
                PALETTE["warning"],
                PALETTE["negative"],
            ],
        }
    )


def register_plotly_template() -> str:
    name = "simply_wall"
    pio.templates[name] = build_plotly_template()
    return name


def apply_figure_theme(fig: go.Figure) -> go.Figure:
    fig.update_layout(template=register_plotly_template())
    return fig
