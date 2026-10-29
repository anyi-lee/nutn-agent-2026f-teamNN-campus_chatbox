"""Run W07 acceptance and record safe, versioned offline evidence.

Does not call Gemini, export cookies, or copy private model inputs.
"""
from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import sys
import unittest
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tests"))
sys.path.insert(0, str(ROOT))


def main() -> int:
    evidence = ROOT / "evidence"
    evidence.mkdir(exist_ok=True)
    now = datetime.now(timezone(timedelta(hours=8)))
    log_path = evidence / "week07_offline_sessions.log"
    suite = unittest.defaultTestLoader.discover(str(ROOT / "tests"), pattern="test_week07_*.py")
    with log_path.open("w", encoding="utf-8") as stream:
        result = unittest.TextTestRunner(stream=stream, verbosity=2).run(suite)
    node = shutil.which("node")
    ui_result = {"status": "NOT_RUN_NODE_UNAVAILABLE", "tests": 0}
    if node:
        ui = subprocess.run([node, "tests/test_week07_ui.cjs"], cwd=ROOT, capture_output=True, text=True, encoding="utf-8")
        ui_log = evidence / "week07_ui_vm.log"
        ui_log.write_text(ui.stdout + ui.stderr, encoding="utf-8")
        if ui.returncode == 0:
            ui_result = json.loads(ui.stdout)
        else:
            ui_result = {"status": "FAIL", "tests": 22}
    passed = result.wasSuccessful() and not result.skipped and ui_result["status"] == "PASS"
    revision = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True, check=True).stdout.strip()
    files = ("app.py", "src/session_host.py", "src/account_memory.py", "src/campus_service.py", "src/gemini_email.py", "ui/app.js", "ui/index.html", "ui/styles.css", "tests/test_week07_sessions.py", "tests/test_week07_account_memory.py", "tests/test_week07_templates.py", "tests/test_week07_revisions.py", "tests/test_week07_ui.cjs", "scripts/run_week07_validation.py", "scripts/run_week07_comparison.py", "scripts/run_week07_memory_demo.py")
    record = {
        "week": "07", "route": "A_saved_email_content", "run_id": f"week07-{uuid.uuid4().hex}",
        "executed_at": now.isoformat(), "timezone": "Asia/Taipei",
        "baseline_sha": "6bbd34f369a40b5a2a46534e881197bddfcfea01",
        "checkout_head": revision, "candidate_version": "WORKING_TREE",
        "candidate_files_sha256": {name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest() for name in files},
        "command": "python -W error::ResourceWarning scripts/run_week07_validation.py",
        "python": sys.version.split()[0], "identity_mode": "local username/password accounts; synthetic credentials; not university SSO",
        "data_mode": "isolated official snapshot copies; synthetic source-v2 and failure injection",
        "chat_backend": "baseline", "email_backend": "manual local template",
        "tests_run": result.testsRun, "failures": len(result.failures), "errors": len(result.errors), "skipped": len(result.skipped),
        "ui_vm": ui_result,
        "offline_status": "WEEK07_OFFLINE_PASS" if passed else "WEEK07_OFFLINE_INCOMPLETE",
        "live_status": "LIVE_NOT_RUN", "real_email_sent": False,
        "live_gap": "This validation run makes no external model calls. Real Gemini evidence for the current candidate is not recorded; ADC integration remains a separate midterm gap.",
        "browser_visual_status": "NOT_VERIFIED_BROWSER_POLICY_BLOCKED",
        "evidence_paths": [log_path.relative_to(ROOT).as_posix()] + (["evidence/week07_ui_vm.log"] if node else []),
        "limitations": ["Local accounts are not university SSO; no password recovery, MFA or public deployment.", "Account credentials (salted hash) and saved content persist in SQLite. Browser sessions, draft and receipt-access bindings remain in memory; restart requires login again.", "Only explicitly selected memories reach email drafting; no automatic memory write from chats.", "No new W07 live Gemini run; offline success is not LIVE_PASS."],
    }
    for name in ("src/personal_memory.py", "tests/test_week07_personal_memory.py", "tests/test_week07_semantic_memory.py"):
        record["candidate_files_sha256"][name] = hashlib.sha256((ROOT / name).read_bytes()).hexdigest()
    record["limitations"][2] = "Email text requires explicit selection. Personal facts from explicit user assertions are saved only after logged-in checkbox confirmation; same-key replacement requires the displayed version. Chat reads relevant confirmed personal facts, separately labelled from official evidence."
    output = evidence / "week07_offline_sessions.json"
    output.write_text(json.dumps(record, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(record, ensure_ascii=False, indent=2))
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
