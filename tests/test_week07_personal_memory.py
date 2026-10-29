"""Offline personal fact acceptance; isolated stores and synthetic identities."""
import secrets
from test_week07_account_memory import AccountFixture, PASSWORD
from personal_memory import candidates_from_message
from session_host import SessionHost


class PersonalMemoryTests(AccountFixture):
    def candidate(self, text="我的微積分老師是林朝興"):
        status, result = self.chat(text)
        self.assertEqual(status, 200)
        return result["personal_memory_candidates"][0]

    def save(self, candidate, **extra):
        return self.call("/api/personal-memory/save", {
            "candidate_id": candidate["candidate_id"], "confirmed": True,
            "operation_id": secrets.token_hex(16), **extra})

    def test_guest_cannot_collect_or_save(self):
        self.assertEqual(self.chat("我的微積分老師是林朝興")[1]["personal_memory_candidates"], [])
        self.assertEqual(self.save({"candidate_id": "forged"})[0], 401)

    def test_explicit_confirmation_and_replay(self):
        self.register()
        candidate = self.candidate()
        self.assertEqual(self.list(), [])
        self.assertEqual(self.save(candidate, confirmed=False)[0], 409)
        op = secrets.token_hex(16)
        first = self.save(candidate, operation_id=op)[1]
        replay = self.save(candidate, operation_id=op)[1]
        self.assertEqual(first["memory_id"], replay["memory_id"])
        self.assertTrue(replay["idempotent_replay"])
        self.assertEqual(len(self.list()), 1)

    def test_overwrite_same_key_and_keep_other_facts(self):
        self.register()
        first = self.save(self.candidate())[1]
        self.save(self.candidate("我的系所是資訊工程學系"))
        changed = self.candidate("我的微積分老師是新的合成教師")
        self.assertEqual(changed["previous_content"], "林朝興")
        saved = self.save(changed)[1]
        self.assertEqual(saved["memory_id"], first["memory_id"])
        self.assertEqual(saved["version"], 2)
        self.assertEqual(len(self.list()), 2)
        self.assertIn("新的合成教師", self.chat("我的微積分老師是誰？")[1]["answer"])

    def test_conflict_requires_new_preview(self):
        self.register()
        pending = self.candidate()
        self.memory("另一位教師", "personal_fact", title="我的微積分老師")
        self.assertEqual(self.save(pending)[0], 409)
        pending = self.candidate("我的微積分老師是新的教師")
        row = self.list()[0]
        self.call("/api/memory/write", {"action": "update", "confirmed": True,
            "operation_id": secrets.token_hex(16), "memory_id": row["memory_id"], "expected_version": row["version"],
            "title": row["title"], "kind": "personal_fact", "content": "並行修改的教師"})
        self.assertEqual(self.save(pending)[0], 409)
        self.assertEqual(self.list()[0]["content"], "並行修改的教師")

    def test_candidate_bound_to_account_and_reset(self):
        self.register()
        candidate = self.candidate()
        self.register("synthetic_b", browser="b")
        self.assertEqual(self.call("/api/personal-memory/save", {"candidate_id": candidate["candidate_id"],
            "confirmed": True, "operation_id": secrets.token_hex(16)}, owner=self.b, session=self.sb)[0], 409)
        self.call("/api/session/reset")
        self.assertEqual(self.save(candidate)[0], 409)
        self.assertEqual(self.list(), [])

    def test_restart_read_and_delete(self):
        self.register()
        self.save(self.candidate())
        self.host = SessionHost(self.host._factory, (self.faculty, self.office))
        self.a, self.sa = self.host.bootstrap(None)
        self.call("/api/auth/login", {"username": "synthetic_a", "password": PASSWORD})
        answer = self.chat("我的微積分老師是誰？")[1]
        self.assertIn("林朝興", answer["answer"])
        self.assertEqual(answer["citations"], [])
        self.assertEqual(len(answer["personal_memory_used"]), 1)
        row = self.list()[0]
        self.call("/api/memory/write", {"action": "delete", "confirmed": True,
            "operation_id": secrets.token_hex(16), "memory_id": row["memory_id"], "expected_version": row["version"]})
        self.assertEqual(self.chat("我的微積分老師是誰？")[1]["personal_memory_used"], [])

    def test_teacher_reference_uses_official_query(self):
        self.register()
        self.save(self.candidate())
        result = self.chat("我的微積分老師的研究領域是什麼？")[1]
        self.assertEqual(result.get("detected_teacher"), "林朝興")
        self.assertTrue(result.get("citations"))
        self.assertEqual(result["personal_memory_used"][0]["title"], "我的微積分老師")

    def test_extractor_ignores_questions_secrets_and_model_answers(self):
        self.assertEqual(candidates_from_message("我的微積分老師是誰？"), [])
        self.assertEqual(candidates_from_message("我的密碼是test-only"), [])
        self.assertEqual(candidates_from_message("我的老師是可能的教師"), [])
        self.assertEqual(candidates_from_message("我的老師是林朝興嗎"), [])
        self.assertEqual(candidates_from_message("我的老師不是林朝興"), [])
        self.assertEqual(len(candidates_from_message("我的系所是資訊工程學系，我的年級是三年級")), 2)
        self.register()
        self.chat("我的微積分老師是誰？")
        self.assertEqual(self.list(), [])

    def test_personal_facts_are_not_email_snippets(self):
        self.register()
        saved = self.save(self.candidate())[1]
        self.assertEqual(self.selected_draft([self.ref(saved)])[0], 422)

    def test_previous_chat_candidate_remains_selectable(self):
        self.register()
        candidate = self.candidate()
        self.chat("林朝興老師的研究領域")
        self.assertEqual(self.save(candidate)[0], 200)

    def test_case_normalization_and_untrusted_save_payload(self):
        self.register()
        candidate = self.candidate("我的 微積分老師是林朝興")
        self.assertEqual(candidate["title"], "我的微積分老師")
        self.save(candidate, content="forged", title="forged", memory_id="forged")
        self.assertEqual(self.list()[0]["content"], "林朝興")
        self.assertEqual(self.list()[0]["title"], "我的微積分老師")

    def test_unresolved_teacher_never_reuses_previous_teacher(self):
        self.register()
        self.save(self.candidate("我的微積分老師是未知的合成教師"))
        self.chat("林朝興老師的研究領域")
        result = self.chat("我的微積分老師的研究領域是什麼？")[1]
        self.assertEqual(result["error"]["code"], "PERSONAL_TEACHER_UNRESOLVED")
        self.assertEqual(result["citations"], [])
        self.assertIsNone(result.get("detected_teacher"))
