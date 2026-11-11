"""A tiny, dependency-free web server shared by the codelabs.

Each part supplies a `Part` object:

    part.name                       shown in the page header
    part.web_dir                    its index.html and renderer module
    part.run(mode, prompt)          generator of protocol messages (dicts)
    part.action(mode, body)         generator of protocol messages for a user action

The server streams those messages to the browser as Server-Sent Events
(`data: <json>\\n\\n`), the same wire framing AG-UI uses. The browser
never receives anything the part did not yield, so the part's validation is
the gate between the model and the page.

    GET  /                          the part's index.html
    GET  /common/...                shared front-end files (components, sandbox, shell)
    GET  /api/run?mode=..&prompt=.. SSE stream of the run
    POST /api/action                SSE stream answering a user action
"""

import json
import time
import mimetypes
import sys
import traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

COMMON_WEB = Path(__file__).parent / "web"
MODES = ("static", "declarative", "open_ended", "mixed")


def make_handler(part):
    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, fmt, *args):  # one compact line per request
            sys.stderr.write(f"[{part.name}] {self.command} {self.path.split('?')[0]} {args[1] if len(args) > 1 else ''}\n")

        # -------------------------------------------------- static files
        def _file(self, path):
            if not path.is_file():
                self.send_error(404)
                return
            body = path.read_bytes()
            ctype = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
            if path.suffix == ".mjs":
                ctype = "text/javascript"
            self.send_response(200)
            self.send_header("content-type", ctype + ("; charset=utf-8" if ctype.startswith("text") else ""))
            self.send_header("content-length", str(len(body)))
            self.send_header("cache-control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def _safe(self, root, rel):
            target = (root / rel).resolve()
            return target if str(target).startswith(str(root.resolve())) else root / "__nope__"

        # -------------------------------------------------- SSE
        def _sse(self, messages):
            self.send_response(200)
            self.send_header("content-type", "text/event-stream")
            self.send_header("cache-control", "no-store")
            self.send_header("connection", "close")
            self.end_headers()
            self.close_connection = True
            try:
                for msg in messages:
                    if getattr(part, "pace", 0):
                        time.sleep(part.pace)   # visible streaming for scripted runs
                    self.wfile.write(f"data: {json.dumps(msg)}\n\n".encode())
                    self.wfile.flush()
            except (BrokenPipeError, ConnectionResetError):
                return
            except Exception as error:  # the page must always see a terminal message
                traceback.print_exc()
                self.wfile.write(f"data: {json.dumps({'error': str(error)})}\n\n".encode())

        def do_GET(self):
            url = urlparse(self.path)
            if url.path in ("/", "/index.html"):
                return self._file(part.web_dir / "index.html")
            if url.path.startswith("/common/"):
                return self._file(self._safe(COMMON_WEB, url.path[len("/common/"):]))
            if url.path == "/api/run":
                q = {k: v[0] for k, v in parse_qs(url.query).items()}
                mode = q.get("mode", "declarative")
                if mode not in MODES:
                    return self.send_error(400, f"mode must be one of {MODES}")
                return self._sse(part.run(mode, q.get("prompt") or part.default_prompt))
            if hasattr(part, "get") and part.get(self, url):
                return None
            return self._file(self._safe(part.web_dir, url.path.lstrip("/")))

        def do_POST(self):
            url = urlparse(self.path)
            length = int(self.headers.get("content-length") or 0)
            body = json.loads(self.rfile.read(length) or b"{}")
            if url.path == "/api/action":
                return self._sse(part.action(body.get("mode", "declarative"), body))
            if hasattr(part, "post") and part.post(self, url, body):
                return None
            self.send_error(404)

        def send_json(self, obj, status=200):
            data = json.dumps(obj).encode()
            self.send_response(status)
            self.send_header("content-type", "application/json")
            self.send_header("content-length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

    return Handler


def serve(part, port):
    httpd = ThreadingHTTPServer(("127.0.0.1", port), make_handler(part))
    print(f"{part.name}: open http://127.0.0.1:{port}  (Ctrl+C to stop)", flush=True)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
