import json
import unittest


class SchemaValidationTests(unittest.TestCase):
    @unittest.skipUnless(__import__('importlib').util.find_spec('jsonschema') is not None, 'jsonschema not installed')
    def test_schema_accepts_sample(self):
        from jsonschema import validate

        schema = json.loads(open("schemas/financials.schema.json").read())
        sample = {
            "company": {"input": "AAPL", "cik": "0000320193", "name": "Apple Inc.", "ticker": "AAPL"},
            "generated_at_utc": "2025-01-01T00:00:00Z",
            "periods": [{
                "fiscal_year": 2024, "fiscal_period": "FY", "period_start": None, "period_end": "2024-09-28",
                "filing": {"form": "10-K", "filing_date": "2024-11-01", "accession": "0000-00-000000", "primary_doc": "a.htm"},
                "revenue": None, "revenue_by_segment": [], "profit_net_income": None, "profit_by_segment": [],
                "capex": None, "capex_by_segment": [], "forecasted_capex": [], "forecasted_capex_by_segment": [],
                "notes": [], "missing_data": [{"field": "revenue", "reason": "missing"}]
            }]
        }
        validate(instance=sample, schema=schema)


if __name__ == "__main__":
    unittest.main()
