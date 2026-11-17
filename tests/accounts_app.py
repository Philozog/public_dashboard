"""Run in a separate process: sign in as two people and check their data is separate."""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import app  # noqa: E402

client = app.server.test_client()


def sign_in(name, password):
    c = app.server.test_client()
    r = c.post("/login", data={"name": name, "password": password, "next": "/portfolio"})
    return c, r


# Not signed in: pages redirect to the sign-in page, Dash API calls are refused.
r = client.get("/portfolio")
assert r.status_code == 302 and "/login" in r.headers["Location"], r.status_code
assert client.post("/_dash-update-component", json={}).status_code == 401
assert client.get("/healthz").status_code == 200
assert client.get("/login").status_code == 200

# Wrong password.
c, r = sign_in("anna", "wrong-password")
assert r.status_code == 401 and b"Wrong name or password" in r.data

# Open-redirect attempt is neutralised.
c, r = sign_in("anna", "anna-password")
assert r.status_code == 302 and r.headers["Location"].endswith("/portfolio")
c2 = app.server.test_client()
r = c2.post("/login", data={"name": "anna", "password": "anna-password", "next": "//evil.example"})
assert r.headers["Location"] == "/", r.headers["Location"]

# Each person writes to and reads from their own file.
from Services import accounts, ledger  # noqa: E402

for name, password, ticker in [("anna", "anna-password", "AAA"), ("Ben", "ben-password", "BBB")]:
    c, r = sign_in(name, password)
    assert r.status_code == 302, (name, r.status_code)
    assert c.get("/portfolio").status_code == 200
    with app.server.test_request_context():
        from flask import g

        users = accounts.parse_users(app.os.environ["DASHBOARD_USERS"])
        g.user = name.lower()
        g.db_path = str(accounts.database_for(name.lower(), users))
        ledger.transact("buy", ticker=ticker, shares=1, price=10, holding_type="Core")

seen = {}
for name in ("anna", "ben"):
    users = accounts.parse_users(app.os.environ["DASHBOARD_USERS"])
    history = ledger.transaction_history(accounts.database_for(name, users))
    seen[name] = sorted(history.ticker)
assert seen == {"anna": ["AAA"], "ben": ["BBB"]}, seen

# A signed-in Dash request sees only that person's holdings.
c, _ = sign_in("ben", "ben-password")
r = c.post(
    "/_dash-update-component",
    json={
        "output": "account-label.children",
        "outputs": {"id": "account-label", "property": "children"},
        "inputs": [{"id": "url", "property": "pathname", "value": "/portfolio"}],
        "changedPropIds": ["url.pathname"],
    },
)
assert r.status_code == 200, (r.status_code, r.data[:300])
assert "Signed in as ben" in json.dumps(r.get_json()), r.get_json()

# Log out ends the session.
assert c.get("/logout").status_code == 302
assert c.get("/portfolio").status_code == 302

# Five wrong attempts lock that address out, even with the right password next.
lock = app.server.test_client()
for _ in range(5):
    lock.post(
        "/login",
        data={"name": "anna", "password": "nope-nope"},
        environ_base={"REMOTE_ADDR": "9.9.9.9"},
    )
r = lock.post(
    "/login",
    data={"name": "anna", "password": "anna-password"},
    environ_base={"REMOTE_ADDR": "9.9.9.9"},
)
assert r.status_code == 429, r.status_code
print("Accounts check passed.")
