# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

import json
import logging
import os
import shutil
import threading
import time
import uuid
from pathlib import Path

from .domain import destination, in_window, now, profile_key, safe_name
from .engine import EngineError, Interrupted
from .store import Store, encode

log = logging.getLogger(__name__)
TERMINAL = {"completed", "partial", "failed", "cancelled"}


class Worker:
    def __init__(self, store: Store, downloads: Path, engine):
        self.store, self.downloads, self.engine = store, downloads.resolve(), engine
        self.shutdown = threading.Event()
        self.wake = threading.Event()
        self.tick_lock = threading.Lock()
        self.thread = None
        self.active_job = None

    def start(self):
        self.store.recover()
        self.thread = threading.Thread(target=self.loop, name="mediagrabber-worker", daemon=True)
        self.thread.start()

    def close(self):
        self.shutdown.set()
        self.wake.set()
        if self.thread:
            self.thread.join(timeout=12)

    def loop(self):
        while not self.shutdown.is_set():
            try:
                self.tick()
            except Exception:
                log.exception("Background operation failed")
            self.wake.wait(2)
            self.wake.clear()

    def reason(self, job_id=None):
        if self.shutdown.is_set():
            return "shutdown"
        if job_id:
            row = self.store.one("SELECT control FROM jobs WHERE id=?", (job_id,))
            if not row:
                return "cancelled"
            if row["control"]:
                return row["control"]
            config = self.store.settings()
            if config["queue_paused"]:
                return "queue"
            if not in_window(config):
                return "window"
        return ""

    def tick(self):
        if not self.tick_lock.acquire(blocking=False):
            return
        try:
            if self.shutdown.is_set():
                return
            config = self.store.settings()
            # Check one due source between jobs, even with a long queue.
            source = self.store.one("SELECT id FROM sources WHERE enabled=1 AND next_check<=? ORDER BY next_check LIMIT 1", (now(),))
            if source:
                self.check_source(source["id"])
            if not config["queue_paused"] and in_window(config):
                row = self.store.one("SELECT j.id FROM jobs j WHERE j.status='queued' AND (j.prepared=0 OR EXISTS(SELECT 1 FROM items i WHERE i.job_id=j.id AND i.status='pending' AND i.ready_at<=?)) ORDER BY j.created LIMIT 1", (now(),))
                if row:
                    self.process_job(row["id"])
                    return
        finally:
            self.tick_lock.release()

    def process_job(self, identifier):
        if not self.store.execute("UPDATE jobs SET status='processing',error='',updated=? WHERE id=? AND status='queued'", (now(), identifier)):
            return
        self.active_job = identifier
        try:
            job = self.store.job(identifier)
            opts = job["options"]
            if not job["prepared"]:
                info = self.engine.listing(job["url"], opts["playlist"], lambda: self.reason(identifier), opts["selected"])
                entries = [e for e in info["entries"] if e["position"] not in opts["exclude"] and (not opts["selected"] or e["position"] in opts["selected"])]
                if not entries:
                    raise EngineError("Ve výběru nezůstala žádná položka.")
                with self.store.tx() as db:
                    Store.insert_items(db, identifier, entries)
                    db.execute("UPDATE jobs SET title=? WHERE id=?", (info["title"], identifier))
                job = self.store.job(identifier)
            for ordinal, item in enumerate(job["items"], 1):
                reason = self.reason(identifier)
                if reason:
                    raise Interrupted(reason)
                if item["status"] != "pending" or item["ready_at"] > now():
                    continue
                self.process_item(job, item, ordinal)
            self.summarize(identifier)
        except Interrupted as e:
            reason = str(e)
            status = {"shutdown": "interrupted", "cancelled": "cancelled", "window": "queued", "queue": "queued"}.get(reason, "paused")
            with self.store.tx() as db:
                db.execute("UPDATE items SET status='pending',progress=0 WHERE job_id=? AND status='running'", (identifier,))
                db.execute("UPDATE jobs SET status=?,control='',updated=? WHERE id=?", (status, now(), identifier))
        except Exception as e:
            log.exception("Job %s failed", identifier)
            self.store.execute("UPDATE items SET status='failed',error=? WHERE job_id=? AND status='running'", (str(e)[:1800], identifier))
            self.store.execute("UPDATE jobs SET status='failed',error=?,updated=? WHERE id=?", (str(e)[:1800], now(), identifier))
        finally:
            self.active_job = None

    def duplicate(self, media_id, opts):
        if not opts["duplicates"]:
            return []
        rows = self.store.all("SELECT path,size FROM downloads WHERE media_id=? AND profile=?", (media_id, profile_key(opts)))
        paths = []
        for row in rows:
            path = Path(row["path"])
            try:
                if path.resolve().is_relative_to(self.downloads) and path.is_file() and path.stat().st_size == row["size"] and row["size"] > 0:
                    paths.append(str(path))
            except OSError:
                continue
        return paths

    def output_base(self, job, item, ordinal):
        opts = job["options"]
        if item["output_base"]:
            path = Path(item["output_base"]).resolve()
            if not path.is_relative_to(self.downloads):
                raise EngineError("Uložený cíl není uvnitř povolené složky.")
            return path
        folder = destination(self.downloads, opts["folder"], create=True)
        if opts["subfolder"]:
            folder = destination(self.downloads, str((folder / safe_name(job["title"])).relative_to(self.downloads)).replace(os.sep, "/"), create=True)
        number = ordinal if opts["renumber"] else item["position"]
        prefix = str(number).zfill(max(2, len(str(max(i["position"] for i in job["items"]))))) + " - " if len(job["items"]) > 1 else ""
        filename = prefix + safe_name(item["title"])
        path = folder / filename
        # Never reuse a path owned by a different queue item, even before it exists.
        allocated = self.store.one("SELECT id FROM items WHERE output_base=? AND id!=?", (str(path), item["id"]))
        if allocated or any(folder.glob(filename.replace("[", "[[]") + ".*")):
            path = folder / (filename + " (" + item["id"][:8] + ")")
        self.store.execute("UPDATE items SET output_base=? WHERE id=?", (str(path), item["id"]))
        return path

    def process_item(self, job, item, ordinal):
        identifier, opts = item["id"], job["options"]
        duplicates = self.duplicate(item["media_id"], opts)
        if duplicates:
            self.store.execute("UPDATE items SET status='skipped',paths=?,notice='Ověřený soubor už existuje.',progress=100 WHERE id=?", (encode(duplicates), identifier))
            return
        config = self.store.settings()
        if shutil.disk_usage(self.downloads).free < config["minimum_free_mb"] * 1024 * 1024:
            self.store.execute("UPDATE jobs SET error='Nedostatek volného místa. Uvolni místo a obnov úlohu.' WHERE id=?", (job["id"],))
            raise Interrupted("paused")
        base = self.output_base(job, item, ordinal)
        self.store.execute("UPDATE items SET status='running',attempts=attempts+1,error='',progress=0 WHERE id=?", (identifier,))
        try:
            date_after = opts.get("date_after", "")
            result = self.engine.download(item, opts, base, config, lambda: self.reason(job["id"]),
                                          lambda p: self.store.execute("UPDATE items SET progress=? WHERE id=?", (p, identifier)), date_after)
            paths = result["paths"]
            for filename in paths:
                path = Path(filename).resolve()
                if not path.is_relative_to(self.downloads) or not path.is_file() or path.stat().st_size <= 0:
                    raise EngineError("Výsledek není platný soubor v povolené složce.")
            if not paths and not result.get("filtered"):
                raise EngineError("Nebyl vytvořen žádný mediální soubor.")
            with self.store.tx() as db:
                for filename in paths:
                    db.execute("INSERT OR REPLACE INTO downloads VALUES(?,?,?,?,?)", (item["media_id"], profile_key(opts), filename, Path(filename).stat().st_size, now()))
                db.execute("UPDATE items SET status=?,paths=?,notice=?,progress=100 WHERE id=?", ("skipped" if result.get("filtered") else "done", encode(paths), result.get("notice", ""), identifier))
        except EngineError as e:
            attempts = self.store.one("SELECT attempts FROM items WHERE id=?", (identifier,))["attempts"]
            retry = e.transient and attempts < config["max_attempts"]
            self.store.execute("UPDATE items SET status=?,error=?,ready_at=?,progress=0 WHERE id=?", ("pending" if retry else "failed", str(e)[:1800], now() + min(3600, 60 * 2 ** (attempts - 1)) if retry else 0, identifier))

    def summarize(self, identifier):
        job = self.store.job(identifier)
        states = [item["status"] for item in job["items"]]
        status = "queued" if "pending" in states else "partial" if "failed" in states and any(s in {"done", "skipped"} for s in states) else "failed" if "failed" in states else "completed"
        self.store.execute("UPDATE jobs SET status=?,updated=? WHERE id=?", (status, now(), identifier))

    def check_source(self, identifier):
        source = self.store.one("SELECT * FROM sources WHERE id=?", (identifier,))
        if not source or not source["enabled"]:
            return
        config = json.loads(source["config"])
        self.store.execute("UPDATE sources SET status='checking',error='' WHERE id=?", (identifier,))
        try:
            info = self.engine.listing(config["url"], True, lambda: "shutdown" if self.shutdown.is_set() else "")
            with self.store.tx() as db:
                # A source disabled while the network operation ran must not enqueue work.
                current = db.execute("SELECT enabled FROM sources WHERE id=?", (identifier,)).fetchone()
                if not current or not current["enabled"]:
                    db.execute("UPDATE sources SET status='waiting' WHERE id=?", (identifier,))
                    return
                count = 0
                for entry in info["entries"]:
                    exists = db.execute("SELECT 1 FROM seen WHERE source_id=? AND media_id=?", (identifier, entry["id"])).fetchone()
                    if exists:
                        continue
                    baseline = not source["initialized"] and config["start_mode"] == "new"
                    if not baseline:
                        # Freeze the original URL and position; later playlist edits cannot swap a video.
                        opts = dict(config["options"], playlist=False, selected=[], exclude=[], date_after=config["start_date"])
                        Store.insert_job(db, entry["url"], opts, config["name"], identifier, [entry])
                        count += 1
                    db.execute("INSERT INTO seen VALUES(?,?)", (identifier, entry["id"]))
                message = "baseline" if not source["initialized"] and config["start_mode"] == "new" else "ok"
                db.execute("UPDATE sources SET initialized=1,status=?,error='',last_check=?,next_check=? WHERE id=?", (message, now(), now() + config["interval_minutes"] * 60, identifier))
        except Interrupted:
            self.store.execute("UPDATE sources SET status='waiting',next_check=? WHERE id=?", (now() + 30, identifier))
        except Exception as e:
            self.store.execute("UPDATE sources SET status='error',error=?,last_check=?,next_check=? WHERE id=?", (str(e)[:1800], now(), now() + 900, identifier))
