# SPDX-License-Identifier: GPL-3.0-or-later
"""Local development runner. Containers use Gunicorn, never this reference server."""
import argparse
import logging
from socketserver import ThreadingMixIn
from wsgiref.simple_server import WSGIServer, make_server

from .app import create_app


class ThreadedServer(ThreadingMixIn, WSGIServer):
    daemon_threads = True


def main():
    parser = argparse.ArgumentParser(description="MediaGrabber NAS local development server")
    parser.add_argument("--port", type=int, default=8787)
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO)
    app = create_app()
    try:
        with make_server("127.0.0.1", args.port, app, server_class=ThreadedServer) as server:
            print(f"Development only: http://127.0.0.1:{args.port}", flush=True)
            server.serve_forever()
    finally:
        app.close()


if __name__ == "__main__":
    main()
