"""Application service used by the local campus chatbot UI.

The service is deterministic, reads only the frozen faculty corpus, and never
sends email. It keeps the retrieval trace visible so the UI can show why an
answer was selected.
"""

from __future__ import annotations

import json
import re
import threading
import uuid
from pathlib import Path
from typing import Any, Mapping

from dense_stub import DenseStubRetriever
from email_tools import CampusToolServer, ToolCallError
from email_draft_baseline import PURPOSE_LABELS
from gemini_email import GeminiEmailError, GeminiEmailGenerator
from retrieval_baseline import BM25Retriever


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
FACULTY_DATA_PATH = REPOSITORY_ROOT / "data" / "faculty_chunks.json"
OFFICE_DATA_PATH = REPOSITORY_ROOT / "data" / "office_chunks.json"
SANDBOX_OUTBOX_PATH = REPOSITORY_ROOT / "runtime" / "sandbox_outbox.sqlite3"

LIVE_STATUS_TERMS = (
    "在研究室",
    "研究室",
    "行程",
    "是否在",
    "在嗎",
    "辦公時間",
    "office hour",
    "幾點會在",
)
CONTACT_TERMS = ("email", "e-mail", "mail", "信箱", "郵件", "聯絡", "聯繫", "寄信")
RESEARCH_TERMS = ("研究", "專長", "領域")
TEACHER_FOLLOW_UP_TERMS = (
    *CONTACT_TERMS,
    *RESEARCH_TERMS,
    *LIVE_STATUS_TERMS,
    "職稱",
    "老師",
    "教授",
    "他",
    "這位",
    "加簽",
    "補交",
    "答案",
    "分數",
    "成績",
    "專題",
    "預約",
    "討論",
    "見面",
)
COURSE_OFFERING_TERMS = (
    "有開什麼課",
    "開什麼課",
    "有哪些課",
    "開課",
    "課程列表",
    "這學期的課",
    "這學期課程",
)
OFFICE_QUERY_TERMS = ("系辦", "系辦公室", "資工辦公室")
OFFICE_HOURS_TERMS = (
    "營業時間",
    "辦公時間",
    "上班時間",
    "開放時間",
    "幾點開",
    "幾點關",
    "幾點上班",
    "幾點下班",
    "中午休息",
)
OFFICE_CONTACT_TERMS = ("電話", "分機", "email", "e-mail", "信箱", "地址", "位置", "在哪", "聯絡")
UNSUPPORTED_ADMIN_ROLE_TERMS = (
    "校長",
    "副校長",
    "教務長",
    "學務長",
    "總務長",
    "研發長",
    "院長",
)
SUPPORTED_DEPARTMENT_TERMS = ("資工系", "資訊工程學系")
DEPARTMENT_QUERY_PREFIXES = ("想詢問", "想問", "請問", "想聯繫", "聯繫", "聯絡")
UNIQUE_ROLE_TERMS = ("系主任", "圖資長")
GENERIC_MATCH_TERMS = {
    "email",
    "e-mail",
    "教授",
    "老師",
    "教師",
    "研究",
    "系主任",
    "主任",
    "聯絡",
    "聯繫",
}
MIN_BM25_RAW_SCORE = 2.0
MAX_UNANCHORED_SCORE_RATIO = 0.75


def _contains_any(text: str, terms: tuple[str, ...]) -> bool:
    normalized = text.lower()
    return any(term.lower() in normalized for term in terms)


def _can_reuse_teacher_context(text: str) -> bool:
    """Only carry a teacher forward for a recognizably teacher-related follow-up."""

    return _contains_any(text, TEACHER_FOLLOW_UP_TERMS)


def _mentions_out_of_scope_department_chair(text: str) -> bool:
    """Detect a named non-CSIE department chair before retrieval can mis-rank it."""

    normalized = text
    for prefix in DEPARTMENT_QUERY_PREFIXES:
        normalized = normalized.replace(prefix, "")
    match = re.search(r"([\u4e00-\u9fff]{2,12}系)(?:的)?主任", normalized)
    if match is None:
        return False
    department = match.group(1)
    return not any(term in department for term in SUPPORTED_DEPARTMENT_TERMS)


def _detected_purpose(text: str) -> str:
    rules = (
        (("加簽",), "course_add_request"),
        (("補交",), "late_submission_request"),
        (("答案", "解題"), "answer_request"),
        (("分數", "成績"), "grade_inquiry"),
        (("專題",), "project_inquiry"),
        (("研究", "研究所"), "research_inquiry"),
        (("預約", "討論", "見面"), "meeting_request"),
        (("課程",), "course_question"),
    )
    for keywords, purpose in rules:
        if any(keyword in text for keyword in keywords):
            return purpose
    return "other"


class CampusService:
    """Answer faculty questions and generate grounded email drafts."""

    def __init__(
        self,
        data_path: Path = FACULTY_DATA_PATH,
        *,
        office_data_path: Path = OFFICE_DATA_PATH,
        email_generator: GeminiEmailGenerator | None = None,
        tool_server: CampusToolServer | None = None,
    ) -> None:
        self.document = json.loads(data_path.read_text(encoding="utf-8"))
        self.office_document = json.loads(
            office_data_path.read_text(encoding="utf-8")
        )
        self.office_source = dict(self.office_document["source"])
        self.office_chunk = dict(self.office_document["chunks"][0])
        self.chunks = list(self.document["chunks"])
        self.source = dict(self.document["source"])
        self.chunk_by_id = {chunk["chunk_id"]: chunk for chunk in self.chunks}
        self.teacher_by_name = {chunk["teacher_name"]: chunk for chunk in self.chunks}
        self.bm25 = BM25Retriever(self.chunks)
        self.dense_stub = DenseStubRetriever(self.chunks)
        self.email_generator = email_generator or GeminiEmailGenerator()
        self.tool_server = tool_server or CampusToolServer(
            self.document,
            SANDBOX_OUTBOX_PATH,
        )
        self.pending_drafts: dict[str, dict[str, Any]] = {}
        self._draft_lock = threading.Lock()

    def config(self) -> dict[str, Any]:
        return {
            "app_name": "南大校務通",
            "scope": "資工系教師資訊、系辦公開聯絡資訊與 Email 草稿",
            "retrievers": [
                {"value": "bm25", "label": "BM25 關鍵字檢索"},
                {"value": "dense_stub", "label": "Dense Stub 概念檢索"},
            ],
            "teachers": [
                {"name": chunk["teacher_name"], "title": chunk["title"]}
                for chunk in self.chunks
            ],
            "purposes": [
                {"value": value, "label": label}
                for value, label in PURPOSE_LABELS.items()
            ],
            "source": self.source,
            "sources": [self.source, self.office_source],
            "can_send_email": True,
            "email_delivery": {
                "mode": "sandbox",
                "label": "Sandbox 模擬寄送",
                "real_email_sent": False,
                "requires_confirmation": True,
            },
            "tools": self.tool_server.list_tools()["tools"],
            "email_generation": {
                "provider": (
                    "gemini" if self.email_generator.configured else "local_template"
                ),
                "configured": self.email_generator.configured,
                "model": (
                    self.email_generator.model
                    if self.email_generator.configured
                    else None
                ),
                "configuration_error": getattr(
                    self.email_generator, "configuration_error", None
                ),
                "function_calling": True,
            },
        }

    def _retrieve(self, query: str, retriever: str) -> dict[str, Any]:
        if retriever == "bm25":
            raw_candidates = self.bm25.search(query, top_k=3)
            candidates = [
                {
                    "rank": candidate["rank"],
                    "chunk_id": candidate["chunk_id"],
                    "teacher_name": candidate["chunk"]["teacher_name"],
                    "title": candidate["chunk"]["title"],
                    "score": candidate["normalized_score"],
                    "raw_score": candidate["raw_score"],
                    "score_label": "normalized BM25",
                    "matched_terms": candidate["matched_terms"],
                }
                for candidate in raw_candidates
            ]
            return {
                "model": "bm25",
                "query_concepts": [],
                "is_zero_vector": False,
                "candidates": candidates,
                "has_match": bool(candidates and candidates[0]["score"] > 0),
            }

        if retriever == "dense_stub":
            result = self.dense_stub.search(query, top_k=3)
            candidates = [
                {
                    "rank": candidate["rank"],
                    "chunk_id": candidate["chunk_id"],
                    "teacher_name": self.chunk_by_id[candidate["chunk_id"]]["teacher_name"],
                    "title": self.chunk_by_id[candidate["chunk_id"]]["title"],
                    "score": candidate["cosine_score"],
                    "raw_score": candidate["cosine_score"],
                    "score_label": "cosine",
                    "matched_concepts": candidate["document_active_concepts"],
                }
                for candidate in result["candidates"]
            ]
            return {
                "model": "dense_stub",
                "query_concepts": result["query_active_concepts"],
                "is_zero_vector": result["query_is_zero_vector"],
                "candidates": candidates,
                "has_match": bool(candidates and candidates[0]["score"] > 0),
            }

        raise ValueError("retriever must be 'bm25' or 'dense_stub'")

    def _answer_office_query(self, query: str) -> dict[str, Any]:
        office = self.office_chunk
        asks_hours = _contains_any(query, OFFICE_HOURS_TERMS)
        extensions = "、".join(office["extensions"])
        retrieval = {
            "model": "official_record",
            "query_concepts": ["department_office", "office_hours" if asks_hours else "contact"],
            "is_zero_vector": False,
            "has_match": True,
            "original_query": query,
            "effective_query": query,
            "context_teacher": None,
            "used_context": False,
            "candidates": [
                {
                    "rank": 1,
                    "chunk_id": office["chunk_id"],
                    "teacher_name": "資訊工程學系辦公室",
                    "title": "系辦公開資訊",
                    "score": 1.0,
                    "raw_score": 1.0,
                    "score_label": "official record",
                    "matched_terms": ["系辦"],
                }
            ],
            "evidence_gate": {
                "passed": not asks_hours,
                "failure_code": "OFFICE_HOURS_NOT_PUBLISHED" if asks_hours else None,
                "checks": {
                    "official_source": office["authority"] == "official",
                    "active_record": office["validity"] == "active",
                    "office_contact_published": True,
                    "office_hours_published": office["office_hours"] is not None,
                },
            },
        }
        evidence = self._office_evidence()
        citation = self._office_citation()

        if asks_hours:
            return {
                "status": "insufficient_evidence",
                "answer": (
                    "南大資工系官網目前沒有公布固定的系辦辦公時間，因此無法確認幾點開放或休息。"
                    f"官網公布的系辦電話是 {office['telephone']} 轉 {extensions}，"
                    f"Email 是 {office['public_email']}；前往前建議先聯絡確認。"
                ),
                "evidence": evidence,
                "citations": [citation],
                "retrieval": retrieval,
                "used_context": False,
                "suggested_action": None,
                "detected_teacher": None,
                "error": {"code": "OFFICE_HOURS_NOT_PUBLISHED"},
            }

        return {
            "status": "ok",
            "answer": (
                f"南大資工系辦地址是 {office['address']}；電話 {office['telephone']} 轉 {extensions}，"
                f"Email 是 {office['public_email']}。官網目前沒有公布固定辦公時間。"
            ),
            "evidence": evidence,
            "citations": [citation],
            "retrieval": retrieval,
            "used_context": False,
            "suggested_action": None,
            "detected_teacher": None,
            "error": None,
        }

    def _evaluate_chat_evidence(
        self,
        query: str,
        retrieval: Mapping[str, Any],
        active_teacher: str | None,
    ) -> dict[str, Any]:
        """Decide whether the top retrieval result actually supports an answer."""

        candidates = list(retrieval.get("candidates") or [])
        if not candidates:
            return {
                "passed": False,
                "failure_code": "INSUFFICIENT_EVIDENCE",
                "checks": {"has_candidate": False},
            }

        top = candidates[0]
        top_chunk = self.chunk_by_id[top["chunk_id"]]
        anchored_identity = active_teacher is not None
        unique_role = next(
            (
                role
                for role in UNIQUE_ROLE_TERMS
                if role in query and role in str(top_chunk.get("title", ""))
            ),
            None,
        )
        matched_terms = {
            str(term).lower() for term in top.get("matched_terms", [])
        }
        meaningful_terms = sorted(
            term
            for term in matched_terms
            if len(term) >= 2 and term not in GENERIC_MATCH_TERMS
        )
        identity_consistent = (
            not anchored_identity or top_chunk["teacher_name"] == active_teacher
        )
        source_supported = (
            top_chunk.get("source_id") == self.source.get("source_id")
            and top_chunk.get("authority") == "official"
            and top_chunk.get("validity") == "active"
        )

        top_score = float(top.get("raw_score") or 0.0)
        second_score = (
            float(candidates[1].get("raw_score") or 0.0)
            if len(candidates) > 1
            else 0.0
        )
        score_ratio = second_score / top_score if top_score else 1.0
        if retrieval.get("model") == "bm25":
            confidence_passed = top_score >= MIN_BM25_RAW_SCORE
        else:
            confidence_passed = float(top.get("score") or 0.0) >= 0.5
        unambiguous = score_ratio < MAX_UNANCHORED_SCORE_RATIO

        checks = {
            "has_candidate": True,
            "source_supported": source_supported,
            "identity_consistent": identity_consistent,
            "identity_or_unique_role": bool(anchored_identity or unique_role),
            "meaningful_attribute_match": bool(meaningful_terms),
            "minimum_confidence": confidence_passed,
            "unambiguous": unambiguous,
        }

        failure_code = None
        if not source_supported or not identity_consistent:
            failure_code = "EVIDENCE_CONSTRAINT_FAILED"
        elif (
            _contains_any(query, CONTACT_TERMS)
            and not anchored_identity
            and unique_role is None
        ):
            failure_code = "MISSING_TEACHER_IDENTITY"
        elif not anchored_identity and unique_role is None and not meaningful_terms:
            failure_code = "UNSUPPORTED_QUERY_INTENT"
        elif not anchored_identity and unique_role is None and not confidence_passed:
            failure_code = "LOW_RETRIEVAL_CONFIDENCE"
        elif not anchored_identity and unique_role is None and not unambiguous:
            failure_code = "AMBIGUOUS_EVIDENCE"

        return {
            "passed": failure_code is None,
            "failure_code": failure_code,
            "checks": checks,
            "top_raw_score": round(top_score, 6),
            "second_to_top_ratio": round(score_ratio, 6),
            "meaningful_terms": meaningful_terms,
            "identity_anchor": active_teacher,
            "role_anchor": unique_role,
        }

    def chat(
        self,
        message: str,
        retriever: str = "bm25",
        context_teacher: str | None = None,
    ) -> dict[str, Any]:
        query = message.strip()
        if not query:
            return {
                "status": "invalid_request",
                "answer": "請先輸入想查詢的內容。",
                "error": {"code": "EMPTY_MESSAGE"},
            }

        if _contains_any(query, OFFICE_QUERY_TERMS):
            return self._answer_office_query(query)

        if _contains_any(query, COURSE_OFFERING_TERMS):
            return {
                "status": "insufficient_evidence",
                "answer": (
                    "目前載入的資料只有資工系教師姓名、職稱、研究領域與公開 Email，"
                    "沒有當學期開課資訊，因此無法回答有哪些課。後續需要另外加入官方課程資料來源。"
                ),
                "evidence": None,
                "citations": [],
                "retrieval": None,
                "used_context": False,
                "suggested_action": None,
                "error": {"code": "OUT_OF_SCOPE_SOURCE"},
            }

        if _contains_any(query, UNSUPPORTED_ADMIN_ROLE_TERMS):
            return {
                "status": "insufficient_evidence",
                "answer": (
                    "目前載入的資料只有資工系教師姓名、職稱、研究領域與公開 Email，"
                    "沒有校級行政主管的聯絡資料，因此無法確認校長或其他行政主管的聯絡方式。"
                    "需要另外加入臺南大學官方行政單位資料來源後才能回答。"
                ),
                "evidence": None,
                "citations": [self._source_citation()],
                "retrieval": None,
                "used_context": False,
                "suggested_action": None,
                "detected_teacher": None,
                "error": {"code": "OUT_OF_SCOPE_ADMIN_ROLE"},
            }

        if _mentions_out_of_scope_department_chair(query):
            return {
                "status": "insufficient_evidence",
                "answer": (
                    "目前載入的來源只有資訊工程學系教師資料，沒有國文系或其他系所的主管資料，"
                    "因此無法確認該系主任是誰或提供聯絡方式。"
                    "需要另外加入該系官方網站資料後才能回答。"
                ),
                "evidence": None,
                "citations": [self._source_citation()],
                "retrieval": None,
                "used_context": False,
                "suggested_action": None,
                "detected_teacher": None,
                "error": {"code": "OUT_OF_SCOPE_DEPARTMENT"},
            }

        explicit_teacher = next(
            (name for name in self.teacher_by_name if name in query),
            None,
        )
        valid_context_teacher = (
            context_teacher if context_teacher in self.teacher_by_name else None
        )
        used_context = (
            explicit_teacher is None
            and valid_context_teacher is not None
            and _can_reuse_teacher_context(query)
        )
        active_teacher = explicit_teacher or valid_context_teacher
        retrieval_query = f"{active_teacher} {query}" if used_context else query

        retrieval = self._retrieve(retrieval_query, retriever)
        retrieval["original_query"] = query
        retrieval["effective_query"] = retrieval_query
        retrieval["context_teacher"] = valid_context_teacher
        retrieval["used_context"] = used_context
        if not retrieval["has_match"]:
            return {
                "status": "insufficient_evidence",
                "answer": "目前的資工系教師資料中找不到足以回答這個問題的證據。你可以改用教師全名，或查看官方系網。",
                "evidence": None,
                "citations": [self._source_citation()],
                "retrieval": retrieval,
                "used_context": used_context,
                "suggested_action": None,
                "error": {"code": "INSUFFICIENT_EVIDENCE"},
            }

        evidence_gate = self._evaluate_chat_evidence(
            query,
            retrieval,
            active_teacher,
        )
        retrieval["evidence_gate"] = evidence_gate
        if not evidence_gate["passed"]:
            failure_code = str(evidence_gate["failure_code"])
            answer_by_code = {
                "MISSING_TEACHER_IDENTITY": (
                    "目前沒有指定教師，無法確認你想聯絡哪一位。"
                    "請提供教師全名，或先查詢明確的職務名稱。"
                ),
                "UNSUPPORTED_QUERY_INTENT": (
                    "檢索結果只有少量共通詞，無法證明它真的能回答這個問題。"
                    "請改用教師全名、研究領域或明確職務查詢。"
                ),
                "LOW_RETRIEVAL_CONFIDENCE": (
                    "目前檢索分數不足，沒有足夠證據支持回答。"
                    "請補充教師全名或更具體的研究領域。"
                ),
                "AMBIGUOUS_EVIDENCE": (
                    "目前有多筆相近的教師資料，Top 1 沒有明顯領先，"
                    "因此不直接猜測。請補充教師姓名或更具體的研究方向。"
                ),
                "EVIDENCE_CONSTRAINT_FAILED": (
                    "檢索結果未通過來源或身分一致性檢查，因此停止回答。"
                ),
            }
            return {
                "status": "insufficient_evidence",
                "answer": answer_by_code.get(
                    failure_code,
                    "目前沒有足夠證據支持回答。",
                ),
                "evidence": None,
                "citations": [self._source_citation()],
                "retrieval": retrieval,
                "used_context": used_context,
                "suggested_action": None,
                "detected_teacher": None,
                "error": {"code": failure_code},
            }

        top_chunk = self.chunk_by_id[retrieval["candidates"][0]["chunk_id"]]
        if _contains_any(query, LIVE_STATUS_TERMS):
            return {
                "status": "insufficient_evidence",
                "answer": (
                    f"我找到的是{top_chunk['teacher_name']}老師的公開教師資料，"
                    "但官方頁面沒有即時行程或目前是否在研究室的資訊，因此不能替你推測。"
                ),
                "evidence": self._public_evidence(top_chunk),
                "citations": [self._chunk_citation(top_chunk)],
                "retrieval": retrieval,
                "used_context": used_context,
                "suggested_action": "email_draft",
                "detected_teacher": top_chunk["teacher_name"],
                "detected_purpose": "meeting_request",
                "error": {"code": "INSUFFICIENT_EVIDENCE"},
            }

        if _contains_any(query, RESEARCH_TERMS):
            areas = "、".join(top_chunk["research_areas"])
            answer = (
                f"{top_chunk['teacher_name']}老師目前職稱為{top_chunk['title']}。"
                f"官方系網列出的研究領域包括：{areas}。"
            )
        elif _contains_any(query, CONTACT_TERMS):
            answer = (
                f"{top_chunk['teacher_name']}老師的公開 Email 是 "
                f"{top_chunk['public_email']}。這筆資料來自資工系官方教師頁面。"
            )
        else:
            areas = "、".join(top_chunk["research_areas"][:3])
            answer = (
                f"我找到{top_chunk['teacher_name']}老師，職稱是{top_chunk['title']}；"
                f"主要研究領域包含{areas}。若要聯絡老師，我也可以協助產生 Email 草稿。"
            )

        wants_email = _contains_any(query, ("寄信", "郵件", "email", "e-mail"))
        return {
            "status": "ok",
            "answer": answer,
            "evidence": self._public_evidence(top_chunk),
            "citations": [self._chunk_citation(top_chunk)],
            "retrieval": retrieval,
            "used_context": used_context,
            "suggested_action": "email_draft" if wants_email else None,
            "detected_teacher": top_chunk["teacher_name"],
            "detected_purpose": _detected_purpose(query),
            "error": None,
        }

    def create_email_draft(self, payload: Mapping[str, Any]) -> tuple[int, dict[str, Any]]:
        normalized = {
            key: value.strip() if isinstance(value, str) else value
            for key, value in payload.items()
        }
        required = ("teacher_name", "purpose", "student_name", "request_details")
        missing = [field for field in required if not normalized.get(field)]
        if missing:
            return 422, {
                "status": "invalid_request",
                "error": {"code": "MISSING_REQUIRED_FIELD", "missing_fields": missing},
                "reason": "請填寫所有必要欄位。",
            }

        purpose = str(normalized["purpose"])
        if purpose not in PURPOSE_LABELS:
            return 422, {
                "status": "invalid_request",
                "error": {"code": "INVALID_PURPOSE"},
                "reason": "寄信目的不在允許清單中。",
            }

        details = str(normalized["request_details"])
        if len(details) < 5:
            return 422, {
                "status": "invalid_request",
                "error": {"code": "INVALID_REQUEST_DETAILS"},
                "reason": "詢問內容至少需要 5 個字。",
            }

        contact_result = self.tool_server.call_tool(
            "get_teacher_contact",
            {"teacher_query": str(normalized["teacher_name"])},
        )
        if contact_result["status"] != "found":
            return 404, {
                "status": "not_found",
                "error": {"code": "TEACHER_NOT_FOUND"},
                "reason": "目前教師資料中找不到完全相符的姓名。",
            }
        contact = contact_result["teacher"]
        teacher = self.chunk_by_id[contact["teacher_id"]]

        department = str(normalized.get("student_department") or "資訊工程學系")
        grade = str(normalized.get("student_grade") or "")
        identity = f"{department}{grade}"
        student_name = str(normalized["student_name"])
        background = str(normalized.get("background") or "")
        draft_content = self._local_email_content(
            teacher=teacher,
            purpose=purpose,
            student_name=student_name,
            identity=identity,
            details=details,
            background=background,
        )
        generation_provider = "local_template"
        generation_warning = None
        generation_failure = None
        gemini_tool_trace: list[dict[str, Any]] = []
        if self.email_generator.configured:
            try:
                facts = {
                    "teacher_name": teacher["teacher_name"],
                    "teacher_title": teacher["title"],
                    "purpose": purpose,
                    "purpose_label": PURPOSE_LABELS[purpose],
                    "student_name": student_name,
                    "student_identity": identity,
                    "request_details": details,
                    "background": background or None,
                }
                if hasattr(self.email_generator, "generate_with_contact_tool"):
                    contact_tool = next(
                        tool
                        for tool in self.tool_server.list_tools()["tools"]
                        if tool["name"] == "get_teacher_contact"
                    )
                    draft_content, gemini_tool_trace = (
                        self.email_generator.generate_with_contact_tool(
                            facts,
                            tool_definition=contact_tool,
                            call_tool=self.tool_server.call_tool,
                        )
                    )
                else:
                    draft_content = self.email_generator.generate(facts)
                generation_provider = "gemini"
            except GeminiEmailError as error:
                generation_failure = str(error)
                generation_warning = (
                    f"Gemini 暫時無法使用（{generation_failure}），已改用本機模板產生草稿。"
                )

        draft_id = f"draft-{uuid.uuid4().hex[:16]}"
        request_id = f"mail-{uuid.uuid4().hex}"
        pending_draft = {
            "draft_id": draft_id,
            "request_id": request_id,
            "teacher_id": contact["teacher_id"],
            "to": contact["public_email"],
            "subject": draft_content["subject"],
            "body": draft_content["body"],
        }
        with self._draft_lock:
            self.pending_drafts[draft_id] = pending_draft

        return 200, {
            "status": "draft_created",
            "draft_id": draft_id,
            "request_id": request_id,
            "teacher": self._public_evidence(teacher),
            "email_draft": {
                "to": teacher["public_email"],
                "subject": draft_content["subject"],
                "body": draft_content["body"],
            },
            "citations": [self._chunk_citation(teacher)],
            "requires_confirmation": True,
            "send_status": "not_sent",
            "reason": "收件人已由官方教師資料驗證；目前只建立草稿，不會寄出。",
            "delivery": {
                "mode": "sandbox",
                "label": "Sandbox 模擬寄送",
                "real_email_sent": False,
            },
            "tool_trace": [
                {
                    "tool": "get_teacher_contact",
                    "kind": "read",
                    "status": "found",
                    "source_id": contact_result["source"]["source_id"],
                    "stage": "host_prevalidation",
                },
                *gemini_tool_trace,
            ],
            "generation": {
                "provider": generation_provider,
                "model": (
                    self.email_generator.model
                    if generation_provider == "gemini"
                    else None
                ),
                "fallback_used": generation_warning is not None,
                "warning": generation_warning,
                "evidence_status": (
                    "LIVE_PASS"
                    if generation_provider == "gemini"
                    else ("LIVE_FAIL" if self.email_generator.configured else "LIVE_NOT_RUN")
                ),
                "failure_reason": generation_failure,
            },
            "error": None,
        }

    def send_email_draft(self, payload: Mapping[str, Any]) -> tuple[int, dict[str, Any]]:
        """Write an approved, server-held draft to the sandbox outbox."""

        draft_id = str(payload.get("draft_id") or "").strip()
        if not draft_id:
            return 422, {
                "status": "invalid_request",
                "error": {"code": "MISSING_DRAFT_ID"},
                "reason": "缺少 draft_id。",
            }
        if payload.get("confirmed") is not True:
            return 409, {
                "status": "confirmation_required",
                "error": {"code": "CONFIRMATION_REQUIRED"},
                "reason": "請先確認收件人、主旨與正文，再執行 Sandbox 寄送。",
            }

        with self._draft_lock:
            draft = self.pending_drafts.get(draft_id)
        if draft is None:
            return 404, {
                "status": "not_found",
                "error": {"code": "DRAFT_NOT_FOUND"},
                "reason": "找不到這份草稿，請重新產生。",
            }

        try:
            receipt = self.tool_server.call_tool(
                "send_email",
                {
                    "teacher_id": draft["teacher_id"],
                    "to": draft["to"],
                    "subject": draft["subject"],
                    "body": draft["body"],
                    "request_id": draft["request_id"],
                    "confirmed": True,
                },
            )
        except ToolCallError as error:
            return 409, {
                "status": "tool_rejected",
                "error": {"code": error.code},
                "reason": error.message,
                "send_status": "not_sent",
            }

        return 200, {
            "status": receipt["status"],
            "send_status": receipt["status"],
            "delivery": {
                "mode": "sandbox",
                "real_email_sent": False,
                "notice": "已寫入本機 Sandbox outbox，沒有寄到真實信箱。",
            },
            "receipt": receipt,
            "tool_trace": [
                {
                    "tool": "send_email",
                    "kind": "write",
                    "status": receipt["status"],
                    "request_id": receipt["request_id"],
                }
            ],
            "error": None,
        }

    def get_email_status(self, request_id: str) -> tuple[int, dict[str, Any]]:
        """Safely resolve an uncertain write by its idempotency key."""

        try:
            result = self.tool_server.call_tool(
                "get_email_status",
                {"request_id": request_id},
            )
        except ToolCallError as error:
            return 422, {
                "status": "invalid_request",
                "error": {"code": error.code},
                "reason": error.message,
            }
        return 200, {
            **result,
            "tool_trace": [
                {
                    "tool": "get_email_status",
                    "kind": "read",
                    "status": result["status"],
                    "request_id": request_id,
                }
            ],
        }

    @staticmethod
    def _local_email_content(
        *,
        teacher: Mapping[str, Any],
        purpose: str,
        student_name: str,
        identity: str,
        details: str,
        background: str,
    ) -> dict[str, str]:
        clean_details = details.rstrip("。！？!? ")
        if purpose == "course_add_request":
            course_name = clean_details.removesuffix("想加簽").strip()
            if course_name != clean_details and course_name:
                request_paragraph = (
                    f"想請問老師，我希望加簽「{course_name}」課程，"
                    "不知道目前是否仍可提出申請。若可以，想再請教加簽方式及需要完成的程序。"
                )
            else:
                request_paragraph = (
                    f"想請問老師，{clean_details}。若目前仍可提出申請，"
                    "想再請教加簽方式及需要完成的程序。"
                )
            subject = "課程加簽詢問"
        elif purpose == "late_submission_request":
            request_paragraph = (
                f"想向老師說明，{clean_details}。若仍有補交的可能，"
                "再請老師告知可行的處理方式；若無法補交，我也會尊重課程規定。"
            )
            subject = "作業補交申請"
        else:
            request_paragraph = f"想向老師請教以下事項：{clean_details}。再請老師於方便時回覆。"
            subject = PURPOSE_LABELS[purpose]

        paragraphs = [
            f"{teacher['teacher_name'][0]}老師您好：",
            f"我是{identity}學生{student_name}。{request_paragraph}",
        ]
        if background:
            paragraphs.append(f"補充說明：{background.rstrip('。')}。")
        paragraphs.extend(
            [
                "感謝老師撥冗閱讀。",
                f"學生 {student_name} 敬上",
            ]
        )
        return {"subject": subject, "body": "\n\n".join(paragraphs)}

    def _public_evidence(self, chunk: Mapping[str, Any]) -> dict[str, Any]:
        return {
            "chunk_id": chunk["chunk_id"],
            "teacher_name": chunk["teacher_name"],
            "title": chunk["title"],
            "research_areas": chunk["research_areas"],
            "public_email": chunk["public_email"],
            "authority": chunk["authority"],
            "validity": chunk["validity"],
        }

    def _office_evidence(self) -> dict[str, Any]:
        office = self.office_chunk
        return {
            "chunk_id": office["chunk_id"],
            "office_name": office["office_name"],
            "address": office["address"],
            "telephone": office["telephone"],
            "extensions": office["extensions"],
            "fax": office["fax"],
            "public_email": office["public_email"],
            "office_hours": office["office_hours"],
            "office_hours_status": office["office_hours_status"],
            "authority": office["authority"],
            "validity": office["validity"],
        }

    def _office_citation(self) -> dict[str, str]:
        office = self.office_chunk
        return {
            "source_id": office["source_id"],
            "chunk_id": office["chunk_id"],
            "label": "南大資工系－官方網站",
            "url": office["source_url"],
        }

    def _chunk_citation(self, chunk: Mapping[str, Any]) -> dict[str, str]:
        return {
            "source_id": chunk["source_id"],
            "chunk_id": chunk["chunk_id"],
            "label": "南大資工系－師資陣容",
            "url": chunk["source_url"],
        }

    def _source_citation(self) -> dict[str, str]:
        return {
            "source_id": self.source["source_id"],
            "chunk_id": "",
            "label": "南大資工系－師資陣容",
            "url": self.source["source_url"],
        }
