"""Real source/license inclusion and offline assembly validation without Docker."""
import gzip
import hashlib
import io
import json
import tarfile
import tempfile
import unittest
from pathlib import Path

from test_spk import builder, payload


def fixture_image(folder, version, architecture='amd64'):
    config=json.dumps({'os':'linux','architecture':architecture,'config':{'Labels':{'org.opencontainers.image.version':version}}}).encode()
    digest=hashlib.sha256(config).hexdigest()
    name=digest+'.json'
    image=folder/'image.tar.gz'
    with tarfile.open(image,'w:gz') as tar:
        builder.add(tar,name,config)
        builder.add(tar,'manifest.json',json.dumps([{'Config':name,'RepoTags':['pjsoft/mediagrabber-nas:spk-'+version],'Layers':[]}]).encode())
    sources=folder/'runtime-sources.tar.gz'
    with tarfile.open(sources,'w:gz') as tar:
        builder.add(tar,'RUNTIME-SOURCE-MANIFEST.json',json.dumps({'version':version,'image_config_sha256':digest}).encode())
    return image,sources


class ReleasePackagingTests(unittest.TestCase):
    def test_packaged_sources_and_licenses_never_include_runtime_secrets(self):
        with tempfile.TemporaryDirectory() as directory:
            artifact=builder.build_spk(Path(directory),21)
            with payload(artifact) as inner:
                self.assertNotIn('port_conf/MediaGrabberNAS.sc',inner.getnames())
                self.assertIn(b'GNU GENERAL PUBLIC LICENSE',inner.extractfile('LICENSE').read())
                archive=inner.extractfile('docker/SOURCE.tar.gz').read()
                with tarfile.open(fileobj=io.BytesIO(archive),mode='r:gz') as source:
                    names=source.getnames()
                    self.assertIn('MediaGrabber-NAS/tools/build_spk.py',names)
                    self.assertIn('MediaGrabber-NAS/LICENSE',names)
                    self.assertTrue(any(n.startswith('MediaGrabber-NAS/vendor-sources/mutagen-') for n in names))
                    self.assertFalse(any('/secrets/' in n or n.endswith('.sqlite3') or '/.git/' in n for n in names))

    def test_offline_package_never_builds_or_pulls_and_keeps_matching_evidence(self):
        with tempfile.TemporaryDirectory() as directory:
            folder=Path(directory);image,sources=fixture_image(folder,'0.1.0-0021')
            artifact=builder.build_spk(folder,21,image,sources)
            with tarfile.open(artifact) as outer:
                resource=json.load(outer.extractfile('conf/resource'))
                self.assertEqual(resource['docker-project']['preload-image'],'image.tar.gz')
                self.assertFalse(resource['docker-project']['projects'][0]['build_params']['build'])
                self.assertEqual(outer.extractfile('image.tar.gz').read(),image.read_bytes())
            with payload(artifact) as inner:
                compose=inner.extractfile('docker/compose.yaml').read()
                self.assertNotIn(b'    build:',compose)
                self.assertIn(b'pull_policy: never',compose)
                info=json.load(inner.extractfile('OFFLINE-IMAGE.json'))
                self.assertEqual(info['runtime_sources_sha256'],hashlib.sha256(sources.read_bytes()).hexdigest())
                manifest=json.load(inner.extractfile('BUILD-MANIFEST.json'))
                for name,digest in manifest['files'].items():self.assertEqual(hashlib.sha256(inner.extractfile(name).read()).hexdigest(),digest)

    def test_offline_rejects_wrong_architecture_version_or_missing_sources(self):
        with tempfile.TemporaryDirectory() as directory:
            folder=Path(directory)
            image,sources=fixture_image(folder,'0.1.0-0021','arm64')
            with self.assertRaises(ValueError):builder.build_spk(folder,21,image,sources)
            image,sources=fixture_image(folder,'0.1.0-0020')
            with self.assertRaises(ValueError):builder.build_spk(folder,21,image,sources)
            image,sources=fixture_image(folder,'0.1.0-0021')
            with self.assertRaises(ValueError):builder.build_spk(folder,21,image,None)


if __name__=='__main__':unittest.main()
