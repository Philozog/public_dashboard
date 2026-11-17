"""Sign-in and per-person databases."""

import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from Services import accounts, database


class ParseUsersTests(unittest.TestCase):
    def test_parses_commas_and_new_lines_in_order(self):
        users = accounts.parse_users(" Anna:anna-password ,\nben:pass:with:colons\n")
        self.assertEqual(list(users), ["anna", "ben"])
        self.assertEqual(users["ben"], "pass:with:colons")

    def test_rejects_bad_entries(self):
        for raw in ["anna", "an na:longpassword", "anna:short", "a:longpass1,a:longpass2"]:
            with self.subTest(raw=raw), self.assertRaises(ValueError):
                accounts.parse_users(raw)

    def test_first_person_keeps_original_file(self):
        users = accounts.parse_users("anna:anna-password,ben:ben-password")
        self.assertEqual(accounts.database_for("anna", users), database.DB_PATH)
        self.assertEqual(
            accounts.database_for("ben", users), database.DB_PATH.parent / "users" / "ben.db"
        )


class SignInTests(unittest.TestCase):
    def test_sign_in_and_separate_portfolios(self):
        with tempfile.TemporaryDirectory() as folder:
            env = {
                **os.environ,
                "APOTHICAIRE_DB": str(Path(folder) / "portfolio.db"),
                "DASHBOARD_USERS": "anna:anna-password, ben:ben-password",
                "SECRET_KEY": "test-secret",
                "PYTHONDONTWRITEBYTECODE": "1",
            }
            env.pop("DASHBOARD_PASSWORD", None)
            result = subprocess.run(
                [sys.executable, "-B", str(Path(__file__).with_name("accounts_app.py"))],
                env=env,
                capture_output=True,
                text=True,
                timeout=120,
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertTrue((Path(folder) / "users" / "ben.db").exists())

    def test_mistake_in_user_list_keeps_site_up_but_locked(self):
        with tempfile.TemporaryDirectory() as folder:
            env = {
                **os.environ,
                "APOTHICAIRE_DB": str(Path(folder) / "portfolio.db"),
                "DASHBOARD_USERS": "anna:short",
                "DASHBOARD_PASSWORD": "old-shared-password",
                "PYTHONDONTWRITEBYTECODE": "1",
            }
            code = (
                "import app\n"
                "c = app.server.test_client()\n"
                "assert c.get('/healthz').status_code == 200\n"
                "r = c.get('/login')\n"
                "assert r.status_code == 503 and b'account list has a mistake' in r.data\n"
                "r = c.post('/login', data={'name': 'x', 'password': 'old-shared-password'})\n"
                "assert r.status_code == 503\n"
                "assert c.get('/portfolio').status_code == 302\n"
            )
            result = subprocess.run(
                [sys.executable, "-B", "-c", code],
                cwd=Path(__file__).resolve().parents[1],
                env=env,
                capture_output=True,
                text=True,
                timeout=120,
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("at least 8 characters", result.stderr)
