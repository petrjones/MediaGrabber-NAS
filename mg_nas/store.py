# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

import contextlib
import base64
import binascii
import json
import math
import re
import sqlite3
import threading
import uuid
from pathlib import Path

from .domain import DEFAULTS, Invalid, now


def encode(value):
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


class Store:
    def __init__(self, directory: Path):
        directory.mkdir(parents=True, exist_ok=True)
        self.directory = directory
        self.lock = threading.RLock()
        self.db = sqlite3.connect(directory / "mediagrabber.sqlite3", timeout=10, check_same_thread=False)
        self.db.row_factory = sqlite3.Row
        self.db.executescript("""
          PRAGMA journal_mode=WAL; PRAGMA synchronous=FULL; PRAGMA foreign_keys=ON;
          CREATE TABLE IF NOT EXISTS kv(key TEXT PRIMARY KEY,value TEXT NOT NULL);
          CREATE TABLE IF NOT EXISTS sources(id TEXT PRIMARY KEY, config TEXT NOT NULL,
            enabled INTEGER NOT NULL, next_check REAL NOT NULL, initialized INTEGER NOT NULL DEFAULT 0,
            last_check REAL, status TEXT NOT NULL DEFAULT 'waiting', error TEXT NOT NULL DEFAULT '');
          CREATE TABLE IF NOT EXISTS seen(source_id TEXT NOT NULL REFERENCES sources(id) ON DELETE CASCADE,
            media_id TEXT NOT NULL, PRIMARY KEY(source_id,media_id));
          CREATE TABLE IF NOT EXISTS jobs(id TEXT PRIMARY KEY,url TEXT NOT NULL,title TEXT NOT NULL,
            options TEXT NOT NULL,status TEXT NOT NULL DEFAULT 'queued',created REAL NOT NULL,
            updated REAL NOT NULL,source_id TEXT REFERENCES sources(id) ON DELETE SET NULL,
            error TEXT NOT NULL DEFAULT '',control TEXT NOT NULL DEFAULT '',prepared INTEGER NOT NULL DEFAULT 0);
          CREATE TABLE IF NOT EXISTS items(id TEXT PRIMARY KEY,job_id TEXT NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
            media_id TEXT NOT NULL,url TEXT NOT NULL,title TEXT NOT NULL,position INTEGER NOT NULL,
            status TEXT NOT NULL DEFAULT 'pending',attempts INTEGER NOT NULL DEFAULT 0,ready_at REAL NOT NULL DEFAULT 0,
            progress REAL NOT NULL DEFAULT 0,paths TEXT NOT NULL DEFAULT '[]',error TEXT NOT NULL DEFAULT '',
            notice TEXT NOT NULL DEFAULT '',output_base TEXT NOT NULL DEFAULT '');
          CREATE INDEX IF NOT EXISTS item_job ON items(job_id);
          CREATE INDEX IF NOT EXISTS job_status ON jobs(status,created);
          CREATE INDEX IF NOT EXISTS history_order ON jobs(created DESC,id DESC)
            WHERE status IN ('completed','partial','failed','cancelled');
          CREATE TABLE IF NOT EXISTS downloads(media_id TEXT NOT NULL,profile TEXT NOT NULL,path TEXT NOT NULL,
            size INTEGER NOT NULL,created REAL NOT NULL,PRIMARY KEY(media_id,profile,path));
          CREATE TABLE IF NOT EXISTS sessions(token TEXT PRIMARY KEY,csrf TEXT NOT NULL,expires REAL NOT NULL);
          CREATE TABLE IF NOT EXISTS login_limits(ip TEXT PRIMARY KEY,failures INTEGER NOT NULL,until REAL NOT NULL);
        """)
        self.db.commit()

    @contextlib.contextmanager
    def tx(self):
        with self.lock:
            try:
                self.db.execute("BEGIN IMMEDIATE")
                yield self.db
                self.db.commit()
            except BaseException:
                self.db.rollback()
                raise

    def all(self, sql, args=()):
        with self.lock:
            return [dict(r) for r in self.db.execute(sql, args)]

    def one(self, sql, args=()):
        values = self.all(sql, args)
        return values[0] if values else None

    def execute(self, sql, args=()):
        with self.tx() as db:
            return db.execute(sql, args).rowcount

    def get(self, key, default=None):
        row = self.one("SELECT value FROM kv WHERE key=?", (key,))
        return json.loads(row["value"]) if row else default

    def set(self, key, value):
        self.execute("INSERT INTO kv(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value", (key, encode(value)))

    def settings(self):
        return DEFAULTS | self.get("settings", {})

    @staticmethod
    def insert_job(db, url, opts, title="", source_id=None, prepared_entries=None):
        identifier, stamp = uuid.uuid4().hex, now()
        db.execute("INSERT INTO jobs(id,url,title,options,created,updated,source_id) VALUES(?,?,?,?,?,?,?)",
                   (identifier, url, title or url, encode(opts), stamp, stamp, source_id))
        if prepared_entries is not None:
            Store.insert_items(db, identifier, prepared_entries)
        return identifier

    @staticmethod
    def insert_items(db, job_id, entries):
        for entry in entries:
            db.execute("INSERT INTO items(id,job_id,media_id,url,title,position) VALUES(?,?,?,?,?,?)",
                       (uuid.uuid4().hex, job_id, entry["id"], entry["url"], entry["title"], entry["position"]))
        db.execute("UPDATE jobs SET prepared=1 WHERE id=?", (job_id,))

    def add_jobs(self, entries):
        if not entries or len(entries) > 100:
            raise Invalid("Najednou vlož 1 až 100 odkazů.")
        with self.tx() as db:
            return [self.insert_job(db, **entry) for entry in entries]

    def job(self, identifier):
        row = self.one("SELECT * FROM jobs WHERE id=?", (identifier,))
        if not row:
            raise Invalid("Úloha nebyla nalezena.")
        row["options"] = json.loads(row["options"])
        row["items"] = self.all("SELECT * FROM items WHERE job_id=? ORDER BY position,id", (identifier,))
        for item in row["items"]:
            item["paths"] = json.loads(item["paths"])
        return row

    def jobs(self, history=False):
        rows = self.all("SELECT id FROM jobs WHERE status " + ("IN" if history else "NOT IN") +
                        " ('completed','partial','failed','cancelled') ORDER BY CASE WHEN status='processing' THEN 0 ELSE 1 END,created DESC LIMIT 300")
        return [self.job(row["id"]) for row in rows]

    def history_page(self, cursor="", limit=50):
        if type(limit) is not int or not 1 <= limit <= 100:
            raise Invalid("Neplatná velikost stránky historie.")
        condition, args = "", []
        if cursor:
            try:
                if not isinstance(cursor, str) or len(cursor) > 512:
                    raise ValueError()
                boundary = json.loads(base64.b64decode(cursor + '=' * (-len(cursor) % 4), altchars=b'-_', validate=True))
                created, identifier = boundary
                if type(created) not in {float, int} or not math.isfinite(created) or not isinstance(identifier, str) or not re.fullmatch(r"[a-f0-9]{32}", identifier):
                    raise ValueError()
            except (ValueError, TypeError, OverflowError, binascii.Error):
                raise Invalid("Neplatná pozice v historii.")
            condition = " AND (created < ? OR (created = ? AND id < ?))"
            args.extend([created, created, identifier])
        args.append(limit + 1)
        # Limit jobs BEFORE joining items. No item titles, errors or file paths
        # are decoded/transferred until the user opens one job's result.
        with self.lock:
            rows = self.all("""
              WITH page AS (
                SELECT * FROM jobs WHERE status IN ('completed','partial','failed','cancelled')
            """ + condition + " ORDER BY created DESC,id DESC LIMIT ?)" + """
              SELECT page.*, count(items.id) AS n_total,
                coalesce(sum(items.status='done'),0) AS n_done,
                coalesce(sum(items.status='failed'),0) AS n_failed,
                coalesce(sum(items.status='skipped'),0) AS n_skipped,
                coalesce(sum(items.status IN ('pending','running')),0) AS n_pending
              FROM page LEFT JOIN items ON items.job_id=page.id
              GROUP BY page.id ORDER BY page.created DESC,page.id DESC
            """, args)
            total = self.one("SELECT count(*) AS n FROM jobs WHERE status IN ('completed','partial','failed','cancelled')")["n"]
        more = len(rows) > limit
        rows = rows[:limit]
        for row in rows:
            row["options"] = json.loads(row["options"])
            row["counts"] = {key:row.pop("n_"+key) for key in ["total","done","failed","skipped","pending"]}
        next_cursor = ""
        if more:
            last = rows[-1]
            next_cursor = base64.urlsafe_b64encode(encode([last["created"], last["id"]]).encode()).decode().rstrip('=')
        return {"jobs":rows, "total":total, "next_cursor":next_cursor}

    def clear_history(self):
        # FK cascade removes only item records. Downloads/seen/media and
        # non-terminal jobs are independent and intentionally preserved.
        with self.tx() as db:
            return db.execute("DELETE FROM jobs WHERE status IN ('completed','partial','failed','cancelled')").rowcount

    def recover(self):
        # The user explicitly resumes interrupted work; restarting never surprises them.
        with self.tx() as db:
            db.execute("UPDATE items SET status='pending',progress=0 WHERE status='running'")
            db.execute("UPDATE jobs SET status='interrupted',control='',error='Služba byla přerušena. Úlohu lze obnovit.',updated=? WHERE status='processing'", (now(),))
            db.execute("UPDATE sources SET status='waiting',next_check=? WHERE status='checking'", (now() + 30,))

    def close(self):
        with self.lock:
            self.db.close()
