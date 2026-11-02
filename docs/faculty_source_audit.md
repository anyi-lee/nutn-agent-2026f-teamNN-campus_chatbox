# 全校師資連結追查與補收錄

日期：2026-11-02～2026-11-03（Asia/Taipei）。基準 `65a8517`＋未提交工作樹。

## 修正範圍

先前只從部分系所入口取得資料，不能據此判定其他系沒有教授信箱。這次逐一使用使用者提供的 16 個入口，沿官方專任名錄、個人頁及分頁追查；部分入口本身是某一位老師的頁面，因此也向同站師資分類追查其他教師。

新增 **147 筆教師／系所／公開信箱關聯**，不是 147 位互不重複的老師。加上原有資料後為 **191 筆所屬關聯、182 組不同姓名／信箱、23 個單位窗口**。22 個教學單位中，21 個已有至少一筆教師收件資料；仍不宣稱全校所有教師已完整收錄。原國文系 10 位教師、資工及其他已驗證資料保留。

## 逐系結果

| 系所／學程 | 新增已驗證教師收件關聯 | 入口及實際追查頁數 |
| --- | ---: | --- |
| 教育學系 | 20 | [官方入口](https://edu.nutn.edu.tw/gac610/mode02.asp?m=20170215093229514&t=list)；6 頁 |
| 特殊教育學系 | 8 | [官方入口](https://sped.nutn.edu.tw/sped/about/detail.php?apx=12&ap=9)；9 頁 |
| 幼兒教育學系 | 8 | [官方入口](https://ece.nutn.edu.tw/teacherfulltime.aspx)；3 頁 |
| 體育學系 | 9 | [官方入口](https://phyedu.nutn.edu.tw/faculty_category/full-time-teacher-zh)；1 頁 |
| 諮商與輔導學系 | 9 | [官方入口](https://cg.nutn.edu.tw/teacherfulltime.aspx)；2 頁 |
| 文化與自然資源學系 | 7 | [官方入口](https://cnr.nutn.edu.tw/?faculty=chingi)；8 頁 |
| 英語學系 | 6 | [官方入口](https://english.nutn.edu.tw/?faculty=%E6%A5%8A%E9%80%B8%E5%90%9B)；7 頁 |
| 應用數學系 | 8 | [官方入口](https://math.nutn.edu.tw/faculty_category/full-time-zh/)；1 頁 |
| 數位學習科技學系 | 11 | [官方入口](https://phpweb4.nutn.edu.tw/ilt/wordpress/?page_id=18)；1 頁 |
| 智慧製造在職學位學程 | 11 | [官方入口](https://scieng.nutn.edu.tw/smfg/)；12 頁 |
| 綠色能源科技學系 | 8 | [官方入口](https://greenergy.nutn.edu.tw/teachers.html)；1 頁 |
| 音樂學系 | 9 | [官方入口](https://music.nutn.edu.tw/member.html)；1 頁 |
| 視覺藝術與設計學系 | 10 | [官方入口](https://fineart.nutn.edu.tw/facultyview_1.html)；11 頁 |
| 戲劇創作與應用學系 | 7 | [官方入口](https://drama.nutn.edu.tw/ch/teachers.asp)；2 頁 |
| 經營與管理學系 | 9 | [官方入口](https://bm.nutn.edu.tw/teacher.html)；1 頁 |
| 行政管理學系 | 7 | [官方入口](https://pam.nutn.edu.tw/?taxonomy=faculty_category&term=full-time-teacher-zh)；1 頁 |

16 個入口合計取得 67 次成功頁面回應（跨系重複 URL 可重複計入）；加上補查生科首頁共 68 次。逐筆姓名、公開信箱、實際來源、所屬來源、抓取時間及 SHA-256 見 [來源稽核 JSON](../evidence/faculty_sources_2026-11-03.json)。只保存公開聯絡事實與來源指紋，不提交原始 HTML、隱藏表單權杖或登入資料。

## 追查與判讀

- 戲劇系跟隨第二頁，補到張麗玉、蔡依仁，沒有停在第一頁。
- 視設、文資、英語、特教等依具名個人頁取得信箱，不借用頁尾系辦信箱。
- 教育系名錄的呂明蓁、蘇建元、張主揚有畫面與 `mailto:` 不一致。解析器拒絕直接選其中一個；另用官方公開教師簡歷／課程頁交叉確認。張主揚的一個舊教務處補證頁回傳 404，失敗紀錄保留，後以公開課程頁取得正確對應。
- 官方網站公開列出的 Gmail、Hotmail 等同樣可作為公開職務聯絡信箱；不要求信箱必須是學校網域。來源本身仍須是官方頁面，不能由姓名猜帳號。
- 體育系龔憶琳的明示信箱有內嵌空白，只移除地址內空白，記錄 `email_whitespace_normalized`；不猜使用者名稱或網域。
- 原始 HTML 有 ASP.NET `<form>` 包住整頁。解析時只去除隱藏輸入與導航，不刪掉整個 form，避免漏掉真正公開教師內容。
- 同一教師在本系及支援學程都有官方列名時，兩個選單均保留，並以系所後綴識別。解析自然語言時，相同姓名／信箱只視為一個聯絡對象；不同信箱仍須澄清。指定系所時保留指定所屬。

## 尚未補齊

1. 智慧製造學程列出李建樹、許正良、蕭鳳翔，但此次由學程連出的個人頁未取得可驗證的姓名／信箱欄位，尚未加入該學程清單。李建樹原資工系的已驗證資料仍保留；不能直接把跨系同名當成已核對。許正良的搜尋快取可能顯示信箱，但直接抓取基本欄位為空，不以快取代替此次原站驗證。
2. 額外補查的生物科技系尚未完成：目前官方入口另導向公開 Google Sites；本次受限於既有官方網域追查邊界，未匯入教師資料。舊版 mobileBst 師資頁以網頁工具追查回傳 502。這是待追查，不是「官網沒有老師／信箱」。
3. 本次以專任／明確列名的學程支援師資為主，不包含所有兼任、退休師資或即時任職變更。頁面抓取成功不代表全校 coverage 完成。

## 重現維護

執行中的程式不需要 lxml；只有來源維護工具需要。已安裝 lxml 的 Python 可執行：

```bash
python3 scripts/refresh_verified_faculty.py --cache-dir /tmp/nutn-faculty-review-new --output /tmp/nutn-faculty-review-new/audit.json
```

審查 `contacts`、`conflicts`、`unresolved_names`、`failures`、`limit_reached` 及實際頁面，確認後才匯入；抓不到、欄位為空、多信箱衝突不能當成功。快取資料夾須使用新的目錄才會重新連網。

```bash
python3 scripts/publish_faculty_audit.py --reviewed-audit /tmp/nutn-faculty-review-new/audit.json
python3 scripts/build_email_directory.py --write
```

發佈會保留其他系原有資料；若信箱變更衝突會停止待人工審核。一般全校名錄刷新也不會抹去這批深入核對的教師資料，會保留各筆原來時間與來源指紋，不假稱重新驗證。移除／過期教師仍需另外人工審核，不由抓取失敗自動刪除。

## 驗證狀態

- 維護解析器：合成 HTML 的離線測試；涵蓋身份／信箱對應、頁尾隔離、畫面／連結衝突、姓名截斷、分頁、官方網域與轉址邊界。
- 系統／前端：16 系所的名單數量、實際表單選取、收件信箱與引用來源、本機模板草稿、跨系相同聯絡人合併及不同信箱澄清。
- 最終離線／localhost HTTP 回歸：194 項 Python 全通過；lxml 維護解析器另 10 項全通過；原前端 22 組、新前端 18 組全通過。分開記錄，不把來源抓取或畫面徽章當成模型成功證據。
- 真實瀏覽器：重新啟動的 8000 服務實測教育系、戲劇系分頁教師與跨系支援名單；使用訪客、未填真實個資、未產生模型草稿、未寄送。
- 本次 Gemini 生成：`LIVE_NOT_RUN`。來源網站真實抓取／UI 選單驗證不等於 Gemini `LIVE_PASS`；沒有寫入 Sandbox 或真實信箱。

證據：[回歸與版本指紋](../evidence/faculty_expansion_tests_2026-11-03.log)、[瀏覽器選項紀錄](../evidence/faculty_options_2026-11-03.txt)、[教育系畫面](../evidence/faculty_education_form_2026-11-03.png)、[戲劇系分頁教師畫面](../evidence/faculty_drama_form_2026-11-03.png)。未修改簡報，未 commit／push。
