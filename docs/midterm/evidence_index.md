# 第五組期中報告證據索引

整理日期：2026-11-04（Asia/Taipei）。系統程式版本：`4d7469e0cb6fcba9e0827f122d48b8436bd7703e`。

- [期中報告最終 PDF（28 頁）](final_2026-11-04/NUTN_Campus_Agent_Midterm_Team05_2026-11-04.pdf)
- [來源／最終 PDF SHA-256](final_2026-11-04/version_manifest.json)
- [團隊分工與後續計畫](team_contributions.md)

## 正常、失敗與邊界案例

| 案例 | 執行日期／證據 | 結果與界線 |
| --- | --- | --- |
| Gemini 建立作業二草稿並改作業三 | 2026-11-03；[真實 API 紀錄](../../evidence/revision_identity_live_2026-11-03.json) | `LIVE_PASS`，無 fallback，收件人 ID／信箱／署名保留，仍需獨立確認；此 API 案例未寄送 |
| 完整本機回歸 | 2026-11-03；[提交前完整 log](../../evidence/prepush_validation_2026-11-03.log) | 207 Python／HTTP、另 10 維護解析器、22＋25 JS VM 通過；初跑沙盒 bind 限制與 lxml 缺少、後續重跑結果均保留 |
| AI 修改收件人守門 | 2026-11-03；[識別修正測試](../../evidence/revision_identity_tests_2026-11-03.log) | 只允許 Host 認定的同一完整姓名相容；不同人／不同所屬仍拒絕。替身測試不能當 Live |
| 舊草稿姓名相容與隔離 | 2026-11-03；[測試](../../evidence/legacy_draft_tests_2026-11-03.log)／[瀏覽器紀錄](../../evidence/legacy_draft_browser_2026-11-03.txt) | 相同姓名／同一官方信箱可重用，不同信箱須澄清，仍查帳號所有權與重新確認 |
| 寄出後重開預設表單 | 2026-11-03；[測試](../../evidence/email_reset_tests_2026-11-03.log) | 成功後重開清空；未寄出／失敗草稿保留；晚到回覆不能恢復已 reset 的狀態 |
| 跨系來源與分頁追查 | 2026-11-03；[來源稽核](../../evidence/faculty_sources_2026-11-03.json)／[限制說明](../faculty_source_audit.md) | 191 所屬／信箱關聯，182 組不同姓名／信箱，不代表全校師資完整覆蓋 |

## 瀏覽器端到端備用截圖

以下為 2026-11-03 實際操作、合成學生與訪客模式的完整流程。配置為 baseline 問答、manual Gemini `gemini-3.5-flash`、API Key transport；**不是 ADC**。圖片保留原始日期，不宣稱為 11/4 重跑。

1. [官方教師查詢，直接帶入寫信](demo_2026-11-03/01_lookup.jpg)
2. [填寫合成寄件人資料](demo_2026-11-03/02_email_form.jpg)
3. [真實 Gemini 草稿](demo_2026-11-03/03_gemini_draft.jpg)
4. [AI 修改作業三](demo_2026-11-03/04_revised_assignment3.jpg)
5. [獨立確認門檻](demo_2026-11-03/05_confirmation_gate.jpg)
6. [Sandbox 回執](demo_2026-11-03/06_sandbox_receipt.jpg)
7. [重開回預設](demo_2026-11-03/07_reopen_default.jpg)
8. [未知教師停止，不以系辦信箱代替](demo_2026-11-03/08_unknown_teacher_stop.jpg)

[瀏覽器操作紀錄](demo_2026-11-03/browser_demo_log.txt)。Sandbox Request ID：`mail-330933d345d74abdb9e29d26f434281c`，Message ID：`sandbox-6c7b5752aceb4ed9`。回執 `simulated_sent` 僅表示寫入本機 outbox，沒有對外寄信。未附新的示範影片，以實際截圖作備用。

最終 PDF 中另含團隊提供的帳號、記憶及週次 Demo 畫面。畫面保留於團隊最終版，但沒有另附日期／版本／trace 的畫面，不單獨提升成新的同版本 `LIVE_PASS` 證據。

## 狀態與補驗證

- `LIVE_PASS`：有實際模型呼叫及成功結果；本索引明確支持 Email 產生／修改。
- `LIVE_FAIL`：有實際呼叫但失敗，保留原錯誤，不以模板 fallback 成功掩蓋。
- `LIVE_NOT_RUN`：尚未執行該功能、配置或版本的真實模型驗證。
- `SANDBOX_PASS`：本機模擬 Write 完成，不能代表真實外寄。

待補：Google Cloud／ADC 主流程、語意記憶候選的同版完整紀錄、LangChain 候選同版 Live、Routing 嚴格單分支及避免二次分流的同版品質驗證。需記錄版本、日期、配置、正常及失敗案例後再更新狀態。簡報的流程示意不代表當前 baseline 問答每次均呼叫 LLM。
