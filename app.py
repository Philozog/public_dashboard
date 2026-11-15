import hmac
import json
import os

import dash
from dash import Dash, Input, Output, dcc, html
from dotenv import load_dotenv
from flask import Response, request

load_dotenv()

from Services.database import get_engine
from Services.theme import register_template

register_template()


engine = get_engine()

app = Dash(
    __name__,
    use_pages=True,
    suppress_callback_exceptions=True,
    title="Apothicaire",
)
nav_pages = [page for page in dash.page_registry.values() if page["path"] != "/portfolio-news"]

app.layout = html.Div(
    [
        dcc.Location(id="url"),
        dcc.Store(id="settings-version", data=0),
        html.Div(
            [
                html.H1("Apothicaire", className="main-title"),
                # Navigation Bar
                html.Div(
                    [
                        dcc.Link(
                            page["name"],
                            href=page["path"],
                            className="nav-link",
                            id=f"nav-link-{index}",
                        )
                        for index, page in enumerate(nav_pages)
                    ],
                    className="navbar",
                ),
            ],
            id="app-header",
            className="app-header",
        ),
        html.Div(
            [
                html.Div(
                    [
                        html.Label("History window", htmlFor="analysis-period"),
                        dcc.Dropdown(
                            id="analysis-period",
                            options=[
                                {"label": label, "value": value}
                                for label, value in [
                                    ("6 months", "6mo"),
                                    ("1 year", "1y"),
                                    ("3 years", "3y"),
                                    ("5 years", "5y"),
                                ]
                            ],
                            value="1y",
                            clearable=False,
                            persistence=True,
                            persistence_type="local",
                        ),
                    ]
                ),
                html.Div(
                    [
                        html.Label("Benchmark", htmlFor="analysis-benchmark"),
                        dcc.Dropdown(
                            id="analysis-benchmark",
                            options=[{"label": v, "value": v} for v in ["SPY", "QQQ", "VT", "AGG"]],
                            value="SPY",
                            clearable=False,
                            persistence=True,
                            persistence_type="local",
                        ),
                    ]
                ),
                html.Span(
                    "Shared by Analytics, Correlations and Monte Carlo history.", className="muted"
                ),
            ],
            id="analysis-controls",
            className="analysis-controls card",
        ),
        dash.page_container,
    ]
)

# The cover page carries its own wordmark, so hide the global title there.
app.clientside_callback(
    "function(path) { return path === '/' ? 'app-header is-cover' : 'app-header'; }",
    Output("app-header", "className"),
    Input("url", "pathname"),
)

app.clientside_callback(
    f"""function(path) {{
        const paths = {json.dumps([page["path"] for page in nav_pages])};
        return paths.map(linkPath => path === linkPath ? 'nav-link active' : 'nav-link');
    }}""",
    [Output(f"nav-link-{index}", "className") for index in range(len(nav_pages))],
    Input("url", "pathname"),
)

server = app.server

# When hosted on the web, set DASHBOARD_PASSWORD so only you can open it.
# Unset (the default on your own computer), no password is asked.
_password = os.environ.get("DASHBOARD_PASSWORD", "")


@server.route("/healthz")
def _healthz():
    return "ok"


@server.before_request
def _require_password():
    if not _password or request.path == "/healthz":
        return None
    auth = request.authorization
    if auth and hmac.compare_digest(auth.password or "", _password):
        return None
    return Response(
        "Password required.", 401, {"WWW-Authenticate": 'Basic realm="Apothicaire"'}
    )



@server.before_request
def _warm_sentiment_model():
    # On the first request, not at import: the debug reloader's parent process
    # imports this module too but never serves requests.
    from Services.sentiment import start_background_load

    start_background_load()


app.clientside_callback(
    "function(path) { return {display: ['/analytics','/covariance','/monte-carlo'].includes(path) ? 'flex' : 'none'}; }",
    Output("analysis-controls", "style"),
    Input("url", "pathname"),
)
