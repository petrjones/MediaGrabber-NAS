# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

import atexit
import functools
import importlib.metadata
import subprocess
import sys
import datetime as dt
import hashlib
import ipaddress
import json
import logging
import mimetypes
import os
import re
import threading
import uuid
from pathlib import Path
from urllib.parse import parse_qs, quote, urlsplit

from . import __version__
from .auth import Auth
from .dsm import DsmBridge
from .domain import Invalid, destination, now, options, settings, youtube_url
from .engine import Engine, EngineError
from .releases import WindowsRelease
from .store import Store, encode
from .worker import TERMINAL, Worker

STATIC = Path(__file__).parent / "static"
MAX_BODY = 32 * 1024 * 1024


@functools.lru_cache(maxsize=1)
def component_info():
    def package(name):
        try:
            return importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            return None
    def command(argv):
        try:
            result = subprocess.run(argv, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=3,
                                    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            return result.stdout.splitlines()[0][:180] if result.returncode == 0 and result.stdout else None
        except (OSError, subprocess.TimeoutExpired):
            return None
    components = [
        {"name":"yt-dlp", "version":package("yt-dlp"), "url":"https://github.com/yt-dlp/yt-dlp"},
        {"name":"FFmpeg", "version":command([os.environ.get("MG_FFMPEG", "ffmpeg"), "-version"]), "url":"https://ffmpeg.org/"},
        {"name":"FFprobe", "version":command(["ffprobe", "-version"]), "url":"https://ffmpeg.org/ffprobe.html"},
        {"name":"Node.js", "version":command(["node", "--version"]), "url":"https://nodejs.org/"},
        {"name":"Python", "version":sys.version.split()[0], "url":"https://www.python.org/"},
        {"name":"Gunicorn", "version":package("gunicorn"), "url":"https://github.com/benoitc/gunicorn"},
        {"name":"Mutagen", "version":package("mutagen"), "url":"https://github.com/quodlibet/mutagen"},
    ]
    path = Path(__file__).resolve().parent.parent / "THIRD-PARTY-NOTICES.md"
    root = path.parent
    return {"version":__version__, "components":components, "notices":path.read_text(encoding="utf-8") if path.is_file() else "https://github.com/petrjones/MediaGrabber-NAS",
            "copyright":(root/"COPYRIGHT").read_text("utf-8") if (root/"COPYRIGHT").is_file() else "GPL-3.0-or-later",
            "license":(root/"LICENSE").read_text("utf-8") if (root/"LICENSE").is_file() else "https://www.gnu.org/licenses/gpl-3.0.html",
            "source_available":(root/"SOURCE.tar.gz").is_file()}


class ServiceLock:
    def __init__(self, path):
        self.file = path.open("a+b")
        try:
            if os.name == "nt":
                import msvcrt
                self.file.seek(0)
                if not self.file.read(1):
                    self.file.write(b"0")
                    self.file.flush()
                self.file.seek(0)
                msvcrt.locking(self.file.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(self.file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            self.file.close()
            raise RuntimeError("S touto databází už běží jiná instance. Použij pouze jeden worker.")

    def close(self):
        self.file.close()


def source_config(raw, root):
    if not isinstance(raw, dict):
        raise Invalid("Neplatné nastavení zdroje.")
    name = str(raw.get("name", "")).strip()
    interval = raw.get("interval_minutes", 120)
    start_mode = raw.get("start_mode", "new")
    start_date = raw.get("start_date", "")
    if not name or len(name) > 120:
        raise Invalid("Zdroj musí mít název dlouhý 1 až 120 znaků.")
    if type(interval) is not int or not 15 <= interval <= 10080:
        raise Invalid("Interval kontroly musí být 15 až 10080 minut.")
    if start_mode not in {"new", "date", "all"}:
        raise Invalid("Neplatný začátek sledování.")
    if start_mode == "date":
        try:
            dt.date.fromisoformat(start_date)
        except (ValueError, TypeError):
            raise Invalid("Vyber platné počáteční datum.")
    else:
        start_date = ""
    opts = options(raw.get("options"), root)
    opts.update(playlist=True, selected=[], exclude=[])
    return {"name": name, "url": youtube_url(raw.get("url", ""), True, True), "interval_minutes": interval,
            "start_mode": start_mode, "start_date": start_date, "options": opts}


class App:
    def __init__(self, data: Path, downloads: Path, password: str, engine=None, start_worker=True, secure_cookie=False, allowed_hosts=None, dsm_key=None):
        self.data, self.downloads = data.resolve(), downloads.resolve()
        self.data.mkdir(parents=True, exist_ok=True)
        self.downloads.mkdir(parents=True, exist_ok=True)
        self.instance_lock = ServiceLock(self.data / "service.lock")
        try:
            self.store = Store(self.data)
            self.windows_release = WindowsRelease(self.store)
            self.auth = Auth(self.store, password, secure_cookie)
            self.dsm = DsmBridge(self.store, dsm_key) if dsm_key else None
            self.engine = engine or Engine(self.data)
            self.worker = Worker(self.store, self.downloads, self.engine)
            self.allowed_hosts = set(allowed_hosts or [])
            self.preview_lock = threading.Lock()
            self.closed = False
            if start_worker:
                self.worker.start()
        except BaseException:
            self.instance_lock.close()
            raise

    def close(self):
        if not self.closed:
            self.closed = True
            self.worker.close()
            self.store.close()
            self.instance_lock.close()

    def valid_host(self, host):
        try:
            name = urlsplit("//" + host).hostname
            if name in {"localhost", *self.allowed_hosts}:
                return True
            ip = ipaddress.ip_address(name or "")
            return ip.is_private or ip.is_loopback
        except ValueError:
            return False

    def __call__(self, env, start_response):
        def respond(status, payload, headers=None, content_type="application/json; charset=utf-8"):
            data = payload if isinstance(payload, bytes) else encode(payload).encode()
            defaults = [("Content-Type", content_type), ("Content-Length", str(len(data))), ("Cache-Control", "no-store"),
                        ("X-Content-Type-Options", "nosniff"), ("Referrer-Policy", "same-origin"),
                        ("Content-Security-Policy", "default-src 'self'; img-src 'self' data:; script-src 'self'; style-src 'self'; connect-src 'self'; frame-ancestors " + ("'self'" if portal else "'none'") + "; base-uri 'none'; form-action 'self'")]
            start_response(status, defaults + (headers or []))
            return [data]

        method, route = env.get("REQUEST_METHOD", "GET"), env.get("PATH_INFO", "/")
        portal = env.get("HTTP_X_MG_PORTAL") == "1"
        secure_portal = portal and env.get("HTTP_X_FORWARDED_PROTO") == "https"
        try:
            host = env.get("HTTP_HOST", "")
            if not self.valid_host(host):
                return respond("400 Bad Request", {"error": "Nepovolený název serveru. Nastav MG_ALLOWED_HOSTS."})
            if route == "/healthz" and method == "GET":
                return respond("200 OK", {"application": "MediaGrabber NAS", "status": "ok", "version": __version__, "package_build": os.environ.get("MG_PACKAGE_BUILD", "")})
            if method not in {"GET", "POST", "PUT", "DELETE"}:
                return respond("405 Method Not Allowed", {"error": "Nepovolená metoda."})
            body = {}
            if method != "GET":
                origin = env.get("HTTP_ORIGIN", "")
                if origin:
                    op = urlsplit(origin)
                    if op.netloc.lower() != host.lower() or op.scheme not in {"http", "https"}:
                        return respond("403 Forbidden", {"error": "Požadavek z jiné stránky byl odmítnut."})
                if not env.get("CONTENT_TYPE", "").lower().startswith("application/json"):
                    return respond("415 Unsupported Media Type", {"error": "Požadavek musí být JSON."})
                try:
                    length = int(env.get("CONTENT_LENGTH", "0") or "0")
                except ValueError:
                    raise Invalid("Neplatná délka požadavku.")
                if not 0 <= length <= MAX_BODY:
                    return respond("413 Content Too Large", {"error": "Soubor nebo požadavek je příliš velký."})
                try:
                    body = json.loads(env["wsgi.input"].read(length))
                except (ValueError, UnicodeDecodeError):
                    raise Invalid("Neplatný JSON.")
                if not isinstance(body, dict):
                    raise Invalid("Požadavek musí být objekt.")
            if route == "/api/dsm/issue" and method == "POST":
                token = self.dsm.issue(env.get("HTTP_X_MG_BRIDGE_KEY", "")) if self.dsm else None
                if not token:
                    return respond("403 Forbidden", {"error": "Ověření DSM bylo odmítnuto."})
                return respond("200 OK", token.encode("ascii"), content_type="text/plain; charset=utf-8")
            if route == "/api/dsm/exchange" and method == "POST":
                if not portal or not self.dsm or not self.dsm.consume(body.get("ticket")):
                    return respond("401 Unauthorized", {"error": "Přihlášení DSM vypršelo. Otevři aplikaci znovu z nabídky DSM."})
                csrf, cookie = self.auth.new_session(portal=True, secure=secure_portal)
                return respond("200 OK", {"csrf": csrf}, [("Set-Cookie", cookie)])
            if route == "/api/login" and method == "POST":
                username, password = body.get("username", ""), body.get("password", "")
                if not isinstance(username, str) or not isinstance(password, str):
                    raise Invalid("Neplatné přihlašovací údaje.")
                csrf, cookie = self.auth.login(username, password, env.get("REMOTE_ADDR", "unknown"), portal=portal, secure=secure_portal)
                return respond("200 OK", {"csrf": csrf}, [("Set-Cookie", cookie)])
            if not route.startswith("/api/"):
                if method != "GET":
                    return respond("405 Method Not Allowed", {"error": "Nepovolená metoda."})
                public_documents = {"/privacy":("PRIVACY.md", "text/plain; charset=utf-8"),
                                    "/license":("LICENSE", "text/plain; charset=utf-8"),
                                    "/source":("SOURCE.tar.gz", "application/gzip")}
                if route in public_documents:
                    name, content_type = public_documents[route]
                    path = Path(__file__).resolve().parent.parent/name
                    if not path.is_file():
                        return respond("404 Not Found", {"error":"Document not available in this development checkout."})
                    headers = [("Content-Disposition", 'attachment; filename="MediaGrabber-NAS-'+__version__+'-source.tar.gz"')] if route == "/source" else []
                    return respond("200 OK", path.read_bytes(), headers, content_type=content_type)
                files = {"/": "index.html", "/app.js": "app.js", "/locales.js": "locales.js", "/style.css": "style.css", "/logo.png": "logo.png", "/favicon.ico": "favicon.ico"}
                if route not in files:
                    return respond("404 Not Found", {"error": "Stránka nebyla nalezena."})
                path = STATIC / files[route]
                return respond("200 OK", path.read_bytes(), content_type=mimetypes.guess_type(path.name)[0] or "application/octet-stream")
            session = self.auth.session(env.get("HTTP_COOKIE", ""), portal=portal)
            if not session:
                return respond("401 Unauthorized", {"error": "Přihlas se prosím."})
            if method != "GET":
                import hmac
                if not hmac.compare_digest(session["csrf"], env.get("HTTP_X_CSRF_TOKEN", "")):
                    return respond("403 Forbidden", {"error": "Chybí ochranný token. Obnov stránku."})
            if route == "/api/logout" and method == "POST":
                self.store.execute("DELETE FROM sessions WHERE token=?", (session["token"],))
                return respond("200 OK", {"ok": True}, [("Set-Cookie", self.auth.cookie("", True, portal=portal, secure=secure_portal))])
            if route == "/api/session" and method == "GET":
                return respond("200 OK", {"csrf": session["csrf"], "version": __version__})
            if route == "/api/about" and method == "GET":
                return respond("200 OK", component_info())
            if route == "/api/windows-release" and method == "GET":
                return respond("200 OK", self.windows_release.get())
            if route == "/api/state" and method == "GET":
                query = parse_qs(env.get("QUERY_STRING", ""))
                return respond("200 OK", self.state(include_history=query.get("history", ["1"])[0] != "0"))
            if route == "/api/history" and method == "GET":
                query = parse_qs(env.get("QUERY_STRING", ""))
                return respond("200 OK", self.store.history_page(query.get("cursor", [""])[0], int(query.get("limit", ["50"])[0])))
            if route == "/api/history" and method == "DELETE":
                return respond("200 OK", {"deleted":self.store.clear_history()})
            if re.fullmatch(r"/api/jobs/[a-f0-9]{32}", route) and method == "GET":
                return respond("200 OK", self.store.job(route.rsplit("/", 1)[1]))
            if route == "/api/settings" and method == "PUT":
                self.store.set("settings", settings(body))
                self.worker.wake.set()
                return respond("200 OK", {"ok": True})
            if route == "/api/preview" and method == "POST":
                opts = options(body.get("options"), self.downloads)
                url = youtube_url(body.get("url", ""), opts["playlist"])
                if not self.preview_lock.acquire(blocking=False):
                    return respond("409 Conflict", {"error": "Jiný náhled se právě načítá."})
                try:
                    result = self.engine.listing(url, opts["playlist"], lambda: "shutdown" if self.worker.shutdown.is_set() else "")
                finally:
                    self.preview_lock.release()
                return respond("200 OK", result)
            if route == "/api/jobs" and method == "POST":
                entries = self.validate_jobs(body.get("jobs"))
                identifiers = self.store.add_jobs(entries)
                self.worker.wake.set()
                return respond("201 Created", {"ids": identifiers})
            if re.fullmatch(r"/api/jobs/[a-f0-9]{32}", route) and method == "POST":
                self.job_action(route.rsplit("/", 1)[1], body.get("action"))
                return respond("200 OK", {"ok": True})
            if route == "/api/sources" and method == "POST":
                config = source_config(body, self.downloads)
                identifier = uuid.uuid4().hex
                self.store.execute("INSERT INTO sources(id,config,enabled,next_check) VALUES(?,?,1,?)", (identifier, encode(config), now()))
                self.worker.wake.set()
                return respond("201 Created", {"id": identifier})
            if re.fullmatch(r"/api/sources/[a-f0-9]{32}", route) and method == "POST":
                self.source_action(route.rsplit("/", 1)[1], body)
                return respond("200 OK", {"ok": True})
            if route == "/api/backup" and method == "GET":
                return respond("200 OK", self.backup(), [("Content-Disposition", 'attachment; filename="MediaGrabber-NAS-backup.json"')])
            if route == "/api/restore" and method == "POST":
                result = self.restore(body)
                return respond("200 OK", result)
            if route == "/api/files" and method == "GET":
                query = parse_qs(env.get("QUERY_STRING", ""))
                item = self.store.one("SELECT paths FROM items WHERE id=?", (query.get("id", [""])[0],))
                if not item:
                    raise Invalid("Soubor nebyl nalezen.")
                paths = json.loads(item["paths"])
                index = int(query.get("index", ["0"])[0])
                if not 0 <= index < len(paths):
                    raise Invalid("Soubor nebyl nalezen.")
                path = Path(paths[index]).resolve()
                if not path.is_relative_to(self.downloads) or not path.is_file():
                    raise Invalid("Soubor už v povolené složce neexistuje.")
                stream = path.open("rb")
                start_response("200 OK", [("Content-Type", "application/octet-stream"), ("Content-Length", str(path.stat().st_size)),
                                          ("Content-Disposition", "attachment; filename*=UTF-8''" + quote(path.name)), ("X-Content-Type-Options", "nosniff"), ("Cache-Control", "no-store")])
                def chunks():
                    try:
                        while data := stream.read(256 * 1024):
                            yield data
                    finally:
                        stream.close()
                return chunks()
            if route == "/api/folders" and method == "GET":
                query = parse_qs(env.get("QUERY_STRING", ""))
                folder = query.get("folder", [""])[0]
                target = destination(self.downloads, folder)
                children = []
                if target.is_dir():
                    for path in sorted(target.iterdir(), key=lambda p: p.name.lower()):
                        if path.is_dir() and path.resolve().is_relative_to(self.downloads):
                            children.append({"name": path.name, "folder": str(path.relative_to(self.downloads)).replace(os.sep, "/")})
                return respond("200 OK", {"folder": folder, "children": children[:1000]})
            return respond("404 Not Found", {"error": "Požadovaná operace nebyla nalezena."})
        except (Invalid, EngineError, ValueError, OSError) as e:
            return respond("400 Bad Request", {"error": str(e)[:1800]})
        except Exception:
            logging.exception("API failed")
            return respond("500 Internal Server Error", {"error": "Vnitřní chyba služby. Podrobnosti jsou v protokolu kontejneru."})

    def validate_jobs(self, raw):
        if not isinstance(raw, list) or not 1 <= len(raw) <= 100:
            raise Invalid("Vlož 1 až 100 odkazů.")
        validated = []
        for entry in raw:
            if not isinstance(entry, dict):
                raise Invalid("Neplatný záznam úlohy.")
            opts = options(entry.get("options"), self.downloads)
            url = youtube_url(entry.get("url", ""), opts["playlist"])
            frozen = entry.get("entries")
            if frozen is not None:
                if not isinstance(frozen, list) or not 1 <= len(frozen) <= 10000:
                    raise Invalid("Vyber alespoň jednu položku.")
                normalized, seen = [], set()
                for item in frozen:
                    if not isinstance(item, dict):
                        raise Invalid("Neplatná položka výběru.")
                    link = youtube_url(item.get("url", ""), False)
                    identifier = parse_qs(urlsplit(link).query)["v"][0]
                    position = item.get("position")
                    if type(position) is not int or not 1 <= position <= 10000 or position in seen:
                        raise Invalid("Neplatné pořadí položek.")
                    seen.add(position)
                    normalized.append({"id": identifier, "url": link, "title": str(item.get("title") or identifier)[:500], "position": position})
                frozen = normalized
                frozen = [item for item in frozen if item["position"] not in opts["exclude"] and (not opts["selected"] or item["position"] in opts["selected"])]
                if not frozen:
                    raise Invalid("Ve výběru nezůstala žádná položka.")
            validated.append({"url": url, "opts": opts, "title": str(entry.get("title") or "")[:500], "prepared_entries": frozen})
        return validated

    def state(self, include_history=True):
        sources = self.store.all("SELECT * FROM sources ORDER BY rowid DESC")
        for source in sources:
            source["config"] = json.loads(source["config"])
            source["seen_count"] = self.store.one("SELECT count(*) AS n FROM seen WHERE source_id=?", (source["id"],))["n"]
        import shutil
        disk = shutil.disk_usage(self.downloads)
        totals = self.store.one("SELECT count(*) AS total,coalesce(sum(status NOT IN ('completed','partial','failed','cancelled')),0) AS active FROM jobs")
        return {"version": __version__, "sources": sources, "jobs": self.store.jobs(), "history": self.store.jobs(True) if include_history else [],
                "job_totals": {"queue": totals["active"], "history": totals["total"] - totals["active"]},
                "settings": self.store.settings(), "free_bytes": disk.free, "download_root": "/downloads"}

    def job_action(self, identifier, action):
        with self.store.tx() as db:
            job = db.execute("SELECT * FROM jobs WHERE id=?", (identifier,)).fetchone()
            if not job:
                raise Invalid("Úloha nebyla nalezena.")
            if action in {"pause", "cancel"}:
                if job["status"] == "processing":
                    db.execute("UPDATE jobs SET control=? WHERE id=?", ("paused" if action == "pause" else "cancelled", identifier))
                elif job["status"] not in TERMINAL:
                    db.execute("UPDATE jobs SET status=?,updated=? WHERE id=?", ("paused" if action == "pause" else "cancelled", now(), identifier))
            elif action == "resume" and job["status"] in {"paused", "interrupted"}:
                db.execute("UPDATE jobs SET status='queued',control='',error='',updated=? WHERE id=?", (now(), identifier))
            elif action == "retry" and job["status"] in {"failed", "partial", "cancelled"}:
                db.execute("UPDATE items SET status='pending',attempts=0,ready_at=0,error='',progress=0 WHERE job_id=? AND status IN ('failed','pending','running')", (identifier,))
                db.execute("UPDATE jobs SET status='queued',control='',error='',updated=? WHERE id=?", (now(), identifier))
            elif action == "remove" and job["status"] != "processing":
                db.execute("DELETE FROM jobs WHERE id=?", (identifier,))
            else:
                raise Invalid("Tuto operaci nelze v aktuálním stavu provést.")
        self.worker.wake.set()

        if action in {"resume", "retry"} and job["prepared"] and not self.store.one("SELECT 1 FROM items WHERE job_id=? AND status IN ('pending','running') LIMIT 1", (identifier,)):
            self.worker.summarize(identifier)

    def source_action(self, identifier, body):
        source = self.store.one("SELECT * FROM sources WHERE id=?", (identifier,))
        if not source:
            raise Invalid("Zdroj nebyl nalezen.")
        action = body.get("action")
        if action == "delete":
            self.store.execute("DELETE FROM sources WHERE id=?", (identifier,))
        elif action == "check":
            self.store.execute("UPDATE sources SET next_check=? WHERE id=?", (now(), identifier))
        elif action == "toggle":
            self.store.execute("UPDATE sources SET enabled=1-enabled WHERE id=?", (identifier,))
        elif action == "update":
            config = source_config(body.get("config"), self.downloads)
            old = json.loads(source["config"])
            if config["url"] != old["url"] or config["start_mode"] != old["start_mode"] or config["start_date"] != old["start_date"]:
                raise Invalid("Začátek sledování a URL změň přidáním nového zdroje, aby se nepomíchala evidence.")
            self.store.execute("UPDATE sources SET config=?,next_check=? WHERE id=?", (encode(config), now(), identifier))
        else:
            raise Invalid("Neznámá operace zdroje.")
        self.worker.wake.set()

    def backup(self):
        # A consistent snapshot includes every job, not just the most recent UI page.
        with self.store.tx():
            result = {"schema": 1, "application": "MediaGrabber NAS", "version": __version__, "created": now(),
                "settings": self.store.settings(),
                "sources": [{"config": json.loads(s["config"]), "enabled": bool(s["enabled"]), "initialized": bool(s["initialized"]),
                             "seen": [r["media_id"] for r in self.store.all("SELECT media_id FROM seen WHERE source_id=?", (s["id"],))]}
                            for s in self.store.all("SELECT * FROM sources")],
                "jobs": [self.store.job(r["id"]) for r in self.store.all("SELECT id FROM jobs ORDER BY created")]}
        if len(encode(result).encode()) > MAX_BODY:
            raise Invalid("Záloha je větší než 32 MiB. Pro úplnou zálohu zastav kontejner a zkopíruj složku data.")
        return result

    def restore(self, body):
        if body.get("schema") != 1 or body.get("application") != "MediaGrabber NAS":
            raise Invalid("Neznámý formát zálohy.")
        raw_sources, raw_jobs = body.get("sources", []), body.get("jobs", [])
        if not isinstance(raw_sources, list) or len(raw_sources) > 1000 or not isinstance(raw_jobs, list) or len(raw_jobs) > 10000:
            raise Invalid("Záloha obsahuje příliš mnoho záznamů.")
        validated_settings = settings(body.get("settings", {}))
        validated_sources = []
        for source in raw_sources:
            if not isinstance(source, dict):
                raise Invalid("Neplatný zdroj v záloze.")
            config = source_config(source.get("config"), self.downloads)
            seen = source.get("seen", [])
            if not isinstance(seen, list) or len(seen) > 100000 or any(not isinstance(v, str) or not re.fullmatch(r"[A-Za-z0-9_-]{11}", v) for v in seen):
                raise Invalid("Poškozená evidence zdroje.")
            validated_sources.append((source, config, seen))
        validated_jobs = []
        total_items = 0
        for job in raw_jobs:
            entry = self.validate_jobs([job])[0]
            status = job.get("status")
            if status not in TERMINAL | {"queued", "processing", "paused", "interrupted"}:
                raise Invalid("Neplatný stav úlohy v záloze.")
            raw_items = job.get("items", [])
            if not isinstance(raw_items, list) or len(raw_items) > 10000:
                raise Invalid("Neplatné položky v záloze.")
            total_items += len(raw_items)
            if total_items > 100000:
                raise Invalid("Záloha obsahuje více než 100 000 položek.")
            normalized_items, positions = [], set()
            for item in raw_items:
                if not isinstance(item, dict):
                    raise Invalid("Neplatná položka v záloze.")
                link = youtube_url(item.get("url", ""), False)
                media_id = parse_qs(urlsplit(link).query).get("v", [""])[0]
                position, item_status = item.get("position"), item.get("status")
                if not media_id or type(position) is not int or not 1 <= position <= 10000 or position in positions or item_status not in {"pending", "running", "done", "skipped", "failed"}:
                    raise Invalid("Neplatné pořadí nebo stav položky v záloze.")
                positions.add(position)
                normalized_items.append({"id": media_id, "url": link, "title": str(item.get("title") or media_id)[:500], "position": position,
                                         "status": item_status, "error": str(item.get("error", ""))[:1800]})
            # The original frozen manifest survives transfer; imported paths never grant file access.
            entry["prepared_entries"] = normalized_items or None
            fingerprint = hashlib.sha256(encode({k: job.get(k) for k in ("id", "url", "created")}).encode()).hexdigest()
            validated_jobs.append((job, entry, status, fingerprint, normalized_items))
        # Imports never start new downloads or erase existing records.
        source_count = job_count = 0
        with self.store.tx() as db:
            existing_sources = {json.loads(r["config"])["url"] for r in db.execute("SELECT config FROM sources")}
            imported = set(self.store.get("imported_jobs", []))
            for raw, config, seen in validated_sources:
                if config["url"] in existing_sources:
                    continue
                identifier = uuid.uuid4().hex
                db.execute("INSERT INTO sources(id,config,enabled,next_check,initialized) VALUES(?,?,0,?,?)", (identifier, encode(config), now(), bool(raw.get("initialized"))))
                db.executemany("INSERT OR IGNORE INTO seen VALUES(?,?)", [(identifier, media_id) for media_id in seen])
                existing_sources.add(config["url"])
                source_count += 1
            for raw, entry, status, fingerprint, items in validated_jobs:
                if fingerprint in imported or db.execute("SELECT 1 FROM jobs WHERE id=?", (str(raw.get("id", "")),)).fetchone():
                    continue
                identifier = Store.insert_job(db, **entry)
                # Old paths are shown as history only; they never authorize file access on this NAS.
                final = status if status in TERMINAL else "paused"
                db.execute("UPDATE jobs SET status=?,error=? WHERE id=?", (final, "Importováno ze zálohy. Soubory se nepřenášejí." if final in TERMINAL else "Importováno — spusť tlačítkem Pokračovat.", identifier))
                if final in TERMINAL:
                    for item in items:
                        db.execute("UPDATE items SET status=?,error=?,progress=?,notice='Importovaná historie; soubor se nepřenášel.' WHERE job_id=? AND position=?",
                                   (item["status"], item["error"], 100 if item["status"] in {"done", "skipped"} else 0, identifier, item["position"]))
                imported.add(fingerprint)
                job_count += 1
            db.execute("INSERT OR REPLACE INTO kv VALUES('imported_jobs',?)", (encode(sorted(imported)[-10000:]),))
            db.execute("INSERT OR REPLACE INTO kv VALUES('settings',?)", (encode(validated_settings | {"queue_paused": True}),))
        return {"sources": source_count, "jobs": job_count, "notice": "Importováno. Zdroje jsou vypnuté, fronta pozastavená. Média se nepřenášejí."}


def create_app():
    data = Path(os.environ.get("MG_DATA", "/data"))
    downloads = Path(os.environ.get("MG_DOWNLOADS", "/downloads"))
    password_file = Path(os.environ.get("MG_PASSWORD_FILE", "/run/secrets/admin_password"))
    password = password_file.read_text("utf-8-sig").strip()
    dsm_key_file = os.environ.get("MG_DSM_KEY_FILE")
    dsm_key = Path(dsm_key_file).read_text("ascii").strip() if dsm_key_file else None
    app = App(data, downloads, password, secure_cookie=os.environ.get("MG_SECURE_COOKIE", "0") == "1",
              allowed_hosts=[s.strip() for s in os.environ.get("MG_ALLOWED_HOSTS", "").split(",") if s.strip()], dsm_key=dsm_key)
    atexit.register(app.close)
    return app
