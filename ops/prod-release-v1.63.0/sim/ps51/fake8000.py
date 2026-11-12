"""RT12 PowerShell 5.1 sim - a stand-in for Michael's :8000 so block B (local/check_8000.ps1) is proven without his
server (it is his; it was down on 12 Nov). Standard library only. Serves, READ ONLY, from the clone it is given:

    python -I fake8000.py <port> <clone dir> <version file>

  /health/version                 {"version": <the file's one line>, "environment": "unset"} - re-read per request, so
                                  the sim flips it between v1.62.0 (block B must STOP [VERSION]) and v1.63.0 (DONE)
  /static/js/<name>?v=N           <clone>/backend/app/static/js/<name>        (the ?v= is ignored, as uvicorn's StaticFiles does)
  /mes-app/assets/<bundle>        <clone>/frontend/dist/assets/<bundle>
Anything else is 404. Binds 127.0.0.1 only.
"""
from __future__ import annotations

import json
import sys
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import urlsplit

PORT, CLONE, VERSION_FILE = int(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3])


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *_):   # quiet
        pass

    def _send(self, code: int, body: bytes, ctype: str) -> None:
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        path = urlsplit(self.path).path
        if path == "/health/version":
            v = VERSION_FILE.read_text(encoding="ascii").strip()
            return self._send(200, json.dumps({"version": v, "environment": "unset"}, separators=(",", ":")).encode(), "application/json")
        root = None
        if path.startswith("/static/js/") and "/" not in path[len("/static/js/"):]:
            root, name = CLONE / "backend" / "app" / "static" / "js", path[len("/static/js/"):]
        elif path.startswith("/mes-app/assets/") and "/" not in path[len("/mes-app/assets/"):]:
            root, name = CLONE / "frontend" / "dist" / "assets", path[len("/mes-app/assets/"):]
        if root is None or not name or name.startswith("."):
            return self._send(404, b"not found", "text/plain")
        f = root / name
        if not f.is_file():
            return self._send(404, b"not found", "text/plain")
        return self._send(200, f.read_bytes(), "application/javascript")


if __name__ == "__main__":
    HTTPServer(("127.0.0.1", PORT), Handler).serve_forever()
