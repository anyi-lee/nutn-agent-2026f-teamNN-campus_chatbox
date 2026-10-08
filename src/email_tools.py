"""Deterministic tools for grounded faculty lookup and sandbox email delivery.

The write tool never connects to an email provider.  It records an immutable
receipt in a local SQLite outbox so the confirmation, idempotency, and status
lookup flow can be tested without risking a real message.
"""

from __future__ import annotations

import json
import sqlite3
import threading
import uuid
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping


class ToolCallError(RuntimeError):
    """A safe, structured tool error that may be returned to the host."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message

    def as_dict(self) -> dict[str, Any]:
        return {"status": "rejected", "error": {"code": self.code, "message": self.message}}


TOOL_DEFINITIONS: list[dict[str, Any]] = [
    {
        "name": "get_teacher_contact",
        "description": "從版本化的南大資工系官方資料查詢教師公開聯絡資訊。",
        "inputSchema": {
            "type": "object",
            "properties": {
                "teacher_query": {
                    "type": "string",
                    "description": "教師全名或可辨識的姓名片段。",
                    "minLength": 1,
                }
            },
            "required": ["teacher_query"],
            "additionalProperties": False,
        },
        "annotations": {
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
        },
    },
    {
        "name": "send_email",
        "description": "經使用者確認後，將已驗證草稿寫入本機 Sandbox outbox；不會寄到真實信箱。",
        "inputSchema": {
            "type": "object",
            "properties": {
                "teacher_id": {"type": "string"},
                "to": {"type": "string"},
                "subject": {"type": "string", "minLength": 1, "maxLength": 80},
                "body": {"type": "string", "minLength": 1, "maxLength": 4000},
                "request_id": {"type": "string", "minLength": 8},
                "confirmed": {"type": "boolean", "const": True},
            },
            "required": ["teacher_id", "to", "subject", "body", "request_id", "confirmed"],
            "additionalProperties": False,
        },
        "annotations": {
            "readOnlyHint": False,
            "destructiveHint": False,
            "idempotentHint": True,
        },
    },
    {
        "name": "get_email_status",
        "description": "依 request_id 查詢 Sandbox 寄送結果，供逾時後安全確認狀態。",
        "inputSchema": {
            "type": "object",
            "properties": {"request_id": {"type": "string", "minLength": 8}},
            "required": ["request_id"],
            "additionalProperties": False,
        },
        "annotations": {
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
        },
    },
]


class CampusToolServer:
    """Small tool server shared by the web host and the stdio MCP adapter."""

    def __init__(
        self,
        faculty_document: Mapping[str, Any],
        outbox_path: Path,
    ) -> None:
        self.source = dict(faculty_document["source"])
        self.teachers = list(faculty_document["chunks"])
        self.teacher_by_id = {teacher["chunk_id"]: teacher for teacher in self.teachers}
        self.outbox_path = Path(outbox_path)
        self._database_lock = threading.Lock()
        self._initialize_outbox()

    def list_tools(self) -> dict[str, Any]:
        return {"tools": json.loads(json.dumps(TOOL_DEFINITIONS, ensure_ascii=False))}

    def call_tool(self, name: str, arguments: Mapping[str, Any]) -> dict[str, Any]:
        if not isinstance(arguments, Mapping):
            raise ToolCallError("INVALID_ARGUMENTS", "工具參數必須是 JSON object。")
        if name == "get_teacher_contact":
            return self._get_teacher_contact(arguments)
        if name == "send_email":
            return self._send_email(arguments)
        if name == "get_email_status":
            return self._get_email_status(arguments)
        raise ToolCallError("TOOL_NOT_FOUND", f"未知工具：{name}")

    def _get_teacher_contact(self, arguments: Mapping[str, Any]) -> dict[str, Any]:
        self._require_allowed_fields(arguments, {"teacher_query"})
        query = str(arguments.get("teacher_query") or "").strip()
        if not query:
            raise ToolCallError("MISSING_TEACHER_QUERY", "請提供教師姓名。")

        exact = [teacher for teacher in self.teachers if teacher["teacher_name"] == query]
        matches = exact or [
            teacher
            for teacher in self.teachers
            if query in teacher["teacher_name"] or teacher["teacher_name"] in query
        ]
        if not matches:
            return {
                "status": "not_found",
                "query": query,
                "source": self._source_summary(),
            }
        if len(matches) > 1:
            return {
                "status": "ambiguous",
                "query": query,
                "candidates": [teacher["teacher_name"] for teacher in matches],
                "source": self._source_summary(),
            }

        teacher = matches[0]
        return {
            "status": "found",
            "teacher": {
                "teacher_id": teacher["chunk_id"],
                "name": teacher["teacher_name"],
                "title": teacher["title"],
                "public_email": teacher["public_email"],
                "source_url": teacher["source_url"],
                "authority": teacher["authority"],
                "validity": teacher["validity"],
            },
            "source": self._source_summary(),
        }

    def _send_email(self, arguments: Mapping[str, Any]) -> dict[str, Any]:
        self._require_allowed_fields(
            arguments,
            {"teacher_id", "to", "subject", "body", "request_id", "confirmed"},
        )
        if arguments.get("confirmed") is not True:
            raise ToolCallError("CONFIRMATION_REQUIRED", "必須取得使用者明確確認後才能執行。")

        required = ("teacher_id", "to", "subject", "body", "request_id")
        missing = [name for name in required if not str(arguments.get(name) or "").strip()]
        if missing:
            raise ToolCallError("MISSING_REQUIRED_FIELD", f"缺少欄位：{', '.join(missing)}")

        teacher_id = str(arguments["teacher_id"]).strip()
        teacher = self.teacher_by_id.get(teacher_id)
        if teacher is None:
            raise ToolCallError("RECIPIENT_NOT_ALLOWED", "收件人不在官方教師資料中。")

        recipient = str(arguments["to"]).strip()
        if recipient != teacher["public_email"]:
            raise ToolCallError("RECIPIENT_MISMATCH", "收件地址與官方教師資料不一致。")

        subject = str(arguments["subject"]).strip()
        body = str(arguments["body"]).strip()
        request_id = str(arguments["request_id"]).strip()
        if len(subject) > 80 or len(body) > 4000:
            raise ToolCallError("CONTENT_TOO_LONG", "主旨或正文超過允許長度。")
        if len(request_id) < 8:
            raise ToolCallError("INVALID_REQUEST_ID", "request_id 格式不正確。")

        with self._database_lock:
            existing = self._read_receipt(request_id)
            if existing is not None:
                existing["status"] = "already_processed"
                existing["idempotent_replay"] = True
                return existing

            receipt = {
                "status": "simulated_sent",
                "delivery_mode": "sandbox",
                "request_id": request_id,
                "message_id": f"sandbox-{uuid.uuid4().hex[:16]}",
                "teacher_id": teacher_id,
                "to": recipient,
                "subject": subject,
                "sent_at": datetime.now(timezone.utc).isoformat(),
                "idempotent_replay": False,
            }
            with closing(sqlite3.connect(self.outbox_path)) as connection:
                connection.execute(
                    """
                    INSERT INTO sandbox_outbox
                        (request_id, message_id, teacher_id, recipient, subject, body, sent_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        request_id,
                        receipt["message_id"],
                        teacher_id,
                        recipient,
                        subject,
                        body,
                        receipt["sent_at"],
                    ),
                )
                connection.commit()
            return receipt

    def _get_email_status(self, arguments: Mapping[str, Any]) -> dict[str, Any]:
        self._require_allowed_fields(arguments, {"request_id"})
        request_id = str(arguments.get("request_id") or "").strip()
        if not request_id:
            raise ToolCallError("MISSING_REQUEST_ID", "請提供 request_id。")
        receipt = self._read_receipt(request_id)
        if receipt is None:
            return {"status": "not_found", "request_id": request_id, "delivery_mode": "sandbox"}
        return receipt

    def _initialize_outbox(self) -> None:
        self.outbox_path.parent.mkdir(parents=True, exist_ok=True)
        with closing(sqlite3.connect(self.outbox_path)) as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS sandbox_outbox (
                    request_id TEXT PRIMARY KEY,
                    message_id TEXT NOT NULL,
                    teacher_id TEXT NOT NULL,
                    recipient TEXT NOT NULL,
                    subject TEXT NOT NULL,
                    body TEXT NOT NULL,
                    sent_at TEXT NOT NULL
                )
                """
            )
            connection.commit()

    def _read_receipt(self, request_id: str) -> dict[str, Any] | None:
        with closing(sqlite3.connect(self.outbox_path)) as connection:
            row = connection.execute(
                """
                SELECT request_id, message_id, teacher_id, recipient, subject, sent_at
                FROM sandbox_outbox WHERE request_id = ?
                """,
                (request_id,),
            ).fetchone()
        if row is None:
            return None
        return {
            "status": "simulated_sent",
            "delivery_mode": "sandbox",
            "request_id": row[0],
            "message_id": row[1],
            "teacher_id": row[2],
            "to": row[3],
            "subject": row[4],
            "sent_at": row[5],
            "idempotent_replay": False,
        }

    def _source_summary(self) -> dict[str, Any]:
        return {
            "source_id": self.source["source_id"],
            "source_url": self.source["source_url"],
            "retrieved_at": self.source["retrieved_at"],
            "index_version": self.source["index_version"],
        }

    @staticmethod
    def _require_allowed_fields(
        arguments: Mapping[str, Any],
        allowed: set[str],
    ) -> None:
        unknown = sorted(str(name) for name in arguments if name not in allowed)
        if unknown:
            raise ToolCallError(
                "UNKNOWN_ARGUMENT",
                f"工具參數包含未允許欄位：{', '.join(unknown)}",
            )
