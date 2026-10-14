"""LangChain candidate backend for the Week 05 orchestration comparison.

Only the read-only ``get_teacher_contact`` tool is exposed to the agent.  The
existing host still owns recipient validation, draft confirmation, sandbox
delivery, and idempotency.  This module is intentionally a replaceable adapter:
setting ``EMAIL_AGENT_BACKEND=manual`` returns to the Week 04 implementation.
"""

from __future__ import annotations

import os
import re
from typing import Any, Callable, Mapping

from gemini_email import (
    EMAIL_SYSTEM_PROMPT,
    GeminiEmailError,
    build_email_prompt,
    validate_email_draft,
)


DEFAULT_MODEL = "gemini-3.5-flash"
_UNSET = object()
_API_KEY_PATTERN = re.compile(r"^[A-Za-z0-9._-]+$")

try:
    from langchain.agents import create_agent
    from langchain.tools import tool
    from langchain_google_genai import ChatGoogleGenerativeAI
    from pydantic import BaseModel, Field

    _LANGCHAIN_IMPORT_ERROR: Exception | None = None
except ImportError as exc:  # pragma: no cover - exercised by config, not the venv suite
    create_agent = None  # type: ignore[assignment]
    tool = None  # type: ignore[assignment]
    ChatGoogleGenerativeAI = None  # type: ignore[assignment]
    BaseModel = object  # type: ignore[assignment,misc]
    Field = None  # type: ignore[assignment]
    _LANGCHAIN_IMPORT_ERROR = exc


if _LANGCHAIN_IMPORT_ERROR is None:

    class TeacherContactInput(BaseModel):
        """Allowed arguments for the only model-visible read tool."""

        teacher_query: str = Field(min_length=1, description="教師完整姓名")


    class EmailDraft(BaseModel):
        """Structured output returned after the grounded tool result."""

        subject: str = Field(min_length=1, max_length=80)
        body: str = Field(min_length=1, max_length=4000)

else:
    TeacherContactInput = object  # type: ignore[assignment,misc]
    EmailDraft = object  # type: ignore[assignment,misc]


LANGCHAIN_SYSTEM_PROMPT = EMAIL_SYSTEM_PROMPT + """

工具與編排規則：
1. 產生草稿前，必須先且只能呼叫一次 get_teacher_contact。
2. teacher_query 必須完全等於使用者已選定的 teacher_name，不得改選教師。
3. 只有工具回傳 status=found 後才能輸出 EmailDraft。
4. 不得要求或嘗試呼叫 send_email；寄送確認由可信 Host 另外處理。
"""


class LangChainEmailGenerator:
    """Use LangChain ``create_agent`` for the model/tool orchestration loop."""

    backend = "langchain"
    framework = "langchain"

    def __init__(
        self,
        api_key: str | None | object = _UNSET,
        *,
        model: str | None = None,
        timeout_seconds: int = 30,
        model_factory: Callable[..., Any] | None = None,
        agent_factory: Callable[..., Any] | None = None,
    ) -> None:
        if api_key is _UNSET:
            self.api_key = os.getenv("GEMINI_API_KEY", "").strip()
        else:
            self.api_key = str(api_key or "").strip()
        self.model = (model or os.getenv("GEMINI_MODEL") or DEFAULT_MODEL).strip()
        self.timeout_seconds = timeout_seconds
        self._model_factory = model_factory
        self._agent_factory = agent_factory

    @property
    def configured(self) -> bool:
        return bool(
            _LANGCHAIN_IMPORT_ERROR is None
            and self.api_key
            and _API_KEY_PATTERN.fullmatch(self.api_key)
        )

    @property
    def configuration_error(self) -> str | None:
        if _LANGCHAIN_IMPORT_ERROR is not None:
            return "LANGCHAIN_DEPENDENCY_MISSING"
        if self.api_key and not _API_KEY_PATTERN.fullmatch(self.api_key):
            return "INVALID_API_KEY_FORMAT"
        return None

    def generate_with_contact_tool(
        self,
        facts: Mapping[str, Any],
        *,
        tool_definition: Mapping[str, Any],
        call_tool: Callable[[str, Mapping[str, Any]], Mapping[str, Any]],
    ) -> tuple[dict[str, str], list[dict[str, Any]]]:
        if not self.configured:
            if self.configuration_error == "LANGCHAIN_DEPENDENCY_MISSING":
                raise GeminiEmailError("LangChain dependencies are not installed")
            raise GeminiEmailError(
                "GEMINI_API_KEY has an invalid format"
                if self.api_key
                else "GEMINI_API_KEY is not configured"
            )
        if tool_definition.get("name") != "get_teacher_contact":
            raise GeminiEmailError("LangChain candidate accepts only get_teacher_contact")

        expected_teacher = str(facts["teacher_name"]).strip()
        tool_events: list[dict[str, Any]] = []

        @tool("get_teacher_contact", args_schema=TeacherContactInput)
        def get_teacher_contact(teacher_query: str) -> dict[str, Any]:
            """從版本化南大資工系官方資料查詢指定教師的公開聯絡資訊。"""

            normalized_query = str(teacher_query or "").strip()
            if normalized_query != expected_teacher:
                raise ValueError("LangChain agent changed the user-confirmed teacher")
            result = dict(
                call_tool(
                    "get_teacher_contact",
                    {"teacher_query": normalized_query},
                )
            )
            if result.get("status") != "found":
                raise ValueError("The contact tool did not return grounded evidence")
            tool_events.append(
                {
                    "stage": "framework_tool_dispatch",
                    "framework": "langchain",
                    "tool": "get_teacher_contact",
                    "arguments": {"teacher_query": normalized_query},
                    "host_validation": "passed",
                    "status": "found",
                }
            )
            return result

        try:
            model_factory = self._model_factory or ChatGoogleGenerativeAI
            chat_model = model_factory(
                model=self.model,
                api_key=self.api_key,
                temperature=1.0,
                retries=0,
                request_timeout=self.timeout_seconds,
                vertexai=False,
            )
            agent_factory = self._agent_factory or create_agent
            agent = agent_factory(
                model=chat_model,
                tools=[get_teacher_contact],
                system_prompt=LANGCHAIN_SYSTEM_PROMPT,
                response_format=EmailDraft,
            )
            result = agent.invoke(
                {
                    "messages": [
                        {
                            "role": "user",
                            "content": (
                                "先呼叫 get_teacher_contact 驗證收件人，再產生結構化草稿。\n\n"
                                + build_email_prompt(facts)
                            ),
                        }
                    ]
                },
                config={"recursion_limit": 8},
            )
        except GeminiEmailError:
            raise
        except Exception as exc:
            safe_name = type(exc).__name__
            raise GeminiEmailError(f"LangChain create_agent failed ({safe_name})") from exc

        if len(tool_events) != 1:
            raise GeminiEmailError(
                "LangChain agent did not execute exactly one grounded contact lookup"
            )
        structured = result.get("structured_response") if isinstance(result, Mapping) else None
        if structured is None:
            raise GeminiEmailError("LangChain agent returned no structured_response")
        if hasattr(structured, "model_dump"):
            structured = structured.model_dump()
        if not isinstance(structured, Mapping):
            raise GeminiEmailError("LangChain agent returned an invalid structured_response")

        draft = validate_email_draft(structured, facts)
        messages = list(result.get("messages") or []) if isinstance(result, Mapping) else []
        model_calls = sum(
            1 for message in messages if type(message).__name__ == "AIMessage"
        )
        trace = [
            {
                "stage": "framework_agent",
                "framework": "langchain",
                "api": "create_agent",
                "status": "completed",
                "model_calls": model_calls,
                "visible_tools": ["get_teacher_contact"],
            },
            *tool_events,
            {
                "stage": "framework_structured_response",
                "framework": "langchain",
                "schema": "EmailDraft",
                "status": "validated",
            },
        ]
        return draft, trace
