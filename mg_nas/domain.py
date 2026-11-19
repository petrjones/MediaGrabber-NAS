# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

import datetime as dt
import hashlib
import json
import re
from pathlib import Path
from urllib.parse import parse_qs, quote, unquote, urlencode, urlsplit
from zoneinfo import ZoneInfo


class Invalid(ValueError):
    pass


def now() -> float:
    return dt.datetime.now(dt.timezone.utc).timestamp()


def youtube_url(value: str, playlist: bool = True, source: bool = False) -> str:
    if not isinstance(value, str) or len(value) > 2048:
        raise Invalid("Neplatný odkaz.")
    try:
        p = urlsplit(value.strip())
        host = (p.hostname or "").lower()
        if p.scheme != "https" or p.username or p.password or p.port not in (None, 443):
            raise Invalid("Použij HTTPS odkaz na YouTube.")
    except ValueError as e:
        raise Invalid("Neplatný odkaz.") from e
    if host not in {"youtube.com", "www.youtube.com", "m.youtube.com", "music.youtube.com", "youtu.be", "www.youtu.be"}:
        raise Invalid("První NAS verze přijímá odkazy pouze z YouTube.")
    q = parse_qs(p.query)
    list_id = q.get("list", [""])[0]
    if playlist and list_id:
        if not re.fullmatch(r"[A-Za-z0-9_-]{8,180}", list_id):
            raise Invalid("Neplatný identifikátor playlistu.")
        return "https://www.youtube.com/playlist?" + urlencode({"list": list_id})
    video = p.path.strip("/") if host.endswith("youtu.be") else q.get("v", [""])[0]
    if p.path.startswith(("/shorts/", "/live/")):
        video = p.path.split("/")[2]
    if re.fullmatch(r"[A-Za-z0-9_-]{11}", video):
        if source:
            raise Invalid("Pro sledování vlož odkaz na celý kanál nebo playlist.")
        return "https://www.youtube.com/watch?v=" + video
    decoded = unquote(p.path).rstrip("/")
    if re.fullmatch(r"/(?:@[\w.\-]{1,100}|channel/[A-Za-z0-9_-]{10,100}|c/[\w.\-]{1,100}|user/[\w.\-]{1,100})(?:/(?:videos|shorts|streams))?", decoded, re.UNICODE):
        if not playlist:
            raise Invalid("Pro celý kanál zapni stažení playlistu, nebo vlož odkaz na jednotlivé video.")
        return "https://www.youtube.com" + quote(decoded, safe="/@-._")
    raise Invalid("Vlož odkaz na video, playlist nebo kartu Videa kanálu.")


def destination(root: Path, relative: str, create: bool = False) -> Path:
    if not isinstance(relative, str) or len(relative) > 240 or "\\" in relative or ":" in relative or "\x00" in relative:
        raise Invalid("Cíl musí být relativní podsložka povolené složky downloads.")
    if relative.startswith("/") or any(part in {"..", "."} for part in relative.split("/") if part):
        raise Invalid("Cíl nesmí obsahovat nadřazenou nebo absolutní cestu.")
    root = root.resolve()
    path = (root / relative).resolve()
    if not path.is_relative_to(root):
        raise Invalid("Cílová cesta opouští povolenou složku.")
    if create:
        path.mkdir(parents=True, exist_ok=True)
    return path


def safe_name(text: str, limit: int = 140) -> str:
    text = re.sub(r'[<>:"/\\|?*\x00-\x1f]', " ", str(text))
    text = re.sub(r"\s+", " ", text).strip(" .")[:limit].rstrip(" .")
    # NAS filesystems limit UTF-8 bytes per component, not Python characters.
    text = text.encode("utf-8")[:180].decode("utf-8", errors="ignore").rstrip(" .")
    if not text or text.upper().split(".")[0] in {"CON", "PRN", "AUX", "NUL", *(f"COM{i}" for i in range(1, 10)), *(f"LPT{i}" for i in range(1, 10))}:
        return "Zaznam"
    return text


def indices(text: str) -> list[int]:
    if isinstance(text, list):
        if len(text) > 10000 or any(type(i) is not int or not 1 <= i <= 10000 for i in text):
            raise Invalid("Neplatná čísla vynechaných položek.")
        return sorted(set(text))
    if not isinstance(text, str) or len(text) > 4000:
        raise Invalid("Příliš dlouhý výběr položek.")
    result = set()
    for token in re.split(r"[,;\s]+", text.strip()):
        if not token:
            continue
        m = re.fullmatch(r"(\d+)(?:[-–](\d+))?", token)
        if not m:
            raise Invalid("Vynechání zapisuj jako 3, 7, 10-12.")
        a, b = int(m[1]), int(m[2] or m[1])
        if not 1 <= a <= b <= 10000:
            raise Invalid("Čísla položek musí být mezi 1 a 10000.")
        result.update(range(a, b + 1))
    return sorted(result)


def options(raw: dict | None, root: Path) -> dict:
    raw = raw or {}
    if not isinstance(raw, dict):
        raise Invalid("Nastavení není objekt.")
    mode = raw.get("mode", "audio")
    quality = raw.get("quality", "mp3_256" if mode == "audio" else "1080")
    allowed = {"audio": {"mp3_192", "mp3_256", "mp3_320", "m4a", "original"}, "video": {"best", "2160", "1440", "1080", "720", "480"}}
    if not isinstance(mode, str) or not isinstance(quality, str) or mode not in allowed or quality not in allowed[mode]:
        raise Invalid("Neplatný typ nebo kvalita stahování.")
    subs = raw.get("subtitles", "")
    if not isinstance(subs, str) or subs not in {"", "cs", "en", "es", "de", "fr", "pt", "pl", "it"}:
        raise Invalid("Neplatný jazyk titulků.")
    folder = raw.get("folder", "")
    destination(root, folder)
    selected = raw.get("selected", [])
    if not isinstance(selected, list) or len(selected) > 10000 or any(type(i) is not int or not 1 <= i <= 10000 for i in selected):
        raise Invalid("Neplatný výběr položek.")
    result = {"mode": mode, "quality": quality, "subtitles": subs, "folder": folder,
              "selected": sorted(set(selected)), "exclude": indices(raw.get("exclude", ""))}
    for name, default in {"playlist": True, "metadata": True, "subfolder": True, "renumber": False, "duplicates": True}.items():
        if type(raw.get(name, default)) is not bool:
            raise Invalid("Neplatná přepínací volba: " + name)
        result[name] = raw.get(name, default)
    date_after = raw.get("date_after", "")
    if date_after:
        try:
            dt.date.fromisoformat(date_after)
        except (ValueError, TypeError):
            raise Invalid("Neplatné počáteční datum úlohy.")
    result["date_after"] = date_after
    return result


def profile_key(opts: dict) -> str:
    # Selection/order belongs to the job, not to the identity of a media encoding.
    fields = {k: opts[k] for k in ("mode", "quality", "subtitles", "folder", "metadata", "subfolder")}
    return hashlib.sha256(json.dumps(fields, sort_keys=True).encode()).hexdigest()


DEFAULTS = {"timezone": "Europe/Prague", "window_start": "00:00", "window_end": "00:00",
            "rate_kib": 0, "minimum_free_mb": 1024, "max_attempts": 3, "queue_paused": False}


def settings(raw: dict) -> dict:
    if not isinstance(raw, dict):
        raise Invalid("Nastavení není objekt.")
    result = DEFAULTS | raw
    try:
        ZoneInfo(result["timezone"])
    except (KeyError, ValueError, TypeError) as e:
        raise Invalid("Neznámé časové pásmo.") from e
    for k in ("window_start", "window_end"):
        if not isinstance(result[k], str) or not re.fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\d", result[k]):
            raise Invalid("Čas okna zapisuj jako HH:MM.")
    for k, low, high in (("rate_kib", 0, 1000000), ("minimum_free_mb", 100, 1000000), ("max_attempts", 1, 5)):
        if type(result[k]) is not int or not low <= result[k] <= high:
            raise Invalid("Neplatná hodnota nastavení: " + k)
    if type(result["queue_paused"]) is not bool:
        raise Invalid("Neplatný stav fronty.")
    return {k: result[k] for k in DEFAULTS}


def in_window(config: dict, timestamp: float | None = None) -> bool:
    if config["window_start"] == config["window_end"]:
        return True
    local = dt.datetime.fromtimestamp(timestamp if timestamp is not None else now(), ZoneInfo(config["timezone"]))
    clock = local.strftime("%H:%M")
    start, end = config["window_start"], config["window_end"]
    return start <= clock < end if start < end else clock >= start or clock < end
