import dash
from dash import Input, Output, State, dcc, html, no_update

from Services.components import holding_types_help
from Services.database import backup_database, utc_now
from Services.settings import get_settings, save_settings

dash.register_page(
    __name__,
    path="/parameters",
    name="Parameters",
    title="Parameters",
    order=7,
    redirect_from=["/settings"],
)


def layout():
    settings = get_settings()
    fields = [
        ("Core (%)", "target-core", settings["targets"]["Core"]),
        ("High Conviction (%)", "target-conviction", settings["targets"]["High Conviction"]),
        ("Moonshot (%)", "target-moonshot", settings["targets"]["Moonshot"]),
        ("Single holding limit (%)", "concentration-limit", settings["concentration"]),
        (
            "Drift tolerance (pts)",
            "drift-tolerance",
            settings["drift_tolerance"],
        ),
        ("Risk-free rate (%)", "risk-free", settings["risk_free"] * 100),
    ]
    return html.Div(
        [
            html.H2("Risk parameters", className="page-title"),
            html.P(
                "Targets must total 100%. These parameters apply to analytics, allocation and concentration checks."
            ),
            holding_types_help(),
            html.Div(
                [
                    html.Div(
                        [
                            html.Label(label, htmlFor=key),
                            dcc.Input(
                                id=key, type="number", min=0, max=100, step="any", value=value
                            ),
                        ]
                    )
                    for label, key, value in fields
                ],
                className="settings-grid",
            ),
            html.Button("Save parameters", id="save-risk-settings", n_clicks=0),
            html.Div(id="settings-status", role="status"),
            html.H3("Data backups"),
            html.P(
                "Backups contain your holdings, transactions and parameters. Keep a separate copy outside this machine."
            ),
            html.Button("Create database backup", id="backup-btn", n_clicks=0),
            html.Div(id="backup-status", role="status"),
        ],
        className="card",
    )


@dash.callback(
    Output("settings-status", "children"),
    Output("settings-version", "data"),
    Input("save-risk-settings", "n_clicks"),
    State("target-core", "value"),
    State("target-conviction", "value"),
    State("target-moonshot", "value"),
    State("concentration-limit", "value"),
    State("drift-tolerance", "value"),
    State("risk-free", "value"),
    prevent_initial_call=True,
)
def save(_clicks, core, conviction, moonshot, concentration, tolerance, rf):
    try:
        save_settings(
            {"Core": core, "High Conviction": conviction, "Moonshot": moonshot},
            concentration,
            tolerance,
            float(rf) / 100,
        )
    except (ValueError, TypeError) as exc:
        return f"Not saved: {exc}", no_update
    return "Parameters saved.", utc_now()


@dash.callback(
    Output("backup-status", "children"), Input("backup-btn", "n_clicks"), prevent_initial_call=True
)
def backup(_clicks):
    target = backup_database()
    return f"Backup created: {target.name}" if target else "No database is available to back up."
