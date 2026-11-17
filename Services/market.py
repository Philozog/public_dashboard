"""Shared adjusted history, bounded caching and complete-date risk samples."""

import logging
import threading
import time

import numpy as np
import pandas as pd
import yfinance as yf

PERIODS = ("6mo", "1y", "3y", "5y")
BENCHMARKS = ("SPY", "QQQ", "VT", "AGG")
_cache = {}
_lock = threading.Lock()
LOG = logging.getLogger(__name__)


def extract_prices(data, tickers):
    if data is None or data.empty:
        return pd.DataFrame()
    if isinstance(data.columns, pd.MultiIndex):
        field = "Adj Close" if "Adj Close" in data.columns.get_level_values(0) else "Close"
        if field not in data.columns.get_level_values(0):
            return pd.DataFrame()
        result = data[field].copy()
        if isinstance(result, pd.Series):
            result = result.to_frame()
        result.columns = [str(c).upper() for c in result.columns]
    else:
        field = "Adj Close" if "Adj Close" in data else "Close"
        if field not in data:
            return pd.DataFrame()
        result = data[[field]].rename(columns={field: tickers[0]})
    result.index = pd.to_datetime(result.index, utc=True).tz_convert(None)
    return (
        result.sort_index()
        .loc[lambda x: ~x.index.duplicated(keep="last")]
        .replace([np.inf, -np.inf], np.nan)
        .where(lambda x: x > 0)
        .dropna(axis=1, how="all")
    )


CACHE_SECONDS = 30 * 60  # daily history barely changes within half an hour
FAILED_SECONDS = 5 * 60  # don't retry a failed ticker on every page view
DOWNLOAD_TIMEOUT = 15  # seconds per request


def _download_one_by_one(tickers, period):
    found = {}
    for index, ticker in enumerate(tickers):
        if index:
            time.sleep(0.4)
        try:
            history = yf.Ticker(ticker).history(
                period=period, auto_adjust=True, timeout=DOWNLOAD_TIMEOUT
            )
        except Exception as exc:
            LOG.warning("Retry for %s failed: %s", ticker, exc)
            continue
        if history is not None and not history.empty and "Close" in history:
            series = history["Close"].replace([np.inf, -np.inf], np.nan)
            series.index = pd.to_datetime(series.index, utc=True).tz_convert(None).normalize()
            series = series[series > 0].dropna()
            if not series.empty:
                found[ticker] = series[~series.index.duplicated(keep="last")]
    return pd.concat(found, axis=1).sort_index() if found else pd.DataFrame()


def get_historical_prices(tickers, period="1y", interval="1d"):
    """Daily adjusted closes, one column per ticker.

    Each (ticker, period) is cached on its own and shared by every page, so
    Home, Analytics, Correlations and Monte Carlo reuse one download, and
    switching benchmark only fetches the new benchmark. Missing tickers are
    downloaded together in one parallel request.
    """
    tickers = sorted({str(t).strip().upper() for t in tickers if str(t).strip()})
    if not tickers:
        return pd.DataFrame()
    if period not in PERIODS or interval != "1d":
        raise ValueError("Unsupported history window or interval.")
    now = time.monotonic()
    found, missing = {}, []
    with _lock:
        for ticker in tickers:
            cached = _cache.get((ticker, period))
            if cached is None:
                missing.append(ticker)
            elif cached[1] is None:  # recent failure
                if now - cached[0] >= FAILED_SECONDS:
                    missing.append(ticker)
            elif now - cached[0] < CACHE_SECONDS:
                found[ticker] = cached[1]
            else:
                missing.append(ticker)
    if missing:
        try:
            data = yf.download(
                tickers=missing,
                period=period,
                interval=interval,
                progress=False,
                auto_adjust=True,
                group_by="column",
                threads=True,
                timeout=DOWNLOAD_TIMEOUT,
            )
            fresh = extract_prices(data, missing)
        except Exception:
            LOG.exception("Historical price download failed")
            fresh = pd.DataFrame()
        # Yahoo sometimes drops tickers from a parallel batch (it throttles
        # busy servers). Retry those one at a time, gently, before giving up.
        retry = [t for t in missing if t not in fresh.columns or fresh[t].dropna().empty][:25]
        if retry:
            recovered = _download_one_by_one(retry, period)
            if not recovered.empty:
                fresh = (
                    recovered
                    if fresh.empty
                    else fresh.drop(columns=recovered.columns, errors="ignore").join(
                        recovered, how="outer"
                    )
                )
        with _lock:
            for ticker in missing:
                series = fresh[ticker].dropna() if ticker in fresh.columns else None
                ok = series is not None and not series.empty
                _cache[(ticker, period)] = (time.monotonic(), series if ok else None)
                if ok:
                    found[ticker] = series
            while len(_cache) > 400:
                _cache.pop(next(iter(_cache)))
        failed = [t for t in missing if t not in found]
        if failed:
            LOG.warning("No price history for %s (%s)", ", ".join(failed), period)
    if not found:
        return pd.DataFrame()
    return pd.concat(found, axis=1).sort_index()[[t for t in tickers if t in found]].copy()


def clean_returns(prices, min_observations=30, log=False):
    values = prices.pct_change(fill_method=None).replace([np.inf, -np.inf], np.nan)
    values = values.dropna(axis=1, thresh=min_observations).dropna()
    if log:
        values = np.log1p(values)
    return values


def coverage_text(holdings, returns, period, benchmark=None):
    included = list(returns.columns)
    values = holdings.groupby("ticker")["market_value"].sum()
    total = float(values.sum())
    covered = float(values.reindex(included).fillna(0).sum())
    missing = sorted(set(values.index) - set(included))
    dates = (
        f"{returns.index.min():%Y-%m-%d} to {returns.index.max():%Y-%m-%d}"
        if not returns.empty
        else "no complete common dates"
    )
    return (
        (
            f"Requested window: {period}. Actual sample: {dates}; {len(returns)} daily observations. "
            f"Holdings: {len(included)}/{len(values)}; value coverage: {covered / total:.1%}. "
            if total > 0
            else "No invested holdings. "
        )
        + (f"Excluded: {', '.join(missing)}. " if missing else "")
        + (f"Benchmark: {benchmark}." if benchmark else "")
    )


def no_history_message(period):
    label = {"6mo": "6-month", "1y": "1-year", "3y": "3-year", "5y": "5-year"}.get(period, period)
    return (
        f"Yahoo Finance didn't return {label} price history for your holdings right now "
        "(it sometimes limits requests). Try again in a few minutes, or choose a shorter "
        "History window above."
    )
