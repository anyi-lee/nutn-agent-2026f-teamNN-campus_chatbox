# NUTN Campus Chatbot

以 AI Agent 改善國立臺南大學學生取得校園資訊與辦理行政事務的體驗。

## 目前版本與交付（2026-10-29 更新）

目前可運作範圍為「資工系公開資訊查詢、教師聯絡與 Email 草稿／Sandbox 寫入」。以下以程式與證據為準，不將課程示範或規劃功能列為已完成：

- [Week 07 A 路線：帳號與多筆常用 Email 內容](docs/week07/README.md)

實作基準為 `6bbd34f`，Week 06 功能 commit 為 `12ab574`。預設配置仍為 `CHAT_WORKFLOW_BACKEND=baseline`、`EMAIL_AGENT_BACKEND=manual`；Routing 與 LangChain 是可切換候選，不應把不同配置的證據當成同一次執行。

2026-10-29 重驗：W7 68 項 Python／HTTP 與 22 組 JS VM 通過；跨週非 HTTP 回歸 137 項，130 通過、7 項因缺 LangChain 依賴跳過。下文 Week 04–06 的 `LIVE_PASS` 與測試數是各週歷史證據，不移作 W7 Live。

Week 07 依使用者確認改採 A 路線：本機帳密登入、每帳號多筆已確認的常用內容、新對話／重新登入讀回並選取套用、更正與撤回。原教師 context 清除保留為支援控制；離線與 HTTP 證據見 W07 文件，真實模型仍為 LIVE_NOT_RUN。Week 03 多證據／coverage failure、Week 06 嚴格分支分派及期中 Google Cloud／ADC 主流程仍為獨立待補項。

## 專題簡介

學生查詢課程、教室、教師或升學資訊時，經常需要瀏覽系所網站的不同頁面，逐一尋找需要的內容。本專題預計開發「校園辦事導航 Agent」，讓使用者直接以自然語言提出需求，Agent 會搜尋並整合系所網站內容，同時提供原始網頁連結，確保資訊可以查證。
除了回答問題，Agent 也能協助使用者實際完成校園事務。例如，當使用者提出「幫我寄信詢問某位老師專題名額」時，Agent 會查找正確的聯絡資訊、產生郵件主旨與正文，並在使用者確認後寄出；也能協助建立課程、活動或升學期限提醒。透過「查詢、規劃、確認、執行」的流程，減少學生搜尋資訊及切換不同工具所花費的時間。
對於寄送郵件、建立提醒或提交資料等會影響外部系統的操作，Agent 必須先顯示執行內容並取得使用者明確同意。若遇到資訊不足、資料衝突、個人資料或必須由人工處理的行政事項，系統不會自行推測，而會提供原始資訊或承辦單位，引導使用者進一步確認。

## 目前原型範圍

本階段使用南大資工系官方「師資陣容」頁面的版本化資料，支援：

- 查詢教師姓名、職稱、研究領域與公開 Email。
- 查詢資工系辦地址、電話分機與 Email；若詢問官網未公布的辦公時間，會明確標示證據不足並提供確認管道。
- BM25 與透明 Dense Stub 檢索比較。
- 顯示官方 Citation、Top-3 排名與檢索分數。
- 追問時沿用上一輪教師脈絡。
- 使用 Gemini 或本機模板產生 Email 草稿。
- 資料不足或超出來源範圍時拒答。

目前**不包含**課程開設資料、教師即時位置、私人聯絡方式、其他系所、校長等校級行政主管資料與真實寄信功能。資工系官網也未公布固定系辦辦公時間，因此系統不會自行推測。Email 的 Write Tool 只會寫入本機 Sandbox outbox，畫面與 receipt 均會清楚標示沒有寄到外部信箱。

## 組員

| 學號 | 姓名 | 分工 |
| --- | --- | --- |
| S11259013 | 羅暐媁 |  |
| S11259019 | 莊旻芳 |  |
| S11259029 | 李安以 |  |


## 問題定義

### 目標使用者

- 不熟悉校園行政流程的新生與在校生
- 想快速確認承辦單位、申請條件或截止日期的學生
- 需要整合校園活動與服務資訊的學生

### 現有痛點

- 校園資訊分散在不同處室網站、公告與文件中。
- 使用者不一定知道正確的行政用語或負責單位。
- 搜尋結果可能過期、缺少來源，或無法直接回答特定情境。
- 跨單位問題往往需要多次搜尋，才能整理出完整辦理步驟。

## 三個候選問題

### 1. 校園辦事導航 Agent（優先方向）

可以用提問的方式直接獲取系所網站相關資訊：課程、教室、教師資訊、升學資訊等
連結各項資訊代替辦公

### 2. 台南大學午餐選擇 AI Agent

建立一個「台南大學午餐選擇 AI Agent」，根據學生的預算、距離、料理類型、飲食偏好以及過去飲食紀錄，自動協助學生選擇今天的午餐。

### 3. 台南大學智慧失物招領 AI Agent

建立「校園失物招領 AI Agent」，利用 LLM 分析失物描述，自動搜尋可能匹配的失物。

## Agent Necessity Test

### 誰遇到問題？目前流程哪裡不夠好？

學生經常不知道資訊由哪個處室維護，也可能只會用口語描述問題。目前流程需要自行辨識關鍵字、瀏覽多個網頁並比較資料，耗時且容易遺漏重要條件。

### 需要哪些資料、工具與權限？

預計使用的資料與工具包括：

- 校方公開規章、行政流程、FAQ 與處室聯絡資料
- 校園公告、活動資訊與重要日期
- 校園文件檢索工具
- 承辦單位與地點查詢工具
- 活動搜尋或行事曆提醒工具（後續功能）

系統原則上只讀取公開資訊；涉及個人資料、寫入行事曆或執行外部操作時，必須取得使用者明確同意。

### 為什麼需要 Agent？

校園問題常包含多個條件，Agent 需要辨識意圖、選擇資料來源或工具、整合不同結果、處理資訊不足，並將答案轉換成可執行步驟。這不只是單次關鍵字查詢。

### 能否以確定性軟體解決？

固定 FAQ、單位電話與地點查詢可以使用確定性規則處理；自然語言理解、跨文件資訊整合及情境式回答則適合由 Agent 協助。系統將結合兩者，讓可驗證的資料查詢交由工具執行，避免語言模型自行捏造事實。

## 預計核心功能

1. 理解使用者的校園問題並輸出結構化意圖。
2. 搜尋校方文件，回覆時附上資料來源。
3. 查詢承辦單位、地點、聯絡方式與辦理時間。
4. 將複合問題整理成明確的辦理步驟。
5. 產生郵件或提醒內容，經使用者確認後代理執行。
6. 資料不足或來源衝突時停止推測並要求確認。
7. 記錄執行軌跡、錯誤與評估結果，供後續改善。

## 預計工具

- `search_campus_documents`：搜尋校規、行政流程與 FAQ。
- `lookup_office_info`：查詢承辦單位、地點及聯絡方式。
- `search_campus_events`：搜尋校園活動與重要日期。
- `create_calendar_reminder`：經使用者確認後建立提醒（選配）。
- `send_email`：顯示收件人、主旨與正文，經使用者確認後寄送郵件。

## 初步成功標準

- 回答引用的規定、日期與承辦單位皆能追溯至校方來源。
- 測試問題能得到正確、完整且可執行的步驟。
- 資訊不足、來源衝突或工具失敗時，不產生無依據答案。
- 敏感或具有外部影響的操作必須先取得使用者確認。
- 系統可記錄延遲、成本、工具結果與失敗原因。


## 開發狀態

Week 03 原型已完成：官方教師資料快照、BM25 Baseline、Dense Stub、Evidence Gate、Generator Comparison、Email 草稿與本機 Web UI 均可重現執行。評估結果位於 `artifacts/`。

Week 04 加入共用 Tool Server 與 stdio MCP adapter：

- `get_teacher_contact`：從版本化官方資料取得教師公開 Email。
- `send_email`：經明確確認後寫入 Sandbox outbox，不寄真實郵件。
- `get_email_status`：用 `request_id` 查詢執行狀態。
- 設定 Gemini Key 時，草稿流程會執行 `functionCall → Host 驗證 → tools/call → functionResponse`；未設定時明確退回本機模板。
- 寄送草稿由 Host 保存，瀏覽器不能替換已確認的收件人與正文。
- SQLite primary key 提供 idempotency，重複請求不會新增第二封。

完整契約、安全規則與 Known Failure 見 `week04_tool_contract.md`。
Week 04 自評、執行證據與尚未完成項目分別見 `week04_self_check.md` 與 `evidence/`。

Week 05 新增可回退的 LangChain 候選版，只替換 Email 草稿中的模型／Read Tool 往返：

- 原版：`EMAIL_AGENT_BACKEND=manual`，由 `GeminiEmailGenerator` 維護 function calling 迴圈。
- 候選：`EMAIL_AGENT_BACKEND=langchain`，由 `langchain.agents.create_agent` 維護迴圈。
- 替換原因：第一次模型請求、Tool Call 解析、Tool Response 組裝與第二次模型請求屬於通用 Agent 編排；交由框架維護可減少專題自行處理模型訊息協定的責任。
- 兩版共用官方資料、Host 驗證、人工確認、Sandbox Write Tool 與冪等規則。
- `send_email` 不會公開給 LangChain Agent，模型無法自行寄送或模擬寄送。
- 固定離線比較 6/6 PASS，完整回歸測試 63/63 PASS。
- LangChain＋Gemini 草稿流程為 `LIVE_PASS`；確認後的本機 Write Tool 為 `SANDBOX_PASS`；`real_email_sent: false`。

本次有條件採用 LangChain 作為 Week 05 課堂展示實作，並保留 `manual` 作為立即回退路徑。替換理由、驗收限制與完整決策見 [`week05_refactor_decision.md`](week05_refactor_decision.md)，執行紀錄見 [`evidence/week05_offline_comparison_2026-10-14.log`](evidence/week05_offline_comparison_2026-10-14.log)。

Week 06 新增可回退的 Routing workflow，只改造聊天入口：

- 選擇 Routing 的原因：教師、系辦與 Email 是互斥的處理分支，原本依關鍵字順序判斷容易在多意圖輸入時先命中錯誤分支；Routing 可先分類，再由 Host 驗證並在不確定時走 `clarify` 停止。
- Gemini Router 只提出 `faculty_query`、`office_query`、`email_request` 或 `clarify`。
- Host Route Gate 會驗證 route 與 reason code；未知結果、provider 失敗與多意圖輸入都會停止，不執行下游工具。
- 每次回應會留下 route、stage、停止原因與證據狀態，UI 可展開查看。
- `CHAT_WORKFLOW_BACKEND=baseline` 保留原本流程；`routing` 啟用候選版。
- 固定離線驗收 8/8 PASS；Gemini Router 的 `faculty_query` 與 `clarify` 實測皆為 `LIVE_PASS`。

完整設計、前後比較與證據索引見 [`docs/week06/README.md`](docs/week06/README.md)。

### Week 07 Account-scoped Memory（2026-10-29）

A 路線新增本人確認的長期記憶：常用 Email 文字、完整草稿及校務問答個人事實。登入後由 Gemini 理解自然說法，提出新增／同義更正候選，使用者勾選確認才保存或覆蓋；後續「找微積分老師」可查用本人關係並核對官方資料。完整草稿在 Email 助手上方勾選直接重用，可手動或選擇性 AI 調整，寄送仍獨立確認且只寫 Sandbox。沒有公版或表單保存。

本週 68 項 Python／localhost HTTP、22 組 JS VM 全通過；跨週非 HTTP 回歸 137 項，130 PASS、7 項選配 LangChain 依賴 skipped。兩份結果有重疊，不加總。語意與 AI 測試用明示替身，本週真實 Gemini／ADC 為 LIVE_NOT_RUN，畫面／備用錄影尚未驗證。候選仍是 WORKING_TREE，沒有 commit／push。

```powershell
python -W error::ResourceWarning scripts/run_week07_validation.py
python scripts/run_personal_memory_validation.py
python -W error::ResourceWarning scripts/run_week07_memory_demo.py
```

文件採歷週格式：[本週 README](docs/week07/README.md)／[記憶決策與版本紀錄（含 ADR／前後比較）](docs/week07/memory_adr.md)／[驗收](docs/week07/acceptance.md)／[Evidence Index](docs/week07/evidence_index.md)／[提交檢核](docs/week07/submission_checklist.md)。啟動、Key 設定、操作與補驗證計畫均由本週 README 索引。

## 本機 UI 原型

目前提供本機 Web UI，可查詢資工系教師公開資訊、切換 BM25／Dense Stub 檢索方式、產生 Email 草稿，並在人工確認後執行 Sandbox Write Tool。Manual 後端不需第三方套件；LangChain 候選版需安裝 Week 05 依賴。兩種後端都不會實際寄送郵件。

```bash
python3 app.py
```

啟動後開啟 `http://127.0.0.1:8000`。未安裝 Week 05 依賴時可執行基礎測試；LangChain 測試會明確標示為 skipped：

```bash
python3 -m unittest discover -s tests -v
```

安裝 Week 05 依賴後，完整 63 項測試可執行：

```bash
.venv/bin/python -W error::ResourceWarning -m unittest discover -s tests -v
```

MCP stdio 的完整讀取、拒絕、確認、重複請求與狀態查詢可執行：

```bash
python3 scripts/run_week04_tool_demo.py
```

輸出中的 `MCP_LOCAL_PASS` 只代表本機 MCP 與 Sandbox 工具流程通過，不代表 Gemini 或真實 Email 服務已成功執行。

### 使用 Gemini 產生 Email 草稿

請勿將 API Key 寫入程式碼或提交到 Git。可使用互動式啟動腳本，Key 只會保留在該次程序的環境變數中：

```bash
bash scripts/run_with_gemini.sh
```

`.env.example` 只列出變數名稱與安全的模型預設值，不含真實 Key；目前啟動腳本不會自動載入 `.env`，而是於終端機互動輸入 Key。未設定 Key 或 Gemini 暫時失敗時，系統會改用本機模板，且不會實際寄出郵件。預設模型可透過 `GEMINI_MODEL` 調整。

### Week 05 LangChain 候選版

先建立專案虛擬環境並安裝固定版本依賴：

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements-week05.txt
```

執行離線前後驗收（不呼叫 Gemini）：

```bash
.venv/bin/python scripts/run_week05_comparison.py
```

啟動原版：

```bash
EMAIL_AGENT_BACKEND=manual bash scripts/run_with_gemini.sh
```

啟動候選版：

```bash
EMAIL_AGENT_BACKEND=langchain bash scripts/run_with_gemini.sh
```

目前狀態：

- `WEEK05_OFFLINE_PASS`：固定比較 6/6 PASS，且測試真的執行 `langchain.agents.create_agent`。
- `LIVE_PASS`：LangChain＋`gemini-3.5-flash` 成功呼叫 `get_teacher_contact` 並產生 grounded 草稿。
- `SANDBOX_PASS`：人工確認後 `send_email` 回傳 `simulated_sent`。
- `real_email_sent: false`：沒有郵件寄至外部信箱。

證據：

- [LangChain Live 草稿](evidence/week05_langchain_live_draft.png)
- [Sandbox Write Tool](evidence/week05_sandbox_write_pass.png)
- [完整狀態與測試紀錄](evidence/week05_offline_comparison_2026-10-14.log)

### Week 06 Routing 候選版

執行離線驗收：

```bash
python3 scripts/run_week06_comparison.py
```

啟動 Routing candidate（Key 仍由終端機互動輸入）：

```bash
CHAT_WORKFLOW_BACKEND=routing bash scripts/run_with_gemini.sh
```

若需立即回退：

```bash
CHAT_WORKFLOW_BACKEND=baseline python3 app.py
```

## 專案結構

```text
data/       教師 Chunks 與 Fixed Queries
artifacts/  Retrieval／Generator 比較結果
evidence/   離線測試、Live 與 Sandbox 執行證據
src/        檢索、Evidence Gate、Gemini 與應用服務
ui/         Web UI
scripts/    可重現執行腳本
tests/      自動化測試
runtime/    本機 Sandbox outbox（Git 忽略）
```
