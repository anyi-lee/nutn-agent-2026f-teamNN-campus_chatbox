# Week 06 — Routing Workflow

> 2026-10-28 架構核對補註：以下為 Week 06 原始設計與歷史證據。現況教師／Email 分支仍呼叫 `_chat_baseline`，可能再次依系辦關鍵字分流；固定案例不能證明所有分派皆一致。此為尚未修正的分派缺口。Week 07 依使用者確認採 A 路線的帳號與多筆常用文字記憶，原 session 清除保留為支援控制；見 [W07](../week07/README.md)，真實模型仍 LIVE_NOT_RUN。

## 本週目標

在既有校園 Chatbot 上加入一個可回退的 **Routing workflow**，把使用者輸入明確分成單一路徑，再由 Host 驗證後執行。這次只改造聊天入口，不改動 Week 04 的 Sandbox Write Tool，也不會寄出真實 Email。

- Baseline SHA：`e83196d`
- Candidate SHA：`12ab574`（Routing 實作與執行證據）
- Workflow：Routing
- 離線證據：`WEEK06_OFFLINE_PASS`（8/8）
- Gemini 路由實測：`LIVE_PASS`（`faculty_query`、`clarify`）
- 真實寄信：`false`

## 為什麼選擇 Routing

目前 Chatbot 已經有三種彼此獨立的任務：查詢教師資料、查詢系辦資訊，以及產生 Email 草稿。原本的 Baseline 依照固定的 `if/else` 關鍵字順序判斷意圖；當功能增加或使用者同時提出兩種需求時，可能只因先命中某個關鍵字就進入錯誤分支。例如「查林老師研究領域，順便詢問系辦時間」同時包含教師與系辦意圖，若直接選第一個命中的規則，就可能執行不完整或錯誤的下游查詢。

因此本週選擇 Routing，讓 Gemini 先把輸入分類為 `faculty_query`、`office_query`、`email_request` 或 `clarify`，再由 Host Route Gate 驗證後只執行一條分支。遇到多意圖、不確定或超出範圍時，必須走 `clarify` 並停止，不會誤用檢索或 Email 工具。這個做法可以直接解決目前的「意圖分流」問題，同時保留既有 RAG、Evidence Gate、人工確認與 Sandbox Write Tool，不需要重寫已驗證的功能，也能用 `CHAT_WORKFLOW_BACKEND=baseline` 立即回退。

沒有選擇 Chaining，是因為教師、系辦與 Email 任務不需要每次依序全部執行；沒有選擇 Evaluator-Optimizer，是因為本週主要問題是選錯處理路徑，而不是反覆改善回答文字；目前資料與工具數量也不需要增加多 Agent 的協調成本。

## 路由與分支

| Route | 用途 | 下游行為 |
| --- | --- | --- |
| `faculty_query` | 教師姓名、職稱、研究與公開聯絡資料 | 執行既有 RAG 與 Evidence Gate |
| `office_query` | 資工系辦地址、電話、Email、辦公時間 | 查詢版本化官方系辦資料 |
| `email_request` | 明確要求產生或撰寫給教師的 Email | 先用官方資料確認教師，再顯示草稿入口 |
| `clarify` | 多意圖、資料不足、超出範圍或不確定 | 停止，不呼叫下游查詢或工具 |

流程為：`Input Gate → Gemini route proposal → Host Route Gate → 單一 branch → result`。模型只提出 `route` 與 `reason_code`；Host 會再次驗證 allowlist，未知路由不會被執行。

## 停止與失敗規則

- 空白輸入：`EMPTY_MESSAGE`，不呼叫 Router。
- Gemini 未設定、逾時或失敗：`ROUTER_PROVIDER_FAILED`，不執行下游。
- 路由或 reason code 不在 allowlist：`ROUTE_DECISION_INVALID`，不執行下游。
- 多意圖或不確定：`ROUTE_REQUIRES_CLARIFICATION`，回問使用者。
- Email Write Tool：仍須人工確認，且只寫入本機 Sandbox；重送相同 `request_id` 不會新增第二封。

## 執行方式

預設保留 Week 05 前的聊天行為：

```bash
CHAT_WORKFLOW_BACKEND=baseline python3 app.py
```

使用 Gemini 路由候選版：

```bash
CHAT_WORKFLOW_BACKEND=routing bash scripts/run_with_gemini.sh
```

啟動腳本會在終端機互動讀取 Key，不會把 Key 寫入專案。

## 重現驗收

固定 Week 06 驗收切片（不呼叫 Gemini）：

```bash
python3 scripts/run_week06_comparison.py
```

完整回歸測試：

```bash
python3 -W error::ResourceWarning -m unittest discover -s tests -v
```

離線測試使用明確標示的 fixture Router，只驗證 workflow、Host Gate 與停止條件。另以 Gemini `gemini-3.5-flash` 完成正常 `faculty_query` 與多意圖 `clarify` 實測；兩者畫面均顯示 `LIVE_PASS`。證據不保存 API Key 或模型內部推理。

## 文件與證據

- [Workflow ADR](workflow_adr.md)
- [Before / After](before_after.md)
- [Evidence Index](evidence_index.md)
- [離線執行紀錄](../../evidence/week06_offline_routing_2026-10-27.log)
- [Live Routing 證據說明](../../evidence/week06_live_routing_2026-10-27.md)
- [faculty_query / LIVE_PASS](../../evidence/week06_routing_faculty_live_pass.png)
- [clarify / LIVE_PASS](../../evidence/week06_routing_clarify_live_pass.png)
- [Gemini Email 草稿](../../evidence/week06_email_live_draft.png)
- [Sandbox Write Tool / SANDBOX_PASS](../../evidence/week06_sandbox_write_pass.png)
