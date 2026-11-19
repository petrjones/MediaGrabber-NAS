# SPDX-License-Identifier: GPL-3.0-or-later
"""SPK-only bootstrap: obtain IDs from the NAS data mount, then permanently drop.

The standalone image still starts directly as USER 1000. The SPK uses this module
because its Compose must be immutable and present before DSM's postinst hook.
"""
from __future__ import annotations

import ctypes
import os
import re
import stat
import sys
from pathlib import Path


def mounted_identity(path: Path):
    info = path.stat()
    if not stat.S_ISDIR(info.st_mode) or info.st_uid <= 0:
        raise RuntimeError("The NAS data mount must be owned by the internal non-root package account.")
    # A package hook can inherit a root primary group. Never retain group 0.
    return info.st_uid, info.st_gid if info.st_gid > 0 else info.st_uid


def drop_identity(uid, gid, system=os):
    if uid <= 0 or gid <= 0:
        raise RuntimeError("Refusing a root application identity.")
    if system.geteuid() != 0:
        raise RuntimeError("The SPK bootstrap requires its brief SETUID/SETGID startup context.")
    system.setgroups([])
    system.setresgid(gid, gid, gid)
    system.setresuid(uid, uid, uid)
    if system.getresuid() != (uid, uid, uid) or system.getresgid() != (gid, gid, gid):
        raise RuntimeError("Unable to permanently drop the bootstrap identity.")


def no_new_privileges():
    """Read the flag on Linux 3.5+, including kernels without its proc field."""
    try:
        prctl = ctypes.CDLL(None, use_errno=True).prctl
        prctl.argtypes = [ctypes.c_int, *([ctypes.c_ulong] * 4)]
        prctl.restype = ctypes.c_int
        return prctl(39, 0, 0, 0, 0) == 1  # PR_GET_NO_NEW_PRIVS; never set/relax it.
    except (OSError, AttributeError):
        return False


def kernel_is_unprivileged(text):
    fields = dict(line.split(":", 1) for line in text.splitlines() if ":" in line)
    try:
        if int(fields.get("CapEff", "1").strip(), 16) != 0:
            return False
    except ValueError:
        return False
    if "NoNewPrivs" in fields:
        return fields["NoNewPrivs"].strip() == "1"
    # /proc/self/status only gained NoNewPrivs in Linux 4.10. Query the
    # same flag via prctl on older kernels; inability to verify still rejects.
    return no_new_privileges()


def runtime_settings(path: Path):
    if not path.is_file() or path.stat().st_size > 8192:
        raise RuntimeError("Missing or invalid private runtime settings from the SPK installer.")
    values = {}
    for line in path.read_text("utf-8").splitlines():
        key, separator, value = line.partition("=")
        if separator and key in {"MG_ALLOWED_HOSTS", "MG_SECURE_COOKIE"}:
            if key in values:
                raise RuntimeError("Duplicate runtime setting.")
            values[key] = value
    if values.get("MG_SECURE_COOKIE", "0") not in {"0", "1"}:
        raise RuntimeError("Invalid secure-cookie setting.")
    if not re.fullmatch(r"[A-Za-z0-9.,:_-]{0,512}", values.get("MG_ALLOWED_HOSTS", "")):
        raise RuntimeError("Invalid allowed-host setting.")
    return values


def main(command=None):
    command = sys.argv[1:] if command is None else command
    if not command:
        raise RuntimeError("Missing application command.")
    uid, gid = mounted_identity(Path(os.environ.get("MG_DATA", "/data")))
    drop_identity(uid, gid)
    if not kernel_is_unprivileged(Path("/proc/self/status").read_text()):
        raise RuntimeError("Application startup refused: capabilities were not cleared or no-new-privileges is missing.")
    values = runtime_settings(Path(os.environ.get("MG_RUNTIME_SETTINGS_FILE", "/run/secrets/runtime.env")))
    os.environ.update(values, USER="mediagrabber", LOGNAME="mediagrabber")
    print(f"MediaGrabber SPK: starting as non-root UID {uid}, GID {gid}, no effective capabilities.", flush=True)
    # tini must start AFTER the UID drop so it can signal its same-UID children
    # without adding CAP_KILL to the container.
    os.execv("/usr/bin/tini", ["/usr/bin/tini", "--", *command])


if __name__ == "__main__":
    try:
        main()
    except (OSError, RuntimeError, ValueError) as exc:
        print("MediaGrabber SPK startup: " + str(exc), file=sys.stderr)
        raise SystemExit(1)
