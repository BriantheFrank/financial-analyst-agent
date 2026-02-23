# SEC EDGAR Financial Extractor + Sell-Side Visualization Report

This repository includes:
1. The SEC EDGAR financial extractor (`sec_financials.py`, `cli.py`), and
2. A publication-style report generator (`report.py`, `viz/`) that turns extractor JSON into chart packs.

## Install

```bash
python -m venv .venv
source .venv/bin/activate
pip install requests lxml jsonschema pandas numpy matplotlib plotly kaleido pytest
```

## Generate extractor JSON

```bash
export SEC_USER_AGENT="Your Name your.email@example.com"
python cli.py --company "AAPL" --years 5 --out out.json
```

## Generate sell-side style chart report

```bash
python report.py --in out.json --outdir reports/AAPL --format png html
```

`--format` accepts one or both of: `png` `html`.

## Output chart set

The CLI deterministically attempts the following chart sequence:

- `01_kpi_dashboard.(png|html)`
- `02_revenue_trend.(png|html)`
- `03_revenue_by_segment.(png|html)`
- `04_profit_and_margin.(png|html)`
- `05_capex_trend.(png|html)`
- `06_capex_intensity.(png|html)`
- `07_snapshot_revenue_mix_latest_q.(png|html)`
- `08_waterfall_revenue_yoy_change.(png|html)` (if sufficient YoY segment history)
- `09_forecast_capex.(png|html)` (if forecast guidance exists)
- `10_data_coverage.(png|html)`

If required data is unavailable, the chart is skipped and the CLI prints a reason.

## Design notes

- Sell-side conventions: trend lines for growth, bars for discrete quarterly values, stacked area for segment mix, heatmap for coverage.
- Stable segment coloring: segment names are hash-mapped to a fixed palette index.
- Raw values are preserved; display unit (`$`, `$M`, `$B`) is selected transparently and labeled in chart footnotes.
- Every chart includes source/provenance footnotes: filing accession list and `Source: SEC filings (XBRL)`.

## Tests

```bash
pytest -q
```

Tests validate:
- deterministic chart ordering,
- expected file creation,
- graceful handling of missing segment datasets.

## Troubleshooting

- If you see `UnicodeDecodeError` mentioning byte `0x8b`, clear `.cache/sec` and ensure you're on the latest version. The SEC client now auto-decompresses `gzip`/`deflate` responses (including older cached gzip payloads).
