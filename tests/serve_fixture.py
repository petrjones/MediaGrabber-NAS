"""Local browser test server; temporary isolated storage, fake download engine."""
import sys
import os
import tempfile
from pathlib import Path
from wsgiref.simple_server import make_server

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from mg_nas.app import App
from mg_nas.__main__ import ThreadedServer
from test_service import FakeEngine, PASSWORD, entry

with tempfile.TemporaryDirectory(prefix="mediagrabber-browser-") as directory:
    root = Path(directory)
    (root/"downloads"/"Music").mkdir(parents=True)
    app = App(root/"data", root/"downloads", PASSWORD, engine=FakeEngine(), start_worker=False)
    try:
        app.store.add_jobs(app.validate_jobs([{"url": entry()["url"], "title": "Ukázková úloha", "entries": [entry()], "options": {}}]))
        with make_server("127.0.0.1", int(os.environ.get("MG_TEST_PORT", "18787")), app, server_class=ThreadedServer) as server:
            print("BROWSER_FIXTURE_READY", flush=True)
            server.serve_forever()
    finally:
        app.close()
