# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

import hashlib
import hmac
import secrets
from http.cookies import CookieError, SimpleCookie

from .domain import Invalid, now
from .store import Store


def password_hash(password: str, salt: str) -> str:
    return hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), 600000).hex()


class Auth:
    def __init__(self, store: Store, password: str, secure_cookie=False):
        if not isinstance(password, str) or len(password) < 14 or len(password) > 1024:
            raise Invalid("Do secrets/admin_password.txt zapiš vlastní heslo dlouhé alespoň 14 znaků.")
        self.store, self.secure_cookie = store, secure_cookie
        current = store.get("credentials")
        if not current or not hmac.compare_digest(password_hash(password, current["salt"]), current["hash"]):
            salt = secrets.token_hex(16)
            store.set("credentials", {"salt": salt, "hash": password_hash(password, salt)})
            store.execute("DELETE FROM sessions")
        store.execute("DELETE FROM sessions WHERE expires<?", (now(),))

    def login(self, username: str, password: str, ip: str, portal=False, secure=False):
        row = self.store.one("SELECT * FROM login_limits WHERE ip=?", (ip,))
        if row and row["until"] > now() and row["failures"] >= 8:
            raise Invalid("Příliš mnoho pokusů. Zkus přihlášení za několik minut.")
        credentials = self.store.get("credentials")
        valid = hmac.compare_digest(password_hash(password[:1024], credentials["salt"]), credentials["hash"])
        if username != "admin" or not valid:
            with self.store.tx() as db:
                failures = (row["failures"] if row and row["until"] > now() else 0) + 1
                db.execute("INSERT OR REPLACE INTO login_limits VALUES(?,?,?)", (ip, failures, now() + 300))
            raise Invalid("Nesprávné jméno nebo heslo.")
        self.store.execute("DELETE FROM login_limits WHERE ip=?", (ip,))
        return self.new_session(portal=portal, secure=secure)

    def new_session(self, portal=False, secure=False):
        token, csrf = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
        self.store.execute("INSERT INTO sessions VALUES(?,?,?)", (hashlib.sha256(token.encode()).hexdigest(), csrf, now() + 12 * 3600))
        return csrf, self.cookie(token, portal=portal, secure=secure)

    def session(self, cookie: str, portal=False):
        try:
            jar = SimpleCookie()
            jar.load(cookie)
            token = jar["mg_portal_session" if portal else "mg_session"].value
        except (CookieError, KeyError, ValueError):
            return None
        if len(token) > 200:
            return None
        row = self.store.one("SELECT * FROM sessions WHERE token=? AND expires>?", (hashlib.sha256(token.encode()).hexdigest(), now()))
        return row

    def cookie(self, token: str, clear=False, portal=False, secure=False):
        name, path = ("mg_portal_session", "/mediagrabber/") if portal else ("mg_session", "/")
        return name + "=" + token + "; Path=" + path + "; HttpOnly; SameSite=Strict; Max-Age=" + ("0" if clear else "43200") + ("; Secure" if self.secure_cookie or secure else "")
