"""Offline tests for the Gemini email client request and response contract."""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path
from unittest.mock import patch


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT / "src"))

from gemini_email import GeminiEmailError, GeminiEmailGenerator  # noqa: E402


FACTS = {
    "teacher_name": "林朝興",
    "teacher_title": "教授兼系主任",
    "purpose": "course_add_request",
    "purpose_label": "申請課程加簽",
    "student_name": "李安以",
    "student_identity": "資訊工程學系大四",
    "request_details": "多媒體想加簽",
    "background": None,
}


class FakeResponse:
    def __init__(self, payload):
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False

    def read(self):
        return json.dumps(self.payload, ensure_ascii=False).encode("utf-8")


class GeminiEmailGeneratorTests(unittest.TestCase):
    def test_api_key_may_contain_periods(self) -> None:
        generator = GeminiEmailGenerator(api_key="example.key_123-abc")

        self.assertTrue(generator.configured)
        self.assertIsNone(generator.configuration_error)

    def test_non_ascii_api_key_is_rejected_before_http_request(self) -> None:
        generator = GeminiEmailGenerator(api_key="、invalid-test-key")

        self.assertFalse(generator.configured)
        self.assertEqual(generator.configuration_error, "INVALID_API_KEY_FORMAT")
        with patch("gemini_email.request.urlopen") as urlopen:
            with self.assertRaises(GeminiEmailError):
                generator.generate(FACTS)
            urlopen.assert_not_called()

    @patch("gemini_email.request.urlopen")
    def test_structured_draft_request_and_response(self, urlopen) -> None:
        generated = {
            "subject": "多媒體課程加簽詢問",
            "body": "林老師您好：\n\n我是學生李安以，想請問加簽方式。\n\n學生 李安以 敬上",
        }
        urlopen.return_value = FakeResponse(
            {
                "candidates": [
                    {"content": {"parts": [{"text": json.dumps(generated, ensure_ascii=False)}]}}
                ]
            }
        )
        generator = GeminiEmailGenerator(api_key="test-secret", model="gemini-test")

        result = generator.generate(FACTS)

        self.assertEqual(result, generated)
        api_request = urlopen.call_args.args[0]
        self.assertNotIn("test-secret", api_request.full_url)
        self.assertEqual(api_request.get_header("X-goog-api-key"), "test-secret")
        request_body = json.loads(api_request.data.decode("utf-8"))
        system_instruction = request_body["systemInstruction"]["parts"][0]["text"]
        self.assertIn("不是複製學生輸入", system_instruction)
        self.assertIn("多媒體系統課程加簽詢問", system_instruction)
        response_format = request_body["generationConfig"]["responseFormat"]
        self.assertEqual(response_format["text"]["mimeType"], "APPLICATION_JSON")

    @patch("gemini_email.request.urlopen")
    def test_function_call_round_trip_uses_host_validated_read_tool(self, urlopen) -> None:
        generated = {
            "subject": "多媒體系統課程加簽詢問",
            "body": (
                "林老師您好：\n\n我是資訊工程學系大四學生李安以，"
                "想請問多媒體系統課程的加簽程序。\n\n"
                "感謝老師撥冗閱讀。\n\n學生 李安以 敬上"
            ),
        }
        urlopen.side_effect = [
            FakeResponse(
                {
                    "candidates": [
                        {
                            "content": {
                                "role": "model",
                                "parts": [
                                    {
                                        "functionCall": {
                                            "id": "call-contact-001",
                                            "name": "get_teacher_contact",
                                            "args": {"teacher_query": "林朝興"},
                                        }
                                    }
                                ],
                            }
                        }
                    ]
                }
            ),
            FakeResponse(
                {
                    "candidates": [
                        {"content": {"parts": [{"text": json.dumps(generated, ensure_ascii=False)}]}}
                    ]
                }
            ),
        ]
        calls = []

        def call_tool(name, arguments):
            calls.append((name, dict(arguments)))
            return {
                "status": "found",
                "teacher": {
                    "teacher_id": "faculty-mikelin",
                    "name": "林朝興",
                    "public_email": "mikelin@mail.nutn.edu.tw",
                },
            }

        generator = GeminiEmailGenerator(api_key="test-secret", model="gemini-test")
        result, trace = generator.generate_with_contact_tool(
            FACTS,
            tool_definition={
                "name": "get_teacher_contact",
                "description": "查詢教師公開聯絡資料",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "teacher_query": {
                            "type": "string",
                            "description": "教師姓名",
                            "minLength": 1,
                        }
                    },
                    "required": ["teacher_query"],
                    "additionalProperties": False,
                },
            },
            call_tool=call_tool,
        )

        self.assertEqual(result, generated)
        self.assertEqual(calls, [("get_teacher_contact", {"teacher_query": "林朝興"})])
        self.assertEqual(trace[0]["stage"], "functionCall")
        self.assertEqual(trace[1]["stage"], "functionResponse")
        proposal_body = json.loads(urlopen.call_args_list[0].args[0].data.decode("utf-8"))
        completion_body = json.loads(urlopen.call_args_list[1].args[0].data.decode("utf-8"))
        self.assertEqual(
            proposal_body["tools"][0]["functionDeclarations"][0]["name"],
            "get_teacher_contact",
        )
        function_schema = proposal_body["tools"][0]["functionDeclarations"][0]["parameters"]
        self.assertNotIn("additionalProperties", function_schema)
        self.assertNotIn("minLength", function_schema["properties"]["teacher_query"])
        function_response = completion_body["contents"][2]["parts"][0]["functionResponse"]
        self.assertEqual(function_response["response"]["status"], "found")
        self.assertEqual(function_response["id"], "call-contact-001")
        self.assertEqual(
            completion_body["tools"][0]["functionDeclarations"][0]["name"],
            "get_teacher_contact",
        )
        self.assertEqual(
            completion_body["toolConfig"]["functionCallingConfig"]["mode"],
            "NONE",
        )

    @patch("gemini_email.request.urlopen")
    def test_function_call_cannot_change_confirmed_teacher(self, urlopen) -> None:
        urlopen.return_value = FakeResponse(
            {
                "candidates": [
                    {
                        "content": {
                            "role": "model",
                            "parts": [
                                {
                                    "functionCall": {
                                        "name": "get_teacher_contact",
                                        "args": {"teacher_query": "其他老師"},
                                    }
                                }
                            ],
                        }
                    }
                ]
            }
        )
        generator = GeminiEmailGenerator(api_key="test-secret")

        with self.assertRaises(GeminiEmailError):
            generator.generate_with_contact_tool(
                FACTS,
                tool_definition={
                    "name": "get_teacher_contact",
                    "description": "查詢教師公開聯絡資料",
                    "inputSchema": {"type": "object"},
                },
                call_tool=lambda name, arguments: self.fail("tool must not run"),
            )

    @patch("gemini_email.request.urlopen")
    def test_low_quality_template_like_draft_is_rejected(self, urlopen) -> None:
        generated = {
            "subject": "申請課程加簽",
            "body": (
                "林老師您好：\n\n我是學生李安以。"
                "想向老師請教以下事項：多媒體想加簽。\n\n學生 李安以 敬上"
            ),
        }
        urlopen.return_value = FakeResponse(
            {
                "candidates": [
                    {"content": {"parts": [{"text": json.dumps(generated, ensure_ascii=False)}]}}
                ]
            }
        )
        generator = GeminiEmailGenerator(api_key="test-secret")

        with self.assertRaises(GeminiEmailError):
            generator.generate(FACTS)

    @patch("gemini_email.request.urlopen")
    def test_invalid_structured_response_is_rejected(self, urlopen) -> None:
        urlopen.return_value = FakeResponse({"candidates": []})
        generator = GeminiEmailGenerator(api_key="test-secret")

        with self.assertRaises(GeminiEmailError):
            generator.generate(FACTS)


if __name__ == "__main__":
    unittest.main(verbosity=2)
