"""Application service used by the local campus chatbot UI.

The service is deterministic, reads only the frozen faculty corpus, and never
sends email. It keeps the retrieval trace visible so the UI can show why an
answer was selected.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping

from dense_stub import DenseStubRetriever
from email_draft_baseline import PURPOSE_LABELS
from gemini_email import GeminiEmailError, GeminiEmailGenerator
from retrieval_baseline import BM25Retriever


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
FACULTY_DATA_PATH = REPOSITORY_ROOT / "data" / "faculty_chunks.json"

LIVE_STATUS_TERMS = ("今天", "現在", "幾點", "在研究室", "行程", "是否在")
CONTACT_TERMS = ("email", "e-mail", "mail", "信箱", "郵件", "聯絡", "聯繫", "寄信")
RESEARCH_TERMS = ("研究", "專長", "領域")
COURSE_OFFERING_TERMS = (
    "有開什麼課",
    "開什麼課",
    "有哪些課",
    "開課",
    "課程列表",
    "這學期的課",
    "這學期課程",
)


def _contains_any(text: str, terms: tuple[str, ...]) -> bool:
    normalized = text.lower()
    return any(term.lower() in normalized for term in terms)


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
        email_generator: GeminiEmailGenerator | None = None,
    ) -> None:
        self.document = json.loads(data_path.read_text(encoding="utf-8"))
        self.chunks = list(self.document["chunks"])
        self.source = dict(self.document["source"])
        self.chunk_by_id = {chunk["chunk_id"]: chunk for chunk in self.chunks}
        self.teacher_by_name = {chunk["teacher_name"]: chunk for chunk in self.chunks}
        self.bm25 = BM25Retriever(self.chunks)
        self.dense_stub = DenseStubRetriever(self.chunks)
        self.email_generator = email_generator or GeminiEmailGenerator()

    def config(self) -> dict[str, Any]:
        return {
            "app_name": "南大校務通",
            "scope": "資工系教師資訊與 Email 草稿",
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
            "can_send_email": False,
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

        explicit_teacher = next(
            (name for name in self.teacher_by_name if name in query),
            None,
        )
        valid_context_teacher = (
            context_teacher if context_teacher in self.teacher_by_name else None
        )
        used_context = explicit_teacher is None and valid_context_teacher is not None
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

        teacher = self.teacher_by_name.get(str(normalized["teacher_name"]))
        if teacher is None:
            return 404, {
                "status": "not_found",
                "error": {"code": "TEACHER_NOT_FOUND"},
                "reason": "目前教師資料中找不到完全相符的姓名。",
            }

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
        if self.email_generator.configured:
            try:
                draft_content = self.email_generator.generate(
                    {
                        "teacher_name": teacher["teacher_name"],
                        "teacher_title": teacher["title"],
                        "purpose": purpose,
                        "purpose_label": PURPOSE_LABELS[purpose],
                        "student_name": student_name,
                        "student_identity": identity,
                        "request_details": details,
                        "background": background or None,
                    }
                )
                generation_provider = "gemini"
            except GeminiEmailError:
                generation_warning = "Gemini 暫時無法使用，已改用本機模板產生草稿。"

        return 200, {
            "status": "draft_created",
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
            "generation": {
                "provider": generation_provider,
                "model": (
                    self.email_generator.model
                    if generation_provider == "gemini"
                    else None
                ),
                "fallback_used": generation_warning is not None,
                "warning": generation_warning,
            },
            "error": None,
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
