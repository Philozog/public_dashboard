import json
import os

import dash
from dash import Dash, Input, Output, dcc, html
from dotenv import load_dotenv

load_dotenv()

import logging  # noqa: E402

# Show warnings and errors (such as account-setup mistakes) in the host's logs.
logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(name)s: %(message)s")

from Services import accounts
from Services.database import get_engine
from Services.theme import register_template

register_template()


engine = get_engine()

app = Dash(
    __name__,
    use_pages=True,
    suppress_callback_exceptions=True,
    title="AP Terminal",
    # Gzip pages and the app's JavaScript: first visits download far less.
    compress=True,
)
# Parameters and Disclosures live in the small top corner, not the main menu.
CORNER_PAGES = [("Parameters", "/parameters"), ("Disclosures", "/disclosures")]
nav_pages = [
    page
    for page in dash.page_registry.values()
    if page["path"] not in ("/portfolio-news", *(path for _, path in CORNER_PAGES))
]
SIGN_IN_ENABLED = bool(os.environ.get("DASHBOARD_USERS") or os.environ.get("DASHBOARD_PASSWORD"))

app.layout = html.Div(
    [
        dcc.Location(id="url"),
        dcc.Store(id="settings-version", data=0),
        html.Div(
            [
                html.Div(
                    [
                        html.Nav(
                            [
                                dcc.Link(
                                    name,
                                    href=path,
                                    className="corner-link",
                                    id=f"corner-link-{index}",
                                )
                                for index, (name, path) in enumerate(CORNER_PAGES)
                            ],
                            className="corner-links",
                            **{"aria-label": "Parameters and disclosures"},
                        ),
                        html.Div(
                            [
                                html.Span(id="account-label", className="muted"),
                                html.A("Log out", href="/logout", className="logout-link"),
                            ],
                            className="account-bar",
                            style=None if SIGN_IN_ENABLED else {"display": "none"},
                        ),
                    ],
                    className="top-bar",
                ),
                dcc.Link(
                    html.H1("AP Terminal", className="main-title"), href="/", className="title-link"
                ),
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

app.clientside_callback(
    f"""function(path) {{
        const paths = {json.dumps([path for _, path in CORNER_PAGES])};
        return paths.map(p => path === p ? 'corner-link active' : 'corner-link');
    }}""",
    [Output(f"corner-link-{index}", "className") for index in range(len(CORNER_PAGES))],
    Input("url", "pathname"),
)

server = app.server

# Sign-in for hosted copies (see Services/accounts.py). On your own computer,
# with no DASHBOARD_USERS or DASHBOARD_PASSWORD set, nobody is asked to sign in.
accounts.install(server)


@server.route("/healthz")
def _healthz():
    return "ok"


@app.callback(Output("account-label", "children"), Input("url", "pathname"))
def _show_account(_path):
    name = accounts.current_user()
    return f"Signed in as {name}" if name else ""


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
