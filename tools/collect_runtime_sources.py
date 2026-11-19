# SPDX-License-Identifier: GPL-3.0-or-later
"""Collect corresponding upstream sources for an exact saved Linux image; fail closed."""
import argparse
import gzip
import hashlib
import io
import json
import os
import subprocess
import tarfile
import tempfile
from pathlib import Path

from build_spk import ROOT, add, validate_image


def collect(image, archive, output, version):
    image_id=validate_image(archive,version)
    local_id=subprocess.check_output(['docker','image','inspect','--format','{{.Id}}',image],text=True).strip().removeprefix('sha256:')
    if local_id != image_id:raise ValueError('Saved image and source-collection image differ.')
    output.parent.mkdir(parents=True,exist_ok=True)
    if output.exists():raise ValueError('Do not overwrite an existing runtime source archive.')
    with tempfile.TemporaryDirectory(prefix='mg-runtime-sources-',dir=output.parent) as directory:
        folder=Path(directory).resolve()
        subprocess.run(['docker','run','--rm','-i','--user','0:0','--entrypoint','python',
            '--mount','type=bind,source='+str(folder)+',target=/out',
            '--env','OUTPUT_UID='+str(os.getuid()),'--env','OUTPUT_GID='+str(os.getgid()),image,'-'],
            input=(ROOT/'tools/collect_sources_worker.py').read_bytes(),check=True)
        records={p.relative_to(folder).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in folder.rglob('*') if p.is_file()}
        if not any(n.startswith('debian/') for n in records) or not any(n.startswith('python/') for n in records):
            raise ValueError('Incomplete runtime source collection.')
        manifest={'version':version,'image_config_sha256':image_id,'files':records}
        # Write only after every required source download has succeeded.
        with output.open('wb') as destination:
            with gzip.GzipFile(fileobj=destination,mode='wb',mtime=0,filename='') as gz:
                with tarfile.open(fileobj=gz,mode='w',format=tarfile.PAX_FORMAT) as tar:
                    add(tar,'RUNTIME-SOURCE-MANIFEST.json',json.dumps(manifest,indent=2).encode())
                    for name in sorted(records):add(tar,name,(folder/name).read_bytes())
    return output


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--image',required=True)
    parser.add_argument('--archive',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--version',required=True)
    args=parser.parse_args()
    print(collect(args.image,args.archive,args.output,args.version))
