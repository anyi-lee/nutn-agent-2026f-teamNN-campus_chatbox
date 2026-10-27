"""Offline acceptance tests for the Week 06 routing workflow."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT / "src"))

from campus_service import CampusService  # noqa: E402
from gemini_email import GeminiEmailGenerator  # noqa: E402
from gemini_router import GeminiRouterError  # noqa: E402


class FixtureRouter:
    """Deterministic router double; it does not represent a live model run."""

    provider = "fixture"
    model = "router-fixture-v1"
    configured = True
    configuration_error = None
    evidence_mode = "offline_fixture"

    def __init__(self, route: str, reason_code: str) -> None:
        self.decision = {"route": route, "reason_code": reason_code}
        self.calls = 0

    def route(self, message: str, *, context_teacher: str | None = None):
        self.calls += 1
        return dict(self.decision)


class FailingRouter(FixtureRouter):
    def __init__(self) -> None:
        super().__init__("faculty_query", "faculty_information")

    def route(self, message: str, *, context_teacher: str | None = None):
        self.calls += 1
        raise GeminiRouterError("offline provider failure fixture")


class CountingCampusService(CampusService):
    def __init__(self, router: FixtureRouter) -> None:
        self.retrieval_calls = 0
        super().__init__(
            email_generator=GeminiEmailGenerator(api_key=""),
            chat_router=router,
            workflow_backend="routing",
        )

    def _retrieve(self, query: str, retriever: str):
        self.retrieval_calls += 1
        return super()._retrieve(query, retriever)


class Week06RoutingTests(unittest.TestCase):
    def service_for(self, route: str, reason_code: str) -> CountingCampusService:
        return CountingCampusService(FixtureRouter(route, reason_code))

    def test_normal_faculty_query_runs_one_allowed_branch(self) -> None:
        service = self.service_for("faculty_query", "faculty_information")

        response = service.chat("林朝興老師的研究領域", "bm25")

        self.assertEqual(response["status"], "ok")
        self.assertEqual(response["workflow"]["route"], "faculty_query")
        self.assertEqual(response["workflow"]["status"], "completed")
        self.assertEqual(response["workflow"]["live_status"], "LIVE_NOT_RUN")
        self.assertEqual(
            response["workflow"]["stages"][-1]["downstream_calls"], 1
        )
        self.assertEqual(service.retrieval_calls, 1)

    def test_invalid_input_stops_before_router_and_retrieval(self) -> None:
        router = FixtureRouter("faculty_query", "faculty_information")
        service = CountingCampusService(router)

        response = service.chat("   ", "bm25")

        self.assertEqual(response["status"], "invalid_request")
        self.assertEqual(response["workflow"]["stop_reason"], "invalid_input")
        self.assertEqual(router.calls, 0)
        self.assertEqual(service.retrieval_calls, 0)

    def test_router_provider_failure_stops_before_retrieval(self) -> None:
        router = FailingRouter()
        service = CountingCampusService(router)

        response = service.chat("林朝興老師的研究領域", "bm25")

        self.assertEqual(response["status"], "provider_failed")
        self.assertEqual(response["error"]["code"], "ROUTER_PROVIDER_FAILED")
        self.assertEqual(response["workflow"]["stop_reason"], "provider_failed")
        self.assertEqual(response["workflow"]["live_status"], "LIVE_NOT_RUN")
        self.assertIsNone(response["retrieval"])
        self.assertEqual(service.retrieval_calls, 0)

    def test_boundary_multi_intent_uses_clarify_without_downstream_call(self) -> None:
        service = self.service_for("clarify", "ambiguous_or_unsupported")

        response = service.chat("查林老師研究領域，順便寫信問系辦時間", "bm25")

        self.assertEqual(response["status"], "needs_clarification")
        self.assertEqual(response["workflow"]["route"], "clarify")
        self.assertEqual(
            response["workflow"]["stages"][-1]["downstream_calls"], 0
        )
        self.assertIsNone(response["retrieval"])
        self.assertEqual(service.retrieval_calls, 0)

    def test_unallowlisted_route_is_rejected_by_host_gate(self) -> None:
        service = self.service_for("weather_tool", "faculty_information")

        response = service.chat("今天天氣如何", "bm25")

        self.assertEqual(response["status"], "route_rejected")
        self.assertEqual(response["error"]["code"], "ROUTE_DECISION_INVALID")
        self.assertEqual(response["workflow"]["stop_reason"], "route_rejected")
        self.assertEqual(service.retrieval_calls, 0)

    def test_office_route_uses_official_record_not_faculty_retrieval(self) -> None:
        service = self.service_for("office_query", "office_information")

        response = service.chat("資工系辦電話和地址", "bm25")

        self.assertEqual(response["status"], "ok")
        self.assertEqual(response["workflow"]["route"], "office_query")
        self.assertEqual(response["retrieval"]["model"], "official_record")
        self.assertEqual(service.retrieval_calls, 0)

    def test_email_route_exposes_draft_action_only_after_grounding(self) -> None:
        service = self.service_for("email_request", "email_action")

        response = service.chat("幫我寫信給林朝興老師詢問加簽", "bm25")

        self.assertEqual(response["status"], "ok")
        self.assertEqual(response["workflow"]["route"], "email_request")
        self.assertEqual(response["suggested_action"], "email_draft")
        self.assertEqual(response["detected_purpose"], "course_add_request")
        self.assertEqual(response["detected_teacher"], "林朝興")

    def test_config_discloses_workflow_and_allowlist(self) -> None:
        service = self.service_for("faculty_query", "faculty_information")

        config = service.config()["chat_workflow"]

        self.assertEqual(config["backend"], "routing")
        self.assertIn("clarify", config["allowed_routes"])


if __name__ == "__main__":
    unittest.main()
