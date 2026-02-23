import unittest

from sec_financials import collect_filings


class FilingTests(unittest.TestCase):
    def test_collect_filings(self):
        submissions = {
            "filings": {
                "recent": {
                    "form": ["10-K", "8-K", "10-Q"],
                    "filingDate": ["2024-11-01", "2024-10-01", "2024-08-01"],
                    "reportDate": ["2024-09-28", "2024-10-01", "2024-06-29"],
                    "accessionNumber": ["1", "2", "3"],
                    "primaryDocument": ["a.htm", "b.htm", "c.htm"],
                    "fy": [2024, 2024, 2024],
                    "fp": ["FY", "", "Q3"],
                }
            }
        }
        filings = collect_filings(submissions, years=5)
        self.assertEqual(len(filings), 2)
        self.assertEqual({f.form for f in filings}, {"10-K", "10-Q"})


if __name__ == "__main__":
    unittest.main()
