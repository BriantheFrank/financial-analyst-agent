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

## One-click Windows launch

1. Download this repository as a ZIP from GitHub and unzip it.
2. Open the extracted folder and double-click `Run-Agent.cmd`.
3. On first run, the launcher will:
   - create `.venv`,
   - install dependencies,
   - prompt for `SEC_USER_AGENT` and save it to `.env`.
4. The Streamlit app launches at: <http://localhost:8501>

### Troubleshooting (Windows launcher)

- **Python not installed**: install Python 3 from <https://www.python.org/downloads/windows/> and re-run `Run-Agent.cmd`.
- **Port 8501 already in use**: run `Run-Agent.cmd --port 8502`.
- **Force dependency refresh**: run `Run-Agent.cmd --reinstall`.

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

## New Premium UI

The Streamlit app now includes a premium Simply Wall St–style interface with themed cards, KPI overview, a 5-axis snowflake radar, and streamlined deep-dive tabs.

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
- premium card-based layout + snowflake visualization,
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

If required data is unavailable, the chart is marked with "Data unavailable" and remaining charts still render.

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
- If you see `streamlit.errors.StreamlitDuplicateElementId`, upgrade to the latest version of this repo. The UI now assigns explicit, stable keys for every Plotly chart instance across tabs/sections.
