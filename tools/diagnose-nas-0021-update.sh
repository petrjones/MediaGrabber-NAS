#!/bin/sh
# SPDX-License-Identifier: GPL-3.0-or-later
# Read-only diagnosis. Only a new report file is created; no lifecycle/build commands.
set -eu
PATH=/usr/syno/bin:/usr/bin:/bin
umask 077

redact() {
    awk '{
        lower=tolower($0)
        if (lower ~ /(password|passwd|authorization|token|cookie|wizard_admin|dsm_bridge_key)/) {
            print "[sensitive log line omitted]"; next
        }
        if (lower ~ /secret/ && !(lower ~ /(runtime\/secrets|\/run\/secrets)/ && lower ~ /(mount|no such file|permission denied|cannot access)/)) {
            print "[sensitive log line omitted]"; next
        }
        gsub(/https?:[^[:space:]"<>]+/, "[URL omitted]")
        print
    }'
}
readable() { awk '{gsub(/\\n/, "\n"); print}'; }
outdir=''
for d in /volume[0-9]*/docker/mediagrabber-nas /volume[0-9]*/MediaGrabber; do
    [ -d "$d" ] && [ -w "$d" ] || continue
    outdir=$d
    break
done
[ -n "$outdir" ] || { echo 'Report folder not found. No changes made.' >&2; exit 1; }
report="$outdir/diagnostika-0021-$(date +%Y%m%d-%H%M%S)-$$.txt"

collect() {
    echo 'MediaGrabber NAS: failed 0021 update/repair, read-only report'
    date
    printf '\n--- Installed version ---\n'
    for f in /var/packages/MediaGrabberNAS/INFO /var/packages/MediaGrabberNAS/target/SPK_VERSION /etc.defaults/VERSION; do
        echo "$f"
        [ -r "$f" ] || { echo 'Unavailable'; continue; }
        case "$f" in
            */SPK_VERSION) head -n 1 "$f" ;;
            *) sed -n '/^version=/p; /^package=/p; /^buildnumber=/p; /^productversion=/p; /^smallfixnumber=/p' "$f" ;;
        esac
    done
    printf '\n--- Package identity and file permissions (no private contents) ---\n'
    id mg-nas 2>&1 || :
    for p in /var/packages/MediaGrabberNAS/target /var/packages/MediaGrabberNAS/var /var/packages/MediaGrabberNAS/var/runtime /var/packages/MediaGrabberNAS/var/runtime/schema /var/packages/MediaGrabberNAS/var/runtime/data /var/packages/MediaGrabberNAS/var/runtime/secrets /var/packages/MediaGrabberNAS/shares/MediaGrabber; do
        ls -ld "$p" 2>&1 || :
    done
    printf '\n--- Native package configuration ---\n'
    for f in /var/packages/MediaGrabberNAS/conf/privilege /var/packages/MediaGrabberNAS/conf/resource /var/packages/MediaGrabberNAS/target/port_conf/MediaGrabberNAS.sc /usr/local/etc/service.d/MediaGrabberNAS.sc; do
        echo "$f"
        if [ -r "$f" ]; then head -c 16384 "$f"; printf '\n'; else echo 'Unavailable'; fi
    done
    for logfile in /var/log/synoscgi.log /var/log/synopkg.log /var/log/synopkgmgr.log /var/log/packages/MediaGrabberNAS.log /var/log/packages/ContainerManager.log /var/log/messages; do
        printf '\n--- Relevant recent events: %s ---\n' "$logfile"
        [ -r "$logfile" ] || { echo 'Unavailable'; continue; }
        tail -n 15000 "$logfile" | grep -iE -B 4 -A 8 'MediaGrabber|mg-nas|mediagrabber-nas-spk|9618d9d7-1d8c-4377-8c91-1a78a91f3994' | tail -n 350 || :
    done
    printf '\n--- Existing native project log (last known project ID) ---\n'
    if [ -x /usr/syno/bin/synowebapi ]; then
        # Same existing project ID as the earlier installation diagnostics. Read only.
        /usr/syno/bin/synowebapi --exec api=SYNO.Docker.Project method=log version=1 id='"9618d9d7-1d8c-4377-8c91-1a78a91f3994"' 2>&1 | readable | tail -n 800 || :
    else
        echo 'Native API helper unavailable'
    fi
    printf '\n--- Application container/image state (no environment or user download log) ---\n'
    dockercli=''
    for executable in /var/packages/ContainerManager/target/usr/bin/docker /usr/local/bin/docker /usr/bin/docker; do
        [ -x "$executable" ] || continue
        dockercli=$executable
        break
    done
    if [ -n "$dockercli" ]; then
        "$dockercli" ps -a --filter name=mediagrabber-nas-spk --format '{{.Names}} {{.Image}} {{.Status}}' 2>&1 || :
        "$dockercli" inspect --format 'Status={{.State.Status}} ExitCode={{.State.ExitCode}} Error={{.State.Error}}' mediagrabber-nas-spk 2>&1 || :
        for build in 0020 0021; do
            "$dockercli" image inspect --format 'ID={{.Id}} Created={{.Created}}' "pjsoft/mediagrabber-nas:spk-0.1.0-$build" 2>&1 || :
        done
    else
        echo 'Docker CLI unavailable'
    fi
    printf '\n--- End of read-only report ---\n'
}

# Noclobber prevents replacing any existing report. Redact before writing to disk.
(set -C; collect 2>&1 | redact > "$report")
chgrp administrators "$report"
chmod 640 "$report"
printf 'Report saved: %s\n' "$report"
