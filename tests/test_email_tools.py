"""Contract and safety tests for the Week 04 campus tools."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT / "src"))

from email_tools import CampusToolServer, ToolCallError  # noqa: E402


class CampusToolServerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        document = json.loads(
            (REPOSITORY_ROOT / "data" / "faculty_chunks.json").read_text(encoding="utf-8")
        )
        self.server = CampusToolServer(
            document,
            Path(self.temporary_directory.name) / "outbox.sqlite3",
        )

    def tearDown(self) -> None:
        self.temporary_directory.cleanup()

    def test_tools_list_has_read_and_write_contracts(self) -> None:
        tools = self.server.list_tools()["tools"]
        by_name = {tool["name"]: tool for tool in tools}

        self.assertTrue(by_name["get_teacher_contact"]["annotations"]["readOnlyHint"])
        self.assertFalse(by_name["send_email"]["annotations"]["readOnlyHint"])
        self.assertTrue(by_name["send_email"]["annotations"]["idempotentHint"])

    def test_read_tool_returns_grounded_official_contact(self) -> None:
        result = self.server.call_tool(
            "get_teacher_contact",
            {"teacher_query": "林朝興"},
        )

        self.assertEqual(result["status"], "found")
        self.assertEqual(result["teacher"]["public_email"], "mikelin@mail.nutn.edu.tw")
        self.assertEqual(result["source"]["source_id"], "nutn-csie-faculty")

    def test_tool_rejects_unknown_arguments(self) -> None:
        with self.assertRaises(ToolCallError) as context:
            self.server.call_tool(
                "get_teacher_contact",
                {"teacher_query": "林朝興", "confirmed": True},
            )

        self.assertEqual(context.exception.code, "UNKNOWN_ARGUMENT")

    def test_write_tool_rejects_missing_confirmation(self) -> None:
        with self.assertRaises(ToolCallError) as context:
            self.server.call_tool(
                "send_email",
                self._valid_send_arguments(confirmed=False),
            )

        self.assertEqual(context.exception.code, "CONFIRMATION_REQUIRED")
        status = self.server.call_tool(
            "get_email_status",
            {"request_id": "mail-test-001"},
        )
        self.assertEqual(status["status"], "not_found")

    def test_write_tool_rejects_recipient_not_in_official_record(self) -> None:
        arguments = self._valid_send_arguments()
        arguments["to"] = "attacker@example.com"

        with self.assertRaises(ToolCallError) as context:
            self.server.call_tool("send_email", arguments)

        self.assertEqual(context.exception.code, "RECIPIENT_MISMATCH")

    def test_write_is_idempotent_and_status_is_queryable(self) -> None:
        first = self.server.call_tool("send_email", self._valid_send_arguments())
        second = self.server.call_tool("send_email", self._valid_send_arguments())
        status = self.server.call_tool(
            "get_email_status",
            {"request_id": "mail-test-001"},
        )

        self.assertEqual(first["status"], "simulated_sent")
        self.assertEqual(second["status"], "already_processed")
        self.assertEqual(first["message_id"], second["message_id"])
        self.assertTrue(second["idempotent_replay"])
        self.assertEqual(status["message_id"], first["message_id"])

    @staticmethod
    def _valid_send_arguments(*, confirmed: bool = True) -> dict[str, object]:
        return {
            "teacher_id": "faculty-mikelin",
            "to": "mikelin@mail.nutn.edu.tw",
            "subject": "多媒體系統課程加簽詢問",
            "body": "林老師您好：\n\n想請問課程加簽方式。\n\n學生 李安以 敬上",
            "request_id": "mail-test-001",
            "confirmed": confirmed,
        }


if __name__ == "__main__":
    unittest.main(verbosity=2)
