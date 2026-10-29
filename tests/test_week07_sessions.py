"""W07 offline acceptance: real local HTTP and synthetic browser identities.

No Gemini request is made. Fault injections and model doubles are explicit.
"""
from __future__ import annotations

import http.cookiejar
import json
import shutil
import sqlite3
import sys
import tempfile
import threading
import unittest
from contextlib import closing
from http.server import ThreadingHTTPServer
from pathlib import Path
from urllib import error, request

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

from campus_service import CampusService
from email_tools import CampusToolServer
from gemini_email import GeminiEmailGenerator
from session_host import SessionHost
from app import CampusRequestHandler


class SessionFixture(unittest.TestCase):
    def setUp(self):
        (ROOT / "runtime").mkdir(exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(dir=ROOT / "runtime")
        self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name)
        self.faculty = self.directory / "faculty.json"
        self.office = self.directory / "office.json"
        shutil.copyfile(ROOT / "data/faculty_chunks.json", self.faculty)
        shutil.copyfile(ROOT / "data/office_chunks.json", self.office)
        self.database = self.directory / "outbox.sqlite3"

        def factory():
            document = json.loads(self.faculty.read_text(encoding="utf-8"))
            return CampusService(self.faculty, office_data_path=self.office,
                                 email_generator=GeminiEmailGenerator(api_key=""),
                                 workflow_backend="baseline",
                                 tool_server=CampusToolServer(document, self.database))
        self.host = SessionHost(factory, (self.faculty, self.office))
        self.a, self.sa = self.host.bootstrap(None)
        self.b, self.sb = self.host.bootstrap(None)

    def call(self, path, fields=None, *, owner=None, session=None):
        owner = owner or self.a
        session = session or self.sa
        status, result = self.host.handle(owner, session["csrf_token"], path, {
            "session_id": session["session_id"], "generation": session["generation"],
            **(fields or {}),
        })
        if owner == self.a and result.get("session"):
            self.sa = result["session"]
        return status, result

    def chat(self, text, **kwargs):
        return self.call("/api/chat", {"message": text}, **kwargs)

    def draft(self):
        return self.call("/api/email-draft", {
            "teacher_name": "林朝興", "purpose": "other", "student_name": "合成學生",
            "request_details": "想請問專題面談方式，這是測試資料。",
        })

    def count(self):
        with closing(sqlite3.connect(self.database)) as connection:
            return connection.execute("SELECT count(*) FROM sandbox_outbox").fetchone()[0]


class SessionTests(SessionFixture):
    def test_c01_followup_draft_confirm_and_replay(self):
        self.assertEqual(self.chat("林朝興老師的研究領域")[0], 200)
        _, reply = self.chat("他的 Email 是什麼？")
        self.assertTrue(reply["used_context"])
        self.assertIn("mikelin@mail.nutn.edu.tw", reply["answer"])
        _, draft = self.draft()
        args = {"draft_id": draft["draft_id"], "confirmed": True}
        _, first = self.call("/api/email-send", args)
        _, second = self.call("/api/email-send", args)
        self.assertEqual(first["status"], "simulated_sent")
        self.assertEqual(second["status"], "already_processed")
        self.assertEqual(first["receipt"]["message_id"], second["receipt"]["message_id"])
        self.assertEqual(self.count(), 1)
        self.assertEqual(draft["generation"]["evidence_status"], "LIVE_NOT_RUN")

    def test_c02_other_browser_has_no_context_or_draft_access(self):
        self.chat("林朝興老師的研究領域")
        _, draft = self.draft()
        _, other = self.chat("他的 Email 是什麼？", owner=self.b, session=self.sb)
        self.assertFalse(other["used_context"])
        self.assertIsNone(other["session"]["context_teacher"])
        status, _ = self.call("/api/email-send", {"draft_id": draft["draft_id"], "confirmed": True}, owner=self.b, session=self.sb)
        self.assertEqual(status, 404)
        self.assertEqual(self.count(), 0)
        self.call("/api/email-send", {"draft_id": draft["draft_id"], "confirmed": True})
        status, _ = self.call("/api/email-status", {"request_id": draft["request_id"]}, owner=self.b, session=self.sb)
        self.assertEqual(status, 404)

    def test_c03_reset_discards_context_and_old_draft(self):
        self.chat("林朝興老師的研究領域")
        _, draft = self.draft()
        self.call("/api/session/reset")
        _, response = self.chat("他的 Email 是什麼？")
        self.assertFalse(response["used_context"])
        status, _ = self.call("/api/email-send", {"draft_id": draft["draft_id"], "confirmed": True})
        self.assertEqual(status, 404)
        self.assertEqual(self.count(), 0)

    def test_c04_inflight_chat_cannot_repopulate_reset_context(self):
        original = self.host.service.chat
        entered, release = threading.Event(), threading.Event()
        def slow(*args, **kwargs):
            entered.set()
            if not release.wait(3):
                raise RuntimeError("test release timed out")
            return original(*args, **kwargs)
        self.host.service.chat = slow
        output = []
        worker = threading.Thread(target=lambda: output.append(self.chat("林朝興老師的研究領域")))
        worker.start()
        self.assertTrue(entered.wait(2))
        try:
            self.call("/api/session/reset")
        finally:
            release.set()
            worker.join(3)
        self.assertFalse(worker.is_alive())
        self.assertEqual(output[0][0], 409)
        self.assertEqual(output[0][1]["error"]["code"], "STALE_SESSION")
        self.assertIsNone(self.host.bootstrap(self.a)[1]["context_teacher"])

    def test_c04_inflight_draft_is_discarded_after_reset(self):
        original = self.host.service.create_email_draft
        service = self.host.service
        entered, release = threading.Event(), threading.Event()
        def slow(*args):
            entered.set()
            if not release.wait(3):
                raise RuntimeError("test release timed out")
            return original(*args)
        service.create_email_draft = slow
        output = []
        worker = threading.Thread(target=lambda: output.append(self.draft()))
        worker.start()
        self.assertTrue(entered.wait(2))
        try:
            self.call("/api/session/reset")
        finally:
            release.set()
            worker.join(3)
        self.assertEqual(output[0][0], 409)
        self.assertEqual(service.pending_drafts, {})

    def test_c05_source_v2_reloads_and_invalidates_old_context_and_draft(self):
        self.chat("林朝興老師的研究領域")
        _, draft = self.draft()
        old = dict(self.sa)
        document = json.loads(self.faculty.read_text(encoding="utf-8"))
        document["source"]["index_version"] = "synthetic-v2"
        teacher = document["chunks"][0]
        teacher["public_email"] = "synthetic-v2@example.invalid"
        teacher["content"] = teacher["content"].replace("mikelin@mail.nutn.edu.tw", teacher["public_email"])
        self.faculty.write_text(json.dumps(document, ensure_ascii=False), encoding="utf-8")
        status, result = self.chat("他的 Email 是什麼？", session=old)
        self.assertEqual(status, 409)
        self.assertIsNone(result["session"]["context_teacher"])
        self.assertEqual(result["session"]["cleared_reason"], "source_changed")
        self.assertNotEqual(result["session"]["source_version"], old["source_version"])
        _, explicit = self.chat("林朝興老師的 Email")
        self.assertIn("synthetic-v2@example.invalid", explicit["answer"])
        status, _ = self.call("/api/email-send", {"draft_id": draft["draft_id"], "confirmed": True})
        self.assertEqual(status, 404)

    def test_c06_topic_change_clears_teacher(self):
        self.chat("林朝興老師的研究領域")
        self.chat("資工系辦電話")
        _, response = self.chat("他的 Email 是什麼？")
        self.assertFalse(response["used_context"])
        self.assertIsNone(response["session"]["context_teacher"])

    def test_c05_withdrawn_teacher_cannot_reenter_context_or_draft(self):
        self.chat("林朝興老師的研究領域")
        document = json.loads(self.faculty.read_text(encoding="utf-8"))
        document["chunks"][0]["validity"] = "inactive"
        self.faculty.write_text(json.dumps(document, ensure_ascii=False), encoding="utf-8")
        self.sa = self.host.bootstrap(self.a)[1]
        _, result = self.chat("林朝興老師的研究領域")
        self.assertEqual(result["status"], "insufficient_evidence")
        self.assertIsNone(result["session"]["context_teacher"])
        status, result = self.draft()
        self.assertEqual(status, 409)
        self.assertEqual(result["error"]["code"], "TEACHER_SOURCE_INVALID")
        self.assertEqual(self.host.service.pending_drafts, {})
        self.assertEqual(self.count(), 0)

    def test_c06_invalid_input_cannot_reuse_context(self):
        self.chat("林朝興老師的研究領域")
        for fields in ({"message": []}, {"message": "你好", "retriever": "evil"}, {"message": "你好", "context_teacher": "林朝興"}):
            status, _ = self.call("/api/chat", fields)
            self.assertEqual(status, 422)

    def test_c06_corrupt_source_fails_closed_then_recovers(self):
        self.chat("林朝興老師的研究領域")
        source = self.faculty.read_bytes()
        self.faculty.write_text("not json", encoding="utf-8")
        status, result = self.chat("他的 Email 是什麼？")
        self.assertEqual(status, 503)
        self.assertIsNone(result["session"]["context_teacher"])
        self.faculty.write_bytes(source)
        self.sa = self.host.bootstrap(self.a)[1]
        _, result = self.chat("他的 Email 是什麼？")
        self.assertFalse(result["used_context"])

    def test_c06_provider_exception_clears_context_and_releases_busy(self):
        self.chat("林朝興老師的研究領域")
        original = self.host.service.chat
        def fail(*args):
            raise RuntimeError("offline provider failure injection")
        self.host.service.chat = fail
        with self.assertRaises(RuntimeError):
            self.chat("他的 Email 是什麼？")
        self.host.service.chat = original
        self.assertIsNone(self.host.bootstrap(self.a)[1]["context_teacher"])
        self.assertEqual(self.chat("林朝興老師的研究領域")[0], 200)

    def test_w01_missing_confirmation_and_forged_identity_do_not_write(self):
        _, draft = self.draft()
        status, _ = self.call("/api/email-send", {"draft_id": draft["draft_id"], "confirmed": False})
        self.assertEqual(status, 409)
        status, _ = self.call("/api/email-send", {"draft_id": draft["draft_id"], "confirmed": True, "user_id": self.a})
        self.assertEqual(status, 422)
        self.assertEqual(self.count(), 0)

    def test_w02_receipt_survives_conversation_clear_without_new_write(self):
        _, draft = self.draft()
        self.call("/api/email-send", {"draft_id": draft["draft_id"], "confirmed": True})
        self.call("/api/session/reset")
        status, receipt = self.call("/api/email-status", {"request_id": draft["request_id"]})
        self.assertEqual(status, 200)
        self.assertEqual(receipt["status"], "simulated_sent")
        self.assertEqual(self.count(), 1)

    def test_session_and_csrf_are_required(self):
        fields = {"session_id": self.sa["session_id"], "generation": 0, "message": "林朝興"}
        self.assertEqual(self.host.handle(None, "", "/api/chat", fields)[0], 401)
        self.assertEqual(self.host.handle(self.a, "錯誤 token", "/api/chat", fields)[0], 403)
        fields["generation"] = True
        self.assertEqual(self.host.handle(self.a, self.sa["csrf_token"], "/api/chat", fields)[0], 409)

    def test_router_receives_only_current_session_context(self):
        class SpyRouter:
            provider = "offline_fixture"
            model = "offline-router"
            evidence_mode = "offline_fixture"
            configured = True
            def __init__(self):
                self.contexts = []
            def route(self, message, *, context_teacher=None):
                self.contexts.append(context_teacher)
                return {"route": "faculty_query", "reason_code": "faculty_information"}
        router = SpyRouter()
        self.host.service.chat_workflow_backend = "routing"
        self.host.service.chat_router = router
        self.chat("林朝興老師的研究領域")
        self.chat("他的 Email 是什麼？")
        self.call("/api/session/reset")
        self.chat("他的 Email 是什麼？")
        self.assertEqual(router.contexts, [None, "林朝興", None])


class HTTPTests(SessionFixture):
    def test_http_cookie_csrf_and_browser_isolation(self):
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
        browser_a = request.build_opener(request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
        browser_b = request.build_opener(request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
        def bootstrap(browser):
            with browser.open(url + "/api/session") as response:
                self.assertIn("HttpOnly", response.headers["Set-Cookie"])
                return json.load(response)["session"]
        sa, sb = bootstrap(browser_a), bootstrap(browser_b)
        def post(browser, session, fields, **headers):
            req = request.Request(url + "/api/chat", data=json.dumps({"session_id": session["session_id"], "generation": session["generation"], **fields}).encode(), headers={"Content-Type": "application/json", "X-CSRF-Token": session["csrf_token"], **headers})
            with browser.open(req) as response:
                return json.load(response)
        post(browser_a, sa, {"message": "林朝興老師的研究領域"})
        self.assertFalse(post(browser_b, sb, {"message": "他的 Email 是什麼？"})["used_context"])
        for headers, expected in (({"X-CSRF-Token": "wrong"}, 403), ({"Origin": "https://untrusted.example"}, 403), ({"Host": "untrusted.example"}, 403)):
            with self.assertRaises(error.HTTPError) as context:
                post(browser_a, sa, {"message": "他的 Email 是什麼？"}, **headers)
            self.assertEqual(context.exception.code, expected)
            context.exception.close()


if __name__ == "__main__":
    unittest.main(verbosity=2)
