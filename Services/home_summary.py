"""Numbers and alerts for the Home page, kept separate from layout so they can be tested."""

from datetime import datetime, timezone

import pandas as pd

from Services.insights import rebalance_plan
from Services.settings import get_settings

BENCHMARK = "SPY"
BIG_MOVE = 0.05  # a daily move this large gets an alert
STALE_AFTER = pd.Timedelta(days=4)  # covers weekends and a holiday


def _pct(new, old):
    return float(new) / float(old) - 1 if old and pd.notna(old) and pd.notna(new) else None


def holdings_value_history(holdings, prices):
    """Daily value of today's shares at past prices (tickers without history are skipped)."""
    shares = holdings.set_index("ticker")["shares"]
    covered = [t for t in shares.index if t in prices.columns]
    if not covered:
        return pd.Series(dtype=float)
    frame = prices[covered].ffill().dropna(how="any")
    return (frame * shares[covered]).sum(axis=1)


def glance(holdings, prices, now=None, raw_holdings=None):
    """Values for the four summary cards. Missing data comes back as None."""
    now = now or pd.Timestamp.now(tz="UTC")
    out = {
        "value": float(holdings["market_value"].sum()) if not holdings.empty else 0.0,
        "day_change": None,
        "day_pct": None,
        "ytd_pct": None,
        "spy_day_pct": None,
        "spy_ytd_pct": None,
        "spark": pd.Series(dtype=float),
        "movers": [],
        "updated": None,
    }
    if holdings.empty:
        return out

    history = holdings_value_history(holdings, prices) if not prices.empty else pd.Series()
    if len(history) >= 2:
        out["day_change"] = float(history.iloc[-1] - history.iloc[-2])
        out["day_pct"] = _pct(history.iloc[-1], history.iloc[-2])
        out["spark"] = history[history.index >= history.index[-1] - pd.Timedelta(days=183)]
        this_year = history[history.index.year == history.index[-1].year]
        if len(this_year) >= 2:
            out["ytd_pct"] = _pct(history.iloc[-1], this_year.iloc[0])

    if BENCHMARK in prices.columns:
        spy = prices[BENCHMARK].dropna()
        if len(spy) >= 2:
            out["spy_day_pct"] = _pct(spy.iloc[-1], spy.iloc[-2])
            this_year = spy[spy.index.year == spy.index[-1].year]
            if len(this_year) >= 2:
                out["spy_ytd_pct"] = _pct(spy.iloc[-1], this_year.iloc[0])

    movers = []
    for ticker in holdings["ticker"]:
        if ticker in prices.columns:
            series = prices[ticker].dropna()
            if len(series) >= 2:
                movers.append((ticker, _pct(series.iloc[-1], series.iloc[-2])))
    out["movers"] = sorted(movers, key=lambda item: item[1], reverse=True)

    # prepare_holdings() drops quote times, so read them from load_data()'s rows.
    source = raw_holdings if raw_holdings is not None else holdings
    if "quote_updated_at" in source:
        stamps = pd.to_datetime(source["quote_updated_at"], utc=True, errors="coerce").dropna()
        if not stamps.empty:
            out["updated"] = stamps.max()
    return out


def alerts(holdings, raw_holdings, movers=(), now=None):
    """(level, text) items that need attention: alert, warn or info. Empty means all clear."""
    if holdings.empty:
        return []
    now = now or pd.Timestamp.now(tz="UTC")
    settings = get_settings()
    items = []

    limit = settings["concentration"]
    for _, row in holdings.sort_values("weight_pct", ascending=False).iterrows():
        if row["weight_pct"] > limit:
            items.append(
                (
                    "alert",
                    f"{row['ticker']} is {row['weight_pct']:.0f}% of your portfolio, "
                    f"above your {limit:g}% limit.",
                )
            )

    for row in rebalance_plan(holdings):
        if row["status"] in ("over", "under"):
            direction = "above" if row["gap_pct"] > 0 else "below"
            items.append(
                (
                    "warn",
                    f"{row['bucket']} is {abs(row['gap_pct']):.0f} points {direction} its "
                    f"{row['target_pct']:g}% target ({row['action'].lower()}).",
                )
            )
        elif row["status"] == "warn":
            items.append(
                (
                    "warn",
                    f"{row['current_pct']:.0f}% of your portfolio has no holding type. "
                    "Set one on the Portfolio page.",
                )
            )

    for ticker, move in movers:
        if abs(move) >= BIG_MOVE:
            items.append(("info", f"{ticker} moved {move:+.1%} on the latest trading day."))

    stamps = pd.to_datetime(raw_holdings.get("quote_updated_at"), utc=True, errors="coerce")
    stale = raw_holdings.loc[stamps.isna() | (now - stamps > STALE_AFTER), "ticker"].tolist()
    if stale:
        items.append(
            (
                "warn",
                f"No recent price for {', '.join(stale)}. Press Refresh quotes on the Portfolio page.",
            )
        )
    return items


def time_ago(stamp, now=None):
    if stamp is None:
        return "never"
    now = now or datetime.now(timezone.utc)
    minutes = int((now - stamp).total_seconds() // 60)
    if minutes < 1:
        return "just now"
    if minutes < 60:
        return f"{minutes} min ago"
    if minutes < 48 * 60:
        return f"{minutes // 60} h ago"
    return f"{minutes // 1440} days ago"
