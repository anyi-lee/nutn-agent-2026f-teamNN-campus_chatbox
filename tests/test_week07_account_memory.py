"""A-route acceptance with synthetic credentials and isolated SQLite stores."""
from __future__ import annotations
import http.cookiejar
import json
import secrets
import sqlite3
import threading
import unittest
from contextlib import closing
from http.server import ThreadingHTTPServer
from urllib import request, error

from test_week07_sessions import SessionFixture, CampusRequestHandler
from session_host import SessionHost
from account_memory import AccountMemoryStore

PASSWORD = "synthetic-test-password-2026"  # Test-only, never a real account.


class AccountFixture(SessionFixture):
    def call(self, path, fields=None, *, owner=None, session=None):
        original = owner or self.a
        status, result = super().call(path, fields, owner=owner, session=session)
        if "_set_cookie" in result:
            replacement = result.pop("_set_cookie")
            if original == self.a:
                self.a, self.sa = replacement, result["session"]
            elif original == self.b:
                self.b, self.sb = replacement, result["session"]
        elif original == self.b and result.get("session"):
            self.sb = result["session"]
        return status, result

    def register(self, username="synthetic_a", *, browser="a"):
        options = {"owner": self.b, "session": self.sb} if browser == "b" else {}
        return self.call("/api/auth/register", {"username": username, "password": PASSWORD}, **options)

    def memory(self, content="我是合成測試學生，對智慧代理人有興趣。", kind="introduction", **extra):
        return self.call("/api/memory/write", {
            "action": "create", "confirmed": True, "operation_id": secrets.token_hex(16),
            "title": "常用自我介紹", "kind": kind, "content": content, **extra,
        })

    def list(self, **options):
        return self.call("/api/memory/list", **options)[1].get("memories", [])

    @staticmethod
    def ref(result):
        return {"memory_id": result["memory_id"], "version": result["version"]}

    def selected_draft(self, refs):
        return self.call("/api/email-draft", {
            "teacher_name": "林朝興", "purpose": "other", "student_name": "合成學生",
            "request_details": "希望詢問專題面談方式。", "memory_selections": refs,
        })


class AccountMemoryTests(AccountFixture):
    def test_a01_multiple_contents_survive_new_session_logout_and_restart(self):
        self.assertEqual(self.register()[0], 200)
        first = self.memory()[1]
        second = self.memory("學生 合成學生 敬上", "signature")[1]
        self.call("/api/session/reset")
        self.assertEqual(len(self.list()), 2)
        self.call("/api/auth/logout")
        self.assertEqual(self.call("/api/memory/list")[0], 401)
        self.host = SessionHost(self.host._factory, (self.faculty, self.office))
        self.a, self.sa = self.host.bootstrap(None)
        self.call("/api/auth/login", {"username": "synthetic_a", "password": PASSWORD})
        self.assertEqual({row["memory_id"] for row in self.list()}, {first["memory_id"], second["memory_id"]})
        _, draft = self.selected_draft([self.ref(first), self.ref(second)])
        self.assertIn("智慧代理人", draft["email_draft"]["body"])
        self.assertIn("學生 合成學生 敬上", draft["email_draft"]["body"])

    def test_a02_read_update_delete_and_apply_are_account_isolated(self):
        self.register()
        _, saved = self.memory()
        self.register("synthetic_b", browser="b")
        self.assertEqual(self.list(owner=self.b, session=self.sb), [])
        for action in ("update", "delete"):
            status, _ = self.call("/api/memory/write", {
                "action": action, "confirmed": True, "operation_id": secrets.token_hex(16),
                "memory_id": saved["memory_id"], "expected_version": 1,
                "title": "other", "kind": "other", "content": "cannot modify another user",
            }, owner=self.b, session=self.sb)
            self.assertEqual(status, 404)
        status, _ = self.call("/api/email-draft", {
            "teacher_name": "林朝興", "purpose": "other", "student_name": "合成學生",
            "request_details": "合成測試詢問內容", "memory_selections": [self.ref(saved)],
        }, owner=self.b, session=self.sb)
        self.assertEqual(status, 404)
        self.assertEqual(len(self.list()), 1)

    def test_a03_confirmed_save_replay_and_operation_conflict(self):
        self.register()
        self.assertEqual(self.memory(confirmed=False)[0], 409)
        self.assertEqual(self.list(), [])
        operation = secrets.token_hex(16)
        first = self.memory(operation_id=operation)[1]
        repeated = self.memory(operation_id=operation)[1]
        self.assertEqual(first["memory_id"], repeated["memory_id"])
        self.assertTrue(repeated["idempotent_replay"])
        self.assertEqual(len(self.list()), 1)
        self.assertEqual(self.memory("different text", operation_id=operation)[0], 409)

    def test_a04_update_version_and_delete_exclude_old_content(self):
        self.register()
        create_operation = secrets.token_hex(16)
        _, saved = self.memory("舊的合成自介", operation_id=create_operation)
        update = {"action": "update", "confirmed": True, "operation_id": secrets.token_hex(16),
                  "memory_id": saved["memory_id"], "expected_version": 1, "title": "新版", "kind": "introduction", "content": "新的合成自介"}
        _, changed = self.call("/api/memory/write", update)
        self.assertEqual(changed["version"], 2)
        self.assertEqual(self.selected_draft([self.ref(saved)])[0], 409)
        self.assertEqual(self.call("/api/memory/write", {**update, "operation_id": secrets.token_hex(16)})[0], 409)
        _, draft = self.selected_draft([self.ref(changed)])
        self.assertIn("新的合成自介", draft["email_draft"]["body"])
        self.assertNotIn("舊的合成自介", draft["email_draft"]["body"])
        self.call("/api/memory/write", {"action": "delete", "confirmed": True, "operation_id": secrets.token_hex(16), "memory_id": saved["memory_id"], "expected_version": 2})
        self.assertEqual(self.list(), [])
        self.assertEqual(self.selected_draft([self.ref(changed)])[0], 404)
        self.assertEqual(self.call("/api/email-send", {"draft_id": draft["draft_id"], "confirmed": True})[0], 404)
        self.assertEqual(self.count(), 0)
        self.memory("舊的合成自介", operation_id=create_operation)  # Old approval replay must not resurrect it.
        self.assertEqual(self.list(), [])
        with closing(sqlite3.connect(self.host.accounts.path)) as connection:
            self.assertEqual(connection.execute("SELECT content FROM email_memories").fetchone()[0], "")
            self.assertNotIn("舊的合成自介", str(connection.execute("SELECT result_json FROM memory_operations").fetchall()))

    def test_a05_only_selected_content_reaches_draft_and_model_facts(self):
        self.register()
        _, selected = self.memory("已確認的合成常用段落", "request")
        self.memory("未選取的私人合成文字", "other")
        class SpyModel:
            configured = True
            model = "offline-spy"
            def generate(self, facts):
                self.facts = facts
                return {"subject": "合成詢問", "body": "林老師您好：\n合成學生\n" + facts["saved_email_content"][0]["content"]}
        model = SpyModel()
        self.host.service.email_generator = model
        _, draft = self.selected_draft([self.ref(selected)])
        self.assertIn("已確認的合成常用段落", draft["email_draft"]["body"])
        serialized = json.dumps(model.facts, ensure_ascii=False)
        self.assertNotIn("未選取的私人合成文字", serialized)
        self.assertNotIn(PASSWORD, serialized)
        self.assertNotIn("username", model.facts)
        self.assertEqual(draft["email_draft"]["to"], "mikelin@mail.nutn.edu.tw")
        self.assertEqual(len(self.list()), 2)  # Draft generation never saves new memory.
        self.assertEqual(draft["memory_trace"]["selection"], [self.ref(selected)])

    def test_a06_deleting_memory_during_draft_discards_old_result(self):
        self.register()
        _, saved = self.memory()
        original = self.host.service.create_email_draft
        entered, release = threading.Event(), threading.Event()
        def slow(payload):
            result = original(payload)
            entered.set()
            if not release.wait(4):
                raise RuntimeError("offline test timed out")
            return result
        self.host.service.create_email_draft = slow
        output = []
        worker = threading.Thread(target=lambda: output.append(self.selected_draft([self.ref(saved)])))
        worker.start()
        self.assertTrue(entered.wait(2))
        try:
            self.call("/api/memory/write", {"action": "delete", "confirmed": True, "operation_id": secrets.token_hex(16), "memory_id": saved["memory_id"], "expected_version": 1})
        finally:
            release.set()
            worker.join(4)
        self.assertFalse(worker.is_alive())
        self.assertEqual(output[0][0], 404)
        self.assertEqual(self.host.service.pending_drafts, {})

    def test_a07_login_logout_rotate_sessions_and_clear_drafts(self):
        old_cookie, old_session = self.a, dict(self.sa)
        self.register()
        self.assertNotEqual(self.a, old_cookie)
        self.assertNotEqual(self.sa["csrf_token"], old_session["csrf_token"])
        self.assertEqual(self.host.handle(old_cookie, old_session["csrf_token"], "/api/memory/list", {"session_id": old_session["session_id"], "generation": 0})[0], 401)
        _, draft = self.draft()
        self.call("/api/auth/logout")
        self.assertIsNone(self.sa["account"])
        self.assertEqual(self.call("/api/email-send", {"draft_id": draft["draft_id"], "confirmed": True})[0], 404)

    def test_a08_password_hashes_and_failed_login(self):
        self.register()
        self.register("synthetic_b", browser="b")
        with closing(sqlite3.connect(self.host.accounts.path)) as connection:
            rows = connection.execute("SELECT salt, password_hash, iterations FROM local_accounts ORDER BY username").fetchall()
        self.assertNotEqual(rows[0][0], rows[1][0])
        self.assertNotEqual(rows[0][1], rows[1][1])
        self.assertEqual(rows[0][2], 600000)
        self.assertNotIn(PASSWORD.encode(), rows[0][1])
        self.call("/api/auth/logout")
        self.assertEqual(self.call("/api/auth/login", {"username": "synthetic_a", "password": "wrong-synthetic-password"})[0], 401)
        self.assertIsNone(self.sa["account"])

    def test_a09_guest_input_limits_and_raw_memory_cannot_bypass(self):
        self.assertEqual(self.call("/api/memory/list")[0], 401)
        self.assertEqual(self.memory()[0], 401)
        self.register()
        for patch in ({"content": []}, {"kind": "admin"}, {"content": "x" * 2001}, {"unexpected": "field"}):
            self.assertEqual(self.memory(**patch)[0], 422)
        self.assertEqual(self.list(), [])
        status, _ = self.call("/api/email-draft", {"teacher_name": "林朝興", "saved_email_content": [{"content": "forged"}]})
        self.assertEqual(status, 422)

    def test_a10_login_attempts_stop_at_limit(self):
        self.register()
        self.call("/api/auth/logout")
        for _ in range(9):
            self.call("/api/auth/login", {"username": "synthetic_a", "password": "wrong-synthetic-password"})
        # Register counted as an attempt for this username too.
        self.assertEqual(self.call("/api/auth/login", {"username": "synthetic_a", "password": PASSWORD})[0], 429)

    def test_a11_combined_memory_length_cannot_create_unwritable_draft(self):
        self.register()
        one = self.memory("甲" * 2000)[1]
        two = self.memory("乙" * 2000, "request")[1]
        status, response = self.selected_draft([self.ref(one), self.ref(two)])
        self.assertEqual(status, 422)
        self.assertEqual(response["error"]["code"], "CONTENT_TOO_LONG")
        self.assertEqual(self.host.service.pending_drafts, {})


class AccountHTTPTests(AccountFixture):
    def test_http_account_memory_roundtrip_cookie_rotation_and_bad_json(self):
        host = self.host
        class Handler(CampusRequestHandler):
            session_host = host
            def log_message(self, *args):
                pass
        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(server.server_close)
        self.addCleanup(lambda: thread.join(3))
        self.addCleanup(server.shutdown)
        url = f"http://127.0.0.1:{server.server_address[1]}"
        browser = request.build_opener(request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
        with browser.open(url + "/api/session", timeout=5) as response:
            session = json.load(response)["session"]
        with browser.open(url + "/api/config", timeout=5) as response:
            config = json.load(response)
            self.assertNotIn("public_examples", config)
            self.assertEqual(config["memory_contract"], "private-draft-revision-v3")
        def post(path, fields):
            nonlocal session
            req = request.Request(url + path, data=json.dumps({"session_id": session["session_id"], "generation": session["generation"], **fields}).encode(), headers={"Content-Type": "application/json", "X-CSRF-Token": session["csrf_token"]})
            with browser.open(req, timeout=5) as response:
                result = json.load(response)
                if result.get("session"):
                    session = result["session"]
                self.assertNotIn("_set_cookie", result)
                return result
        old_session = session["session_id"]
        post("/api/auth/register", {"username": "http_synthetic", "password": PASSWORD})
        self.assertNotEqual(old_session, session["session_id"])
        saved = post("/api/memory/write", {"action": "create", "confirmed": True, "operation_id": secrets.token_hex(16), "title": "常用面談", "kind": "request", "content": "請問可面談的時間，這是合成文字。"})
        post("/api/session/reset", {})
        self.assertEqual(post("/api/memory/list", {})["memories"][0]["memory_id"], saved["memory_id"])
        draft = post("/api/email-draft", {"teacher_name": "林朝興", "purpose": "other", "student_name": "合成學生", "request_details": "想詢問專題方向。", "memory_selections": [self.ref(saved)]})
        self.assertIn("請問可面談的時間", draft["email_draft"]["body"])
        post("/api/auth/logout", {})
        post("/api/auth/login", {"username": "http_synthetic", "password": PASSWORD})
        self.assertEqual(len(post("/api/memory/list", {})["memories"]), 1)
        source = post("/api/email-draft", {"teacher_name": "林朝興", "purpose": "answer_request", "student_name": "合成學生", "request_details": "請問本次微積分 Practice 的解答。"})
        full = post("/api/memory/write", {"action": "create", "confirmed": True,
                    "operation_id": secrets.token_hex(16), "title": "Practice 固定詢問", "kind": "draft_template",
                    "source_draft_id": source["draft_id"],
                    "content": source["email_draft"]["body"], "template_fields": {
                        "teacher_name": "林朝興", "subject": source["email_draft"]["subject"]}})
        rows = post("/api/memory/list", {})["memories"]
        stored = next(row for row in rows if row["memory_id"] == full["memory_id"])
        draft = post("/api/email-template-draft", {"teacher_name": stored["template_fields"]["teacher_name"],
                     "subject": stored["template_fields"]["subject"], "confirmed": True,
                     "body": stored["content"] + "本次是第 3 次。",
                     "memory_selections": [self.ref(full)]})
        self.assertEqual(draft["email_draft"]["to"], "mikelin@mail.nutn.edu.tw")
        self.assertIn("合成學生 敬上", draft["email_draft"]["body"])
        self.assertEqual(draft["email_draft"]["body"], stored["content"] + "本次是第 3 次。")
        self.assertEqual(draft["email_draft"]["body"].count("本次微積分"), 1)
        with self.assertRaises(error.HTTPError) as revision_error:
            post("/api/email-draft-revise", {"source_draft_id": draft["draft_id"], "instructions": "語氣簡短禮貌"})
        self.assertEqual(revision_error.exception.code, 503)
        failure = json.load(revision_error.exception)
        revision_error.exception.close()
        self.assertEqual(failure["generation"]["evidence_status"], "LIVE_NOT_RUN")
        self.assertIn(draft["draft_id"], host.service.pending_drafts)
        req = request.Request(url + "/api/chat", data=b"not-json", headers={"Content-Type": "application/json"})
        with self.assertRaises(error.HTTPError) as context:
            browser.open(req, timeout=5)
        self.assertEqual(context.exception.code, 400)
        context.exception.close()


if __name__ == "__main__":
    unittest.main(verbosity=2)
