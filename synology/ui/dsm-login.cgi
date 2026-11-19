#!/bin/sh
# Executed by DSM's CGI handler as mg-nas. No host root or DSM password needed.
set -eu
PATH=/usr/bin:/bin:/usr/sbin:/sbin:/usr/syno/bin:/usr/syno/sbin
export PATH

fail() {
    case "${HTTP_ACCEPT:-}" in *application/json*)
        escaped=$(printf '%s' "$2" | sed 's/\\/\\\\/g; s/"/\\"/g')
        printf 'Status: %s\r\nContent-Type: application/json; charset=utf-8\r\nCache-Control: no-store\r\nReferrer-Policy: no-referrer\r\n\r\n{"error":"%s"}' "$1" "$escaped"
        exit 0
    ;; esac
    printf 'Status: %s\r\nContent-Type: text/html; charset=utf-8\r\nCache-Control: no-store\r\nReferrer-Policy: no-referrer\r\nContent-Security-Policy: default-src '\''none'\''; frame-ancestors '\''self'\''\r\n\r\n' "$1"
    printf '<!doctype html><meta charset="utf-8"><title>MediaGrabber NAS</title><h1>MediaGrabber NAS</h1><p>%s</p><p><a href="/mediagrabber/">Přihlásit heslem aplikace / Use application password</a></p>' "$2"
    exit 0
}

[ "${REQUEST_METHOD:-}" = GET ] || fail '405 Method Not Allowed' 'Použij nabídku DSM. / Open from the DSM menu.'
case "${HTTP_SEC_FETCH_SITE:-}" in cross-site) fail '403 Forbidden' 'Otevři aplikaci přímo v DSM. / Open the application directly in DSM.' ;; esac
[ -n "${HTTP_COOKIE:-}" ] || fail '401 Unauthorized' 'Nejprve se přihlas do DSM. / Sign in to DSM first.'
# Keep the original cookie and client/server addresses. Some DSM launchers put
# SynoToken in the query rather than the HTTP header expected by the validator.
# Copy only a single plain URL-safe value; DSM still validates the real session.
if [ -z "${HTTP_X_SYNO_TOKEN:-}" ]; then
    syno=$(printf '%s' "${QUERY_STRING:-}" | tr '&' '\n' | sed -n 's/^SynoToken=//p')
    case "$syno" in ''|*[!a-zA-Z0-9_.-]*) ;; *)
        if [ "${#syno}" -le 256 ]; then HTTP_X_SYNO_TOKEN=$syno; export HTTP_X_SYNO_TOKEN; fi
    ;; esac
fi
if [ -n "${HTTP_X_SYNO_TOKEN:-}" ]; then
    case "$HTTP_X_SYNO_TOKEN" in *[!a-zA-Z0-9_.-]*) fail '400 Bad Request' 'DSM-TOKEN-INVALID' ;; esac
    [ "${#HTTP_X_SYNO_TOKEN}" -le 256 ] || fail '400 Bad Request' 'DSM-TOKEN-INVALID'
    # Modern DSM helper reads the header; legacy helper reads CGI query/URI.
    QUERY_STRING="SynoToken=$HTTP_X_SYNO_TOKEN"
    REQUEST_URI="/webman/3rdparty/MediaGrabberNAS/dsm-login.cgi?$QUERY_STRING"
    export QUERY_STRING REQUEST_URI
fi
syno_auth=/usr/syno/synoman/webman/authenticate.cgi
[ -x "$syno_auth" ] || syno_auth=/usr/syno/synoman/webman/modules/authenticate.cgi
mg_authenticate() {
    # POSIX shell watchdog: do not depend on DSM's optional/version-specific
    # timeout command. Only our own child PID can be signalled.
    "$syno_auth" &
    auth_pid=$!
    (sleep 5; kill -KILL "$auth_pid" 2>/dev/null || :) >/dev/null 2>&1 &
    guard_pid=$!
    auth_code=0
    wait "$auth_pid" || auth_code=$?
    kill "$guard_pid" 2>/dev/null || :
    wait "$guard_pid" 2>/dev/null || :
    return "$auth_code"
}
if user=$(mg_authenticate 2>/dev/null); then :; else
    auth_code=$?
    token_state=missing
    [ -z "${HTTP_X_SYNO_TOKEN:-}" ] || token_state=present
    fail '401 Unauthorized' "Přihlášení DSM se nepodařilo ověřit. / Unable to verify the DSM session. (DSM-AUTH-$auth_code; token: $token_state)"
fi
case "$user" in ''|-*|*/*|*:*) fail '401 Unauthorized' 'Neplatné přihlášení DSM. / Invalid DSM session.' ;; esac
case "$user" in *'
'*) fail '401 Unauthorized' 'Neplatné přihlášení DSM. / Invalid DSM session.' ;; esac
if printf '%s' "$user" | LC_ALL=C grep -q '[[:cntrl:]]'; then
    fail '401 Unauthorized' 'Neplatné přihlášení DSM. / Invalid DSM session.'
fi
[ "${#user}" -le 128 ] || fail '401 Unauthorized' 'Neplatné přihlášení DSM. / Invalid DSM session.'
groups=$(id -Gn "$user" 2>/dev/null) || fail '403 Forbidden' 'Účet nemá přístup. / Account not permitted.'
case " $groups " in *' administrators '*) ;; *) fail '403 Forbidden' 'MediaGrabber zatím spravuje administrátor DSM. / A DSM administrator account is required.' ;; esac
key=$(cat /var/packages/MediaGrabberNAS/var/runtime/secrets/dsm_bridge_key 2>/dev/null) || fail '503 Service Unavailable' 'Otevři aplikaci heslem nebo aktualizuj balíček. / Use the application password or update the package.'
case "$key" in *[!a-f0-9]*|'') fail '503 Service Unavailable' 'Chybí nastavení přihlášení. / Login configuration unavailable.' ;; esac
[ "${#key}" = 64 ] || fail '503 Service Unavailable' 'Chybí nastavení přihlášení. / Login configuration unavailable.'
# The long-lived key goes through curl stdin, never a URL or process argument.
ticket=$(curl --silent --show-error --fail --max-time 5 --noproxy '*' --config - 2>/dev/null <<EOF
url = "http://127.0.0.1:8787/api/dsm/issue"
request = "POST"
header = "Content-Type: application/json"
header = "X-MG-Bridge-Key: $key"
data = "{}"
EOF
) || fail '503 Service Unavailable' 'Služba ještě není připravená. / The service is not ready yet.'
case "$ticket" in *[!a-f0-9]*|'') fail '503 Service Unavailable' 'Neplatná odpověď služby. / Invalid service response.' ;; esac
[ "${#ticket}" = 64 ] || fail '503 Service Unavailable' 'Neplatná odpověď služby. / Invalid service response.'
case "${HTTP_ACCEPT:-}" in *application/json*)
    printf 'Content-Type: application/json; charset=utf-8\r\nCache-Control: no-store\r\nReferrer-Policy: no-referrer\r\n\r\n{"ticket":"%s"}' "$ticket"
    exit 0
;; esac
# Relative redirect preserves the DSM hostname, port and HTTPS. The grant is
# in a fragment (not sent to nginx or Referer), expires in 60s, works once.
printf 'Status: 303 See Other\r\nLocation: /mediagrabber/#dsm-ticket=%s\r\nCache-Control: no-store\r\nReferrer-Policy: no-referrer\r\nContent-Length: 0\r\n\r\n' "$ticket"
