# Week 07 Submission Self-check

更新：2026-10-29（Asia/Taipei）。題目：校務問答與 Email 助手；A 路線。此頁沿用 W04 自檢與 W06 交付索引形式，區分 W7 共同交付、A 路線驗收及期中追加要求。工程通過、資料已備齊、遠端已繳交分別記錄。

## 版本與交付索引

- Repository：[campus_chatbox](https://github.com/anyi-lee/nutn-agent-2026f-teamNN-campus_chatbox)
- Baseline：`6bbd34f369a40b5a2a46534e881197bddfcfea01`。
- Candidate SHA：`967ee1ef8e484a41250688474dbcaba7c3139896`（功能及證據）；已本機 commit，未 push。後續文件補記與本次受測程式分開辨識。
- 本週 run ID：`week07-069fc5f5d0174cf1bfd884529f1641ad`；日期、條件與指紋見 [metadata](../../evidence/week07_offline_sessions.json)。

| 交付項目 | 位置 | 狀態 |
| --- | --- | --- |
| 本週目標、路線、啟動與流程 | [README](README.md) | 已對齊 W06 格式，包含模型／一般程式責任及停止條件 |
| ADR 決策摘要 | [統一版本紀錄](memory_adr.md#決策摘要adr) | 開頭集中說明缺口、選擇、理由、代價及採用狀態 |
| 記憶分層、固定條件與三層比較 | [同份版本紀錄](memory_adr.md) | 與適用原因、前後差異寫在一起；舊比較檔保留為導向入口 |
| 正常／邊界、跨 user、W01／W02 | [驗收矩陣](acceptance.md) | 16 組摘要；68 項 Python／HTTP、22 組 JS VM PASS |
| 執行證據與版本索引 | [Evidence Index](evidence_index.md) | 最新／歷史／待驗證分開；raw log、run ID、code hash 可追溯 |
| 語意記憶與草稿操作 | [個人記憶](personal_memory.md)／[Email](template_manual_test.md) | 已提供手動判準；步驟本身不算 Live 或畫面證據 |
| 本週版本的真實 Gemini 證據 | [補驗證計畫](evidence_index.md) | LIVE_NOT_RUN；離線替身、舊週 Live 或未綁版本的 503 回報均不能取代 |
| 實際 UI／trace | [證據索引](evidence_index.md) | NOT_VERIFIED；需呈現需求→call→驗證／批准→result→response／摘要，標示日期與版本 |
| Candidate SHA、遠端存取與教師權限 | `967ee1ef8e484a41250688474dbcaba7c3139896` | 本機 COMMITTED；尚未 push，遠端及教師權限 PENDING |

## 工程檢查

本週 68／68、0 skipped；跨週非 HTTP 137 項中 130 PASS、7 項選配 LangChain 依賴 skipped。後者排除的兩項 HTTP 已在本週切片重驗，結果有重疊不加總。原固定教師／工具／Sandbox 流程回歸通過。

本輪先重現後修正兩項 W7 問題：AI 丟失／替換可辨識來源署名；切換草稿後晚到生成覆蓋新畫面。原「關閉再開可續編」仍通過。非中文或無法辨識的原署名仍需人工檢查。

歷週已知缺口仍未修正：ADC、W06 嚴格分派、W03 多證據、原工具型別與來源 Gate、W04 逾時查狀態。本輪未擴大修正，也不宣稱整個專案沒有缺失。本機架構調查、跨週盤點與內部審查檔案不列為課程交付。

## 實際繳交範圍

### 必要內容與檔案安排的區別

W7 投影片規定交付內容，沒有指定必須建立以下每一個 Markdown 檔名。先前把版本補記的 8 份文件一律說成獨立必交，並不精確；本清單區分如下。

| 性質 | 投影片／歷週依據 | 本專題安排 |
| --- | --- | --- |
| 必要：題目、路線、版本、修改位置及可重現流程 | W7 PDF 實際頁序 77、88；W6 使用 README 作入口 | 根 README／W7 README 提供入口；不代表教師要求兩份獨立 README |
| 必要：一頁 ADR、程式差異與比較 | W7 PDF 80、86–88；W5 決策紀錄，W6 workflow_adr／before_after | 依使用者要求集中於 `memory_adr.md`；`before_after.md` 僅保留導向，不重複內容 |
| 必要：預期／實際測試、路線邊界、命令及 run ID | W7 PDF 80、85、88；W6 有固定比較案例 | `acceptance.md` 整理矩陣；內容必要，但檔名與獨立成檔不是指定要求 |
| 必要：真實 Gemini、UI／trace、證據索引、狀態與缺口 | W7 PDF 80、88；W4–6 均有 evidence 檔與說明 | `evidence_index.md` 連結實際紀錄；目前 Live／視覺缺口仍未補齊 |
| 補充：詳細個人記憶契約與操作 | 內容支援理解及重現，不是歷版固定同名交付 | `personal_memory.md` 可保留作詳細說明，也可整合回 README／決策紀錄 |
| 補充：自檢清單 | W4 有 self-check 的先例；W7 未指定這個檔名 | 本 `submission_checklist.md` 是整理工具，不是額外獨立必交項 |
| 補充：草稿手動驗收步驟 | 重現步驟需要交代，但未要求獨立步驟檔 | `template_manual_test.md` 為補充操作文件，可與 README 合併 |

因此，不能說「歷週都有這 8 個檔案，所以 8 份全部獨立必交」。既有專案選擇保留的補充文件可以隨 Repository 提交，但不把檔案數或新增檔名當作課程要求。本輪只釐清分類，未刪檔、未新增提交。

以下功能、文件及證據已列入本機候選 commit；本文件同步補記實際 SHA。尚未 push，不表示 GitHub 已可見。

| 類別 | 預計提交內容 | 核對結果 |
| --- | --- | --- |
| 專案入口及排除規則 | 根目錄 `README.md`、`.gitignore` | W7 入口可讀；本機架構調查與私人 runtime 已排除 |
| W7 文件 | `docs/week07/README.md`、`memory_adr.md`、`before_after.md`、`acceptance.md`、`evidence_index.md`、`personal_memory.md`、`template_manual_test.md`、本清單 | 記憶種類／理由／前後差異集中於 `memory_adr.md`，`before_after.md` 僅作相容導向；連結可解析 |
| 產品程式 | `app.py`、`src/account_memory.py`、`src/session_host.py`、`src/personal_memory.py`、`src/campus_service.py`、`src/gemini_email.py`、`ui/app.js`、`ui/index.html`、`ui/styles.css` | 已有實作及對應受測指紋 |
| 重現腳本 | `scripts/run_week07_validation.py`、`run_personal_memory_validation.py`、`run_week07_memory_demo.py` | 本週驗收、非 HTTP 回歸及合成示範皆有執行紀錄 |
| W7 測試 | `tests/test_week07_account_memory.py`、`test_week07_sessions.py`、`test_week07_templates.py`、`test_week07_revisions.py`、`test_week07_personal_memory.py`、`test_week07_semantic_memory.py`、`test_week07_ui.cjs` | 68 項 Python／HTTP、22 組 JS VM 通過 |
| 本次主要證據 | `evidence/week07_offline_sessions.json`／`.log`、`week07_ui_vm.log`、`week07_personal_memory.json`、`week07_personal_memory_offline.log`、`week07_personal_memory_ui.log`、`week07_memory_demo.json` | 日期、run ID、條件及程式指紋存在；無真實 Gemini／視覺證據 |

`evidence_index.md` 另外列出的早期回歸、UI 修正、沙盒失敗及 session 比較是歷史佐證，不是本次必要成功證據；保留時維持原日期與限制，不冒充新版驗收。`run_week07_comparison.py` 也是歷史 session 比較重現腳本，不代表完整原版 checkout 的語意記憶比較。

`docs/week06/README.md` 與 `docs/week06/before_after.md` 目前有先前加入的限制補註；不是新增 W7 功能，也未改寫前週 Live 結果。提交時須將這兩份變更視為文件勘誤，不能當成 W7 的實測證據。

明確不提交：`docs/architecture/`、`evidence/architecture_review_*`、`evidence/week07_delivery_review.json`、`runtime/`、`.env`、API Key／ADC 憑證、Cookie／存取權杖及私人資料。本次僅依使用者指示作本機 commit，不執行 push。

## W7 尚待完成

1. 固定本週候選版本、model、backend 及來源，使用合成資料實跑真實 Gemini 正常流程與 A 路線邊界。保留工具／記憶回填及確認 trace；真實失敗保留錯誤，不以離線替身補成 LIVE_PASS。
2. 整理同版實際 UI／trace，呈現需求、call、驗證／批准、result、response 與摘要；目前只有 HTTP／in-process／JS VM，不能當成畫面證據。
3. 補齊可用的 calls／tokens／延遲量測，未測維持 NOT_MEASURED；baseline 新記憶比較目前是程式盤點，若未補完整原版同條件實測，維持既有限制說明。
4. 本次已依指示完成本機 candidate commit，並另外提交文件 SHA 補記，沿用 W6 作法；push 及教師遠端可見性仍需後續指示與確認。Git commit 不可能在自身內容預先寫自己的 SHA，故文件標示功能／證據 commit，而不是宣稱文件 commit 自行包含自己的 SHA。

W7 投影片允許受阻或未完成時提交程式、如實狀態及具體補驗證計畫；因此可以提交階段性成果，但不能記為全部功能或 Live 驗收通過。

## 期中另有的追加要求

以下來自期中報告要求，不與 W7 投影片最低交付混為同一份清單：

| 項目 | 目前狀態 |
| --- | --- |
| Google Cloud／ADC 後端實際呼叫 Gemini | 未接入／LIVE_NOT_RUN；目前 API Key 接頭不等同 ADC |
| 20 分鐘分組報告、簡報 PDF、組別／題目／姓名學號 | 尚未備妥可驗證的簡報與完整名單；本輪未代填 |
| 每位組員具體貢獻、進度、已知限制及期末驗收計畫 | 需團隊補充本人貢獻及確認內容 |
| 同報告版本的備用示範錄影或截圖 | NOT_VERIFIED；須標日期與版本，使用合成或去識別化資料 |

若同一次整理要涵蓋期中，需另補以上項目；本清單不因此把 W7 簡報 PDF 或 ADC 當作投影片當週額外指定的檔案格式。
