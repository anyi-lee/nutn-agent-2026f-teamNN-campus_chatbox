"""Real isolated SQLite/Host tests; no model calls or external email."""
import json
import secrets
import sqlite3
from contextlib import closing

from test_week07_account_memory import AccountFixture
from account_memory import AccountMemoryStore


class TemplateTests(AccountFixture):
    def full(self, **extra):
        source = self.draft()[1]
        return self.memory("林老師您好：\n想請問微積分本次 Practice 的參考解答是否方便提供？\n合成學生 祝教安", "draft_template",
                           template_fields={"teacher_name": "林朝興", "subject": "微積分 Practice 解答詢問"},
                           source_draft_id=source["draft_id"], **extra)

    def test_t01_guest_can_create_new_email_but_saved_content_is_private(self):
        self.assertEqual(self.draft()[0], 200)
        self.assertEqual(self.call("/api/memory/list")[0], 401)
        self.assertEqual(self.memory()[0], 401)
        self.register()
        self.memory("我自己的常用內容")
        self.assertEqual(self.list()[0]["content"], "我自己的常用內容")
        self.assertEqual(self.call("/api/memory/list", owner=self.b, session=self.sb)[0], 401)

    def test_t02_full_template_roundtrip_editable_request_signature_and_revocation(self):
        self.register()
        status, saved = self.full()
        self.assertEqual(status, 200)
        row = self.list()[0]
        self.assertEqual(row["template_fields"]["teacher_name"], "林朝興")
        # Browser confirmed application supplies editable request fields; server owns recipient lookup.
        status, draft = self.call("/api/email-template-draft", {
            **row["template_fields"], "confirmed": True,
            "body": row["content"] + "這次為 Practice 3。",
            "memory_selections": [self.ref(saved)],
        })
        self.assertEqual(status, 200)
        self.assertEqual(draft["email_draft"]["to"], "mikelin@mail.nutn.edu.tw")
        self.assertEqual(draft["email_draft"]["body"].count("想請問微積分"), 1)
        self.assertIn("Practice 3", draft["email_draft"]["body"])
        self.assertIn("合成學生 祝教安", draft["email_draft"]["body"])
        self.call("/api/memory/write", {"action": "delete", "confirmed": True,
                  "operation_id": secrets.token_hex(16), "memory_id": saved["memory_id"], "expected_version": 1})
        self.assertEqual(self.call("/api/email-send", {"draft_id": draft["draft_id"], "confirmed": True})[0], 404)
        with closing(sqlite3.connect(self.host.accounts.path)) as connection:
            self.assertEqual(connection.execute("SELECT template_json FROM email_memories").fetchone()[0], "{}")
        self.assertEqual(self.count(), 0)

    def test_t03_reject_unknown_teacher_email_and_template_fields_on_text(self):
        self.register()
        for fields in ({"teacher_name": "不存在", "subject": "測試"},
                       {"teacher_name": "林朝興", "subject": "測試", "to": "attacker@example.invalid"},
                       {"teacher_name": "林朝興", "subject": "不合法\n主旨"}, []):
            status, _ = self.memory("合成固定詢問文字", "draft_template", template_fields=fields)
            self.assertEqual(status, 422)
        self.assertEqual(self.memory(template_fields={"teacher_name": "林朝興"})[0], 422)
        self.assertEqual(self.list(), [])

    def test_t04_template_selection_still_checks_owner_and_multiple_full_templates(self):
        self.register()
        first = self.full()[1]
        second = self.full()[1]
        self.assertEqual(self.selected_draft([self.ref(first), self.ref(second)])[0], 422)
        self.register("synthetic_b", browser="b")
        status, _ = self.call("/api/email-draft", {
            "teacher_name": "林朝興", "purpose": "other", "student_name": "合成學生",
            "request_details": "合成固定詢問文字", "memory_selections": [self.ref(first)],
        }, owner=self.b, session=self.sb)
        self.assertEqual(status, 404)

    def test_t05_removed_public_api_rejected_and_private_selection_limit_validated(self):
        base = {"teacher_name": "林朝興", "purpose": "other", "student_name": "合成學生", "request_details": "合成固定詢問文字"}
        ref = {"example_id": "practice_answers", "version": 1}
        for refs in ([{**ref, "version": True}], [ref, ref], [{**ref, "version": 999}], ["bad"], {}):
            self.assertGreaterEqual(self.call("/api/email-draft", {**base, "public_selections": refs})[0], 400)
        self.register()
        private = [self.ref(self.memory()[1]) for _ in range(9)]
        self.assertEqual(self.call("/api/email-draft", {**base, "memory_selections": private})[0], 422)
        self.assertEqual(self.call("/api/email-draft", {**base, "public_selections": []})[1]["error"]["code"], "PUBLIC_EXAMPLES_REMOVED")

    def test_t06_old_sqlite_schema_migrates_without_losing_text(self):
        legacy = self.directory / "legacy.sqlite3"
        with closing(sqlite3.connect(legacy)) as connection, connection:
            connection.execute("""CREATE TABLE email_memories (
                memory_id TEXT PRIMARY KEY, account_id TEXT NOT NULL, title TEXT NOT NULL,
                kind TEXT NOT NULL, content TEXT NOT NULL, version INTEGER NOT NULL,
                created_at TEXT NOT NULL, updated_at TEXT NOT NULL, deleted_at TEXT)""")
            connection.execute("INSERT INTO email_memories VALUES ('old', 'owner', 'old title', 'other', '保留既有內容', 1, 'date', 'date', NULL)")
        store = AccountMemoryStore(legacy)
        self.assertEqual(store.list_memories("owner")[0]["content"], "保留既有內容")
        self.assertEqual(store.list_memories("owner")[0]["template_fields"], {})
        AccountMemoryStore(legacy)  # Migration is safe to repeat on subsequent starts.

    def test_t07_draft_source_required_and_form_template_creation_removed(self):
        self.register()
        self.assertEqual(self.memory("完整信件正文", "draft_template", template_fields={"teacher_name": "林朝興", "subject": "主旨"})[0], 404)
        self.assertEqual(self.memory("舊表單模板", "email_template")[0], 422)
        _, source = self.draft()
        self.register("synthetic_b", browser="b")
        status, _ = self.call("/api/memory/write", {"action": "create", "confirmed": True,
            "operation_id": secrets.token_hex(16), "title": "不能另存別人的草稿", "kind": "draft_template",
            "content": "完整信件正文", "template_fields": {"teacher_name": "林朝興", "subject": "主旨"},
            "source_draft_id": source["draft_id"]}, owner=self.b, session=self.sb)
        self.assertEqual(status, 404)
        self.assertEqual(self.list(), [])

    def test_t08_reuse_and_edit_preserve_exact_text_skip_model_and_invalidate_old_send(self):
        self.register()
        _, saved = self.full()
        class MustNotCall:
            configured = True
            model = "offline-must-not-call"
            def generate(self, facts):
                raise AssertionError("Reusing approved text must not call a model")
        self.host.service.email_generator = MustNotCall()
        original = "老師您好：\n請問 Practice 4 第 2 題。\n學生甲 敬上"
        fields = {"teacher_name": "林朝興", "subject": "我確認過的主旨", "body": original,
                  "confirmed": True, "memory_selections": [self.ref(saved)]}
        self.assertEqual(self.call("/api/email-template-draft", {**fields, "confirmed": False})[0], 409)
        status, draft = self.call("/api/email-template-draft", fields)
        self.assertEqual(status, 200)
        self.assertEqual(draft["email_draft"]["body"], original)
        self.assertEqual(draft["generation"]["provider"], "saved_draft")
        self.assertEqual(draft["generation"]["evidence_status"], "LIVE_NOT_RUN")
        self.assertTrue(draft["requires_confirmation"])
        changed = {"teacher_name": "林朝興", "subject": "已修改主旨", "body": original.replace("4", "5"),
                   "confirmed": True, "source_draft_id": draft["draft_id"]}
        status, updated = self.call("/api/email-draft-edit", changed)
        self.assertEqual(status, 200)
        self.assertNotEqual(updated["draft_id"], draft["draft_id"])
        self.assertNotEqual(updated["request_id"], draft["request_id"])
        self.assertEqual(updated["email_draft"]["body"], changed["body"])
        self.assertEqual(self.call("/api/email-send", {"draft_id": draft["draft_id"], "confirmed": True})[0], 404)
        self.assertEqual(self.call("/api/email-send", {"draft_id": updated["draft_id"], "confirmed": False})[0], 409)
        self.assertEqual(self.count(), 0)
        self.assertEqual(self.call("/api/email-send", {"draft_id": updated["draft_id"], "confirmed": True})[0], 200)
        self.assertEqual(self.count(), 1)
        with closing(sqlite3.connect(self.database)) as connection:
            self.assertEqual(connection.execute("SELECT body FROM sandbox_outbox").fetchone()[0], changed["body"])
