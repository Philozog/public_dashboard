import unittest

from Services.importer import parse_positions


class ImporterTests(unittest.TestCase):
    def test_yahoo_finance_export_combines_lots(self):
        csv = (
            "Symbol,Current Price,Date,Time,Change,Open,High,Low,Volume,Trade Date,Purchase Price,Quantity,Commission\n"
            "AAPL,230,2026/11/17,16:00 EST,1,229,231,228,100,20240105,150,10,0\n"
            "AAPL,230,2026/11/17,16:00 EST,1,229,231,228,100,20240605,200,10,0\n"
            "KWEB,22,2026/11/17,16:00 EST,0,22,22,22,100,20250101,25,759,0\n"
        )
        positions, notes = parse_positions(csv.encode())
        self.assertEqual(
            positions,
            [
                {"ticker": "AAPL", "shares": 20, "avg_cost": 175},
                {"ticker": "KWEB", "shares": 759, "avg_cost": 25},
            ],
        )
        self.assertEqual(notes, [])

    def test_fidelity_style_with_preamble_money_and_cash_rows(self):
        csv = (
            "Brokerage account X12345\n\n"
            "Account Number,Symbol,Description,Quantity,Last Price,Current Value,Cost Basis Total,Average Cost Basis\n"
            'X12345,SPAXX**,MONEY MARKET,"1,000.00",$1.00,"$1,000.00",,\n'
            'X12345,MSFT,MICROSOFT CORP,"5","$420.00","$2,100.00","$1,500.00",$300.00\n'
            'X12345,NVDA,NVIDIA CORP,"2","$140.00","$280.00","$200.00",\n'
            '"The data and information in this spreadsheet is provided to you solely..."\n'
        )
        positions, notes = parse_positions(csv.encode())
        self.assertEqual(
            positions,
            [
                {"ticker": "MSFT", "shares": 5, "avg_cost": 300},
                {"ticker": "NVDA", "shares": 2, "avg_cost": 100},  # from total cost basis
            ],
        )
        self.assertTrue(any("SPAXX" in n for n in notes))

    def test_unreadable_file_says_why(self):
        with self.assertRaisesRegex(ValueError, "Symbol and Quantity"):
            parse_positions(b"name,amount\nfoo,1\n")
        with self.assertRaisesRegex(ValueError, "cost column"):
            parse_positions(b"Symbol,Quantity\nAAPL,1\n")

    def test_accepts_dash_upload_string(self):
        import base64

        data = (
            "data:text/csv;base64,"
            + base64.b64encode(b"Ticker,Shares,Avg Cost\nGOOG,3,100\n").decode()
        )
        self.assertEqual(
            parse_positions(data)[0], [{"ticker": "GOOG", "shares": 3, "avg_cost": 100}]
        )
