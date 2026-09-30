"""Compare BM25 and the transparent dense stub on fixed queries."""

from __future__ import annotations

from time import perf_counter_ns
from typing import Any, Mapping, Sequence

from dense_stub import CONCEPTS, MODEL_VERSION, DenseStubRetriever
from retrieval_baseline import BM25Retriever, TOKENIZER_VERSION


def _elapsed_ms(start_ns: int) -> float:
    return round((perf_counter_ns() - start_ns) / 1_000_000, 6)


def _ranking_metrics(
    query_traces: Sequence[Mapping[str, Any]], retriever_key: str
) -> dict[str, float]:
    answerable = [trace for trace in query_traces if trace["gold_chunk_ids"]]
    hits = 0
    reciprocal_ranks = []
    for trace in answerable:
        gold_ids = set(trace["gold_chunk_ids"])
        candidates = trace[retriever_key]["candidates"]
        rank = next(
            (
                candidate["rank"]
                for candidate in candidates
                if candidate["chunk_id"] in gold_ids
            ),
            None,
        )
        if rank is not None:
            hits += 1
            reciprocal_ranks.append(1 / rank)
        else:
            reciprocal_ranks.append(0.0)

    return {
        "recall_at_3": round(hits / len(answerable), 6),
        "mrr": round(sum(reciprocal_ranks) / len(reciprocal_ranks), 6),
        "mean_latency_ms": round(
            sum(trace[retriever_key]["latency_ms"] for trace in query_traces)
            / len(query_traces),
            6,
        ),
    }


def compare_retrievers(
    chunks_document: Mapping[str, Any],
    queries_document: Mapping[str, Any],
) -> dict[str, Any]:
    chunks = chunks_document["chunks"]
    queries = queries_document["queries"]
    top_k = int(queries_document["top_k"])
    bm25 = BM25Retriever(chunks)
    dense_stub = DenseStubRetriever(chunks)

    query_traces = []
    for query_spec in queries:
        query = str(query_spec["query"])

        start = perf_counter_ns()
        bm25_candidates = bm25.search(query, top_k=top_k)
        bm25_latency = _elapsed_ms(start)
        public_bm25_candidates = [
            {key: value for key, value in candidate.items() if key != "chunk"}
            for candidate in bm25_candidates
        ]

        start = perf_counter_ns()
        dense_result = dense_stub.search(query, top_k=top_k)
        dense_latency = _elapsed_ms(start)

        query_traces.append(
            {
                "query_id": query_spec["query_id"],
                "query_type": query_spec["query_type"],
                "query": query,
                "gold_chunk_ids": query_spec["gold_chunk_ids"],
                "should_abstain": query_spec["should_abstain"],
                "bm25": {
                    "latency_ms": bm25_latency,
                    "candidates": public_bm25_candidates,
                },
                "dense_stub": {
                    "latency_ms": dense_latency,
                    **dense_result,
                },
                "same_top_1": (
                    public_bm25_candidates[0]["chunk_id"]
                    == dense_result["candidates"][0]["chunk_id"]
                ),
            }
        )

    zero_vector_query = "請協助處理這件事情"
    zero_vector_result = dense_stub.search(zero_vector_query, top_k=top_k)
    zero_vector_observation = {
        "query": zero_vector_query,
        **zero_vector_result,
        "all_cosine_scores_zero": all(
            candidate["cosine_score"] == 0.0
            for candidate in zero_vector_result["candidates"]
        ),
        "reason": "Query 未命中任何人工 alias，因此向量為全 0，cosine 回傳 0。",
    }

    return {
        "schema_version": "1.0",
        "comparison_id": "week03-bm25-vs-dense-stub",
        "corpus": {
            "index_version": queries_document["index_version"],
            "chunk_count": len(chunks),
            "top_k": top_k,
        },
        "retrievers": {
            "bm25": {
                "tokenizer_version": TOKENIZER_VERSION,
                "k1": bm25.k1,
                "b": bm25.b,
            },
            "dense_stub": {
                "model_version": MODEL_VERSION,
                "concept_count": len(CONCEPTS),
                "concepts": list(CONCEPTS),
                "learned_embedding": False,
            },
        },
        "metrics": {
            "bm25": _ranking_metrics(query_traces, "bm25"),
            "dense_stub": _ranking_metrics(query_traces, "dense_stub"),
        },
        "query_traces": query_traces,
        "zero_vector_observation": zero_vector_observation,
        "limitations": [
            "dense_stub 使用人工 alias，不代表真實語言理解。",
            "新增或修改 alias 等同修改 model version。",
            "小型合成資料的 Recall、MRR 與 latency 不可外推 production。",
        ],
    }
