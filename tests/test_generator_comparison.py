"""Tests for frozen-evidence Offline versus Fixture comparison."""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT / "src"))

from generator_comparison import build_generator_comparison  # noqa: E402


class GeneratorComparisonTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        retrieval_report = json.loads(
            (
                REPOSITORY_ROOT
                / "artifacts"
                / "week03-initial-retrieval.json"
            ).read_text(encoding="utf-8")
        )
        queries_document = json.loads(
            (REPOSITORY_ROOT / "data" / "fixed_queries.json").read_text(
                encoding="utf-8"
            )
        )
        cls.comparison = build_generator_comparison(
            retrieval_report, queries_document
        )

    def test_generators_use_identical_frozen_evidence(self) -> None:
        generators = self.comparison["generators"]

        self.assertEqual(len(generators), 2)
        self.assertTrue(self.comparison["checks"]["same_selected_evidence"])
        self.assertTrue(self.comparison["checks"]["same_frozen_evidence"])
        self.assertEqual(
            generators[0]["frozen_evidence_hash"],
            self.comparison["frozen_evidence"]["sha256"],
        )

    def test_generators_use_identical_citations(self) -> None:
        generators = self.comparison["generators"]

        self.assertTrue(self.comparison["checks"]["same_citations"])
        self.assertEqual(generators[0]["citations"], generators[1]["citations"])

    def test_fact_coverage_passes_without_unsupported_claims(self) -> None:
        checks = self.comparison["checks"]

        self.assertTrue(checks["fact_coverage"]["passed"])
        self.assertEqual(checks["fact_coverage"]["covered_count"], 2)
        self.assertEqual(checks["fact_coverage"]["required_count"], 2)
        self.assertEqual(checks["unsupported_claims"], [])

    def test_fixture_is_not_reported_as_live_llm_call(self) -> None:
        fixture = next(
            generator
            for generator in self.comparison["generators"]
            if generator["path"] == "gemini_fixture"
        )

        self.assertFalse(fixture["llm_actually_called"])
        self.assertFalse(self.comparison["checks"]["live_llm_called"])
        self.assertEqual(fixture["send_status"], "not_sent")

    def test_no_answer_blocks_generator(self) -> None:
        failure = self.comparison["failure_observation"]

        self.assertFalse(failure["can_answer"])
        self.assertEqual(failure["selected_evidence_ids"], [])
        self.assertEqual(failure["failure_code"], "INSUFFICIENT_EVIDENCE")
        self.assertFalse(failure["generator_called"])

    def test_all_comparison_checks_pass(self) -> None:
        self.assertTrue(self.comparison["checks_passed"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
