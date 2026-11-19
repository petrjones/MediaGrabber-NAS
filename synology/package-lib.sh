#!/bin/sh
# Shared SPK lifecycle functions. Never source passwords or user-controlled shell.
set -eu
MG_STATE_SCHEMA=1
MG_PACKAGE_ID=MediaGrabberNAS
MG_TARGET=${SYNOPKG_PKGDEST:?}
MG_VAR=${SYNOPKG_PKGVAR:-/var/packages/MediaGrabberNAS/var}
MG_RUNTIME="$MG_VAR/runtime"
MG_SHARE=${MG_SPK_SHARE_PATH:-/var/packages/MediaGrabberNAS/shares/MediaGrabber}

mg_fail() {
    printf '%s\n' "$1" >&2
    if [ -n "${SYNOPKG_TEMP_LOGFILE:-}" ]; then
        printf '%s\n' "$1" > "$SYNOPKG_TEMP_LOGFILE"
    fi
    exit 1
}

mg_setting() {
    if [ -f "$MG_RUNTIME/settings.env" ]; then
        sed -n "s/^$1=//p" "$MG_RUNTIME/settings.env" | head -n 1
    fi
}

mg_numeric() {
    case "$1" in ''|*[!0-9]*) return 1 ;; esac
    [ "$1" -gt 0 ]
}

mg_validate_schema() {
    [ -f "$MG_RUNTIME/schema" ] || mg_fail "Missing MediaGrabber state marker. / Chybi oznaceni dat aplikace."
    schema=$(cat "$MG_RUNTIME/schema")
    [ "$schema" = "$MG_STATE_SCHEMA" ] || mg_fail "Unsupported state schema; existing data was preserved. / Nepodporovana verze dat. Data zustala zachovana."
}

mg_validate_state() {
    mg_validate_schema
    [ -s "$MG_RUNTIME/secrets/admin_password" ] || mg_fail "Missing application password. / Chybi heslo aplikace."
}

mg_backup() {
    # Called in postinst during UPGRADE: the old container is already stopped.
    # Copy database + WAL/SHM together; never put media in this archive.
    mkdir -p "$MG_RUNTIME/backups"
    chmod 700 "$MG_RUNTIME/backups"
    stamp=$(date -u +%Y%m%dT%H%M%SZ)
    new_version=$(cat "$MG_TARGET/SPK_VERSION")
    backup="$MG_RUNTIME/backups/before-$new_version-$stamp-$$.tar.gz"
    tar -czf "$backup.tmp" -C "$MG_RUNTIME" data settings.env secrets schema || {
        rm -f "$backup.tmp"
        mg_fail "Unable to back up stopped application data. Upgrade setup aborted. / Zaloha dat se nezdarila."
    }
    chmod 600 "$backup.tmp"
    mv "$backup.tmp" "$backup"
}

mg_write_settings() {
    uid=$(id -u)
    gid=$(id -g)
    mg_numeric "$uid" || mg_fail "The installer must run under its non-root package account."
    if ! mg_numeric "$gid"; then gid=$uid; fi
    secure=$(mg_setting MG_SECURE_COOKIE)
    secure=${secure:-0}
    case "$secure" in 0|1) ;; *) mg_fail "Invalid MG_SECURE_COOKIE." ;; esac
    hosts=$(mg_setting MG_ALLOWED_HOSTS)
    if [ ! -f "$MG_RUNTIME/settings.env" ]; then
        host=$(hostname | tr '[:upper:]' '[:lower:]')
        case "$host" in ''|*[!a-z0-9._-]*) host='' ;; esac
        if [ -n "$host" ]; then
            hosts=$host
            case "$host" in *.*) ;; *) hosts="$host,$host.local" ;; esac
        fi
    fi
    case "$hosts" in *[!a-zA-Z0-9.,:_-]*) mg_fail "Invalid MG_ALLOWED_HOSTS." ;; esac
    [ "${#hosts}" -le 512 ] || mg_fail "MG_ALLOWED_HOSTS is too long."
    {
        printf 'PUID=%s\nPGID=%s\nMG_PORT=8787\nMG_SECURE_COOKIE=%s\nMG_ALLOWED_HOSTS=%s\n' "$uid" "$gid" "$secure" "$hosts"
    } > "$MG_RUNTIME/settings.env.new"
    chmod 600 "$MG_RUNTIME/settings.env.new"
    mv "$MG_RUNTIME/settings.env.new" "$MG_RUNTIME/settings.env"
    cp "$MG_RUNTIME/settings.env" "$MG_RUNTIME/secrets/runtime.env.new"
    chmod 600 "$MG_RUNTIME/secrets/runtime.env.new"
    mv "$MG_RUNTIME/secrets/runtime.env.new" "$MG_RUNTIME/secrets/runtime.env"
}

mg_install() {
    umask 077
    case "${SYNOPKG_PKGNAME:-MediaGrabberNAS}" in MediaGrabberNAS) ;; *) mg_fail "Unexpected package identity." ;; esac
    if [ -f "$MG_RUNTIME/schema" ]; then
        mg_validate_schema
        if [ "${SYNOPKG_PKG_STATUS:-INSTALL}" = UPGRADE ]; then
            mg_validate_state
            mg_backup
        fi
    else
        [ "${SYNOPKG_PKG_STATUS:-INSTALL}" != UPGRADE ] || mg_fail "Cannot initialize missing state during upgrade."
        [ ! -e "$MG_RUNTIME" ] || mg_fail "Unrecognized runtime directory; existing files were left untouched."
        mkdir -p "$MG_RUNTIME/data" "$MG_RUNTIME/secrets"
        printf '%s\n' "$MG_STATE_SCHEMA" > "$MG_RUNTIME/schema"
    fi
    chmod 700 "$MG_RUNTIME" "$MG_RUNTIME/data" "$MG_RUNTIME/secrets"
    if [ "${SYNOPKG_PKG_STATUS:-INSTALL}" != UPGRADE ]; then
        # An explicit install/reinstall uses the password entered in its wizard.
        [ -n "${wizard_admin_password:-}" ] || mg_fail "Missing password from installation wizard."
        printf '%s\n' "$wizard_admin_password" > "$MG_RUNTIME/secrets/admin_password.new"
        chmod 600 "$MG_RUNTIME/secrets/admin_password.new"
        mv "$MG_RUNTIME/secrets/admin_password.new" "$MG_RUNTIME/secrets/admin_password"
    fi
    mg_validate_state
    if [ ! -f "$MG_RUNTIME/secrets/dsm_bridge_key" ]; then
        # Random private host-to-container key; never a DSM password or cookie.
        od -An -N32 -tx1 /dev/urandom | tr -d ' \n' > "$MG_RUNTIME/secrets/dsm_bridge_key.new"
        [ "$(wc -c < "$MG_RUNTIME/secrets/dsm_bridge_key.new" | tr -d ' ')" = 64 ] || mg_fail "Unable to generate DSM bridge key."
        chmod 600 "$MG_RUNTIME/secrets/dsm_bridge_key.new"
        mv "$MG_RUNTIME/secrets/dsm_bridge_key.new" "$MG_RUNTIME/secrets/dsm_bridge_key"
    fi
    mg_write_settings
    printf '%s\n' "MediaGrabber NAS state and private runtime settings are ready."
}

mg_prestart() {
    mg_validate_state
    [ -d "$MG_SHARE" ] && [ -r "$MG_SHARE" ] && [ -w "$MG_SHARE" ] || mg_fail "MediaGrabber shared folder is unavailable or not writable. / Sdilena slozka MediaGrabber neni dostupna pro zapis."
}

mg_running() {
    health_url=${MG_SPK_HEALTH_URL:-http://127.0.0.1:8787/healthz}
    if command -v curl >/dev/null 2>&1; then
        reply=$(curl -fsS --max-time 3 "$health_url" 2>/dev/null) || return 1
    elif command -v wget >/dev/null 2>&1; then
        reply=$(wget -q -T 3 -O - "$health_url" 2>/dev/null) || return 1
    else
        return 1
    fi
    printf '%s' "$reply" | grep -q '"application":"MediaGrabber NAS"'
}
