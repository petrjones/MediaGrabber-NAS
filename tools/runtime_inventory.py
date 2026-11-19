# SPDX-License-Identifier: GPL-3.0-or-later
"""Public build-time software inventory. Never reads runtime secrets or user state."""
import hashlib
import importlib.metadata as metadata
import json
import platform
import subprocess
from pathlib import Path


def command(args):
    result = subprocess.run(args, capture_output=True, text=True, timeout=30, check=True)
    return (result.stdout + result.stderr).strip()


def inventory():
    packages = []
    for line in command(["dpkg-query", "-W", "-f=${Package}\t${Version}\t${source:Package}\t${source:Version}\n"]).splitlines():
        name, version, source, source_version = line.split("\t")
        notice = Path("/usr/share/doc") / name / "copyright"
        packages.append({"name":name,"version":version,"source":source or name,"source_version":source_version or version,
                         "copyright_sha256":hashlib.sha256(notice.read_bytes()).hexdigest() if notice.is_file() else None})
    return {"python":platform.python_version(),"node":command(["node","--version"]),
            "ffmpeg":command(["ffmpeg","-version"]),"ffmpeg_license":command(["ffmpeg","-L"]),
            "debian_packages":packages,
            "python_packages":[{"name":d.metadata["Name"],"version":d.version} for d in sorted(metadata.distributions(),key=lambda d:d.metadata["Name"].lower())]}


if __name__ == "__main__":
    print(json.dumps(inventory(), indent=2))
