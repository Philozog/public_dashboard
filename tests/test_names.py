import tempfile
import unittest
from pathlib import Path

from Services import database, names


class CompanyNameTests(unittest.TestCase):
    def test_names_are_looked_up_once_and_failures_left_blank(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "p.db"
            database.initialize_database(path)
            calls = []

            def lookup_any(ticker):
                calls.append(ticker)
                return {"ABCD": "Abcd Corp"}.get(ticker, "")

            first = names.company_names(["abcd", "ZZZZ"], path, lookup_any)
            second = names.company_names(["ABCD", "ZZZZ"], path, lookup_any)
            self.assertEqual(first, {"ABCD": "Abcd Corp", "ZZZZ": ""})
            self.assertEqual(second, first)
            self.assertEqual(sorted(calls), ["ABCD", "ZZZZ"])  # not looked up again soon

    def test_known_names_need_no_lookup(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "p.db"
            database.initialize_database(path)

            def fail(ticker):
                raise AssertionError(f"looked up {ticker}")

            result = names.company_names(["kweb", "TSM", "RKLB"], path, fail)
            self.assertEqual(result["KWEB"], "KraneShares CSI China Internet ETF")
            self.assertEqual(result["TSM"], "Taiwan Semiconductor (TSMC)")
