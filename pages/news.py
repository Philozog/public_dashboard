"""News: the day's market headlines for everyone, portfolio or not."""

from datetime import datetime, timezone

import dash
from dash import Input, Output, dcc, html

from Services.home_summary import time_ago
from Services.news import NewsFetchError, fetch_market_news
from Services.sentiment import score_articles

dash.register_page(__name__, path="/news", name="News", title="News", order=6)

MAX_HEADLINES = 20


def layout(**_kwargs):
    return html.Div(
        [
            html.Div(
                [
                    html.Div("Markets", className="page-eyebrow"),
                    html.H2("Today's news", className="page-title"),
                    html.P(
                        "The main US business and market headlines, most market-related first. "
                        "Updated about every 30 minutes. Tags are automated and can be wrong.",
                        className="page-subtitle",
                    ),
                ],
                className="page-header",
            ),
            dcc.Location(id="news-location"),
            dcc.Loading(html.Div(id="news-list"), type="dot"),
        ]
    )


def _headline(article, now):
    label = article["sentiment"]["label"]
    return html.Li(
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
                    html.P(article["description"], className="news-page-text")
                    if article.get("description")
                    else None,
                    html.Div(
                        f"{article['source']} · {time_ago(article['published_at'], now)}",
                        className="home-note",
                    ),
                ]
            ),
        ],
        className="home-headline",
    )


@dash.callback(Output("news-list", "children"), Input("news-location", "pathname"))
def _load(_path):
    try:
        articles = fetch_market_news(max_items=MAX_HEADLINES)
    except NewsFetchError as exc:
        message = str(exc)
        if "NEWS_API_KEY" in message:
            message = "Headlines need a NewsAPI key on the server (see README)."
        return html.Div(html.P(message, className="muted"), className="card")
    if not articles:
        return html.Div(html.P("No headlines yet today.", className="muted"), className="card")
    now = datetime.now(timezone.utc)
    scored = score_articles(articles)
    lead, rest = scored[0], scored[1:]
    label = lead["sentiment"]["label"]
    return html.Div(
        [
            html.Div(
                [
                    html.Div("Top story", className="metric-title"),
                    html.A(
                        lead["title"],
                        href=lead["url"],
                        target="_blank",
                        rel="noopener noreferrer",
                        className="home-lead-title",
                    ),
                    html.P(lead["description"], className="home-lead-text")
                    if lead.get("description")
                    else None,
                    html.Div(
                        [
                            html.Span(label.title(), className=f"home-tone home-tone-{label}"),
                            html.Span(
                                f"{lead['source']} · {time_ago(lead['published_at'], now)}",
                                className="home-note",
                            ),
                        ],
                        className="home-lead-meta",
                    ),
                ],
                className="card home-lead",
            ),
            html.Div(
                [
                    html.H3("More headlines", className="card-title"),
                    html.Ul([_headline(a, now) for a in rest], className="home-headlines"),
                ],
                className="card",
            )
            if rest
            else None,
        ]
    )
