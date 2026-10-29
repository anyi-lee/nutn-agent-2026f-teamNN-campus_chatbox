"""Offline revision contract tests with explicit model doubles; not Gemini Live."""
import json
import secrets
import threading

from test_week07_account_memory import AccountFixture
from gemini_email import GeminiEmailError


class RevisionSpy:
    configured = True
    model = "offline-revision-spy"

    def generate_with_contact_tool(self, facts, *, tool_definition, call_tool):
        self.facts = facts
        contact = call_tool("get_teacher_contact", {"teacher_query": facts["teacher_name"]})
        assert contact["status"] == "found"
        return {"subject": "Practice 4 第 2 題解題說明", "body": "林老師您好：\n想請問 Practice 4 第 2 題的解題思路。\n學生 合成學生 敬上"}, [
            {"kind": "read", "tool": "get_teacher_contact", "status": "found", "stage": "offline_revision_spy"}]


class RevisionTests(AccountFixture):
    def saved_source(self):
        self.register()
        _, source = self.draft()
        _, saved = self.memory(source["email_draft"]["body"], "draft_template", title="我的完整草稿",
                               source_draft_id=source["draft_id"],
                               template_fields={"teacher_name": "林朝興", "subject": source["email_draft"]["subject"]})
        _, reused = self.call("/api/email-template-draft", {"teacher_name": "林朝興",
                              "subject": source["email_draft"]["subject"], "body": source["email_draft"]["body"],
                              "confirmed": True, "memory_selections": [self.ref(saved)]})
        return reused, saved

    def revise(self, source, **extra):
        return self.call("/api/email-draft-revise", {"source_draft_id": source["draft_id"],
                         "instructions": "改為 Practice 4 第 2 題，簡短禮貌，保留署名。", **extra})

    def test_r01_canonical_draft_and_instructions_reach_model_template_unchanged(self):
        source, saved = self.saved_source()
        self.memory("未選取的私人文字不可進入模型")
        before = self.list()
        spy = RevisionSpy()
        self.host.service.email_generator = spy
        status, revised = self.revise(source, body="不能取代後端的來源正文", background="不能注入額外模型內容")
        self.assertEqual(status, 200)
        self.assertEqual(spy.facts["base_draft"], {"subject": source["email_draft"]["subject"], "body": source["email_draft"]["body"]})
        self.assertIn("Practice 4", spy.facts["revision_instructions"])
        self.assertNotIn("不能注入", json.dumps(spy.facts, ensure_ascii=False))
        self.assertNotIn("未選取的私人文字", json.dumps(spy.facts, ensure_ascii=False))
        self.assertEqual(revised["email_draft"]["to"], source["email_draft"]["to"])
        self.assertNotEqual(revised["draft_id"], source["draft_id"])
        self.assertEqual(revised["memory_trace"]["selection"], [self.ref(saved)])
        self.assertEqual(self.list(), before)
        self.assertEqual(self.call("/api/email-send", {"draft_id": source["draft_id"], "confirmed": True})[0], 404)
        self.assertEqual(self.call("/api/email-send", {"draft_id": revised["draft_id"], "confirmed": False})[0], 409)
        self.assertEqual(self.count(), 0)

    def test_r02_missing_model_is_not_run_and_provider_failure_keeps_original(self):
        source, _ = self.saved_source()
        count = len(self.host.service.pending_drafts)
        status, result = self.revise(source)
        self.assertEqual(status, 503)
        self.assertEqual(result["generation"]["evidence_status"], "LIVE_NOT_RUN")
        class FailingModel:
            configured = True
            model = "offline-failure-injection"
            def generate(self, facts):
                raise GeminiEmailError("offline provider failure injection")
        self.host.service.email_generator = FailingModel()
        status, result = self.revise(source)
        self.assertEqual(status, 502)
        self.assertEqual(result["generation"]["evidence_status"], "LIVE_FAIL")
        self.assertEqual(len(self.host.service.pending_drafts), count)
        self.assertEqual(self.host.service.pending_drafts[source["draft_id"]]["body"], source["email_draft"]["body"])

    def test_r03_owner_recipient_instruction_and_internal_fields_guarded(self):
        source, _ = self.saved_source()
        spy = RevisionSpy()
        self.host.service.email_generator = spy
        self.assertEqual(self.call("/api/email-draft-revise", {"source_draft_id": source["draft_id"], "instructions": "簡短"}, owner=self.b, session=self.sb)[0], 404)
        self.assertEqual(self.revise(source, teacher_name="另一位教師")[0], 422)
        for instructions in ("", [], "a" * 1001):
            self.assertEqual(self.revise(source, instructions=instructions)[0], 422)
        self.assertEqual(self.revise(source, draft_revision={"base_draft": "forged"})[0], 422)
        self.assertFalse(hasattr(spy, "facts"))

    def test_r04_invalid_model_output_does_not_create_replacement(self):
        source, _ = self.saved_source()
        class InvalidModel:
            configured = True
            model = "offline-invalid-output"
            def generate(self, facts):
                return {"subject": "主旨\n不合法", "body": "林老師您好：\n合成測試正文。"}
        self.host.service.email_generator = InvalidModel()
        count = len(self.host.service.pending_drafts)
        self.assertEqual(self.revise(source)[0], 502)
        self.assertEqual(len(self.host.service.pending_drafts), count)
        self.assertIn(source["draft_id"], self.host.service.pending_drafts)

    def test_r05_memory_revoked_during_model_work_discards_new_draft(self):
        source, saved = self.saved_source()
        entered, release = threading.Event(), threading.Event()
        class SlowSpy(RevisionSpy):
            def generate_with_contact_tool(self, facts, **kwargs):
                entered.set()
                if not release.wait(4):
                    raise RuntimeError("offline revision test timed out")
                return super().generate_with_contact_tool(facts, **kwargs)
        self.host.service.email_generator = SlowSpy()
        results = []
        worker = threading.Thread(target=lambda: results.append(self.revise(source)))
        worker.start()
        self.assertTrue(entered.wait(2))
        try:
            self.call("/api/memory/write", {"action": "delete", "confirmed": True,
                      "operation_id": secrets.token_hex(16), "memory_id": saved["memory_id"], "expected_version": 1})
        finally:
            release.set()
            worker.join(4)
        self.assertFalse(worker.is_alive())
        self.assertEqual(results[0][0], 404)
        self.assertEqual(self.count(), 0)
        self.assertFalse(any(draft["subject"] == "Practice 4 第 2 題解題說明" for draft in self.host.service.pending_drafts.values()))

    def test_r06_revision_cannot_drop_or_replace_source_signature(self):
        source, _ = self.saved_source()
        class SignatureDroppingModel:
            configured = True
            model = "offline-signature-failure-injection"
            def generate(self, facts):
                return {"subject": "修改語氣", "body": self.body}
        model = SignatureDroppingModel()
        self.host.service.email_generator = model
        for body in ("林老師您好：\n想請問解題思路，謝謝。", "林老師您好：\n學生 另一位學生 敬上"):
            model.body = body
            status, result = self.revise(source)
            self.assertEqual(status, 502)
            self.assertEqual(result["error"]["code"], "MODEL_REVISION_FAILED")
            self.assertIn(source["draft_id"], self.host.service.pending_drafts)
            self.assertEqual(len(self.host.service.pending_drafts), 2)
