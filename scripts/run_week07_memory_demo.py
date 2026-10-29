"""Synthetic in-process A-route demonstration. No model or external email call."""
from __future__ import annotations
import json
import secrets
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tests"))
from test_week07_account_memory import AccountFixture, PASSWORD
from session_host import SessionHost


def main() -> int:
    fixture = AccountFixture()
    fixture.setUp()
    observations = {}
    try:
        status, _ = fixture.register()
        observations["registered"] = status == 200
        first = fixture.memory("我是合成學生，想了解智慧代理人相關專題。", "introduction")[1]
        second = fixture.memory("學生 合成學生 敬上", "signature")[1]
        observations["multiple_records_saved"] = len(fixture.list()) == 2
        fixture.call("/api/session/reset")
        observations["new_conversation_reads_two"] = len(fixture.list()) == 2
        fixture.call("/api/auth/logout")
        observations["logged_out_read_denied"] = fixture.call("/api/memory/list")[0] == 401
        fixture.host = SessionHost(fixture.host._factory, (fixture.faculty, fixture.office))
        fixture.a, fixture.sa = fixture.host.bootstrap(None)
        fixture.b, fixture.sb = fixture.host.bootstrap(None)
        fixture.call("/api/auth/login", {"username": "synthetic_a", "password": PASSWORD})
        observations["restart_then_login_reads_two"] = len(fixture.list()) == 2
        refs = [fixture.ref(first), fixture.ref(second)]
        status, draft = fixture.selected_draft(refs)
        observations["selected_text_applied_to_draft"] = status == 200 and "智慧代理人" in draft["email_draft"]["body"]
        observations["recipient_still_official"] = draft["email_draft"]["to"] == "mikelin@mail.nutn.edu.tw"
        fixture.register("synthetic_b", browser="b")
        observations["other_account_list_empty"] = fixture.list(owner=fixture.b, session=fixture.sb) == []
        status, _ = fixture.call("/api/email-draft", {"teacher_name": "林朝興", "purpose": "other", "student_name": "合成學生", "request_details": "合成專題詢問", "memory_selections": refs}, owner=fixture.b, session=fixture.sb)
        observations["other_account_cannot_apply_known_ids"] = status == 404
        fixture.call("/api/memory/write", {"action": "delete", "confirmed": True, "operation_id": secrets.token_hex(16), "memory_id": first["memory_id"], "expected_version": first["version"]})
        observations["deleted_record_excluded"] = len(fixture.list()) == 1
        observations["draft_using_deleted_record_rejected"] = fixture.call("/api/email-send", {"draft_id": draft["draft_id"], "confirmed": True})[0] == 404
        observations["outbox_rows"] = fixture.count()
        passed = all(value for key, value in observations.items() if key != "outbox_rows") and observations["outbox_rows"] == 0
        record = {
            "mode": "OFFLINE_IN_PROCESS_DEMO", "route": "A_saved_email_content",
            "executed_at": datetime.now(timezone(timedelta(hours=8))).isoformat(),
            "baseline_sha": "6bbd34f369a40b5a2a46534e881197bddfcfea01", "candidate_version": "WORKING_TREE",
            "identity": "synthetic local accounts; no credentials or cookies exported",
            "observations": observations, "status": "PASS" if passed else "FAIL",
            "live_status": "LIVE_NOT_RUN", "real_email_sent": False,
            "boundary": "This demo invokes SessionHost in process. Real localhost HTTP is covered separately by the W07 account test suite. No browser recording or actual Gemini request is represented here.",
        }
        (ROOT / "evidence/week07_memory_demo.json").write_text(json.dumps(record, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(json.dumps(record, ensure_ascii=False, indent=2))
        return 0 if passed else 1
    finally:
        fixture.doCleanups()


if __name__ == "__main__":
    raise SystemExit(main())
