"""Offline acceptance tests for the Week 05 LangChain candidate backend."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

try:
    from langchain_core.language_models.chat_models import BaseChatModel
    from langchain_core.messages import AIMessage, ToolMessage
    from langchain_core.outputs import ChatGeneration, ChatResult
    from pydantic import PrivateAttr

    LANGCHAIN_AVAILABLE = True
except ImportError:
    LANGCHAIN_AVAILABLE = False
    BaseChatModel = object


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT / "src"))

from campus_service import CampusService  # noqa: E402
from gemini_email import GeminiEmailError  # noqa: E402
from langchain_email import LangChainEmailGenerator  # noqa: E402


FACTS = {
    "teacher_name": "林朝興",
    "teacher_title": "教授兼系主任",
    "purpose": "course_add_request",
    "purpose_label": "申請課程加簽",
    "student_name": "測試學生",
    "student_identity": "資訊工程學系大四",
    "request_details": "多媒體想加簽",
    "background": None,
}

CONTACT_TOOL = {
    "name": "get_teacher_contact",
    "description": "查詢教師公開聯絡資料",
    "inputSchema": {
        "type": "object",
        "properties": {"teacher_query": {"type": "string"}},
        "required": ["teacher_query"],
        "additionalProperties": False,
    },
}

GOOD_DRAFT = {
    "subject": "多媒體課程加簽詢問",
    "body": (
        "林老師您好：\n\n"
        "我是資訊工程學系大四學生測試學生，希望申請多媒體課程加簽。\n\n"
        "若仍可提出申請，再麻煩老師告知相關程序。\n\n"
        "感謝老師撥冗閱讀。\n\n學生 測試學生 敬上"
    ),
}


def fake_model_factory(**kwargs):
    return {"fake_model_options": kwargs}


def found_contact(name, arguments):
    if name != "get_teacher_contact":
        raise AssertionError("only the read tool may be called")
    return {
        "status": "found",
        "teacher": {
            "teacher_id": "faculty-mikelin",
            "name": arguments["teacher_query"],
            "public_email": "mikelin@mail.nutn.edu.tw",
        },
        "source": {"source_id": "nutn-csie-faculty"},
    }


class FakeAgent:
    def __init__(self, contact_tool, *, query="林朝興", invoke_tool=True, draft=None):
        self.contact_tool = contact_tool
        self.query = query
        self.invoke_tool = invoke_tool
        self.draft = GOOD_DRAFT if draft is None else draft

    def invoke(self, payload, config):
        if self.invoke_tool:
            self.contact_tool.invoke({"teacher_query": self.query})
        return {"messages": [], "structured_response": self.draft}


if LANGCHAIN_AVAILABLE:
    class ScriptedToolCallingModel(BaseChatModel):
        """Deterministic model used to exercise the real create_agent runtime offline."""

        _calls: int = PrivateAttr(default=0)

        @property
        def _llm_type(self):
            return "week05-scripted-tool-calling-model"

        def bind_tools(self, tools, *, tool_choice=None, **kwargs):
            return self

        def _generate(self, messages, stop=None, run_manager=None, **kwargs):
            self._calls += 1
            has_contact_result = any(
                isinstance(message, ToolMessage)
                and message.name == "get_teacher_contact"
                for message in messages
            )
            if not has_contact_result:
                message = AIMessage(
                    content="",
                    tool_calls=[
                        {
                            "name": "get_teacher_contact",
                            "args": {"teacher_query": "林朝興"},
                            "id": "offline-contact-001",
                            "type": "tool_call",
                        }
                    ],
                )
            else:
                message = AIMessage(
                    content="",
                    tool_calls=[
                        {
                            "name": "EmailDraft",
                            "args": GOOD_DRAFT,
                            "id": "offline-draft-001",
                            "type": "tool_call",
                        }
                    ],
                )
            return ChatResult(generations=[ChatGeneration(message=message)])
else:
    class ScriptedToolCallingModel:
        pass


@unittest.skipUnless(LANGCHAIN_AVAILABLE, "Week 5 LangChain dependencies are not installed")
class LangChainEmailGeneratorTests(unittest.TestCase):
    def make_generator(self, agent_builder):
        def agent_factory(**kwargs):
            self.agent_options = kwargs
            return agent_builder(kwargs["tools"][0])

        return LangChainEmailGenerator(
            api_key="test-secret",
            model="gemini-test",
            model_factory=fake_model_factory,
            agent_factory=agent_factory,
        )

    def test_candidate_uses_create_agent_contract_and_read_tool(self) -> None:
        generator = self.make_generator(lambda contact_tool: FakeAgent(contact_tool))

        draft, trace = generator.generate_with_contact_tool(
            FACTS,
            tool_definition=CONTACT_TOOL,
            call_tool=found_contact,
        )

        self.assertEqual(draft, GOOD_DRAFT)
        self.assertEqual(generator.backend, "langchain")
        self.assertEqual(len(self.agent_options["tools"]), 1)
        self.assertEqual(self.agent_options["tools"][0].name, "get_teacher_contact")
        self.assertNotIn("send_email", [tool.name for tool in self.agent_options["tools"]])
        self.assertEqual(trace[0]["api"], "create_agent")
        self.assertEqual(trace[1]["host_validation"], "passed")
        self.assertEqual(trace[-1]["status"], "validated")

    def test_real_create_agent_runtime_executes_tool_loop_offline(self) -> None:
        generator = LangChainEmailGenerator(
            api_key="test-secret",
            model="scripted-test-model",
            model_factory=lambda **kwargs: ScriptedToolCallingModel(),
        )

        draft, trace = generator.generate_with_contact_tool(
            FACTS,
            tool_definition=CONTACT_TOOL,
            call_tool=found_contact,
        )

        self.assertEqual(draft, GOOD_DRAFT)
        self.assertEqual(trace[0]["api"], "create_agent")
        self.assertGreaterEqual(trace[0]["model_calls"], 2)
        self.assertEqual(trace[1]["tool"], "get_teacher_contact")

    def test_candidate_rejects_changed_teacher_before_host_tool(self) -> None:
        calls = []
        generator = self.make_generator(
            lambda contact_tool: FakeAgent(contact_tool, query="其他老師")
        )

        with self.assertRaises(GeminiEmailError) as raised:
            generator.generate_with_contact_tool(
                FACTS,
                tool_definition=CONTACT_TOOL,
                call_tool=lambda name, arguments: calls.append((name, arguments)),
            )

        self.assertEqual(calls, [])
        self.assertIn("LangChain create_agent failed", str(raised.exception))

    def test_candidate_rejects_agent_that_skips_grounded_tool(self) -> None:
        generator = self.make_generator(
            lambda contact_tool: FakeAgent(contact_tool, invoke_tool=False)
        )

        with self.assertRaisesRegex(GeminiEmailError, "exactly one grounded"):
            generator.generate_with_contact_tool(
                FACTS,
                tool_definition=CONTACT_TOOL,
                call_tool=found_contact,
            )

    def test_candidate_rejects_ungrounded_tool_result(self) -> None:
        generator = self.make_generator(lambda contact_tool: FakeAgent(contact_tool))

        with self.assertRaises(GeminiEmailError):
            generator.generate_with_contact_tool(
                FACTS,
                tool_definition=CONTACT_TOOL,
                call_tool=lambda name, arguments: {"status": "not_found"},
            )

    def test_candidate_uses_same_host_quality_gate(self) -> None:
        bad_draft = {
            "subject": "申請加簽",
            "body": "林老師您好：測試學生想請教以下事項：多媒體想加簽。",
        }
        generator = self.make_generator(
            lambda contact_tool: FakeAgent(contact_tool, draft=bad_draft)
        )

        with self.assertRaisesRegex(GeminiEmailError, "quality gate"):
            generator.generate_with_contact_tool(
                FACTS,
                tool_definition=CONTACT_TOOL,
                call_tool=found_contact,
            )

    def test_service_reports_langchain_backend_without_changing_write_gate(self) -> None:
        generator = self.make_generator(lambda contact_tool: FakeAgent(contact_tool))
        service = CampusService(email_generator=generator)

        status, response = service.create_email_draft(
            {
                "teacher_name": "林朝興",
                "purpose": "course_add_request",
                "student_name": "測試學生",
                "student_department": "資訊工程學系",
                "student_grade": "大四",
                "request_details": "多媒體想加簽",
            }
        )
        rejected_status, rejected = service.send_email_draft(
            {"draft_id": response["draft_id"], "confirmed": False}
        )

        self.assertEqual(status, 200)
        self.assertEqual(response["generation"]["provider"], "gemini")
        self.assertEqual(response["generation"]["backend"], "langchain")
        self.assertEqual(response["generation"]["framework"], "langchain")
        self.assertEqual(response["send_status"], "not_sent")
        self.assertEqual(rejected_status, 409)
        self.assertEqual(rejected["error"]["code"], "CONFIRMATION_REQUIRED")


if __name__ == "__main__":
    unittest.main(verbosity=2)
