# SPDX-License-Identifier: GPL-3.0-or-later
"""Build an unsigned DSM 7.2.2+ SPK, without a Docker daemon or a Synology SDK.

The native Container Manager worker builds the bundled Dockerfile on the NAS.
Keep PACKAGE_ID fixed and increase --build for every release.
"""
from __future__ import annotations

import argparse
import gzip
import hashlib
import io
import json
import re
import tarfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PACKAGE_ID = "MediaGrabberNAS"
FEATURE_VERSION = "0.1.0"
DEFAULT_BUILD = 24
EPOCH = 1794614400  # deterministic artifact timestamps, 2026-11-14 UTC


def add(tar, name, data, mode=0o644):
    item = tarfile.TarInfo(name)
    item.size, item.mode, item.mtime = len(data), mode, EPOCH
    item.uid = item.gid = 0
    item.uname = item.gname = "root"
    tar.addfile(item, io.BytesIO(data))


def text(path):
    return path.read_text("utf-8-sig").replace("\r\n", "\n").encode("utf-8")


def application_version(version):
    return version.rsplit("-",1)[0] + "-beta." + str(int(version.rsplit("-",1)[1]))


def versioned_module(data, version):
    return re.sub(rb'__version__ = "[^"]+"', ('__version__ = "'+application_version(version)+'"').encode(), data)


def source_archive(version=None):
    """Only the maintained source tree, never runtime/user state or build outputs."""
    allowed = {"mg_nas", "synology", "tools", "tests", "LICENSES", "vendor-sources", ".github"}
    root_files = {"LICENSE", "COPYRIGHT", "PRIVACY.md", "THIRD-PARTY-NOTICES.md", "README.md", "CHANGELOG.md", "VERSION", "requirements.txt", "requirements-linux.lock", "requirements-dev.txt", "Dockerfile", "compose.yaml", ".dockerignore", ".gitignore", ".env.example"}
    stream = io.BytesIO()
    with gzip.GzipFile(fileobj=stream, mode="wb", mtime=0, filename="") as gz:
        with tarfile.open(fileobj=gz, mode="w", format=tarfile.PAX_FORMAT) as tar:
            for path in sorted(ROOT.rglob("*")):
                rel = path.relative_to(ROOT)
                if path.is_symlink() or not path.is_file() or "__pycache__" in rel.parts or path.suffix == ".pyc":
                    continue
                if not (len(rel.parts) == 1 and rel.name in root_files or rel.parts[0] in allowed):
                    continue
                if any(p in {".git", ".env", "data", "downloads", "secrets"} for p in rel.parts) or rel.name == "release-state.json":
                    continue
                data = path.read_bytes()
                if version and rel.as_posix() == "mg_nas/__init__.py":data = versioned_module(data,version)
                if version and rel.as_posix() == "VERSION":data = (application_version(version)+"\n").encode()
                add(tar, "MediaGrabber-NAS/" + rel.as_posix(), data, 0o755 if path.suffix == ".sh" else 0o644)
    return stream.getvalue()


def payload_files(version):
    files = {
        "SPK_VERSION": (version + "\n").encode(),
        "installer/package-lib.sh": text(ROOT/"synology/package-lib.sh"),
        "nginx/portal.conf": text(ROOT/"synology/nginx/portal.conf"),
        "docker/Dockerfile": text(ROOT/"Dockerfile"),
        "docker/requirements.txt": text(ROOT/"requirements.txt"),
        "docker/requirements-linux.lock": text(ROOT/"requirements-linux.lock"),
        "docker/tools/runtime_inventory.py": text(ROOT/"tools/runtime_inventory.py"),
        "docker/THIRD-PARTY-NOTICES.md": text(ROOT/"THIRD-PARTY-NOTICES.md"),
        "docker/compose.yaml": text(ROOT/"synology/compose.yaml").replace(b"__SPK_VERSION__", version.encode("ascii")),
        "THIRD-PARTY-NOTICES.md": text(ROOT/"THIRD-PARTY-NOTICES.md"),
        "docker/SOURCE.tar.gz": source_archive(version),
    }
    for name in ["LICENSE", "COPYRIGHT", "PRIVACY.md"]:
        files[name] = files["docker/" + name] = text(ROOT/name)
    for path in sorted((ROOT/"LICENSES").iterdir()):
        if path.is_file():
            files["docker/LICENSES/" + path.name] = files["LICENSES/" + path.name] = path.read_bytes()
    for path in (ROOT/"mg_nas").rglob("*"):
        if path.is_file() and "__pycache__" not in path.parts and path.suffix != ".pyc":
            name = "docker/" + path.relative_to(ROOT).as_posix()
            files[name] = text(path) if path.suffix in {".py", ".js", ".css", ".html"} else path.read_bytes()
    for path in (ROOT/"synology/ui").rglob("*"):
        if path.is_file():
            files["ui/"+path.relative_to(ROOT/"synology/ui").as_posix()] = text(path) if path.suffix == ".cgi" else path.read_bytes()
    files["docker/mg_nas/__init__.py"] = versioned_module(files["docker/mg_nas/__init__.py"],version)
    files["BUILD-MANIFEST.json"] = json.dumps({"package":PACKAGE_ID,"version":version,"files":{name:hashlib.sha256(data).hexdigest() for name,data in sorted(files.items())}},indent=2).encode()+b"\n"
    return files


def wizard(kind, czech, offline=False):
    code = (ROOT/"synology/wizard-runtime.js").read_text("utf-8")
    code = code.replace("__KIND__", json.dumps(kind)).replace("__CZECH__", "true" if czech else "false")
    code = code.replace("__OFFLINE__", "true" if offline else "false")
    return json.dumps([{"custom_render_fn":code,"custom_render_name":"mediagrabber_"+kind}],ensure_ascii=False).encode()+b"\n"


def validate_image(path, version):
    expected = "pjsoft/mediagrabber-nas:spk-" + version
    with tarfile.open(path, "r:*") as image:
        manifests = json.load(image.extractfile("manifest.json"))
        if not isinstance(manifests, list) or len(manifests) != 1 or expected not in manifests[0].get("RepoTags", []):
            raise ValueError("Offline image must contain exactly the expected versioned image tag.")
        config_name = manifests[0]["Config"]
        if not isinstance(config_name, str) or config_name.startswith("/") or ".." in config_name.split("/"):
            raise ValueError("Unsafe image configuration path.")
        data = image.extractfile(config_name).read()
        config = json.loads(data)
        labels = config.get("config", {}).get("Labels", {})
        if config.get("architecture") != "amd64" or config.get("os") != "linux" or labels.get("org.opencontainers.image.version") != version:
            raise ValueError("Offline image architecture, operating system or version label is invalid.")
        return hashlib.sha256(data).hexdigest()


def build_spk(output_dir: Path, build=DEFAULT_BUILD, offline_image=None, runtime_sources=None):
    # Keep the minimal privilege declaration accepted by the physical pilot.
    # CGI mode 0755 is set in the payload; no per-executable privilege request.
    privilege = json.loads(text(ROOT/"synology/conf/privilege"))
    if privilege != {"defaults":{"run-as":"package"},"username":"mg-nas","groupname":"mg-nas"}:
        raise ValueError("DSM package privileges must retain the minimal mg-nas package-account declaration.")
    if type(build) is not int or not 1 <= build < 2**31:
        raise ValueError("Build must be a positive integer; never reuse a published build number")
    version = FEATURE_VERSION + "-" + str(build).zfill(4)
    assert re.fullmatch(r"\d+\.\d+\.\d+-\d+", version)
    files = payload_files(version)
    if offline_image:
        image_id = validate_image(offline_image, version)
        if not runtime_sources or not runtime_sources.is_file():
            raise ValueError("Offline releases require the matching runtime source archive.")
        with tarfile.open(runtime_sources, "r:*") as sources:
            evidence = json.load(sources.extractfile("RUNTIME-SOURCE-MANIFEST.json"))
        if evidence.get("image_config_sha256") != image_id or evidence.get("version") != version:
            raise ValueError("Runtime sources do not match the offline image.")
        # Use the saved image only. Container Manager must not pull or build online.
        compose = files["docker/compose.yaml"].decode().replace("    build:\n      context: .\n", "    pull_policy: never\n")
        files["docker/compose.yaml"] = compose.encode()
        # DSM resolves preload-image relative to the installed target. Only
        # package.tgz is extracted there; the outer SPK is installer metadata.
        files["image.tar.gz"] = offline_image.read_bytes()
        files["OFFLINE-IMAGE.json"] = json.dumps({"image_config_sha256":image_id,
            "image_archive_sha256":hashlib.sha256(offline_image.read_bytes()).hexdigest(),
            "runtime_sources":runtime_sources.name,"runtime_sources_sha256":hashlib.sha256(runtime_sources.read_bytes()).hexdigest()}).encode()
        manifest = json.loads(files["BUILD-MANIFEST.json"])
        manifest["files"] = {name:hashlib.sha256(data).hexdigest() for name,data in sorted(files.items()) if name != "BUILD-MANIFEST.json"}
        files["BUILD-MANIFEST.json"] = json.dumps(manifest, indent=2).encode()+b"\n"
    stream = io.BytesIO()
    with gzip.GzipFile(fileobj=stream,mode="wb",mtime=0,filename="",compresslevel=9) as gz:
        with tarfile.open(fileobj=gz,mode="w",format=tarfile.USTAR_FORMAT) as tar:
            for name, data in sorted(files.items()):
                add(tar, name, data, 0o755 if name.endswith(".cgi") else 0o644)
    package = stream.getvalue()
    info = {
        "package":PACKAGE_ID,"version":version,"arch":"x86_64","os_min_ver":"7.2.2-72806",
        "maintainer":"PJSoft","displayname":"MediaGrabber NAS",
        "description":"Test beta: video/audio downloads and watched YouTube sources. Automatic Container Manager setup; settings and history retained on upgrade.",
        "description_csy":"Testovací beta: stahování videa/zvuku a sledování zdrojů YouTube. Automatické nastavení Container Manageru; aktualizace zachová historii a nastavení.",
        "maintainer_url":"https://github.com/petrjones/MediaGrabber-NAS",
        "install_dep_packages":"ContainerManager>=20.10.23-1437",
        "install_type":"volume","startable":"yes","ctl_stop":"yes","ctl_uninstall":"yes",
        "precheckstartstop":"yes",
        "instuninst_restart_services":"nginx.service","startstop_restart_services":"nginx.service",
        "dsmuidir":"ui","dsmappname":"SYNO.SDS.App.MediaGrabberNAS.Instance",
        "beta":"yes","checksum":hashlib.md5(package).hexdigest(),
    }
    content = "".join(f'{key}="{value}"\n' for key,value in info.items()).encode("utf-8")
    output_dir.mkdir(parents=True,exist_ok=True)
    result = output_dir/f"MediaGrabber-NAS-{version}.spk"
    spk_stream = io.BytesIO()
    with tarfile.open(fileobj=spk_stream,mode="w",format=tarfile.USTAR_FORMAT) as tar:
        add(tar,"INFO",content)
        add(tar,"package.tgz",package)
        for name,size in [("PACKAGE_ICON.PNG",64),("PACKAGE_ICON_256.PNG",256)]:
            add(tar,name,(ROOT/f"synology/ui/images/mediagrabber_{size}.png").read_bytes())
        for path in sorted((ROOT/"synology/conf").iterdir()):
            content = text(path)
            if offline_image and path.name == "resource":
                resource = json.loads(content)
                resource["docker-project"]["preload-image"] = "image.tar.gz"
                for project in resource["docker-project"]["projects"]:
                    project["build_params"].update(build=False, force_pull=False)
                content = json.dumps(resource, indent=2).encode()+b"\n"
            add(tar,"conf/"+path.name,content)
        for path in sorted((ROOT/"synology/scripts").iterdir()):
            add(tar,"scripts/"+path.name,text(path),0o755)
        for kind in ["install","upgrade","uninstall"]:
            add(tar,f"WIZARD_UIFILES/{kind}_uifile",wizard(kind,False,bool(offline_image)))
            add(tar,f"WIZARD_UIFILES/{kind}_uifile_csy",wizard(kind,True,bool(offline_image)))
    artifact = spk_stream.getvalue()
    if result.exists() and result.read_bytes() != artifact:
        raise ValueError(f"{result.name} already exists with different contents. Increase --build; never overwrite a delivered SPK.")
    result.write_bytes(artifact)
    digest = hashlib.sha256(artifact).hexdigest()
    result.with_suffix(".spk.sha256").write_text(digest+"  "+result.name+"\n","ascii")
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--build",type=int,default=DEFAULT_BUILD)
    parser.add_argument("--output",type=Path,default=ROOT.parent/"outputs")
    parser.add_argument("--offline-image",type=Path)
    parser.add_argument("--runtime-sources",type=Path)
    args = parser.parse_args()
    output = build_spk(args.output,args.build,args.offline_image,args.runtime_sources)
    print(json.dumps({"path":str(output),"bytes":output.stat().st_size,"sha256":hashlib.sha256(output.read_bytes()).hexdigest()}))
