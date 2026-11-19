# SPDX-License-Identifier: GPL-3.0-or-later
"""Read public Windows release metadata on demand; retain the last verified value."""
from __future__ import annotations

import json
import math
import re
import threading
import time
from urllib.request import Request, urlopen

PROJECT = "https://github.com/petrjones/MediaGrabber"
API_URL = "https://api.github.com/repos/petrjones/MediaGrabber/releases/latest"
CACHE_KEY = "windows_release"
CHECK_INTERVAL = 6 * 60 * 60
RETRY_INTERVAL = 5 * 60
MAX_RESPONSE = 256 * 1024
TAG = re.compile(r"v?\d{1,6}(?:\.\d{1,6}){1,3}")


class WindowsRelease:
    def __init__(self, store):
        self.store = store
        self.lock = threading.Lock()
        self.record = self.valid_record(store.get(CACHE_KEY), time.time())
        self.next_attempt = 0
        self.failed = False

    @staticmethod
    def valid_record(value, stamp):
        if not isinstance(value, dict) or not isinstance(value.get("tag"), str) or not TAG.fullmatch(value["tag"]):
            return None
        checked = value.get("checked_at")
        if type(checked) not in (int, float) or not math.isfinite(checked) or not 0 <= checked <= stamp + 300:
            return None
        return {"tag": value["tag"], "checked_at": checked}

    @staticmethod
    def fetch(stamp):
        request = Request(API_URL, headers={"Accept": "application/vnd.github+json",
                                          "User-Agent": "PJSoft-MediaGrabber-NAS",
                                          "X-GitHub-Api-Version": "2022-11-28"})
        with urlopen(request, timeout=3) as response:
            if response.status != 200 or response.geturl() != API_URL:
                raise ValueError("Unexpected release response")
            raw = response.read(MAX_RESPONSE + 1)
        if len(raw) > MAX_RESPONSE:
            raise ValueError("Release response too large")
        data = json.loads(raw)
        if not isinstance(data, dict) or data.get("draft") is not False or data.get("prerelease") is not False:
            raise ValueError("Not a stable public release")
        record = WindowsRelease.valid_record({"tag": data.get("tag_name"), "checked_at": stamp}, stamp)
        assets = data.get("assets")
        if not record or not isinstance(assets, list) or not any(
                isinstance(asset, dict) and isinstance(asset.get("name"), str)
                and re.fullmatch(r"MediaGrabber-[\w.-]+-Windows-[\w.-]+\.zip", asset["name"], re.IGNORECASE)
                for asset in assets):
            raise ValueError("Not a Windows release")
        return record

    def get(self):
        with self.lock:
            stamp = time.time()
            fresh = self.record and 0 <= stamp - self.record["checked_at"] < CHECK_INTERVAL
            if not (fresh and not self.failed) and stamp >= self.next_attempt:
                try:
                    record = self.fetch(stamp)
                except (OSError, ValueError, TypeError):
                    self.failed = True
                    self.next_attempt = stamp + RETRY_INTERVAL
                else:
                    self.store.set(CACHE_KEY, record)
                    self.record = record
                    self.failed = False
            if self.record:
                return {"status": "cached" if self.failed else "current",
                        "version": self.record["tag"].removeprefix("v"),
                        "url": PROJECT + "/releases/tag/" + self.record["tag"],
                        "checked_at": self.record["checked_at"]}
            return {"status": "unavailable", "version": None, "url": PROJECT + "/releases/latest"}
