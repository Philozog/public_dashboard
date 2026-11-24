"""Company names for tickers, looked up once from Yahoo Finance and remembered."""

import logging
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone

import yfinance as yf

from Services.database import connect

LOG = logging.getLogger(__name__)
RETRY_AFTER = timedelta(hours=6)  # a failed lookup is retried a few times a day

# Common stocks and ETFs, so their names show even when Yahoo limits requests.
KNOWN_NAMES = {
    "AAPL": "Apple",
    "ABBV": "AbbVie",
    "ADBE": "Adobe",
    "AMD": "Advanced Micro Devices",
    "AMZN": "Amazon.com",
    "ARM": "Arm Holdings",
    "ASML": "ASML Holding",
    "AVGO": "Broadcom",
    "BA": "Boeing",
    "BABA": "Alibaba Group",
    "BAC": "Bank of America",
    "BIDU": "Baidu",
    "BRK-B": "Berkshire Hathaway (Class B)",
    "C": "Citigroup",
    "CEG": "Constellation Energy",
    "CLF": "Cleveland-Cliffs",
    "COIN": "Coinbase",
    "COST": "Costco",
    "CRM": "Salesforce",
    "CSCO": "Cisco Systems",
    "CVX": "Chevron",
    "DIA": "SPDR Dow Jones Industrial Average ETF",
    "DIS": "Walt Disney",
    "EXE": "Expand Energy",
    "F": "Ford Motor",
    "GLD": "SPDR Gold Shares",
    "GM": "General Motors",
    "GOOG": "Alphabet (Class C)",
    "GOOGL": "Alphabet (Class A)",
    "GS": "Goldman Sachs",
    "HD": "Home Depot",
    "IBM": "IBM",
    "INTC": "Intel",
    "IWM": "iShares Russell 2000 ETF",
    "JNJ": "Johnson & Johnson",
    "JPM": "JPMorgan Chase",
    "KO": "Coca-Cola",
    "KWEB": "KraneShares CSI China Internet ETF",
    "LLY": "Eli Lilly",
    "MA": "Mastercard",
    "MCD": "McDonald's",
    "META": "Meta Platforms",
    "MRK": "Merck",
    "MS": "Morgan Stanley",
    "MSFT": "Microsoft",
    "MU": "Micron Technology",
    "NFLX": "Netflix",
    "NKE": "Nike",
    "NOK": "Nokia",
    "NVDA": "NVIDIA",
    "ORCL": "Oracle",
    "PEP": "PepsiCo",
    "PFE": "Pfizer",
    "PLTR": "Palantir",
    "PYPL": "PayPal",
    "QCOM": "Qualcomm",
    "QQQ": "Invesco QQQ (Nasdaq-100)",
    "RKLB": "Rocket Lab",
    "SBUX": "Starbucks",
    "SHOP": "Shopify",
    "SMCI": "Super Micro Computer",
    "SOFI": "SoFi Technologies",
    "SPY": "SPDR S&P 500 ETF",
    "T": "AT&T",
    "TSLA": "Tesla",
    "TSM": "Taiwan Semiconductor (TSMC)",
    "UBER": "Uber",
    "UNH": "UnitedHealth",
    "V": "Visa",
    "VOO": "Vanguard S&P 500 ETF",
    "VT": "Vanguard Total World Stock ETF",
    "VTI": "Vanguard Total Stock Market ETF",
    "VZ": "Verizon",
    "WFC": "Wells Fargo",
    "WMT": "Walmart",
    "XOM": "Exxon Mobil",
}


def _lookup(ticker):
    """Yahoo's search endpoint first (lighter, rarely limited), then the quote summary."""
    try:
        for quote in yf.Search(ticker, max_results=5, news_count=0, timeout=10).quotes:
            if str(quote.get("symbol", "")).upper() == ticker:
                name = quote.get("shortname") or quote.get("longname")
                if name:
                    return str(name).strip()
    except Exception:
        LOG.warning("Company name search failed for %s", ticker)
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
    known = {t: KNOWN_NAMES[t] for t in tickers if t in KNOWN_NAMES}
    tickers = [t for t in tickers if t not in known]
    if not tickers:
        return known
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
    return {**known, **{t: rows[t][0] for t in tickers}}
