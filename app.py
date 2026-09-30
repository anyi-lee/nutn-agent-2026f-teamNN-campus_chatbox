"""Dependency-free local web server for the campus chatbot UI."""

from __future__ import annotations

import json
import sys
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any


REPOSITORY_ROOT = Path(__file__).resolve().parent
UI_ROOT = REPOSITORY_ROOT / "ui"
sys.path.insert(0, str(REPOSITORY_ROOT / "src"))

from campus_service import CampusService  # noqa: E402


SERVICE = CampusService()


class CampusRequestHandler(SimpleHTTPRequestHandler):
    """Serve the static UI and its two JSON endpoints."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, directory=str(UI_ROOT), **kwargs)

    def end_headers(self) -> None:
        self.send_header("Cache-Control", "no-store")
        super().end_headers()

    def _send_json(self, payload: Any, status: int = 200) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _read_json(self) -> dict[str, Any]:
        length = int(self.headers.get("Content-Length", "0"))
        if length <= 0 or length > 1_000_000:
            raise ValueError("Invalid request size")
        payload = json.loads(self.rfile.read(length).decode("utf-8"))
        if not isinstance(payload, dict):
            raise ValueError("JSON body must be an object")
        return payload

    def do_GET(self) -> None:  # noqa: N802
        if self.path == "/api/config":
            self._send_json(SERVICE.config())
            return
        if self.path == "/":
            self.path = "/index.html"
        super().do_GET()

    def do_POST(self) -> None:  # noqa: N802
        try:
            payload = self._read_json()
            if self.path == "/api/chat":
                response = SERVICE.chat(
                    str(payload.get("message", "")),
                    str(payload.get("retriever", "bm25")),
                    str(payload.get("context_teacher") or "") or None,
                )
                self._send_json(response)
                return
            if self.path == "/api/email-draft":
                status, response = SERVICE.create_email_draft(payload)
                self._send_json(response, status)
                return
            self._send_json(
                {"error": {"code": "NOT_FOUND"}}, HTTPStatus.NOT_FOUND
            )
        except (ValueError, json.JSONDecodeError) as error:
            self._send_json(
                {"error": {"code": "BAD_REQUEST", "message": str(error)}},
                HTTPStatus.BAD_REQUEST,
            )
        except Exception:
            self._send_json(
                {"error": {"code": "INTERNAL_ERROR", "message": "伺服器處理失敗。"}},
                HTTPStatus.INTERNAL_SERVER_ERROR,
            )


def run(host: str = "127.0.0.1", port: int = 8000) -> None:
    server = ThreadingHTTPServer((host, port), CampusRequestHandler)
    print(f"Campus Chatbot UI: http://{host}:{port}")
    print("Press Ctrl+C to stop")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    run()
