"""Execute shipped shell CGI with only DSM/curl boundaries mocked; no NAS."""
import os
import json
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SHELL = os.environ.get("MG_TEST_SHELL", "")


@unittest.skipUnless(SHELL, "set MG_TEST_SHELL to run the CGI fixture")
class CgiTests(unittest.TestCase):
    def run_cgi(self, **overrides):
        with tempfile.TemporaryDirectory(prefix="mg-dsm-cgi-") as temp:
            root = Path(temp)
            key = root / "key"
            key.write_text("abcd1234" * 8)
            # Substitute only the private key's location. Function doubles
            # represent unavailable host DSM executables and the HTTP boundary.
            source = (ROOT / "synology/ui/dsm-login.cgi").read_text("utf-8").replace(
                "/var/packages/MediaGrabberNAS/var/runtime/secrets/dsm_bridge_key", key.as_posix())
            source = source.replace('"$syno_auth" &', "mg_native_auth &")
            source = source.replace("export PATH", "export PATH\n" + r'''
timeout() { echo 'forbidden timeout dependency' >&2; exit 127; }
mg_native_auth() {
    printf 'auth\n' >> "$FIXTURE_LOG"
    if [ "$FIXTURE_HANG" = 1 ]; then while :; do :; done; fi
    if [ -n "$FIXTURE_EXPECTED_SYNO" ]; then
        [ "${HTTP_X_SYNO_TOKEN:-}" = "$FIXTURE_EXPECTED_SYNO" ] || return 5
        [ "${QUERY_STRING:-}" = "SynoToken=$FIXTURE_EXPECTED_SYNO" ] || return 7
        [ "${REQUEST_URI:-}" = "/webman/3rdparty/MediaGrabberNAS/dsm-login.cgi?SynoToken=$FIXTURE_EXPECTED_SYNO" ] || return 7
    fi
    printf '%s' "$FIXTURE_USER"; return "$FIXTURE_AUTH_EXIT"
}
id() { printf 'id:%s\n' "$2" >> "$FIXTURE_LOG"; printf '%s' "$FIXTURE_GROUPS"; }
curl() { printf 'curl\n' >> "$FIXTURE_LOG"; cat > "$FIXTURE_CONFIG"; printf '%s' "$FIXTURE_TICKET"; return "$FIXTURE_CURL_EXIT"; }
''')
            script = root / "login.cgi"
            script.write_text(source, "utf-8", newline="\n")
            env = dict(os.environ, REQUEST_METHOD="GET", HTTP_COOKIE="DSM_SESSION=fixture", FIXTURE_USER="Petr",
                       FIXTURE_GROUPS="users administrators", FIXTURE_AUTH_EXIT="0", FIXTURE_CURL_EXIT="0",
                       FIXTURE_HANG="0", FIXTURE_SHELL=SHELL.replace('\\','/'), FIXTURE_EXPECTED_SYNO="",
                       FIXTURE_TICKET="a" * 64, FIXTURE_LOG=(root/"calls").as_posix(), FIXTURE_CONFIG=(root/"curl-config").as_posix())
            env.update(overrides)
            command = [SHELL, "sh"] if "busybox" in Path(SHELL).name.lower() else [SHELL]
            result = subprocess.run([*command, str(script)], env=env, capture_output=True, timeout=10)
            self.assertEqual(result.returncode, 0, result.stderr.decode(errors="replace"))
            output = result.stdout.decode("utf-8")
            self.assertNotIn(key.read_text(), output)
            calls = (root/"calls").read_text("utf-8") if (root/"calls").exists() else ""
            config = (root/"curl-config").read_text("utf-8") if (root/"curl-config").exists() else ""
            return output, calls, config

    def test_admin_and_unicode_admin_receive_fragment_redirect_without_password(self):
        for user in ["Petr", "René", "O'Connor"]:
            output, calls, config = self.run_cgi(FIXTURE_USER=user)
            self.assertIn("Status: 303 See Other", output)
            self.assertIn("Location: /mediagrabber/#dsm-ticket=" + "a"*64, output)
            self.assertIn("id:"+user, calls)
            self.assertIn("curl", calls)
            self.assertIn('url = "http://127.0.0.1:8787/api/dsm/issue"', config)
            self.assertNotIn("DSM_SESSION", config)
            self.assertNotIn("passwd", config)

    def test_anonymous_failed_validation_and_non_admin_never_request_grant(self):
        cases = [(dict(HTTP_COOKIE=""), "401"), (dict(FIXTURE_AUTH_EXIT="1"), "401"),
                 (dict(FIXTURE_USER=""), "401"), (dict(FIXTURE_USER="-root"), "401"),
                 (dict(FIXTURE_USER="Petr\nadmin"), "401"),
                 (dict(FIXTURE_GROUPS="users"), "403"), (dict(FIXTURE_GROUPS="not-administrators"), "403"),
                 (dict(HTTP_SEC_FETCH_SITE="cross-site"), "403"), (dict(REQUEST_METHOD="POST"), "405")]
        for args, status in cases:
            with self.subTest(args=args):
                output, calls, _ = self.run_cgi(**args)
                self.assertIn("Status: " + status, output)
                self.assertNotIn("curl", calls)
                self.assertNotIn("Location:", output)

    def test_unavailable_or_malformed_service_response_keeps_password_fallback(self):
        for args in [dict(FIXTURE_CURL_EXIT="1"), dict(FIXTURE_TICKET="a\nLocation: https://evil.invalid"), dict(FIXTURE_TICKET="x")]:
            output, _, _ = self.run_cgi(**args)
            self.assertIn("Status: 503", output)
            self.assertIn('href="/mediagrabber/"', output)
            self.assertNotIn("Location:", output)

    def test_native_exit_code_is_visible_without_exposing_session_secrets(self):
        for code in [5, 126, 127]:
            output, calls, _ = self.run_cgi(FIXTURE_AUTH_EXIT=str(code), HTTP_X_SYNO_TOKEN="fixture-private-token")
            self.assertIn("DSM-AUTH-"+str(code)+"; token: present", output)
            self.assertNotIn("fixture-private-token", output)
            self.assertNotIn("curl", calls)

    def test_query_token_maps_to_header_without_replacing_existing_header(self):
        token = "fixture-private-token_123"
        output, _, config = self.run_cgi(QUERY_STRING="foo=bar&SynoToken="+token, FIXTURE_EXPECTED_SYNO=token)
        self.assertIn("Status: 303", output)
        self.assertNotIn(token, output+config)
        output, _, _ = self.run_cgi(QUERY_STRING="SynoToken=other", HTTP_X_SYNO_TOKEN=token, FIXTURE_EXPECTED_SYNO=token)
        self.assertIn("Status: 303", output)
        for query in ["SynoToken=a&SynoToken=b", "SynoToken=%0d%0abad", "SynoToken="+"x"*257]:
            output, calls, _ = self.run_cgi(QUERY_STRING=query, FIXTURE_EXPECTED_SYNO=token)
            self.assertIn("DSM-AUTH-5; token: missing", output)
            self.assertNotIn("curl", calls)

    def test_hanging_native_child_is_bounded_without_timeout_utility(self):
        import time
        started = time.monotonic()
        output, calls, _ = self.run_cgi(FIXTURE_HANG="1")
        self.assertLess(time.monotonic()-started, 9)
        self.assertIn("Status: 401", output)
        self.assertIn("DSM-AUTH-", output)
        self.assertNotIn("curl", calls)

    def test_native_json_handoff_requires_valid_session_and_admin_group(self):
        token = "native-loader-token_123"
        output, calls, config = self.run_cgi(HTTP_ACCEPT="application/json", HTTP_X_SYNO_TOKEN=token, FIXTURE_EXPECTED_SYNO=token)
        headers, body = output.split("\r\n\r\n", 1)
        self.assertIn("application/json", headers)
        self.assertNotIn("Location:", headers)
        self.assertEqual(json.loads(body), {"ticket":"a"*64})
        self.assertNotIn(token, output+config)
        for overrides, status in [(dict(FIXTURE_AUTH_EXIT="7"), 401), (dict(FIXTURE_GROUPS="users"), 403)]:
            output, calls, _ = self.run_cgi(HTTP_ACCEPT="application/json", HTTP_X_SYNO_TOKEN=token, **overrides)
            headers, body = output.split("\r\n\r\n", 1)
            self.assertIn("Status: "+str(status), headers)
            self.assertIn("error", json.loads(body))
            self.assertNotIn("curl", calls)

    def test_invalid_header_token_is_rejected_before_native_validator(self):
        for token in ['unsafe"token', "x"*257, "bad\nheader"]:
            output, calls, _ = self.run_cgi(HTTP_ACCEPT="application/json", HTTP_X_SYNO_TOKEN=token)
            self.assertIn("Status: 400", output)
            self.assertEqual(calls, "")


@unittest.skipUnless(SHELL, "set MG_TEST_SHELL to execute native loader CGI")
class NativeLoaderTests(unittest.TestCase):
    def test_loader_injects_only_safe_single_token_and_no_username_or_password(self):
        script = ROOT/"synology/ui/MediaGrabber.cgi"
        command = [SHELL,"sh"] if "busybox" in Path(SHELL).name.lower() else [SHELL]
        cases = [("SynoToken=fixture-token_123", "fixture-token_123"),
                 ("", ""), ("SynoToken=a&SynoToken=b", ""),
                 ('SynoToken=\");alert(1);//', ""), ("SynoToken=%22", ""),
                 ("SynoToken="+"x"*257, "")]
        for query, expected in cases:
            result = subprocess.run([*command,str(script)], env=dict(os.environ,QUERY_STRING=query), capture_output=True, timeout=10)
            self.assertEqual(result.returncode,0,result.stderr.decode(errors="replace"))
            headers, code = result.stdout.decode("utf-8").split("\r\n\r\n",1)
            self.assertIn("application/javascript", headers)
            self.assertIn("Cache-Control: no-store", headers)
            self.assertTrue(code.endswith('})("'+expected+'");\n'))
            self.assertNotIn("alert(1)", code)
