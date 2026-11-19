"""History pagination/erasure regressions in isolated SQLite + WSGI fixtures."""
import base64
import json
import tempfile
import unittest
import uuid
from pathlib import Path
from unittest.mock import patch

from mg_nas.app import App, source_config
from mg_nas.domain import options
import test_service as service


class HistoryTests(unittest.TestCase):
    request = service.ServiceTests.request
    login = service.ServiceTests.login

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        root = Path(self.temp.name)
        self.app = App(root/"data", root/"downloads", service.PASSWORD, engine=service.FakeEngine(), start_worker=False)
        self.cookie, self.csrf = "", ""

    def tearDown(self):
        self.app.close()
        self.temp.cleanup()

    def seed(self, count=130):
        opts = json.dumps(options({}, self.app.downloads))
        with self.app.store.tx() as db:
            for i in range(count):
                identifier = f"{i:032x}"
                db.execute("INSERT INTO jobs(id,url,title,options,status,created,updated) VALUES(?,?,?,?,?,?,?)",
                           (identifier,"https://www.youtube.com/watch?v=AAAAAAAAAAA","History "+str(i),opts,"completed",1000,1000))
                for status in ["done","skipped"]:
                    db.execute("INSERT INTO items(id,job_id,media_id,url,title,position,status,paths,notice) VALUES(?,?,?,?,?,?,?,?,?)",
                               (uuid.uuid4().hex,identifier,"AAAAAAAAAAA","https://www.youtube.com/watch?v=AAAAAAAAAAA", "large-detail"*200,1,status,
                                json.dumps(["private-detail-file.mp3"]),"detail-notice"*200))

    def test_keyset_pages_equal_timestamps_and_deleted_boundary_without_duplicates(self):
        self.seed(330)
        first = self.app.store.history_page()
        self.assertEqual(len(first["jobs"]),50)
        self.assertEqual(first["total"],330)
        ids = [job["id"] for job in first["jobs"]]
        self.app.job_action(ids[-1],"remove")
        cursor = first["next_cursor"]
        while cursor:
            page = self.app.store.history_page(cursor)
            ids.extend(job["id"] for job in page["jobs"])
            cursor = page["next_cursor"]
        self.assertEqual(len(ids),330)  # includes boundary seen before deletion; exceeds old 300 cap
        self.assertEqual(len(set(ids)),330)
        self.assertEqual(ids, sorted(ids,reverse=True))

    def test_page_uses_bounded_queries_and_transfers_counts_not_item_details(self):
        self.seed()
        queries=[]
        self.app.store.db.set_trace_callback(queries.append)
        try:
            with patch.object(self.app.store,"job",side_effect=AssertionError("must not materialize job details")):
                page = self.app.store.history_page()
        finally:
            self.app.store.db.set_trace_callback(None)
        self.assertLessEqual(len(queries),2)
        payload = json.dumps(page)
        self.assertLess(len(payload),100000)
        self.assertNotIn("private-detail-file",payload)
        self.assertNotIn("large-detail",payload)
        for job in page["jobs"]:
            self.assertNotIn("items",job)
            self.assertEqual(job["counts"],{"total":2,"done":1,"failed":0,"skipped":1,"pending":0})

    def test_state_without_history_and_lazy_details_require_authentication(self):
        self.seed(2)
        self.assertEqual(self.request("/api/history")["status"],401)
        self.assertEqual(self.request("/api/jobs/"+"0"*32)["status"],401)
        self.login()
        with patch.object(self.app.store,"jobs",wraps=self.app.store.jobs) as jobs:
            result=self.request("/api/state?history=0")
            self.assertEqual(result["body"]["history"],[])
            self.assertEqual(jobs.call_count,1)
            self.assertEqual(jobs.call_args.args,())
        self.assertEqual(self.request("/api/history")["body"]["jobs"][0]["counts"]["total"],2)
        detail=self.request("/api/jobs/"+"0"*32)
        self.assertEqual(detail["status"],200)
        self.assertEqual(len(detail["body"]["items"]),2)
        self.assertIn("private-detail-file",json.dumps(detail["body"]))

    def test_clear_is_csrf_guarded_and_preserves_active_jobs_media_and_ledgers(self):
        self.seed(330)
        source=uuid.uuid4().hex
        config=source_config({"name":"Watch","url":"https://www.youtube.com/@TestChannel","options":{}},self.app.downloads)
        self.app.store.execute("INSERT INTO sources(id,config,enabled,next_check) VALUES(?,?,1,?)",(source,json.dumps(config),9999999999))
        self.app.store.execute("INSERT INTO seen VALUES(?,?)",(source,"AAAAAAAAAAA"))
        media=self.app.downloads/"existing.mp3";media.write_bytes(b"preserved")
        self.app.store.execute("INSERT INTO downloads VALUES(?,?,?,?,?)",("AAAAAAAAAAA","fixture",str(media),9,1000))
        with self.app.store.tx() as db:
            for i,status in enumerate(["queued","processing","paused","interrupted"]):
                db.execute("UPDATE jobs SET status=? WHERE id=?",(status,f"{i:032x}"))
        self.seed_extra_terminal()
        self.assertEqual(self.request("/api/history","DELETE")["status"],401)
        self.login()
        self.assertEqual(self.request("/api/history","DELETE",headers={"HTTP_X_CSRF_TOKEN":""})["status"],403)
        self.assertEqual(self.request("/api/history","DELETE",headers={"HTTP_ORIGIN":"https://evil.invalid"})["status"],403)
        result=self.request("/api/history","DELETE")
        self.assertEqual(result["status"],200)
        self.assertEqual(result["body"]["deleted"],330)
        self.assertEqual(self.app.store.history_page()["jobs"],[])
        self.assertEqual(self.app.store.one("SELECT count(*) AS n FROM jobs")["n"],4)
        self.assertEqual(self.app.store.one("SELECT count(*) AS n FROM items")["n"],8)
        self.assertEqual(self.app.store.one("SELECT count(*) AS n FROM downloads")["n"],1)
        self.assertEqual(self.app.store.one("SELECT count(*) AS n FROM seen")["n"],1)
        self.assertEqual(self.app.store.one("SELECT count(*) AS n FROM sources")["n"],1)
        self.assertEqual(media.read_bytes(),b"preserved")
        self.assertEqual(self.request("/api/history","DELETE")["body"]["deleted"],0)

    def seed_extra_terminal(self):
        opts=json.dumps(options({},self.app.downloads))
        for status in ["completed","partial","failed","cancelled"]:
            identifier=uuid.uuid4().hex
            self.app.store.execute("INSERT INTO jobs(id,url,title,options,status,created,updated) VALUES(?,?,?,?,?,?,?)",
                                   (identifier,"https://www.youtube.com/watch?v=AAAAAAAAAAA",status,opts,status,1000,1000))

    def test_invalid_cursor_and_page_limits_are_rejected(self):
        self.login()
        for raw in ["not-base64",base64.urlsafe_b64encode(b'[null,"x"]').decode(),base64.urlsafe_b64encode(b'[1e999,"x"]').decode(),"x"*513]:
            self.assertEqual(self.request("/api/history?cursor="+raw)["status"],400)
        for value in ["0","101","bad"]:
            self.assertEqual(self.request("/api/history?limit="+value)["status"],400)
