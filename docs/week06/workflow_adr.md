# ADR — 採用 Routing Workflow

## 狀態

Accepted for Week 06 candidate；可透過環境變數回退。

## 背景與問題

原本的 `CampusService.chat()` 依序用關鍵字條件判斷系辦、課程、行政角色與教師查詢。這在目前小範圍可運作，但新增意圖時條件順序會影響結果；多意圖輸入也可能被第一個命中的條件直接送進錯誤分支。例如同時要求教師研究資訊與系辦事項，Baseline 可能只因出現「系辦」而執行系辦分支。

## 決策

加入可選的 Routing candidate：Gemini 只輸出結構化的 `route` 與 `reason_code`，Host Route Gate 驗證 allowlist 後，只允許執行一條分支。可接受路由為：

- `faculty_query`
- `office_query`
- `email_request`
- `clarify`

多意圖、不確定、缺少對象或超出資料範圍必須選 `clarify`。若 provider 失敗、schema 不符或 route 不合法，系統停止而不是猜測或改走預設工具。

## 為什麼選 Routing

目前最明顯風險發生在「進哪一條處理路徑」，而不是單一路徑內需要很多連續步驟。Routing 能直接展示明確的分支、Host 驗證、停止條件與邊界測試，且能重用既有 RAG、Evidence Gate、Email 草稿與 Sandbox Write Tool。

沒有選 Chaining，因為教師查詢與系辦查詢不是固定必須依序完成的步驟；硬串接會增加不必要呼叫。沒有選 Evaluator-Optimizer，因為目前首要問題不是反覆潤稿，而是避免錯誤意圖進入錯誤工具。沒有採用平行或多 Agent，因為目前資料範圍小，額外協調成本高於收益。

## Scaffold 與 Context Engineering

- Model context 只包含目前訊息與可選的 `context_teacher`。
- 不提供 API Key、完整聊天紀錄、檢索全文、Sandbox receipt 或 Write Tool。
- Router 沒有可呼叫工具，只能提出決策。
- Host 保留資料來源、Evidence Gate、收件人驗證、人工確認與冪等規則。
- UI 顯示 route、各 stage 狀態與停止原因，不顯示模型內部推理。

## 代價與風險

- 正常聊天多一次 Gemini 呼叫，會增加延遲與成本。
- Provider 不可用時，Routing candidate 會停止；不自動用規則猜路由。
- 離線 fixture 只能驗證控制流程，不能代表真實模型的路由品質。
- Router 的 prompt 或模型版本改變後，必須重新跑四類案例與邊界案例。

## 回退方式

設定 `CHAT_WORKFLOW_BACKEND=baseline` 即回到原本條件式入口；預設值也是 `baseline`。回退不會改動資料、Sandbox outbox 或 Email 工具契約。

