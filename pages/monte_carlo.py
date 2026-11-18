from io import StringIO

import dash
import numpy as np
import pandas as pd
import plotly.graph_objects as go
from dash import Input, Output, State, dcc, html

from Services import theme
from Services.components import metric_card as _metric_card
from Services.helper import load_data
from Services.market import clean_returns, coverage_text, get_historical_prices
from Services.performance import (
    BENCHMARK_ANNUAL_RETURN,
    DRIFT_SHRINKAGE,
    MAX_ANNUAL_DRIFT,
    simulate_paths,
)
from Services.theme import blank_figure

DEFAULT_SIMULATIONS = 10000
DEFAULT_YEARS = 1


dash.register_page(
    __name__,
    path="/monte-carlo",
    name="Monte Carlo",
    title="Monte Carlo",
    order=5,
)


def _empty_figure(title, message):
    fig = go.Figure()
    fig.update_layout(
        title=title,
        annotations=[
            {
                "text": message,
                "xref": "paper",
                "yref": "paper",
                "x": 0.5,
                "y": 0.5,
                "showarrow": False,
                "font": {"size": 15},
            }
        ],
        xaxis={"visible": False},
        yaxis={"visible": False},
    )
    fig.update_yaxes(automargin=True, title_standoff=16)
    return fig


def _load_holdings():
    df = load_data().copy()
    if df.empty:
        return df

    df["ticker"] = df["ticker"].astype(str).str.strip().str.upper()
    df = df[df["ticker"] != ""]

    df["market_value_num"] = pd.to_numeric(df["market_value"], errors="coerce")
    df["shares_num"] = pd.to_numeric(df["shares"], errors="coerce")
    df["current_price_num"] = pd.to_numeric(df["current_price"], errors="coerce")

    fallback_value = df["shares_num"].fillna(0) * df["current_price_num"].fillna(0)
    df["position_value"] = df["market_value_num"].where(df["market_value_num"] > 0, fallback_value)
    df["position_value"] = df["position_value"].where(df["position_value"] > 0, 0.0).fillna(0.0)
    return df


def _download_prices(tickers, period="1y"):
    return get_historical_prices(tickers, period=period)


def _build_weights(holdings, valid_tickers):
    position_values = (
        holdings.groupby("ticker", as_index=True)["position_value"]
        .sum()
        .reindex(valid_tickers)
        .fillna(0.0)
    )

    total_value = float(position_values.sum())
    if total_value <= 0:
        return pd.Series(dtype=float), 0.0

    return position_values / total_value, total_value


def _simulate_portfolio_paths(returns, weights, initial_value, years, simulations, **assumptions):
    return simulate_paths(returns, weights, initial_value, years, simulations, **assumptions)


SHOCK_LABELS = {
    "normal": "Normal (bell curve)",
    "student_t": "Fat tails (Student-t)",
    "bootstrap": "Historical days (bootstrap)",
}


def _assumption_input(label, input_id, value, minimum, maximum):
    return html.Div(
        [
            html.Label(label, htmlFor=input_id),
            # No min/max on the box: Dash would silently blank an out-of-range value and the
            # default would be used. The model checks the range and says what's wrong.
            dcc.Input(id=input_id, type="number", value=value, step="any"),
            html.Div(f"{minimum:g} to {maximum:g}", className="muted", style={"fontSize": "12px"}),
        ],
        className="form-field",
    )


def _format_currency(value):
    return f"${value:,.0f}"


def _format_percent(value):
    return f"{value:.1%}"


def _build_projection_chart(years_axis, path_values):
    percentile_5 = np.percentile(path_values, 5, axis=1)
    percentile_25 = np.percentile(path_values, 25, axis=1)
    percentile_50 = np.percentile(path_values, 50, axis=1)
    percentile_75 = np.percentile(path_values, 75, axis=1)
    percentile_95 = np.percentile(path_values, 95, axis=1)

    fig = go.Figure()
    fig.add_trace(
        go.Scatter(
            x=years_axis,
            y=percentile_95,
            mode="lines",
            line={"width": 0},
            hoverinfo="skip",
            showlegend=False,
        )
    )
    fig.add_trace(
        go.Scatter(
            x=years_axis,
            y=percentile_5,
            mode="lines",
            fill="tonexty",
            fillcolor="rgba(37, 99, 235, 0.15)",
            line={"width": 0},
            name="5th-95th percentile",
        )
    )
    fig.add_trace(
        go.Scatter(
            x=years_axis,
            y=percentile_75,
            mode="lines",
            line={"width": 0},
            hoverinfo="skip",
            showlegend=False,
        )
    )
    fig.add_trace(
        go.Scatter(
            x=years_axis,
            y=percentile_25,
            mode="lines",
            fill="tonexty",
            fillcolor="rgba(29, 78, 216, 0.25)",
            line={"width": 0},
            name="25th-75th percentile",
        )
    )
    fig.add_trace(
        go.Scatter(
            x=years_axis,
            y=percentile_50,
            mode="lines",
            line={"color": theme.ACCENT_BRIGHT, "width": 3},
            name="Median path",
        )
    )
    fig.update_layout(
        title={"text": "Projected Portfolio Value Paths", "y": 0.97, "yanchor": "top"},
        xaxis_title="Years",
        yaxis_title="Portfolio Value",
        # Legend on its own line between the title and the plot, with space around it.
        legend={
            "orientation": "h",
            "x": 0,
            "xanchor": "left",
            "y": 1.02,
            "yanchor": "bottom",
            "itemwidth": 40,
            "tracegroupgap": 24,
            "font": {"size": 12},
        },
        margin={"t": 85},
    )
    fig.update_yaxes(tickprefix="$", separatethousands=True)
    fig.update_yaxes(automargin=True, title_standoff=16)
    return fig


def _build_distribution_chart(final_values, initial_value):
    fig = go.Figure()
    fig.add_trace(
        go.Histogram(
            x=final_values,
            nbinsx=40,
            marker={"color": "#38bdf8"},
            name="Ending values",
        )
    )
    for percentile, color in ((5, theme.NEGATIVE), (50, theme.TEXT_STRONG), (95, theme.POSITIVE)):
        value = float(np.percentile(final_values, percentile))
        fig.add_vline(
            x=value,
            line_width=2,
            line_dash="dash",
            line_color=color,
            annotation_text=f"P{percentile}: {_format_currency(value)}",
            annotation_position="top",
        )

    fig.add_vline(
        x=float(initial_value),
        line_width=2,
        line_color=theme.MUTED,
        annotation_text=f"Today: {_format_currency(initial_value)}",
        annotation_position="bottom right",
    )
    fig.update_layout(
        title="Distribution of Ending Portfolio Values",
        xaxis_title="Ending Value",
        yaxis_title="Simulation Count",
    )
    fig.update_xaxes(tickprefix="$", separatethousands=True)
    fig.update_yaxes(automargin=True, title_standoff=16)
    return fig


def _build_explanation(
    current_value,
    median_value,
    downside_value,
    upside_value,
    loss_probability,
    years,
    simulations,
    severe_value,
    long_run,
    shrinkage,
    cap,
    shocks,
    period,
):
    plural = "s" if years != 1 else ""
    return html.Div(
        [
            html.H4("How to read this", style={"marginTop": "0"}),
            html.P(
                f"These are {simulations:,} illustrative scenarios over {years} year{plural}, built "
                "from your current weights and the assumptions above. They show what could happen "
                "if those assumptions hold; they are not a forecast of what will happen."
            ),
            html.P(
                f"The middle scenario ends near {_format_currency(median_value)}. One in twenty "
                f"scenarios ends below {_format_currency(downside_value)} and one in twenty above "
                f"{_format_currency(upside_value)}. One in a hundred ends below "
                f"{_format_currency(severe_value)}. {_format_percent(loss_probability)} of scenarios "
                f"end below today's {_format_currency(current_value)}. That share comes from the "
                "assumptions, so it is not a real-world probability."
            ),
            html.H4("What drives the result"),
            html.Ul(
                [
                    html.Li(
                        f"Long-run return {long_run:.1%}: the biggest single driver of the middle "
                        "scenario. It is a choice, not something the data estimated."
                    ),
                    html.Li(
                        f"Weight on history {shrinkage:.0%}: each holding's expected return is "
                        f"{shrinkage:.0%} its own past return and {1 - shrinkage:.0%} the long-run "
                        "return, because past returns are very noisy."
                    ),
                    html.Li(
                        f"Return cap ±{cap:.0%}: no holding is assumed to earn more (or lose more) "
                        "than this per year on average."
                    ),
                    html.Li(
                        f"Shocks: {SHOCK_LABELS[shocks]}. The bell curve understates crashes like "
                        "2008 or March 2020, so its worst scenarios are probably too optimistic. "
                        "Fat tails lets each simulated year be calmer or far more turbulent than "
                        "the history; Historical days replays month-long stretches of your actual "
                        "history. Compare the one-in-a-hundred figure across settings."
                    ),
                    html.Li(
                        f"Volatility and correlations come from the {period} history window. In a "
                        "crisis, correlations tend to jump, so diversification can look better here "
                        "than it is when it's needed most."
                    ),
                    html.Li(
                        "Weights stay fixed and are rebalanced daily, with no trading costs, "
                        "contributions, withdrawals, fees or taxes. Cash and holdings without "
                        "price history are left out. Annual figures use 252 trading days."
                    ),
                ],
                style={"lineHeight": "1.6"},
            ),
        ],
        className="panel",
    )


layout = html.Div(
    [
        html.H2("Portfolio Monte Carlo Simulation", className="subtitle"),
        html.Div(
            [
                html.B("Illustrative scenarios under stated assumptions, not a forecast. "),
                "The range below shows what could happen if the assumptions listed hold. "
                "Change them to see how sensitive the results are.",
            ],
            className="mc-notice",
        ),
        html.Div(
            [
                html.Div(
                    [
                        html.Label("Time horizon"),
                        dcc.Dropdown(
                            id="mc-years",
                            options=[
                                {"label": "1 year", "value": 1},
                                {"label": "3 years", "value": 3},
                                {"label": "5 years", "value": 5},
                            ],
                            value=DEFAULT_YEARS,
                            clearable=False,
                        ),
                    ],
                    style={"width": "180px"},
                ),
                html.Div(
                    [
                        html.Label("Simulation count"),
                        dcc.Dropdown(
                            id="mc-simulations",
                            options=[
                                {"label": "500", "value": 500},
                                {"label": "1,000", "value": 1000},
                                {"label": "5,000", "value": 5000},
                                {"label": "10,000", "value": 10000},
                            ],
                            value=DEFAULT_SIMULATIONS,
                            clearable=False,
                        ),
                    ],
                    style={"width": "180px"},
                ),
                html.Button("Run simulation", id="mc-run-btn", n_clicks=0, className="mc-run"),
            ],
            className="mc-controls",
        ),
        html.Div(
            [
                html.Div("Assumptions", className="card-title"),
                html.Div(
                    [
                        _assumption_input(
                            "Long-run return (%/yr)",
                            "mc-long-run",
                            round(BENCHMARK_ANNUAL_RETURN * 100, 2),
                            -20,
                            30,
                        ),
                        _assumption_input(
                            "Weight on history (%)",
                            "mc-shrinkage",
                            round(DRIFT_SHRINKAGE * 100),
                            0,
                            100,
                        ),
                        _assumption_input(
                            "Return cap (± %/yr)", "mc-cap", round(MAX_ANNUAL_DRIFT * 100), 1, 100
                        ),
                        html.Div(
                            [
                                html.Label("Shocks", htmlFor="mc-shocks"),
                                dcc.Dropdown(
                                    id="mc-shocks",
                                    options=[
                                        {"label": label, "value": value}
                                        for value, label in SHOCK_LABELS.items()
                                    ],
                                    value="normal",
                                    clearable=False,
                                ),
                            ],
                            className="form-field",
                        ),
                    ],
                    className="holding-form mc-assumptions",
                ),
                html.P(
                    "Fixed in this model: weights stay constant and are rebalanced daily; volatility "
                    "and correlations come from the History window above; no contributions, "
                    "withdrawals, fees or taxes; 252 trading days a year.",
                    className="muted",
                    style={"margin": "10px 0 0", "fontSize": "13px"},
                ),
            ],
            className="card",
            # Keep the Shocks list above the result boxes when it opens.
            style={
                "marginBottom": "12px",
                "position": "relative",
                "zIndex": 20,
                "overflow": "visible",
            },
        ),
        html.Div(
            "Choose a time horizon and how many simulations to run, then press Run simulation.",
            id="mc-status",
            className="mc-status",
        ),
        dcc.Loading(
            html.Div(
                [
                    html.Div(
                        [
                            _metric_card("Modeled holdings value", "mc-current-value"),
                            _metric_card("Middle scenario (median)", "mc-median-value"),
                            _metric_card("Low scenario (5th pct)", "mc-downside-value"),
                            _metric_card("High scenario (95th pct)", "mc-upside-value"),
                            _metric_card("Scenarios below today", "mc-loss-probability"),
                            _metric_card("Middle scenario yearly return", "mc-cagr"),
                        ],
                        style={
                            "display": "flex",
                            "gap": "12px",
                            "flexWrap": "wrap",
                            "marginBottom": "12px",
                        },
                    ),
                    dcc.Graph(id="mc-projection-chart", figure=blank_figure()),
                    dcc.Graph(id="mc-distribution-chart", figure=blank_figure()),
                    html.Div(id="mc-explanation"),
                ]
            ),
            type="circle",
            delay_show=150,
        ),
    ]
)


if not hasattr(dash, "_monte_carlo_callback_registered"):
    dash._monte_carlo_callback_registered = True

    def fetch_prices(period="1y"):
        holdings = _load_holdings()
        if holdings.empty:
            return {"error": "No holdings found. Add positions on the Portfolio page first."}

        tickers = sorted(holdings["ticker"].dropna().unique().tolist())
        prices = _download_prices(tickers, period)
        if prices.empty:
            return {"error": "Unable to fetch enough price history to run the simulation."}

        prices = prices[[column for column in prices.columns if column in tickers]]
        prices = prices.dropna(axis=1, how="all")
        if prices.empty:
            return {"error": "Not enough clean price history after filtering missing data."}

        returns = clean_returns(prices, min_observations=30, log=True)

        valid_tickers = returns.columns.tolist()
        if returns.empty or not valid_tickers:
            return {"error": "Return history is unavailable after filtering."}

        min_obs = int(returns.notna().sum().min())
        if min_obs < 30:
            return {"error": "Not enough clean price history after filtering missing data."}

        weights, current_value = _build_weights(holdings, valid_tickers)
        if weights.empty or current_value <= 0:
            return {"error": "Current portfolio value is zero, so the simulation cannot run."}

        dropped = sorted(set(tickers) - set(valid_tickers))
        return {
            "coverage": coverage_text(holdings, returns, period),
            "period": period,
            "returns_json": returns.to_json(orient="split"),
            "weights_json": weights.to_json(orient="split"),
            "current_value": current_value,
            "valid_tickers": valid_tickers,
            "total_tickers": len(tickers),
            "min_obs": min_obs,
            "max_obs": int(returns.notna().sum().max()),
            "dropped": dropped,
            "error": None,
        }

    @dash.callback(
        Output("mc-status", "children"),
        Output("mc-projection-chart", "figure"),
        Output("mc-distribution-chart", "figure"),
        Output("mc-current-value", "children"),
        Output("mc-median-value", "children"),
        Output("mc-downside-value", "children"),
        Output("mc-upside-value", "children"),
        Output("mc-loss-probability", "children"),
        Output("mc-cagr", "children"),
        Output("mc-explanation", "children"),
        Input("mc-run-btn", "n_clicks"),
        State("mc-years", "value"),
        State("mc-simulations", "value"),
        State("analysis-period", "value"),
        State("mc-long-run", "value"),
        State("mc-shrinkage", "value"),
        State("mc-cap", "value"),
        State("mc-shocks", "value"),
        prevent_initial_call=True,
    )
    def update_monte_carlo(_clicks, years, simulations, period, long_run, shrinkage, cap, shocks):
        """Runs only when the Run simulation button is pressed."""
        cache = fetch_prices(period or "1y")
        empty_projection = _empty_figure(
            "Projected Portfolio Value Paths", "No simulation data available."
        )
        empty_distribution = _empty_figure(
            "Distribution of Ending Portfolio Values", "No simulation data available."
        )
        blank = ("--",) * 6

        error = cache.get("error")
        if error:
            return (error, empty_projection, empty_distribution, *blank, html.Div(error))

        returns = pd.read_json(StringIO(cache["returns_json"]), orient="split")
        weights = pd.read_json(StringIO(cache["weights_json"]), orient="split", typ="series")
        current_value = float(cache["current_value"])

        assumptions = dict(
            long_run=(BENCHMARK_ANNUAL_RETURN * 100 if long_run is None else long_run) / 100,
            shrinkage=(DRIFT_SHRINKAGE * 100 if shrinkage is None else shrinkage) / 100,
            cap=(MAX_ANNUAL_DRIFT * 100 if cap is None else cap) / 100,
            shocks=shocks or "normal",
        )
        try:
            years_axis, path_values = _simulate_portfolio_paths(
                returns=returns,
                weights=weights,
                initial_value=current_value,
                years=int(years or DEFAULT_YEARS),
                simulations=int(simulations or DEFAULT_SIMULATIONS),
                **assumptions,
            )
        except ValueError as exc:
            message = f"Not run: {exc}"
            return (message, empty_projection, empty_distribution, *blank, html.Div(message))

        final_values = path_values[-1]
        median_value = float(np.percentile(final_values, 50))
        downside_value = float(np.percentile(final_values, 5))
        upside_value = float(np.percentile(final_values, 95))
        severe_value = float(np.percentile(final_values, 1))
        loss_probability = float(np.mean(final_values < current_value))
        median_cagr = float((median_value / current_value) ** (1 / max(int(years), 1)) - 1)

        n = len(cache["valid_tickers"])
        status_parts = [
            f"Simulated {int(simulations or DEFAULT_SIMULATIONS):,} paths over "
            f"{int(years or DEFAULT_YEARS)} year{'s' if int(years or DEFAULT_YEARS) != 1 else ''}"
            f" ({SHOCK_LABELS[assumptions['shocks']]}, long-run {assumptions['long_run']:.1%},"
            f" {assumptions['shrinkage']:.0%} history, cap ±{assumptions['cap']:.0%}).",
            f"Using {n} of {cache['total_tickers']} holdings."
            f" Observations per ticker: {cache['min_obs']}–{cache['max_obs']} trading days.",
            cache["coverage"],
        ]
        if cache.get("dropped"):
            status_parts.append(
                f"Filtered due to missing price history: {', '.join(cache['dropped'])}."
            )

        return (
            " ".join(status_parts),
            _build_projection_chart(years_axis, path_values),
            _build_distribution_chart(final_values, current_value),
            _format_currency(current_value),
            _format_currency(median_value),
            _format_currency(downside_value),
            _format_currency(upside_value),
            _format_percent(loss_probability),
            _format_percent(median_cagr),
            _build_explanation(
                current_value=current_value,
                median_value=median_value,
                downside_value=downside_value,
                upside_value=upside_value,
                loss_probability=loss_probability,
                years=int(years or DEFAULT_YEARS),
                simulations=int(simulations or DEFAULT_SIMULATIONS),
                severe_value=severe_value,
                period={"6mo": "6-month", "1y": "1-year", "3y": "3-year", "5y": "5-year"}.get(
                    cache.get("period"), "selected"
                ),
                **assumptions,
            ),
        )
