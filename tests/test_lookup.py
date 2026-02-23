import unittest
from unittest.mock import MagicMock

from sec_financials import SecClient, resolve_company


class LookupTests(unittest.TestCase):
    def test_ticker_resolution(self):
        client = SecClient(user_agent="test@example.com")
        client.get_json = MagicMock(return_value={
            "0": {"cik_str": 320193, "ticker": "AAPL", "title": "Apple Inc."}
        })
        result = resolve_company(client, "AAPL")
        self.assertEqual(result["cik"], "0000320193")
        self.assertEqual(result["ticker"], "AAPL")


if __name__ == "__main__":
    unittest.main()
