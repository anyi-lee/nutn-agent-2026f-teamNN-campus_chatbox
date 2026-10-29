# Week 06 Before / After

## 比較基準

- Before：`e83196d`，條件式 Baseline。
- After：`12ab574`，Routing candidate。離線 log 中的 `e83196d-WORKTREE` 是 commit 前的實測版本標記。
- Offline fixture：不呼叫 Gemini，狀態為 `LIVE_NOT_RUN`。
- Live evidence：Gemini `gemini-3.5-flash` 的 `faculty_query` 與 `clarify` 均為 `LIVE_PASS`。
- 固定檢索器：BM25；資料來源與 Evidence Gate 兩版相同。

## 固定案例

| 類型 | 固定輸入／條件 | Before | After | 結果 |
| --- | --- | --- | --- | --- |
| 正常 | `林朝興老師的研究領域` | 直接進 RAG | `faculty_query → Route Gate → RAG` | PASS |
| 無效輸入 | 空白字串 | 回傳 `EMPTY_MESSAGE` | Input Gate 停止，Router 0 次、RAG 0 次 | PASS |
| Provider 失敗 | Router 丟出 provider error | Baseline 無 Router | 回傳 `ROUTER_PROVIDER_FAILED`，下游 0 次 | PASS |
| Workflow 邊界 | `查林老師研究領域，順便寫信問系辦時間` | 可能因「系辦」先命中單一規則 | `clarify`，下游 0 次 | PASS |
| 未知路由 | Router 提出 `weather_tool` | Baseline 無 Route Gate | Host 拒絕 `ROUTE_DECISION_INVALID` | PASS |
| 第二分支 | `資工系辦電話和地址` | 官方資料分支 | `office_query → official_record` | PASS |
| Email 分支 | `幫我寫信給林朝興老師詢問加簽` | RAG 後顯示草稿入口 | `email_request`，先 grounding 再顯示入口 | PASS |
| 重送／冪等 | 同一草稿、相同 `request_id` 確認兩次 | 第二次 `already_processed` | Write Tool 未改，結果相同 | PASS |

## 呼叫與量測

| 指標 | Before | After fixture | 備註 |
| --- | --- | --- | --- |
| 正常案例 Router model calls | 0 | 1 次 fixture | fixture 不算 Live model call |
| 正常案例下游 branch | 1 | 1 | 固定案例已驗證；任意輸入的分派一致性仍待修正，本表未涵蓋所有輸入 |
| `clarify` 下游 calls | 不保證為 0 | 0 | 由測試計數確認 |
| Live latency | 未量測 | 未提供 | Live 畫面未顯示 latency，不自行推測 |
| Token usage | unavailable | unavailable | 離線 fixture 無 token 資料 |
| 真實 Email | 0 | 0 | 僅 Sandbox |

離線切片 8/8 PASS；使用專案 `.venv` 執行完整回歸為 71/71 PASS、0 skipped。另以系統 Python 驗證時，同樣 71 項中有 7 項因未安裝 Week 05 LangChain 依賴而明確 skipped。

Live 驗證結果：正常教師查詢被路由到 `faculty_query`，完成 BM25 與 Evidence Gate；教師查詢加系辦查詢的多意圖輸入被路由到 `clarify`，畫面沒有執行 BM25 下游。兩個案例均顯示 `LIVE_PASS`。
