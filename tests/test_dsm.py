"""Real WSGI login routes: no NAS, user files or network access."""
import concurrent.futures
import hashlib
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from mg_nas.app import App
from mg_nas.domain import Invalid
from mg_nas.dsm import DsmBridge

KEY = "abc12345" * 8
PASSWORD = "test-only-password-83942"


class DsmTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        root = Path(self.temp.name)
        self.app = App(root / "data", root / "downloads", PASSWORD, start_worker=False, dsm_key=KEY)

    def tearDown(self):
        self.app.close()
        self.temp.cleanup()

    def request(self, route, method="POST", body=None, headers=None):
        data = json.dumps(body or {}).encode()
        env = {"HTTP_HOST":"localhost:5001", "PATH_INFO":route, "REQUEST_METHOD":method,
               "CONTENT_TYPE":"application/json", "CONTENT_LENGTH":str(len(data)), "wsgi.input":io.BytesIO(data), "REMOTE_ADDR":"127.0.0.1"}
        env.update(headers or {})
        result = {}
        raw = b"".join(self.app(env, lambda status, h: result.update(status=int(status[:3]), headers=dict(h))))
        result["body"] = json.loads(raw) if "application/json" in result["headers"]["Content-Type"] else raw.decode()
        return result

    def ticket(self):
        result = self.request("/api/dsm/issue", headers={"HTTP_X_MG_BRIDGE_KEY":KEY})
        self.assertEqual(result["status"], 200)
        return result["body"]

    def test_no_key_or_claimed_dsm_identity_never_logs_in(self):
        for headers in [{}, {"HTTP_X_MG_BRIDGE_KEY":"x"}, {"HTTP_X_MG_PORTAL":"1", "HTTP_X_DSM_USER":"admin"}]:
            self.assertEqual(self.request("/api/dsm/issue", headers=headers)["status"], 403)
        self.assertEqual(self.request("/api/state", "GET", headers={"HTTP_X_MG_PORTAL":"1"})["status"], 401)
        for ticket in [None, {}, [], 12, "z"*64, "a"*64]:
            self.assertEqual(self.request("/api/dsm/exchange", body={"ticket":ticket}, headers={"HTTP_X_MG_PORTAL":"1"})["status"], 401)

    def test_one_use_login_secure_scoped_cookie_csrf_and_logout(self):
        ticket = self.ticket()
        self.assertEqual(self.app.store.one("SELECT digest FROM dsm_grants")["digest"], hashlib.sha256(ticket.encode()).hexdigest())
        self.assertNotIn(ticket, json.dumps(self.app.backup()))
        self.assertNotIn(KEY, json.dumps(self.app.backup()))
        portal = {"HTTP_X_MG_PORTAL":"1", "HTTP_X_FORWARDED_PROTO":"https", "HTTP_ORIGIN":"https://localhost:5001"}
        result = self.request("/api/dsm/exchange", body={"ticket":ticket}, headers=portal)
        self.assertEqual(result["status"], 200)
        cookie = result["headers"]["Set-Cookie"]
        self.assertTrue(cookie.startswith("mg_portal_session="))
        for attribute in ["Path=/mediagrabber/", "HttpOnly", "SameSite=Strict", "Secure"]:
            self.assertIn(attribute, cookie)
        self.assertEqual(self.request("/api/dsm/exchange", body={"ticket":ticket}, headers=portal)["status"], 401)
        portal["HTTP_COOKIE"] = cookie.split(";", 1)[0]
        self.assertEqual(self.request("/api/state", "GET", headers=portal)["status"], 200)
        self.assertEqual(self.request("/api/logout", headers=portal)["status"], 403)
        portal["HTTP_X_CSRF_TOKEN"] = result["body"]["csrf"]
        logout = self.request("/api/logout", headers=portal)
        self.assertEqual(logout["status"], 200)
        self.assertIn("Max-Age=0", logout["headers"]["Set-Cookie"])
        self.assertEqual(self.request("/api/state", "GET", headers=portal)["status"], 401)

    def test_expiry_restart_and_concurrent_replay(self):
        with patch("mg_nas.dsm.now", return_value=1000):
            ticket = self.ticket()
        with patch("mg_nas.dsm.now", return_value=1060):
            self.assertFalse(self.app.dsm.consume(ticket))
        ticket = self.ticket()
        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
            self.assertEqual(sum(pool.map(self.app.dsm.consume, [ticket]*8)), 1)
        ticket = self.ticket()
        self.assertFalse(DsmBridge(self.app.store, KEY).consume(ticket))

    def test_cross_origin_rejected_without_consuming_ticket(self):
        ticket = self.ticket()
        result = self.request("/api/dsm/exchange", body={"ticket":ticket}, headers={"HTTP_X_MG_PORTAL":"1", "HTTP_ORIGIN":"https://evil.invalid"})
        self.assertEqual(result["status"], 403)
        self.assertTrue(self.app.dsm.consume(ticket))

    def test_password_fallback_direct_and_portal_remain_independent(self):
        for portal in [False, True]:
            headers = {"HTTP_X_MG_PORTAL":"1", "HTTP_X_FORWARDED_PROTO":"https"} if portal else {}
            result = self.request("/api/login", body={"username":"admin", "password":PASSWORD}, headers=headers)
            self.assertEqual(result["status"], 200)
            cookie = result["headers"]["Set-Cookie"]
            self.assertTrue(cookie.startswith("mg_portal_session=" if portal else "mg_session="))
            headers["HTTP_COOKIE"] = cookie.split(";", 1)[0]
            self.assertEqual(self.request("/api/session", "GET", headers=headers)["status"], 200)
            headers["HTTP_X_MG_PORTAL"] = "0" if portal else "1"
            self.assertEqual(self.request("/api/session", "GET", headers=headers)["status"], 401)

    def test_disabled_and_invalid_bridge_fail_closed_and_grants_bounded(self):
        for i in range(200):
            self.app.store.execute("INSERT INTO dsm_grants VALUES(?,?)", (str(i), 9999999999))
        with self.assertRaises(Invalid):
            self.app.dsm.issue(KEY)
        with self.assertRaises(ValueError):
            DsmBridge(self.app.store, "not-a-key")
        self.app.dsm = None
        self.assertEqual(self.request("/api/dsm/issue", headers={"HTTP_X_MG_BRIDGE_KEY":KEY})["status"], 403)
        self.assertEqual(self.request("/api/dsm/exchange", headers={"HTTP_X_MG_PORTAL":"1"})["status"], 401)

    def test_only_portal_allows_same_origin_dsm_framing(self):
        self.assertIn("frame-ancestors 'none'", self.request("/", "GET")["headers"]["Content-Security-Policy"])
        policy = self.request("/", "GET", headers={"HTTP_X_MG_PORTAL":"1"})["headers"]["Content-Security-Policy"]
        self.assertIn("frame-ancestors 'self'", policy)
        self.assertNotIn("frame-ancestors *", policy)
