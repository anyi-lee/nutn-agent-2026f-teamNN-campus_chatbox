"""Tests for the Week 03 BM25 retrieval baseline and evidence gate."""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT / "src"))

from retrieval_baseline import run_initial_retrieval, tokenize  # noqa: E402


class RetrievalBaselineTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        chunks_document = json.loads(
            (REPOSITORY_ROOT / "data" / "faculty_chunks.json").read_text(
                encoding="utf-8"
            )
        )
        queries_document = json.loads(
            (REPOSITORY_ROOT / "data" / "fixed_queries.json").read_text(
                encoding="utf-8"
            )
        )
        cls.report = run_initial_retrieval(chunks_document, queries_document)
        cls.traces = {
            trace["query_id"]: trace for trace in cls.report["traces"]
        }

    def test_tokenizer_emits_cjk_unigrams_and_bigrams(self) -> None:
        tokens = tokenize("聯絡 Email")

        self.assertIn("聯", tokens)
        self.assertIn("聯絡", tokens)
        self.assertIn("email", tokens)

    def test_normal_query_returns_gold_evidence(self) -> None:
        trace = self.traces["q-normal-email"]

        self.assertTrue(trace["gold_in_top_k"])
        self.assertEqual(trace["candidates"][0]["chunk_id"], "faculty-mikelin")
        self.assertEqual(trace["selected_evidence_ids"], ["faculty-mikelin"])
        self.assertTrue(trace["can_answer"])
        self.assertIsNone(trace["failure_code"])

    def test_paraphrase_query_returns_same_gold_evidence(self) -> None:
        normal = self.traces["q-normal-email"]
        paraphrase = self.traces["q-paraphrase-contact"]

        self.assertTrue(paraphrase["gold_in_top_k"])
        self.assertEqual(
            paraphrase["selected_evidence_ids"], normal["selected_evidence_ids"]
        )
        self.assertEqual(paraphrase["citations"], normal["citations"])

    def test_no_answer_retrieves_name_but_evidence_gate_abstains(self) -> None:
        trace = self.traces["q-no-answer-office-hours"]
        candidate_ids = [candidate["chunk_id"] for candidate in trace["candidates"]]

        self.assertIn("faculty-mikelin", candidate_ids)
        self.assertFalse(trace["can_answer"])
        self.assertEqual(trace["selected_evidence_ids"], [])
        self.assertEqual(trace["citations"], [])
        self.assertEqual(trace["failure_code"], "INSUFFICIENT_EVIDENCE")

    def test_all_fixed_query_expectations_pass(self) -> None:
        summary = self.report["summary"]

        self.assertEqual(summary["query_count"], 3)
        self.assertEqual(summary["expectations_passed"], 3)
        self.assertEqual(summary["recall_at_3_answerable"], 1.0)
        self.assertEqual(summary["abstention_accuracy"], 1.0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
