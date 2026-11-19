"""Offline regression tests. Never access YouTube or the user's media."""
import datetime as dt
import io
import json
import tempfile
import unittest
import uuid
from pathlib import Path
from unittest.mock import patch

from mg_nas.app import App, source_config
from mg_nas.domain import DEFAULTS, Invalid, destination, in_window, indices, now, options, safe_name, settings, youtube_url
from mg_nas.engine import Engine, EngineError, Interrupted
from mg_nas.store import encode

PASSWORD = "test-only-password-83942"
IDS = ["AAAAAAAAAAA", "BBBBBBBBBBB", "CCCCCCCCCCC"]


def entry(index=0, position=None):
    identifier = IDS[index]
    return {"id": identifier, "url": "https://www.youtube.com/watch?v=" + identifier,
            "title": "Track " + str(index + 1), "position": position or index + 1}


class FakeEngine:
    def __init__(self):
        self.entries = [entry(0), entry(1)]
        self.list_calls, self.download_calls = [], []
        self.failures = {}
        self.interrupt = ""

    def listing(self, url, playlist=True, stop=lambda: "", selected=None):
        if reason := stop():
            raise Interrupted(reason)
        self.list_calls.append((url, selected))
        return {"title": "Test album", "entries": [e for e in self.entries if not selected or e["position"] in selected]}

    def download(self, item, opts, base, config, stop, progress, date_after=""):
        self.download_calls.append((item["media_id"], date_after))
        if self.interrupt:
            raise Interrupted(self.interrupt)
        if reason := stop():
            raise Interrupted(reason)
        if failure := self.failures.get(item["media_id"]):
            raise failure
        progress(50)
        path = base.with_suffix(".mp3")
        path.write_bytes(b"offline audio fixture")
        return {"paths": [str(path)], "notice": "", "filtered": False}


class DomainTests(unittest.TestCase):
    def test_url_canonicalization_and_restrictions(self):
        self.assertEqual(youtube_url("https://youtu.be/AAAAAAAAAAA?t=2", False), entry()["url"])
        self.assertIn("/playlist?list=PLabcdefgh", youtube_url(entry()["url"] + "&list=PLabcdefgh"))
        self.assertEqual(youtube_url("https://www.youtube.com/@PJSoft", source=True), "https://www.youtube.com/@PJSoft")
        with self.assertRaises(Invalid):
            youtube_url("https://www.youtube.com/@PJSoft", playlist=False)
        for url in ["http://youtube.com/watch?v=AAAAAAAAAAA", "https://youtube.com.evil.test/watch?v=AAAAAAAAAAA", "https://user:pass@youtube.com/watch?v=AAAAAAAAAAA", "file:///etc/passwd", "https://127.0.0.1/"]:
            with self.subTest(url=url), self.assertRaises(Invalid):
                youtube_url(url)

    def test_channel_tabs_are_not_invented(self):
        for path in ('@anetkasimkova', 'channel/UCabcdefghijklmno', 'c/Example', 'user/Example'):
            for suffix in ('', '/videos', '/shorts', '/streams'):
                url = 'https://www.youtube.com/' + path + suffix
                self.assertEqual(youtube_url(url, source=True), url)

    def test_paths_and_names(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.assertEqual(destination(root, "music/albums"), root / "music/albums")
            for value in ["../other", "/outside", "music/../other", "C:/temp", "music\\other", "a\x00b"]:
                with self.subTest(value=value), self.assertRaises(Invalid):
                    destination(root, value)
            self.assertEqual(safe_name("CON"), "Zaznam")
            self.assertNotIn("/", safe_name("a/b:*?"))
            self.assertLessEqual(len(safe_name("音" * 140).encode("utf-8")), 180)

    def test_symlink_escape(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "root"
            root.mkdir()
            try:
                (root / "link").symlink_to(Path(directory), target_is_directory=True)
            except OSError:
                self.skipTest("OS does not permit creating symlinks")
            with self.assertRaises(Invalid):
                destination(root, "link/outside")

    def test_indices_and_normalized_profile_roundtrip(self):
        self.assertEqual(indices("3,7,10-12"), [3, 7, 10, 11, 12])
        with tempfile.TemporaryDirectory() as directory:
            opts = options({"exclude": "3,7"}, Path(directory))
            self.assertEqual(options(opts, Path(directory)), opts)
        for value in ["0", "4-2", "10001", "x"]:
            with self.assertRaises(Invalid):
                indices(value)

    def test_overnight_window_and_dst_timezone(self):
        config = settings({"window_start": "22:00", "window_end": "06:00"})
        def at(hour):
            return dt.datetime(2026, 11, 14, hour, tzinfo=dt.timezone.utc).timestamp()
        self.assertTrue(in_window(config, at(22)))
        self.assertTrue(in_window(config, at(3)))
        self.assertFalse(in_window(config, at(12)))
        self.assertTrue(in_window(DEFAULTS, at(12)))
        with self.assertRaises(Invalid):
            settings({"timezone": "not/a/timezone"})


class ServiceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.engine = FakeEngine()
        self.app = App(self.root / "data", self.root / "downloads", PASSWORD, engine=self.engine, start_worker=False)
        self.cookie = ""
        self.csrf = ""

    def tearDown(self):
        self.app.close()
        self.temp.cleanup()

    def request(self, path, method="GET", body=None, headers=None):
        payload = encode(body or {}).encode() if method != "GET" else b""
        env = {"REQUEST_METHOD": method, "PATH_INFO": path.split("?")[0], "QUERY_STRING": path.partition("?")[2],
               "HTTP_HOST": "localhost:8787", "REMOTE_ADDR": "127.0.0.1", "wsgi.input": io.BytesIO(payload),
               "CONTENT_TYPE": "application/json", "CONTENT_LENGTH": str(len(payload)),
               "HTTP_COOKIE": self.cookie, "HTTP_X_CSRF_TOKEN": self.csrf}
        env.update(headers or {})
        response = {}
        chunks = self.app(env, lambda status, heads: response.update(status=int(status[:3]), headers=dict(heads)))
        data = b"".join(chunks)
        response["body"] = json.loads(data) if response["headers"].get("Content-Type", "").startswith("application/json") else data
        return response

    def login(self):
        result = self.request("/api/login", "POST", {"username": "admin", "password": PASSWORD})
        self.assertEqual(result["status"], 200, result)
        self.cookie = result["headers"]["Set-Cookie"].split(";", 1)[0]
        self.csrf = result["body"]["csrf"]

    def add_job(self, entries=None, **overrides):
        opts = options(overrides, self.app.downloads)
        raw = {"url": "https://www.youtube.com/playlist?list=PLabcdefgh", "options": opts}
        if entries is not None:
            raw.update(entries=entries, title="Test album")
        return self.app.store.add_jobs(self.app.validate_jobs([raw]))[0]

    def add_source(self, mode="new", date=""):
        identifier = uuid.uuid4().hex
        config = source_config({"name": "Watch", "url": "https://www.youtube.com/@TestChannel", "start_mode": mode,
                                "start_date": date, "options": {}}, self.app.downloads)
        self.app.store.execute("INSERT INTO sources(id,config,enabled,next_check) VALUES(?,?,1,?)", (identifier, encode(config), now()))
        return identifier

    def test_about_requires_login_and_reports_components_and_notices(self):
        self.assertEqual(self.request("/api/about")["status"], 401)
        self.login()
        with patch("mg_nas.app.subprocess.run") as run:
            run.return_value.returncode = 0
            run.return_value.stdout = "fixture-version\n"
            from mg_nas.app import component_info
            component_info.cache_clear()
            result = self.request("/api/about")
            self.assertEqual(result["status"], 200)
            info = result["body"]
            self.assertEqual({c["name"] for c in info["components"]}, {"yt-dlp", "FFmpeg", "FFprobe", "Node.js", "Python", "Gunicorn", "Mutagen"})
            self.assertIn("Third-party components", info["notices"])
            self.assertIn("version", info)
            self.request("/api/about")
            self.assertEqual(run.call_count, 3)
            component_info.cache_clear()

    def test_windows_release_requires_login_and_is_independent_of_component_cache(self):
        with patch("mg_nas.releases.WindowsRelease.fetch", return_value={"tag":"v4.3.0", "checked_at":now()}) as fetch:
            self.assertEqual(self.request("/api/windows-release")["status"], 401)
            fetch.assert_not_called()
            self.login()
            with patch("mg_nas.app.component_info", return_value={"version":"fixture"}):
                self.assertEqual(self.request("/api/about")["status"], 200)
            fetch.assert_not_called()
            result = self.request("/api/windows-release")
            self.assertEqual(result["status"], 200)
            self.assertEqual(result["body"]["version"], "4.3.0")
            self.request("/api/windows-release")
            self.assertEqual(fetch.call_count, 1)

    def test_public_license_and_privacy_require_no_login_and_reject_paths(self):
        license=self.request('/license')
        self.assertEqual(license['status'],200)
        self.assertIn(b'GNU GENERAL PUBLIC LICENSE',license['body'])
        privacy=self.request('/privacy')
        self.assertEqual(privacy['status'],200)
        self.assertIn(b'YouTube',privacy['body'])
        self.assertIn(b'12 hours',privacy['body'])
        for path in ['/../secrets/admin_password','/SOURCE.tar.gz','/privacy/../../COPYRIGHT']:
            self.assertEqual(self.request(path)['status'],404)

    def test_login_csrf_origin_host_and_static(self):
        self.assertEqual(self.request("/api/state")["status"], 401)
        self.assertEqual(self.request("/")["status"], 200)
        self.assertEqual(self.request("/locales.js")["status"], 200)
        self.assertEqual(self.request("/healthz")["status"], 200)
        self.assertEqual(self.request("/api/state", headers={"HTTP_HOST": "evil.example"})["status"], 400)
        self.login()
        self.assertEqual(self.request("/api/settings", "PUT", {}, {"HTTP_X_CSRF_TOKEN": ""})["status"], 403)
        self.assertEqual(self.request("/api/settings", "PUT", {}, {"HTTP_ORIGIN": "https://evil.example"})["status"], 403)
        self.assertEqual(self.request("/api/state")["status"], 200)
        self.request("/api/logout", "POST", {})
        self.assertEqual(self.request("/api/state")["status"], 401)

    def test_login_throttle_and_password_change(self):
        for _ in range(8):
            with self.assertRaises(Invalid):
                self.app.auth.login("admin", "bad", "test-ip")
        with self.assertRaisesRegex(Invalid, "Příliš"):
            self.app.auth.login("admin", PASSWORD, "test-ip")
        self.login()
        from mg_nas.auth import Auth
        Auth(self.app.store, PASSWORD + "changed")
        self.assertIsNone(self.app.auth.session(self.cookie))

    def test_exact_selection_downloads_without_relisting(self):
        identifier = self.add_job([entry(0), entry(1), entry(2)], selected=[1, 3], exclude="1")
        self.app.worker.tick()
        job = self.app.store.job(identifier)
        self.assertEqual(job["status"], "completed")
        self.assertEqual([i["position"] for i in job["items"]], [3])
        self.assertEqual(self.engine.list_calls, [])
        self.assertEqual(self.engine.download_calls, [(IDS[2], "")])

    def test_unprepared_selection_passes_only_selected_positions(self):
        identifier = self.add_job(selected=[2])
        self.app.worker.tick()
        self.assertEqual(self.engine.list_calls[0][1], [2])
        self.assertEqual(self.app.store.job(identifier)["items"][0]["media_id"], IDS[1])

    def test_retry_only_failed_preserves_completed_files(self):
        self.engine.failures[IDS[1]] = EngineError("unavailable")
        identifier = self.add_job([entry(0), entry(1)])
        self.app.worker.tick()
        job = self.app.store.job(identifier)
        self.assertEqual(job["status"], "partial")
        first = Path(job["items"][0]["paths"][0])
        stamp = first.stat().st_mtime_ns
        del self.engine.failures[IDS[1]]
        self.app.job_action(identifier, "retry")
        self.app.worker.tick()
        self.assertEqual(self.app.store.job(identifier)["status"], "completed")
        self.assertEqual(self.engine.download_calls, [(IDS[0], ""), (IDS[1], ""), (IDS[1], "")])
        self.assertEqual(first.stat().st_mtime_ns, stamp)

    def test_duplicate_checks_existing_size_and_profile(self):
        first = self.add_job([entry(0)])
        self.app.worker.tick()
        second = self.add_job([entry(0)])
        self.app.worker.tick()
        self.assertEqual(self.app.store.job(second)["items"][0]["status"], "skipped")
        Path(self.app.store.job(first)["items"][0]["paths"][0]).unlink()
        third = self.add_job([entry(0)])
        self.app.worker.tick()
        self.assertEqual(self.app.store.job(third)["items"][0]["status"], "done")
        fourth = self.add_job([entry(0)], quality="mp3_320")
        self.app.worker.tick()
        self.assertEqual(self.app.store.job(fourth)["items"][0]["status"], "done")
        self.assertEqual(len(self.engine.download_calls), 3)

    def test_transient_error_backs_off_then_succeeds(self):
        self.engine.failures[IDS[0]] = EngineError("timeout", True)
        identifier = self.add_job([entry(0)])
        self.app.worker.tick()
        item = self.app.store.job(identifier)["items"][0]
        self.assertEqual(item["status"], "pending")
        self.assertGreater(item["ready_at"], now())
        self.app.worker.tick()
        self.assertEqual(len(self.engine.download_calls), 1)
        del self.engine.failures[IDS[0]]
        self.app.store.execute("UPDATE items SET ready_at=0 WHERE job_id=?", (identifier,))
        self.app.worker.tick()
        self.assertEqual(self.app.store.job(identifier)["status"], "completed")

    def test_global_pause_resumes_queue_individual_pause_is_held(self):
        identifier = self.add_job([entry(0)])
        self.app.store.set("settings", DEFAULTS | {"queue_paused": True})
        self.app.worker.tick()
        self.assertEqual(self.engine.download_calls, [])
        self.assertEqual(self.app.worker.reason(identifier), "queue")
        self.app.store.set("settings", DEFAULTS)
        self.app.job_action(identifier, "pause")
        self.app.worker.tick()
        self.assertEqual(self.engine.download_calls, [])
        self.app.job_action(identifier, "resume")
        self.app.worker.tick()
        self.assertEqual(self.app.store.job(identifier)["status"], "completed")

    def test_interrupted_recovery_and_path_retained(self):
        self.engine.interrupt = "shutdown"
        identifier = self.add_job([entry(0)])
        self.app.worker.tick()
        before = self.app.store.job(identifier)
        self.assertEqual(before["status"], "interrupted")
        self.assertEqual(before["items"][0]["status"], "pending")
        self.engine.interrupt = ""
        self.app.job_action(identifier, "resume")
        self.app.worker.tick()
        self.assertEqual(self.app.store.job(identifier)["items"][0]["output_base"], before["items"][0]["output_base"])
        self.app.store.execute("UPDATE jobs SET status='processing' WHERE id=?", (identifier,))
        self.app.store.execute("UPDATE items SET status='running' WHERE job_id=?", (identifier,))
        self.app.store.recover()
        self.assertEqual(self.app.store.job(identifier)["status"], "interrupted")
        self.assertEqual(self.app.store.job(identifier)["items"][0]["status"], "pending")

    def test_disk_guard_and_time_window(self):
        identifier = self.add_job([entry(0)])
        with patch("mg_nas.worker.shutil.disk_usage") as usage:
            usage.return_value.free = 1
            self.app.worker.tick()
        self.assertEqual(self.app.store.job(identifier)["status"], "paused")
        self.assertIn("místa", self.app.store.job(identifier)["error"])
        self.app.job_action(identifier, "resume")
        with patch("mg_nas.worker.in_window", return_value=False):
            self.app.worker.tick()
        self.assertEqual(self.engine.download_calls, [])

    def test_watch_baseline_then_only_new_and_remember_deleted(self):
        source = self.add_source()
        self.app.worker.check_source(source)
        self.assertEqual(self.app.store.all("SELECT * FROM jobs"), [])
        self.engine.entries.append(entry(2))
        self.app.worker.check_source(source)
        jobs = self.app.store.jobs()
        self.assertEqual(len(jobs), 1)
        self.assertEqual(jobs[0]["items"][0]["media_id"], IDS[2])
        self.app.job_action(jobs[0]["id"], "remove")
        self.app.worker.check_source(source)
        self.assertEqual(self.app.store.jobs(), [])

    def test_watch_date_is_frozen_even_if_source_removed(self):
        source = self.add_source("date", "2026-11-01")
        self.app.worker.check_source(source)
        self.assertEqual(len(self.app.store.jobs()), 2)
        self.app.source_action(source, {"action": "delete"})
        self.app.worker.tick()
        self.assertEqual(self.engine.download_calls[0][1], "2026-11-01")

    def test_watch_all_queues_initial_items_then_only_new(self):
        source = self.add_source(mode="all")
        self.app.worker.check_source(source)
        self.assertEqual(len(self.app.store.jobs()), 2)
        self.app.worker.check_source(source)
        self.assertEqual(len(self.app.store.jobs()), 2)
        self.engine.entries.append(entry(2))
        self.app.worker.check_source(source)
        self.assertEqual(len(self.app.store.jobs()), 3)
        self.assertEqual(len(self.app.store.all("SELECT * FROM seen WHERE source_id=?", (source,))), 3)

    def test_due_watch_not_starved_by_queue(self):
        self.add_job([entry(0)])
        source = self.add_source()
        self.app.worker.tick()
        self.assertEqual(self.app.store.one("SELECT initialized FROM sources WHERE id=?", (source,))["initialized"], 1)

    def test_remove_keeps_files_and_ledger(self):
        identifier = self.add_job([entry(0)])
        self.app.worker.tick()
        path = Path(self.app.store.job(identifier)["items"][0]["paths"][0])
        self.app.job_action(identifier, "remove")
        self.assertTrue(path.exists())
        self.assertEqual(len(self.app.store.all("SELECT * FROM downloads")), 1)

    def test_cancel_at_completion_retry_does_not_get_stuck(self):
        identifier = self.add_job([entry(0)])
        self.app.worker.tick()
        self.app.store.execute("UPDATE jobs SET status='cancelled' WHERE id=?", (identifier,))
        self.app.job_action(identifier, "retry")
        self.assertEqual(self.app.store.job(identifier)["status"], "completed")
        self.assertEqual(len(self.engine.download_calls), 1)

    def test_backup_all_jobs_and_held_import(self):
        self.add_source()
        identifier = self.add_job([entry(0), entry(1)])
        self.engine.failures[IDS[1]] = EngineError("not available")
        self.app.worker.tick()
        pending = self.add_job([entry(2)])
        backup = self.app.backup()
        serialized = encode(backup)
        self.assertNotIn(PASSWORD, serialized)
        self.assertNotIn("credentials", serialized)
        with tempfile.TemporaryDirectory() as other:
            other_app = App(Path(other)/"data", Path(other)/"downloads", PASSWORD, engine=FakeEngine(), start_worker=False)
            try:
                report = other_app.restore(backup)
                self.assertEqual(report, report | {"jobs": 2, "sources": 1})
                self.assertTrue(other_app.store.settings()["queue_paused"])
                self.assertEqual(other_app.store.all("SELECT enabled FROM sources")[0]["enabled"], 0)
                history = other_app.store.jobs(True)[0]
                self.assertEqual([i["status"] for i in history["items"]], ["done", "failed"])
                self.assertEqual(history["items"][0]["paths"], [])
                held = other_app.store.jobs()[0]
                self.assertEqual(held["status"], "paused")
                self.assertEqual(held["items"][0]["media_id"], IDS[2])
                self.assertEqual(other_app.restore(backup)["jobs"], 0)
            finally:
                other_app.close()
        # UI has a 300-record page; exports must still contain every record.
        for _ in range(302):
            self.add_job([entry(0)])
        self.assertEqual(len(self.app.backup()["jobs"]), 304)

    def test_malformed_restore_is_atomic_and_paths_untrusted(self):
        self.login()
        backup = {"schema": 1, "application": "MediaGrabber NAS", "sources": [None]}
        self.assertEqual(self.request("/api/restore", "POST", backup)["status"], 400)
        self.assertEqual(self.app.store.jobs(), [])
        identifier = self.add_job([entry(0)])
        item = self.app.store.job(identifier)["items"][0]
        self.app.store.execute("UPDATE items SET paths=? WHERE id=?", (encode([str(self.root / "data" / "mediagrabber.sqlite3")]), item["id"]))
        self.assertEqual(self.request("/api/files?id=" + item["id"])["status"], 400)

    def test_single_instance_and_database_persistence(self):
        identifier = self.add_job([entry(0)])
        with self.assertRaises(RuntimeError):
            App(self.root/"data", self.root/"downloads", PASSWORD, start_worker=False)
        self.app.close()
        self.app = App(self.root/"data", self.root/"downloads", PASSWORD, engine=self.engine, start_worker=False)
        self.assertEqual(self.app.store.job(identifier)["items"][0]["media_id"], IDS[0])


class EngineTests(unittest.TestCase):
    def test_args_and_subtitle_failure_fallback(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            engine = Engine(root)
            opts = options({"subtitles": "cs", "quality": "mp3_320"}, root)
            base = root / "100% song"
            args = engine.download_args(entry(), opts, base, DEFAULTS)
            self.assertIn("320K", args)
            self.assertIn("100%% song.%(ext)s", args[args.index("--output") + 1])
            path = base.with_suffix(".mp3")
            path.write_bytes(b"fixture")
            success = (0, "__MG_FILE__" + json.dumps(str(path)))
            with patch.object(engine, "_run", side_effect=[(1, "ERROR: Unable to download video subtitles for 'cs': HTTP Error 429"), success]) as run:
                result = engine.download(entry(), opts, base, DEFAULTS, lambda: "", lambda p: None)
                self.assertEqual(run.call_count, 2)
                self.assertIn("bez titulků", result["notice"])
                self.assertNotIn("--write-subs", run.call_args.args[0])
            with patch.object(engine, "_run", return_value=(1, "[info] Downloading subtitles: cs\nERROR: Unable to download video data: HTTP Error 403")) as run:
                with self.assertRaises(EngineError):
                    engine.download(entry(), opts, base, DEFAULTS, lambda: "", lambda p: None)
                self.assertEqual(run.call_count, 1)

    def test_missing_videos_tab_retries_channel_root(self):
        with tempfile.TemporaryDirectory() as directory:
            engine = Engine(Path(directory))
            payload = {"_type": "playlist", "entries": [{"id": IDS[0]}]}
            with patch.object(engine, "_run", side_effect=[
                (1, "ERROR: [youtube:tab] @anetkasimkova: This channel does not have a videos tab"),
                (0, json.dumps(payload)),
            ]) as run:
                result = engine.listing('https://www.youtube.com/@anetkasimkova/videos')
                self.assertEqual(result['entries'][0]['id'], IDS[0])
                self.assertEqual(run.call_count, 2)
                self.assertEqual(run.call_args.args[0][-1], 'https://www.youtube.com/@anetkasimkova')
            with patch.object(engine, "_run", return_value=(1, 'ERROR: HTTP Error 403')) as run:
                with self.assertRaises(EngineError):
                    engine.listing('https://www.youtube.com/@anetkasimkova/videos')
                self.assertEqual(run.call_count, 1)

    def test_channel_tabs_flatten_with_unique_global_positions(self):
        with tempfile.TemporaryDirectory() as directory:
            engine = Engine(Path(directory))
            payload = {"_type": "playlist", "entries": [
                {"_type": "playlist", "entries": [{"id": IDS[0], "playlist_index": 1}]},
                {"_type": "playlist", "entries": [{"id": IDS[1], "playlist_index": 1}, {"id": IDS[0]}]},
            ]}
            with patch.object(engine, '_run', return_value=(0, json.dumps(payload))):
                result = engine.listing('https://www.youtube.com/@anetkasimkova')
                self.assertEqual([e['id'] for e in result['entries']], IDS[:2])
                self.assertEqual([e['position'] for e in result['entries']], [1, 2])
            with patch.object(engine, '_run', return_value=(1, json.dumps(payload))):
                with self.assertRaises(EngineError):
                    engine.listing('https://www.youtube.com/@anetkasimkova')

    def test_listing_failure_does_not_accept_partial_baseline(self):
        with tempfile.TemporaryDirectory() as directory:
            engine = Engine(Path(directory))
            payload = {"_type": "playlist", "title": "Incomplete", "entries": [{"id": IDS[0]}]}
            with patch.object(engine, "_run", return_value=(1, json.dumps(payload))):
                with self.assertRaises(EngineError):
                    engine.listing("https://www.youtube.com/playlist?list=PLabcdefgh")


if __name__ == "__main__":
    unittest.main()
