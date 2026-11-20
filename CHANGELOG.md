## Build0024 / 0.1.0-beta.24 — 2026-11-19

- Correct the beta.23 preload bundle path: include image.tar.gz inside package.tgz so DSM installs it under the application target directory. The beta.23 image was valid but incorrectly placed in the outer SPK archive.
- Add a regression that resolves the configured preload path against the installed payload and verifies a regular file with the exact saved image bytes.
- Split CI output into installer/application-source and runtime-source downloads. Pin Node24-based checkout and upload actions; enable POSIX lifecycle tests on the Linux runner. Keep the existing manual trigger and read-only repository access.
- Beta.24 requires a new Linux CI build and a physical DSM upgrade test. Delivered beta.23 remains unchanged and must not be reused as a working installer.

## Build0022 / 0.1.0-beta.22 — 2026-11-19

- Fix the confirmed DSM port registration collision: Container Manager owns the published TCP8787 port; do not additionally register it through native port-config. The beta.21 pilot image built successfully but DSM rejected its container profile with error1202.
- Make postuninst self-contained. DSM removes the application payload before calling this hook, so it cannot source installer/package-lib.sh from that payload. Preserve explicit opt-in and canonical private-path checks; upgrades retain private data and media is retained in every case.
- Add regressions for exclusive port ownership and the actual remove-payload-before-postuninst lifecycle order.
- Keep this correction as an online development SPK. Move the unrun offline workflow candidate to0023; do not overwrite0021 or claim an offline image has been tested.

## Build0021 / 0.1.0-beta.21 — 2026-11-19

- Original NAS source licensed GPL-3.0-or-later with the owner's explicit authorization. Preserve original upstream licenses, add all pinned Python notices, actual Node image notice copy and the corresponding Mutagen source.
- Package own source/build/install archive; provide license, source and bilingual data information from the UI, with privacy information accessible before sign-in.
- Register TCP8787 through DSM port-config without automatic port forwarding.
- Add explicit opt-in removal of private state/credentials/backups during genuine UNINSTALL only. Retain media; upgrades ignore the flag; reject redirected/overlapping/unrecognized targets.
- Pin and hash the Linux Python runtime dependency set. Record actual image/runtime package inventory at build time.
- Prepare separate offline candidate0022 through a manual Linux Docker workflow: saved image, matching corresponding-source archive, version/architecture validation and no-pull/no-build native configuration. The offline workflow has not yet run in the Windows development environment.

## Build 0020 / 0.1.0-beta.20 — 2026-11-19

About now checks the latest stable Windows release from the Windows GitHub repository through a separate authenticated NAS endpoint. A six-hour persistent cache, five-minute failure backoff, bounded response and three-second network timeout keep failed checks independent of the About component list and download worker. The last verified version is labelled on failure; without a cache the dialog links to GitHub and does not show a fixed version. All nine locales remove the stale 4.2.0 claim and translate loading/current/cached/unavailable states. The generic Windows feature overview remains separately maintained. The native package maintainer URL now points to the separate MediaGrabber-NAS repository. Package identity, privileges, DSM login and download behavior are unchanged.

## Build 0019 / 0.1.0-beta.19 — 2026-11-18

- Compact history cards put action buttons beside the summary on desktop and wrap cleanly on narrow screens.
- Add Clear all history with explicit confirmation, plus Refresh history and Load more records. Deletion removes only terminal job/item records; media files, active/paused/interrupted queue jobs, watched sources/seen state and duplicate ledger remain intact.
- History uses indexed cursor pages of 50 summaries, including aggregate result counts. It can continue beyond the former 300-record display limit; detail items/file paths load only when Result is opened. Ordering is stable for equal timestamps and after a boundary row is deleted.
- Routine 4s UI polling now requests state without history and never rebuilds the history list. More records append to existing DOM nodes. Open/Refresh fetches current history; polling does not move the reader or reset loaded pages.
- All new labels/confirmation/help are present in nine languages. DSM launch/authentication, package privilege and native resources remain those of 0018.

## Build 0018 / 0.1.0-beta.18 — 2026-11-18

Replace the plain `.url` launcher with a native DSM Vue application and script CGI. Build 0017 reached authenticate.cgi but reported `DSM-AUTH-7; token: missing`; an existing application cookie made the password fallback open directly, which did not prove fresh DSM login. The new native loader receives the DSM-provided SynoToken, confines it to a JavaScript closure, and forwards it as a same-origin request header to the login CGI. The CGI still validates the actual DSM session and administrator membership; it returns a short one-use grant as JSON for the application iframe. Existing app sessions are not a prerequisite.

The loader uses the Vue application/window structure in Synology ExamplePackages; CGI token injection follows the native loading pattern visible in Duplicati, with strict single-value validation. Preserve a live DSM Session token when available; reject absent or malformed tokens. Normalize the genuine token into both modern header and legacy CGI query/URI environments. Prefer executable modern webman/authenticate.cgi, otherwise use the legacy modules path. No root, system group membership, copied/modified DSM binaries or authentication bypass.

The portal allows framing only by its own origin; direct port access keeps frame-ancestors none. Package Center Open now uses the native dsmappname; package ID, data/secret locations, private key and minimum privilege are unchanged. Application password and direct-port fallback remain available.

## Build 0017 / 0.1.0-beta.17 — 2026-11-16

Physical 0016 reached the DSM login CGI with a cookie, but the combined `timeout 5 authenticate.cgi` invocation returned nonzero. The screenshot does not distinguish missing/incompatible timeout from a native validator failure. Replace external timeout with a five-second POSIX-shell watchdog, retain the genuine CGI request environment and expand the standard DSM executable search path. Map one plain URL-safe SynoToken query value into HTTP_X_SYNO_TOKEN only if that header is absent; DSM still validates the session. Never accept a username or portal flag as authentication.

Failure now displays DSM-AUTH plus the numeric exit status and token presence (no actual cookie/token/password or raw stderr). Thus an independent native validator failure can be distinguished on the next pilot attempt. Password fallback, administrator check, minimal non-root privileges, private grant exchange and proxy configuration are unchanged. This is a compatibility correction with diagnostic improvement; success on the physical DSM validator is not yet established.

## Build 0016 / 0.1.0-beta.16 — 2026-11-16

The physical pilot rejected 0015 immediately at SPK upload with the DSM root-privilege warning. Remove the redundant per-executable privilege entry added for the CGI; restore the exact minimal mg-nas package-account declaration used by previous 0014. The CGI remains normal mode 0755, owned through the package default. No root hooks, setuid/setgid modes or security-setting changes. DSM launch/authentication code is unchanged; only package/app version metadata advances.

Nine archive/config tests pass, including exact minimal privilege, no setid bits, builder rejection of privilege overrides, native resources, manifest/reproducibility and the real Compose 2.20.1 parser. Native installation and CGI/DSM authentication remain pending: the screenshot identifies permission rejection, not the internal validator branch.

## Build 0015 / 0.1.0-beta.15 — 2026-11-16

- DSM menu/Open now uses a package-account CGI launch bridge. Synology authenticate.cgi verifies the existing DSM session, then host group membership restricts automatic access to DSM administrators.
- Private random host/container key issues a 60-second single-use grant. Only its digest is stored; consumption is atomic and grants are cleared on restart. DSM cookies/passwords never enter the container through the portal.
- Native web-config registers /mediagrabber/ at the existing DSM origin, preserving HTTPS and port. It strips DSM cookies, Authorization and bridge-key headers before proxying. No global nginx templates or root package hooks.
- Portal sessions use a separate HttpOnly path-scoped cookie, Secure on HTTPS, with existing CSRF/origin checks. Original application password remains valid for direct port 8787 and portal fallback. Sessions remain independent of DSM logout and expire after 12h or application logout.
- Relative assets, API/file links and JSON backup work through the portal and direct address. Upgrade retains schema-1 data, media, password and private bridge key; initial old-version upgrade generates the new key automatically.
- Local WSGI, shell-boundary, browser and real nginx tests are detailed in VALIDATION.md. Physical DSM 7.3.1 integration remains pending.

## Build 0014 / 0.1.0-beta.14 — 2026-11-15

Grouped language and action buttons in the top header row. Moved the tooltip
checkbox below that row, aligned right. Narrow screens allow the action row to
wrap. Packaged HTML hierarchy, manifest and exact six-file payload diff verified.
No runtime logic changed. Native visual verification remains pending.

## Build 0013 / 0.1.0-beta.13 — 2026-11-15

Correct SPK build context: Dockerfile in 0012 copies THIRD-PARTY-NOTICES.md,
but the builder included it only in the package root, outside docker/. The
actual delivered archive confirms the missing COPY source. Add the same notice
to docker/. Seven archive/parser tests pass, including a regression over every
local COPY input in the actual built payload. Final manifest and exact five-file
payload diff verified. No Docker engine build or native 0013 update is claimed.
UI/features remain those of 0012. Update the existing package; do not uninstall.

## Build 0012 / 0.1.0-beta.12 — 2026-11-15

Added a default-on tooltip checkbox persisted per browser; disabling hides all
custom bubbles while keeping accessibility descriptions. Labels inherit their
control help, including checkbox text. About includes a Windows 4.2.0 feature
snapshot and GitHub releases link, authenticated cached runtime component versions
and third-party notices. Docker now copies the notices into the application image.
Support opens a voluntary bank-transfer information dialog using the same account
as Windows; no payment is sent, no feature is gated and no automatic nag is added.
All new texts are localized in nine languages. Donation UI is not represented as
Synology-approved: public developer agreement covers free and paid products but
explicit donation approval was not found. Confirm at official package review.
Daily automatic yt-dlp updates remain future work.

Validation: 53 Python tests: 44 pass, 9 optional/environment skips. 216 JS locale
checks plus tooltip preference/persistence and shared-label checks pass. Final
FFprobe addition separately passed the authenticated About/caching test. Native
install and visual inspection remain pending; no browser screenshot is claimed.

## Build 0011 / 0.1.0-beta.11 — 2026-11-15

Added full UI catalogs, hover/focus tooltips and guide content for all nine Windows
language codes: cs, en, es, de, fr, pt-PT, pt-BR, pl, it (177 keys each). The language
is detected regionally and manually selected language persists per browser.
Added visible first-download guidance, per-source monitoring mode and new-only
explanation, mode-specific form text and an explanation of locked source fields.
Corrected the earlier instruction that every user must manually download first:
start_mode=all already queues existing items and later discovers only unseen ones.
Existing source configurations/history and download processing are unchanged.
Detailed service/downloader diagnostics can still be in their original language.

Validation: full Python suite 52 tests, 43 passed, 9 optional/environment skips;
JavaScript syntax checks and 216 mode/control hint checks across nine locales,
plus regional language detection. New all-mode regression verifies initial queue,
no duplicate queue on repeat check and discovery of a subsequently added item.
Final archive/parser checks are recorded in release-state.json. Browser visual QA
was attempted but blocked by unavailable localhost and Windows URL identification;
no layout screenshot or native 0011 installation is claimed verified.

# Build 0010 / 0.1.0-beta.10 — 2026-11-15

DSM launcher now directly targets protocol http, port 8787 and URL / instead of
a 3rdparty/index.html redirect. INFO adminprotocol/adminport remain consistent.
Native app config follows the upstream spksrc service-shortcut generator:
https://github.com/SynoCommunity/spksrc/blob/master/mk/spksrc.service.mk

Six archive/parser tests passed, including the packaged native app configuration
and upstream Compose 2.20.1 parsing. Delivered checksums, manifest and exact
five-file payload diff verified. Actual DSM menu launch/cache update pending.
Source checking and download code unchanged. User confirmed beta.9 lists 50
entries; initial new-only baseline deliberately does not enqueue existing media.

# Build 0009 / 0.1.0-beta.9 — 2026-11-15

Channel root URLs no longer acquire an invented /videos suffix. Explicit videos,
shorts and streams tabs remain explicit. For sources already saved by earlier
builds, the specific missing-videos-tab error retries the channel root without
changing its monitoring ID, baseline or history. Nested channel-tab playlists
are flattened with global positions and duplicate video IDs removed. Failed or
incomplete listings still cannot become a successful monitoring baseline.

Validation: 48 tests ran, 39 passed and 9 optional/environment tests skipped.
Includes real Compose 2.20.1 parsing of the generated package. Actual YouTube
listing and native 0009 installation still require verification on the NAS.

Upstream extraction behavior: https://github.com/yt-dlp/yt-dlp/blob/master/yt_dlp/extractor/youtube/_tab.py

# Changelog

## 0.1.0-beta.8 / SPK 0.1.0-0008 — 2026-11-15

Quoted the application-factory argument inside the scalar SPK command. Compose 2.20.1 rejects unquoted parentheses with invalid command line string, reproduced locally using the official standalone binary; Python shlex alone had missed this distinction. The corrected packaged source and a serialized configuration both pass the real parser and yield exactly the original image argv. A regression also reproduces the prior numeric-list failure. Five focused archive/parser tests passed; native startup remains pending.

## 0.1.0-beta.7 / SPK 0.1.0-0007 — 2026-11-15

Changed the SPK command to a single scalar instead of an argument list. The physical 0006 probe built the image and created a stopped container successfully, but native Container Manager rejected services.mediagrabber.command.5 in its generated docker-compose.admin.yaml. A scalar avoids per-item numeric typing while preserving the complete image command. Four archive tests passed, including scalar serialization and argument-equivalence checks. Native 0007 startup is pending.

## 0.1.0-beta.6 / SPK 0.1.0-0006 — 2026-11-15

Explicitly passes the Gunicorn application command to the SPK bootstrap. Overriding the Compose entrypoint had cleared the image CMD, causing 0005 to exit with Missing application command before startup. Added packaged-command/image-CMD consistency and full-argv forwarding checks. NoNewPrivs verification now uses the existing prctl getter when older kernels omit the proc field; failure remains a hard rejection. CPU-quota compatibility correction is retained. 11 focused local tests passed; native 0006 startup remains pending.

## 0.1.0-beta.5 / SPK 0.1.0-0005 — 2026-11-14

Removed the one-CPU quota from both NAS Compose profiles. A physical DS1817+ creation test reproduced Docker’s rejection of NanoCPUs because the kernel lacks CPU CFS support. The image itself builds successfully; this correction targets container creation. Memory/PID limits, read-only filesystem and privilege settings are retained. Added a regression covering templates and packaged YAML. Actual 0005 installation/startup remains to be verified.

## 0.1.0-beta.4 / SPK 0.1.0-0004 — 2026-11-14

Corrected wizard getValues from an array of records to a flat object of strings, matching Synology’s executable ExamplePackage. Both earlier pilot attempts aborted with a native JSON string-conversion exception before package scripts ran. Upgrade/uninstall export an empty object. Added regression rejection of the old array/nested values and a browser-to-POSIX-preinst bridge with Unicode and literal shell metacharacters. Local validation does not establish successful DSM installation; the 0004 retry is pending. No runtime/lifecycle behavior changed.

## 0.1.0-beta.3 / SPK 0.1.0-0003 — 2026-11-14

Corrected SPK project preparation after the first physical pilot showed an immediate generic DSM installation error. Build 0002 omitted Compose from the package and generated it in postinst; the native Docker Project worker can need it in WHEN_POSTINST, before that hook. Build 0003 ships the complete immutable Compose configuration and uses deferred local bind volumes for state/secrets/media.

A short SPK-only container bootstrap obtains IDs from the NAS-owned data mount, clears supplementary groups, permanently sets all real/effective/saved IDs, verifies no effective capabilities and no-new-privileges, then execs tini/Gunicorn as the non-root account. Only SETUID/SETGID are provided to the brief bootstrap; package control scripts remain unprivileged. Runtime host/cookie settings are data in a read-only settings mount. Wizard values now export one field per record. Added a native-order regression and privilege-drop tests. These changes fix verified packaging weaknesses; the exact cause of the NAS's generic error remains unconfirmed until a retry/log.

## 0.1.0-beta.2 / SPK 0.1.0-0002 — 2026-11-14

First native SPK installer for manual installation through DSM Package Center. Uses the native Container Manager project worker, an automatically provisioned internal package account and a persistent MediaGrabber shared folder. Czech/English installation wizard asks for the application password; no manual UID/GID discovery or .env preparation.

Stable package identity and increasing build numbers support repeated test upgrades. Permanent state is outside the replaceable application target; upgrades retain credentials/settings/history and create a stopped-state backup before new configuration is generated. Uninstall hooks do not delete state or media. Added lifecycle/archive tests and six Vue wizard variants tested with a simulated DSM host. Docker/physical DSM installation remains to be validated on the first pilot.

## 0.1.0-beta.1 — 2026-11-14

Initial independent NAS implementation: browser UI (Czech/English), persistent download queue/history, public YouTube source monitoring, exact preview selections, bulk links/TXT, per-job/source audio/video profiles, available metadata/artwork, duplicate ledger, pause/recovery/retry, schedules/rate/free-space guards and held JSON import/export.

Includes Container Manager/Docker build recipe and installation instructions. No published image, native SPK or claim of Synology certification. Windows 3.14.0 is unchanged. Physical NAS/container validation remains outstanding.
