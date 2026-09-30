"""Run the Week 03 initial retrieval and save a reproducible trace."""

from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT / "src"))

from retrieval_baseline import run_initial_retrieval  # noqa: E402


CHUNKS_PATH = REPOSITORY_ROOT / "data" / "faculty_chunks.json"
QUERIES_PATH = REPOSITORY_ROOT / "data" / "fixed_queries.json"
OUTPUT_PATH = REPOSITORY_ROOT / "artifacts" / "week03-initial-retrieval.json"


def main() -> int:
    chunks_document = json.loads(CHUNKS_PATH.read_text(encoding="utf-8"))
    queries_document = json.loads(QUERIES_PATH.read_text(encoding="utf-8"))
    report = run_initial_retrieval(chunks_document, queries_document)
    report["generated_at"] = datetime.now(ZoneInfo("Asia/Taipei")).isoformat()
    report["inputs"] = {
        "chunks": "data/faculty_chunks.json",
        "queries": "data/fixed_queries.json",
    }
    report["reproducible_command"] = "python3 -m scripts.run_initial_retrieval"

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    summary = report["summary"]
    print(f"output={OUTPUT_PATH.relative_to(REPOSITORY_ROOT)}")
    print(f"query_count={summary['query_count']}")
    print(f"expectations_passed={summary['expectations_passed']}")
    print(f"recall_at_3_answerable={summary['recall_at_3_answerable']:.3f}")
    print(f"mrr_answerable={summary['mrr_answerable']:.3f}")
    print(f"abstention_accuracy={summary['abstention_accuracy']:.3f}")
    for trace in report["traces"]:
        candidate_ids = ",".join(
            candidate["chunk_id"] for candidate in trace["candidates"]
        )
        print(
            f"{trace['query_id']}: top_k={candidate_ids}; "
            f"selected={trace['selected_evidence_ids']}; "
            f"failure={trace['failure_code']}; "
            f"passed={trace['expectation_passed']}"
        )

    return 0 if summary["expectations_passed"] == summary["query_count"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
