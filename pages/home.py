from datetime import datetime, timezone

import dash
import plotly.graph_objects as go
from dash import Input, Output, dcc, html

from Services import accounts
from Services.helper import load_data
from Services.home_summary import (
    BENCHMARK,
    MARKET_INDEXES,
    alerts,
    glance,
    market_snapshot,
    time_ago,
)
from Services.insights import prepare_holdings
from Services.market import get_historical_prices
from Services.news import NewsFetchError, fetch_market_news, fetch_portfolio_news
from Services.sentiment import score_articles

dash.register_page(__name__, path="/", name="Home", title="Apothicaire", order=0)


def layout(**_kwargs):
    name = accounts.current_user()
    return html.Div(
        [
            dcc.Store(id="home-name", data=name.title() if name else ""),
            html.Div(
                [
                    html.Div("Apothicaire", className="home-wordmark"),
                    html.H2(id="home-greeting", className="home-greeting"),
                    html.P(id="home-date", className="home-date"),
                ],
                className="home-hero",
            ),
            dcc.Loading(html.Div(id="home-glance", className="home-glance"), type="dot"),
            html.Div(
                [
                    html.Div(
                        [
                            html.H3("Main points of the day", className="card-title"),
                            dcc.Loading(html.Div(id="home-alerts"), type="dot"),
                        ],
                        className="card home-panel",
                    ),
                    html.Div(
                        [
                            html.Div(
                                [
                                    html.H3("Top headlines", className="card-title"),
                                    dcc.Link(
                                        "All news →", href="/sentiment", className="home-more"
                                    ),
                                ],
                                className="home-panel-head",
                            ),
                            dcc.Loading(html.Div(id="home-news"), type="dot"),
                        ],
                        className="card home-panel",
                    ),
                ],
                className="home-panels",
                id="home-panels",
            ),
        ],
        className="home",
    )


# Greeting, date and US market status use the visitor's own clock.
dash.clientside_callback(
    """function(name) {
        const now = new Date();
        const h = now.getHours();
        const part = h < 5 ? 'Good evening' : h < 12 ? 'Good morning' : h < 18 ? 'Good afternoon' : 'Good evening';
        const date = now.toLocaleDateString(undefined, {weekday: 'long', day: 'numeric', month: 'long', year: 'numeric'});
        const et = new Date(now.toLocaleString('en-US', {timeZone: 'America/New_York'}));
        const day = et.getDay(), minute = et.getHours() * 60 + et.getMinutes();
        let market;
        if (day === 0 || day === 6) market = 'US market closed for the weekend';
        else if (minute >= 570 && minute < 960) market = 'US market open until 4:00 pm ET';
        else if (minute < 570) market = 'US market opens at 9:30 am ET';
        else market = 'US market closed, opens 9:30 am ET';
        return [name ? part + ', ' + name : part, date + ' · ' + market + ' (regular hours; holidays not shown)'];
    }""",
    Output("home-greeting", "children"),
    Output("home-date", "children"),
    Input("home-name", "data"),
)


def _signed_pct(value):
    if value is None:
        return html.Span("—", className="muted")
    return html.Span(f"{value:+.2%}", className="home-pos" if value >= 0 else "home-neg")


def _sparkline(series):
    figure = go.Figure(
        go.Scatter(
            x=series.index,
            y=series.values,
            mode="lines",
            line=dict(color="#34d399", width=2),
            fill="tozeroy",
            fillcolor="rgba(52, 211, 153, 0.10)",
            hovertemplate="%{x|%d %b}: $%{y:,.0f}<extra></extra>",
        )
    )
    low, high = float(series.min()), float(series.max())
    pad = (high - low) * 0.1 or high * 0.01 or 1
    figure.update_layout(
        height=70,
        margin=dict(l=0, r=0, t=4, b=0),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        xaxis=dict(visible=False),
        yaxis=dict(visible=False, range=[low - pad, high + pad]),
        showlegend=False,
    )
    return dcc.Graph(figure=figure, config={"displayModeBar": False}, className="home-spark")


def _card(title, main, *details, extra=None):
    return html.Div(
        [
            html.Div(title, className="metric-title"),
            html.Div(main, className="metric-value home-main"),
            *[html.Div(line, className="home-detail") for line in details],
            extra,
        ],
        className="metric-card home-card",
    )


def _glance_cards(data):
    """Only cards (and lines) with real data are shown; nothing says "unavailable"."""
    cards = []

    day = data["day_change"]
    value_lines = []
    if day is not None:
        value_lines.append(
            [
                "Latest day: ",
                html.Span(
                    f"{'+' if day >= 0 else '−'}${abs(day):,.0f}",
                    className="home-pos" if day >= 0 else "home-neg",
                ),
                " (",
                _signed_pct(data["day_pct"]),
                ")",
            ]
        )
    spark = _sparkline(data["spark"]) if len(data["spark"]) >= 2 else None
    cards.append(
        _card(
            "Portfolio value",
            f"${data['value']:,.2f}",
            *value_lines,
            extra=html.Div(
                [spark, html.Div("Today's holdings, last 6 months", className="home-note")]
            )
            if spark is not None
            else None,
        )
    )

    you, spy = data["day_pct"], data["spy_day_pct"]
    if you is not None and spy is not None:
        lines = [["Latest day: you ", _signed_pct(you), " · S&P ", _signed_pct(spy)]]
        if data["ytd_pct"] is not None and data["spy_ytd_pct"] is not None:
            lines.append(
                [
                    "This year: you ",
                    _signed_pct(data["ytd_pct"]),
                    " · S&P ",
                    _signed_pct(data["spy_ytd_pct"]),
                ]
            )
        lines.append(html.Span("Based on today's holdings at past prices.", className="home-note"))
        verdict = "Ahead of the S&P 500" if you >= spy else "Behind the S&P 500"
        cards.append(_card(f"You vs the S&P 500 ({BENCHMARK})", verdict, *lines))

    movers = data["movers"]
    if movers:
        best = movers[0]
        lines = [["Best: ", html.B(best[0]), " ", _signed_pct(best[1])]]
        if len(movers) > 1:
            worst = movers[-1]
            lines.append(["Worst: ", html.B(worst[0]), " ", _signed_pct(worst[1])])
        cards.append(_card("Biggest movers, latest day", best[0], *lines))

    updated = data["updated"]
    if updated is not None:
        cards.append(
            _card(
                "Prices last updated",
                time_ago(updated.to_pydatetime(), datetime.now(timezone.utc)),
                updated.strftime("%d %b, %H:%M UTC"),
                dcc.Link("Refresh on Portfolio →", href="/portfolio", className="home-more"),
            )
        )
    return html.Div(cards, className="home-cards")


def _index_level(row):
    if row["kind"] == "yield":
        return f"{row['last']:.2f}%"
    if row["kind"] == "level":
        return f"{row['last']:.1f}"
    return f"{row['last']:,.2f}"


def _index_change(row):
    change = row["change"]
    css = "home-pos" if change >= 0 else "home-neg"
    if row["kind"] == "yield":  # quoted in percent, so 0.01 = 1 basis point
        text = f"{change * 100:+.0f} bp"
    elif row["kind"] == "level":
        text = f"{change:+.1f} pts"
    else:
        text = f"{row['pct']:+.2%} ({change:+,.0f})"
    return [html.Span(text, className=css), f" on {row['date']:%a %d %b}"]


def _market_cards(rows):
    cards = []
    for row in rows:
        details = [_index_change(row)]
        extra = None
        if row["symbol"] == "^GSPC":
            if row["ytd_pct"] is not None:
                details.append(["This year: ", _signed_pct(row["ytd_pct"])])
            if len(row["spark"]) >= 2:
                extra = html.Div(
                    [_sparkline(row["spark"]), html.Div("Last 3 months", className="home-note")]
                )
        cards.append(_card(row["name"], _index_level(row), *details, extra=extra))
    return (
        html.Div(cards, className="home-cards")
        if cards
        else html.P("Market data is unavailable right now.", className="muted")
    )


def _market_headlines():
    try:
        articles = fetch_market_news(max_items=5)
    except NewsFetchError as exc:
        message = str(exc)
        if "NEWS_API_KEY" in message:
            message = "Add a NewsAPI key to see today's headlines (see README)."
        return html.Div(html.P(message, className="muted"), className="card")
    if not articles:
        return html.Div(
            html.P("No market headlines yet today.", className="muted"), className="card"
        )
    now = datetime.now(timezone.utc)
    scored = score_articles(articles)
    main, rest = scored[0], scored[1:]
    label = main["sentiment"]["label"]
    lead = html.Div(
        [
            html.Div("Main headline of the day", className="metric-title"),
            html.A(
                main["title"],
                href=main["url"],
                target="_blank",
                rel="noopener noreferrer",
                className="home-lead-title",
            ),
            html.P(main["description"], className="home-lead-text")
            if main["description"]
            else None,
            html.Div(
                [
                    html.Span(label.title(), className=f"home-tone home-tone-{label}"),
                    html.Span(
                        f"{main['source']} · {time_ago(main['published_at'], now)}",
                        className="home-note",
                    ),
                ],
                className="home-lead-meta",
            ),
        ],
        className="card home-lead",
    )
    others = (
        html.Div(
            [
                html.H3("Also today", className="card-title"),
                html.Ul(
                    [
                        html.Li(
                            [
                                html.Span(
                                    a["sentiment"]["label"].title(),
                                    className=f"home-tone home-tone-{a['sentiment']['label']}",
                                ),
                                html.Div(
                                    [
                                        html.A(
                                            a["title"],
                                            href=a["url"],
                                            target="_blank",
                                            rel="noopener noreferrer",
                                        ),
                                        html.Div(
                                            f"{a['source']} · {time_ago(a['published_at'], now)}",
                                            className="home-note",
                                        ),
                                    ]
                                ),
                            ],
                            className="home-headline",
                        )
                        for a in rest
                    ],
                    className="home-headlines",
                ),
            ],
            className="card home-panel",
        )
        if rest
        else None
    )
    return html.Div([lead, others], className="home-panels home-market-news")


def _market_view():
    """What someone with no holdings sees: today's market and the day's main headlines."""
    prices = get_historical_prices([symbol for symbol, _, _ in MARKET_INDEXES], period="1y")
    return html.Div(
        [
            html.Div(
                [
                    html.Span("You haven't added any holdings yet, so here is today's market. "),
                    dcc.Link("Add your first holding →", href="/portfolio", className="home-more"),
                ],
                className="home-intro",
            ),
            _market_cards(market_snapshot(prices)),
            _market_headlines(),
        ]
    )


@dash.callback(
    Output("home-glance", "children"),
    Output("home-alerts", "children"),
    Output("home-panels", "style"),
    Input("home-name", "data"),
)
def _load_summary(_name):
    raw = load_data()
    holdings = prepare_holdings(raw)
    if holdings.empty:
        # Nothing of their own to show yet: show the day's market instead.
        return _market_view(), None, {"display": "none"}
    prices = get_historical_prices(list(holdings["ticker"]) + [BENCHMARK], period="1y")
    data = glance(holdings, prices, raw_holdings=raw)
    items = alerts(holdings, raw, data["movers"])
    if not items:
        alert_view = html.P("Nothing stands out today.", className="home-clear")
    else:
        alert_view = html.Ul(
            [html.Li(text, className=f"home-alert home-alert-{level}") for level, text in items],
            className="home-alert-list",
        )
    return _glance_cards(data), alert_view, None


@dash.callback(Output("home-news", "children"), Input("home-name", "data"))
def _load_news(_name):
    holdings = prepare_holdings(load_data())
    if holdings.empty:
        return None  # the market view shows the day's headlines instead
    tickers = list(holdings["ticker"])
    try:
        articles = fetch_portfolio_news(tickers, per_ticker=1, max_items=3)
        if len(articles) < 3:
            articles = fetch_portfolio_news(tickers, per_ticker=3, max_items=3)
    except NewsFetchError as exc:
        message = str(exc)
        if "NEWS_API_KEY" in message:
            message = "Add a NewsAPI key to see headlines (see README)."
        return html.P(message, className="muted")
    if not articles:
        return html.P("No recent headlines about your holdings.", className="muted")
    now = datetime.now(timezone.utc)
    items = []
    for article in score_articles(articles):
        label = article["sentiment"]["label"]
        items.append(
            html.Li(
                [
                    html.Span(label.title(), className=f"home-tone home-tone-{label}"),
                    html.Div(
                        [
                            html.A(
                                article["title"],
                                href=article["url"],
                                target="_blank",
                                rel="noopener noreferrer",
                            ),
                            html.Div(
                                f"{article['ticker']} · {article['source']} · {time_ago(article['published_at'], now)}",
                                className="home-note",
                            ),
                        ]
                    ),
                ],
                className="home-headline",
            )
        )
    return html.Ul(items, className="home-headlines")
