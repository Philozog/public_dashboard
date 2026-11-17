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

            def lookup(ticker):
                calls.append(ticker)
                return {"AAPL": "Apple Inc."}.get(ticker, "")

            first = names.company_names(["aapl", "ZZZZ"], path, lookup)
            second = names.company_names(["AAPL", "ZZZZ"], path, lookup)
            self.assertEqual(first, {"AAPL": "Apple Inc.", "ZZZZ": ""})
            self.assertEqual(second, first)
            self.assertEqual(sorted(calls), ["AAPL", "ZZZZ"])  # no second lookup within a day
