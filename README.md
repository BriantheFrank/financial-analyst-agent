# SEC EDGAR Financial Extractor + Sell-Side Visualization Report

This repository includes:
1. The SEC EDGAR financial extractor (`sec_financials.py`, `cli.py`),
2. A publication-style report generator (`report.py`, `viz/`) that turns extractor JSON into chart packs, and
3. A local Streamlit UI (`app.py`) for interactive demo/screen-sharing workflows.

## Install

```bash
python -m venv .venv
source .venv/bin/activate
pip install requests lxml jsonschema pandas numpy matplotlib plotly kaleido streamlit pytest
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

## Run the UI (local only)

```bash
export SEC_USER_AGENT="Your Name your.email@example.com"
streamlit run app.py
```

Windows PowerShell one-click launcher:

```powershell
./run_app.ps1
```

The UI includes:
- sidebar controls for company/years/cache preference,
- interactive Plotly charts (hover/zoom/legend),
- data coverage + accession details,
- downloads for extractor JSON and a report ZIP pack (HTML + PNG + JSON + summary).

## Output chart set

The pipeline deterministically attempts the following chart sequence:

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

If required data is unavailable, the chart is marked with "Data unavailable" and remaining charts still render.

## Tests

```bash
pytest -q
```
