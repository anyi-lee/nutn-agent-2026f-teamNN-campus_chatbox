# Week 04 Tool Contract：教師查詢與 Sandbox Email

## 目標與邊界

本週把既有「教師資料查詢＋Email 草稿」改成可測試的 Tool Use 流程：

1. Read Tool 從版本化官方資料解析教師聯絡資訊。
2. Gemini 或本機模板產生草稿，但不能決定是否執行寫入。
3. Host 顯示不可變的收件人、主旨與正文。
4. 使用者明確確認後，Host 才加入 `confirmed: true` 與 `request_id`。
5. Write Tool 將信件寫入本機 Sandbox outbox，回傳可查詢的 receipt。

目前不寄送真實 Email，也不支援任意收件地址、CC、BCC、附件或自動重試。

## Host 流程

```text
使用者需求
  → get_teacher_contact（read）
  → 產生 Email 草稿
  → 顯示預覽與官方來源
  → 使用者勾選確認
  → Host 取回伺服器端草稿並加入 confirmed/request_id
  → send_email（write）
  → receipt / get_email_status
```

瀏覽器只傳送 `draft_id` 和確認事件。收件人、主旨與正文由 Host 使用伺服器端保存的草稿組成，避免確認後遭到竄改。

## Chat Evidence Gate

檢索 Top 1 不等於可以回答。Host 會在生成回答前檢查：

- 來源是否為目前允許的官方且有效資料。
- 明確教師姓名或對話脈絡是否與 Top 1 身分一致。
- 未指定教師的聯絡問題是否缺少必要實體。
- 命中的詞是否包含具辨識力的職務或研究屬性，而非只有共通詞。
- BM25 原始分數是否達到最低門檻。
- 未錨定教師時，Top 1 是否明顯領先第二名。

未通過時回傳結構化錯誤，例如 `MISSING_TEACHER_IDENTITY`、`LOW_RETRIEVAL_CONFIDENCE` 或 `AMBIGUOUS_EVIDENCE`，並保留檢索軌跡供測試；不會把「有命中」直接當成「有答案」。

## Tool 1：`get_teacher_contact`

- 類型：Read
- 副作用：無
- 輸入：`teacher_query`
- 成功狀態：`found`
- 其他狀態：`not_found`、`ambiguous`
- 證據：`source_id`、`source_url`、`retrieved_at`、`index_version`

成功輸出包含 `teacher_id`、姓名、職稱、公開 Email、來源 URL、權威性與有效狀態。

## Tool 2：`send_email`

- 類型：Write
- 執行模式：Sandbox
- 真實寄信：否
- 必填：`teacher_id`、`to`、`subject`、`body`、`request_id`、`confirmed`
- 人工確認：`confirmed` 必須為 boolean `true`
- 收件人限制：必須與版本化官方教師資料完全一致
- 冪等性：`request_id` 是 SQLite outbox 的 primary key

第一次執行回傳 `simulated_sent`；相同 `request_id` 再次執行回傳 `already_processed`，且沿用原 `message_id`，不新增第二筆資料。

## Tool 3：`get_email_status`

- 類型：Read
- 輸入：`request_id`
- 用途：在 Write Tool timeout 或連線中斷後先查明狀態
- 狀態：`simulated_sent` 或 `not_found`

## 寫入安全規則

- 未確認：停止，回傳 `CONFIRMATION_REQUIRED`。
- 非官方教師：停止，回傳 `RECIPIENT_NOT_ALLOWED`。
- Email 與官方資料不一致：停止，回傳 `RECIPIENT_MISMATCH`。
- Timeout：不直接重送；先呼叫 `get_email_status`。
- 查到 receipt：視為已處理，不重送。
- 查無 receipt：只在重試預算內使用同一個 `request_id` 重試一次。
- Log 與 receipt 不包含 API key；正式證據不應保存完整私人信件內容。

## MCP 介面

`mcp_server.py` 透過 stdio JSON-RPC 提供：

- `initialize`
- `tools/list`
- `tools/call`

Web Host 與 MCP adapter 共用 `src/email_tools.py`，避免 UI 測試與 MCP 行為使用兩套不同規則。

## Gemini Function Calling

設定 `GEMINI_API_KEY` 時，草稿生成先只向 Gemini 公開 Read Tool `get_teacher_contact`：

1. Gemini 回傳 `functionCall`。
2. Host 驗證工具名稱必須在 read-only allowlist，且 `teacher_query` 必須等於使用者已選定的教師。
3. Host 執行 `get_teacher_contact`。
4. Host 將真實工具結果作為 `functionResponse` 傳回 Gemini；若 `functionCall` 帶有 `id`，會原樣放入對應的 `functionResponse`。
5. Gemini 才能輸出結構化 `subject` 與 `body`。

草稿階段不會向模型公開 `send_email`。Write Tool 只能由 UI 的人工確認事件觸發；Gemini 無法自行填入 `confirmed: true`。

## 證據狀態

- 本機 Read/Write Tool：執行測試通過後標為 `LOCAL_PASS`。
- MCP stdio round trip：執行 smoke script 通過後標為 `MCP_LOCAL_PASS`。
- Gemini 真實呼叫：只有實際使用 Key 成功時才能標為 `LIVE_PASS`；否則為 `LIVE_NOT_RUN` 或 `LIVE_FAIL`。
- 真實 Email：目前固定為 `LIVE_NOT_RUN`，不得用 Sandbox receipt 冒充。

## Known Failure

待確認草稿目前只保存在 Web Host 記憶體。伺服器重啟後，舊的 `draft_id` 會回傳 `DRAFT_NOT_FOUND`，使用者必須重新產生並確認草稿；已寫入 Sandbox 的 receipt 仍可用 `request_id` 查詢。

## 參考

- Google AI for Developers：<https://ai.google.dev/gemini-api/docs/generate-content/function-calling>
- Gemini Generate Content API：<https://ai.google.dev/api/generate-content>
