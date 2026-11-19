#!/bin/sh
# 0006 diagnosis: read logs, build diagnostic image, create STOPPED probe, clean probe only.
set -eu
PATH=/usr/syno/bin:/usr/bin:/bin
outdir=''
for d in /volume[0-9]*/docker/mediagrabber-nas; do
 [ -d "$d" ] || continue
 outdir=$d; break
done
[ -n "$outdir" ] || exit 1
umask 027
base="$outdir/diagnostika-0006-$(date +%Y%m%d-%H%M%S)-$$"
project="mediagrabber-probe-0006-$$"
context=/var/packages/MediaGrabberNAS/target/docker
compose() {
 if [ "$mode" = plugin ]; then "$dockercli" compose "$@"; else "$mode" "$@"; fi
}
collect() {
 date
 echo 'MediaGrabber 0006: logs, image build and stopped project probe'
 for logfile in /var/log/synoscgi.log /var/log/packages/MediaGrabberNAS.log; do
  printf '\n--- %s ---\n' "$logfile"
  [ -r "$logfile" ] || continue
  tail -n 5000 "$logfile" | grep -iE -B 2 -A 4 'MediaGrabber|9618d9d7-1d8c-4377-8c91-1a78a91f3994' | tail -n 150
 done
 [ -r "$context/compose.yaml" ] && [ -r "$context/Dockerfile" ] || { echo 'Missing installed context'; return 1; }
 [ "$(cat /var/packages/MediaGrabberNAS/target/SPK_VERSION)" = 0.1.0-0006 ] || { echo 'Expected installed 0006'; return 1; }
 dockercli=''
 for executable in /var/packages/ContainerManager/target/usr/bin/docker /usr/local/bin/docker /usr/bin/docker; do
  [ -x "$executable" ] || continue
  dockercli=$executable; break
 done
 [ -n "$dockercli" ] || { echo 'Docker CLI unavailable'; return 1; }
 printf '\n--- Current application container ---\n'
 "$dockercli" ps -a --filter name=mediagrabber-nas-spk --format '{{.Names}} {{.Image}} {{.Status}}'
 "$dockercli" inspect --format 'Status={{.State.Status}} ExitCode={{.State.ExitCode}} Error={{.State.Error}}' mediagrabber-nas-spk || :
 "$dockercli" logs --tail 50 mediagrabber-nas-spk || :
 printf '\n--- Diagnostic image build ---\n'
 build_status=0
 DOCKER_BUILDKIT=0 "$dockercli" build --tag pjsoft/mediagrabber-nas:diagnostic-0006 "$context" || build_status=$?
 echo "BUILD_EXIT_CODE=$build_status"
 [ "$build_status" -eq 0 ] || return 0
 mode=''
 if "$dockercli" compose version >/dev/null 2>&1; then mode=plugin; else
  for executable in /var/packages/ContainerManager/target/usr/bin/docker-compose /usr/local/bin/docker-compose /usr/bin/docker-compose; do
   [ -x "$executable" ] || continue
   mode=$executable; break
  done
 fi
 [ -n "$mode" ] || { echo 'Compose CLI unavailable'; return 1; }
 compose version
 override="$base.yaml"
 (set -C; printf 'services:\n  mediagrabber:\n    image: pjsoft/mediagrabber-nas:diagnostic-0006\n    container_name: %s\n' "$project" > "$override")
 config_status=0
 compose -p "$project" -f "$context/compose.yaml" -f "$override" config --quiet || config_status=$?
 echo "CONFIG_EXIT_CODE=$config_status"
 if [ "$config_status" -eq 0 ]; then
  create_status=0
  compose -p "$project" -f "$context/compose.yaml" -f "$override" up --no-start --no-build || create_status=$?
  echo "CREATE_EXIT_CODE=$create_status"
  cleanup_status=0
  compose -p "$project" -f "$context/compose.yaml" -f "$override" down || cleanup_status=$?
  echo "CLEANUP_EXIT_CODE=$cleanup_status"
 fi
 date
}
(set -C; { result=0; collect || result=$?; echo "DIAGNOSTIC_EXIT_CODE=$result"; } 2>&1 | awk 'tolower($0) ~ /(password|passwd|authorization|token|cookie)/ { print "[sensitive log line omitted]"; next } { print; fflush() }' > "$base.running")
chgrp administrators "$base.running"
chmod 640 "$base.running"
mv -n "$base.running" "$base.txt"
printf 'Completed report: %s.txt\n' "$base"
