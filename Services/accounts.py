"""Sign-in for a hosted copy: each person gets their own portfolio file.

Configure on the host (never in source control):

    DASHBOARD_USERS   one "name:password" per person, separated by commas or
                      new lines, e.g. "alex:long-pass-1, sam:long-pass-2".
                      The FIRST person listed keeps the original portfolio
                      file; everyone else gets data/users/<name>.db.
    SECRET_KEY        random text that signs the sign-in cookie.

Older setups with only DASHBOARD_PASSWORD keep working: any name plus that
password opens the original portfolio. With neither variable set (running on
your own computer) nobody is asked to sign in.
"""

import hmac
import html
import os
import re
import secrets
import threading
import time
from datetime import timedelta
from pathlib import Path

from flask import Response, g, redirect, request, session

from Services.database import DB_PATH

NAME = re.compile(r"[a-z0-9_-]{1,32}")
MAX_FAILURES = 5
LOCKOUT_SECONDS = 15 * 60
_failures = {}
_failures_lock = threading.Lock()


def parse_users(raw):
    """Return {name: password} in the order given. Raise ValueError on bad input."""
    users = {}
    for entry in re.split(r"[,\n]", raw or ""):
        entry = entry.strip()
        if not entry:
            continue
        name, sep, password = entry.partition(":")
        name = name.strip().lower()
        if not sep or not NAME.fullmatch(name):
            raise ValueError(
                f"DASHBOARD_USERS entry {name or entry[:12]!r} must look like name:password; "
                "names use only a-z, 0-9, - and _."
            )
        if len(password) < 8:
            raise ValueError(f"Password for {name!r} must be at least 8 characters.")
        if name in users:
            raise ValueError(f"{name!r} is listed twice in DASHBOARD_USERS.")
        users[name] = password
    return users


def database_for(name, users):
    """The first listed person keeps the original file; the rest get their own."""
    if not users or name == next(iter(users)):
        return DB_PATH
    return DB_PATH.parent / "users" / f"{name}.db"


def _client():
    # Render puts the visitor's address first in X-Forwarded-For.
    forwarded = request.headers.get("X-Forwarded-For", "")
    return forwarded.split(",")[0].strip() or request.remote_addr or "?"


def _locked_out(client):
    with _failures_lock:
        stamps = [t for t in _failures.get(client, []) if time.time() - t < LOCKOUT_SECONDS]
        _failures[client] = stamps
        return len(stamps) >= MAX_FAILURES


def _record_failure(client):
    with _failures_lock:
        _failures.setdefault(client, []).append(time.time())


def _check(users, shared_password, name, password):
    """Return the signed-in name, or None. Compares every entry to keep timing flat."""
    match = None
    for candidate, expected in users.items():
        ok = hmac.compare_digest(candidate.encode(), name.encode())
        ok &= hmac.compare_digest(expected.encode(), password.encode())
        if ok:
            match = candidate
    if (
        not users
        and shared_password
        and hmac.compare_digest(shared_password.encode(), password.encode())
    ):
        match = name or "owner"
    return match


LOGIN_PAGE = """<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Sign in · Apothicaire</title>
<style>
  :root {{ color-scheme: dark; }}
  body {{ margin: 0; min-height: 100vh; display: grid; place-items: center;
    background: #0b1220; color: #e2e8f0; font: 16px/1.5 system-ui, sans-serif; }}
  form {{ width: min(360px, calc(100vw - 32px)); padding: 28px; border-radius: 14px;
    background: #111a2e; border: 1px solid rgba(148,163,184,.18); box-sizing: border-box; }}
  h1 {{ margin: 0 0 4px; font-size: 24px; letter-spacing: .08em; color: #34d399; }}
  p {{ margin: 0 0 20px; color: #94a3b8; font-size: 14px; }}
  label {{ display: block; margin: 14px 0 6px; font-size: 14px; }}
  input {{ width: 100%; box-sizing: border-box; padding: 11px 12px; border-radius: 8px;
    border: 1px solid rgba(148,163,184,.3); background: #0b1220; color: inherit; font: inherit; }}
  button {{ width: 100%; margin-top: 22px; padding: 12px; border: 0; border-radius: 8px;
    background: #10b981; color: #052e1f; font: 600 16px system-ui, sans-serif; cursor: pointer; }}
  .error {{ margin: 14px 0 0; color: #fca5a5; font-size: 14px; }}
</style></head>
<body><form method="post" action="/login">
  <h1>APOTHICAIRE</h1>
  <p>Sign in to see your portfolio.</p>
  <label for="name">Name</label>
  <input id="name" name="name" autocomplete="username" autocapitalize="none" value="{name}" required>
  <label for="password">Password</label>
  <input id="password" name="password" type="password" autocomplete="current-password" required>
  <input type="hidden" name="next" value="{next}">
  {error}
  <button type="submit">Sign in</button>
</form></body></html>"""


def _login_page(error="", name="", next_path="/", status=200):
    body = LOGIN_PAGE.format(
        name=html.escape(name),
        next=html.escape(next_path),
        error=f'<p class="error" role="alert">{html.escape(error)}</p>' if error else "",
    )
    return Response(body, status, {"Cache-Control": "no-store"})


def _safe_next(value):
    # Only same-site paths, never "//other.site" or a full URL.
    return value if value.startswith("/") and not value.startswith("//") else "/"


def install(server):
    """Add sign-in to the Flask server when the host configures accounts."""
    users = parse_users(os.environ.get("DASHBOARD_USERS", ""))
    shared_password = os.environ.get("DASHBOARD_PASSWORD", "")
    enabled = bool(users or shared_password)
    server.config["ACCOUNTS_ENABLED"] = enabled
    if not enabled:
        return
    server.secret_key = os.environ.get("SECRET_KEY") or secrets.token_hex(32)
    server.config.update(
        PERMANENT_SESSION_LIFETIME=timedelta(days=30),
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
        # Render serves over HTTPS and sets RENDER=true.
        SESSION_COOKIE_SECURE=bool(os.environ.get("RENDER")),
    )

    @server.route("/login", methods=["GET", "POST"])
    def _login():
        if request.method == "GET":
            return _login_page(next_path=_safe_next(request.args.get("next", "/")))
        client = _client()
        name = request.form.get("name", "").strip().lower()
        next_path = _safe_next(request.form.get("next", "/"))
        if _locked_out(client):
            return _login_page(
                "Too many wrong attempts. Wait 15 minutes and try again.", name, next_path, 429
            )
        signed_in = _check(users, shared_password, name, request.form.get("password", ""))
        if not signed_in:
            _record_failure(client)
            return _login_page("Wrong name or password.", name, next_path, 401)
        session.clear()
        session.permanent = True
        session["user"] = signed_in
        return redirect(next_path)

    @server.route("/logout")
    def _logout():
        session.clear()
        return redirect("/login")

    @server.before_request
    def _require_sign_in():
        if request.path in ("/healthz", "/login", "/logout"):
            return None
        name = session.get("user")
        if name and (name in users or (not users and shared_password)):
            g.user = name
            g.db_path = str(database_for(name, users))
            return None
        session.clear()
        if request.method == "GET" and not request.path.startswith("/_"):
            return redirect(f"/login?next={request.full_path.rstrip('?')}")
        return Response("Sign-in required.", 401)


def current_user():
    try:
        return g.get("user")
    except RuntimeError:
        return None


def database_path_for_request():
    """The signed-in person's portfolio file, or None outside a signed-in request."""
    try:
        value = g.get("db_path")
    except RuntimeError:  # no request in progress
        return None
    return Path(value) if value else None
