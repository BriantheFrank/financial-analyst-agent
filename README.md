# SEC EDGAR Financial Extractor

Production-style Python tool to extract Revenue, Net Income (profit), CAPEX, segment breakdowns, and conservative forward-looking CAPEX guidance from SEC EDGAR filings.

## Setup

```bash
python -m venv .venv
source .venv/bin/activate
pip install requests lxml jsonschema
```

## SEC User-Agent configuration (required)

SEC requires descriptive identification headers.

```bash
export SEC_USER_AGENT="Your Name your.email@example.com"
```

You can also pass `--user-agent` directly.

## Run

```bash
python cli.py --company "AAPL" --years 5 --out out.json
```

Output is deterministic JSON (`sort_keys=True`) and can be validated with:

```bash
python - <<'PY'
import json
from jsonschema import validate
schema=json.load(open('schemas/financials.schema.json'))
data=json.load(open('out.json'))
validate(data,schema)
print('valid')
PY
```

## What is extracted

- Revenue (XBRL tags in priority order)
- Profit as `NetIncomeLoss`
- CAPEX as `PaymentsToAcquirePropertyPlantAndEquipment` (fallback to `CapitalExpenditures`)
- Segment breakdowns from XBRL dimensions (`explicitMember` contexts)
- Forecasted CAPEX from narrative text only when explicitly forward-looking

Every numeric field includes provenance (filing type, accession, filing date, source reference, unit).

## Caching and rate limiting

- Disk cache: `.cache/sec/`
- Throttling: default ~3 requests/sec (safe SEC fair access posture)

## Limitations

- Segment availability is issuer-dependent; if dimensional facts do not exist, fields are empty and `missing_data` explains why.
- Forecast CAPEX guidance varies widely in disclosure style; extractor is intentionally conservative and returns empty arrays unless language is clearly forward-looking.
- Quarter-only conversion from YTD is only attempted when safely inferable; otherwise value is left as available with explanatory notes/missing reasons.
