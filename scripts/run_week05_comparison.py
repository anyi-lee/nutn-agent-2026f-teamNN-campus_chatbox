#!/usr/bin/env python3
"""Run the fixed Week 05 baseline/candidate acceptance slice offline."""

from __future__ import annotations

import importlib.metadata
import json
import sys
import unittest
import uuid
from datetime import datetime, timezone
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT))


TEST_NAMES = [
    "tests.test_gemini_email.GeminiEmailGeneratorTests.test_function_call_round_trip_uses_host_validated_read_tool",
    "tests.test_langchain_email.LangChainEmailGeneratorTests.test_real_create_agent_runtime_executes_tool_loop_offline",
    "tests.test_langchain_email.LangChainEmailGeneratorTests.test_candidate_rejects_changed_teacher_before_host_tool",
    "tests.test_langchain_email.LangChainEmailGeneratorTests.test_candidate_rejects_agent_that_skips_grounded_tool",
    "tests.test_langchain_email.LangChainEmailGeneratorTests.test_service_reports_langchain_backend_without_changing_write_gate",
    "tests.test_campus_service.CampusServiceTests.test_sandbox_send_requires_confirmation_and_is_idempotent",
]


def main() -> int:
    suite = unittest.defaultTestLoader.loadTestsFromNames(TEST_NAMES)
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    status = "WEEK05_OFFLINE_PASS" if result.wasSuccessful() else "WEEK05_OFFLINE_FAIL"
    summary = {
        "run_id": f"week05-{datetime.now(timezone.utc):%Y%m%dT%H%M%SZ}-{uuid.uuid4().hex[:6]}",
        "evidence_status": status,
        "live_model_called": False,
        "real_email_sent": False,
        "baseline_backend": "manual",
        "candidate_backend": "langchain",
        "framework_api_exercised": "langchain.agents.create_agent",
        "framework_versions": {
            "langchain": importlib.metadata.version("langchain"),
            "langchain-google-genai": importlib.metadata.version("langchain-google-genai"),
        },
        "cases_run": result.testsRun,
        "failures": len(result.failures),
        "errors": len(result.errors),
        "live_status": "LIVE_NOT_RUN",
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())
