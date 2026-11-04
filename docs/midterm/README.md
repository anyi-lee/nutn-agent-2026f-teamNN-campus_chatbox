# 第五組期中報告

報告日期：2026-11-04。專題：南大校務通 - 校園辦事導航與 Email Agent。

- [期中報告最終簡報 PDF（28 頁）](final_2026-11-04/NUTN_Campus_Agent_Midterm_Team05_2026-11-04.pdf)
- [團隊分工與後續計畫](team_contributions.md)
- [證據索引](evidence_index.md)
- [PDF 版本與檔案指紋](final_2026-11-04/version_manifest.json)

## 交付版本

系統程式版本：[`4d7469e0cb6fcba9e0827f122d48b8436bd7703e`](https://github.com/anyi-lee/nutn-agent-2026f-teamNN-campus_chatbox/commit/4d7469e0cb6fcba9e0827f122d48b8436bd7703e)。

最終簡報以團隊於 2026-11-04 提供的 Canva 匯出 PDF 為準，共 28 頁，不是先前的 17／24 頁草稿。保留既有版型、流程圖與 Demo 畫面，更新第 1 頁為「第五組」、第 25 頁標題為「團隊分工」，並將第 28 頁過期的「尚未 commit／push」改成已提交的系統程式版本。PDF metadata 與檔名均標示「期中報告」。其他 25 頁的內容串流保持不變。

簡報與交付文件的版本可由 GitHub 上最後修改該 PDF 的 commit 查得；程式版本與簡報提交版本分開記錄。來源與最終 PDF 的 SHA-256 見版本檔。

只提交這份最終 PDF 與相關交付資料。舊草稿及其 PPTX 未作為本次最終簡報上傳；不把舊版 PPTX 誤稱為這份 28 頁 Canva 版的可編輯來源。

## 目前配置與驗證界線

預設聊天為 `baseline`（名錄匹配／BM25／Evidence Gate），Email 為 `manual` + Gemini。LangChain 與 Routing 是可切換候選，不能把週次架構圖當作所有候選已在目前主流程啟用。

207 項 Python／HTTP、另 10 項維護解析器、22＋25 組 JS VM 是 2026-11-03 的回歸證據。Email 草稿與 AI 修改有同日真實 Gemini `LIVE_PASS`；Sandbox 回執只表示本機模擬操作完成，不表示外寄郵件。本次 2026-11-04 文件發布沒有重新執行模型，也沒有寄信。

Google Cloud／ADC 主流程仍待補。API Key 的成功不能代替 ADC；個人記憶畫面徽章也不能單獨代替具日期、版本和 trace 的端到端驗證。其他缺口與補驗證計畫見證據索引。

## 安全與 AI 使用說明

不提交 API Key、ADC 憑證、權杖、私人資料庫或瀏覽器 Cookie。教學與測試案例中的寄件人使用合成資料，教師聯絡資訊引用官方公開來源。所有 Write 維持課程 Sandbox。

使用 AI 協助開發、測試、文件與簡報整理。團隊須理解、核對並能解釋提交內容；資料與程式來源詳見各週文件、Source Card 與證據索引。
