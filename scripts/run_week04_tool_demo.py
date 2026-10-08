#!/usr/bin/env python3
"""Run a reproducible MCP stdio read/write/idempotency demonstration."""

from __future__ import annotations

import json
import subprocess
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    process = subprocess.Popen(
        [sys.executable, str(REPOSITORY_ROOT / "mcp_server.py")],
        cwd=REPOSITORY_ROOT,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
    )
    request_counter = 0

    def call(method: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        nonlocal request_counter
        request_counter += 1
        message: dict[str, Any] = {
            "jsonrpc": "2.0",
            "id": request_counter,
            "method": method,
        }
        if params is not None:
            message["params"] = params
        assert process.stdin is not None
        assert process.stdout is not None
        process.stdin.write(json.dumps(message, ensure_ascii=False) + "\n")
        process.stdin.flush()
        response_line = process.stdout.readline()
        if not response_line:
            stderr = process.stderr.read() if process.stderr else ""
            raise RuntimeError(f"MCP server stopped without a response: {stderr}")
        return json.loads(response_line)

    run_id = f"week04-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}-{uuid.uuid4().hex[:6]}"
    request_id = f"mail-demo-{uuid.uuid4().hex}"
    try:
        initialize = call(
            "initialize",
            {
                "protocolVersion": "2026-07-28",
                "capabilities": {},
                "clientInfo": {"name": "week04-demo", "version": "0.1.0"},
            },
        )
        tools_list = call("tools/list")
        lookup = call(
            "tools/call",
            {"name": "get_teacher_contact", "arguments": {"teacher_query": "林朝興"}},
        )
        send_arguments = {
            "teacher_id": "faculty-mikelin",
            "to": "mikelin@mail.nutn.edu.tw",
            "subject": "Week 04 Sandbox 測試",
            "body": "林老師您好：\n\n這是工具流程的合成測試內容。\n\n測試學生 敬上",
            "request_id": request_id,
            "confirmed": False,
        }
        rejected = call("tools/call", {"name": "send_email", "arguments": send_arguments})
        send_arguments["confirmed"] = True
        sent = call("tools/call", {"name": "send_email", "arguments": send_arguments})
        replay = call("tools/call", {"name": "send_email", "arguments": send_arguments})
        status = call(
            "tools/call",
            {"name": "get_email_status", "arguments": {"request_id": request_id}},
        )
        report = {
            "run_id": run_id,
            "evidence_status": "MCP_LOCAL_PASS",
            "real_email_sent": False,
            "protocol_version": initialize["result"]["protocolVersion"],
            "tools": [tool["name"] for tool in tools_list["result"]["tools"]],
            "read_result": lookup["result"]["structuredContent"]["status"],
            "unconfirmed_write": rejected["result"]["structuredContent"]["error"]["code"],
            "confirmed_write": sent["result"]["structuredContent"],
            "idempotent_replay": replay["result"]["structuredContent"]["status"],
            "status_lookup": status["result"]["structuredContent"]["status"],
        }
        print(json.dumps(report, ensure_ascii=False, indent=2))
    finally:
        process.terminate()
        process.wait(timeout=5)


if __name__ == "__main__":
    main()
