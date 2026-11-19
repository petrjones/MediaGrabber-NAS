#!/bin/sh
# Create a uniquely named STOPPED diagnostic project, capture errors, then remove it.
set -eu
PATH=/usr/syno/bin:/usr/bin:/bin
outdir=''
for d in /volume[0-9]*/docker/mediagrabber-nas; do
    [ -d "$d" ] || continue
    outdir=$d
    break
done
[ -n "$outdir" ] || exit 1
context=/var/packages/MediaGrabberNAS/target/docker
[ -r "$context/compose.yaml" ] || { echo 'Installed Compose file unavailable.' >&2; exit 1; }
dockercli=''
for executable in /var/packages/ContainerManager/target/usr/bin/docker /usr/local/bin/docker /usr/bin/docker; do
    [ -x "$executable" ] || continue
    dockercli=$executable
    break
done
[ -n "$dockercli" ] || exit 1
composecli=''
if "$dockercli" compose version >/dev/null 2>&1; then
    composecli=plugin
else
    for executable in /var/packages/ContainerManager/target/usr/bin/docker-compose /usr/local/bin/docker-compose /usr/bin/docker-compose; do
        [ -x "$executable" ] || continue
        composecli=$executable
        break
    done
fi
[ -n "$composecli" ] || { echo 'Compose CLI unavailable.' >&2; exit 1; }
compose() {
    if [ "$composecli" = plugin ]; then "$dockercli" compose "$@"; else "$composecli" "$@"; fi
}
umask 027
project="mediagrabber-probe-0004-$$"
base="$outdir/projekt-0004-$(date +%Y%m%d-%H%M%S)-$$"
override="$base.yaml"
(set -C; printf 'services:\n  mediagrabber:\n    image: pjsoft/mediagrabber-nas:diagnostic-0004\n    container_name: %s\n' "$project" > "$override")
(
    set -C
    {
        echo 'MediaGrabber 0004 stopped project creation probe'
        date
        echo "Temporary project: $project"
        compose version
        config_status=0
        compose -p "$project" -f "$context/compose.yaml" -f "$override" config --quiet || config_status=$?
        printf 'CONFIG_EXIT_CODE=%s\n' "$config_status"
        if [ "$config_status" -eq 0 ]; then
            create_status=0
            compose -p "$project" -f "$context/compose.yaml" -f "$override" up --no-start --no-build || create_status=$?
            printf 'CREATE_EXIT_CODE=%s\n' "$create_status"
            "$dockercli" inspect --format 'Status={{.State.Status}} Error={{.State.Error}}' "$project" || :
            cleanup_status=0
            compose -p "$project" -f "$context/compose.yaml" -f "$override" down || cleanup_status=$?
            printf 'CLEANUP_EXIT_CODE=%s\n' "$cleanup_status"
        fi
        date
    } 2>&1 | awk '{ print; fflush() }' > "$base.running"
)
chgrp administrators "$base.running" "$override"
chmod 640 "$base.running" "$override"
mv -n "$base.running" "$base.txt"
printf 'Completed stopped-project report: %s.txt\n' "$base"
