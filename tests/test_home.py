"""Home page numbers and alerts, with synthetic prices."""

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import pandas as pd

from Services import database, home_summary, settings
from Services.insights import prepare_holdings


def holdings_frame(rows, stamp="2026-11-16T21:00:00+00:00"):
    raw = pd.DataFrame(
        [
            {
                "ticker": t,
                "shares": sh,
                "avg_price": cost,
                "current_price": px,
                "market_value": sh * px,
                "Total_Profit_Loss": (px - cost) * sh,
                "holding_type": kind,
                "quote_updated_at": stamp,
            }
            for t, sh, cost, px, kind in rows
        ]
    )
    return raw, prepare_holdings(raw)


class HomeSummaryTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        path = Path(tmp.name) / "p.db"
        database.initialize_database(path)
        patcher = patch.object(database, "DB_PATH", path)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.now = pd.Timestamp("2026-11-17T15:00:00Z")

    def prices(self):
        index = pd.to_datetime(["2025-12-31", "2026-01-02", "2026-11-13", "2026-11-16"])
        return pd.DataFrame(
            {
                "AAA": [8.0, 10.0, 10.0, 11.0],
                "BBB": [20.0, 20.0, 20.0, 19.0],
                "SPY": [500, 500, 600, 606],
            },
            index=index,
        )

    def test_glance_changes_movers_and_benchmark(self):
        _, holdings = holdings_frame([("AAA", 10, 10, 11, "Core"), ("BBB", 5, 20, 19, "Core")])
        data = home_summary.glance(holdings, self.prices(), self.now)
        self.assertAlmostEqual(data["value"], 205)
        # 10 x (11-10) + 5 x (19-20) = +5 on a base of 200.
        self.assertAlmostEqual(data["day_change"], 5)
        self.assertAlmostEqual(data["day_pct"], 0.025)
        # Since the first trading day of 2026: 205 / 200 - 1.
        self.assertAlmostEqual(data["ytd_pct"], 0.025)
        self.assertAlmostEqual(data["spy_day_pct"], 0.01)
        self.assertAlmostEqual(data["spy_ytd_pct"], 606 / 500 - 1)
        self.assertEqual([t for t, _ in data["movers"]], ["AAA", "BBB"])
        # Only the last 6 months are drawn: 13 and 16 November.
        self.assertEqual(len(data["spark"]), 2)

    def test_last_update_comes_from_raw_rows(self):
        raw, holdings = holdings_frame([("AAA", 1, 10, 10, "Core")])
        data = home_summary.glance(holdings, pd.DataFrame(), self.now, raw_holdings=raw)
        self.assertEqual(data["updated"], pd.Timestamp("2026-11-16T21:00:00Z"))

    def test_glance_without_prices_or_holdings(self):
        _, holdings = holdings_frame([("AAA", 1, 10, 10, "Core")])
        data = home_summary.glance(holdings, pd.DataFrame(), self.now)
        self.assertIsNone(data["day_change"])
        self.assertEqual(data["movers"], [])
        self.assertEqual(home_summary.glance(holdings.iloc[0:0], pd.DataFrame())["value"], 0)

    def test_alerts_concentration_drift_moves_and_stale(self):
        settings.save_settings({"Core": 60, "High Conviction": 30, "Moonshot": 10}, 25, 5, 0.04)
        raw, holdings = holdings_frame(
            [("AAA", 10, 10, 11, "Core"), ("BBB", 5, 20, 19, "Moonshot")],
            stamp=None,
        )
        items = home_summary.alerts(holdings, raw, [("AAA", 0.10), ("BBB", -0.01)], self.now)
        text = " | ".join(t for _, t in items)
        self.assertIn("AAA is 54% of your portfolio, above your 25% limit", text)
        self.assertIn("High Conviction is 30 points below its 30% target", text)
        self.assertIn("AAA moved +10.0%", text)
        self.assertNotIn("BBB moved", text)
        self.assertIn("No recent price for AAA, BBB", text)

    def test_no_alerts_when_balanced_and_fresh(self):
        settings.save_settings({"Core": 60, "High Conviction": 30, "Moonshot": 10}, 70, 5, 0.04)
        raw, holdings = holdings_frame(
            [
                ("A", 60, 1, 1, "Core"),
                ("B", 30, 1, 1, "High Conviction"),
                ("C", 10, 1, 1, "Moonshot"),
            ],
            stamp="2026-11-17T14:00:00+00:00",
        )
        self.assertEqual(home_summary.alerts(holdings, raw, [], self.now), [])

    def test_time_ago(self):
        now = pd.Timestamp("2026-11-17T15:00:00Z").to_pydatetime()
        self.assertEqual(home_summary.time_ago(None, now), "never")
        self.assertEqual(home_summary.time_ago(now - pd.Timedelta(minutes=5), now), "5 min ago")
        self.assertEqual(home_summary.time_ago(now - pd.Timedelta(hours=3), now), "3 h ago")
        self.assertEqual(home_summary.time_ago(now - pd.Timedelta(days=3), now), "3 days ago")
