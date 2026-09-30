"""Generate the Week 03 Offline versus Gemini Fixture comparison artifact."""

from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT / "src"))

from generator_comparison import build_generator_comparison  # noqa: E402


RETRIEVAL_PATH = REPOSITORY_ROOT / "artifacts" / "week03-initial-retrieval.json"
QUERIES_PATH = REPOSITORY_ROOT / "data" / "fixed_queries.json"
OUTPUT_PATH = REPOSITORY_ROOT / "artifacts" / "week03-generator-comparison.json"


def main() -> int:
    retrieval_report = json.loads(RETRIEVAL_PATH.read_text(encoding="utf-8"))
    queries_document = json.loads(QUERIES_PATH.read_text(encoding="utf-8"))
    comparison = build_generator_comparison(retrieval_report, queries_document)
    comparison["generated_at"] = datetime.now(
        ZoneInfo("Asia/Taipei")
    ).isoformat()
    comparison["inputs"] = {
        "retrieval_trace": "artifacts/week03-initial-retrieval.json",
        "queries": "data/fixed_queries.json",
    }
    comparison["reproducible_command"] = (
        "python3 -m scripts.run_generator_comparison"
    )

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(
        json.dumps(comparison, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    checks = comparison["checks"]
    failure = comparison["failure_observation"]
    print(f"output={OUTPUT_PATH.relative_to(REPOSITORY_ROOT)}")
    print(f"comparison_query={comparison['query_id']}")
    print(f"generator_paths={','.join(g['path'] for g in comparison['generators'])}")
    print(f"same_selected_evidence={checks['same_selected_evidence']}")
    print(f"same_frozen_evidence={checks['same_frozen_evidence']}")
    print(f"same_citations={checks['same_citations']}")
    print(
        "fact_coverage="
        f"{checks['fact_coverage']['covered_count']}/"
        f"{checks['fact_coverage']['required_count']}"
    )
    print(f"unsupported_claims={checks['unsupported_claims']}")
    print(f"live_llm_called={checks['live_llm_called']}")
    print(
        f"failure_observation={failure['query_id']}:"
        f"{failure['failure_code']};generator_called={failure['generator_called']}"
    )
    print(f"checks_passed={comparison['checks_passed']}")

    return 0 if comparison["checks_passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
