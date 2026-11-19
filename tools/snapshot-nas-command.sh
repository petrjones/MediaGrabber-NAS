#!/bin/sh
# Read-only snapshot of package version, command configuration and native errors.
set -eu
PATH=/usr/syno/bin:/usr/bin:/bin
outdir=''
for d in /volume[0-9]*/docker/mediagrabber-nas; do
 [ -d "$d" ] || continue
 outdir=$d; break
done
[ -n "$outdir" ] || exit 1
umask 027
report="$outdir/konfigurace-mediagrabber-$(date +%Y%m%d-%H%M%S)-$$.txt"
(set -C
 {
  date
  echo 'Installed payload version:'
  cat /var/packages/MediaGrabberNAS/target/SPK_VERSION 2>&1 || :
  for config in /var/packages/MediaGrabberNAS/target/docker/compose.yaml /var/packages/MediaGrabberNAS/target/docker/docker-compose.admin.yaml; do
   printf '\n--- Command fields: %s ---\n' "$config"
   ls -l "$config" 2>&1 || :
   [ -r "$config" ] || continue
   awk '
    /^[ \t]*(command|entrypoint|image):/ { match($0,/[^ \t]/); indent=RSTART; active=1; print; next }
    active {
     if ($0 ~ /^[ \t]*$/) { print; next }
     match($0,/[^ \t]/)
     if (RSTART>indent || (RSTART==indent && $0 ~ /^[ \t]*-/)) print
     else active=0
    }
   ' "$config"
  done
  for logfile in /var/log/synoscgi.log /var/log/packages/MediaGrabberNAS.log; do
   printf '\n--- Recent install errors: %s ---\n' "$logfile"
   [ -r "$logfile" ] || continue
   tail -n 10000 "$logfile" | grep -iE -B 2 -A 3 'MediaGrabber|9618d9d7-1d8c-4377-8c91-1a78a91f3994' | tail -n 120
  done
 } 2>&1 | awk 'tolower($0) ~ /(password|passwd|authorization|token|cookie)/ { print "[sensitive log line omitted]"; next } { print }' > "$report"
)
chgrp administrators "$report"
chmod 640 "$report"
printf 'Report saved: %s\n' "$report"
