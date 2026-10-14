# Week 05 Framework Refactor Decision

日期：2026-10-14
目前決策：**有條件採用 LangChain；保留 manual 作為立即回退路徑**

## 替換範圍

| 類別 | 原版 | 候選版 |
| --- | --- | --- |
| 被替換機制 | `GeminiEmailGenerator.generate_with_contact_tool()` 手刻 Gemini function call 往返 | `LangChainEmailGenerator.generate_with_contact_tool()` 使用 `langchain.agents.create_agent` |
| 原專題入口 | `POST /api/email-draft` | 相同入口，不另開獨立 Demo |
| 切換方式 | `EMAIL_AGENT_BACKEND=manual` | `EMAIL_AGENT_BACKEND=langchain` |
| 模型可見工具 | `get_teacher_contact` | 同樣只有 `get_teacher_contact` |

候選版將模型訊息、ToolMessage 往返與結構化輸出交給 LangChain；Host 仍要求模型先執行一次官方聯絡資料查詢，且教師姓名必須與使用者已選定姓名完全一致。

## 為什麼替換這個部分

Week 04 原版必須自行處理 Gemini 第一次請求、解析 `functionCall`、檢查工具名稱與參數、執行 Host Tool、組裝 `functionResponse`、發出第二次模型請求，再解析與驗證結構化草稿。這些步驟大多是通用的 Agent 編排工作，不是校園 Email 的核心業務邏輯；模型或 Tool Calling API 格式改變時，也需要由專題自行維護整段訊息迴圈。

因此本次只將「模型與 Read Tool 的往返編排」換成 LangChain `create_agent`。這個邊界已有明確輸入、輸出與錯誤條件，能用相同案例比較原版和候選版，也能檢查框架是否真的降低手刻編排程式的責任，而不是只把套件裝進專案。

RAG 檢索、官方教師資料、收件人驗證、人工確認與 Sandbox Write Tool 不一起替換，原因是它們屬於本專題的資料與安全規則。若同時改動，發生結果差異時將無法判斷是框架、檢索資料或寄送流程造成，也會擴大錯寄與無依據回答的風險。本次目標不是重寫整個系統，而是驗證框架能否接手通用編排，同時不削弱既有安全邊界。

## 仍由本專題維護

- 官方教師資料、來源 metadata 與 `get_teacher_contact` 業務函式。
- Tool allowlist；Email 草稿階段絕不向模型公開 `send_email`。
- 收件人一致性、輸出品質與欄位長度驗證。
- 使用者確認、Sandbox Write Tool、`request_id` 冪等性與狀態查詢。
- Gemini Key、錯誤顯示、fallback 證據標示與 API 用量邊界。

## 同案例驗收

| 案例 | Manual 基線 | LangChain 候選 | 通過條件 |
| --- | --- | --- | --- |
| 正常工具往返 | 離線 PASS | 離線 PASS | 官方收件人、結構化草稿、可見 trace |
| 模型更換教師 | 原版拒絕 | 候選拒絕 | Host Tool 不得執行錯誤姓名 |
| 模型跳過 Read Tool | 原版要求 functionCall | 候選拒絕 | 不得在無官方工具結果時建立模型草稿 |
| 未確認 Write Tool | PASS | PASS | 回傳 `CONFIRMATION_REQUIRED` |
| 同一請求重送 | PASS | PASS | Sandbox 不新增第二筆 |

可重現指令：`.venv/bin/python scripts/run_week05_comparison.py`。離線測試會真的走過 `langchain.agents.create_agent`，但不呼叫 Gemini；固定比較結果為 6/6 PASS，完整回歸測試為 63/63 PASS。

## Live 與 Sandbox 證據

- `LIVE_PASS`：LangChain 搭配 `gemini-3.5-flash` 成功執行 `create_agent → get_teacher_contact`，以官方教師資料驗證收件人並產生結構化草稿。證據：[`evidence/week05_langchain_live_draft.png`](evidence/week05_langchain_live_draft.png)。
- `SANDBOX_PASS`：使用者確認後，既有 `send_email` Write Tool 回傳 `simulated_sent`。證據：[`evidence/week05_sandbox_write_pass.png`](evidence/week05_sandbox_write_pass.png)。
- `real_email_sent: false`：Write Tool 只寫入本機 Sandbox outbox，沒有寄送至外部信箱。
- 完整狀態、Request ID、Message ID 與測試紀錄保存在 `evidence/week05_offline_comparison_2026-10-14.log`。

## 得失、依賴與維護成本

候選版的收益是不用自行維護標準模型／工具訊息迴圈，框架也統一處理工具訊息與 `structured_response`。Live smoke test 已證明整合可執行，但目前只有一筆 Live 成功案例，尚未量測節省的開發時間、延遲與 Token 成本，也沒有足夠證據宣稱回答品質全面提升。

新增直接依賴為 `langchain==1.4.5` 與 `langchain-google-genai==4.4.2`，並帶入 LangGraph、Pydantic、Google GenAI SDK 等傳遞依賴。相較原版只用標準函式庫的 Gemini REST 接頭，安裝、冷啟動、版本相容性與除錯路徑都變複雜。

## 決策、回退與下一步

本次決策為有條件採用 LangChain 作為 Week 05 Email 草稿編排實作，課堂展示使用 `EMAIL_AGENT_BACKEND=langchain`。為避免一次 Live smoke test 被誤當成完整可靠性證明，`.env.example` 仍保留 `manual` 安全預設；後續累積更多 Live 案例並量測延遲與失敗率後，再評估是否變更預設值。

若 Gemini 或框架不穩定、草稿品質退步，或依賴成本不值得，設定 `EMAIL_AGENT_BACKEND=manual` 即可立即切回 Week 04 原版，不影響 RAG、收件人驗證、人工確認關卡或 Sandbox outbox。
