"""Cross-platform checks of the SPK bootstrap's fail-closed privilege contract.

Actual Linux identity/capability syscalls still require the NAS/container pilot.
"""
import json
import os
import stat
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from mg_nas import container_entrypoint as entry


class BootstrapTests(unittest.TestCase):
    def test_mount_identity_rejects_root_and_files(self):
        def path(uid,gid,mode=stat.S_IFDIR):
            return SimpleNamespace(stat=lambda:SimpleNamespace(st_uid=uid,st_gid=gid,st_mode=mode))
        self.assertEqual(entry.mounted_identity(path(1234,5678)),(1234,5678))
        self.assertEqual(entry.mounted_identity(path(1234,0)),(1234,1234))
        for value in [path(0,100),path(1234,5678,stat.S_IFREG)]:
            with self.assertRaises(RuntimeError): entry.mounted_identity(value)

    def test_all_real_effective_saved_ids_dropped_before_application(self):
        state={"uid":(0,0,0),"gid":(0,0,0)};calls=[]
        system=SimpleNamespace(geteuid=lambda:0,setgroups=lambda groups:calls.append(("groups",groups)),
            setresgid=lambda *ids:(calls.append(("gid",ids)),state.update(gid=ids)),
            setresuid=lambda *ids:(calls.append(("uid",ids)),state.update(uid=ids)),
            getresuid=lambda:state["uid"],getresgid=lambda:state["gid"])
        entry.drop_identity(1234,5678,system)
        self.assertEqual(calls,[("groups",[]),("gid",(5678,5678,5678)),("uid",(1234,1234,1234))])
        system.getresuid=lambda:(1234,1234,0)
        with self.assertRaises(RuntimeError): entry.drop_identity(1234,5678,system)
        with self.assertRaises(RuntimeError): entry.drop_identity(0,100,system)

    def test_no_effective_capability_or_privilege_regain_allowed(self):
        self.assertTrue(entry.kernel_is_unprivileged("CapEff:\t0000000000000000\nNoNewPrivs:\t1\n"))
        for text in ["", "CapEff: 80\nNoNewPrivs: 1", "CapEff: 0\nNoNewPrivs: 0"]:
            self.assertFalse(entry.kernel_is_unprivileged(text))

    def test_older_kernel_without_proc_field_requires_verified_prctl_flag(self):
        with patch.object(entry,"no_new_privileges",return_value=True) as check:
            self.assertTrue(entry.kernel_is_unprivileged("CapEff: 0\n"))
            check.assert_called_once_with()
            check.reset_mock()
            for text in ["CapEff: 80", "CapEff: invalid", "CapEff: 0\nNoNewPrivs: 0", "NoNewPrivs: 1"]:
                self.assertFalse(entry.kernel_is_unprivileged(text))
            check.assert_not_called()
        with patch.object(entry,"no_new_privileges",return_value=False):
            self.assertFalse(entry.kernel_is_unprivileged("CapEff: 0"))

    def test_prctl_getter_uses_typed_zero_arguments_and_fails_closed(self):
        for value in [1,0,-1]:
            prctl=Mock(return_value=value)
            with patch.object(entry.ctypes,"CDLL",return_value=SimpleNamespace(prctl=prctl)):
                self.assertEqual(entry.no_new_privileges(),value==1)
            prctl.assert_called_once_with(39,0,0,0,0)
            self.assertEqual(prctl.argtypes,[entry.ctypes.c_int,*([entry.ctypes.c_ulong]*4)])
        for error in [OSError("unavailable"),AttributeError("no prctl")]:
            with patch.object(entry.ctypes,"CDLL",side_effect=error):
                self.assertFalse(entry.no_new_privileges())

    def test_runtime_file_is_data_not_shell_and_restricts_values(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/"runtime.env"
            path.write_text("PUID=1234\nMG_SECURE_COOKIE=0\nMG_ALLOWED_HOSTS=nas.local,diskstation\nIGNORED=$(touch marker)\n")
            self.assertEqual(entry.runtime_settings(path),{"MG_SECURE_COOKIE":"0","MG_ALLOWED_HOSTS":"nas.local,diskstation"})
            for value in ["MG_SECURE_COOKIE=2", "MG_ALLOWED_HOSTS=$(touch marker)", "MG_SECURE_COOKIE=0\nMG_SECURE_COOKIE=1"]:
                path.write_text(value)
                with self.assertRaises(RuntimeError): entry.runtime_settings(path)
            self.assertFalse((Path(folder)/"marker").exists())

    def test_tini_exec_occurs_after_identity_drop_and_settings_read(self):
        calls=[]
        dockerfile=(Path(__file__).resolve().parents[1]/"Dockerfile").read_text()
        command=json.loads(next(line[4:] for line in dockerfile.splitlines() if line.startswith("CMD ")))
        with patch.dict(os.environ,{},clear=False), patch.object(entry,"mounted_identity",return_value=(1234,5678)), \
             patch.object(entry,"drop_identity",side_effect=lambda *args:calls.append("drop")), \
             patch.object(entry.Path,"read_text",return_value="CapEff: 0\nNoNewPrivs: 1"), \
             patch.object(entry,"runtime_settings",side_effect=lambda path:(calls.append("settings") or {})), \
             patch.object(entry.sys,"argv",["bootstrap",*command]), \
             patch.object(entry.os,"execv",side_effect=lambda path,args:calls.append((path,args))):
            entry.main()
        self.assertEqual(calls,["drop","settings",("/usr/bin/tini",["/usr/bin/tini","--",*command])])


if __name__=="__main__": unittest.main()
