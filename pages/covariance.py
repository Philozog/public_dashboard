import dash
import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from dash import Input, Output, dcc, html

from Services import theme
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
from Services.performance import RISK_HEAVY, risk_takeaway, risk_vs_weight, valid_covariance
from Services.settings import get_settings
from Services.theme import blank_figure

dash.register_page(__name__, path="/covariance", name="Correlations", title="Correlations", order=3)

layout = html.Div(
    [
        dcc.Location(id="cov_location"),
        html.H2("Correlations", className="page-title"),
        # Spinner while the price history loads.
        dcc.Loading(
            html.Div(
                [
                    html.Div(
                        [
                            _metric_card(label, key)
                            for label, key in [
                                (
                                    "Portfolio annualized volatility",
                                    "covariance-metric-portfolio-vol",
                                ),
                                ("Benchmark volatility", "covariance-metric-spy-vol"),
                                ("Diversification ratio", "covariance-metric-div-ratio"),
                            ]
                        ],
                        className="summary-grid",
                    ),
                    html.Div(id="covariance-status", className="data-status"),
                    dcc.Graph(id="covariance-heatmap", figure=blank_figure()),
                    html.Div(id="covariance-insights", className="panel"),
                    html.H3("Money vs risk", className="card-title", style={"marginTop": "24px"}),
                    html.P(id="risk-takeaway", className="risk-takeaway"),
                    dcc.Graph(id="risk-contribution-chart", figure=blank_figure()),
                    html.Div(id="risk-table"),
                    html.P(
                        "Risk contribution is the share of the portfolio's modeled ups and downs "
                        "(variance) attributed to each holding, including its share of how it moves "
                        "with the others. A risk/weight above 1.0× means it adds more risk than its "
                        "share of your money; below 1.0× it helps diversify, and a negative value "
                        "means it tends to offset the rest. Standalone volatility is how much the "
                        "stock swings on its own in a year, ignoring the other holdings. Uses current "
                        "invested weights; cash is excluded.",
                        className="muted",
                        style={"fontSize": "13px"},
                    ),
                ]
            ),
            type="circle",
            delay_show=200,
        ),
    ]
)


def _money_vs_risk_chart(table):
    heavy = table["ratio"] >= RISK_HEAVY
    fig = go.Figure(
        [
            go.Bar(
                name="Share of money",
                x=table.index,
                y=table["weight"] * 100,
                marker_color="rgba(148, 163, 184, 0.55)",
                hovertemplate="%{x}: %{y:.1f}% of money<extra></extra>",
            ),
            go.Bar(
                name="Share of risk",
                x=table.index,
                y=table["risk"] * 100,
                marker_color=[theme.NEGATIVE if h else theme.ACCENT_BRIGHT for h in heavy],
                text=[f"{r:.2f}×" if pd.notna(r) else "" for r in table["ratio"]],
                textposition="outside",
                hovertemplate="%{x}: %{y:.1f}% of risk (%{text})<extra></extra>",
            ),
        ]
    )
    fig.update_layout(
        barmode="group",
        title="Share of money vs share of risk (red = at least 10% more risk than money)",
        yaxis_title="% of portfolio",
        legend={"orientation": "h", "x": 0, "y": 1.02, "yanchor": "bottom"},
        margin={"t": 90},
    )
    fig.update_yaxes(ticksuffix="%", automargin=True, title_standoff=16)
    return fig


def _risk_table(table):
    def cell(value, fmt):
        return html.Td(fmt.format(value) if pd.notna(value) else "—")

    header = [
        "Stock",
        "Weight",
        "Risk contribution",
        "Risk/weight",
        "Standalone volatility (yearly)",
    ]
    rows = [
        html.Tr(
            [
                html.Td(ticker, style={"fontWeight": "700"}),
                cell(row["weight"], "{:.1%}"),
                cell(row["risk"], "{:.1%}"),
                html.Td(
                    f"{row['ratio']:.2f}×" if pd.notna(row["ratio"]) else "—",
                    style={
                        "color": theme.NEGATIVE if row["ratio"] >= RISK_HEAVY else theme.TEXT,
                        "fontWeight": "700" if row["ratio"] >= RISK_HEAVY else "400",
                    },
                ),
                cell(row["volatility"], "{:.1%}"),
            ]
        )
        for ticker, row in table.iterrows()
    ]
    return html.Div(
        html.Table(
            [html.Thead(html.Tr([html.Th(h) for h in header])), html.Tbody(rows)],
            className="risk-table",
        ),
        style={"overflowX": "auto"},
    )


@dash.callback(
    Output("covariance-status", "children"),
    Output("covariance-heatmap", "figure"),
    Output("covariance-insights", "children"),
    Output("covariance-metric-portfolio-vol", "children"),
    Output("covariance-metric-spy-vol", "children"),
    Output("covariance-metric-div-ratio", "children"),
    Output("risk-contribution-chart", "figure"),
    Output("risk-takeaway", "children"),
    Output("risk-table", "children"),
    Input("cov_location", "pathname"),
    Input("analysis-period", "value"),
    Input("analysis-benchmark", "value"),
    Input("settings-version", "data"),
)
def refresh_covariance(_pathname, period="1y", benchmark="SPY", _version=None):
    def empty(message):
        return message, px.line(), "", "N/A", "N/A", "N/A", px.line(), "", ""

    holdings = load_data()
    if holdings.empty or holdings.market_value.sum() <= 0:
        return empty("No invested holdings.")
    prices = get_historical_prices(holdings.ticker.tolist() + [benchmark], period)
    if prices.empty:
        return empty(_no_history(period))
    returns = clean_returns(prices.reindex(columns=holdings.ticker.tolist()))
    bench = (
        prices[benchmark].pct_change(fill_method=None).dropna()
        if benchmark in prices
        else pd.Series(dtype=float)
    )
    if not bench.empty:
        common = returns.index.intersection(bench.index)
        returns, bench = returns.loc[common], bench.loc[common]
    status = coverage_text(holdings, returns, period, benchmark)
    if len(returns) < 30 or returns.shape[1] == 0:
        return empty(status + " At least 30 complete common observations are required.")
    values = holdings.set_index("ticker").market_value.reindex(returns.columns)
    weights = values / values.sum()
    cov = valid_covariance(returns)
    w = weights.to_numpy()
    variance = float(w @ cov @ w)
    volatility = np.sqrt(variance * 252)
    avg_vol = float(w @ np.sqrt(np.diag(cov) * 252))
    ratio = avg_vol / volatility if volatility > 0 else None
    corr = returns.corr()
    fig = px.imshow(
        corr,
        zmin=-1,
        zmax=1,
        color_continuous_scale="RdBu",
        title=f"Daily-return correlations ({period})",
        labels={"color": "Correlation"},
    )
    table = risk_vs_weight(returns, weights)
    contribution_fig = _money_vs_risk_chart(table)
    settings = get_settings()
    top = weights.idxmax()
    explanation = [
        html.P(
            f"Largest modeled holding: {top} ({weights[top]:.1%}). Concentration limit: {settings['concentration']:g}%."
        )
    ]
    if weights[top] * 100 > settings["concentration"]:
        explanation.append(html.P("This holding exceeds your configured concentration limit."))
    pairs = [
        (a, b, float(corr.loc[a, b]))
        for i, a in enumerate(corr)
        for b in corr.columns[i + 1 :]
        if pd.notna(corr.loc[a, b])
    ]
    strong = sorted([p for p in pairs if abs(p[2]) >= 0.7], key=lambda p: abs(p[2]), reverse=True)[
        :5
    ]
    explanation.append(
        html.Ul(
            [
                html.Li(f"{a} / {b}: {v:.2f} ({'move together' if v > 0 else 'tend to offset'}).")
                for a, b, v in strong
            ]
        )
        if strong
        else html.P("No pair has absolute correlation of at least 0.70 in this sample.")
    )
    explanation.append(
        html.P(
            "Diversification ratio = weighted average individual volatility / portfolio volatility. It describes this sample, not a guarantee about future diversification."
        )
    )
    return (
        status,
        fig,
        explanation,
        f"{volatility:.2%}",
        f"{bench.std() * np.sqrt(252):.2%}" if len(bench) > 1 else "N/A",
        f"{ratio:.2f}" if ratio is not None else "N/A",
        contribution_fig,
        risk_takeaway(table),
        _risk_table(table),
    )
