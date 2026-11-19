# Build0022: repair confirmed beta.21 lifecycle failures

The pilot diagnostic dated2026-11-19 proves that0021 built and tagged its image successfully. Native registration of port8787 collided with Container Manager's own docker_mediagrabber-nas-spk.sc registration; profile update failed with1202 and the container remained Created. Remove the package port-config worker and its SC file. Container Manager remains the single owner of the published port; do not modify DSM system configuration manually.

The same report shows DSM deletes the application target before postuninst. Sourcing target/installer/package-lib.sh therefore failed on repair. The new hook is self-contained, returns before any path access during UPGRADE or non-opt-in uninstall, and retains the previous canonical private-child/media-overlap/schema checks for explicit data erasure. Regression fixtures remove the whole target before exercising retention and erasure.

0022 is an online correction; the unrun offline workflow now targets0023. No claim of physical0022 success is made before the pilot. Install using Package Center Manual Install as an upgrade/repair over the existing package; do not uninstall or delete its state.

## Historical build 0019: history update; native DSM launch retained

0019 adds compact cursor-paged history, lazy details and confirmed terminal-history erasure. The additive SQLite index and new APIs are described in ../VALIDATION.md. Native DSM launch/CGI/resource/privilege behavior is unchanged from 0018.

The native application ID is SYNO.SDS.App.MediaGrabberNAS.Instance. `ui/config` registers it as type app under MediaGrabber.cgi; INFO sets dsmappname and deliberately omits adminurl so Open follows the native loader instead of plain URL navigation. The native Vue instance/window structure follows Synology ExamplePackages. The script CGI obtains the DSM loader query token and injects only a single URL-safe value into a closure; a valid current SYNO.SDS.Session.SynoToken is preferred if available. No token is stored in localStorage or a custom public global.

The native component performs a same-origin GET to dsm-login.cgi with the token in X-Syno-Token and accepts JSON. The host CGI preserves the browser cookie/address environment and normalizes that actual token into the header, QUERY_STRING and REQUEST_URI needed by modern/legacy DSM helpers. It selects executable webman/authenticate.cgi or the legacy modules path, enforces a 5s POSIX watchdog, rejects failures and requires the validated account to be an administrator. Only then does host curl send the private bridge key via stdin configuration to the fixed loopback grant endpoint. The browser receives only a 60-second single-use grant, never the bridge key or the DSM password. No DSM cookie/token is forwarded into the container through the portal.

The iframe loads /mediagrabber/#dsm-ticket=... and the existing application consumes the grant atomically before issuing its own session. Portal CSP now permits only same-origin framing; direct-port CSP continues to forbid framing. Native errors are rendered as text and retain a password-fallback link. Missing token or expired native identity does not open an iframe or create an application session. App sessions remain independent of DSM logout, expire within 12h and can be ended with app Logout. The original direct/password login remains available.

Minimal conf/privilege, package ID MediaGrabberNAS, permanent directories, credentials, data schema, upgrade backup and native Docker/nginx resources are unchanged. Normal CGI modes are 0755; no executable privilege override, root hook, system-group membership, setid mode or system binary modification is introduced. A browser/SDK loading cache may require closing the old window and refreshing the DSM desktop after the app-ID change.

Tests use real shipped shell CGIs, Vue, nginx, WSGI and grant exchange, starting without an app cookie. Only native DSM SDK container widgets and identity/group validation are mocked; actual DSM loading/validation is still a physical pilot requirement. References and exact results are in ../VALIDATION.md.

---

# Synology SPK implementation

Keep package identity **MediaGrabberNAS** fixed. Installer version **0.1.0-0008** differs from application **0.1.0-beta.8**. Pilot: DS1817+, DSM 7.3.1-86003 Update 1, Container Manager 24.0.2-1606. Build 0002 reached the actual Czech DSM wizard/confirmation and then failed immediately with a generic error; build 0003 also failed immediately with the same generic error. The native log now identifies a JSON conversion abort before package control hooks; build 0004 corrects the wizard export shape, with installation still pending.

## Design

- `conf/privilege` requests DSM's internal `mg-nas` user/group and runs scripts as the package identity. No root hooks, Docker socket, manual UID/GID, scheduled tasks or host Python.
- The native [data-share worker](https://help.synology.com/developer-guide/resource_acquisition/data_share.html) provisions `MediaGrabber` and grants `mg-nas` read/write. Its link is `/var/packages/MediaGrabberNAS/shares/MediaGrabber`. DSM retains this shared folder on package removal.
- The native [Docker Project worker](https://help.synology.com/developer-guide/resource_acquisition/docker-project.html) owns `mediagrabber-nas-spk`, builds the Dockerfile and starts/stops the project. Scripts never invoke Docker or system user-management commands.
- `docker/compose.yaml` is immutable and included in package.tgz from the start. The Docker Project worker acquires its configuration at WHEN_POSTINST, before the postinst script. All three mounts use deferred local bind volumes with nocopy so missing runtime/share paths are not accessed during build/create. Postinst prepares private state/settings only and never rewrites the project.
- State, read-only secrets and media use named **local bind volumes**, not copied Docker data volumes. Media points to the DSM shared-folder link. Removing the Docker volume objects does not delete the underlying directories. The SPK-only Python bootstrap reads the data mount owner; with only SETUID/SETGID it clears supplementary groups and all real/effective/saved IDs, verifies zero effective capabilities and no-new-privileges, then execs tini/Gunicorn as the non-root owner. Tini starts after the drop so it needs no extra KILL capability. The standalone image continues directly as USER 1000.
- State is in `SYNOPKG_PKGVAR/runtime`, outside `target`. The [DSM FHS](https://help.synology.com/developer-guide/integrate_dsm/fhs.html) lists var as permanent storage. Runtime is 0700; secret/settings files are 0600. Paths in Compose are fixed DSM FHS links; only the build number is substituted by the builder. Runtime settings are parsed as a restricted data file, never sourced as shell code.
- Port 8787 is reserved/checked through INFO. The DSM launcher opens that port on the browser's NAS hostname. NAS hostname and `.local` alias are allowed automatically; private IPs work by default. Advanced aliases/HTTPS flags can be edited in private `settings.env`, taking effect on the next package update/restart of the generated runtime settings; these values are preserved.

## Lifecycle and updates

The [DSM script sequence](https://help.synology.com/developer-guide/synology_package/scripts.html) invokes old uninstall hooks during upgrades. Both uninstall hooks are deliberately non-destructive for every status.

`preinst` only validates install/reinstall passwords. `preupgrade` only checks existing schema/secret. In the new `postinst`, upgrade validates schema 1 and snapshots **stopped** state (SQLite DB/WAL/SHM together, private settings/secret and marker) before private settings are refreshed and the new application starts. No media enters the archive. Upgrades retain the original password and database. Explicit install/reinstall uses its new wizard password while retaining database contents; the application invalidates old sessions when credentials change.

The native worker stops/removes the project. `stop` leaves Docker stopping to native WHEN_HALT. `prestart` checks private state only, because data-share may be acquired later. `start` checks the share then waits up to 30 seconds for the application's localhost health marker. `status` returns 0 only for that marker, otherwise 3.

There is no DB schema migration in this build. Future schema changes require explicit forward migration and compatibility/restore tests. Do not blindly restore old data as a downgrade. Backup archives are private, include the credential and are not automatically pruned. The manual `docker/mediagrabber-nas` project and `Mediagrabber` DSM account are not used or changed; Windows application files are unchanged.

## Build and tests

The Python standard-library builder writes tar/gzip, executable bits and LF scripts on Windows too. Icons are size exports of existing PJSoft artwork. A manifest checks payload integrity; INFO has the format's MD5 for package.tgz and SHA-256 accompanies the full SPK.

```sh
python tools/build_spk.py --build 8
```

Increase the build number for **every delivered file** (0009, 0010, …). Never change PACKAGE_ID or reuse a released build number. Image tags include the SPK version. The builder refuses to overwrite an existing SPK with different bytes; increment --build instead. Identical inputs produce identical artifacts. This is an unsigned third-party test package, not Synology-certified software.

The SPK bundles a source/build context. The NAS builds a Linux image from Docker Hub/Debian/PyPI and needs internet. A prebuilt image can be added later through `preload-image`; no Docker build is claimed by local tar validation.

Install `requirements-dev.txt`, then set `MG_TEST_SHELL` to a POSIX shell. Windows tests used upstream Unicode BusyBox for Windows, not MSYS Bash. No shell executable is bundled in the SPK.

```sh
python -m unittest discover -s tests -p test_spk.py -v
```

Fixtures test syntax, UTF-8/shell-metacharacter passwords, immutable Compose availability before postinst, privilege-drop contracts, target replacement with permanent SQLite preservation, backup contents, schema rejection, retained uninstall and reinstall password changes. Only temporary directories are touched; no NAS, Docker daemon or OS account creation.

`tests/spk-wizard-smoke.cjs` uses Playwright, Chrome and Vue 2.7.14 (`MG_TEST_VUE`) to render six JSONP/Vue variants with a **mock DSM UI host**. It checks Next-button validation/getValues and browser errors. The Czech install variant has also rendered and advanced to confirmation on real DSM 7.3.1. Actual installation failed in build 0002; the other variants remain locally mocked. The pilot must verify native resource acquisition/build/start order, ACLs, widget integration, upgrade and shutdown.

## Build 0003 correction

The old local fixture incorrectly ran postinst before requiring the native project configuration, so it did not detect the missing Compose in 0002. A regression now loads Compose after preinst and before postinst and verifies that postinst leaves it unchanged. This fixes a verified packaging defect; the exact cause of the NAS generic error was not obtained from a native log and is not claimed as proven. That build still emitted one field per array record; build 0004 supersedes this export shape. Actual Linux capability and identity operations need the next container pilot, beyond the mocked syscall tests.

## Build 0004: wizard serialization correction

The v2 pilot log contains `JSON_FAIL_MESSAGE("Type is not convertible to string")` followed by signal 6 for the install CGI at 19:36:16 (0002) and 20:14:06 (0003). The package user exists, but package FHS links and control-hook log do not. It establishes a native JSON conversion abort, without identifying the exact JSON field or call site.

Our wizard returned an array of field records. This matched the guide’s Object[] illustration but contradicted Synology’s executable [ExamplePackage install-setting.vue](https://github.com/SynologyOpenSource/ExamplePackages/blob/main/ExamplePackage/WIZARD_UIFILES/src/install-setting.vue), whose getValues returns a single flat object. Build 0004 adopts that actual example for install; upgrade/uninstall return an empty object. All exported values are strings. No other runtime/lifecycle design changed.

The browser fixture now rejects the old array and nested values, checks serialized text values including Unicode and shell metacharacters, and passes valid exports as literal input to POSIX sh, exports the named environment variables, and runs the actual preinst hook. It remains a local fixture, not DSM’s proprietary serialization code. Previous browser tests incorrectly enforced an array and therefore missed this defect. Confirmation of the causal link and further native resource/build/start behavior requires the 0004 pilot.

## Build 0005: DS1817+ CPU CFS compatibility

The physical stopped-project probe parsed Compose successfully but Docker create rejected NanoCPUs because the kernel lacks the CPU CFS scheduler/cgroup. This is the exact error reproduced using the original 0004 configuration and the successfully built image; the scoped cleanup completed. Both NAS profiles now omit cpus (and any equivalent CFS quota). Memory 1 GiB, PID limit, read-only root and privilege settings are retained. The package identity/state schema/hooks are unchanged, allowing an update over retained 0004 state. A compatibility regression checks both templates and the actual built SPK payload. Actual 0005 installation and application startup are still pending.

## Build 0006: explicit application command and older-kernel verification

The 2026-11-15 v3 log reports the 0005 container exited with code 1 and repeated Missing application command. The SPK overrides entrypoint but omitted command. Docker’s [entrypoint contract](https://docs.docker.com/reference/compose-file/services/#entrypoint) discards the image CMD in this case. The SPK now supplies the same complete Gunicorn argument list explicitly. A regression compares the actual packaged Compose command against the packaged Dockerfile CMD, and the bootstrap test exercises forwarding the complete sys.argv to tini after dropping IDs.

Also corrected the independently identified old-kernel verification concern: NoNewPrivs appears in /proc only since Linux 4.10, whereas [PR_GET_NO_NEW_PRIVS](https://man7.org/linux/man-pages/man2/PR_GET_NO_NEW_PRIVS.2const.html) is available since 3.5. If the field is absent, a typed libc prctl(39, 0, 0, 0, 0) must explicitly return 1; 0/error/unavailable rejects startup. Effective capabilities must still be zero; an explicit NoNewPrivs=0 is never overridden. This reads the existing restriction and never sets or disables it. Syscalls are locally mocked on Windows and require the native pilot.

4 archive and 7 bootstrap tests passed. Other application/lifecycle/wizard code is unchanged; prior test records remain historical. The native 0006 update and running application have not yet been verified.

## Build 0007: native command serialization

The combined 0006 probe reports build=0, config=0, stopped-create=0 and cleanup=0. The native installation log instead pinpoints docker-compose.admin.yaml: services.mediagrabber.command.5 must be a string. In the source list, element 5 is the quoted workers value 1; source YAML is accepted by the same Docker Compose 2.20.1. This locates the failure in the native generated configuration, consistent with scalar type conversion during reserialization (the generated file itself has not been obtained).

Use a folded string command, a supported [Compose command form](https://docs.docker.com/reference/compose-file/services/#command), so the native writer handles one nonnumeric scalar. Compose splits it into the exact same argv, verified against the packaged Dockerfile CMD with shlex after a YAML roundtrip. No shell is added, and no application arguments, IDs, mounts, restrictions or lifecycle hooks changed. Application startup on the NAS and its native admin-YAML generation remain to be verified with 0007.

The probe also showed DS1817+ discards the requested PID limit as unsupported. This was a nonfatal warning; it is not treated as the failed create cause or an enforced limit on that kernel. Other supported hosts may apply the requested PID limit.

## Build 0008: factory quoting and real Compose parser validation

The command snapshot confirms both original and generated admin YAML contain the 0007 scalar command. The retained-old-list hypothesis was disproved. Subsequent native errors changed to invalid command line string. In go-shellwords v1.0.12 (used by Compose 2.20.1), unquoted parentheses are rejected; Python shlex.split accepted the same value, making the earlier regression insufficient.

Quote the application-factory argument within the scalar. This is command parsing, not an extra shell process. Upstream Docker Compose 2.20.1 Windows standalone (official Docker release asset, SHA-256 7e6f1f0e5fadd6f834de067f4e321560eb1b6465dff62f59cffe36a23a300497) reproduced the unquoted failure and accepted the corrected command. config --format json yields exactly the image's CMD argv, including the literal factory parentheses and numeric arguments as strings.

Set MG_TEST_COMPOSE to that standalone executable to run the optional real-parser archive test. It checks the actual built payload and a YAML roundtrip, plus negative cases for the native 0006 numeric entry and unquoted 0007 scalar. No Docker Engine, image pull, container execution or system installation is involved. The upstream Windows parser is not the Synology fork/runtime, so native installation/startup remains a separate pilot.

References: https://github.com/docker/compose/releases/tag/v2.20.1 ; https://github.com/docker/compose/blob/v2.20.1/go.mod ; https://github.com/mattn/go-shellwords/blob/v1.0.12/shellwords.go .
