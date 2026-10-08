"""Dependency-free stdio MCP adapter for the campus email tools.

Messages are one JSON-RPC object per line.  This adapter is intentionally
small, but exposes the course-required initialize, tools/list, and tools/call
round trip using the same tool implementation as the web application.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any


REPOSITORY_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(REPOSITORY_ROOT / "src"))

from email_tools import CampusToolServer, ToolCallError  # noqa: E402


def build_server() -> CampusToolServer:
    faculty_document = json.loads(
        (REPOSITORY_ROOT / "data" / "faculty_chunks.json").read_text(encoding="utf-8")
    )
    return CampusToolServer(
        faculty_document,
        REPOSITORY_ROOT / "runtime" / "sandbox_outbox.sqlite3",
    )


def response_for(server: CampusToolServer, message: dict[str, Any]) -> dict[str, Any] | None:
    request_id = message.get("id")
    method = message.get("method")
    params = message.get("params") or {}

    if method == "notifications/initialized":
        return None
    if method == "initialize":
        return {
            "jsonrpc": "2.0",
            "id": request_id,
            "result": {
                "protocolVersion": "2026-07-28",
                "capabilities": {"tools": {"listChanged": False}},
                "serverInfo": {"name": "nutn-campus-email-tools", "version": "0.1.0"},
            },
        }
    if method == "tools/list":
        return {"jsonrpc": "2.0", "id": request_id, "result": server.list_tools()}
    if method == "tools/call":
        try:
            result = server.call_tool(str(params.get("name") or ""), params.get("arguments") or {})
            return {
                "jsonrpc": "2.0",
                "id": request_id,
                "result": {
                    "content": [{"type": "text", "text": json.dumps(result, ensure_ascii=False)}],
                    "structuredContent": result,
                    "isError": False,
                    "_meta": {"resultType": "complete"},
                },
            }
        except ToolCallError as error:
            result = error.as_dict()
            return {
                "jsonrpc": "2.0",
                "id": request_id,
                "result": {
                    "content": [{"type": "text", "text": error.message}],
                    "structuredContent": result,
                    "isError": True,
                    "_meta": {"resultType": "complete"},
                },
            }

    return {
        "jsonrpc": "2.0",
        "id": request_id,
        "error": {"code": -32601, "message": f"Method not found: {method}"},
    }


def main() -> None:
    server = build_server()
    for line in sys.stdin:
        if not line.strip():
            continue
        try:
            message = json.loads(line)
            response = response_for(server, message)
        except (json.JSONDecodeError, TypeError, ValueError) as error:
            response = {
                "jsonrpc": "2.0",
                "id": None,
                "error": {"code": -32700, "message": f"Parse error: {error}"},
            }
        if response is not None:
            print(json.dumps(response, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
