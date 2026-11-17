"""Company names for tickers, looked up once from Yahoo Finance and remembered."""

import logging
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone

import yfinance as yf

from Services.database import connect

LOG = logging.getLogger(__name__)
RETRY_AFTER = timedelta(days=1)  # a failed lookup is retried at most once a day


def _lookup(ticker):
    try:
        info = yf.Ticker(ticker).get_info()
    except Exception:  # network, rate limit or unknown symbol
        LOG.warning("Company name lookup failed for %s", ticker)
        return ""
    return (info.get("shortName") or info.get("longName") or "").strip()


def company_names(tickers, path=None, lookup=_lookup):
    """{ticker: name}; unknown names come back as an empty string."""
    tickers = sorted({str(t).strip().upper() for t in tickers if str(t).strip()})
    if not tickers:
        return {}
    now = datetime.now(timezone.utc)
    with connect(path) as conn:
        conn.execute(
            "CREATE TABLE IF NOT EXISTS ticker_names "
            "(ticker TEXT PRIMARY KEY, name TEXT NOT NULL DEFAULT '', checked_at TEXT NOT NULL)"
        )
        rows = {
            r["ticker"]: (r["name"], r["checked_at"])
            for r in conn.execute(
                f"SELECT * FROM ticker_names WHERE ticker IN ({','.join('?' * len(tickers))})",
                tickers,
            )
        }
    missing = [
        t
        for t in tickers
        if t not in rows
        or (not rows[t][0] and now - datetime.fromisoformat(rows[t][1]) > RETRY_AFTER)
    ]
    if missing:
        # Lookups are slow (about a second each), so do several at once, outside the database.
        with ThreadPoolExecutor(max_workers=min(8, len(missing))) as pool:
            found = dict(zip(missing, pool.map(lookup, missing)))
        with connect(path) as conn:
            conn.executemany(
                "INSERT INTO ticker_names(ticker,name,checked_at) VALUES(?,?,?) "
                "ON CONFLICT(ticker) DO UPDATE SET name=excluded.name, checked_at=excluded.checked_at",
                [(t, n, now.isoformat()) for t, n in found.items()],
            )
        rows.update({t: (n, now.isoformat()) for t, n in found.items()})
    return {t: rows[t][0] for t in tickers}
