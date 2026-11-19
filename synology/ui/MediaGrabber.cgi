#!/bin/sh
# DSM supplies SynoToken when its native application loader requests this script.
set -eu
PATH=/usr/bin:/bin
export PATH
token=$(printf '%s' "${QUERY_STRING:-}" | tr '&' '\n' | sed -n 's/^SynoToken=//p')
case "$token" in ''|*[!a-zA-Z0-9_.-]*) token='' ;; esac
[ "${#token}" -le 256 ] || token=''
printf 'Content-Type: application/javascript; charset=utf-8\r\nCache-Control: no-store\r\nReferrer-Policy: no-referrer\r\nX-Content-Type-Options: nosniff\r\n\r\n'
ui_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
cat "$ui_dir/native-app.js"
printf '\n})("%s");\n' "$token"
