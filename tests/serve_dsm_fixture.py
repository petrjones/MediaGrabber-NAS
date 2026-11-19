"""Loopback-only development fixture; native DSM identity is NOT emulated."""
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from wsgiref.simple_server import make_server

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from mg_nas.app import App
from mg_nas.__main__ import ThreadedServer
from test_service import FakeEngine, PASSWORD

with tempfile.TemporaryDirectory(prefix="mg-dsm-browser-") as temp:
    root = Path(temp)
    app = App(root/"data", root/"downloads", PASSWORD, engine=FakeEngine(), start_worker=False, dsm_key="a"*64)
    ui = Path(__file__).resolve().parents[1]/"synology/ui"
    key = root/"dsm_bridge_key"
    key.write_text("a"*64)
    script = root/"dsm-login.cgi"
    source = (ui/"dsm-login.cgi").read_text("utf-8").replace(
        "/var/packages/MediaGrabberNAS/var/runtime/secrets/dsm_bridge_key", key.as_posix()).replace('"$syno_auth" &', 'fixture_auth &')
    source = source.replace("export PATH", "export PATH\n" + r'''
fixture_auth() {
    case "${HTTP_COOKIE:-}" in *'id=fixture-private-dsm-cookie'*) ;; *) return 7 ;; esac
    [ "${HTTP_X_SYNO_TOKEN:-}" = fixture-dsm-token ] || return 7
    [ "${QUERY_STRING:-}" = SynoToken=fixture-dsm-token ] || return 7
    printf Petr
}
id() { printf 'users administrators'; }
curl() { "$FIXTURE_CURL" "$@"; }
''')
    script.write_text(source,"utf-8",newline="\n")

    def reply(respond, status, content, mime="text/html; charset=utf-8"):
        if isinstance(content,str): content=content.encode("utf-8")
        respond(status, [("Content-Type",mime),("Content-Length",str(len(content))),("Cache-Control","no-store")])
        return [content]

    def fixture(env, respond):
        path = env["PATH_INFO"]
        if path == "/fixture/native-host":
            mode = env.get("QUERY_STRING", "")
            token = "" if mode in {"missing", "session"} else ("stale-token" if mode == "current" else "fixture-dsm-token")
            session = "{SynoToken:'fixture-dsm-token'}" if mode in {"session","current"} else "{}"
            return reply(respond,"200 OK",'''<!doctype html><meta charset="utf-8"><div id="native-app"></div>
<script src="/mediagrabber/fixture/vue.js"></script><script>
window.SYNO={SDS:{Session:''' + session + '''},namespace:function(name){var target=window;name.split('.').forEach(function(part){target=target[part]||(target[part]={});});}};
Vue.component('v-app-instance',{render:function(h){return h('div',{style:{height:'850px'}},this.$slots.default);}});
Vue.component('v-app-window',{render:function(h){return h('div',{style:{height:'100%'}},this.$slots.default);}});
</script><script src="/webman/3rdparty/MediaGrabberNAS/MediaGrabber.cgi?SynoToken='''+token+'''" onload="new SYNO.SDS.App.MediaGrabberNAS.Instance().$mount('#native-app')"></script>''')
        if path == "/fixture/vue.js":
            return reply(respond,"200 OK",Path(os.environ["MG_TEST_VUE"]).read_bytes(),"application/javascript")
        if path in {"/webman/3rdparty/MediaGrabberNAS/MediaGrabber.cgi", "/webman/3rdparty/MediaGrabberNAS/dsm-login.cgi"}:
            shell = os.environ["MG_TEST_SHELL"]
            command = [shell,"sh"] if "busybox" in Path(shell).name.lower() else [shell]
            target = ui/"MediaGrabber.cgi" if path.endswith("/MediaGrabber.cgi") else script
            cgi_env = dict(os.environ, FIXTURE_CURL=os.environ["MG_TEST_CURL"])
            cgi_env.update({k:str(v) for k,v in env.items() if k.startswith("HTTP_") or k in {"REQUEST_METHOD","QUERY_STRING","REMOTE_ADDR","REMOTE_PORT","SERVER_ADDR","SERVER_PORT","REQUEST_URI"}})
            result = subprocess.run([*command,str(target)],env=cgi_env,capture_output=True,timeout=10)
            if result.returncode: return reply(respond,"500 Internal Server Error","CGI fixture execution failed.")
            header, body = result.stdout.split(b"\r\n\r\n",1)
            headers = [line.decode().split(":",1) for line in header.split(b"\r\n")]
            status = next((value.strip() for name,value in headers if name.lower()=="status"),"200 OK")
            final = [(name,value.strip()) for name,value in headers if name.lower() not in {"status","content-length"}]
            respond(status,final+[("Content-Length",str(len(body)))])
            return [body]
        if env["PATH_INFO"] == "/fixture/launch":
            token = app.dsm.issue("a"*64)
            respond("303 See Other", [("Location", "/mediagrabber/#dsm-ticket="+token), ("Content-Length", "0")])
            return [b""]
        if env["PATH_INFO"] == "/fixture/received":
            data = json.dumps({"cookie":env.get("HTTP_COOKIE", ""), "authorization":env.get("HTTP_AUTHORIZATION", ""),
                               "portal":env.get("HTTP_X_MG_PORTAL", ""), "key":env.get("HTTP_X_MG_BRIDGE_KEY", "")}).encode()
            respond("200 OK", [("Content-Type","application/json"), ("Content-Length",str(len(data)))])
            return [data]
        return app(env, respond)
    try:
        with make_server("127.0.0.1", 8787, fixture, server_class=ThreadedServer) as server:
            print("DSM_FIXTURE_READY", flush=True)
            server.serve_forever()
    finally:
        app.close()
