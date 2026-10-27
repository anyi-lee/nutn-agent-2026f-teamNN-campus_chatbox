# Week 06 Live Routing Evidence

- Date：2026-10-27（Asia/Taipei）
- Workflow：Routing
- Provider：Gemini
- Model：`gemini-3.5-flash`
- Status：`LIVE_PASS`
- API Key：未保存
- Internal reasoning：未保存
- Real email sent：`false`

## Case 1 — 正常教師查詢

Input：`林朝興老師的研究領域`

Observed result：

- Route：`faculty_query`
- Live status：`LIVE_PASS`
- Downstream：BM25 Top 3
- Evidence Gate：PASS
- Grounded official citation：present

Evidence：[week06_routing_faculty_live_pass.png](week06_routing_faculty_live_pass.png)

SHA-256：`e747cddcf8a19a60c6dafe76da3168c2297beb56737ffaab81f9975e48b1ee90`

## Case 2 — 多意圖 Workflow 邊界

Input：`查林朝興老師的研究領域，順便詢問系辦辦公時間`

Observed result：

- Route：`clarify`
- Live status：`LIVE_PASS`
- Stop code：`ROUTE_REQUIRES_CLARIFICATION`
- Downstream retrieval：not executed
- Tool action：not executed

Evidence：[week06_routing_clarify_live_pass.png](week06_routing_clarify_live_pass.png)

SHA-256：`1a4dcdb3c0ec40ca2f21a861f721e13e01e03e4889a878ef0cff2e4c77a648ae`

## Evidence boundary

這兩張截圖證明 Live Router 的正常路由與邊界停止行為，不提供 latency 或 token 數據，因此相關欄位仍標示 unavailable。Provider failure、無效輸入及未知 route 由離線自動化測試覆蓋。

## Email 與 Sandbox 補充證據

- Gemini Email 草稿完成 `functionCall → functionResponse`：[week06_email_live_draft.png](week06_email_live_draft.png)
- 人工確認後 Write Tool 回傳 `simulated_sent`：[week06_sandbox_write_pass.png](week06_sandbox_write_pass.png)
- Sandbox status：`SANDBOX_PASS`
- Real email sent：`false`
- 重送冪等性由固定離線測試覆蓋；單張 Sandbox 截圖本身不宣稱證明重送行為。
