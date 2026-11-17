"""Atomic trades and observed account performance.

Cash is not tracked: account value is the market value of the holdings. A buy
counts as money added to the account and a sale as money taken out, so
recorded returns reflect price moves (and fees), not the trades themselves.
"""

import math
import re

import pandas as pd

from Services.database import connect, utc_now

HOLDING_TYPES = ("Core", "High Conviction", "Moonshot", "Unassigned")


def number(value, label, positive=False):
    try:
        result = float(value)
    except (TypeError, ValueError):
        raise ValueError(f"Enter a valid {label}.") from None
    if not math.isfinite(result) or result < 0 or (positive and result == 0):
        raise ValueError(
            f"{label.capitalize()} must be {'positive' if positive else 'nonnegative'}."
        )
    return result


def record_valuation(conn, external_flow=0):
    holdings = float(
        conn.execute("SELECT COALESCE(SUM(market_value),0) FROM portfolio").fetchone()[0]
    )
    conn.execute(
        "INSERT INTO valuations(timestamp,nav,external_flow) VALUES(?,?,?)",
        (utc_now(), holdings, external_flow),
    )


def transact(
    kind,
    ticker=None,
    shares=None,
    price=None,
    holding_type=None,
    fees=0,
    note="",
    path=None,
):
    if kind not in ("buy", "sell"):
        raise ValueError("Unknown transaction type.")
    ticker = str(ticker or "").strip().upper()
    fees = number(fees or 0, "fees")
    with connect(path) as conn:
        conn.execute("BEGIN IMMEDIATE")
        record_valuation(conn)
        now = utc_now()
        realized = 0.0
        if not re.fullmatch(r"[A-Z0-9^][A-Z0-9.^=\-]{0,24}", ticker):
            raise ValueError("Enter a valid ticker.")
        qty, execution = number(shares, "shares", True), number(price, "execution price", True)
        row = conn.execute("SELECT * FROM portfolio WHERE ticker=?", (ticker,)).fetchone()
        current_qty = row["shares"] if row else 0.0
        avg = row["avg_price"] if row else 0.0
        if kind == "buy":
            if holding_type not in HOLDING_TYPES:
                raise ValueError("Select a valid holding type.")
            change = -(qty * execution + fees)
            new_qty = current_qty + qty
            avg = (current_qty * avg + qty * execution + fees) / new_qty
            quote = row["current_price"] if row and row["current_price"] else execution
            if row:
                conn.execute(
                    "UPDATE portfolio SET shares=?,avg_price=?,market_value=?,Total_Profit_Loss=?,holding_type=?,last_updated=? WHERE ticker=?",
                    (
                        new_qty,
                        avg,
                        new_qty * quote,
                        (quote - avg) * new_qty,
                        holding_type,
                        now,
                        ticker,
                    ),
                )
            else:
                conn.execute(
                    "INSERT INTO portfolio(ticker,shares,avg_price,current_price,market_value,Total_Profit_Loss,holding_type,last_updated) VALUES(?,?,?,?,?,?,?,?)",
                    (
                        ticker,
                        new_qty,
                        avg,
                        execution,
                        new_qty * execution,
                        (execution - avg) * new_qty,
                        holding_type,
                        now,
                    ),
                )
        else:
            if not row or qty > current_qty + 1e-10:
                raise ValueError(f"Cannot sell {qty:g} shares; you hold {current_qty:g}.")
            change = qty * execution - fees
            realized = (execution - avg) * qty - fees
            new_qty = max(current_qty - qty, 0.0)
            quote = row["current_price"] or avg
            if new_qty <= 1e-10:
                conn.execute("DELETE FROM portfolio WHERE ticker=?", (ticker,))
            else:
                conn.execute(
                    "UPDATE portfolio SET shares=?,market_value=?,Total_Profit_Loss=?,last_updated=? WHERE ticker=?",
                    (new_qty, new_qty * quote, (quote - avg) * new_qty, now, ticker),
                )
        conn.execute(
            "INSERT INTO transactions(timestamp,kind,ticker,shares,price,amount,fees,realized_pnl,note) VALUES(?,?,?,?,?,?,?,?,?)",
            (now, kind, ticker or None, qty, execution, change, fees, realized, str(note or "")),
        )
        # Money put into a buy (or taken out by a sale) is an external flow.
        record_valuation(conn, -change)
    return f"Recorded {kind}: {qty:g} {ticker} at ${execution:,.2f}."


def correct_holding(
    ticker, shares=None, avg_price=None, holding_type=None, delete=False, path=None
):
    """Fix a mistyped holding (or delete it) without counting it as a trade.

    The change in value is booked as an external flow, so it never shows up
    as a gain or loss in recorded returns. A "correction" row keeps the history.
    """
    ticker = str(ticker or "").strip().upper()
    with connect(path) as conn:
        conn.execute("BEGIN IMMEDIATE")
        row = conn.execute("SELECT * FROM portfolio WHERE ticker=?", (ticker,)).fetchone()
        if not row:
            raise ValueError(f"{ticker or 'That holding'} is not in your portfolio.")
        record_valuation(conn)
        before = f"{row['shares']:g} shares at ${row['avg_price']:,.2f}"
        old_value = row["market_value"] or 0.0
        if delete:
            conn.execute("DELETE FROM portfolio WHERE ticker=?", (ticker,))
            note, qty, price, new_value = f"Deleted holding (was {before}).", 0.0, 0.0, 0.0
            message = f"Deleted {ticker}."
        else:
            qty = number(shares, "shares", True)
            price = number(avg_price, "average cost", True)
            if holding_type not in HOLDING_TYPES:
                raise ValueError("Select a valid holding type.")
            quote = row["current_price"] or price
            new_value = qty * quote
            conn.execute(
                "UPDATE portfolio SET shares=?,avg_price=?,market_value=?,Total_Profit_Loss=?,holding_type=?,last_updated=? WHERE ticker=?",
                (qty, price, new_value, (quote - price) * qty, holding_type, utc_now(), ticker),
            )
            note = f"Corrected from {before}."
            message = f"Corrected {ticker}: {qty:g} shares at ${price:,.2f}."
        conn.execute(
            "INSERT INTO transactions(timestamp,kind,ticker,shares,price,amount,fees,realized_pnl,note) VALUES(?,?,?,?,?,0,0,0,?)",
            (utc_now(), "correction", ticker, qty, price, note),
        )
        record_valuation(conn, new_value - old_value)
    return message


def set_holding_type(ticker, holding_type, path=None):
    if holding_type not in HOLDING_TYPES:
        raise ValueError("Select a valid holding type.")
    with connect(path) as conn:
        result = conn.execute(
            "UPDATE portfolio SET holding_type=?,last_updated=? WHERE ticker=?",
            (holding_type, utc_now(), str(ticker or "").strip().upper()),
        )
        if result.rowcount != 1:
            raise ValueError("Ticker not found.")
    return "Holding type updated."


def account_summary(path=None):
    with connect(path) as conn:
        row = conn.execute(
            "SELECT COALESCE(SUM(market_value),0),COALESCE(SUM(Total_Profit_Loss),0) FROM portfolio"
        ).fetchone()
        realized = conn.execute(
            "SELECT COALESCE(SUM(realized_pnl),0) FROM transactions"
        ).fetchone()[0]
    return dict(holdings=row[0], nav=row[0], unrealized=row[1], realized=realized)


def transaction_history(path=None):
    with connect(path) as conn:
        return pd.read_sql_query("SELECT * FROM transactions ORDER BY id DESC", conn)


def account_performance(path=None):
    with connect(path) as conn:
        values = pd.read_sql_query("SELECT * FROM valuations ORDER BY id", conn)
    if values.empty:
        return values
    previous = values.nav.shift(1)
    values["return"] = ((values.nav - values.external_flow) / previous - 1).where(previous > 0, 0.0)
    values["growth"] = (1 + values["return"]).cumprod()
    return values
