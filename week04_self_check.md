# Week 04 Submission Self-check

更新日期：2026-10-08

## 提交資訊

- Repository：待確認 remote；目前本機 `origin` 為 `https://github.com/anyi-lee/nutn-agent-2026f-teamNN-campus_chatbox.git`，與先前提供的 `s11259029` URL 不同。
- 測試基準 commit：提交前基準為 `6557bf2f7b55d2c03573621e865925e450b28ea7`。
- Week 04 commit SHA：commit 後由 Git 與課程繳交欄位提供；commit 無法在自身內容中記錄自己的 SHA。
- Gemini LIVE_PASS run ID：`mail-3076e583fcce4dce884b5e82b5500e1b`
- MCP local run ID：`week04-20261008T143601Z-23c581`

## 自評

| 檢查項目 | 狀態 | 證據或說明 |
| --- | --- | --- |
| README、可重現執行方式 | PASS | `README.md` |
| 無 Key 的環境變數範例 | PASS | `.env.example`；Key 欄位留空 |
| API Key、`.env`、Sandbox runtime 排除提交 | PASS | `.gitignore` 與上傳前 secrets scan |
| Read Tool | PASS | `get_teacher_contact` |
| Write Tool | PASS | `send_email`，僅寫入本機 Sandbox outbox |
| MCP `tools/list` / `tools/call` | MCP_LOCAL_PASS | `mcp_server.py`、`scripts/run_week04_tool_demo.py` |
| Write Tool 人工確認 | PASS | 未勾選時按鈕停用；工具也拒絕 `confirmed != true` |
| 收件人與正文不可由瀏覽器竄改 | PASS | Host 依 `draft_id` 取回伺服器端草稿 |
| 冪等性與狀態查詢 | PASS | SQLite `request_id` primary key；`get_email_status` |
| Timeout / retry / stop condition | PASS | timeout 後先查狀態，同一 request ID 最多重試一次；詳見 `week04_tool_contract.md` |
| Gemini 真實 function calling | LIVE_PASS | `evidence/week04_gemini_live_pass_2026-10-08.json` |
| Gemini 成功畫面 | PASS | `evidence/week04_gemini_function_call_live_pass_ui.png` |
| Sandbox Write Tool 成功畫面 | PASS | `evidence/week04_sandbox_write_simulated_sent_ui.png` |
| Gemini 錯誤與 fallback | PASS | 503、400 與修正紀錄見 `evidence/week04_tool_run_2026-10-08.log` |
| 自動化測試 | PASS | 56 tests，見同一 log |
| 真實 Email 寄送 | LIVE_NOT_RUN | 專題刻意限制為 Sandbox，不得冒充真實寄送 |
| GitHub push 與遠端 commit SHA | PENDING | remote 已確認；commit 後取得 SHA，push 後再確認遠端內容 |

## Known Issues

1. 待確認的草稿只保存在 Web Host 記憶體；伺服器重啟後必須重新產生。
2. Gemini 偶爾會回傳 HTTP 503；目前停止該次模型流程並改用明確標示的本機模板，不自動反覆重送。
3. 資工系官網未公布固定系辦辦公時間，因此系統只提供官方聯絡方式，不推測營業時間。
4. 真實 Email delivery 尚未實作；Week 04 Write Tool 只驗證確認、收件人限制、冪等性與 Sandbox receipt。

## 後續驗證計畫

1. 確認正確 GitHub remote 與要提交的檔案。
2. commit 後重新執行完整單元測試及 MCP demo。
3. 將最終 commit SHA 補入本檔，push 後確認 GitHub 頁面可看到 README、契約、測試與證據檔。
4. 若未來接真實寄信服務，另做測試帳號、權限隔離、撤銷／重試政策與稽核紀錄，不沿用目前 Sandbox 的 `LIVE_NOT_RUN` 證據。
