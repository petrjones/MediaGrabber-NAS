# SPDX-License-Identifier: GPL-3.0-or-later
"""Run only in a disposable build container with an empty /out mount, never on a NAS."""
import hashlib
import json
import os
import subprocess
import urllib.request
from pathlib import Path

OUT = Path('/out')


def download(url, target, expected=None):
    target.parent.mkdir(parents=True, exist_ok=True)
    digest = hashlib.sha256()
    with urllib.request.urlopen(urllib.request.Request(url, headers={'User-Agent':'PJSoft-source-collector'}), timeout=60) as response, target.open('wb') as stream:
        while chunk := response.read(1024 * 1024):
            stream.write(chunk)
            digest.update(chunk)
    if expected and digest.hexdigest() != expected:
        raise RuntimeError('Source checksum mismatch: ' + target.name)


def main():
    inventory = json.loads(Path('/app/runtime-inventory.json').read_text())
    # Resolve source packages using the same signed repositories as the image.
    for path in Path('/etc/apt/sources.list.d').glob('*.sources'):
        text = path.read_text()
        if 'Types: deb\n' in text:
            path.with_name('source-' + path.name).write_text(text.replace('Types: deb\n', 'Types: deb-src\n'))
    subprocess.run(['apt-get','update'], check=True)
    debian = OUT/'debian';debian.mkdir()
    for name, version in sorted({(p['source'],p['source_version']) for p in inventory['debian_packages']}):
        subprocess.run(['apt-get','-y','--download-only','source',name+'='+version], cwd=debian, check=True)
    for package in inventory['python_packages']:
        url = 'https://pypi.org/pypi/'+package['name']+'/'+package['version']+'/json'
        with urllib.request.urlopen(url, timeout=30) as response: info=json.load(response)
        source = next((p for p in info['urls'] if p['packagetype']=='sdist' and not p['yanked']),None)
        if not source or not source['url'].startswith('https://files.pythonhosted.org/'):
            raise RuntimeError('No corresponding Python source: '+package['name'])
        filename=Path(source['filename']).name
        download(source['url'], OUT/'python'/filename, source['digests']['sha256'])
    node = inventory['node'].strip()
    node_name='node-'+node+'.tar.xz'
    with urllib.request.urlopen('https://nodejs.org/dist/'+node+'/SHASUMS256.txt',timeout=30) as r: sums=r.read().decode()
    expected=next(line.split()[0] for line in sums.splitlines() if line.split()[-1]==node_name)
    download('https://nodejs.org/dist/'+node+'/'+node_name, OUT/'runtimes'/node_name, expected)
    python=inventory['python']
    download('https://www.python.org/ftp/python/'+python+'/Python-'+python+'.tar.xz',OUT/'runtimes'/('Python-'+python+'.tar.xz'))
    # Preserve the actual runtime/build metadata, not an assumed package list.
    (OUT/'runtime-inventory.json').write_text(json.dumps(inventory,indent=2))
    for name in ['Dockerfile','LICENSE','COPYRIGHT','THIRD-PARTY-NOTICES.md','python-install-report.json']:
        path=Path('/app')/name
        if path.is_file(): (OUT/name).write_bytes(path.read_bytes())
    # Return ownership of files in this dedicated build-output mount to the CI user.
    uid,gid=int(os.environ['OUTPUT_UID']),int(os.environ['OUTPUT_GID'])
    for path in OUT.rglob('*'):
        if not path.is_symlink(): os.chown(path,uid,gid)


if __name__=='__main__':main()
