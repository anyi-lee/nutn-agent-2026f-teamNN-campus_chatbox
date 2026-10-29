"""Compare original HTTP boundary at 6bbd34f with W07, entirely offline.

Uses identical isolated source copies, local template backend and synthetic
browser identities. Only baseline app.py is loaded from git; shared domain
modules are the current compatible versions, with no saved-memory input in
these historical session cases. This is not a full old-checkout replay.
"""
from __future__ import annotations
import http.cookiejar
import json
import subprocess
import sys
import threading
import types
from datetime import datetime, timedelta, timezone
from http.server import ThreadingHTTPServer
from pathlib import Path
from urllib import error, request

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tests"))
from test_week07_sessions import SessionFixture, CampusRequestHandler

BASELINE = "6bbd34f369a40b5a2a46534e881197bddfcfea01"


def main() -> int:
    original = subprocess.run(["git", "show", f"{BASELINE}:app.py"], cwd=ROOT, check=True, capture_output=True, text=True, encoding="utf-8").stdout
    module = types.ModuleType("week07_original_http")
    module.__file__ = str(ROOT / "app.py")
    exec(compile(original, str(ROOT / "app.py"), "exec"), module.__dict__)
    rows = []
    fixtures, servers = [], []
    try:
        for mode in ("baseline", "candidate"):
            fixture = SessionFixture()
            fixture.setUp()
            fixtures.append(fixture)
            if mode == "baseline":
                module.SERVICE = fixture.host.service
                parent = module.CampusRequestHandler
            else:
                parent = CampusRequestHandler
            class Handler(parent):
                session_host = fixture.host
                def log_message(self, *args):
                    pass
            server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
            worker = threading.Thread(target=server.serve_forever, daemon=True)
            worker.start()
            servers.append((server, worker))
            url = f"http://127.0.0.1:{server.server_address[1]}"
            a = request.build_opener(request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
            b = request.build_opener(request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
            sessions = {}
            if mode == "candidate":
                for name, browser in (("a", a), ("b", b)):
                    with browser.open(url + "/api/session", timeout=5) as response:
                        sessions[name] = json.load(response)["session"]
            def post(name, path, fields):
                headers = {"Content-Type": "application/json"}
                payload = dict(fields)
                if mode == "candidate":
                    session = sessions[name]
                    payload.update(session_id=session["session_id"], generation=session["generation"])
                    headers["X-CSRF-Token"] = session["csrf_token"]
                req = request.Request(url + path, data=json.dumps(payload).encode(), headers=headers)
                try:
                    response = (a if name == "a" else b).open(req, timeout=5)
                except error.HTTPError as exc:
                    response = exc
                with response:
                    status, result = response.status, json.load(response)
                if result.get("session"):
                    sessions[name] = result["session"]
                return status, result
            status, normal = post("a", "/api/chat", {"message": "林朝興老師的研究領域"})
            follow_fields = {"message": "他的 Email 是什麼？"}
            if mode == "baseline":
                follow_fields["context_teacher"] = normal["detected_teacher"]
            _, follow = post("a", "/api/chat", follow_fields)
            _, draft = post("a", "/api/email-draft", {"teacher_name": "林朝興", "purpose": "other", "student_name": "合成學生", "request_details": "請問專題面談方式，這是合成驗收資料。"})
            cross_status, cross = post("b", "/api/email-send", {"draft_id": draft["draft_id"], "confirmed": True})
            reset_status, _ = post("a", "/api/session/reset", {})
            old_status, old = post("a", "/api/email-send", {"draft_id": draft["draft_id"], "confirmed": True})
            rows.append({
                "mode": mode, "normal_http": status, "normal_teacher": normal.get("detected_teacher"),
                "normal_citation_present": bool(normal.get("citations")),
                "followup_used_context": follow.get("used_context"),
                "cross_browser_write_http": cross_status, "cross_browser_write_status": cross.get("status"),
                "reset_http": reset_status, "old_draft_after_reset_http": old_status,
                "old_draft_after_reset_status": old.get("status"), "outbox_rows": fixture.count(),
            })
        baseline, candidate = rows
        passed = (all(row["normal_http"] == 200 and row["normal_citation_present"] and row["followup_used_context"] for row in rows)
                  and baseline["cross_browser_write_http"] == 200
                  and candidate["cross_browser_write_http"] == 404
                  and baseline["reset_http"] == 404 and candidate["reset_http"] == 200
                  and candidate["old_draft_after_reset_http"] == 404
                  and baseline["outbox_rows"] == 1 and candidate["outbox_rows"] == 0)
        record = {"executed_at": datetime.now(timezone(timedelta(hours=8))).isoformat(),
                  "baseline_sha": BASELINE, "candidate_version": "WORKING_TREE", "mode": "OFFLINE_HTTP_COMPARISON",
                  "live_status": "LIVE_NOT_RUN", "real_email_sent": False,
                  "conditions": "Isolated identical source copies; baseline chat/manual template; original app.py handler vs W07 handler; current compatible domain modules; no saved-memory parameters; synthetic browser cookies. This comparison covers historical session boundaries, not the new A-route persistence.",
                  "results": rows, "comparison_status": "PASS" if passed else "FAIL"}
        (ROOT / "evidence/week07_before_after.json").write_text(json.dumps(record, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(json.dumps(record, ensure_ascii=False, indent=2))
        return 0 if passed else 1
    finally:
        for server, worker in servers:
            server.shutdown()
            worker.join(3)
            server.server_close()
        for fixture in fixtures:
            fixture.doCleanups()


if __name__ == "__main__":
    raise SystemExit(main())
