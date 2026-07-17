"""Local read-only HTTP server for the reasoning visualizer."""

from __future__ import annotations

from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import mimetypes
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlparse


STATIC_ROOT = Path(__file__).resolve().parent / "static"


class VisualizerRequestHandler(BaseHTTPRequestHandler):
    snapshot: dict[str, Any] = {}
    static_root: Path = STATIC_ROOT

    def do_GET(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler API
        parsed = urlparse(self.path)
        if parsed.path == "/api/health":
            self._send_json({"status": "ok", "schema_version": self.snapshot.get("schema_version")})
            return
        if parsed.path == "/api/snapshot":
            self._send_json(self.snapshot)
            return
        self._send_static(parsed.path)

    def do_POST(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler API
        self.send_error(HTTPStatus.METHOD_NOT_ALLOWED, "read-only server")

    def log_message(self, format: str, *args: Any) -> None:
        return

    def _send_json(self, payload: Any) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(body)

    def _send_static(self, request_path: str) -> None:
        relative = unquote(request_path).lstrip("/") or "index.html"
        candidate = (self.static_root / relative).resolve()
        root = self.static_root.resolve()
        if candidate != root and root not in candidate.parents:
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        if not candidate.is_file():
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        body = candidate.read_bytes()
        content_type = mimetypes.guess_type(candidate.name)[0] or "application/octet-stream"
        if content_type.startswith("text/") or content_type in {"application/javascript", "application/json"}:
            content_type += "; charset=utf-8"
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Content-Security-Policy", "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self'")
        self.end_headers()
        self.wfile.write(body)


def create_server(
    snapshot: dict[str, Any],
    host: str = "127.0.0.1",
    port: int = 8765,
    static_root: str | Path | None = None,
) -> ThreadingHTTPServer:
    if host not in {"127.0.0.1", "localhost", "::1"}:
        raise ValueError("the visualizer is intentionally restricted to localhost")

    handler = type(
        "BoundVisualizerRequestHandler",
        (VisualizerRequestHandler,),
        {
            "snapshot": snapshot,
            "static_root": Path(static_root) if static_root else STATIC_ROOT,
        },
    )
    return ThreadingHTTPServer((host, port), handler)
