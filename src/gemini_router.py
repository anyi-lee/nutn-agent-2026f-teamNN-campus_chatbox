"""Gemini-backed intent router for the Week 06 routing workflow.

The model may only propose one of four routes. The application host validates
the proposal before dispatching any retrieval or business tool.
"""

from __future__ import annotations

import json
import os
import re
from typing import Any, Mapping
from urllib import error, parse, request


DEFAULT_MODEL = "gemini-3.5-flash"
API_ROOT = "https://generativelanguage.googleapis.com/v1beta/models"
ALLOWED_ROUTES = (
    "faculty_query",
    "office_query",
    "email_request",
    "clarify",
)
REASON_CODES = (
    "faculty_information",
    "office_information",
    "email_action",
    "ambiguous_or_unsupported",
)
EXPECTED_REASON_BY_ROUTE = dict(zip(ALLOWED_ROUTES, REASON_CODES, strict=True))
_UNSET = object()
_API_KEY_PATTERN = re.compile(r"^[A-Za-z0-9._-]+$")

ROUTER_SYSTEM_PROMPT = """你是南大資工系校園 Chatbot 的意圖路由器。

你只負責選擇路由，不回答問題、不呼叫工具，也不產生郵件。

合法路由：
- faculty_query：詢問資工系教師姓名、職稱、研究領域或公開聯絡資料。
- office_query：詢問資工系辦公室地址、電話、Email 或辦公時間。
- email_request：明確要求撰寫、寄送或產生給某位老師的 Email。
- clarify：同時包含多種主要意圖、缺少必要對象、超出目前資料範圍，或無法可靠判斷。

規則：
1. 多重主要意圖一律選 clarify，不自行拆成多個工具任務。
2. 課程開設、天氣、其他系所、校級主管與即時位置不在目前資料範圍，選 clarify。
3. 若使用者是在追問上一位教師，context_teacher 會提供姓名，可選 faculty_query。
4. 只能輸出 schema 允許的 route 與 reason_code，不得加入額外欄位。
"""


class GeminiRouterError(RuntimeError):
    """Raised when the router provider or structured response is invalid."""


class GeminiIntentRouter:
    provider = "gemini"
    workflow = "routing"
    evidence_mode = "live"

    def __init__(
        self,
        api_key: str | None | object = _UNSET,
        *,
        model: str | None = None,
        timeout_seconds: int = 20,
    ) -> None:
        if api_key is _UNSET:
            self.api_key = os.getenv("GEMINI_API_KEY", "").strip()
        else:
            self.api_key = str(api_key or "").strip()
        self.model = (model or os.getenv("GEMINI_MODEL") or DEFAULT_MODEL).strip()
        self.timeout_seconds = timeout_seconds

    @property
    def configured(self) -> bool:
        return bool(self.api_key and _API_KEY_PATTERN.fullmatch(self.api_key))

    @property
    def configuration_error(self) -> str | None:
        if self.api_key and not self.configured:
            return "INVALID_API_KEY_FORMAT"
        if not self.api_key:
            return "GEMINI_API_KEY_NOT_CONFIGURED"
        return None

    def route(
        self,
        message: str,
        *,
        context_teacher: str | None = None,
    ) -> dict[str, str]:
        if not self.configured:
            raise GeminiRouterError(
                "GEMINI_API_KEY has an invalid format"
                if self.api_key
                else "GEMINI_API_KEY is not configured"
            )

        router_input = {
            "message": message,
            "context_teacher": context_teacher,
        }
        payload = {
            "systemInstruction": {"parts": [{"text": ROUTER_SYSTEM_PROMPT}]},
            "contents": [
                {
                    "role": "user",
                    "parts": [
                        {
                            "text": json.dumps(
                                router_input,
                                ensure_ascii=False,
                                indent=2,
                            )
                        }
                    ],
                }
            ],
            "generationConfig": {
                "responseFormat": {
                    "text": {
                        "mimeType": "APPLICATION_JSON",
                        "schema": {
                            "type": "object",
                            "properties": {
                                "route": {
                                    "type": "string",
                                    "enum": list(ALLOWED_ROUTES),
                                },
                                "reason_code": {
                                    "type": "string",
                                    "enum": list(REASON_CODES),
                                },
                            },
                            "required": ["route", "reason_code"],
                        },
                    }
                }
            },
        }
        response_payload = self._post(payload)
        try:
            text = response_payload["candidates"][0]["content"]["parts"][0]["text"]
            decision = json.loads(text)
        except (KeyError, IndexError, TypeError, json.JSONDecodeError) as exc:
            raise GeminiRouterError("Gemini returned an invalid router response") from exc

        if not isinstance(decision, Mapping) or set(decision) != {
            "route",
            "reason_code",
        }:
            raise GeminiRouterError("Gemini router response failed the host schema")
        route = str(decision["route"])
        reason_code = str(decision["reason_code"])
        if (
            route not in ALLOWED_ROUTES
            or reason_code not in REASON_CODES
            or EXPECTED_REASON_BY_ROUTE.get(route) != reason_code
        ):
            raise GeminiRouterError("Gemini proposed a route outside the allowlist")
        return {"route": route, "reason_code": reason_code}

    def _post(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        endpoint = f"{API_ROOT}/{parse.quote(self.model, safe='-_.')}:generateContent"
        api_request = request.Request(
            endpoint,
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "x-goog-api-key": self.api_key,
            },
            method="POST",
        )
        try:
            with request.urlopen(api_request, timeout=self.timeout_seconds) as response:
                return json.loads(response.read().decode("utf-8"))
        except error.HTTPError as exc:
            raise GeminiRouterError(f"Gemini router HTTP {exc.code}") from exc
        except (error.URLError, TimeoutError, json.JSONDecodeError) as exc:
            raise GeminiRouterError("Gemini router request failed") from exc
