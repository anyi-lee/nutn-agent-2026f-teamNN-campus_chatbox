"""Local accounts and explicitly approved, account-scoped reusable email text.

Passwords use salted PBKDF2-HMAC-SHA256 (600,000 iterations). Stored memories
are user-authored data, never campus facts or executable model instructions.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import re
import secrets
import sqlite3
from personal_memory import fact_key
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


class MemoryError(RuntimeError):
    def __init__(self, code: str, message: str, status: int = 422):
        super().__init__(message)
        self.code, self.status = code, status


class AccountMemoryStore:
    ITERATIONS = 600_000
    KINDS = ("introduction", "request", "signature", "other", "draft_template", "personal_fact")

    def __init__(self, path: Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with closing(self._connect()) as connection:
            connection.executescript("""
                CREATE TABLE IF NOT EXISTS local_accounts (
                    account_id TEXT PRIMARY KEY, username TEXT NOT NULL UNIQUE,
                    salt BLOB NOT NULL, password_hash BLOB NOT NULL, iterations INTEGER NOT NULL
                );
                CREATE TABLE IF NOT EXISTS email_memories (
                    memory_id TEXT PRIMARY KEY, account_id TEXT NOT NULL,
                    title TEXT NOT NULL, kind TEXT NOT NULL, content TEXT NOT NULL,
                    version INTEGER NOT NULL, created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL, deleted_at TEXT,
                    FOREIGN KEY (account_id) REFERENCES local_accounts(account_id)
                );
                CREATE TABLE IF NOT EXISTS memory_operations (
                    account_id TEXT NOT NULL, operation_id TEXT NOT NULL,
                    fingerprint TEXT NOT NULL, result_json TEXT NOT NULL,
                    PRIMARY KEY (account_id, operation_id)
                );
            """)
            columns = {row[1] for row in connection.execute("PRAGMA table_info(email_memories)")}
            if "template_json" not in columns:
                connection.execute("ALTER TABLE email_memories ADD COLUMN template_json TEXT NOT NULL DEFAULT '{}'")
            connection.execute("""CREATE UNIQUE INDEX IF NOT EXISTS personal_fact_key
                ON email_memories(account_id, title)
                WHERE kind='personal_fact' AND deleted_at IS NULL""")
            connection.commit()

    @staticmethod
    def _record(row):
        record = dict(row)
        record["template_fields"] = json.loads(record.pop("template_json"))
        return record

    @staticmethod
    def template_fields(kind, fields):
        limits = {"teacher_name": 100, "subject": 80}
        if not isinstance(fields, dict) or set(fields) - set(limits):
            raise MemoryError("INVALID_TEMPLATE_FIELDS", "整封模板欄位格式不合法。")
        if kind != "draft_template":
            if fields:
                raise MemoryError("INVALID_TEMPLATE_FIELDS", "文字範本只保存內容，不保存對象等欄位。")
            return {}
        for key, value in fields.items():
            if not isinstance(value, str) or len(value) > limits[key]:
                raise MemoryError("INVALID_TEMPLATE_FIELDS", f"模板 {key} 格式或長度不合法。")
        if (not fields.get("teacher_name", "").strip() or not fields.get("subject", "").strip()
                or any(char in fields["subject"] for char in "\r\n")):
            raise MemoryError("INVALID_TEMPLATE_FIELDS", "草稿模板需有教師及單行主旨。")
        return {key: value.strip() for key, value in fields.items()}

    def _connect(self):
        connection = sqlite3.connect(self.path, timeout=10)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys=ON")
        return connection

    @staticmethod
    def _credentials(username: Any, password: Any) -> tuple[str, str]:
        if not isinstance(username, str) or not re.fullmatch(r"[A-Za-z0-9_-]{3,32}", username):
            raise MemoryError("INVALID_ACCOUNT", "帳號需為 3–32 個英數字、底線或連字號。")
        if not isinstance(password, str) or not 12 <= len(password) <= 128:
            raise MemoryError("INVALID_PASSWORD", "密碼需為 12–128 個字元。")
        return username.lower(), password

    def register(self, username: Any, password: Any) -> dict[str, str]:
        username, password = self._credentials(username, password)
        salt = secrets.token_bytes(32)
        digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, self.ITERATIONS)
        account = {"account_id": secrets.token_hex(16), "username": username}
        try:
            with closing(self._connect()) as connection, connection:
                connection.execute("INSERT INTO local_accounts VALUES (?, ?, ?, ?, ?)",
                                   (account["account_id"], username, salt, digest, self.ITERATIONS))
        except sqlite3.IntegrityError as exc:
            raise MemoryError("ACCOUNT_EXISTS", "此帳號已存在，請登入或更換帳號。", 409) from exc
        return account

    def login(self, username: Any, password: Any) -> dict[str, str]:
        username, password = self._credentials(username, password)
        with closing(self._connect()) as connection:
            row = connection.execute("SELECT * FROM local_accounts WHERE username=?", (username,)).fetchone()
        salt = bytes(row["salt"]) if row else b"local-unknown-account-dummy-salt"
        iterations = row["iterations"] if row else self.ITERATIONS
        digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, iterations)
        expected = bytes(row["password_hash"]) if row else bytes(32)
        if not hmac.compare_digest(digest, expected) or row is None:
            raise MemoryError("LOGIN_FAILED", "帳號或密碼不正確。", 401)
        return {"account_id": row["account_id"], "username": row["username"]}

    def list_memories(self, account_id: str) -> list[dict[str, Any]]:
        with closing(self._connect()) as connection:
            rows = connection.execute("""SELECT memory_id, title, kind, content, version,
                created_at, updated_at, template_json FROM email_memories
                WHERE account_id=? AND deleted_at IS NULL ORDER BY created_at, memory_id""", (account_id,)).fetchall()
        return [self._record(row) for row in rows]

    def selected(self, account_id: str, selections: Any) -> list[dict[str, Any]]:
        if not isinstance(selections, list) or len(selections) > 8:
            raise MemoryError("INVALID_MEMORY_SELECTION", "一次最多選取 8 筆常用內容。")
        selected, seen = [], set()
        with closing(self._connect()) as connection:
            for selection in selections:
                if (not isinstance(selection, dict) or set(selection) != {"memory_id", "version"}
                        or not isinstance(selection["memory_id"], str) or type(selection["version"]) is not int
                        or selection["memory_id"] in seen):
                    raise MemoryError("INVALID_MEMORY_SELECTION", "常用內容識別與版本格式錯誤。")
                seen.add(selection["memory_id"])
                row = connection.execute("""SELECT memory_id, title, kind, content, version, template_json
                    FROM email_memories WHERE memory_id=? AND account_id=? AND deleted_at IS NULL""",
                    (selection["memory_id"], account_id)).fetchone()
                if row is None:
                    raise MemoryError("MEMORY_NOT_FOUND", "常用內容不存在或無權存取。", 404)
                if row["version"] != selection["version"]:
                    raise MemoryError("MEMORY_VERSION_CONFLICT", "常用內容已修改，請重新讀取並選取。", 409)
                selected.append(self._record(row))
        if sum(len(item["content"]) for item in selected) > 4000:
            raise MemoryError("MEMORY_CONTEXT_TOO_LONG", "選取內容合計最多 4000 字，請減少選取。")
        return selected

    def mutate(self, account_id: str, action: str, payload: dict[str, Any]) -> dict[str, Any]:
        if payload.get("kind") == "personal_fact" and isinstance(payload.get("title"), str):
            payload = {**payload, "title": fact_key(payload["title"])}
        if payload.get("confirmed") is not True:
            raise MemoryError("MEMORY_CONFIRMATION_REQUIRED", "請明確確認保存、修改或刪除。", 409)
        operation_id = payload.get("operation_id")
        if not isinstance(operation_id, str) or not re.fullmatch(r"[A-Za-z0-9_-]{8,100}", operation_id):
            raise MemoryError("INVALID_OPERATION_ID", "操作識別格式錯誤。")
        allowed = {"action", "confirmed", "operation_id", "memory_id", "expected_version", "title", "kind", "content", "template_fields", "source_draft_id"}
        if set(payload) - allowed or action not in ("create", "update", "delete"):
            raise MemoryError("INVALID_MEMORY_INPUT", "常用內容參數不合法。")
        if action != "delete":
            for name, maximum in (("title", 60), ("content", 4000 if payload.get("kind") == "draft_template" else 2000)):
                value = payload.get(name)
                if not isinstance(value, str) or not value.strip() or len(value) > maximum:
                    raise MemoryError("INVALID_MEMORY_INPUT", f"{name} 必須為 1–{maximum} 字的文字。")
            if payload.get("kind") not in self.KINDS:
                raise MemoryError("INVALID_MEMORY_KIND", "請選擇文字類型或整封模板。")
            template_fields = self.template_fields(payload["kind"], payload.get("template_fields", {}))
        if action != "create" and (not isinstance(payload.get("memory_id"), str)
                                     or type(payload.get("expected_version")) is not int):
            raise MemoryError("INVALID_MEMORY_INPUT", "請提供常用內容識別與預期版本。")
        fingerprint = hashlib.sha256(json.dumps({**payload, "action": action}, ensure_ascii=False, sort_keys=True).encode()).hexdigest()
        now = datetime.now(timezone.utc).isoformat()
        with closing(self._connect()) as connection, connection:
            connection.execute("BEGIN IMMEDIATE")
            replay = connection.execute("SELECT fingerprint, result_json FROM memory_operations WHERE account_id=? AND operation_id=?",
                                        (account_id, operation_id)).fetchone()
            if replay:
                if replay["fingerprint"] != fingerprint:
                    raise MemoryError("OPERATION_CONFLICT", "相同操作識別不能套用不同內容。", 409)
                return {**json.loads(replay["result_json"]), "idempotent_replay": True}
            if action != "delete" and payload["kind"] == "personal_fact":
                duplicate = connection.execute("""SELECT memory_id FROM email_memories
                    WHERE account_id=? AND title=? AND kind='personal_fact' AND deleted_at IS NULL""",
                    (account_id, payload["title"])).fetchone()
                if duplicate and (action == "create" or duplicate["memory_id"] != payload.get("memory_id")):
                    raise MemoryError("MEMORY_VERSION_CONFLICT", "此項個人記憶已存在或更新，請重新提出資訊並確認覆蓋。", 409)
            if action == "create":
                count = connection.execute("SELECT count(*) FROM email_memories WHERE account_id=? AND deleted_at IS NULL", (account_id,)).fetchone()[0]
                if count >= 100:
                    raise MemoryError("MEMORY_CAPACITY", "目前最多保存 100 筆，請先整理。", 409)
                memory_id, version = secrets.token_hex(16), 1
                connection.execute("""INSERT INTO email_memories
                    (memory_id, account_id, title, kind, content, version, created_at, updated_at, template_json)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                                   (memory_id, account_id, payload["title"].strip(), payload["kind"], payload["content"].strip(), version, now, now, json.dumps(template_fields, ensure_ascii=False)))
            else:
                memory_id = payload["memory_id"]
                row = connection.execute("SELECT version FROM email_memories WHERE memory_id=? AND account_id=? AND deleted_at IS NULL", (memory_id, account_id)).fetchone()
                if row is None:
                    raise MemoryError("MEMORY_NOT_FOUND", "常用內容不存在或無權存取。", 404)
                if row["version"] != payload["expected_version"]:
                    raise MemoryError("MEMORY_VERSION_CONFLICT", "常用內容已變更，請重新讀取再操作。", 409)
                version = row["version"] + 1
                if action == "delete":
                    connection.execute("UPDATE email_memories SET title='', content='', template_json='{}', version=?, updated_at=?, deleted_at=? WHERE memory_id=?", (version, now, now, memory_id))
                else:
                    connection.execute("UPDATE email_memories SET title=?, kind=?, content=?, version=?, updated_at=?, template_json=? WHERE memory_id=?",
                                       (payload["title"].strip(), payload["kind"], payload["content"].strip(), version, now, json.dumps(template_fields, ensure_ascii=False), memory_id))
            result = {"status": "memory_deleted" if action == "delete" else "memory_saved",
                      "memory_id": memory_id, "version": version, "idempotent_replay": False}
            # No private content in replay receipts; delete clears the active text.
            connection.execute("INSERT INTO memory_operations VALUES (?, ?, ?, ?)",
                               (account_id, operation_id, fingerprint, json.dumps(result)))
            return result
