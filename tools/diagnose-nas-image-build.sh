#!/bin/sh
# Rebuild ONLY the bundled 0004 image and capture output; no container is started.
set -eu
PATH=/usr/syno/bin:/usr/bin:/bin
outdir=''
for d in /volume[0-9]*/docker/mediagrabber-nas; do
    [ -d "$d" ] || continue
    outdir=$d
    break
done
[ -n "$outdir" ] || { echo 'Existing docker/mediagrabber-nas folder not found.' >&2; exit 1; }
context=/var/packages/MediaGrabberNAS/target/docker
[ -r "$context/Dockerfile" ] && [ -r "$context/requirements.txt" ] || { echo 'Installed build context unavailable.' >&2; exit 1; }
versionfile=/var/packages/MediaGrabberNAS/target/SPK_VERSION
[ -r "$versionfile" ] && [ "$(cat "$versionfile")" = 0.1.0-0004 ] || { echo 'This diagnostic is only for installed build 0004.' >&2; exit 1; }
dockercli=''
for executable in /var/packages/ContainerManager/target/usr/bin/docker /usr/local/bin/docker /usr/bin/docker; do
    [ -x "$executable" ] || continue
    dockercli=$executable
    break
done
[ -n "$dockercli" ] || { echo 'Docker CLI unavailable.' >&2; exit 1; }
umask 027
base="$outdir/sestaveni-0004-$(date +%Y%m%d-%H%M%S)-$$"
(
    set -C
    {
        echo 'MediaGrabber NAS 0004 isolated diagnostic image build'
        date
        echo 'Tag: pjsoft/mediagrabber-nas:diagnostic-0004'
        echo 'No application container is started by this task.'
        build_status=0
        DOCKER_BUILDKIT=0 "$dockercli" build --tag pjsoft/mediagrabber-nas:diagnostic-0004 "$context" || build_status=$?
        printf '\nBUILD_EXIT_CODE=%s\n' "$build_status"
        date
    } 2>&1 | awk 'tolower($0) ~ /(password|passwd|authorization|token|cookie|secret)/ { print "[sensitive log line omitted]"; next } { print; fflush() }' > "$base.running"
)
chgrp administrators "$base.running"
chmod 640 "$base.running"
mv -n "$base.running" "$base.txt"
printf 'Completed build report: %s.txt\n' "$base"
