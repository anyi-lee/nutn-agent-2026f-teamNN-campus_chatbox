# Week 06 Evidence Index

## 可重現證據

| 證據 | 位置 | 狀態 |
| --- | --- | --- |
| Router prompt 與結構化 schema | `src/gemini_router.py` | IMPLEMENTED |
| Host Route Gate 與停止條件 | `src/campus_service.py` | IMPLEMENTED |
| UI 路由軌跡 | `ui/app.js` | IMPLEMENTED |
| 四類案例與邊界測試 | `tests/test_week06_routing.py` | WEEK06_OFFLINE_PASS |
| 固定驗收腳本 | `scripts/run_week06_comparison.py` | WEEK06_OFFLINE_PASS |
| 離線輸出 | `evidence/week06_offline_routing_2026-10-27.log` | WEEK06_OFFLINE_PASS |
| 正常教師路由 Live 截圖 | `evidence/week06_routing_faculty_live_pass.png` | LIVE_PASS |
| 多意圖澄清 Live 截圖 | `evidence/week06_routing_clarify_live_pass.png` | LIVE_PASS |
| Gemini Email 草稿截圖 | `evidence/week06_email_live_draft.png` | LIVE_PASS |
| Sandbox Write Tool 截圖 | `evidence/week06_sandbox_write_pass.png` | SANDBOX_PASS |
| Live 證據說明 | `evidence/week06_live_routing_2026-10-27.md` | LIVE_PASS |
| 前後比較 | `docs/week06/before_after.md` | DOCUMENTED |
| Workflow ADR | `docs/week06/workflow_adr.md` | DOCUMENTED |

## 執行軌跡欄位

每次 Routing response 會輸出：

- `run_id`
- `provider` 與 `model`
- `route` 與 `reason_code`
- `stages[]`：proposal、gate、dispatch 狀態
- `stop_reason`
- `live_status`

證據不保存 API Key、個人私密資料或模型內部推理。

## Live 驗證結果

Gemini Router 已完成兩筆 Live 驗證：

- 正常案例：`林朝興老師的研究領域` → `faculty_query` → `LIVE_PASS`，並通過 BM25 Evidence Gate。
- Workflow 邊界：同時查詢教師研究與系辦時間 → `clarify` → `LIVE_PASS`，沒有執行 BM25 下游。

Provider failure、無效輸入與未知 route 由可重現離線測試驗證。Sandbox Write Tool 另有 `SANDBOX_PASS` 證據，且 `real_email_sent: false`。
