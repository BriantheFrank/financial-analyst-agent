import unittest
from unittest.mock import MagicMock

from sec_financials import Filing, SecClient, extract_segment_metrics


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


if __name__ == "__main__":
    unittest.main()
