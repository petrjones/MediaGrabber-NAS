"""Local-only UI fixture: 125 history records, one queued job, temporary media."""
import json
import os
import sys
import tempfile
import uuid
from pathlib import Path
from wsgiref.simple_server import make_server

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from mg_nas.app import App, source_config
from mg_nas.__main__ import ThreadedServer
from mg_nas.domain import options
from test_service import FakeEngine,PASSWORD,entry

with tempfile.TemporaryDirectory(prefix="mg-history-browser-") as temp:
    root=Path(temp)
    app=App(root/"data",root/"downloads",PASSWORD,engine=FakeEngine(),start_worker=False)
    media=app.downloads/"preserved.mp3";media.write_bytes(b"existing fixture file")
    opts=options({},app.downloads)
    with app.store.tx() as db:
        for i in range(125):
            identifier=f"{i:032x}"
            db.execute("INSERT INTO jobs(id,url,title,options,status,created,updated) VALUES(?,?,?,?,?,?,?)",
                       (identifier,entry()["url"],f"History {i+1:03}",json.dumps(opts),"completed",1700000000,1700000000))
            db.execute("INSERT INTO items(id,job_id,media_id,url,title,position,status,paths) VALUES(?,?,?,?,?,?,?,?)",
                       (uuid.uuid4().hex,identifier,entry()["id"],entry()["url"],"Detailed track",1,"done",json.dumps([str(media)])))
    app.store.add_jobs(app.validate_jobs([{"url":entry()["url"],"options":opts,"title":"Preserved queue"}]))
    config=source_config({"name":"Preserved source","url":"https://www.youtube.com/@TestChannel","options":{}},app.downloads)
    app.store.execute("INSERT INTO sources(id,config,enabled,next_check) VALUES(?,?,1,?)",(uuid.uuid4().hex,json.dumps(config),9999999999))
    def portal_fixture(env,respond):
        # Prefix adapter only; native nginx/DSM behavior is not emulated here.
        if env["PATH_INFO"].startswith("/mediagrabber/"):
            env=dict(env,PATH_INFO=env["PATH_INFO"][len("/mediagrabber"):],HTTP_X_MG_PORTAL="1")
        return app(env,respond)
    try:
        with make_server("127.0.0.1",int(os.environ.get("MG_TEST_PORT","18819")),portal_fixture,server_class=ThreadedServer) as server:
            print("HISTORY_FIXTURE_READY",flush=True)
            server.serve_forever()
    finally:
        app.close()
