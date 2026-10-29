# Week 07 Acceptance Matrix

更新：2026-10-29；A 路線；baseline `6bbd34f`／candidate `WORKING_TREE`。預期與實際分列，離線模型替身／故障注入不作 Live。

## 本次執行

| 範圍 | 命令 | 實際結果 |
| --- | --- | --- |
| 本週完整切片 | `python -W error::ResourceWarning scripts/run_week07_validation.py` | 68／68 Python PASS，0 skipped；含兩項 localhost HTTP；22 組 JS VM PASS |
| 跨週非 HTTP | `python scripts/run_personal_memory_validation.py` | 137 項：130 PASS、7 LangChain 依賴 skipped；相同 22 組 JS VM PASS |
| A 流程示範 | `python -W error::ResourceWarning scripts/run_week07_memory_demo.py` | in-process PASS；保存多筆、重啟登入讀回、跨帳號拒絕、撤回後舊草稿不能送出 |

本週 run ID `week07-069fc5f5d0174cf1bfd884529f1641ad`；回歸 run ID `week07-review-e06bdb3b9dcd49e985b12c24bb7d6c1c`。程式／資料指紋及 raw logs 見 [證據索引](evidence_index.md)。

本週切片＝帳號 12＋session 16＋完整草稿 8＋AI 調整 6＋個人事實 12＋語意規劃 14。非 HTTP 回歸明確排除的兩項 HTTP 已在本週切片實跑；兩份結果有重疊，不相加宣稱測試數。

## 固定案例與判準

測試使用隔離官方資料副本、合成帳號、私有臨時 SQLite；chat baseline、Email manual 本機模板；語意及 AI 部分注入明示模型替身。下列為 16 組交付案例摘要，不等於僅執行 16 個 test methods。

| ID／適用 | 預期結果 | 本次實際與測試來源 |
| --- | --- | --- |
| C01 正常主流程 | 官方教師查詢→草稿→確認→Sandbox receipt，工具與摘要一致 | PASS；`test_c01_followup_draft_confirm_and_replay`，收件人來自官方，重送不新增 |
| C02 跨 user | 另一人不可讀、改、刪、引用或寄出本人的記憶／草稿 | PASS；Account `a02`、Session `c02`、Personal `candidate_bound_to_account_and_reset` |
| C03 非法／越界輸入 | 未登入、壞 schema、偽造 owner／內容及 CSRF 拒絕 | PASS；Account `a09`、Session `session_and_csrf_are_required`、Templates `t03`／`t05` |
| C04 有限失敗 | 缺模型／503／壞 JSON／模型越權 ID 停止或明示降級，不偽造成功 | PASS；Revision `r02`／`r04`、Semantic `unowned_id_and_fabricated_value_are_rejected`／`malformed_model_json_is_rejected` |
| C05 來源更新 | v2 生效，撤回／損壞資料不能沿用舊教師／草稿 | PASS；Session `c05` 及 `corrupt_source_fails_closed_then_recovers` |
| C06 in-flight | 新對話、換身分或更正／撤回後，晚到結果不回填 | PASS；Account `a06`、Revision `r05`、Semantic `reset_wins_during_semantic_model_work`／`memory_version_is_rechecked_after_model_returns` |
| A01 保存與新 session | 確認保存多筆；新對話、登出登入與重啟讀回原 IDs | PASS；Account `a01`、Personal `restart_read_and_delete`、流程示範 |
| A02 更正 | 個人同義更正指向原 ID；顯示原／新值，確認後只讀新版 | PASS；Personal `overwrite_same_key_and_keep_other_facts`、Semantic `semantic_update_preserves_same_key_until_confirmation` |
| A03 撤回／舊版本 | 撤回讀不到；舊版本或競態保存 409，舊草稿不能寫出 | PASS；Account `a04`、Personal `conflict_requires_new_preview`／`restart_read_and_delete` |
| A04 回填用對 | 模型只收允許資料，不帶帳密／未選 Email 記憶；個人來源不冒用官方 | PASS；Account `a05`、Semantic `transport_uses_structured_schema_and_only_personal_facts` |
| A05 自然語意 | 非固定句型可提出候選、查用或釐清；模型不自動維護 DB | OFFLINE DOUBLE PASS；Semantic `natural_statement_has_proposal_but_no_automatic_write`／`semantic_recall_does_not_require_same_words`／`ambiguity_does_not_change_memory`；真實 Gemini NOT_RUN |
| A06 官方對象 | 用個人關係找官方教師；未知教師停止，當前明確教師優先 | PASS；Personal `teacher_reference_uses_official_query`／`unresolved_teacher_never_reuses_previous_teacher`、Semantic `current_explicit_teacher_is_not_overridden_by_memory` |
| A07 完整草稿 | 來源須本人有效草稿；重用逐字保留、新 ID、新寄送確認 | PASS；Templates `t07`／`t08`，不呼叫模型；公版與表單保存入口已移除 |
| A08 Email 續編與改寫 | 關閉重開保留修改／指示；API 失敗保留介面；切換後舊生成不覆蓋；可辨識署名不能被 AI 丟失／換名 | PASS；JS VM 對應情境、Revision `r06`；未辨識署名仍須人工檢查 |
| W01 寫入未授權 | 未確認不存記憶／不寫 Sandbox；訪客與跨 owner 拒絕 | PASS；Account `a03`／`a09`、Personal `guest_cannot_collect_or_save`／`explicit_confirmation_and_replay`、Session `w01` |
| W02 同 ID 重送 | 同 operation／request ID 不新增副作用；不同內容撞 ID 拒絕 | PASS；Account `a03`、Personal `explicit_confirmation_and_replay`、Session `c01`／`w02` |

測試檔：[accounts](../../tests/test_week07_account_memory.py)、[sessions](../../tests/test_week07_sessions.py)、[templates](../../tests/test_week07_templates.py)、[revisions](../../tests/test_week07_revisions.py)、[personal](../../tests/test_week07_personal_memory.py)、[semantic](../../tests/test_week07_semantic_memory.py)、[JS VM](../../tests/test_week07_ui.cjs)。

## 三層結果與未測項目

1. 讀對：owner、ID、版本、撤回與官方來源有測試；無跨帳號共享或 embedding。
2. 用對：已選段落、語意規劃及改寫以 Spy／模型替身驗證契約；不證明真實模型一定理解所有自然說法。
3. 完成：保存／讀回／覆蓋／撤回及 Sandbox 終點有離線證據。另存不等於寄送；直接引用不代表執行了模型。

B 事件問答、D 角色共享及 TTL 路線測試為 N/A：本週只選 A；session 清除另作安全回歸。真實 Gemini、Cloud／ADC、瀏覽器畫面／備用錄影、tokens／Live latency 均為 NOT_RUN／NOT_MEASURED。使用者曾回報 503，但未有版本／日期綁定的完整 trace，因此不移作本週 LIVE_FAIL 證據。

2026-10-29 檢查中新增的 `r06` 與 JS 晚到覆蓋案例，修正前均重現失敗、修正後通過。既有跨週缺口仍未修正：ADC、W06 嚴格分派、W03 多證據、原工具型別與來源 Gate、W04 逾時查狀態；不以 W7 測試通過宣稱全專案無缺失。
