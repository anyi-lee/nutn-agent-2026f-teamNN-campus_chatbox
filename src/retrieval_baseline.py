"""Transparent BM25 retrieval baseline for the Week 03 faculty corpus."""

from __future__ import annotations

import math
import re
from collections import Counter
from typing import Any, Iterable, Mapping, Sequence


BM25_K1 = 1.5
BM25_B = 0.75
TOKENIZER_VERSION = "cjk-unigram-bigram-latin-v1"

_LATIN_OR_NUMBER = re.compile(r"[a-z0-9@._+-]+")
_CJK = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff]+")


def tokenize(text: str) -> list[str]:
    """Return lowercase Latin tokens plus CJK unigrams and bigrams."""

    normalized = text.lower()
    tokens = _LATIN_OR_NUMBER.findall(normalized)
    for sequence in _CJK.findall(normalized):
        tokens.extend(sequence)
        tokens.extend(sequence[index : index + 2] for index in range(len(sequence) - 1))
    return tokens


def _document_text(chunk: Mapping[str, Any]) -> str:
    return " ".join(
        [
            str(chunk.get("teacher_name", "")),
            str(chunk.get("title", "")),
            " ".join(str(value) for value in chunk.get("research_areas", [])),
            str(chunk.get("public_email", "")),
            str(chunk.get("content", "")),
        ]
    )


class BM25Retriever:
    """Small dependency-free BM25 implementation with query-level traces."""

    def __init__(
        self,
        chunks: Sequence[Mapping[str, Any]],
        *,
        k1: float = BM25_K1,
        b: float = BM25_B,
    ) -> None:
        if not chunks:
            raise ValueError("At least one chunk is required")

        self.chunks = list(chunks)
        self.k1 = k1
        self.b = b
        self.document_tokens = [tokenize(_document_text(chunk)) for chunk in chunks]
        self.term_frequencies = [Counter(tokens) for tokens in self.document_tokens]
        self.document_lengths = [len(tokens) for tokens in self.document_tokens]
        self.average_document_length = sum(self.document_lengths) / len(chunks)

        self.document_frequencies: Counter[str] = Counter()
        for tokens in self.document_tokens:
            self.document_frequencies.update(set(tokens))

    def _idf(self, term: str) -> float:
        document_count = len(self.chunks)
        document_frequency = self.document_frequencies.get(term, 0)
        return math.log(
            1 + (document_count - document_frequency + 0.5) / (document_frequency + 0.5)
        )

    def _score(self, query_tokens: Iterable[str], document_index: int) -> float:
        frequencies = self.term_frequencies[document_index]
        document_length = self.document_lengths[document_index]
        score = 0.0

        for term in set(query_tokens):
            term_frequency = frequencies.get(term, 0)
            if not term_frequency:
                continue
            numerator = term_frequency * (self.k1 + 1)
            denominator = term_frequency + self.k1 * (
                1 - self.b + self.b * document_length / self.average_document_length
            )
            score += self._idf(term) * numerator / denominator

        return score

    def search(self, query: str, *, top_k: int) -> list[dict[str, Any]]:
        query_tokens = tokenize(query)
        scored = []
        for index, chunk in enumerate(self.chunks):
            raw_score = self._score(query_tokens, index)
            matched_terms = sorted(set(query_tokens) & set(self.document_tokens[index]))
            scored.append((raw_score, str(chunk["chunk_id"]), chunk, matched_terms))

        scored.sort(key=lambda item: (-item[0], item[1]))
        maximum_score = scored[0][0] if scored else 0.0
        candidates = []
        for rank, (raw_score, chunk_id, chunk, matched_terms) in enumerate(
            scored[:top_k], start=1
        ):
            normalized_score = raw_score / maximum_score if maximum_score else 0.0
            candidates.append(
                {
                    "rank": rank,
                    "chunk_id": chunk_id,
                    "raw_score": round(raw_score, 6),
                    "normalized_score": round(normalized_score, 6),
                    "matched_terms": matched_terms,
                    "chunk": chunk,
                }
            )
        return candidates


def _supports_aspect(chunk: Mapping[str, Any], aspect: str) -> bool:
    field_by_aspect = {
        "teacher_identity": "teacher_name",
        "public_email": "public_email",
        "research_areas": "research_areas",
    }
    field = field_by_aspect.get(aspect)
    if field is None:
        return False
    value = chunk.get(field)
    return bool(value)


def _evaluate_evidence_gate(
    query_spec: Mapping[str, Any],
    candidates: Sequence[Mapping[str, Any]],
) -> tuple[list[Mapping[str, Any]], list[dict[str, Any]], str | None]:
    gate_trace: list[dict[str, Any]] = []
    allowed_sources = set(query_spec["allowed_sources"])

    for candidate in candidates:
        chunk = candidate["chunk"]
        checks = {
            "category": query_spec["category"] == "faculty_contact"
            and chunk.get("category") == "faculty_contact",
            "source": chunk.get("source_id") in allowed_sources,
            "authority": chunk.get("authority") == "official",
            "validity": chunk.get("validity") == "active",
            "claim_support": all(
                _supports_aspect(chunk, aspect)
                for aspect in query_spec["required_aspects"]
            ),
        }
        passed = all(checks.values())
        gate_trace.append(
            {
                "chunk_id": candidate["chunk_id"],
                "checks": checks,
                "passed": passed,
            }
        )
        if passed:
            return [chunk], gate_trace, None

    return [], gate_trace, "INSUFFICIENT_EVIDENCE"


def evaluate_query(
    retriever: BM25Retriever,
    query_spec: Mapping[str, Any],
    *,
    top_k: int,
) -> dict[str, Any]:
    candidates = retriever.search(str(query_spec["query"]), top_k=top_k)
    gold_ids = set(query_spec["gold_chunk_ids"])
    candidate_ids = [str(candidate["chunk_id"]) for candidate in candidates]

    for candidate in candidates:
        candidate["is_gold"] = candidate["chunk_id"] in gold_ids

    selected_chunks, gate_trace, failure_code = _evaluate_evidence_gate(
        query_spec, candidates
    )
    selected_ids = [str(chunk["chunk_id"]) for chunk in selected_chunks]
    can_answer = bool(selected_chunks)
    citations = [
        {
            "source_id": chunk["source_id"],
            "chunk_id": chunk["chunk_id"],
            "url": chunk["source_url"],
        }
        for chunk in selected_chunks
    ]
    selected_evidence = [
        {
            "chunk_id": chunk["chunk_id"],
            "teacher_name": chunk["teacher_name"],
            "title": chunk["title"],
            "research_areas": chunk["research_areas"],
            "public_email": chunk["public_email"],
            "source_url": chunk["source_url"],
        }
        for chunk in selected_chunks
    ]

    expected_failure_code = query_spec["expected_failure_code"]
    expectation_passed = (
        selected_ids == query_spec["expected_selected_evidence_ids"]
        and failure_code == expected_failure_code
        and can_answer is not bool(query_spec["should_abstain"])
    )

    public_candidates = [
        {key: value for key, value in candidate.items() if key != "chunk"}
        for candidate in candidates
    ]
    return {
        "query_id": query_spec["query_id"],
        "query_type": query_spec["query_type"],
        "query": query_spec["query"],
        "category": query_spec["category"],
        "top_k": top_k,
        "gold_chunk_ids": query_spec["gold_chunk_ids"],
        "acceptable_chunk_ids": query_spec["acceptable_chunk_ids"],
        "candidates": public_candidates,
        "gold_in_top_k": bool(gold_ids & set(candidate_ids)) if gold_ids else None,
        "gate_trace": gate_trace,
        "selected_evidence_ids": selected_ids,
        "selected_evidence": selected_evidence,
        "citations": citations,
        "can_answer": can_answer,
        "should_abstain": query_spec["should_abstain"],
        "failure_code": failure_code,
        "expected_failure_code": expected_failure_code,
        "expectation_passed": expectation_passed,
    }


def run_initial_retrieval(
    chunks_document: Mapping[str, Any],
    queries_document: Mapping[str, Any],
) -> dict[str, Any]:
    chunks = chunks_document["chunks"]
    queries = queries_document["queries"]
    top_k = int(queries_document["top_k"])
    retriever = BM25Retriever(chunks)

    traces = [
        evaluate_query(retriever, query_spec, top_k=top_k)
        for query_spec in queries
    ]
    answerable = [trace for trace in traces if not trace["should_abstain"]]
    no_answer = [trace for trace in traces if trace["should_abstain"]]
    reciprocal_ranks = []
    for trace in answerable:
        gold_ids = set(trace["gold_chunk_ids"])
        rank = next(
            (
                candidate["rank"]
                for candidate in trace["candidates"]
                if candidate["chunk_id"] in gold_ids
            ),
            None,
        )
        reciprocal_ranks.append(1 / rank if rank else 0.0)

    return {
        "schema_version": "1.0",
        "retriever": {
            "type": "bm25",
            "tokenizer_version": TOKENIZER_VERSION,
            "k1": retriever.k1,
            "b": retriever.b,
            "top_k": top_k,
            "index_version": queries_document["index_version"],
            "chunk_count": len(chunks),
        },
        "summary": {
            "query_count": len(traces),
            "expectations_passed": sum(
                1 for trace in traces if trace["expectation_passed"]
            ),
            "recall_at_3_answerable": round(
                sum(1 for trace in answerable if trace["gold_in_top_k"])
                / len(answerable),
                6,
            ),
            "mrr_answerable": round(
                sum(reciprocal_ranks) / len(reciprocal_ranks), 6
            ),
            "abstention_accuracy": round(
                sum(1 for trace in no_answer if not trace["can_answer"])
                / len(no_answer),
                6,
            ),
        },
        "traces": traces,
    }
