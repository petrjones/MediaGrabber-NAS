# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

import collections
import json
import os
import re
import shutil
import signal
import subprocess
import tempfile
import time
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from .domain import Invalid, youtube_url

MEDIA_EXTENSIONS = {".mp3", ".m4a", ".opus", ".ogg", ".flac", ".wav", ".webm", ".mp4", ".mkv", ".mov", ".aac"}


class Interrupted(Exception):
    pass


class EngineError(Exception):
    def __init__(self, message, transient=False):
        super().__init__(message)
        self.transient = transient


def transient_error(text):
    return any(value in text.lower() for value in ("timed out", "timeout", "connection reset", "temporary failure", "unable to download", "http error 429", "http error 500", "http error 502", "http error 503", "network is unreachable")) and not any(value in text.lower() for value in ("video unavailable", "private video", "removed by", "copyright", "not available"))


class Engine:
    def __init__(self, data: Path, executable=None, ffmpeg=None):
        self.data = data
        self.executable = executable or os.environ.get("MG_YTDLP", "yt-dlp")
        self.ffmpeg = ffmpeg or os.environ.get("MG_FFMPEG") or shutil.which("ffmpeg") or "ffmpeg"
        (data / "process").mkdir(exist_ok=True)

    def _run(self, args, stop=lambda: "", progress=lambda p: None, capture=False, timeout=21600):
        output = tempfile.NamedTemporaryFile(prefix="run-", suffix=".log", dir=self.data / "process", delete=False)
        filename, proc = Path(output.name), None
        tail = collections.deque(maxlen=35)
        started, last_progress = time.monotonic(), 0.0
        try:
            proc = subprocess.Popen([self.executable, "--ignore-config", "--no-colors", "--encoding", "utf-8", *args], stdout=output,
                                    stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL,
                                    start_new_session=os.name != "nt", creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            with filename.open("r", encoding="utf-8", errors="replace") as reader:
                while True:
                    reason = stop()
                    if reason:
                        raise Interrupted(reason)
                    if time.monotonic() - started > timeout:
                        raise EngineError("Vypršel časový limit nástroje.", True)
                    if filename.stat().st_size > 32 * 1024 * 1024:
                        raise EngineError("Výpis nástroje překročil povolenou velikost.")
                    line = reader.readline(32 * 1024 * 1024)
                    if line:
                        if not capture:
                            tail.append(line[-2500:].strip())
                        if line.startswith("__MG_PROGRESS__") and time.monotonic() - last_progress > 0.8:
                            try:
                                downloaded, total = map(float, line.removeprefix("__MG_PROGRESS__").strip().split("/"))
                                if total > 0:
                                    progress(min(99.0, downloaded / total * 100))
                                    last_progress = time.monotonic()
                            except (ValueError, ZeroDivisionError):
                                pass
                    elif proc.poll() is not None:
                        break
                    else:
                        time.sleep(0.1)
            text = filename.read_text("utf-8", errors="replace") if capture else "\n".join(tail)
            return proc.wait(), text
        except FileNotFoundError as e:
            raise EngineError("Nástroj yt-dlp nebyl nalezen. Ověř instalaci kontejneru.") from e
        finally:
            if proc is not None and proc.poll() is None:
                if os.name != "nt":
                    try:
                        os.killpg(proc.pid, signal.SIGTERM)
                    except ProcessLookupError:
                        pass
                else:
                    subprocess.run(["taskkill", "/PID", str(proc.pid), "/T", "/F"], capture_output=True, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
                try:
                    proc.wait(timeout=8)
                except subprocess.TimeoutExpired:
                    if os.name != "nt":
                        try:
                            os.killpg(proc.pid, signal.SIGKILL)
                        except ProcessLookupError:
                            pass
                    proc.kill()
            output.close()
            filename.unlink(missing_ok=True)

    def listing(self, url, playlist=True, stop=lambda: "", selected=None):
        args = ["--dump-single-json", "--skip-download", "--flat-playlist", "--ignore-errors", "--no-warnings",
                "--socket-timeout", "30", "--extractor-retries", "2", "--js-runtimes", "node",
                "--yes-playlist" if playlist else "--no-playlist"]
        if selected:
            args += ["--playlist-items", ",".join(map(str, selected))]
        else:
            args += ["--playlist-end", "10001"]
        code, text = self._run([*args, "--", url], stop=stop, capture=True, timeout=600)
        # Older builds appended /videos to every channel. Retry only the specific
        # missing-tab error; network/authentication failures must remain failures.
        if code != 0 and url.endswith("/videos") and "does not have a videos tab" in text:
            root = youtube_url(url[:-7])
            return self.listing(root, playlist, stop, selected)
        try:
            info = next(json.loads(line) for line in reversed(text.splitlines()) if line.startswith("{"))
        except (StopIteration, ValueError) as e:
            raise EngineError(self.error(text) or "Zdroj se nepodařilo načíst.", transient_error(text)) from e
        entries = info.get("entries")
        if entries is None:
            entries = [info]
        if not isinstance(entries, list) or len(entries) > 10000:
            raise EngineError("Zdroj má více než 10 000 položek. Použij menší playlist.")
        # Channel roots can contain nested playlists for videos/shorts/streams.
        # Flatten them without fetching individual videos, retaining global positions.
        normalized, seen = [], set()
        nested = any(isinstance(e, dict) and "entries" in e for e in entries)
        def leaves(items, depth=0):
            if depth > 8 or not isinstance(items, list):
                raise EngineError("Neplatný nebo příliš vnořený seznam zdroje.")
            for entry in items:
                if not isinstance(entry, dict):
                    continue
                if "entries" in entry:
                    yield from leaves(entry["entries"], depth + 1)
                else:
                    yield entry
        for i, entry in enumerate(leaves(entries), 1):
            if i > 10000:
                raise EngineError("Zdroj má více než 10 000 položek. Použij menší playlist.")
            identifier = str(entry.get("id") or "")
            try:
                link = youtube_url("https://www.youtube.com/watch?v=" + identifier, playlist=False)
            except Invalid:
                continue
            if nested and identifier in seen:
                continue
            seen.add(identifier)
            normalized.append({"id": identifier, "url": link, "title": str(entry.get("title") or identifier)[:500],
                               "position": len(normalized) + 1 if nested else int(entry.get("playlist_index") or i),
                               "duration": entry.get("duration"), "upload_date": entry.get("upload_date")})
        if not normalized:
            raise EngineError(self.error(text) or "Zdroj neobsahuje žádné dostupné identifikátory videí.")
        # An incomplete baseline must never be silently accepted as a complete source.
        if code != 0 and info.get("_type") == "playlist":
            raise EngineError(self.error(text) or "Seznam je neúplný. Kontrola se později zopakuje.", True)
        return {"title": str(info.get("title") or "YouTube")[:500], "entries": normalized}

    @staticmethod
    def error(text):
        lines = [line.strip() for line in text.splitlines() if "ERROR:" in line]
        return (lines[-1] if lines else text.strip().splitlines()[-1] if text.strip() else "")[-1800:]

    def download_args(self, item, opts, base: Path, config, without_subtitles=False, date_after=""):
        args = ["--no-playlist", "--no-simulate", "--no-warnings", "--newline", "--progress", "--no-overwrites", "--continue",
                "--socket-timeout", "30", "--retries", "2", "--fragment-retries", "2", "--concurrent-fragments", "1",
                "--js-runtimes", "node", "--ffmpeg-location", self.ffmpeg, "--output", str(base).replace("%", "%%") + ".%(ext)s",
                "--print", "after_move:__MG_FILE__%(filepath)j",
                "--progress-template", "download:__MG_PROGRESS__%(progress.downloaded_bytes)s/%(progress.total_bytes,progress.total_bytes_estimate)s"]
        if opts["mode"] == "audio":
            args += ["-f", "bestaudio/best", "-x"]
            quality = opts["quality"]
            if quality.startswith("mp3_"):
                args += ["--audio-format", "mp3", "--audio-quality", quality.split("_")[1] + "K"]
            elif quality == "m4a":
                args += ["--audio-format", "m4a"]
            else:
                args += ["--audio-format", "best"]
        else:
            height = "" if opts["quality"] == "best" else "[height<=" + opts["quality"] + "]"
            args += ["-f", "bestvideo" + height + "+bestaudio/best" + height, "--merge-output-format", "mkv", "--remux-video", "mkv"]
        if opts["metadata"]:
            args += ["--embed-metadata", "--embed-thumbnail", "--convert-thumbnails", "jpg"]
        if opts["subtitles"] and not without_subtitles:
            args += ["--write-subs", "--write-auto-subs", "--sub-langs", opts["subtitles"] + ".*", "--sub-format", "srt/best", "--convert-subs", "srt"]
        if config["rate_kib"]:
            args += ["--limit-rate", str(config["rate_kib"]) + "K"]
        if date_after:
            args += ["--dateafter", date_after.replace("-", ""), "--print", "pre_process:__MG_DATE__%(upload_date)s"]
        return [*args, "--", item["url"]]

    def download(self, item, opts, base, config, stop, progress, date_after=""):
        notice = ""
        code, text = self._run(self.download_args(item, opts, base, config, date_after=date_after), stop, progress)
        low = text.lower()
        subtitle_failure = any(re.search(r"ERROR:.*(?:unable to download (?:video )?subtitles|subtitles?.*(?:HTTP Error|failed))", line, re.I) for line in text.splitlines())
        if code and opts["subtitles"] and subtitle_failure:
            notice = "Titulky se nepodařilo získat; položka byla zopakována bez titulků."
            code, text = self._run(self.download_args(item, opts, base, config, True, date_after), stop, progress)
            low = text.lower()
        if code:
            message = self.error(text) or "yt-dlp skončil chybou " + str(code)
            raise EngineError(message, transient_error(text))
        paths = []
        for line in text.splitlines():
            if line.startswith("__MG_FILE__"):
                try:
                    path = Path(json.loads(line.removeprefix("__MG_FILE__"))).resolve()
                    if path.is_file() and path.suffix.lower() in MEDIA_EXTENSIONS and path.stat().st_size > 0:
                        paths.append(str(path))
                except (ValueError, TypeError, OSError):
                    pass
        if not paths:
            dates = [line.removeprefix("__MG_DATE__").strip() for line in text.splitlines() if line.startswith("__MG_DATE__")]
            filtered_by_date = date_after and any(re.fullmatch(r"\d{8}", value) and value < date_after.replace("-", "") for value in dates)
            if filtered_by_date or (date_after and any(v in low for v in ("upload date is not in range", "does not pass filter"))):
                return {"paths": [], "notice": "Položka je starší než zvolené datum.", "filtered": True}
            raise EngineError("Nástroj neoznámil žádný dokončený mediální soubor. " + self.error(text))
        for name in paths:
            # Keep covers readable in older Windows players as in the desktop edition.
            if name.lower().endswith(".mp3") and opts["metadata"]:
                try:
                    from mutagen.id3 import ID3
                    tags = ID3(name)
                    tags.save(name, v2_version=3)
                except ImportError:
                    notice = (notice + " Kontrola kompatibility ID3 není dostupná.").strip()
                except Exception as exc:
                    notice = (notice + " Úprava kompatibility ID3 se nezdařila: " + str(exc)[:200]).strip()
        return {"paths": sorted(set(paths)), "notice": notice, "filtered": False}
