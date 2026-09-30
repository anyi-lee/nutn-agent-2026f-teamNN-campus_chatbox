# Week 03 Data Source Card

## 1. 基本資料

| 項目 | 內容 |
| --- | --- |
| `source_id` | `nutn-csie-faculty` |
| 資料名稱 | 南大資工系師資陣容 |
| Owner | 國立臺南大學資訊工程學系 |
| Authority | 資工系官方網站 |
| 原始 URL | <https://csie.nutn.edu.tw/faculty> |
| 資料類型 | 官方公開教師資料 |
| 介面形式 | HTML 網頁 |
| 預計更新方式 | 定期重新擷取並建立版本化快照 |
| 本次擷取日期 | `2026-09-30` |
| 初始版本 | `faculty-index-v1` |

## 2. 資料用途

本資料來源用於回答資工系教師相關問題，包括：

- 教師姓名
- 職稱
- 研究領域
- 公開 Email
- 教師個人網站
- 系所網站上的其他公開職務資訊

系統會使用檢索結果確認教師身分與公開聯絡方式，再根據使用者需求產生 Email 草稿。

## 3. 資料欄位

每位教師的資料整理為以下結構：

```json
{
  "source_id": "nutn-csie-faculty",
  "chunk_id": "faculty-<stable-id>",
  "teacher_name": "<教師姓名>",
  "title": "<職稱>",
  "research_areas": [
    "<研究領域>"
  ],
  "public_email": "<公開 Email>",
  "source_url": "https://csie.nutn.edu.tw/faculty",
  "retrieved_at": "2026-09-30",
  "index_version": "faculty-index-v1",
  "authority": "official",
  "validity": "active"
}
```

## 4. Chunking 規則

- 每位教師建立一個 Chunk。
- 教師姓名、職稱、研究領域與 Email 必須保留在同一個 Chunk。
- 不將姓名與 Email 分割到不同 Chunk。
- `chunk_id` 應保持穩定，不因重新排序教師名單而改變。
- 建議使用教師姓名或穩定識別碼建立 `chunk_id`。
- 每個 Chunk 必須保留原始 URL、擷取日期與索引版本。

範例：

```text
chunk_id: faculty-mikelin
姓名：林朝興
職稱：教授兼系主任
研究領域：AI 神經網路及應用、深度學習、多媒體內容分析辨識與生成、
媒體串流與編碼技術、行動普適計算、物聯網
Email：mikelin@mail.nutn.edu.tw
Source：https://csie.nutn.edu.tw/faculty
```

## 5. Freshness 與有效性

- 每次擷取資料時記錄 `retrieved_at`。
- 每次建立索引時記錄 `index_version`。
- 正式展示或提交前，重新確認官方頁面是否更新。
- 官方頁面仍存在且教師資料仍列於頁面時，設定 `validity = active`。
- 找不到教師、頁面失效或資料已被移除時，設定 `validity = inactive`。
- `inactive` 的 Chunk 不得進入 Selected Evidence。

## 6. 更新與重新索引

發生以下情況時，必須重新擷取資料並建立新版本：

- 教師名單增加或刪除
- 教師職稱變更
- Email 變更
- 研究領域更新
- 個人網站連結變更
- 官方教師頁面結構改版

更新流程：

```text
重新擷取官方頁面
→ 比較新舊資料
→ 更新或刪除對應 Chunk
→ 建立新 index_version
→ 重新執行三個 Fixed Queries
→ 保存新的 Retrieval Trace
```

## 7. 資料撤回

如果教師資料從官方頁面移除：

- 將對應 Chunk 標記為 `inactive`。
- 從 Active Index 中移除。
- 建立新的 `index_version`。
- 不再使用舊資料回答問題。
- 保留必要的版本與變更紀錄，但不繼續顯示已撤回的聯絡資訊。

## 8. 來源衝突處理

若資料來源出現衝突：

1. 以資工系官方師資頁面為主要依據。
2. 不使用搜尋引擎摘要取代官方頁面。
3. 不使用社群網站或非官方資料補充 Email。
4. 官方頁面內部欄位互相衝突時，停止回答。
5. 回傳：

```json
{
  "can_answer": false,
  "failure_code": "SOURCE_CONFLICT",
  "citations": []
}
```

## 9. PII 與資料保存

- 只保存官方網站公開的職務資訊。
- 不保存私人 Email、手機、住址、個人行程或未公開資料。
- 不保存學生輸入的敏感內容至教師資料索引。
- 教師資料只保留目前使用的 Active Version，以及必要的版本變更紀錄。
- Email 草稿中的學生資料不得寫入教師 Retrieval Corpus。

## 10. 已知限制

- 官方網站內容可能不是即時更新。
- 研究領域的寫法可能與學生使用的自然語言不同。
- 只有姓氏或「老師」等模糊稱呼可能對應多位教師。
- 官方頁面未提供的資訊不能透過 RAG 推測。
- 本資料來源無法回答教師即時位置、行程或是否願意加簽等問題。

## 11. 證據狀態

**Data Source Card 初稿與教師資料 JSON 已完成；Retrieval Index 與資料更新流程尚未正式部署。**

目前已有：

- `data/faculty_chunks.json`
- 8 個教師 Chunks
- `faculty-index-v1`
- 固定資料來源與 Metadata

後續仍需補上正式擷取指令、網站變更差異紀錄與重新索引操作紀錄。
