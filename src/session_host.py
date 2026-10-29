"""W07 route A: account-owned memory with browser-scoped working context.

The opaque cookie represents a local demo browser, not a university login.
Only this web boundary resolves context; CampusService remains reusable by the
offline baseline and trusted stdio adapter. No private prompt history is stored.
"""
from __future__ import annotations

import hashlib
import hmac
import secrets
import re
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from campus_service import CampusService, FACULTY_DATA_PATH, OFFICE_DATA_PATH
from account_memory import AccountMemoryStore, MemoryError as AccountMemoryError
from personal_memory import candidates_from_message, relevant_facts, GeminiPersonalMemoryPlanner, validate_plan
from gemini_email import GeminiEmailGenerator, GeminiEmailError


class SessionError(RuntimeError):
    def __init__(self, code: str, message: str, status: int = 409):
        super().__init__(message)
        self.code, self.status = code, status


@dataclass
class Conversation:
    session_id: str = field(default_factory=lambda: secrets.token_urlsafe(24))
    csrf: str = field(default_factory=lambda: secrets.token_urlsafe(32))
    generation: int = 0
    teacher: str | None = None
    cleared_reason: str = "new_session"
    active: str | None = None
    account_id: str | None = None
    username: str | None = None
    personal_candidates: dict = field(default_factory=dict)


class SessionHost:
    def __init__(self, service_factory: Callable[[], CampusService] = CampusService,
                 source_paths: tuple[Path, ...] = (FACULTY_DATA_PATH, OFFICE_DATA_PATH),
                 account_store: AccountMemoryStore | None = None, memory_planner: Any | None = None):
        self._lock = threading.RLock()
        self._factory = service_factory
        self._source_paths = source_paths
        self.service = service_factory()
        self.memory_planner = memory_planner or GeminiPersonalMemoryPlanner(GeminiEmailGenerator(
            api_key=getattr(self.service.email_generator, "api_key", ""),
            model=getattr(self.service.email_generator, "model", None)))
        self.source_version = self._fingerprint()
        self._source_failed = False
        self._users: dict[str, Conversation] = {}
        self._drafts: dict[str, tuple[str, int, str]] = {}
        self._receipts: dict[str, str] = {}
        self.accounts = account_store or AccountMemoryStore(self.service.tool_server.outbox_path.parent / "account_memory.sqlite3")
        self._draft_memories: dict[str, tuple[str, list[dict[str, Any]]]] = {}
        self._login_attempts: dict[str, list[float]] = {}

    def _fingerprint(self) -> str:
        digest = hashlib.sha256()
        for path in self._source_paths:
            digest.update(path.read_bytes())
            digest.update(b"\0")
        return digest.hexdigest()

    def _clear(self, owner: str, reason: str) -> None:
        conversation = self._users[owner]
        conversation.generation += 1
        conversation.teacher = None
        conversation.active = None
        conversation.personal_candidates.clear()
        conversation.cleared_reason = reason
        for draft_id, binding in list(self._drafts.items()):
            if binding[0] == owner:
                self.service.pending_drafts.pop(draft_id, None)
                del self._drafts[draft_id]
                self._draft_memories.pop(draft_id, None)

    def _refresh(self) -> None:
        """Reload changed snapshots before context resolution; fail closed."""
        try:
            version = self._fingerprint()
            if version == self.source_version and not self._source_failed:
                return
            replacement = self._factory()
            if self._fingerprint() != version:
                raise ValueError("Source changed while loading")
        except Exception as exc:
            if not self._source_failed:
                for owner in self._users:
                    self._clear(owner, "source_unavailable")
            self._source_failed = True
            raise SessionError("SOURCE_UNAVAILABLE", "官方資料載入失敗，已清除脈絡並停止。", 503) from exc
        for owner in self._users:
            self._clear(owner, "source_changed")
        self.service = replacement
        self.source_version = version
        self._source_failed = False

    def _public(self, owner: str) -> dict[str, Any]:
        conversation = self._users[owner]
        return {
            "session_id": conversation.session_id,
            "generation": conversation.generation,
            "csrf_token": conversation.csrf,
            "source_version": self.source_version,
            "context_teacher": conversation.teacher,
            "cleared_reason": conversation.cleared_reason,
            "identity_mode": "local_account" if conversation.account_id else "guest_browser_cookie",
            "account": {"username": conversation.username} if conversation.account_id else None,
            "memory_route": "A_saved_email_content",
        }

    def _account(self, conversation: Conversation) -> str:
        if conversation.account_id is None:
            raise SessionError("LOGIN_REQUIRED", "請先登入，才能保存或讀取自己的常用內容。", 401)
        return conversation.account_id

    def _rotate(self, owner: str, account: dict[str, str] | None) -> dict[str, Any]:
        self._clear(owner, "identity_changed")
        del self._users[owner]
        replacement = secrets.token_urlsafe(32)
        self._users[replacement] = Conversation(
            account_id=account["account_id"] if account else None,
            username=account["username"] if account else None,
        )
        return {"session": self._public(replacement), "_set_cookie": replacement}

    def bootstrap(self, cookie: str | None) -> tuple[str, dict[str, Any]]:
        with self._lock:
            self._refresh()
            owner = cookie if cookie in self._users else secrets.token_urlsafe(32)
            if owner not in self._users:
                if len(self._users) >= 128:
                    raise SessionError("SESSION_CAPACITY", "本機 session 已達上限，請重啟展示服務。", 429)
                self._users[owner] = Conversation()
            return owner, self._public(owner)

    def _validate(self, owner: str | None, csrf: str, payload: dict[str, Any]) -> Conversation:
        if owner not in self._users:
            raise SessionError("SESSION_REQUIRED", "請重新載入頁面以建立 session。", 401)
        conversation = self._users[owner]
        if not isinstance(csrf, str) or not hmac.compare_digest(csrf.encode("utf-8"), conversation.csrf.encode("ascii")):
            raise SessionError("CSRF_REJECTED", "確認來源無效，請重新載入頁面。", 403)
        self._refresh()
        if (payload.get("session_id") != conversation.session_id
                or type(payload.get("generation")) is not int
                or payload["generation"] != conversation.generation):
            raise SessionError("STALE_SESSION", "對話或資料版本已更新，請重新提出需求。")
        if any(key in payload for key in ("context_teacher", "user_id", "owner")):
            raise SessionError("CLIENT_CONTEXT_FORBIDDEN", "身分與教師脈絡必須由後端解析。", 422)
        return conversation

    def handle(self, owner: str | None, csrf: str, path: str,
               payload: dict[str, Any]) -> tuple[int, dict[str, Any]]:
        try:
            return self._handle(owner, csrf, path, payload)
        except (SessionError, AccountMemoryError) as exc:
            with self._lock:
                response: dict[str, Any] = {
                    "status": "session_rejected", "error": {"code": exc.code},
                    "reason": str(exc), "answer": str(exc),
                }
                if owner in self._users and exc.code in ("STALE_SESSION", "SOURCE_UNAVAILABLE"):
                    response["session"] = self._public(owner)
                return exc.status, response

    def _handle(self, owner: str | None, csrf: str, path: str,
                payload: dict[str, Any]) -> tuple[int, dict[str, Any]]:
        with self._lock:
            conversation = self._validate(owner, csrf, payload)
            if path in ("/api/auth/register", "/api/auth/login"):
                now = time.monotonic()
                name = payload.get("username")
                keys = (f"browser:{owner}", f"name:{name.lower()[:32] if isinstance(name, str) else 'invalid'}")
                for key in keys:
                    self._login_attempts[key] = [stamp for stamp in self._login_attempts.get(key, []) if now - stamp < 60]
                    if len(self._login_attempts[key]) >= 10:
                        raise SessionError("LOGIN_RATE_LIMIT", "登入嘗試過多，請稍後再試。", 429)
                for key in keys:
                    self._login_attempts[key].append(now)
                authenticate = self.accounts.register if path.endswith("register") else self.accounts.login
                account = authenticate(payload.get("username"), payload.get("password"))
                return 200, {"status": "authenticated", **self._rotate(owner, account)}
            if path == "/api/auth/logout":
                return 200, {"status": "logged_out", **self._rotate(owner, None)}
            if path == "/api/memory/list":
                memories = self.accounts.list_memories(self._account(conversation))
                return 200, {"status": "ok", "memories": memories, "session": self._public(owner)}
            if path == "/api/personal-memory/save":
                account_id = self._account(conversation)
                candidate = conversation.personal_candidates.get(payload.get("candidate_id")) if isinstance(payload.get("candidate_id"), str) else None
                if not candidate:
                    raise SessionError("MEMORY_CANDIDATE_EXPIRED", "這筆候選已過期，請重新提出資訊後勾選。", 409)
                fields = {"action": "update" if candidate.get("memory_id") else "create",
                          "title": candidate["title"], "kind": "personal_fact", "content": candidate["content"],
                          "confirmed": payload.get("confirmed"), "operation_id": payload.get("operation_id")}
                if candidate.get("memory_id"):
                    fields.update(memory_id=candidate["memory_id"], expected_version=candidate["version"])
                result = self.accounts.mutate(account_id, fields["action"], fields)
                return 200, {**result, "session": self._public(owner)}
            if path == "/api/memory/write":
                fields = {key: value for key, value in payload.items() if key not in ("session_id", "generation")}
                account_id = self._account(conversation)
                if fields.get("kind") == "draft_template" and fields.get("action") != "delete":
                    template = self.accounts.template_fields("draft_template", fields.get("template_fields", {}))
                    record = self.service.teacher_by_name.get(template["teacher_name"])
                    if not record or record.get("authority") != "official" or record.get("validity") != "active":
                        raise SessionError("INVALID_TEMPLATE_TEACHER", "請選擇有效的官方教師，不能保存任意收件 Email。", 422)
                    if fields.get("action") == "create":
                        source_id = fields.get("source_draft_id")
                        if not isinstance(source_id, str) or self._drafts.get(source_id) != (owner, conversation.generation, self.source_version):
                            raise SessionError("DRAFT_NOT_FOUND", "請先產生自己的草稿，再另存為模板。", 404)
                result = self.accounts.mutate(account_id, fields.get("action"), fields)
                return 200, {**result, "session": self._public(owner)}
            if path == "/api/session/reset":
                self._clear(owner, "new_session")
                return 200, {"status": "session_cleared", "session": self._public(owner)}
            if path == "/api/email-status":
                request_id = payload.get("request_id")
                if not isinstance(request_id, str) or self._receipts.get(request_id) != owner:
                    raise SessionError("RECEIPT_NOT_FOUND", "找不到可存取的執行紀錄。", 404)
                status, result = self.service.get_email_status(request_id)
                return status, {**result, "session": self._public(owner)}
            if path == "/api/email-send":
                draft_id = payload.get("draft_id")
                if not isinstance(draft_id, str) or self._drafts.get(draft_id) != (
                        owner, conversation.generation, self.source_version):
                    raise SessionError("DRAFT_NOT_FOUND", "草稿不存在或已失效，請重新產生。", 404)
                if draft_id in self._draft_memories:
                    account_id, selections = self._draft_memories[draft_id]
                    if account_id != self._account(conversation):
                        raise SessionError("DRAFT_NOT_FOUND", "草稿不存在或已失效。", 404)
                    self.accounts.selected(account_id, selections)
                # Reset/source invalidation cannot race this local SQLite write.
                status, result = self.service.send_email_draft(payload)
                return status, {**result, "session": self._public(owner)}
            if path not in ("/api/chat", "/api/email-draft", "/api/email-template-draft", "/api/email-draft-edit", "/api/email-draft-revise"):
                raise SessionError("NOT_FOUND", "找不到此操作。", 404)
            if conversation.active:
                raise SessionError("SESSION_BUSY", "此對話仍在處理，請稍後再試。")
            if path == "/api/chat" and (
                    not isinstance(payload.get("message"), str)
                    or payload.get("retriever", "bm25") not in ("bm25", "dense_stub")):
                raise SessionError("INVALID_CHAT_INPUT", "請提供文字與允許的檢索方式。", 422)
            is_email = path != "/api/chat"
            is_revision = path == "/api/email-draft-revise"
            reuse_content = path in ("/api/email-template-draft", "/api/email-draft-edit")
            revision_context = None
            if is_revision:
                source_id = payload.get("source_draft_id")
                if not isinstance(source_id, str) or self._drafts.get(source_id) != (owner, conversation.generation, self.source_version):
                    raise SessionError("DRAFT_NOT_FOUND", "草稿不存在或已失效，請重新引用。", 404)
                source = self.service.pending_drafts.get(source_id)
                if not source:
                    raise SessionError("DRAFT_NOT_FOUND", "草稿不存在或已失效。", 404)
                instructions = payload.get("instructions")
                if not isinstance(instructions, str) or not instructions.strip() or len(instructions) > 1000:
                    raise SessionError("INVALID_REVISION_INSTRUCTIONS", "請填寫 1–1000 字的調整指示。", 422)
                revision_context = {"base_draft": {"subject": source["subject"], "body": source["body"]},
                                    "revision_instructions": instructions.strip()}
                # Model revisions cannot change the selected recipient.
                name = self.service.chunk_by_id[source["teacher_id"]]["teacher_name"]
                if payload.get("teacher_name", name) != name:
                    raise SessionError("REVISION_RECIPIENT_LOCKED", "AI 調整不能更換收件教師；請先手動修改並更新草稿。", 422)
                payload = {**payload, "teacher_name": name}
            if "public_selections" in payload:
                raise SessionError("PUBLIC_EXAMPLES_REMOVED", "公版功能已移除，請重新載入並選用自己的草稿或文字。", 422)
            if is_email:
                if any(key in payload for key in ("saved_email_content", "approved_draft_content", "draft_revision")):
                    raise SessionError("CLIENT_MEMORY_FORBIDDEN", "常用內容必須由後端依帳號與版本讀取。", 422)
                name = payload.get("teacher_name")
                if not isinstance(name, str):
                    raise SessionError("INVALID_DRAFT_INPUT", "請選擇教師全名。", 422)
                teacher_record = self.service.teacher_by_name.get(name.strip())
                if teacher_record and (teacher_record.get("authority") != "official"
                                       or teacher_record.get("validity") != "active"):
                    raise SessionError("TEACHER_SOURCE_INVALID", "教師資料已失效，不能建立草稿。")
            selections = payload.get("memory_selections", []) if is_email else []
            if path in ("/api/email-draft-edit", "/api/email-draft-revise"):
                source_id = payload.get("source_draft_id")
                if not isinstance(source_id, str) or self._drafts.get(source_id) != (owner, conversation.generation, self.source_version):
                    raise SessionError("DRAFT_NOT_FOUND", "草稿不存在或已失效。", 404)
                binding = self._draft_memories.get(source_id)
                selections = binding[1] if binding else []
            saved_content = self.accounts.selected(self._account(conversation), selections) if selections else []
            if any(item["kind"] == "personal_fact" for item in saved_content):
                raise SessionError("PERSONAL_FACT_NOT_EMAIL_TEXT", "個人記憶供校務問答查用，不能當成常用信件段落套用。", 422)
            if is_email and not isinstance(selections, list):
                raise SessionError("INVALID_MEMORY_SELECTION", "常用內容選取格式錯誤。", 422)
            if any(item["kind"] == "email_template" for item in saved_content):
                raise SessionError("LEGACY_FORM_TEMPLATE", "舊表單模板不再套用；請產生草稿後另存新模板。", 422)
            templates = [item for item in saved_content if item["kind"] == "draft_template"]
            if len(templates) > 1:
                raise SessionError("MULTIPLE_EMAIL_TEMPLATES", "一次只能套用一份整封模板。", 422)
            if templates and not (reuse_content or is_revision):
                raise SessionError("DRAFT_TEMPLATE_REQUIRES_PREVIEW", "請套用草稿模板並確認主旨與正文，不要重新交由模型產生。", 422)
            if path == "/api/email-template-draft" and len(templates) != 1:
                raise SessionError("DRAFT_TEMPLATE_REQUIRED", "請選擇一份草稿模板。", 422)
            if reuse_content:
                if payload.get("confirmed") is not True:
                    raise SessionError("DRAFT_CONFIRMATION_REQUIRED", "請確認編輯後的主旨與正文。", 409)
                for key, limit in (("subject", 80), ("body", 4000)):
                    value = payload.get(key)
                    if not isinstance(value, str) or not value.strip() or len(value) > limit or (key == "subject" and any(char in value for char in "\r\n")):
                        raise SessionError("INVALID_DRAFT_CONTENT", "主旨須為 1–80 字單行文字，正文須為 1–4000 字。", 422)
            draft_content = [item for item in saved_content if item["kind"] != "draft_template"]
            if sum(len(item["content"]) for item in draft_content) > 4000:
                raise SessionError("MEMORY_CONTEXT_TOO_LONG", "選取文字合計最多 4000 字。", 422)
            token = secrets.token_urlsafe(16)
            conversation.active = token
            generation = conversation.generation
            source_version = self.source_version
            service = self.service
            teacher = conversation.teacher
            personal_candidates, used_personal, unresolved_teacher = [], [], []
            chat_message = payload.get("message", "")
            memories = self.accounts.list_memories(conversation.account_id) if not is_email and conversation.account_id else []

        # Model/network work must not hold the session store lock: reset can win.
        try:
            if path == "/api/chat":
                memory_plan = None
                analysis = {"backend": "rules", "live_status": "LIVE_NOT_RUN", "status": "not_configured"}
                if conversation.account_id:
                    existing = {item["title"]: item for item in memories if item["kind"] == "personal_fact"}
                    by_id = {item["memory_id"]: item for item in existing.values()}
                    if self.memory_planner.configured:
                        try:
                            memory_plan = validate_plan(self.memory_planner.plan(chat_message, memories), chat_message, memories)
                            live = getattr(self.memory_planner, "evidence_mode", "offline") == "live"
                            analysis = {"backend": "gemini", "model": self.memory_planner.model,
                                        "live_status": "LIVE_PASS" if live else "LIVE_NOT_RUN",
                                        "status": "success" if live else "offline_model_double"}
                        except GeminiEmailError as exc:
                            detail = str(exc)
                            api_key = getattr(getattr(self.memory_planner, "client", None), "api_key", "")
                            if api_key:
                                detail = detail.replace(api_key, "[已遮蔽金鑰]")
                            analysis = {"backend": "rules", "live_status": "LIVE_FAIL" if getattr(self.memory_planner, "evidence_mode", "offline") == "live" else "LIVE_NOT_RUN",
                                        "status": "semantic_failed_fallback", "failure_reason": detail}
                    proposals = memory_plan["proposals"] if memory_plan else candidates_from_message(chat_message)
                    for fact in proposals:
                        old = by_id.get(fact.get("replaces_memory_id")) or existing.get(fact["title"])
                        personal_candidates.append({"title": old["title"] if old else fact["title"], "content": fact["content"],
                            "evidence_quote": fact.get("evidence_quote", ""),
                            "candidate_id": secrets.token_urlsafe(18), "memory_id": old["memory_id"] if old else None,
                            "version": old["version"] if old else None, "previous_content": old["content"] if old else None})
                    used_personal = [by_id[key] for key in memory_plan["read_memory_ids"]] if memory_plan else ([] if personal_candidates else relevant_facts(chat_message, memories))
                    target_id = memory_plan["teacher_memory_id"] if memory_plan else ""
                    for fact in sorted(used_personal, key=lambda item: len(item["title"]), reverse=True):
                        if target_id and fact["memory_id"] != target_id:
                            continue
                        if not target_id and not fact["title"].endswith(("老師", "教師", "教授")):
                            continue
                        teacher_name = re.sub(r"(?:老師|教師|教授)$", "", fact["content"]).strip()
                        record = service.teacher_by_name.get(teacher_name)
                        explicit_others = [name for name in service.teacher_by_name if name in payload["message"] and name != teacher_name]
                        if explicit_others:
                            used_personal = []
                            break
                        if record and record.get("authority") == "official" and record.get("validity") == "active":
                            if memory_plan:
                                rewrite = memory_plan["resolved_query"]
                                chat_message = rewrite if teacher_name in rewrite else f'{teacher_name} {payload["message"]}'
                            else:
                                chat_message = f'{teacher_name} {payload["message"]}'
                        else:
                            unresolved_teacher.append(fact)
                if memory_plan and memory_plan["intent"] == "clarify":
                    result = {"status": "needs_clarification", "answer": memory_plan["clarification"] or "請補充課程、教師或要更新的個人資訊，以免用錯記憶。", "citations": [], "error": {"code": "MEMORY_NEEDS_CLARIFICATION"}}
                elif personal_candidates and (not memory_plan or memory_plan["intent"] == "remember"):
                    result = {"status": "ok", "answer": "已整理可保存的個人資訊，請在下方勾選並確認。確認前不會新增或覆蓋記憶。", "citations": []}
                elif (memory_plan and memory_plan["intent"] == "recall" and used_personal) or any(re.fullmatch(r"\s*(?:請問)?(?:我的)?" + re.escape(item["title"].removeprefix("我的")) + r"(?:是誰|是什麼|是甚麼|叫什麼|叫甚麼)[？?]?\s*", payload["message"]) for item in used_personal):
                    result = {"status": "ok", "answer": "依你確認保存的個人記憶：\n" + "\n".join(f'{item["title"]}：{item["content"]}' for item in used_personal), "citations": []}
                    if len(used_personal) == 1 and used_personal[0]["title"].endswith(("老師", "教師", "教授")):
                        name = re.sub(r"(?:老師|教師|教授)$", "", used_personal[0]["content"]).strip()
                        record = service.teacher_by_name.get(name)
                        if record and record.get("authority") == "official" and record.get("validity") == "active":
                            result.update(detected_teacher=name, suggested_action="email_draft")
                elif unresolved_teacher:
                    result = {"status": "needs_clarification", "answer": "個人記憶中的教師無法對應目前有效的官方教師資料，請提供完整姓名或更新記憶後再查詢。", "citations": [], "error": {"code": "PERSONAL_TEACHER_UNRESOLVED"}}
                else:
                    result = service.chat(chat_message, payload.get("retriever", "bm25"), teacher)
                result["personal_memory_analysis"] = analysis if conversation.account_id else {"status": "guest_disabled", "live_status": "LIVE_NOT_RUN"}
                status = 200
            else:
                fields = {**payload, "saved_email_content": draft_content}
                if reuse_content:
                    fields.update(purpose="other", student_name="模板使用者", request_details=payload["body"],
                                  approved_draft_content={"subject": payload["subject"].strip(), "body": payload["body"].strip()})
                if is_revision:
                    fields = {"teacher_name": payload["teacher_name"], "purpose": "other", "student_name": "",
                              "request_details": revision_context["revision_instructions"],
                              "draft_revision": revision_context, "saved_email_content": []}
                status, result = service.create_email_draft(fields)
        except Exception:
            with self._lock:
                if conversation.active == token:
                    conversation.active = None
                    conversation.teacher = None
                    conversation.cleared_reason = "request_failed"
            raise

        with self._lock:
            try:
                self._refresh()
                if (conversation.generation != generation or conversation.active != token
                        or self.source_version != source_version):
                    raise SessionError("STALE_SESSION", "已排除舊對話回覆，請重新提出需求。")
                if selections:
                    self.accounts.selected(self._account(conversation), selections)
                if not is_email and conversation.account_id:
                    refs = {item["memory_id"]: {"memory_id": item["memory_id"], "version": item["version"]} for item in used_personal}
                    refs.update({item["memory_id"]: {"memory_id": item["memory_id"], "version": item["version"]} for item in personal_candidates if item.get("memory_id")})
                    # selected() is bounded to eight records per call.
                    refs = list(refs.values())
                    for offset in range(0, len(refs), 8):
                        self.accounts.selected(self._account(conversation), refs[offset:offset + 8])
            except (SessionError, AccountMemoryError):
                if is_email:
                    service.pending_drafts.pop(result.get("draft_id"), None)
                if conversation.active == token:
                    conversation.active = None
                raise
            conversation.active = None
            if path == "/api/chat":
                conversation.personal_candidates.update({item["candidate_id"]: item for item in personal_candidates})
                while len(conversation.personal_candidates) > 64:
                    del conversation.personal_candidates[next(iter(conversation.personal_candidates))]
                result["personal_memory_candidates"] = personal_candidates
                result["personal_memory_used"] = [{"title": item["title"], "content": item["content"], "version": item["version"]} for item in used_personal]
                candidate = result.get("detected_teacher")
                conversation.teacher = candidate if candidate in service.teacher_by_name else None
                if conversation.teacher is None:
                    conversation.cleared_reason = "topic_ended"
                else:
                    conversation.cleared_reason = "context_valid"
            elif status == 200:
                if path in ("/api/email-draft-edit", "/api/email-draft-revise"):
                    # Replacing a draft invalidates the old content and its send authorization.
                    old_id = payload["source_draft_id"]
                    self._drafts.pop(old_id, None)
                    self._draft_memories.pop(old_id, None)
                    service.pending_drafts.pop(old_id, None)
                self._drafts[result["draft_id"]] = (owner, generation, source_version)
                self._receipts[result["request_id"]] = owner
                if selections:
                    self._draft_memories[result["draft_id"]] = (self._account(conversation), selections)
                result["memory_trace"] = {
                    "source": "account_saved_email_content", "selection": selections,
                    "read_status": "loaded" if selections else "not_selected",
                    "persisted_automatically": False,
                }
            return status, {**result, "session": self._public(owner)}
