"""Tests for the service backing the local UI."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT / "src"))

from campus_service import CampusService  # noqa: E402
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


if __name__ == "__main__":
    unittest.main(verbosity=2)
