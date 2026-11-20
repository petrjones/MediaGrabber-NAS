"""Exercise CI shell paths and artifact separation without Docker or a network."""
import fnmatch
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
import yaml

from test_spk import ROOT, SHELL, builder


@unittest.skipUnless(SHELL, 'set MG_TEST_SHELL for the CI-shell fixture')
class WorkflowTests(unittest.TestCase):
    def test_build_shell_produces_two_separate_complete_artifact_groups(self):
        workflow=yaml.load((ROOT/'.github/workflows/build-synology.yml').read_text(),Loader=yaml.BaseLoader)
        steps=workflow['jobs']['build']['steps']
        script=next(s['run'] for s in steps if s.get('name')=='Build Linux image and collect its corresponding sources')
        stubs='''
docker() {
    case "$1" in
        build) return 0 ;;
        save) printf 'saved-image-fixture' ;;
        *) return 2 ;;
    esac
}
python() {
    mode=$1; shift
    output=''; build=''
    while [ "$#" -gt 0 ]; do
        case "$1" in
            --output) output=$2; shift 2 ;;
            --build) build=$2; shift 2 ;;
            *) shift ;;
        esac
    done
    [ -n "$output" ] || return 2
    case "$mode" in
        tools/collect_runtime_sources.py) printf 'runtime-source-fixture' > "$output" ;;
        tools/build_spk.py)
            [ "$build" = "$EXPECTED_BUILD" ] || return 2
            printf 'spk-fixture' > "$output/MediaGrabber-NAS-$EXPECTED_VERSION.spk"
            printf 'spk-sha-fixture' > "$output/MediaGrabber-NAS-$EXPECTED_VERSION.spk.sha256" ;;
        *) return 2 ;;
    esac
}
'''
        version='0.1.0-'+str(builder.DEFAULT_BUILD).zfill(4)
        with tempfile.TemporaryDirectory() as directory:
            folder=Path(directory)
            context=folder/'release-build/context';context.mkdir(parents=True)
            (context/'SOURCE.tar.gz').write_bytes(b'app-source-fixture')
            probe=folder/'probe.sh';probe.write_text(stubs+'\n'+script,encoding='utf-8',newline='\n')
            executable=[SHELL,'sh'] if 'busybox' in Path(SHELL).name.lower() else [SHELL]
            result=subprocess.run([*executable,str(probe)],cwd=folder,
                env=dict(os.environ,EXPECTED_BUILD=str(builder.DEFAULT_BUILD),EXPECTED_VERSION=version),
                capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stdout+result.stderr)
            self.assertFalse((folder/'release-build/image.tar.gz').exists())
            actual={p.relative_to(folder).as_posix() for p in (folder/'release-build').iterdir() if p.is_file()}
            uploads=[s['with'] for s in steps if s.get('uses','').startswith('actions/upload-artifact@')]
            self.assertEqual(len(uploads),2)
            groups=[]
            for upload in uploads:
                selected={p for p in actual if any(fnmatch.fnmatchcase(p,pattern) for pattern in upload['path'].splitlines())}
                self.assertTrue(selected)
                self.assertEqual(upload['if-no-files-found'],'error')
                groups.append(selected)
            self.assertFalse(groups[0]&groups[1])
            self.assertEqual(groups[0]|groups[1],actual)
            self.assertTrue(any(p.endswith('.spk') for p in groups[0]))
            self.assertFalse(any('runtime-sources' in p for p in groups[0]))
            self.assertTrue(all('runtime-sources' in p for p in groups[1]))
