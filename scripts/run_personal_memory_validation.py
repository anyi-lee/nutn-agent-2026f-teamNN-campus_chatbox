"""Offline regression without HTTP servers or real Gemini requests."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import unittest
import uuid
from datetime import datetime, timezone, timedelta

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tests"))


def flatten(suite):
    for item in suite:
        if isinstance(item, unittest.TestSuite):
            yield from flatten(item)
        else:
            yield item


def main():
    tests = list(flatten(unittest.defaultTestLoader.discover(str(ROOT / "tests"))))
    excluded = [test for test in tests if test.__class__.__name__ in ("HTTPTests", "AccountHTTPTests")]
    selected = [test for test in tests if test not in excluded]
    with (ROOT / "evidence/week07_personal_memory_offline.log").open("w", encoding="utf-8") as stream:
        result = unittest.TextTestRunner(stream=stream, verbosity=2).run(unittest.TestSuite(selected))
    ui = subprocess.run(["node", "tests/test_week07_ui.cjs"], cwd=ROOT, capture_output=True, text=True, encoding="utf-8")
    (ROOT / "evidence/week07_personal_memory_ui.log").write_text(ui.stdout + ui.stderr, encoding="utf-8")
    files = ("app.py", "src/personal_memory.py", "src/account_memory.py", "src/session_host.py", "src/campus_service.py", "src/gemini_email.py", "ui/app.js", "ui/index.html", "ui/styles.css",
             "tests/test_week07_personal_memory.py", "tests/test_week07_ui.cjs", "scripts/run_week07_validation.py",
             "scripts/run_personal_memory_validation.py", "tests/test_week07_semantic_memory.py", "tests/test_week07_revisions.py",
             "tests/test_week07_account_memory.py", "tests/test_week07_sessions.py", "tests/test_week07_templates.py")
    record = dict(executed_at=datetime.now(timezone(timedelta(hours=8))).isoformat(), candidate_version="WORKING_TREE",
        mode="OFFLINE_IN_PROCESS_AND_JS_VM", command="python scripts/run_personal_memory_validation.py",
        tests_run=result.testsRun, failures=len(result.failures), errors=len(result.errors),
        skipped=[{"test": test.id(), "reason": reason} for test, reason in result.skipped],
        not_run_http=[test.id() for test in excluded], ui_vm=json.loads(ui.stdout) if ui.returncode == 0 else {"status": "FAIL"},
        live_status="LIVE_NOT_RUN", browser_visual_verified=False,
        candidate_files_sha256={name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest() for name in files})
    record.update(schema_version="2.0", run_id=f"week07-review-{uuid.uuid4().hex}",
        timezone="Asia/Taipei", baseline_sha="6bbd34f369a40b5a2a46534e881197bddfcfea01",
        checkout_head=subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True, check=True).stdout.strip(),
        python=sys.version.split()[0], tests_passed=result.testsRun-len(result.failures)-len(result.errors)-len(result.skipped),
        offline_status="OFFLINE_PASS_WITH_SKIPS" if result.wasSuccessful() and ui.returncode == 0 else "OFFLINE_FAIL",
        data_files_sha256={name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest() for name in ("data/faculty_chunks.json", "data/office_chunks.json")},
        data_mode="isolated official snapshot copies, synthetic accounts and memory, explicit model doubles / fault injections",
        real_email_sent=False, tokens="NOT_MEASURED", live_latency="NOT_MEASURED")
    (ROOT / "evidence/week07_personal_memory.json").write_text(json.dumps(record, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({key: value for key, value in record.items() if key != "candidate_files_sha256"}, ensure_ascii=True, indent=2))
    return 0 if result.wasSuccessful() and ui.returncode == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
