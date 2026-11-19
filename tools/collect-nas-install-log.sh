#!/bin/sh
# Diagnostic v3: read package log context and ownership; create one new report only.
set -eu
PATH=/usr/syno/bin:/usr/bin:/bin
redact() {
    awk '{
        lower=tolower($0)
        if (lower ~ /(password|passwd|authorization|token|cookie)/) { print "[sensitive log line omitted]"; next }
        if (lower ~ /secret/ && !(lower ~ /(runtime\/secrets|\/run\/secrets)/ && lower ~ /(mount|no such file|permission denied|cannot access)/)) { print "[sensitive log line omitted]"; next }
        print
    }'
}
outdir=''
for d in /volume[0-9]*/docker/mediagrabber-nas; do
    [ -d "$d" ] || continue
    outdir=$d
    break
done
[ -n "$outdir" ] || { echo 'Existing docker/mediagrabber-nas folder not found.' >&2; exit 1; }
umask 027
report="$outdir/diagnostika-v3-$(date +%Y%m%d-%H%M%S)-$$.txt"
(
    set -C
    {
        echo 'MediaGrabber NAS installation log excerpts - diagnostic v3'
        date
        printf '\n--- Internal package identity ---\n'
        id mg-nas 2>&1 || :
        printf '\n--- Package directory ownership ---\n'
        for pkgpath in /var/packages/MediaGrabberNAS /var/packages/MediaGrabberNAS/target /var/packages/MediaGrabberNAS/var /var/packages/MediaGrabberNAS/var/runtime/data /var/packages/MediaGrabberNAS/var/runtime/secrets /var/packages/MediaGrabberNAS/shares/MediaGrabber; do
            ls -ld "$pkgpath" 2>&1 || :
        done
        for logfile in /var/log/synoscgi.log /var/log/synoscgi.log.1 /var/log/synopkg.log /var/log/packages/MediaGrabberNAS.log /var/log/synopkgmgr.log /var/log/messages /var/log/packages/ContainerManager.log /var/packages/ContainerManager/var/log/docker.log; do
            printf '\n--- %s ---\n' "$logfile"
            if [ ! -r "$logfile" ]; then echo 'Log unavailable.'; continue; fi
            tail -n 10000 "$logfile" | grep -iE -B 6 -A 8 'MediaGrabber|mg-nas|mediagrabber-nas-spk|d214377d-f376-44d0-9efc-f0665f99b4f3|fail compose up' | tail -n 500 |
                redact
        done
        printf '\n--- MediaGrabber container state and recent log ---\n'
        dockercli=''
        for executable in /var/packages/ContainerManager/target/usr/bin/docker /usr/local/bin/docker /usr/bin/docker; do
            [ -x "$executable" ] || continue
            dockercli=$executable
            break
        done
        if [ -n "$dockercli" ]; then
            {
                "$dockercli" ps -a --filter name=mediagrabber-nas-spk --format '{{.Names}} {{.Image}} {{.Status}}' 2>&1 || :
                "$dockercli" inspect --format 'Status={{.State.Status}} ExitCode={{.State.ExitCode}} Error={{.State.Error}}' mediagrabber-nas-spk 2>&1 || :
                "$dockercli" logs --tail 100 mediagrabber-nas-spk 2>&1 || :
            } | redact
        else
            echo 'Docker CLI unavailable.'
        fi
    } > "$report"
)
chgrp administrators "$report"
chmod 640 "$report"
printf 'Report saved: %s\n' "$report"
