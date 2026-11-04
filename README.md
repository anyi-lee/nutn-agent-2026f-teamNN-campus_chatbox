# NUTN Campus Chatbot

以 AI Agent 改善國立臺南大學學生取得校園資訊與辦理行政事務的體驗。

組別：第五組（Team 05）。

## 期中報告（2026-11-04）

- [第五組期中報告最終簡報 PDF（28 頁）](docs/midterm/final_2026-11-04/NUTN_Campus_Agent_Midterm_Team05_2026-11-04.pdf)
- [期中報告交付說明](docs/midterm/README.md)
- [團隊分工與後續計畫](docs/midterm/team_contributions.md)
- [正常／邊界案例與測試證據索引](docs/midterm/evidence_index.md)

系統程式版本為 [`4d7469e`](https://github.com/anyi-lee/nutn-agent-2026f-teamNN-campus_chatbox/commit/4d7469e0cb6fcba9e0827f122d48b8436bd7703e)。期中報告 PDF 由團隊提供的最終版整理，封面標示「期中報告」及「第五組」，分工依簡報第 25 頁同步。報告檔案指紋見 [version_manifest.json](docs/midterm/final_2026-11-04/version_manifest.json)。以下測試紀錄保留原執行日期，不宣稱本次文件更新重新執行了模型驗證。

## 目前版本與交付（2026-11-03 更新）

目前 Web 系統已從資工系擴充為「全校公開單位名錄＋已收錄教師聯絡資料」。依最新需求，寫信改為「處室／學系」單選的分層表單，恢復姓名、目的、自己的系所、年級與詢問內容欄位。全校名錄不等於全校知識完整收錄：目前有 73 筆單位／組別、191 筆教師所屬／信箱關聯（182 組不同姓名／信箱，跨系支援分列）及 23 個單位公開收件窗口。已沿使用者提供的 16 個入口深入名錄、個人頁與分頁，新增 147 筆關聯；生科與部分學程教師仍待補。沒有驗證的信箱、固定服務時間、現任主管或辦理規章不自行推測。

- [最新：分層寫信表單、欄位與驗證](docs/email_form.md)
- [16 系所／學程師資深入追查、逐系數量與未完成項目](docs/faculty_source_audit.md)
- [提交前完整測試 Log](evidence/prepush_validation_2026-11-03.log)
- [Gemini 草稿與修改 Live 證據（合成學生）](evidence/revision_identity_live_2026-11-03.json)
- [國文系個人頁漏抓修正與來源](docs/chinese_faculty_refresh.md)
- [全校來源與先前對話式原型紀錄](docs/campus_conversation.md)

流程：選處室再選組別，或選學系再選老師 → 填寫寄件人與詢問資料 → Host／Read Tool 查核官方收件人 → Gemini 潤稿（無 Key 時明示本機模板）→ 草稿預覽／修改 → 獨立人工確認 → 僅寫入本機 Sandbox。點擊查詢回答的寫信按鈕會直接帶入分類、處室／組別或系所與對象。既有帳號隔離、常用內容與完整草稿重用保留。

提交前重驗：207 項 Python／localhost HTTP、原有 22 組與新版 25 組 JS VM 測試通過；資料維護解析器另 10 項通過（需 lxml，不併入 207 項）。初跑的 3 項 HTTP 測試受沙盒禁止綁定本機埠影響，允許本機測試伺服器後完整重跑通過；維護解析器改用已安裝 lxml 的 Python 通過，錯誤與重跑均保留於 log。

2026-11-03 已用合成訪客實際呼叫 Gemini，建立作業二草稿再修改為作業三，均為 `LIVE_PASS`、沒有 fallback、收件人／信箱／署名不變；此案例未寄送且仍要求獨立確認。修正包含寄出後重開還原預設表單、舊草稿姓名相容及 AI 修改收件人鎖定。Google Cloud／ADC 主流程、語意個人記憶與可選框架／Routing 的同版本 Live 仍待補，不以 Email 成功代替其他功能驗證。

`4d7469e` 程式提交包含程式、公開資料、測試與對應技術文件／證據；期中簡報另於 2026-11-04 提交，入口見上方「期中報告」。私人資料庫、Key、ADC 憑證與本機快取不提交。

查詢回答現在附上可用的「寫信給對方」入口，含個人記憶解析出的已驗證教師與有公開信箱的單位。點擊直接帶入對象，既有草稿更換收件人須先確認；查詢與寫信送出即清空輸入框，失敗可還原且不覆蓋新輸入，另有中文輸入法 Enter 保護。[前端修正證據](evidence/chat_email_ui_fix_2026-11-02.log)

以下為歷週交付索引與歷史證據，配置／測試數請依各週文件辨識：

- [Week 07 A 路線：帳號與多筆常用 Email 內容](docs/week07/README.md)

本次修改前同步基準為 `65a8517`；W7 程式基準為 `967ee1e`，Week 06 功能 commit 為 `12ab574`。預設配置仍為 `CHAT_WORKFLOW_BACKEND=baseline`、`EMAIL_AGENT_BACKEND=manual`；Routing 與 LangChain 是可切換候選，不應把不同配置的證據當成同一次執行。

2026-10-29 重驗：W7 68 項 Python／HTTP 與 22 組 JS VM 通過；跨週非 HTTP 回歸 137 項，130 通過、7 項因缺 LangChain 依賴跳過。下文 Week 04–06 的 `LIVE_PASS` 與測試數是各週歷史證據，不移作 W7 Live。

Week 07 依使用者確認改採 A 路線：本機帳密登入、每帳號多筆已確認的常用內容、新對話／重新登入讀回並選取套用、更正與撤回。原教師 context 清除保留為支援控制；離線與 HTTP 證據見 W07 文件，真實模型仍為 LIVE_NOT_RUN。Week 03 多證據／coverage failure、Week 06 嚴格分支分派及期中 Google Cloud／ADC 主流程仍為獨立待補項。

## 專題簡介

學生查詢課程、教室、教師或升學資訊時，經常需要瀏覽系所網站的不同頁面，逐一尋找需要的內容。本專題預計開發「校園辦事導航 Agent」，讓使用者直接以自然語言提出需求，Agent 會搜尋並整合系所網站內容，同時提供原始網頁連結，確保資訊可以查證。
除了回答問題，Agent 也能協助使用者實際完成校園事務。例如，當使用者提出「幫我寄信詢問某位老師專題名額」時，Agent 會查找正確的聯絡資訊、產生郵件主旨與正文，並在使用者確認後寄出；也能協助建立課程、活動或升學期限提醒。透過「查詢、規劃、確認、執行」的流程，減少學生搜尋資訊及切換不同工具所花費的時間。
對於寄送郵件、建立提醒或提交資料等會影響外部系統的操作，Agent 必須先顯示執行內容並取得使用者明確同意。若遇到資訊不足、資料衝突、個人資料或必須由人工處理的行政事項，系統不會自行推測，而會提供原始資訊或承辦單位，引導使用者進一步確認。

## 目前原型範圍

本階段使用南大官方教學／行政單位、人事室電話分機表、各單位公開網站及原有資工系版本化師資資料，支援：

- 查詢全校已收錄單位的官方入口、公開電話／分機及信箱。
- 查詢已收錄教師的姓名、公開 Email 與來源；研究領域依來源有無收錄，不假設每位都有。
- 未收錄的辦公時間、主管姓名或辦事流程，標示證據不足並提供確認管道。
- 教師使用 BM25；透明 Dense Stub 是原資工系人工 alias 教學比較，不代表全校 embedding。新增跨系教師自動使用 BM25 並在軌跡標示實際檢索方式。
- 顯示官方 Citation、Top-3 排名與檢索分數。
- 追問時沿用上一輪教師脈絡。
- 分層選擇處室／學系老師，填寫姓名、目的、自己的系所與年級後，使用 Gemini 或明示的本機模板產生草稿，保留預覽、編輯及獨立確認。
- 資料不足或超出來源範圍時拒答。

目前**不包含**完整全校師資、當學期課程開設資料、教師即時位置、私人聯絡方式、未驗證的現任主管姓名、完整業務規章與真實寄信功能。校長室等單位入口可查，但不等於已確認現任主管私人或個人信箱。Email 的 Write Tool 只會寫入本機 Sandbox outbox，畫面與 receipt 均會清楚標示沒有寄到外部信箱。

## 第五組組員與分工

| 學號 | 姓名 | 負責範圍 | 報告主講內容 |
| --- | --- | --- | --- |
| S11259013 | 羅暐媁 | 資料來源與 RAG：官方名錄、Source Card、資料清理與引用核對 | 問題定義、W1–W3、資料覆蓋 |
| S11259019 | 莊旻芳 | 互動與驗收：表單流程、Demo 腳本、失敗案例與證據整理 | Demo、測試、使用限制 |
| S11259029 | 李安以 | 後端與系統整合：工具契約、Gemini／框架／Routing、記憶與 Sandbox | 架構、W4–W7、後續計畫 |

分工依團隊指定的期中報告最終簡報第 25 頁同步，詳細說明見 [團隊分工](docs/midterm/team_contributions.md)。


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

本週 68 項 Python／localhost HTTP、22 組 JS VM 全通過；跨週非 HTTP 回歸 137 項，130 PASS、7 項選配 LangChain 依賴 skipped。兩份結果有重疊，不加總。語意與 AI 測試用明示替身，本週真實 Gemini／ADC 為 LIVE_NOT_RUN，畫面／備用錄影尚未驗證。W7 功能與證據已本機提交，candidate SHA 為 `967ee1ef8e484a41250688474dbcaba7c3139896`；尚未 push，遠端可見性待確認。

```powershell
python -W error::ResourceWarning scripts/run_week07_validation.py
python scripts/run_personal_memory_validation.py
python -W error::ResourceWarning scripts/run_week07_memory_demo.py
```

文件採歷週格式：[本週 README](docs/week07/README.md)／[記憶決策與版本紀錄（含 ADR／前後比較）](docs/week07/memory_adr.md)／[驗收](docs/week07/acceptance.md)／[Evidence Index](docs/week07/evidence_index.md)／[提交檢核](docs/week07/submission_checklist.md)。啟動、Key 設定、操作與補驗證計畫均由本週 README 索引。

## 本機 UI 原型

目前提供本機 Web UI，可查詢全校官方名錄與已收錄教師，透過分層表單產生 Email 草稿，並在人工確認後執行 Sandbox Write Tool。選擇 Email Agent →「學系」→「電機工程學系」→「盧陽明」，再填自己的姓名、目的、系所、年級與詢問內容。收件系所不會自動當成寄件人的系所。Manual 執行不需第三方套件；LangChain 候選版需安裝 Week 05 依賴。兩種後端都不會實際寄送郵件。

```bash
python3 app.py
```

啟動後開啟 `http://127.0.0.1:8000`。未安裝 Week 05 依賴時可執行基礎測試；LangChain 測試會明確標示為 skipped：

```bash
python3 -m unittest discover -s tests -v
```

安裝 Week 05 依賴後，可執行完整跨週測試（本次 184 項），以及前端狀態測試：

```bash
.venv/bin/python -W error::ResourceWarning -m unittest discover -s tests -v
node tests/test_week07_ui.cjs
node tests/test_campus_conversation_ui.cjs
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
