"""Offline tests for public release checks, persistent fallback and failure limits."""
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from mg_nas.releases import API_URL, CACHE_KEY, CHECK_INTERVAL, MAX_RESPONSE, RETRY_INTERVAL, WindowsRelease
from mg_nas.store import Store

STAMP = 1_800_000_000


def release(tag="v4.3.0"):
    return {"tag_name": tag, "draft": False, "prerelease": False,
            "assets": [{"name": "MediaGrabber-4.3.0-Windows-x64-Portable.zip"}]}


class Response(io.BytesIO):
    status = 200

    def geturl(self):
        return API_URL


class ReleaseTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.store = Store(Path(self.temp.name))
        self.clock = patch("mg_nas.releases.time.time", return_value=STAMP)
        self.clock.start()
        self.client = WindowsRelease(self.store)

    def tearDown(self):
        self.clock.stop()
        self.store.close()
        self.temp.cleanup()

    def test_success_uses_fixed_public_endpoint_and_caches_without_credentials(self):
        with patch("mg_nas.releases.urlopen", return_value=Response(json.dumps(release()).encode())) as opened:
            result = self.client.get()
            self.assertEqual(result["status"], "current")
            self.assertEqual(result["version"], "4.3.0")
            self.assertEqual(result["url"], "https://github.com/petrjones/MediaGrabber/releases/tag/v4.3.0")
            request = opened.call_args.args[0]
            self.assertEqual(request.full_url, API_URL)
            self.assertIsNone(request.data)
            self.assertIsNone(request.get_header("Authorization"))
            self.assertIsNone(request.get_header("Cookie"))
            self.assertEqual(opened.call_args.kwargs["timeout"], 3)
            self.client.get()
            WindowsRelease(self.store).get()
            self.assertEqual(opened.call_count, 1)

    def test_expired_cache_refreshes_to_new_release(self):
        self.store.set(CACHE_KEY, {"tag": "v4.2.0", "checked_at": STAMP - CHECK_INTERVAL - 1})
        self.client = WindowsRelease(self.store)
        with patch("mg_nas.releases.urlopen", return_value=Response(json.dumps(release()).encode())):
            self.assertEqual(self.client.get()["version"], "4.3.0")
        self.assertEqual(self.store.get(CACHE_KEY)["tag"], "v4.3.0")

    def test_failure_keeps_persistent_value_and_backs_off_then_recovers(self):
        self.store.set(CACHE_KEY, {"tag": "v4.3.0", "checked_at": STAMP - CHECK_INTERVAL - 1})
        self.client = WindowsRelease(self.store)
        with patch("mg_nas.releases.urlopen", side_effect=TimeoutError) as opened:
            result = self.client.get()
            self.assertEqual(result["status"], "cached")
            self.assertEqual(result["version"], "4.3.0")
            self.client.get()
            self.assertEqual(opened.call_count, 1)
        with patch("mg_nas.releases.time.time", return_value=STAMP + RETRY_INTERVAL + 1), \
                patch("mg_nas.releases.urlopen", return_value=Response(json.dumps(release("v4.4.0")).encode())):
            result = self.client.get()
            self.assertEqual((result["status"], result["version"]), ("current", "4.4.0"))
        self.assertEqual(self.store.get(CACHE_KEY)["tag"], "v4.4.0")

    def test_fresh_install_offline_never_invents_a_version(self):
        with patch("mg_nas.releases.urlopen", side_effect=OSError) as opened:
            for _ in range(3):
                result = self.client.get()
                self.assertEqual(result["status"], "unavailable")
                self.assertIsNone(result["version"])
                self.assertEqual(result["url"], "https://github.com/petrjones/MediaGrabber/releases/latest")
            self.assertEqual(opened.call_count, 1)
        self.assertIsNone(self.store.get(CACHE_KEY))

    def test_rate_limit_preserves_cache_across_client_restart(self):
        self.store.set(CACHE_KEY, {"tag": "v4.3.0", "checked_at": STAMP - CHECK_INTERVAL - 1})
        with patch("mg_nas.releases.urlopen", side_effect=OSError("HTTP 403 rate limited")):
            self.assertEqual(WindowsRelease(self.store).get()["status"], "cached")
            self.assertEqual(WindowsRelease(self.store).get()["version"], "4.3.0")

    def test_non_windows_drafts_prereleases_and_invalid_tags_are_rejected(self):
        values = [release("nas-v0.1.0-beta.20"), release("v4.4.0-beta.1"), release("../../bad"),
                  release() | {"prerelease": True}, release() | {"draft": True},
                  release() | {"assets": [{"name": "MediaGrabber-NAS-0.1.0-0020.spk"}]},
                  release() | {"assets": None}, [], {"tag_name": "v4.3.0"}]
        for value in values:
            with self.subTest(value=value), patch("mg_nas.releases.urlopen", return_value=Response(json.dumps(value).encode())):
                self.assertEqual(WindowsRelease(self.store).get()["status"], "unavailable")

    def test_invalid_or_oversized_responses_are_not_cached(self):
        for value in [b"not-json", b"x" * (MAX_RESPONSE + 1)]:
            with self.subTest(length=len(value)), patch("mg_nas.releases.urlopen", return_value=Response(value)):
                self.assertEqual(WindowsRelease(self.store).get()["status"], "unavailable")

    def test_unexpected_status_or_redirect_is_rejected(self):
        for field, value in [("status", 503), ("geturl", lambda: "https://example.test/")]:
            response = Response(json.dumps(release()).encode())
            setattr(response, field, value)
            with self.subTest(field=field), patch("mg_nas.releases.urlopen", return_value=response):
                self.assertEqual(WindowsRelease(self.store).get()["status"], "unavailable")

    def test_corrupt_cache_and_future_timestamps_are_ignored(self):
        for value in [None, [], {"tag": "evil", "checked_at": STAMP},
                      {"tag": "v4.3.0", "checked_at": float("inf")},
                      {"tag": "v4.3.0", "checked_at": STAMP + 1000},
                      {"tag": "v4.3.0", "checked_at": True}]:
            with self.subTest(value=value):
                self.store.set(CACHE_KEY, value)
                with patch("mg_nas.releases.urlopen", side_effect=OSError):
                    self.assertEqual(WindowsRelease(self.store).get()["status"], "unavailable")


if __name__ == "__main__":
    unittest.main()
