"""Tests for the transparent dense_stub and BM25 comparison."""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT / "src"))

from dense_stub import CONCEPTS, DenseStubRetriever, cosine_similarity  # noqa: E402
from retriever_comparison import compare_retrievers  # noqa: E402


class DenseStubTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.chunks_document = json.loads(
            (REPOSITORY_ROOT / "data" / "faculty_chunks.json").read_text(
                encoding="utf-8"
            )
        )
        cls.queries_document = json.loads(
            (REPOSITORY_ROOT / "data" / "fixed_queries.json").read_text(
                encoding="utf-8"
            )
        )
        cls.retriever = DenseStubRetriever(cls.chunks_document["chunks"])
        cls.comparison = compare_retrievers(
            cls.chunks_document, cls.queries_document
        )

    def test_cosine_returns_zero_for_zero_vector(self) -> None:
        zero = [0] * len(CONCEPTS)
        one = [1] + [0] * (len(CONCEPTS) - 1)

        self.assertEqual(cosine_similarity(zero, one), 0.0)
        self.assertEqual(cosine_similarity(zero, zero), 0.0)

    def test_normal_query_activates_identity_and_contact(self) -> None:
        result = self.retriever.search("林朝興教授的 Email 是什麼？", top_k=3)

        self.assertIn("faculty_mikelin", result["query_active_concepts"])
        self.assertIn("contact", result["query_active_concepts"])
        self.assertNotIn("ai", result["query_active_concepts"])
        self.assertEqual(result["candidates"][0]["chunk_id"], "faculty-mikelin")

    def test_short_latin_alias_requires_a_complete_word(self) -> None:
        result = self.retriever.encode_query("請問 Email 是什麼？")

        self.assertIn("contact", result["active_concepts"])
        self.assertNotIn("ai", result["active_concepts"])

    def test_paraphrase_query_keeps_same_dense_top_1(self) -> None:
        result = self.retriever.search("我要怎麼聯絡林朝興老師？", top_k=3)

        self.assertEqual(result["candidates"][0]["chunk_id"], "faculty-mikelin")

    def test_alias_miss_produces_zero_vector_and_scores(self) -> None:
        observation = self.comparison["zero_vector_observation"]

        self.assertTrue(observation["query_is_zero_vector"])
        self.assertEqual(observation["query_active_concepts"], [])
        self.assertTrue(observation["all_cosine_scores_zero"])

    def test_bm25_and_dense_stub_retrieve_gold_in_top_3(self) -> None:
        metrics = self.comparison["metrics"]

        self.assertEqual(metrics["bm25"]["recall_at_3"], 1.0)
        self.assertEqual(metrics["dense_stub"]["recall_at_3"], 1.0)
        self.assertEqual(metrics["bm25"]["mrr"], 1.0)
        self.assertEqual(metrics["dense_stub"]["mrr"], 1.0)

    def test_no_answer_still_ranks_named_teacher_first(self) -> None:
        trace = next(
            trace
            for trace in self.comparison["query_traces"]
            if trace["query_type"] == "no_answer"
        )

        self.assertEqual(
            trace["dense_stub"]["candidates"][0]["chunk_id"],
            "faculty-mikelin",
        )
        self.assertTrue(trace["should_abstain"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
