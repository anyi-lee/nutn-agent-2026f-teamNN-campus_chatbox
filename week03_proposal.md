# Week 03 Retrieval Proposal

## 專題題目

**NUTN Campus Chatbot：資工系教師資訊檢索與 Email 草稿產生**

組員：S11259013 羅暐媁、S11259019 莊旻芳、S11259029 李安以

提案狀態：原型與評估已完成。

## 使用者與問題情境

想聯絡資工系教師的學生，可能只知道教師姓名或研究方向，不熟悉教師的公開 Email、職稱與個人頁面，因此必須逐一搜尋系所網站。本功能讓學生輸入教師姓名與寄信目的，由系統先從資工系官方網站檢索並驗證教師資料，再根據取得的 Evidence 產生 Email 草稿。本週只產生草稿，不實際寄信。

## Claim Card

| 項目 | 定義 |
| --- | --- |
| 使用者 | 想查詢並聯絡資工系教師的學生 |
| Claim | 指定教師的姓名、職稱、研究領域與公開 Email，可由南大資工系官方教師頁面支持 |
| 外部 Evidence 的必要性 | 教師名單、職稱、研究領域與 Email 可能更新，不能依賴模型記憶或自行猜測 |
| 最小回答 | `teacher_name`、`title`、`research_areas`、`public_email`、`citation` |
| 成功後動作 | 使用查證後的 Email 與使用者需求產生郵件草稿，`send_status = not_sent` |

## 資料範圍

唯一允許的主要來源為國立臺南大學資訊工程學系官方「師資陣容」頁面：<https://csie.nutn.edu.tw/faculty>。

### In Scope

- 教師姓名、職稱、研究領域、公開 Email 與個人網站連結。
- 事先擷取並版本化的官方資料快照。
- 以教師為單位建立的 3–10 個 Stable Chunks。
- Normal、Paraphrase 與 No-answer 三種固定查詢。
- 教師資料回答與 Email 草稿產生。

### Out of Scope

- 資工系以外的教師與非官方資料來源。
- 未公開的 Email、電話、研究室時間或私人行程。
- 教師的即時狀態，例如「老師現在是否在研究室」。
- 登入信箱、實際寄信或代表教師做出承諾。

## Data Source 摘要

| 項目 | 決定 |
| --- | --- |
| `source_id` | `nutn-csie-faculty` |
| Owner／Authority | 國立臺南大學資訊工程學系官方網站 |
| Freshness | 擷取時記錄 `retrieved_at`；提交前重新確認官方頁面 |
| Update／Withdrawal | 頁面變更時建立新 `index_version`；資料移除時刪除 Chunk 並重新索引 |
| Conflict precedence | 官方教師頁面優先；官方欄位互相衝突時拒答並留下 Failure Log |

## Retrieval Baseline

採用透明且可重現的 BM25／Keyword Baseline，不讓 LLM 選擇 Evidence。

- 每位教師建立一個 Chunk，姓名、職稱、研究領域、Email 與 URL 保留在同一 Chunk。
- 每個 Chunk 保存 `source_id`、`chunk_id`、`source_url`、`retrieved_at`、`index_version`、`authority` 與 `validity`。
- `top_k = 3`。
- 保存 Query、Top-k Chunk IDs、Scores、Gold／Acceptable IDs、是否應拒答及可重現指令。
- Retrieval Score 只負責候選排序，不能直接證明 Claim 正確。

## Fixed Queries

| 類型 | Query | 預期結果 |
| --- | --- | --- |
| Normal | `林朝興教授的 Email 是什麼？` | Gold 教師 Chunk 出現在 Top-3 |
| Paraphrase | `我要怎麼聯絡林朝興老師？` | 找回與 Normal 相同的 Gold Chunk |
| No-answer | `林朝興教授今天幾點會在研究室？` | Evidence 不支持即時行程，系統安全拒答 |

Normal 與 Paraphrase 的 Gold Chunk ID 均為 `faculty-mikelin`；實際 Top-k Scores 與執行結果保存在 `artifacts/week03-initial-retrieval.json`。

## Evidence Gate 與拒答條件

候選 Evidence 必須依序通過 Category、Authority、Freshness、Identity Match 與 Claim Support。Citation 只能由通過 Gate 的 Selected Evidence 組裝，不允許 Generator 自行產生。

| 拒答條件 | `failure_code` |
| --- | --- |
| 找不到指定教師 | `TEACHER_NOT_FOUND` |
| 教師稱呼無法唯一對應 | `AMBIGUOUS_TEACHER` |
| 官方網站未公開 Email | `EMAIL_NOT_PUBLIC` |
| Evidence 不支持使用者問題 | `INSUFFICIENT_EVIDENCE` |
| 官方資料互相衝突 | `SOURCE_CONFLICT` |
| 資料版本失效 | `STALE_SOURCE` |

拒答時必須設定 `can_answer = false`，不產生無依據的 Citation 或郵件草稿。

## Generator Comparison

系統先凍結同一份 Selected Evidence，再比較 Offline 與 Gemini Fixture／Live。三條路徑不得改變 Route、Selected Evidence 或 Citation，並驗證：

- `same_selected_evidence = true`
- `same_citations = true`
- 必要事實完整
- `unsupported_claims = 0`
- `send_status = not_sent`

Gemini Live 為選配；使用 Fixture 時必須標示 `llm_actually_called = false`。

## 本週成功標準與交付

- Normal 與 Paraphrase 的 Gold Chunk 均出現在 Top-3。
- No-answer 安全拒答，Citation 與郵件草稿皆為空。
- 所有姓名、研究領域與 Email Claim 都能回到 Selected Evidence。
- 交付 Proposal、完整 Source Card、3–10 個 Chunks、三個 Fixed Queries、Top-k Trace、Generator Comparison JSON 與至少一個 Failure Observation。

## 證據狀態

**Proposal、資料快照、Chunks、Initial Retrieval Trace 與 Generator Comparison 已在目前工作目錄完成。**

目前已產生：

- `artifacts/week03-initial-retrieval.json`
- `artifacts/week03-retriever-comparison.json`
- `artifacts/week03-generator-comparison.json`

另已完成本機 Web UI、對話教師脈絡、Scope Gate、Gemini System Instruction 與低品質草稿 Gate。
