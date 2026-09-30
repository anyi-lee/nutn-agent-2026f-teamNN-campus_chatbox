"""Run BM25 versus dense_stub comparison and save a JSON artifact."""

from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT / "src"))

from retriever_comparison import compare_retrievers  # noqa: E402


CHUNKS_PATH = REPOSITORY_ROOT / "data" / "faculty_chunks.json"
QUERIES_PATH = REPOSITORY_ROOT / "data" / "fixed_queries.json"
OUTPUT_PATH = REPOSITORY_ROOT / "artifacts" / "week03-retriever-comparison.json"


def main() -> int:
    chunks_document = json.loads(CHUNKS_PATH.read_text(encoding="utf-8"))
    queries_document = json.loads(QUERIES_PATH.read_text(encoding="utf-8"))
    report = compare_retrievers(chunks_document, queries_document)
    report["generated_at"] = datetime.now(ZoneInfo("Asia/Taipei")).isoformat()
    report["inputs"] = {
        "chunks": "data/faculty_chunks.json",
        "queries": "data/fixed_queries.json",
    }
    report["reproducible_command"] = "python3 -m scripts.compare_retrievers"

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    print(f"output={OUTPUT_PATH.relative_to(REPOSITORY_ROOT)}")
    for retriever_name, metrics in report["metrics"].items():
        print(
            f"{retriever_name}: recall_at_3={metrics['recall_at_3']:.3f}; "
            f"mrr={metrics['mrr']:.3f}; "
            f"mean_latency_ms={metrics['mean_latency_ms']:.6f}"
        )
    for trace in report["query_traces"]:
        bm25_ids = ",".join(
            candidate["chunk_id"] for candidate in trace["bm25"]["candidates"]
        )
        dense_ids = ",".join(
            candidate["chunk_id"]
            for candidate in trace["dense_stub"]["candidates"]
        )
        print(
            f"{trace['query_id']}: bm25={bm25_ids}; dense_stub={dense_ids}; "
            f"same_top_1={trace['same_top_1']}"
        )
    zero = report["zero_vector_observation"]
    print(
        f"zero_vector={zero['query_is_zero_vector']}; "
        f"all_cosine_scores_zero={zero['all_cosine_scores_zero']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
