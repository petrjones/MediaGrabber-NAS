# SPDX-License-Identifier: GPL-3.0-or-later
"""Prepare a clean Docker build context with the exact source download archive."""
import argparse
from pathlib import Path
from build_spk import ROOT, DEFAULT_BUILD, FEATURE_VERSION, source_archive, payload_files

if __name__ == "__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--build',type=int,default=DEFAULT_BUILD)
    parser.add_argument('--output',type=Path)
    args=parser.parse_args()
    if not 0<args.build<2**31:raise ValueError('Invalid build number.')
    version=FEATURE_VERSION+'-'+str(args.build).zfill(4)
    if args.output:
        target=args.output.resolve()
        if not target.is_relative_to((ROOT/'release-build').resolve()) or target.exists() and any(target.iterdir()):
            raise ValueError('Use a new empty context under the project release-build directory.')
        for name,data in payload_files(version).items():
            if name.startswith('docker/'):
                path=target/name.removeprefix('docker/')
                path.parent.mkdir(parents=True,exist_ok=True)
                path.write_bytes(data)
    else:
        target=ROOT/'SOURCE.tar.gz'
        target.write_bytes(source_archive(version))
    print(target)
