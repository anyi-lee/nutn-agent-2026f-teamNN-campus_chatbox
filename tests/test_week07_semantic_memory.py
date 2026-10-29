"""Semantic-memory tests use explicit offline model doubles, never Gemini."""
import json
import threading
import unittest
from test_week07_account_memory import AccountFixture
from personal_memory import GeminiPersonalMemoryPlanner, validate_plan
from gemini_email import GeminiEmailGenerator, GeminiEmailError


def decision(intent="none", **extra):
    return {"intent": intent, "proposals": [], "read_memory_ids": [], "teacher_memory_id": "",
            "resolved_query": "", "clarification": "", **extra}


class OfflinePlanner:
    configured = True
    evidence_mode = "offline"
    model = "offline-semantic-spy"

    def __init__(self, response):
        self.response, self.calls = response, []

    def plan(self, message, memories):
        self.calls.append((message, memories))
        if isinstance(self.response, Exception):
            raise self.response
        return self.response


class SemanticMemoryTests(AccountFixture):
    def seed(self):
        self.register()
        return self.memory("林朝興", "personal_fact", title="我的微積分老師")[1]

    def planner(self, plan):
        self.host.memory_planner = OfflinePlanner(plan)
        return self.host.memory_planner

    def save(self, candidate):
        return self.call("/api/personal-memory/save", {"candidate_id": candidate["candidate_id"],
            "operation_id": "synthetic-semantic-operation", "confirmed": True})

    def test_natural_statement_has_proposal_but_no_automatic_write(self):
        self.register()
        message = "這學期微積分給林朝興教，幫我記一下"
        self.planner(decision("remember", proposals=[{"title": "我的微積分老師", "content": "林朝興",
            "replaces_memory_id": "", "evidence_quote": "這學期微積分給林朝興教"}]))
        result = self.chat(message)[1]
        self.assertEqual(self.list(), [])
        self.assertEqual(result["personal_memory_analysis"]["backend"], "gemini")
        self.assertEqual(result["personal_memory_analysis"]["live_status"], "LIVE_NOT_RUN")
        self.assertEqual(self.save(result["personal_memory_candidates"][0])[0], 200)
        self.assertEqual(self.list()[0]["content"], "林朝興")

    def test_semantic_recall_does_not_require_same_words(self):
        row = self.seed()
        self.planner(decision("recall", read_memory_ids=[row["memory_id"]]))
        for text in ("找微積分老師", "微積分要找哪位？", "教我微積分的是誰"):
            result = self.chat(text)[1]
            self.assertIn("林朝興", result["answer"])
            self.assertEqual(len(result["personal_memory_used"]), 1)

    def test_semantic_teacher_query_uses_official_pipeline(self):
        row = self.seed()
        self.planner(decision("campus_query", read_memory_ids=[row["memory_id"]], teacher_memory_id=row["memory_id"],
            resolved_query="林朝興老師的研究領域是什麼？"))
        result = self.chat("教我微積分的老師做哪方面研究")[1]
        self.assertEqual(result["detected_teacher"], "林朝興")
        self.assertTrue(result["citations"])

    def test_semantic_update_preserves_same_key_until_confirmation(self):
        row = self.seed()
        text = "微積分換成新的合成教師教了"
        self.planner(decision("remember", proposals=[{"title": "微積分任課教師", "content": "新的合成教師",
            "replaces_memory_id": row["memory_id"], "evidence_quote": text}]))
        candidate = self.chat(text)[1]["personal_memory_candidates"][0]
        self.assertEqual(candidate["title"], "我的微積分老師")
        self.assertEqual(candidate["previous_content"], "林朝興")
        self.assertEqual(self.list()[0]["content"], "林朝興")
        self.assertEqual(self.save(candidate)[1]["version"], 2)
        self.assertEqual(len(self.list()), 1)

    def test_unowned_id_and_fabricated_value_are_rejected(self):
        self.register()
        invalid_plans = [decision("recall", read_memory_ids=["foreign-id"]),
            decision("remember", proposals=[{"title": "我的老師", "content": "捏造的教師",
                "replaces_memory_id": "", "evidence_quote": "這學期微積分給林朝興教"}])]
        for plan in invalid_plans:
            self.planner(plan)
            result = self.chat("這學期微積分給林朝興教")[1]
            self.assertEqual(result["personal_memory_analysis"]["status"], "semantic_failed_fallback")
            self.assertEqual(result["personal_memory_candidates"], [])
            self.assertEqual(self.list(), [])

    def test_provider_failure_is_labelled_and_basic_examples_work(self):
        self.register()
        self.planner(GeminiEmailError("Gemini HTTP 503: synthetic provider unavailable"))
        result = self.chat("微積分老師是林朝興")[1]
        self.assertEqual(result["personal_memory_analysis"]["status"], "semantic_failed_fallback")
        self.assertEqual(self.save(result["personal_memory_candidates"][0])[0], 200)
        result = self.chat("找微積分老師")[1]
        self.assertEqual(result["detected_teacher"], "林朝興")

    def test_ambiguity_does_not_change_memory(self):
        self.seed()
        self.planner(decision("clarify", clarification="你指哪一門微積分課？"))
        result = self.chat("微積分那個老師換人了")[1]
        self.assertEqual(result["error"]["code"], "MEMORY_NEEDS_CLARIFICATION")
        self.assertEqual(result["personal_memory_candidates"], [])
        self.assertEqual(self.list()[0]["content"], "林朝興")

    def test_guest_does_not_call_planner(self):
        planner = self.planner(decision())
        self.chat("微積分老師是林朝興")
        self.assertEqual(planner.calls, [])

    def test_reset_wins_during_semantic_model_work(self):
        self.seed()
        entered, release = threading.Event(), threading.Event()
        planner = self.planner(decision())
        def blocked(message, memories):
            entered.set()
            if not release.wait(5):
                raise RuntimeError("offline test model wait timed out")
            return decision()
        planner.plan = blocked
        response = []
        worker = threading.Thread(target=lambda: response.append(self.chat("找微積分老師")))
        worker.start()
        try:
            self.assertTrue(entered.wait(5))
            self.assertEqual(self.call("/api/session/reset")[0], 200)
        finally:
            release.set()
            worker.join(5)
        self.assertFalse(worker.is_alive())
        self.assertEqual(response[0][0], 409)
        self.assertEqual(self.host._users[self.a].personal_candidates, {})

    def test_current_explicit_teacher_is_not_overridden_by_memory(self):
        row = self.seed()
        other = next(name for name in self.host.service.teacher_by_name if name != "林朝興")
        self.planner(decision("campus_query", read_memory_ids=[row["memory_id"]], teacher_memory_id=row["memory_id"],
            resolved_query="林朝興老師的研究領域"))
        result = self.chat(f"請查{other}老師的研究領域")[1]
        self.assertEqual(result["detected_teacher"], other)
        self.assertEqual(result["personal_memory_used"], [])

    def test_memory_version_is_rechecked_after_model_returns(self):
        row = self.seed()
        planner = self.planner(decision())
        def update_during_plan(message, memories):
            self.memory("新的合成教師", "personal_fact", action="update", memory_id=row["memory_id"],
                        expected_version=1, title="我的微積分老師")
            return decision("recall", read_memory_ids=[row["memory_id"]])
        planner.plan = update_during_plan
        status, result = self.chat("找微積分老師")
        self.assertEqual(status, 409)
        self.assertEqual(result["error"]["code"], "MEMORY_VERSION_CONFLICT")


class SemanticPlannerContractTests(unittest.TestCase):
    def test_transport_uses_structured_schema_and_only_personal_facts(self):
        client = GeminiEmailGenerator(api_key="synthetic-offline-key")
        captured = []
        def post(payload):
            captured.append(payload)
            return {"candidates": [{"content": {"parts": [{"text": json.dumps(decision())}]}}]}
        client._post = post
        planner = GeminiPersonalMemoryPlanner(client)
        planner.plan("你好", [{"kind": "signature", "content": "private email signature"},
            {"kind": "personal_fact", "memory_id": "owned", "title": "我的系所", "content": "合成系所", "version": 1}])
        serialized = json.dumps(captured)
        self.assertNotIn("synthetic-offline-key", serialized)
        self.assertNotIn("private email signature", serialized)
        self.assertIn("owned", serialized)
        self.assertEqual(captured[0]["generationConfig"]["responseFormat"]["text"]["mimeType"], "APPLICATION_JSON")

    def test_malformed_model_json_is_rejected(self):
        client = GeminiEmailGenerator(api_key="synthetic-offline-key")
        client._post = lambda payload: {"candidates": [{"content": {"parts": [{"text": "invalid JSON"}]}}]}
        with self.assertRaises(GeminiEmailError):
            GeminiPersonalMemoryPlanner(client).plan("找老師", [])

    def test_credential_proposal_is_rejected(self):
        with self.assertRaises(GeminiEmailError):
            validate_plan(decision("remember", proposals=[{"title": "我的密碼", "content": "synthetic",
                "replaces_memory_id": "", "evidence_quote": "我的密碼是synthetic"}]), "我的密碼是synthetic", [])
