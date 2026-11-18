import dash
import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from dash import Input, Output, dcc, html

from Services import theme
from Services.helper import load_data
from Services.market import (
    clean_returns,
    get_historical_prices,
)
from Services.market import (
    no_history_message as _no_history,
)
from Services.performance import RISK_HEAVY, risk_takeaway, risk_vs_weight, valid_covariance
from Services.settings import get_settings
from Services.theme import blank_figure

dash.register_page(__name__, path="/covariance", name="Correlations", title="Correlations", order=3)

_PERIOD_LABEL = {"6mo": "6 months", "1y": "1 year", "3y": "3 years", "5y": "5 years"}


def _explained_card(title, value_id, meaning):
    return html.Div(
        [
            html.Div(title, className="metric-title"),
            html.Div("--", id=value_id, className="metric-value"),
            html.Div(meaning, className="muted", style={"fontSize": "12px", "marginTop": "6px"}),
        ],
        className="metric-card",
    )


def _diversification_text(ratio, avg_vol, volatility):
    if ratio is None:
        return ""
    return (
        f"Your stocks swing about {avg_vol:.0%} a year on their own, but together only "
        f"{volatility:.0%}, because they don't all move at once. 1.0× would mean no benefit; "
        "higher is better."
    )


def _plain_status(holdings, returns, period, benchmark):
    values = holdings.groupby("ticker")["market_value"].sum()
    included = list(returns.columns)
    total = float(values.sum())
    covered = float(values.reindex(included).fillna(0).sum()) / total if total else 0
    missing = sorted(set(values.index) - set(included))
    if returns.empty:
        return f"No common price history for the last {_PERIOD_LABEL.get(period, period)}."
    text = (
        f"Based on {len(returns)} trading days of prices ({returns.index.min():%d %b %Y} to "
        f"{returns.index.max():%d %b %Y}) for {len(included)} of {len(values)} holdings "
        f"({covered:.0%} of your money), compared with {benchmark}."
    )
    if missing:
        text += f" Left out (no price history): {', '.join(missing)}."
    return text


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
                            _explained_card(
                                "Your portfolio's yearly swings",
                                "covariance-metric-portfolio-vol",
                                "In a typical year, your portfolio's value moves up or down by about "
                                "this much (annualized volatility).",
                            ),
                            _explained_card(
                                "Market's yearly swings",
                                "covariance-metric-spy-vol",
                                "The same measure for the benchmark chosen at the top of the page, "
                                "for comparison. Higher than the market means a bumpier ride.",
                            ),
                            _explained_card(
                                "Diversification benefit",
                                "covariance-metric-div-ratio",
                                html.Span(id="covariance-div-explain"),
                            ),
                        ],
                        className="summary-grid",
                    ),
                    html.Div(id="covariance-status", className="data-status"),
                    html.P(
                        "The grid below shows how each pair of stocks moves together: 1 = always "
                        "move together, 0 = unrelated, -1 = move in opposite directions. Pairs that "
                        "move together give less protection when markets fall.",
                        className="muted",
                        style={"fontSize": "13px", "margin": "0 0 4px"},
                    ),
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
    Output("covariance-div-explain", "children"),
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
        return message, px.line(), "", "N/A", "N/A", "N/A", "", px.line(), "", ""

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
    status = _plain_status(holdings, returns, period, benchmark)
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
        title=f"How your stocks move together ({_PERIOD_LABEL.get(period, period)})",
        labels={"color": "Moves together"},
    )
    table = risk_vs_weight(returns, weights)
    contribution_fig = _money_vs_risk_chart(table)
    settings = get_settings()
    top = weights.idxmax()
    explanation = [
        html.P(
            f"Largest holding: {top} ({weights[top]:.1%} of your money). Your limit for a single "
            f"holding: {settings['concentration']:g}%."
        )
    ]
    if weights[top] * 100 > settings["concentration"]:
        explanation.append(html.P("This holding is above your limit (set on the Parameters page)."))
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
                html.Li(
                    f"{a} and {b}: {v:.2f} "
                    f"({'strongly move together' if v > 0 else 'tend to move in opposite directions'})."
                )
                for a, b, v in strong
            ]
        )
        if strong
        else html.P("No two holdings move closely together (none at 0.70 or above) in this period.")
    )
    explanation.append(
        html.P(
            "These figures describe the chosen period and can change, especially in a crisis, "
            "when stocks tend to move together more.",
            className="muted",
        )
    )
    return (
        status,
        fig,
        explanation,
        f"{volatility:.1%}",
        f"{bench.std() * np.sqrt(252):.1%}" if len(bench) > 1 else "N/A",
        f"{ratio:.2f}×" if ratio is not None else "N/A",
        _diversification_text(ratio, avg_vol, volatility),
        contribution_fig,
        risk_takeaway(table),
        _risk_table(table),
    )
