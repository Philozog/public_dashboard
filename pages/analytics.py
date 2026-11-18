import dash
import numpy as np
import pandas as pd
import plotly.express as px
from dash import Input, Output, dcc, html

from Services.components import metric_card as _metric_card
from Services.helper import load_data
from Services.market import (
    clean_returns,
    coverage_text,
    get_historical_prices,
)
from Services.market import (
    no_history_message as _no_history,
)
from Services.performance import (
    compute_performance_metrics,
    compute_portfolio_returns,
    compute_returns,
    compute_ttwr,
    drawdown_summary,
)
from Services.settings import get_settings
from Services.theme import blank_figure

dash.register_page(__name__, path="/analytics", name="Analytics", title="Analytics", order=2)
layout = html.Div(
    [
        dcc.Location(id="analytics_location"),
        html.H2("Analytics", className="page-title"),
        # Spinner while the price history loads.
        dcc.Loading(
            html.Div(
                [
                    html.Div(
                        [
                            _metric_card(label, key)
                            for label, key in [
                                ("Sharpe Ratio", "sharpe"),
                                ("Sortino Ratio", "sortino"),
                                ("Beta", "beta"),
                                ("Alpha (annualized)", "alpha"),
                                ("Current allocation return", "ttwr"),
                                ("Max Drawdown", "max_drawdown"),
                            ]
                        ],
                        className="summary-grid",
                    ),
                    html.P(
                        "Historical model of today's invested holdings, rebalanced daily; cash is excluded. "
                        "Returns use adjusted prices and matching dates."
                    ),
                    html.Div(id="analytics-status", className="data-status"),
                    dcc.Graph(id="performance_chart", figure=blank_figure()),
                    html.Div(id="drawdown-summary"),
                ]
            ),
            type="circle",
            delay_show=200,
        ),
    ]
)


def _duration(days):
    if days < 1:
        return "None"
    if days < 45:
        return f"{days} days"
    months = round(days / 30.4)
    return (
        f"{months} month{'s' if months != 1 else ''}" if months < 24 else f"{days / 365:.1f} years"
    )


def _drawdown_cards(mine, market, benchmark):
    if not mine:
        return ""

    def card(title, value, detail):
        return html.Div(
            [
                html.Div(title, className="metric-title"),
                html.Div(value, className="metric-value"),
                html.Div(detail, className="home-detail"),
            ],
            className="metric-card",
        )

    market_text = f"{benchmark}: {market['worst']:.1%}" if market else f"{benchmark}: n/a"
    current = mine["current"]
    return html.Div(
        [
            html.H3(
                "How far it fell from its high", className="card-title", style={"marginTop": "24px"}
            ),
            html.P(
                "A drop is measured from the highest value reached before it, using today's holdings "
                "over the history window.",
                className="muted",
                style={"margin": "0 0 10px", "fontSize": "13px"},
            ),
            html.Div(
                [
                    card(
                        "Worst drop",
                        f"{mine['worst']:.1%}",
                        f"{market_text} · lowest point {mine['worst_date']:%d %b %Y}",
                    ),
                    card(
                        "Below its high today",
                        "At its high" if current > -0.0005 else f"{current:.1%}",
                        f"{benchmark}: at its high"
                        if market and market["current"] > -0.0005
                        else (f"{benchmark}: {market['current']:.1%}" if market else ""),
                    ),
                    card(
                        "Longest time below a high",
                        _duration(mine["longest_days"]),
                        "Recovered" if mine["longest_recovered"] else "Not yet recovered",
                    ),
                ],
                className="summary-grid",
            ),
        ]
    )


@dash.callback(
    Output("performance_chart", "figure"),
    Output("drawdown-summary", "children"),
    Output("sharpe", "children"),
    Output("sortino", "children"),
    Output("beta", "children"),
    Output("alpha", "children"),
    Output("ttwr", "children"),
    Output("max_drawdown", "children"),
    Output("analytics-status", "children"),
    Input("analytics_location", "pathname"),
    Input("analysis-period", "value"),
    Input("analysis-benchmark", "value"),
    Input("settings-version", "data"),
)
def update_analytics(pathname, period="1y", benchmark="SPY", _version=None):
    empty = px.line()

    def unavailable(message):
        return empty, "", *("N/A",) * 6, message

    holdings = load_data()
    if holdings.empty or holdings.market_value.sum() <= 0:
        return unavailable("No invested holdings.")
    tickers = holdings.ticker.tolist()
    prices = get_historical_prices(tickers + [benchmark], period=period)
    if prices.empty:
        return unavailable(_no_history(period))
    if benchmark not in prices:
        return unavailable(
            f"Yahoo Finance didn't return history for the benchmark {benchmark} right now. "
            "Try again in a few minutes or pick another benchmark."
        )
    # Keep low-sample data out of displayed estimates in normal operation.
    returns = clean_returns(prices.reindex(columns=tickers), min_observations=30)
    bench = compute_returns(prices[benchmark])
    common = returns.index.intersection(bench.index)
    returns, bench = returns.loc[common], bench.loc[common]
    status = coverage_text(holdings, returns, period, benchmark)
    if returns.empty or returns.shape[1] == 0 or len(returns) < 30:
        return unavailable(status + " At least 30 complete common observations are required.")
    weights = holdings.set_index("ticker").market_value.reindex(returns.columns).fillna(0)
    weights /= weights.sum()
    portfolio = compute_portfolio_returns(returns, weights)
    rf = get_settings()["risk_free"]
    metrics = compute_performance_metrics(portfolio, bench, rf)
    cumulative = pd.DataFrame(
        {"Current allocation": (1 + portfolio).cumprod() - 1, benchmark: (1 + bench).cumprod() - 1}
    )
    baseline = pd.DataFrame(
        0.0,
        index=[prices.index[prices.index < common[0]][-1]]
        if any(prices.index < common[0])
        else [common[0] - pd.Timedelta(days=1)],
        columns=cumulative.columns,
    )
    perf = px.line(
        pd.concat([baseline, cumulative]),
        title="Historical return of current allocation",
        labels={"value": "Return", "index": "Date"},
    )
    perf.update_yaxes(tickformat=".1%")
    dd = _drawdown_cards(drawdown_summary(portfolio), drawdown_summary(bench), benchmark)

    def fmt(value, percent=False):
        return (
            "N/A"
            if value is None or not np.isfinite(value)
            else (f"{value:.2%}" if percent else f"{value:.2f}")
        )

    status += f" Annual risk-free assumption: {rf:.2%}."
    return (
        perf,
        dd,
        fmt(metrics["sharpe"]),
        fmt(metrics["sortino"]),
        fmt(metrics["beta"]),
        fmt(metrics["alpha"], True),
        fmt(compute_ttwr(portfolio), True),
        fmt(metrics["max_drawdown"], True),
        status,
    )
