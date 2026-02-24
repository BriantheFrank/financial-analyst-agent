import unittest
from unittest.mock import MagicMock

from sec_financials import Filing, SecClient, build_financials, extract_segment_metrics


class XbrlSegmentTests(unittest.TestCase):
    def test_extract_segment_metrics(self):
        client = SecClient(user_agent="test@example.com")
        client.get_json = MagicMock(return_value={
            "directory": {"item": [{"name": "inst.xml"}]}
        })
        xml = """<?xml version='1.0'?>
        <xbrli:xbrl xmlns:xbrli='http://www.xbrl.org/2003/instance' xmlns:xbrldi='http://xbrl.org/2006/xbrldi' xmlns:us-gaap='http://fasb.org/us-gaap/2023'>
          <xbrli:context id='C1'>
            <xbrli:entity>
              <xbrli:identifier scheme='x'>x</xbrli:identifier>
              <xbrli:segment>
                <xbrldi:explicitMember dimension='us-gaap:StatementBusinessSegmentsAxis'>us-gaap:ServicesMember</xbrldi:explicitMember>
              </xbrli:segment>
            </xbrli:entity>
            <xbrli:period><xbrli:endDate>2024-09-28</xbrli:endDate></xbrli:period>
          </xbrli:context>
          <us-gaap:Revenues contextRef='C1'>100</us-gaap:Revenues>
        </xbrli:xbrl>
        """
        client.get_text = MagicMock(return_value=xml)
        filing = Filing("10-K", "2024-11-01", "2024-09-28", "0001-01-000001", "a.htm", 2024, "FY")
        out, missing = extract_segment_metrics(client, "0000320193", filing)
        self.assertEqual(len(out["revenue_by_segment"]), 1)
        self.assertEqual(out["revenue_by_segment"][0]["segment"], "ServicesMember")
        self.assertTrue(any(m["field"] == "profit_by_segment" for m in missing))

    def test_full_mode_keeps_segment_extraction(self):
        from unittest.mock import patch

        filing = Filing("10-Q", "2024-08-01", "2024-06-29", "0001-01-000001", "a.htm", 2024, "Q2")
        with patch("sec_financials.resolve_company", return_value={"cik": "0000320193", "name": "Apple", "ticker": "AAPL"}), \
             patch("sec_financials.get_submissions", return_value={}), \
             patch("sec_financials.collect_filings", return_value=[filing]), \
             patch("sec_financials.get_companyfacts", return_value={"facts": {"us-gaap": {}}}), \
             patch("sec_financials.extract_primary_metrics", return_value=({"revenue": None, "profit_net_income": None, "capex": None}, [], [])), \
             patch("sec_financials.extract_segment_metrics", return_value=({"revenue_by_segment": [{"segment": "ServicesMember", "value": 1.0}], "profit_by_segment": [], "capex_by_segment": []}, [])), \
             patch("sec_financials.extract_forecasted_capex", return_value=([], [])):
            out = build_financials("AAPL", 5, "ua@example.com", segments_mode="full", max_quarters=8)
        self.assertEqual(len(out["periods"][0]["revenue_by_segment"]), 1)


if __name__ == "__main__":
    unittest.main()
