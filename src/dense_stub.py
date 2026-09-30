"""Transparent dense stub using manual concept vectors and cosine similarity.

This is a teaching scaffold, not a learned embedding model. Concept aliases
are deliberately visible and versioned so every score can be reproduced.
"""

from __future__ import annotations

import math
import re
from typing import Any, Mapping, Sequence


MODEL_VERSION = "faculty-concepts-v1"

CONCEPT_ALIASES: dict[str, tuple[str, ...]] = {
    "faculty_mikelin": ("林朝興", "mikelin"),
    "faculty_leecs": ("李健興", "leecs"),
    "faculty_cslee": ("李建樹", "cslee"),
    "faculty_chents": ("陳宗禧", "chents"),
    "faculty_rmchen": ("陳榮銘", "rmchen"),
    "faculty_cckao": ("高啟洲", "cckao"),
    "faculty_myju": ("朱明毅", "myju"),
    "faculty_ifangsu": ("蘇溢芳", "ifangsu"),
    "contact": (
        "email",
        "e-mail",
        "mail",
        "信箱",
        "郵件",
        "聯絡",
        "聯繫",
        "寄信",
    ),
    "research": ("研究", "專長", "領域"),
    "ai": ("ai", "人工智慧", "神經網路", "深度學習", "智慧型代理人"),
    "data": (
        "資料科學",
        "大數據",
        "巨量資料",
        "生醫資訊",
        "時空資料庫",
        "估測理論",
        "訊號處理",
    ),
    "network_iot": ("無線網路", "網路", "物聯網", "行動計算", "行動學習"),
    "embedded_robotics": (
        "嵌入式",
        "機器人",
        "軟式計算",
        "晶片",
        "積體電路",
    ),
    "vision_media": ("影像", "視覺", "多媒體", "媒體串流", "aoi"),
    "cloud": ("雲端", "cloud"),
    "live_status": ("今天", "現在", "幾點", "在研究室", "行程", "是否在"),
}

CONCEPTS = tuple(CONCEPT_ALIASES)


def _normalize(text: str) -> str:
    return "".join(text.lower().split())


def _alias_matches(alias: str, text: str) -> bool:
    lowered_alias = alias.lower()
    lowered_text = text.lower()
    if re.fullmatch(r"[a-z0-9-]+", lowered_alias):
        pattern = rf"(?<![a-z0-9]){re.escape(lowered_alias)}(?![a-z0-9])"
        return re.search(pattern, lowered_text) is not None
    return _normalize(lowered_alias) in _normalize(lowered_text)


def encode_concepts(text: str) -> list[int]:
    return [
        int(any(_alias_matches(alias, text) for alias in CONCEPT_ALIASES[concept]))
        for concept in CONCEPTS
    ]


def active_concepts(vector: Sequence[int]) -> list[str]:
    return [concept for concept, value in zip(CONCEPTS, vector) if value]


def cosine_similarity(left: Sequence[int], right: Sequence[int]) -> float:
    left_norm = math.sqrt(sum(value * value for value in left))
    right_norm = math.sqrt(sum(value * value for value in right))
    if not left_norm or not right_norm:
        return 0.0
    dot_product = sum(a * b for a, b in zip(left, right))
    return dot_product / (left_norm * right_norm)


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


class DenseStubRetriever:
    """Rank chunks by cosine over a visible binary concept space."""

    def __init__(self, chunks: Sequence[Mapping[str, Any]]) -> None:
        if not chunks:
            raise ValueError("At least one chunk is required")
        self.chunks = list(chunks)
        self.document_vectors = [encode_concepts(_document_text(chunk)) for chunk in chunks]

    def encode_query(self, query: str) -> dict[str, Any]:
        vector = encode_concepts(query)
        return {
            "vector": vector,
            "active_concepts": active_concepts(vector),
            "is_zero_vector": not any(vector),
        }

    def search(self, query: str, *, top_k: int) -> dict[str, Any]:
        query_encoding = self.encode_query(query)
        query_vector = query_encoding["vector"]
        scored = []
        for chunk, document_vector in zip(self.chunks, self.document_vectors):
            score = cosine_similarity(query_vector, document_vector)
            scored.append((score, str(chunk["chunk_id"]), chunk, document_vector))

        scored.sort(key=lambda item: (-item[0], item[1]))
        candidates = []
        for rank, (score, chunk_id, _chunk, document_vector) in enumerate(
            scored[:top_k], start=1
        ):
            candidates.append(
                {
                    "rank": rank,
                    "chunk_id": chunk_id,
                    "cosine_score": round(score, 6),
                    "document_vector": document_vector,
                    "document_active_concepts": active_concepts(document_vector),
                }
            )

        return {
            "query_vector": query_vector,
            "query_active_concepts": query_encoding["active_concepts"],
            "query_is_zero_vector": query_encoding["is_zero_vector"],
            "candidates": candidates,
        }
