"""Tests for the service backing the local UI."""

from __future__ import annotations

import sys
import json
import tempfile
import unittest
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT / "src"))

from campus_service import CampusService  # noqa: E402
from email_tools import CampusToolServer  # noqa: E402
from gemini_email import GeminiEmailError, GeminiEmailGenerator  # noqa: E402


class FakeGeminiGenerator:
    configured = True
    model = "gemini-test"

    def generate(self, facts):
        return {
            "subject": "多媒體課程加簽詢問",
            "body": (
                "林老師您好：\n\n"
                "我是資訊工程學系大四學生李安以，想請問多媒體課程的加簽方式。\n\n"
                "感謝老師撥冗閱讀。\n\n學生 李安以 敬上"
            ),
        }


class FailingGeminiGenerator(FakeGeminiGenerator):
    def generate(self, facts):
        raise GeminiEmailError("fixture failure")


class CampusServiceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.service = CampusService(
            email_generator=GeminiEmailGenerator(api_key="")
        )

    def test_bm25_contact_query_returns_grounded_email(self) -> None:
        response = self.service.chat("林朝興教授的 Email 是什麼？", "bm25")

        self.assertEqual(response["status"], "ok")
        self.assertIn("mikelin@mail.nutn.edu.tw", response["answer"])
        self.assertEqual(response["evidence"]["teacher_name"], "林朝興")
        self.assertEqual(response["citations"][0]["source_id"], "nutn-csie-faculty")

    def test_dense_stub_contact_query_returns_same_teacher(self) -> None:
        response = self.service.chat("我要怎麼聯絡林朝興老師？", "dense_stub")

        self.assertEqual(response["status"], "ok")
        self.assertEqual(response["evidence"]["teacher_name"], "林朝興")
        self.assertEqual(response["retrieval"]["model"], "dense_stub")

    def test_live_status_query_abstains(self) -> None:
        response = self.service.chat("林朝興教授今天幾點會在研究室？", "bm25")

        self.assertEqual(response["status"], "insufficient_evidence")
        self.assertEqual(response["error"]["code"], "INSUFFICIENT_EVIDENCE")
        self.assertIn("不能替你推測", response["answer"])

    def test_follow_up_uses_previous_teacher_context(self) -> None:
        response = self.service.chat(
            "研究方下",
            "bm25",
            context_teacher="陳宗禧",
        )

        self.assertEqual(response["status"], "ok")
        self.assertTrue(response["used_context"])
        self.assertEqual(response["evidence"]["teacher_name"], "陳宗禧")
        self.assertIn("無線網路", response["answer"])

    def test_unrelated_weather_query_does_not_reuse_teacher_context(self) -> None:
        response = self.service.chat(
            "今天天氣如何",
            "bm25",
            context_teacher="林朝興",
        )

        self.assertEqual(response["status"], "insufficient_evidence")
        self.assertEqual(response["error"]["code"], "INSUFFICIENT_EVIDENCE")
        self.assertFalse(response["used_context"])
        self.assertNotIn("林朝興", response["answer"])

    def test_explicit_teacher_overrides_previous_context(self) -> None:
        response = self.service.chat(
            "朱明毅老師的研究方向",
            "bm25",
            context_teacher="陳宗禧",
        )

        self.assertFalse(response["used_context"])
        self.assertEqual(response["evidence"]["teacher_name"], "朱明毅")

    def test_zero_vector_dense_query_abstains(self) -> None:
        response = self.service.chat("請協助處理這件事情", "dense_stub")

        self.assertEqual(response["status"], "insufficient_evidence")
        self.assertTrue(response["retrieval"]["is_zero_vector"])

    def test_course_offering_question_is_blocked_by_scope_gate(self) -> None:
        response = self.service.chat("有開什麼課", "bm25")

        self.assertEqual(response["status"], "insufficient_evidence")
        self.assertEqual(response["error"]["code"], "OUT_OF_SCOPE_SOURCE")
        self.assertIsNone(response["retrieval"])
        self.assertIn("沒有當學期開課資訊", response["answer"])

    def test_office_hours_query_reports_missing_official_hours(self) -> None:
        response = self.service.chat(
            "資工系辦營業時間是幾點？",
            "bm25",
            context_teacher="林朝興",
        )

        self.assertEqual(response["status"], "insufficient_evidence")
        self.assertEqual(response["error"]["code"], "OFFICE_HOURS_NOT_PUBLISHED")
        self.assertFalse(response["used_context"])
        self.assertIsNone(response["evidence"]["office_hours"])
        self.assertEqual(
            response["evidence"]["office_hours_status"],
            "not_published_on_source",
        )
        self.assertIn("7701", response["answer"])
        self.assertIn("csie@mail.nutn.edu.tw", response["answer"])
        self.assertFalse(response["retrieval"]["evidence_gate"]["passed"])

    def test_office_contact_query_returns_official_record(self) -> None:
        response = self.service.chat("系辦電話和地址", "bm25")

        self.assertEqual(response["status"], "ok")
        self.assertEqual(response["evidence"]["extensions"], ["7701", "7702"])
        self.assertEqual(
            response["citations"][0]["source_id"],
            "nutn-csie-homepage-contact",
        )
        self.assertTrue(response["retrieval"]["evidence_gate"]["passed"])

    def test_admin_role_does_not_reuse_previous_teacher_context(self) -> None:
        response = self.service.chat(
            "想聯繫校長",
            "bm25",
            context_teacher="陳宗禧",
        )

        self.assertEqual(response["status"], "insufficient_evidence")
        self.assertEqual(response["error"]["code"], "OUT_OF_SCOPE_ADMIN_ROLE")
        self.assertFalse(response["used_context"])
        self.assertIsNone(response["detected_teacher"])
        self.assertNotIn("chents@mail.nutn.edu.tw", response["answer"])

    def test_other_department_chair_is_blocked_before_retrieval(self) -> None:
        response = self.service.chat(
            "想詢問國文系主任",
            "bm25",
            context_teacher="林朝興",
        )

        self.assertEqual(response["status"], "insufficient_evidence")
        self.assertEqual(response["error"]["code"], "OUT_OF_SCOPE_DEPARTMENT")
        self.assertIsNone(response["retrieval"])
        self.assertFalse(response["used_context"])
        self.assertIsNone(response["detected_teacher"])
        self.assertNotIn("林朝興", response["answer"])

    def test_unanchored_contact_query_fails_evidence_gate(self) -> None:
        response = self.service.chat("想聯絡老師", "bm25")

        self.assertEqual(response["status"], "insufficient_evidence")
        self.assertEqual(response["error"]["code"], "MISSING_TEACHER_IDENTITY")
        self.assertFalse(response["retrieval"]["evidence_gate"]["passed"])
        self.assertIsNone(response["detected_teacher"])

    def test_ambiguous_expertise_query_does_not_force_top_one_answer(self) -> None:
        response = self.service.chat("誰研究人工智慧", "bm25")

        self.assertEqual(response["status"], "insufficient_evidence")
        self.assertEqual(response["error"]["code"], "AMBIGUOUS_EVIDENCE")
        self.assertGreaterEqual(
            response["retrieval"]["evidence_gate"]["second_to_top_ratio"],
            0.75,
        )

    def test_distinctive_expertise_query_passes_evidence_gate(self) -> None:
        response = self.service.chat("有做機器人研究的老師嗎", "bm25")

        self.assertEqual(response["status"], "ok")
        self.assertEqual(response["evidence"]["teacher_name"], "朱明毅")
        self.assertTrue(response["retrieval"]["evidence_gate"]["passed"])

    def test_email_draft_uses_official_faculty_email_and_does_not_send(self) -> None:
        status, response = self.service.create_email_draft(
            {
                "teacher_name": "林朝興",
                "purpose": "course_add_request",
                "student_name": "李安以",
                "request_details": "想詢問人工智慧課程是否可以加簽",
            }
        )

        self.assertEqual(status, 200)
        self.assertEqual(response["email_draft"]["to"], "mikelin@mail.nutn.edu.tw")
        self.assertEqual(response["send_status"], "not_sent")
        self.assertTrue(response["requires_confirmation"])
        self.assertEqual(response["generation"]["provider"], "local_template")
        self.assertIn("想再請教加簽方式", response["email_draft"]["body"])

    def test_local_template_rewrites_short_course_add_request(self) -> None:
        status, response = self.service.create_email_draft(
            {
                "teacher_name": "林朝興",
                "purpose": "course_add_request",
                "student_name": "李安以",
                "student_grade": "大四",
                "request_details": "多媒體想加簽",
            }
        )

        self.assertEqual(status, 200)
        self.assertIn("希望加簽「多媒體」課程", response["email_draft"]["body"])
        self.assertNotIn("多媒體想加簽", response["email_draft"]["body"])

    def test_gemini_draft_keeps_recipient_grounded_in_official_data(self) -> None:
        service = CampusService(email_generator=FakeGeminiGenerator())
        status, response = service.create_email_draft(
            {
                "teacher_name": "林朝興",
                "purpose": "course_add_request",
                "student_name": "李安以",
                "student_grade": "大四",
                "request_details": "多媒體想加簽",
            }
        )

        self.assertEqual(status, 200)
        self.assertEqual(response["email_draft"]["to"], "mikelin@mail.nutn.edu.tw")
        self.assertEqual(response["email_draft"]["subject"], "多媒體課程加簽詢問")
        self.assertEqual(response["generation"]["provider"], "gemini")
        self.assertEqual(response["send_status"], "not_sent")

    def test_gemini_failure_falls_back_to_local_template(self) -> None:
        service = CampusService(email_generator=FailingGeminiGenerator())
        status, response = service.create_email_draft(
            {
                "teacher_name": "林朝興",
                "purpose": "course_add_request",
                "student_name": "李安以",
                "request_details": "多媒體想加簽",
            }
        )

        self.assertEqual(status, 200)
        self.assertEqual(response["generation"]["provider"], "local_template")
        self.assertTrue(response["generation"]["fallback_used"])
        self.assertIn("Gemini", response["generation"]["warning"])

    def test_email_draft_rejects_unknown_teacher(self) -> None:
        status, response = self.service.create_email_draft(
            {
                "teacher_name": "不存在老師",
                "purpose": "other",
                "student_name": "測試學生",
                "request_details": "想詢問一項課程相關問題",
            }
        )

        self.assertEqual(status, 404)
        self.assertEqual(response["error"]["code"], "TEACHER_NOT_FOUND")

    def test_sandbox_send_requires_confirmation_and_is_idempotent(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            document = json.loads(
                (REPOSITORY_ROOT / "data" / "faculty_chunks.json").read_text(encoding="utf-8")
            )
            tools = CampusToolServer(document, Path(directory) / "outbox.sqlite3")
            service = CampusService(
                email_generator=GeminiEmailGenerator(api_key=""),
                tool_server=tools,
            )
            draft_status, draft = service.create_email_draft(
                {
                    "teacher_name": "林朝興",
                    "purpose": "course_add_request",
                    "student_name": "李安以",
                    "request_details": "多媒體想加簽",
                }
            )

            rejected_status, rejected = service.send_email_draft(
                {"draft_id": draft["draft_id"], "confirmed": False}
            )
            sent_status, sent = service.send_email_draft(
                {"draft_id": draft["draft_id"], "confirmed": True}
            )
            replay_status, replay = service.send_email_draft(
                {"draft_id": draft["draft_id"], "confirmed": True}
            )

            self.assertEqual(draft_status, 200)
            self.assertEqual(rejected_status, 409)
            self.assertEqual(rejected["error"]["code"], "CONFIRMATION_REQUIRED")
            self.assertEqual(sent_status, 200)
            self.assertEqual(sent["status"], "simulated_sent")
            self.assertFalse(sent["delivery"]["real_email_sent"])
            self.assertEqual(replay_status, 200)
            self.assertEqual(replay["status"], "already_processed")
            self.assertEqual(
                sent["receipt"]["message_id"],
                replay["receipt"]["message_id"],
            )


if __name__ == "__main__":
    unittest.main(verbosity=2)
