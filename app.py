"""Dependency-free local web server for the campus chatbot UI."""

from __future__ import annotations

import json
import sys
from http import HTTPStatus
from http.cookies import SimpleCookie
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any


REPOSITORY_ROOT = Path(__file__).resolve().parent
UI_ROOT = REPOSITORY_ROOT / "ui"
sys.path.insert(0, str(REPOSITORY_ROOT / "src"))

from session_host import SessionHost, SessionError  # noqa: E402


SESSION_HOST = SessionHost()


class CampusRequestHandler(SimpleHTTPRequestHandler):
    """Serve the static UI and its JSON host endpoints."""

    session_host = SESSION_HOST

    def _owner(self) -> str | None:
        cookie = SimpleCookie()
        try:
            cookie.load(self.headers.get("Cookie", ""))
            return cookie["campus_browser"].value if "campus_browser" in cookie else None
        except Exception:
            return None

    def _valid_host(self) -> bool:
        port = self.server.server_address[1]
        return self.headers.get("Host") in (f"127.0.0.1:{port}", f"localhost:{port}")

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, directory=str(UI_ROOT), **kwargs)

    def end_headers(self) -> None:
        self.send_header("Cache-Control", "no-store")
        super().end_headers()

    def _send_json(self, payload: Any, status: int = 200) -> None:
        cookie = payload.pop("_set_cookie", None) if isinstance(payload, dict) else None
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        if cookie:
            self.send_header("Set-Cookie", f"campus_browser={cookie}; HttpOnly; SameSite=Strict; Path=/")
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
        if not self._valid_host():
            self._send_json({"error": {"code": "HOST_REJECTED"}}, 403)
            return
        if self.path == "/api/session":
            try:
                owner, session = self.session_host.bootstrap(self._owner())
                body = json.dumps({"session": session}, ensure_ascii=False).encode("utf-8")
                self.send_response(200)
                self.send_header("Set-Cookie", f"campus_browser={owner}; HttpOnly; SameSite=Strict; Path=/")
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
            except SessionError as exc:
                self._send_json({"error": {"code": exc.code}, "reason": str(exc)}, exc.status)
            return
        if self.path == "/api/config":
            self._send_json({**self.session_host.service.config(), "memory_contract": "private-draft-revision-v3"})
            return
        if self.path == "/api/tools":
            self._send_json(self.session_host.service.tool_server.list_tools())
            return
        if self.path == "/":
            self.path = "/index.html"
        super().do_GET()

    def do_POST(self) -> None:  # noqa: N802
        try:
            if not self._valid_host():
                self._send_json({"error": {"code": "HOST_REJECTED"}}, 403)
                return
            origin = self.headers.get("Origin")
            if origin and origin != f"http://{self.headers.get('Host')}":
                self._send_json({"error": {"code": "ORIGIN_REJECTED"}}, 403)
                return
            payload = self._read_json()
            status, response = self.session_host.handle(
                self._owner(), self.headers.get("X-CSRF-Token", ""), self.path, payload
            )
            self._send_json(response, status)
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
