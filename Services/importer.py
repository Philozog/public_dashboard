"""Read holdings from a broker or Yahoo Finance CSV export."""

import base64
import csv
import io
import re

# Column names seen in common exports, compared lower-case without punctuation.
TICKER_COLUMNS = ("symbol", "ticker", "instrument", "security symbol")
SHARES_COLUMNS = ("quantity", "shares", "qty", "qty quantity", "position", "units")
PRICE_COLUMNS = (  # cost per share
    "purchase price",  # Yahoo Finance
    "average cost basis",  # Fidelity
    "average cost",
    "avg cost",
    "cost price",
    "price paid",
    "cost basis per share",
    "cost per share",
    "average price",
)
TOTAL_COST_COLUMNS = ("cost basis", "cost basis total", "total cost", "cost basis total amount")
TICKER = re.compile(r"[A-Z0-9^][A-Z0-9.^=\-]{0,24}")


def _key(name):
    return re.sub(r"[^a-z ]", "", str(name).lower()).strip()


def _number(value):
    text = str(value or "").replace("$", "").replace(",", "").replace("+", "").strip()
    if text.startswith("(") and text.endswith(")"):
        text = "-" + text[1:-1]
    try:
        return float(text)
    except ValueError:
        return None


def _find(header, names):
    keys = [_key(h) for h in header]
    for name in names:
        if name in keys:
            return keys.index(name)
    return None


def parse_positions(contents):
    """contents: dcc.Upload's "data:...;base64,..." string or raw bytes.

    Returns (positions, notes). positions is a list of
    {"ticker", "shares", "avg_cost"}, lots of the same ticker combined at
    their weighted average cost. notes explains anything skipped.
    """
    if isinstance(contents, str):
        contents = base64.b64decode(contents.split(",", 1)[-1])
    text = contents.decode("utf-8-sig", errors="replace")
    rows = list(csv.reader(io.StringIO(text)))

    # Brokers often put account details above the real header; find the header row.
    start = next(
        (
            i
            for i, row in enumerate(rows[:30])
            if _find(row, TICKER_COLUMNS) is not None and _find(row, SHARES_COLUMNS) is not None
        ),
        None,
    )
    if start is None:
        raise ValueError(
            "Couldn't find Symbol and Quantity columns. Export positions as a CSV file "
            "from Yahoo Finance or your broker."
        )
    header = rows[start]
    col_ticker, col_shares = _find(header, TICKER_COLUMNS), _find(header, SHARES_COLUMNS)
    col_price, col_total = _find(header, PRICE_COLUMNS), _find(header, TOTAL_COST_COLUMNS)
    if col_price is None and col_total is None:
        raise ValueError("Couldn't find a cost column (such as Purchase Price or Cost Basis).")

    combined, notes = {}, []
    for row in rows[start + 1 :]:
        if len(row) <= max(col_ticker, col_shares):
            continue
        ticker = row[col_ticker].strip().upper().replace("*", "")
        shares = _number(row[col_shares])
        if not ticker or shares is None:
            continue
        if not TICKER.fullmatch(ticker) or " " in ticker:
            notes.append(f"Skipped {ticker[:20]!r} (not a ticker).")
            continue
        if shares <= 0:
            notes.append(f"Skipped {ticker}: quantity is {shares:g}.")
            continue
        cost = _number(row[col_price]) if col_price is not None and col_price < len(row) else None
        if (cost is None or cost <= 0) and col_total is not None and col_total < len(row):
            total = _number(row[col_total])
            cost = total / shares if total and total > 0 else None
        if cost is None or cost <= 0:
            notes.append(f"Skipped {ticker}: no purchase price in the file.")
            continue
        lot = combined.setdefault(ticker, [0.0, 0.0])
        lot[0] += shares
        lot[1] += shares * cost
    positions = [
        {"ticker": t, "shares": round(s, 6), "avg_cost": round(c / s, 4)}
        for t, (s, c) in sorted(combined.items())
    ]
    if not positions:
        raise ValueError("No holdings with a ticker, quantity and purchase price were found.")
    return positions, notes
