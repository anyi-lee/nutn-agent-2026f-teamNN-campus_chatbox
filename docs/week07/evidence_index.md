# Week 07 Evidence Index

更新：2026-10-29（Asia/Taipei）；A 路線；baseline `6bbd34f`，candidate `967ee1ef8e484a41250688474dbcaba7c3139896`。功能與證據已本機 commit、未 push。測試原始 metadata 的 WORKING_TREE 是執行當時狀態，不補造新執行；受測程式指紋已與提交候選核對一致。最新證據和歷史階段分開。

## 本次可用證據

| 項目 | 檔案 | 日期／結果／範圍 |
| --- | --- | --- |
| 本週完整驗收 metadata | [week07_offline_sessions.json](../../evidence/week07_offline_sessions.json) | 2026-10-29；run `week07-069fc5f5d0174cf1bfd884529f1641ad`；68／68、0 skipped、JS 22 PASS；含 code hashes |
| Python／localhost HTTP raw log | [week07_offline_sessions.log](../../evidence/week07_offline_sessions.log) | 68 個 test methods；2 項實際 localhost HTTP；非 Gemini 網路請求 |
| JS VM raw log | [week07_ui_vm.log](../../evidence/week07_ui_vm.log) | 22 組實際 app.js 狀態測試；不是瀏覽器視覺 |
| 跨週非 HTTP 回歸 metadata | [week07_personal_memory.json](../../evidence/week07_personal_memory.json) | 2026-10-29；run `week07-review-e06bdb3b9dcd49e985b12c24bb7d6c1c`；137 項，130 PASS、7 LangChain 依賴 skipped；code／data hashes |
| 跨週回歸／JS raw log | [Python](../../evidence/week07_personal_memory_offline.log)／[JS](../../evidence/week07_personal_memory_ui.log) | 與本週切片重疊，不加總；此 runner 排除的兩項 HTTP 已由本週 runner 實跑 |
| A 路線合成示範 | [week07_memory_demo.json](../../evidence/week07_memory_demo.json) | 2026-10-29；保存兩筆→新對話→重啟登入→套用→跨帳號拒絕→撤回→舊草稿停止；in-process PASS |
| 操作流程及判準 | [驗收矩陣](acceptance.md)／[語意記憶](personal_memory.md)／[Email](template_manual_test.md) | 測試預期與實際分開；手動步驟不當作已執行證據 |

語意／AI 正常、503、故障注入、壞 schema 與競態測試均使用明示替身。測試中的 LIVE_FAIL 是模擬分支結果，不是課程的外部模型 Live 紀錄。

## 目前未完成的證據

| 項目 | 狀態 | 補驗證方式 |
| --- | --- | --- |
| W7 真實 Gemini 記憶及 Email 工具往返 | LIVE_NOT_RUN | 固定 candidate SHA／model／backend／來源 hash，使用合成資料測正常＋更正／失敗，保存去識別化 trace |
| Google Cloud／ADC | 未接入／LIVE_NOT_RUN | 建立課程允許的後端認證接頭，實跑 Gemini→Read Tool→結果回模型→草稿，不以 Developer API Key 冒充 |
| UI 畫面／備用錄影 | NOT_VERIFIED | 同版登入、候選勾選、更正、新對話查用、草稿重用及失敗保留畫面；標示日期與版本 |
| tokens／Live latency | NOT_MEASURED | 以同條件的真實執行量測，不從 fixture 或畫面推估 |
| Candidate commit／教師可存取 | 本機 COMMITTED／遠端 PENDING | 功能與證據 SHA `967ee1ef8e484a41250688474dbcaba7c3139896`；尚未 push，未確認教師權限 |

使用者回報的 Gemini 503 沒有候選 SHA、完整 trace 與錄製日期，故不在此補造 LIVE_FAIL；W04–06 歷史 Live 也不移作 W7 Live。

## 歷史階段，不能取代本次指紋

| 紀錄 | 檔案／用途 |
| --- | --- |
| 早期 session HTTP 前後比較 | [week07_before_after.json](../../evidence/week07_before_after.json)；只載入舊 app.py，限制見比較文件 |
| 早期全回歸 | [week07_regression.log](../../evidence/week07_regression.log)；99 項／92 PASS／7 skipped |
| 草稿另存階段摘要 | [week07_templates_regression_summary.json](../../evidence/week07_templates_regression_summary.json)；112 項／105 PASS／7 skipped |
| API 錯誤保留介面 | [week07_ui_error_preservation.json](../../evidence/week07_ui_error_preservation.json)；當時 16 組 VM，當時未獲准 HTTP 重驗；不是目前限制 |
| 續編助手 | [week07_ui_draft_resume.json](../../evidence/week07_ui_draft_resume.json)；當時 18 組 VM |
| 個人記憶首次沙盒嘗試 | [metadata](../../evidence/week07_personal_memory_sandbox_attempt.json)／[log](../../evidence/week07_personal_memory_sandbox_attempt.log)；Windows 暫存目錄權限失敗，後來獲准重跑；不能列 PASS |

以上保留原執行日期與內容，不改寫舊證據冒充新版成功。全部測試資料為合成帳號、隔離來源與臨時 DB；不提交 API Key、Cookie、CSRF、私人 runtime DB 或模型內部推理。
