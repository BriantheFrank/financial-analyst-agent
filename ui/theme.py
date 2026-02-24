from __future__ import annotations

PALETTE = {
    "primary_teal": "#14B8A6",
    "accent_sky": "#0EA5E9",
    "positive": "#22C55E",
    "negative": "#EF4444",
    "warning": "#F59E0B",
    "background": "#F8FAFC",
    "surface": "#FFFFFF",
    "heading": "#0F172A",
    "body": "#64748B",
}

FONT_FAMILY = "Inter, system-ui, -apple-system, Segoe UI, Roboto, Arial"


def build_app_css() -> str:
    return f"""
    <style>
    .stApp {{
        background-color: {PALETTE['background']};
        color: {PALETTE['heading']};
        font-family: {FONT_FAMILY};
    }}
    .block-container {{
        padding-top: 1.5rem;
        padding-bottom: 1.5rem;
        max-width: 1400px;
    }}
    h1, h2, h3 {{
        color: {PALETTE['heading']};
        letter-spacing: -0.01em;
        margin-bottom: 0.35rem;
    }}
    p, span, label, .stCaption {{
        color: {PALETTE['body']};
    }}
    [data-testid='stMetric'] {{
        background: {PALETTE['surface']};
        border: 1px solid #E2E8F0;
        border-radius: 14px;
        box-shadow: 0 2px 12px rgba(15, 23, 42, 0.06);
        padding: 0.65rem 0.8rem;
    }}
    .ui-card {{
        background: {PALETTE['surface']};
        border-radius: 14px;
        border: 1px solid #E2E8F0;
        box-shadow: 0 8px 26px rgba(15, 23, 42, 0.06);
        padding: 1rem 1.1rem;
        margin-bottom: 1rem;
    }}
    .status-pill {{
        display: inline-block;
        padding: 0.25rem 0.65rem;
        border-radius: 999px;
        font-weight: 600;
        font-size: 0.8rem;
        color: {PALETTE['surface']};
    }}
    </style>
    """
