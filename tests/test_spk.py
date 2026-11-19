"""SPK archive + lifecycle regressions with an isolated DSM filesystem fixture.

Set MG_TEST_SHELL to a POSIX shell or BusyBox executable to include lifecycle tests.
These tests never call Docker, DSM APIs, add OS users, or access a NAS.
"""
import gzip
import hashlib
import importlib.util
import io
import functools
import json
import os
import shlex
import shutil
import sqlite3
import struct
import subprocess
import tarfile
import tempfile
import threading
import unittest
from pathlib import Path
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("spk_builder", ROOT/"tools/build_spk.py")
builder = importlib.util.module_from_spec(spec)
spec.loader.exec_module(builder)
SHELL = os.environ.get("MG_TEST_SHELL", "")
COMPOSE = os.environ.get("MG_TEST_COMPOSE", "")
PASSWORD = "Test ' \" $HOME ; & \\ long password žluťoučký"


def payload(archive):
    with tarfile.open(archive) as outer:
        return tarfile.open(fileobj=io.BytesIO(outer.extractfile("package.tgz").read()),mode="r:gz")


class ArchiveTests(unittest.TestCase):
    def test_container_manager_is_the_only_owner_of_published_port_registration(self):
        import yaml
        with tempfile.TemporaryDirectory() as directory:
            archive = builder.build_spk(Path(directory))
            with tarfile.open(archive) as outer:
                resource = json.load(outer.extractfile("conf/resource"))
                self.assertNotIn("port-config", resource)
                self.assertEqual(resource["docker-project"]["projects"][0]["name"], "mediagrabber-nas-spk")
            with payload(archive) as inner:
                self.assertFalse(any(m.name.startswith("port_conf/") for m in inner.getmembers()))
                compose = yaml.safe_load(inner.extractfile("docker/compose.yaml"))
                self.assertEqual(str(compose["services"]["mediagrabber"]["ports"][0]), "8787:8787")

    def test_privilege_is_minimal_package_identity_and_payload_has_no_setid(self):
        with tempfile.TemporaryDirectory() as directory:
            archive = builder.build_spk(Path(directory))
            with tarfile.open(archive) as outer:
                self.assertEqual(json.load(outer.extractfile("conf/privilege")),
                                 {"defaults":{"run-as":"package"},"username":"mg-nas","groupname":"mg-nas"})
                for member in outer.getmembers():
                    self.assertFalse(member.mode & 0o6000, member.name)
            with payload(archive) as inner:
                for member in inner.getmembers():
                    self.assertFalse(member.mode & 0o6000, member.name)
                self.assertEqual(inner.getmember("ui/dsm-login.cgi").mode, 0o755)

    def test_builder_rejects_optional_privilege_overrides_before_writing(self):
        variants = [{"defaults":{"run-as":"root"}},
                    {"defaults":{"run-as":"package"},"username":"mg-nas","groupname":"mg-nas",
                     "executable":[{"relpath":"ui/dsm-login.cgi","run-as":"package"}]}]
        with tempfile.TemporaryDirectory() as directory:
            original_text = builder.text
            for value in variants:
                def read(path):
                    return json.dumps(value).encode() if path == ROOT/"synology/conf/privilege" else original_text(path)
                with patch.object(builder, "text", side_effect=read), self.assertRaises(ValueError):
                    builder.build_spk(Path(directory))
            self.assertEqual(list(Path(directory).iterdir()), [])

    def test_all_local_dockerfile_copy_sources_are_inside_packaged_build_context(self):
        with tempfile.TemporaryDirectory() as directory:
            archive = builder.build_spk(Path(directory))
            with payload(archive) as inner:
                files = {m.name:inner.extractfile(m).read() for m in inner.getmembers() if m.isfile()}
        dockerfile = files['docker/Dockerfile'].decode()
        checked = []
        for line in dockerfile.splitlines():
            if not line.startswith('COPY ') or '--from=' in line:
                continue
            parts = shlex.split(line)[1:]
            for source in parts[:-1]:
                path = 'docker/' + source.removeprefix('./').rstrip('/')
                self.assertTrue(path in files or any(n.startswith(path + '/') for n in files),
                                'Missing COPY source in packaged Docker context: ' + source)
                checked.append(source)
        self.assertIn('THIRD-PARTY-NOTICES.md', checked)
        self.assertEqual(files['docker/THIRD-PARTY-NOTICES.md'], files['THIRD-PARTY-NOTICES.md'])

    def test_native_launcher_uses_dsm_bridge_and_registered_same_origin_portal(self):
        with tempfile.TemporaryDirectory() as directory:
            archive = builder.build_spk(Path(directory))
            with tarfile.open(archive) as outer:
                info = outer.extractfile('INFO').read().decode()
            with payload(archive) as inner:
                app = json.loads(inner.extractfile('ui/config').read())['MediaGrabber.cgi']['SYNO.SDS.App.MediaGrabberNAS.Instance']
                for name in ['ui/dsm-login.cgi', 'ui/MediaGrabber.cgi']:
                    cgi = inner.getmember(name)
                    self.assertEqual(cgi.mode, 0o755)
                    self.assertNotIn(b'\r', inner.extractfile(cgi).read())
                self.assertIn('ui/native-app.js', inner.getnames())
                config = inner.extractfile('nginx/portal.conf').read().decode()
            with tarfile.open(archive) as outer:
                resource = json.load(outer.extractfile('conf/resource'))
            self.assertNotIn('protocol', app)
            self.assertNotIn('port', app)
            self.assertEqual(app['type'], 'app')
            self.assertEqual(app['appWindow'], 'SYNO.SDS.App.MediaGrabberNAS.Instance')
            self.assertNotIn('url', app)
            self.assertIn('dsmappname="SYNO.SDS.App.MediaGrabberNAS.Instance"', info)
            self.assertNotIn('adminurl=', info)
            self.assertNotIn('adminprotocol=', info)
            self.assertNotIn('adminport=', info)
            self.assertIn('instuninst_restart_services="nginx.service"', info)
            self.assertEqual(resource['web-config']['nginx-static-config']['enable'], [{'type':'dsm','relpath':'nginx/portal.conf'}])
            self.assertIn('proxy_set_header Cookie "mg_portal_session=$cookie_mg_portal_session";', config)
            self.assertIn('proxy_set_header X-MG-Bridge-Key "";', config)

    @unittest.skipUnless(COMPOSE,"optional real Compose parser test: set MG_TEST_COMPOSE")
    def test_compose_2201_parser_on_packaged_command_and_historical_failures(self):
        # Run upstream Compose's real config parser without a Docker daemon.
        # Python shlex accepts the unquoted factory parentheses that Compose
        # 2.20.1 rejects; it was not sufficient validation for the 0007 fix.
        import yaml
        with tempfile.TemporaryDirectory() as directory:
            folder=Path(directory)/"docker"
            folder.mkdir()
            archive=builder.build_spk(Path(directory)/"spk")
            with payload(archive) as inner:
                source=inner.extractfile("docker/compose.yaml").read()
                dockerfile=inner.extractfile("docker/Dockerfile").read().decode()
            expected=json.loads(next(line[4:] for line in dockerfile.splitlines() if line.startswith("CMD ")))
            config=yaml.safe_load(source)
            def parse(name, contents):
                path=folder/name
                path.write_bytes(contents if isinstance(contents,bytes) else yaml.safe_dump(contents).encode())
                return subprocess.run([COMPOSE,"-p","mg-parser-regression","-f",str(path),"config","--format","json"],
                                      capture_output=True,text=True,encoding="utf-8",timeout=30)
            for name,contents in [("compose.yaml",source),("roundtrip.yaml",config)]:
                result=parse(name,contents)
                self.assertEqual(result.returncode,0,result.stderr)
                normalized=json.loads(result.stdout)["services"]["mediagrabber"]
                self.assertEqual(normalized["command"],expected)
                self.assertEqual(normalized["entrypoint"],["python","-m","mg_nas.container_entrypoint"])
            bad_unquoted={"services":{"test":{"image":"fixture:parser-only","command":" ".join(expected)}}}
            result=parse("bad-0007.yaml",bad_unquoted)
            self.assertNotEqual(result.returncode,0)
            self.assertIn("invalid command line string",result.stderr)
            bad_numbers=expected.copy()
            self.assertEqual(bad_numbers[5],"1")
            bad_numbers[5]=1
            result=parse("bad-native-0006.yaml",{"services":{"test":{"image":"fixture:parser-only","command":bad_numbers}}})
            self.assertNotEqual(result.returncode,0)
            self.assertIn("command.5 must be a string",result.stderr)

    def test_spk_entrypoint_explicitly_receives_complete_image_command(self):
        # Compose discards an image CMD when it overrides entrypoint. The
        # physical 0005 container exited before startup because argv was empty.
        import yaml
        with tempfile.TemporaryDirectory() as directory:
            archive=builder.build_spk(Path(directory))
            with payload(archive) as inner:
                service=yaml.safe_load(inner.extractfile("docker/compose.yaml").read())["services"]["mediagrabber"]
                dockerfile=inner.extractfile("docker/Dockerfile").read().decode()
        image_command=json.loads(next(line[4:] for line in dockerfile.splitlines() if line.startswith("CMD ")))
        self.assertEqual(service["entrypoint"],["python","-m","mg_nas.container_entrypoint"])
        # Native Container Manager rejected command.5 in its generated admin
        # YAML for the 0006 list, while a direct Compose probe passed. Keep a
        # scalar across serialization and let Compose split it into argv.
        self.assertIsInstance(service["command"],str)
        roundtrip=yaml.safe_load(yaml.safe_dump(service))["command"]
        self.assertEqual(roundtrip,service["command"])
        command=shlex.split(roundtrip)
        self.assertEqual(command,image_command)
        self.assertTrue(all(isinstance(arg,str) and arg for arg in command))
        self.assertEqual(command[:2],["gunicorn","mg_nas.app:create_app()"])

    def test_nas_profiles_and_payload_do_not_require_cpu_cfs_support(self):
        # Physical DS1817+ create failed on HostConfig.NanoCpus; check both
        # distribution profiles and the actual SPK, not only a YAML template.
        import yaml
        forbidden={"cpus","cpu_quota","cpu_period","cpu_rt_runtime","cpu_rt_period"}
        with tempfile.TemporaryDirectory() as directory:
            archive=builder.build_spk(Path(directory))
            with payload(archive) as inner:
                documents=[yaml.safe_load(inner.extractfile("docker/compose.yaml").read())]
            documents.extend(yaml.safe_load(path.read_text()) for path in [ROOT/"compose.yaml",ROOT/"synology/compose.yaml"])
            for document in documents:
                for service in document["services"].values():
                    self.assertFalse(forbidden.intersection(service))
                    limits=service.get("deploy",{}).get("resources",{}).get("limits",{})
                    self.assertNotIn("cpus",limits)
                    self.assertEqual(service["mem_limit"],"1g")
                    self.assertEqual(service["pids_limit"],128)
                    self.assertTrue(service["read_only"])

    def test_structure_metadata_resources_icons_manifest_and_reproducibility(self):
        with tempfile.TemporaryDirectory() as directory:
            a = builder.build_spk(Path(directory)/"a",2)
            b = builder.build_spk(Path(directory)/"b",2)
            self.assertEqual(a.read_bytes(), b.read_bytes())
            with tarfile.open(a) as tar:
                names = tar.getnames()
                self.assertIn("INFO", names)
                info = tar.extractfile("INFO").read().decode()
                self.assertIn('package="MediaGrabberNAS"',info)
                self.assertIn('version="0.1.0-0002"',info)
                self.assertIn('os_min_ver="7.2.2-72806"',info)
                self.assertIn('arch="x86_64"',info)
                self.assertIn('checksum="'+hashlib.md5(tar.extractfile("package.tgz").read()).hexdigest()+'"',info)
                privilege = json.load(tar.extractfile("conf/privilege"))
                self.assertEqual(privilege["defaults"]["run-as"],"package")
                self.assertEqual(privilege["username"],"mg-nas")
                resource = json.load(tar.extractfile("conf/resource"))
                self.assertEqual(resource["data-share"]["shares"][0]["name"],"MediaGrabber")
                self.assertEqual(resource["docker-project"]["projects"][0]["name"],"mediagrabber-nas-spk")
                for name,size in [("PACKAGE_ICON.PNG",64),("PACKAGE_ICON_256.PNG",256)]:
                    png = tar.extractfile(name).read()
                    self.assertEqual(png[:8],b"\x89PNG\r\n\x1a\n")
                    self.assertEqual(struct.unpack(">II",png[16:24]),(size,size))
                for member in tar.getmembers():
                    self.assertFalse(member.name.startswith("/"))
                    self.assertNotIn("..",Path(member.name).parts)
                    if member.name.startswith("scripts/"):
                        self.assertEqual(member.mode,0o755)
                        self.assertNotIn(b"\r",tar.extractfile(member).read())
                for language in ["","_csy"]:
                    for kind in ["install","upgrade","uninstall"]:
                        wizard = json.load(tar.extractfile(f"WIZARD_UIFILES/{kind}_uifile{language}"))[0]
                        self.assertEqual(wizard["custom_render_name"],"mediagrabber_"+kind)
                        self.assertNotIn("__KIND__",wizard["custom_render_fn"])
                        self.assertIn("JsonpLoader.load",wizard["custom_render_fn"])
            with payload(a) as inner:
                manifest = json.load(inner.extractfile("BUILD-MANIFEST.json"))
                for name,digest in manifest["files"].items():
                    self.assertEqual(hashlib.sha256(inner.extractfile(name).read()).hexdigest(),digest)
                self.assertIn("docker/compose.yaml",inner.getnames())
                import yaml
                compose=yaml.safe_load(inner.extractfile("docker/compose.yaml").read())
                self.assertEqual(compose["services"]["mediagrabber"]["entrypoint"],["python","-m","mg_nas.container_entrypoint"])
                self.assertEqual(compose["services"]["mediagrabber"]["cap_add"],["SETUID","SETGID"])
                self.assertTrue(all(v["volume"]["nocopy"] for v in compose["services"]["mediagrabber"]["volumes"]))
                self.assertTrue(compose["services"]["mediagrabber"]["volumes"][1]["read_only"])
                self.assertNotIn(".env",inner.getnames())
                self.assertFalse(any("admin_password" in name for name in inner.getnames()))

    def test_build_number_changes_identity_stays_fixed(self):
        with tempfile.TemporaryDirectory() as directory:
            a = builder.build_spk(Path(directory),2)
            b = builder.build_spk(Path(directory),3)
            for path in [a,b]:
                with tarfile.open(path) as tar:
                    info = tar.extractfile("INFO").read().decode()
                    self.assertIn('package="MediaGrabberNAS"',info)
            with tarfile.open(b) as tar:
                self.assertIn('version="0.1.0-0003"',tar.extractfile("INFO").read().decode())
            self.assertNotEqual(a.read_bytes(),b.read_bytes())
            original=a.read_bytes()
            modified=builder.payload_files("0.1.0-0002") | {"changed-build.txt":b"different source"}
            with patch.object(builder,"payload_files",return_value=modified), self.assertRaises(ValueError):
                builder.build_spk(Path(directory),2)
            self.assertEqual(a.read_bytes(),original)
            for bad in [0,-1,2**31,"2"]:
                with self.assertRaises(ValueError):
                    builder.build_spk(Path(directory),bad)


@unittest.skipUnless(SHELL,"optional lifecycle tests: set MG_TEST_SHELL to sh/bash or BusyBox")
class LifecycleTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="mg-spk-")
        self.root = Path(self.temp.name)
        self.target = self.root/"target ' quoted $MG_NOT_INTERPOLATED"
        (self.target/"installer").mkdir(parents=True)
        (self.target/"installer/package-lib.sh").write_bytes((ROOT/"synology/package-lib.sh").read_bytes())
        (self.target/"SPK_VERSION").write_text("0.1.0-0002\n")
        (self.target/"docker").mkdir()
        self.initial_compose=(ROOT/"synology/compose.yaml").read_text().replace("__SPK_VERSION__","0.1.0-0002")
        (self.target/"docker/compose.yaml").write_text(self.initial_compose)
        self.state = self.root/"permanent-var"
        self.state.mkdir()
        self.share = self.root/"MediaGrabber"
        self.share.mkdir()
        self.env = dict(os.environ,SYNOPKG_PKGNAME="MediaGrabberNAS",SYNOPKG_PKGDEST=self.target.as_posix(),
                        SYNOPKG_PKGVAR=self.state.as_posix(),MG_SPK_SHARE_PATH=self.share.as_posix(),
                        SYNOPKG_PKG_STATUS="INSTALL",wizard_admin_password=PASSWORD,wizard_admin_password_confirm=PASSWORD,
                        SYNOPKG_TEMP_LOGFILE=(self.root/"installer-result.log").as_posix())

    def tearDown(self):
        self.temp.cleanup()

    def run_hook(self, name, *args, success=True, env=None):
        executable = [SHELL,"sh"] if "busybox" in Path(SHELL).name.lower() else [SHELL]
        result = subprocess.run([*executable,str(ROOT/"synology/scripts"/name),*args],env=env or self.env,capture_output=True,text=True,encoding="utf-8",errors="replace")
        if success:
            self.assertEqual(result.returncode,0,result.stdout+result.stderr)
        else:
            self.assertNotEqual(result.returncode,0)
        self.assertNotIn(PASSWORD,result.stdout+result.stderr)
        return result

    def install(self):
        self.run_hook("preinst")
        self.run_hook("postinst")
        return self.state/"runtime"

    def test_syntax_and_password_validation_has_no_side_effects(self):
        executable = [SHELL,"sh"] if "busybox" in Path(SHELL).name.lower() else [SHELL]
        for script in [*(ROOT/"synology/scripts").iterdir(),ROOT/"synology/package-lib.sh",ROOT/"synology/ui/dsm-login.cgi"]:
            result=subprocess.run([*executable,"-n",str(script)],capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stderr)
        self.run_hook("preinst")
        self.assertEqual(list(self.state.iterdir()),[])
        for password,confirmation in [("short","short"),("long-enough-password","different"),(" leading-space-long-password"," leading-space-long-password"),("many\nlines-long-password","many\nlines-long-password"),("ž"*13,"ž"*13)]:
            env=dict(self.env,wizard_admin_password=password,wizard_admin_password_confirm=confirmation)
            self.run_hook("preinst",success=False,env=env)
        self.assertEqual(list(self.state.iterdir()),[])

    def test_service_status_and_start_only_accept_our_http_health_marker(self):
        self.install()
        response={"code":200,"body":b'{"application":"MediaGrabber NAS","status":"ok"}'}
        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                self.send_response(response["code"])
                self.send_header("Content-Length",str(len(response["body"])))
                self.end_headers()
                self.wfile.write(response["body"])
            def log_message(self,*args):
                pass
        server=ThreadingHTTPServer(("127.0.0.1",0),Handler)
        thread=threading.Thread(target=server.serve_forever,daemon=True)
        thread.start()
        env=dict(self.env,MG_SPK_HEALTH_URL=f"http://127.0.0.1:{server.server_port}/healthz")
        try:
            self.run_hook("start-stop-status","status",env=env)
            self.run_hook("start-stop-status","start",env=env)
            response["body"]=b'{"application":"Other server"}'
            self.assertEqual(self.run_hook("start-stop-status","status",env=env,success=False).returncode,3)
            response["code"]=503
            self.assertEqual(self.run_hook("start-stop-status","status",env=env,success=False).returncode,3)
            self.run_hook("start-stop-status","stop",env=env)
            self.assertTrue((self.state/"runtime/secrets/admin_password").exists())
        finally:
            server.shutdown();server.server_close();thread.join(3)

    def test_install_automatic_ids_secret_safe_compose_and_prestart(self):
        runtime=self.install()
        bridge_key = (runtime/"secrets/dsm_bridge_key").read_bytes()
        self.assertRegex(bridge_key.decode(), r"^[a-f0-9]{64}$")
        self.assertEqual((runtime/"secrets/admin_password").read_text("utf-8"),PASSWORD+"\n")
        self.assertEqual((runtime/"schema").read_text().strip(),"1")
        import yaml
        compose=yaml.safe_load((self.target/"docker/compose.yaml").read_text())
        service=compose["services"]["mediagrabber"]
        self.assertEqual(service["user"],"0:0")
        self.assertEqual(service["entrypoint"],["python","-m","mg_nas.container_entrypoint"])
        self.assertNotIn(PASSWORD,(self.target/"docker/compose.yaml").read_text())
        self.assertTrue(service["read_only"])
        self.assertEqual(service["cap_drop"],["ALL"])
        self.assertEqual((self.target/"docker/compose.yaml").read_text(),self.initial_compose)
        self.assertEqual(service["volumes"][0]["source"],"state")
        self.assertEqual(service["volumes"][1]["target"],"/run/secrets")
        self.assertTrue(service["volumes"][1]["read_only"])
        self.assertEqual(compose["volumes"]["media"]["driver_opts"]["device"],"/var/packages/MediaGrabberNAS/shares/MediaGrabber")
        self.assertEqual((runtime/"settings.env").read_bytes(),(runtime/"secrets/runtime.env").read_bytes())
        self.run_hook("start-stop-status","prestart")
        self.share.rmdir()
        # Prestart only checks private state; data-share is acquired on enable.
        self.run_hook("start-stop-status","prestart")
        self.run_hook("start-stop-status","start",success=False)

    def test_upgrade_replaces_code_preserves_sqlite_settings_password_and_backup(self):
        runtime=self.install()
        bridge_key = (runtime/"secrets/dsm_bridge_key").read_bytes()
        db=sqlite3.connect(runtime/"data/mediagrabber.sqlite3")
        db.execute("CREATE TABLE history(title TEXT)")
        db.execute("INSERT INTO history VALUES('Preserved track')")
        db.commit();db.close()
        (runtime/"data/mediagrabber.sqlite3-wal").write_bytes(b"leftover WAL fixture")
        old_db=(runtime/"data/mediagrabber.sqlite3").read_bytes()
        (runtime/"settings.env").write_text("PUID=4095\nPGID=4095\nMG_PORT=8787\nMG_SECURE_COOKIE=1\nMG_ALLOWED_HOSTS=nas.local\n")
        (self.share/"existing-song.mp3").write_bytes(b"existing media unchanged")
        env=dict(self.env,SYNOPKG_PKG_STATUS="UPGRADE")
        env.pop("wizard_admin_password");env.pop("wizard_admin_password_confirm")
        self.run_hook("preupgrade",env=env)
        self.run_hook("preuninst",env=env)
        self.run_hook("postuninst",env=env)
        # Model replacement of target: runtime lives outside it.
        original=self.target
        replacement=self.root/"new-target"
        (replacement/"installer").mkdir(parents=True)
        shutil.copyfile(ROOT/"synology/package-lib.sh",replacement/"installer/package-lib.sh")
        (replacement/"SPK_VERSION").write_text("0.1.0-0003\n")
        (replacement/"docker").mkdir()
        (replacement/"docker/compose.yaml").write_text((ROOT/"synology/compose.yaml").read_text().replace("__SPK_VERSION__","0.1.0-0003"))
        env["SYNOPKG_PKGDEST"]=replacement.as_posix()
        self.run_hook("preinst",env=env)
        self.run_hook("postinst",env=env)
        self.run_hook("postupgrade",env=env)
        self.assertEqual((runtime/"data/mediagrabber.sqlite3").read_bytes(),old_db)
        self.assertEqual((runtime/"secrets/dsm_bridge_key").read_bytes(),bridge_key)
        self.assertEqual((runtime/"secrets/admin_password").read_text("utf-8"),PASSWORD+"\n")
        self.assertIn("MG_SECURE_COOKIE=1",(runtime/"settings.env").read_text())
        self.assertIn("MG_ALLOWED_HOSTS=nas.local",(runtime/"settings.env").read_text())
        self.assertIn("spk-0.1.0-0003",(replacement/"docker/compose.yaml").read_text())
        backups=list((runtime/"backups").glob("*.tar.gz"))
        self.assertEqual(len(backups),1)
        with tarfile.open(backups[0],"r:gz") as tar:
            self.assertEqual(tar.extractfile("data/mediagrabber.sqlite3").read(),old_db)
            self.assertEqual(tar.extractfile("data/mediagrabber.sqlite3-wal").read(),b"leftover WAL fixture")
            self.assertEqual(tar.extractfile("secrets/admin_password").read().decode(),PASSWORD+"\n")
            self.assertFalse(any(n.endswith(".mp3") for n in tar.getnames()))
        self.assertEqual((self.share/"existing-song.mp3").read_bytes(),b"existing media unchanged")

    def test_upgrade_from_pre_bridge_build_creates_private_key(self):
        runtime = self.install()
        (runtime/"secrets/dsm_bridge_key").unlink()  # isolated fixture: model 0014
        password = (runtime/"secrets/admin_password").read_bytes()
        env = dict(self.env, SYNOPKG_PKG_STATUS="UPGRADE")
        env.pop("wizard_admin_password")
        env.pop("wizard_admin_password_confirm")
        self.run_hook("preupgrade", env=env)
        self.run_hook("postinst", env=env)
        self.assertRegex((runtime/"secrets/dsm_bridge_key").read_text(), r"^[a-f0-9]{64}$")
        self.assertEqual((runtime/"secrets/admin_password").read_bytes(), password)

    def test_unsupported_state_rejected_without_rewriting_data(self):
        runtime=self.install()
        (runtime/"schema").write_text("999\n")
        before=(runtime/"secrets/admin_password").read_bytes()
        env=dict(self.env,SYNOPKG_PKG_STATUS="UPGRADE")
        self.run_hook("preupgrade",env=env,success=False)
        self.run_hook("postinst",env=env,success=False)
        self.assertEqual((runtime/"secrets/admin_password").read_bytes(),before)
        self.assertFalse((runtime/"backups").exists())

    def test_uninstall_retains_state_and_media_and_reinstall_can_reset_password(self):
        runtime=self.install()
        (self.share/"track.mp3").write_bytes(b"media")
        self.run_hook("preuninst",env=dict(self.env,SYNOPKG_PKG_STATUS="UNINSTALL"))
        self.run_hook("postuninst",env=dict(self.env,SYNOPKG_PKG_STATUS="UNINSTALL"))
        self.assertTrue((runtime/"schema").exists())
        self.assertTrue((runtime/"secrets/admin_password").exists())
        self.assertTrue((self.share/"track.mp3").exists())
        changed="replacement-password-9912"
        env=dict(self.env,wizard_admin_password=changed,wizard_admin_password_confirm=changed)
        self.run_hook("preinst",env=env)
        self.run_hook("postinst",env=env)
        self.assertEqual((runtime/"secrets/admin_password").read_text().strip(),changed)

    def test_native_resource_can_read_compose_before_postinst_exists(self):
        import yaml
        self.run_hook("preinst")
        self.assertFalse((self.state/"runtime").exists())
        # DSM WHEN_POSTINST acquires the project before postinst prepares state.
        compose=yaml.safe_load((self.target/"docker/compose.yaml").read_text())
        self.assertEqual(compose["services"]["mediagrabber"]["build"]["context"],".")
        self.assertTrue(all(v["type"]=="volume" and v["volume"]["nocopy"] for v in compose["services"]["mediagrabber"]["volumes"]))
        before=(self.target/"docker/compose.yaml").read_bytes()
        self.run_hook("postinst")
        self.assertEqual(before,(self.target/"docker/compose.yaml").read_bytes())

    def test_explicit_uninstall_erases_only_private_runtime(self):
        runtime=self.install()
        (self.share/"track.mp3").write_bytes(b"media")
        env=dict(self.env,SYNOPKG_PKG_STATUS="UNINSTALL",wizard_remove_private_data="yes")
        self.run_hook("postuninst",env=env)
        self.assertFalse(runtime.exists())
        self.assertEqual((self.share/"track.mp3").read_bytes(),b"media")
        self.assertTrue(self.state.exists())

    def test_postuninst_works_after_dsm_has_removed_the_payload(self):
        runtime = self.install()
        (self.share/"track.mp3").write_bytes(b"media")
        # Actual DSM order in the pilot log: remove target, then postuninst.
        shutil.rmtree(self.target)
        for status, flag in [("UPGRADE", "yes"), ("UNINSTALL", "no")]:
            self.run_hook("postuninst", env=dict(self.env, SYNOPKG_PKG_STATUS=status, wizard_remove_private_data=flag))
            self.assertTrue((runtime/"schema").is_file())
            self.assertTrue((runtime/"secrets/admin_password").is_file())
        self.run_hook("postuninst", env=dict(self.env, SYNOPKG_PKG_STATUS="UNINSTALL", wizard_remove_private_data="yes"))
        self.assertFalse(runtime.exists())
        self.assertEqual((self.share/"track.mp3").read_bytes(), b"media")

    def test_upgrade_and_invalid_erasure_flag_never_erase(self):
        runtime=self.install()
        for status,flag in [("UPGRADE","yes"),("INSTALL","yes"),("UNINSTALL","true")]:
            self.run_hook("postuninst",env=dict(self.env,SYNOPKG_PKG_STATUS=status,wizard_remove_private_data=flag))
            self.assertTrue((runtime/"secrets/admin_password").is_file())

    def test_private_erasure_refuses_overlap_and_unrecognized_state(self):
        runtime=self.install()
        env=dict(self.env,SYNOPKG_PKG_STATUS="UNINSTALL",wizard_remove_private_data="yes",MG_SPK_SHARE_PATH=str(runtime))
        self.run_hook("postuninst",env=env,success=False)
        self.assertTrue((runtime/"secrets/admin_password").is_file())
        (runtime/"schema").write_text("unknown\n")
        self.run_hook("postuninst",env=dict(self.env,SYNOPKG_PKG_STATUS="UNINSTALL",wizard_remove_private_data="yes"),success=False)
        self.assertTrue(runtime.exists())


if __name__=="__main__":
    unittest.main()
