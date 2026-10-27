#!/usr/bin/env python3
"""Run the fixed Week 06 routing acceptance slice without calling Gemini."""

from __future__ import annotations

import json
import subprocess
import sys
import unittest
import uuid
from datetime import datetime, timezone
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT))

BASELINE_SHA = "e83196d"
TEST_NAMES = [
    "tests.test_week06_routing.Week06RoutingTests.test_normal_faculty_query_runs_one_allowed_branch",
    "tests.test_week06_routing.Week06RoutingTests.test_invalid_input_stops_before_router_and_retrieval",
    "tests.test_week06_routing.Week06RoutingTests.test_router_provider_failure_stops_before_retrieval",
    "tests.test_week06_routing.Week06RoutingTests.test_boundary_multi_intent_uses_clarify_without_downstream_call",
    "tests.test_week06_routing.Week06RoutingTests.test_unallowlisted_route_is_rejected_by_host_gate",
    "tests.test_week06_routing.Week06RoutingTests.test_office_route_uses_official_record_not_faculty_retrieval",
    "tests.test_week06_routing.Week06RoutingTests.test_email_route_exposes_draft_action_only_after_grounding",
    "tests.test_campus_service.CampusServiceTests.test_sandbox_send_requires_confirmation_and_is_idempotent",
]


def candidate_revision() -> str:
    sha = subprocess.run(
        ["git", "rev-parse", "--short", "HEAD"],
        cwd=REPOSITORY_ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    dirty = subprocess.run(
        ["git", "status", "--porcelain"],
        cwd=REPOSITORY_ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    return f"{sha}-WORKTREE" if dirty else sha


def main() -> int:
    suite = unittest.defaultTestLoader.loadTestsFromNames(TEST_NAMES)
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    status = "WEEK06_OFFLINE_PASS" if result.wasSuccessful() else "WEEK06_OFFLINE_FAIL"
    summary = {
        "run_id": f"week06-{datetime.now(timezone.utc):%Y%m%dT%H%M%SZ}-{uuid.uuid4().hex[:6]}",
        "evidence_status": status,
        "workflow": "routing",
        "baseline_sha": BASELINE_SHA,
        "candidate_revision": candidate_revision(),
        "routes": ["faculty_query", "office_query", "email_request", "clarify"],
        "cases_run": result.testsRun,
        "failures": len(result.failures),
        "errors": len(result.errors),
        "live_router_called": False,
        "live_status": "LIVE_NOT_RUN",
        "real_email_sent": False,
        "token_usage": "unavailable_offline_fixture",
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())
