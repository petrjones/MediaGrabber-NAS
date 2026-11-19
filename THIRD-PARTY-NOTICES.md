# Third-party components and notices

Original MediaGrabber NAS source code is GPL-3.0-or-later; see LICENSE and COPYRIGHT. Third-party software retains the licenses and copyrights shown below. This does not relicense independent tools or all operating-system components under the application license.

## Python runtime, pinned in requirements-linux.lock

| Component | Version | Upstream license | Included notice texts |
| --- | --- | --- | --- |
| gunicorn | 27.0.1 | MIT | [notice](LICENSES/gunicorn-27.0.1-0-LICENSE) |
| yt-dlp | 2026.10.26 | Unlicense | [notice](LICENSES/yt-dlp-2026.10.26-0-LICENSE) |
| mutagen | 1.48.1 | GPL-2.0-or-later | [notice](LICENSES/mutagen-1.48.1-0-COPYING) |
| yt-dlp-ejs | 0.8.0 | Unlicense AND MIT AND ISC | [notice](LICENSES/yt-dlp-ejs-0.8.0-0-LICENSE) |
| requests | 2.34.2 | Apache-2.0 | [notice](LICENSES/requests-2.34.2-0-LICENSE), [notice](LICENSES/requests-2.34.2-1-NOTICE) |
| charset-normalizer | 3.5.2 | MIT | [notice](LICENSES/charset-normalizer-3.5.2-0-LICENSE) |
| idna | 3.20 | BSD-3-Clause | [notice](LICENSES/idna-3.20-0-LICENSE.md) |
| urllib3 | 2.8.0 | MIT | [notice](LICENSES/urllib3-2.8.0-0-LICENSE.txt) |
| certifi | 2026.10.23 | MPL-2.0 | [notice](LICENSES/certifi-2026.10.23-0-LICENSE) |
| websockets | 17.4 | BSD-3-Clause | [notice](LICENSES/websockets-17.4-0-LICENSE) |
| brotli | 1.2.1 | MIT | [notice](LICENSES/brotli-1.2.1-0-LICENSE) |
| pycryptodomex | 3.24.2 | BSD, Public Domain | [notice](LICENSES/pycryptodomex-3.24.2-0-LICENSE.rst) |

## Runtimes, native tools and examples

- Python: PSF license and included notices; reference text in LICENSES/python3.12-LICENSE.txt. The image version is recorded at build time.
- Node.js: MIT and bundled dependency notices. The Dockerfile copies the actual upstream image LICENSE to /usr/local/share/doc/node/LICENSE; LICENSES/node22-LICENSE.txt is a branch reference.
- FFmpeg/FFprobe: LGPL/GPL depending on the actual Debian build. The app invokes them as separate executables. The runtime inventory includes their build configuration and license output. Debian copyright files remain under /usr/share/doc.
- Tini: MIT; reference text in LICENSES/tini-LICENSE.txt, with actual Debian notices retained in the image.
- DSM application/wizard integration follows Synology ExamplePackages. Adapted example patterns retain the Synology MIT notice in LICENSES/Synology-ExamplePackage-MIT.txt. DSM/Vue SDK runtime is supplied by DSM and not copied into this SPK.
- Debian/base image packages retain their upstream licenses, copyright notices and source-package identities; see runtime-inventory.json in an actual built image.

## Corresponding source and distribution

SOURCE.tar.gz contains this NAS source tree and its build/install scripts, including the unmodified Mutagen 1.48.1 source in vendor-sources with its verified upstream SHA-256. It never includes NAS data, passwords or private backups. It is available through the About source link in a packaged installation.

Online development SPKs contain source/build context and obtain other runtime tools from their upstream distribution services. Offline SPKs also redistribute a saved Linux image; the build requires a matching runtime source archive, checks the image identity, and emits that archive as a separate review/release artifact. Publish it alongside the SPK. Do not claim the runtime source obligation has been completed merely because the build recipe exists.

No proprietary permission to use YouTube content, trademarks or services is supplied by these software licenses. Application users and distributors must separately comply with applicable rights and service terms.
