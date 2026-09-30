"""Frozen-evidence generator comparison for the Week 03 project studio."""

from __future__ import annotations

import hashlib
import json
from typing import Any, Mapping


def _canonical_hash(value: Any) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _find_trace(
    retrieval_report: Mapping[str, Any], query_id: str
) -> Mapping[str, Any]:
    return next(
        trace
        for trace in retrieval_report["traces"]
        if trace["query_id"] == query_id
    )


def _find_query(
    queries_document: Mapping[str, Any], query_id: str
) -> Mapping[str, Any]:
    return next(
        query
        for query in queries_document["queries"]
        if query["query_id"] == query_id
    )


def _offline_answer(evidence: Mapping[str, Any]) -> str:
    research_areas = "、".join(evidence["research_areas"])
    return (
        f"教師：{evidence['teacher_name']}\n"
        f"職稱：{evidence['title']}\n"
        f"研究領域：{research_areas}\n"
        f"公開 Email：{evidence['public_email']}"
    )


def _fixture_answer(evidence: Mapping[str, Any]) -> str:
    research_areas = "、".join(evidence["research_areas"])
    return (
        f"{evidence['teacher_name']}老師目前為{evidence['title']}，"
        f"研究領域包括{research_areas}。"
        f"官方公開 Email 是 {evidence['public_email']}。"
        "你可以先確認收件人與郵件內容，再自行決定是否寄出。"
    )


def _required_aspect_coverage(
    required_aspects: list[str], evidence: Mapping[str, Any]
) -> dict[str, Any]:
    aspect_values = {
        "teacher_identity": evidence.get("teacher_name"),
        "public_email": evidence.get("public_email"),
        "research_areas": evidence.get("research_areas"),
    }
    covered = [aspect for aspect in required_aspects if aspect_values.get(aspect)]
    missing = [aspect for aspect in required_aspects if aspect not in covered]
    return {
        "required": required_aspects,
        "covered": covered,
        "missing": missing,
        "covered_count": len(covered),
        "required_count": len(required_aspects),
        "passed": not missing,
    }


def build_generator_comparison(
    retrieval_report: Mapping[str, Any],
    queries_document: Mapping[str, Any],
    *,
    query_id: str = "q-normal-email",
    failure_query_id: str = "q-no-answer-office-hours",
) -> dict[str, Any]:
    trace = _find_trace(retrieval_report, query_id)
    query_spec = _find_query(queries_document, query_id)
    if not trace["can_answer"] or len(trace["selected_evidence"]) != 1:
        raise ValueError("Comparison query must have exactly one selected evidence item")

    evidence = trace["selected_evidence"][0]
    selected_evidence_ids = list(trace["selected_evidence_ids"])
    citations = list(trace["citations"])
    frozen_evidence = {
        "selected_evidence_ids": selected_evidence_ids,
        "evidence": [evidence],
        "citations": citations,
    }
    frozen_evidence_hash = _canonical_hash(frozen_evidence)
    coverage = _required_aspect_coverage(
        list(query_spec["required_aspects"]), evidence
    )
    if not coverage["passed"]:
        raise ValueError("Required-aspect coverage must pass before generation")

    generators = [
        {
            "path": "offline",
            "provider": "offline",
            "model": None,
            "llm_actually_called": False,
            "selected_evidence_ids": selected_evidence_ids,
            "frozen_evidence_hash": frozen_evidence_hash,
            "answer": _offline_answer(evidence),
            "citations": citations,
            "unsupported_claims": [],
            "send_status": "not_sent",
        },
        {
            "path": "gemini_fixture",
            "provider": "gemini_fixture",
            "model": "fixture-v1",
            "llm_actually_called": False,
            "selected_evidence_ids": selected_evidence_ids,
            "frozen_evidence_hash": frozen_evidence_hash,
            "answer": _fixture_answer(evidence),
            "citations": citations,
            "unsupported_claims": [],
            "send_status": "not_sent",
        },
    ]

    same_selected_evidence = len(
        {tuple(generator["selected_evidence_ids"]) for generator in generators}
    ) == 1
    same_frozen_evidence = len(
        {generator["frozen_evidence_hash"] for generator in generators}
    ) == 1
    same_citations = len(
        {
            json.dumps(generator["citations"], ensure_ascii=False, sort_keys=True)
            for generator in generators
        }
    ) == 1
    unsupported_claims = [
        claim
        for generator in generators
        for claim in generator["unsupported_claims"]
    ]

    failure_trace = _find_trace(retrieval_report, failure_query_id)
    failure_observation = {
        "query_id": failure_trace["query_id"],
        "query": failure_trace["query"],
        "retrieved_candidate_ids": [
            candidate["chunk_id"] for candidate in failure_trace["candidates"]
        ],
        "selected_evidence_ids": failure_trace["selected_evidence_ids"],
        "can_answer": failure_trace["can_answer"],
        "failure_code": failure_trace["failure_code"],
        "generator_called": False,
        "reason": (
            "教師姓名可被檢索，但官方教師資料不包含今日研究室時間；"
            "Evidence Gate 阻擋所有 Generator。"
        ),
    }

    checks = {
        "same_selected_evidence": same_selected_evidence,
        "same_frozen_evidence": same_frozen_evidence,
        "same_citations": same_citations,
        "fact_coverage": coverage,
        "unsupported_claims": unsupported_claims,
        "all_send_status_not_sent": all(
            generator["send_status"] == "not_sent" for generator in generators
        ),
        "live_llm_called": False,
    }
    checks_passed = (
        same_selected_evidence
        and same_frozen_evidence
        and same_citations
        and coverage["passed"]
        and not unsupported_claims
        and checks["all_send_status_not_sent"]
        and not failure_observation["generator_called"]
    )

    return {
        "schema_version": "1.0",
        "comparison_id": "week03-faculty-email-generator-comparison",
        "query_id": trace["query_id"],
        "query": trace["query"],
        "frozen_evidence": {
            **frozen_evidence,
            "sha256": frozen_evidence_hash,
        },
        "evidence_gate": {
            "passed": True,
            "coverage": coverage,
        },
        "generators": generators,
        "checks": checks,
        "checks_passed": checks_passed,
        "failure_observation": failure_observation,
        "live_path": {
            "executed": False,
            "reason": "Gemini Live is optional; this comparison uses the reproducible fixture path.",
        },
    }
