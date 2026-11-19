# SPDX-License-Identifier: GPL-3.0-or-later
"""One-use DSM launch grants; the bridge itself uses no DSM cookies/passwords."""
from __future__ import annotations

import hashlib
import hmac
import re
import secrets

from .domain import Invalid, now


class DsmBridge:
    def __init__(self, store, key):
        if not re.fullmatch(r"[a-f0-9]{64}", key):
            raise ValueError("Invalid private DSM bridge key.")
        self.store, self.key = store, key
        store.execute("CREATE TABLE IF NOT EXISTS dsm_grants (digest TEXT PRIMARY KEY, expires INTEGER NOT NULL)")
        # Grants do not survive an application restart or package upgrade.
        store.execute("DELETE FROM dsm_grants")

    def issue(self, key):
        if not isinstance(key, str) or not re.fullmatch(r"[a-f0-9]{64}", key) or not hmac.compare_digest(self.key, key):
            return None
        token = secrets.token_hex(32)
        with self.store.tx() as db:
            db.execute("DELETE FROM dsm_grants WHERE expires<=?", (now(),))
            if db.execute("SELECT count(*) FROM dsm_grants").fetchone()[0] >= 200:
                raise Invalid("Příliš mnoho otevřených přihlášení DSM. Zkus to za minutu.")
            db.execute("INSERT INTO dsm_grants VALUES(?,?)", (hashlib.sha256(token.encode()).hexdigest(), now() + 60))
        return token

    def consume(self, token):
        if not isinstance(token, str) or not re.fullmatch(r"[a-f0-9]{64}", token):
            return False
        digest = hashlib.sha256(token.encode()).hexdigest()
        with self.store.tx() as db:
            row = db.execute("SELECT expires FROM dsm_grants WHERE digest=?", (digest,)).fetchone()
            db.execute("DELETE FROM dsm_grants WHERE digest=?", (digest,))
            return row is not None and row[0] > now()
