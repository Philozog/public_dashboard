from dash import html


def metric_card(title, value_id):
    return html.Div(
        [
            html.Div(title, className="metric-title"),
            html.Div("--", id=value_id, className="metric-value"),
        ],
        className="metric-card",
    )


HOLDING_TYPES_EXPLAINED = [
    (
        "Core",
        "The foundation of the portfolio: broad, diversified, lower-risk holdings you plan "
        "to keep for years, such as index funds or large, established companies. "
        "Usually the biggest share (default target 60%).",
    ),
    (
        "High Conviction",
        "Individual picks you have researched and strongly believe in, sized larger than a "
        "speculative bet but riskier than Core because each one depends on a single "
        "company or theme (default target 30%).",
    ),
    (
        "Moonshot",
        "Small, speculative positions with a big upside but a real chance of losing most of "
        "their value, such as early-stage or very volatile stocks. Kept small on purpose "
        "(default target 10%).",
    ),
]


def holding_types_help(open_=False):
    """Collapsible plain-English explanation of the three holding types."""
    return html.Details(
        [
            html.Summary("What do Core, High Conviction and Moonshot mean?"),
            html.Ul(
                [
                    html.Li([html.B(name + ": "), text], style={"marginBottom": "6px"})
                    for name, text in HOLDING_TYPES_EXPLAINED
                ],
                style={"margin": "6px 0 0", "paddingLeft": "20px", "lineHeight": "1.55"},
            ),
            html.P(
                "Targets for each type are set on the Parameters page. The types are labels "
                "for your own planning, not investment advice.",
                className="muted",
                style={"margin": "6px 0 0", "fontSize": "13px"},
            ),
        ],
        open=open_,
        className="holding-types-help",
        style={"marginTop": "12px", "fontSize": "14px"},
    )
