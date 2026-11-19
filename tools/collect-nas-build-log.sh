#!/bin/sh
# Read the failed native project's action log; do not build/start/change Docker.
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
readable() {
    awk '{ gsub(/\\n/, "\n"); gsub(/[}],[ ]*[{]/, "}\n{"); print }'
}
outdir=''
for d in /volume[0-9]*/docker/mediagrabber-nas; do
    [ -d "$d" ] || continue
    outdir=$d
    break
done
[ -n "$outdir" ] || { echo 'Existing docker/mediagrabber-nas folder not found.' >&2; exit 1; }
umask 027
report="$outdir/diagnostika-v4-$(date +%Y%m%d-%H%M%S)-$$.txt"
(
    set -C
    {
        echo 'MediaGrabber NAS native project build log - diagnostic v4'
        date
        printf '\n--- Native project action log ---\n'
        if [ -x /usr/syno/bin/synowebapi ]; then
            /usr/syno/bin/synowebapi --exec api=SYNO.Docker.Project method=log version=1 id='"d214377d-f376-44d0-9efc-f0665f99b4f3"' 2>&1 | readable | redact
        else
            echo 'Native API helper unavailable.'
        fi
        printf '\n--- Docker daemon build errors ---\n'
        for logfile in /var/log/systemd/pkg-ContainerManager-dockerd.service.log /var/log/docker.log; do
            printf '\n--- %s ---\n' "$logfile"
            [ -r "$logfile" ] || { echo 'Log unavailable.'; continue; }
            tail -n 5000 "$logfile" | grep -iE -B 3 -A 5 'error|fail|denied|timeout|d214377d|mediagrabber' | tail -n 250 | readable | redact
        done
        printf '\n--- MediaGrabber image availability ---\n'
        for dockercli in /var/packages/ContainerManager/target/usr/bin/docker /usr/local/bin/docker /usr/bin/docker; do
            [ -x "$dockercli" ] || continue
            "$dockercli" image inspect --format 'ID={{.Id}} Created={{.Created}}' pjsoft/mediagrabber-nas:spk-0.1.0-0004 2>&1 | redact
            break
        done
    } > "$report"
)
chgrp administrators "$report"
chmod 640 "$report"
printf 'Report saved: %s\n' "$report"
