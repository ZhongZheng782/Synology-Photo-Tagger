# Synology Photo Tagger

[![Docker Pulls](https://img.shields.io/docker/pulls/wenchiehlee1020/synology-photo-tagger?style=flat-square)](https://hub.docker.com/r/wenchiehlee1020/synology-photo-tagger)
[![Docker Image Version](https://img.shields.io/docker/v/wenchiehlee1020/synology-photo-tagger?sort=semver&style=flat-square)](https://hub.docker.com/r/wenchiehlee1020/synology-photo-tagger)
[![Docker Image Size](https://img.shields.io/docker/image-size/wenchiehlee1020/synology-photo-tagger?style=flat-square)](https://hub.docker.com/r/wenchiehlee1020/synology-photo-tagger)

> 以 AI 描述與標籤，讓 Synology Photos 照片更容易搜尋。

## 目標

本專案讓使用者先利用 Synology Photos 已有的資料（地點、拍攝日期、相簿與標籤）選出候選照片，再由 AI 產生補充描述與標籤，並在分析成功後透過 Synology Photos API 自動寫入及讀回核對。目標是協助搜尋與整理；無效或失敗的分析不得寫入，使用者可選擇 dry run 僅產生報告。

成功不只是「AI 看得懂照片」，而是能在 Synology Photos 中自然搜尋，例如搜尋 `購物`、`寺廟`、`夜景` 或 `美食`，並且標籤不會被綁死在某一個資料庫或單一 AI 模型。

## 核心原則

1. **Photos API 是唯一寫入介面**：不直接寫入 Synology Photos 資料庫，也不直接改寫照片檔。容器中的照片目錄唯讀掛載；標籤與描述透過 Photos API 更新。
2. **先選片、再分析**：以地點、拍攝日期或既有標籤建立候選範圍；若照片缺少所需篩選 metadata，需排除並說明原因。
3. **成功分析後自動寫入**：不要求逐張人工確認。只有格式有效、可解析的分析結果才進入寫入；空結果、錯誤或無法驗證的項目跳過並回報。提供 dry run 供使用者只預覽、不寫入。
4. **保護既有資料**：不得刪除使用者標籤、評分或拍攝資訊。若照片已有描述，批次工作保留原文並略過描述更新；只有原描述空白時才寫入 AI 描述。標籤採新增與讀回核對，不移除使用者原有標籤。
5. **使用者空間內的標籤詞彙**：優先沿用目前帳號與照片空間已有的標籤；只有沒有準確詞彙時才自動建立相關的新標籤，避免任意製造同義詞。
6. **逐張核對與可復原**：寫入後讀回 Photos API 結果；記錄每張照片的成功、失敗或不確定狀態。復原僅撤銷本工具明確新增且可識別的變更。

## 使用案例

下列案例共用相同的標記流程：先由 Synology Photos 條件（地點、日期或既有標籤）選出照片，再由 AI 產生補充描述與標籤。標籤優先沿用目前空間已定義的標籤；沒有合適詞彙時，才建立簡潔、可重複使用的相關標籤。分析成功後透過 Synology Photos API 自動寫入並讀回核對；dry run 可只產生報告。既有使用者描述與標籤應保留，不直接修改照片像素或繞過 Photos API 寫入檔案。

### UC-01｜日本地點照片的補充描述與標籤

**使用者故事**

> 我想找出所有地點在日本的照片，讓 AI 依照片內容補充描述，並加入已定義或合適的相關標籤，方便日後搜尋。

**流程**

1. 從目前選定的個人或共享空間，篩出 Synology Photos 地點資料顯示為日本的照片。
2. 建立候選清單並顯示縮圖、既有標籤與可用 metadata；缺少日本地點資訊的照片不列入此案例。
3. AI 逐張描述可見內容，並先從目前空間的既有標籤中選擇適合的標籤；沒有合適標籤時才自動建立相關的新標籤。
4. 驗證 AI 回應格式及內容；無效、空白或失敗的結果跳過並記錄原因。
5. 對有效結果透過 Photos API 自動寫入描述與標籤，逐張讀回確認；dry run 僅報告將執行的變更。

**驗收條件**

- 日本地點篩選只依 Photos API 回傳的地點資料，不因照片內容猜測拍攝國家。
- 描述只陳述照片中可見或 Photos metadata 已確認的資訊，不猜測人物身分或敏感特徵。
- AI 優先沿用目前空間已定義的標籤，不為同一概念任意產生多個同義標籤。
- 分析失敗、無有效建議或寫入未成功的照片會清楚標示，不回報為已完成。

### UC-02｜依日期區間的補充描述與標籤

**使用者故事**

> 我想指定拍攝日期區間，讓 AI 為該期間的照片補充描述及已定義或合適的相關標籤，方便整理與搜尋。

**流程**

1. 使用者指定起訖日期與個人或共享空間；Photos API 只提供拍攝時間落在區間內的候選照片。
2. 候選清單顯示縮圖、拍攝日期、既有標籤與可用 metadata，並讓使用者檢視實際範圍。
3. AI 逐張根據畫面內容產生簡潔補充描述與標籤建議；優先沿用目前空間已定義的標籤，必要時提出相關標籤。
4. 驗證 AI 回應；無效、空白或失敗的結果跳過並記錄原因。
5. 對有效結果透過 Photos API 自動寫入描述與標籤並逐張讀回核對；失敗項目可單獨檢查或重試。dry run 不寫入。

**驗收條件**

- 日期區間使用 Synology Photos 的拍攝時間；沒有可用拍攝時間的照片不會被誤列為符合。
- 描述補充可見內容，不把日期、地點或畫面中未確認的文字當成事實。
- 既有描述與使用者標籤不得被 AI 結果靜默覆寫或移除。
- 可在 dry run 預覽變更；自動寫入後可讀回確認每張照片的結果。

### UC-03｜日期區間整理健康與健檢照片（UC-02 範例）

這是 UC-02 的一種內容情境，不另設不同的選片或寫入流程。

> 我想在指定日期區間內找出健檢報告、量測畫面或醫療文件，取得客觀的補充描述與適合的既有標籤，例如 `健檢`、`血壓` 或 `心率`。

- AI 只描述可見的文件或量測內容，不提供診斷、健康風險判斷或治療建議。
- OCR 僅在需要讀取文件內容時使用；完整 OCR 原文不作為照片描述或標籤，也不保存在工作紀錄。
- 不將診斷、身分證號等敏感 OCR 文字寫入描述、標籤或工作紀錄；無法可靠判讀的結果不寫入。

### UC-04｜已標籤照片的補充描述與相關標籤

**使用者故事**

> 我想從已經有標籤的照片中選出一批，讓 AI 參考既有標籤與照片內容補充描述，並補上尚缺的已定義或相關標籤。

**流程與規則**

1. 使用者選擇空間及一個或多個既有標籤，列出目前帶有這些標籤的照片；可先預覽實際候選清單。
2. AI 同時參考照片可見內容、既有標籤與已確認 metadata，產生補充描述及標籤建議；既有標籤不重複加入。
3. 標籤優先從目前空間的既有詞彙中選擇；若沒有準確詞彙，才自動建立簡潔、可重複使用的相關標籤，並記錄於工作報告。
4. 補充描述應保留使用者原有描述，只更新本工具管理的內容；不得把既有標籤當成已由 AI 驗證的影像事實。
5. 分析有效的照片由 Photos API 自動寫入並讀回核對，結果可追溯到照片與本次工作；dry run 可略過寫入。

**驗收條件**

- 只處理所選既有標籤符合條件的照片，並在寫入前顯示候選數量。
- 不重複新增照片上已存在的標籤，也不移除使用者既有標籤。
- 描述與標籤變更可由 dry run 報告預覽；失敗或讀回未核對的項目不會計為成功。
- 寫入只透過 Synology Photos API；不直接修改 Synology Photos 資料庫或照片像素。

## Production requirements

以下是 UC-01 至 UC-04 共用的產品需求。它們描述目標行為，不代表目前全部已實作。

### FR-01｜候選範圍與快照

- 支援個人空間與共享空間，並在每次工作中明確記錄所選空間與篩選條件。
- 地點篩選使用 Synology Photos API 回傳的地點欄位；日期篩選使用拍攝時間，起訖日均包含在範圍內，並以使用者可見時區顯示。
- 既有標籤篩選只在所選空間內生效；同一工作可明確選擇單一或多個標籤。
- 建立工作時固定候選照片 ID 清單及總數。掃描達上限、API 分頁不完整或缺少篩選 metadata 時，必須明確顯示，不能把部分結果說成完整相簿。
- 工作建立後保留候選快照；照片後續被移除、權限變更或標籤變動時，寫入前要重新讀取照片狀態並跳過不再符合條件的項目。

### FR-02｜AI 建議與標籤一致性

- 每張候選照片可產生簡潔、客觀的繁體中文補充描述，以及 0 個以上的標籤；不得為了湊數強迫加標籤。
- AI 先使用目前帳號、目前空間的既有標籤；沒有合適詞彙時，可自動建立明確相關的新標籤，並在工作報告中列出。
- 建議不得把既有標籤當作畫面已證實的事實；人物姓名只可引用 Synology Photos 已辨識的人物 metadata，不得單憑影像猜測身分。不得推斷健康、年齡或其他敏感特徵。
- 每個結果需關聯照片 ID、所屬空間、模型／提示版本、分析時間與處理狀態，供工作報告與重試使用。

### FR-03｜預覽、寫入與驗證

- 成功分析後自動寫入，不要求逐張確認。提供 dry run 模式，僅呈現目前值、將新增或更新的內容及候選數量，不呼叫寫入 API。
- 僅格式有效且可解析的 AI 結果可寫入；分析錯誤、空結果、缺少必要欄位或不支援的操作必須跳過並回報。
- 寫入只使用 Synology Photos API。每張照片在寫入後都需讀回標籤與描述，分別記錄已驗證、失敗或狀態不確定。
- Photos API 呼叫或讀回失敗時不可回報成功。重試必須冪等：已存在的目標標籤不重複建立；若目標標籤已寫入但來源標籤尚未移除，重試應先核對現況再續做。
- 容器或網路中斷後，不可假設批次未執行；重新掃描 Photos API 現況，列出已完成、待處理與需人工核對項目。
- 描述更新不得覆蓋使用者原有文字。現行安全策略只在原描述空白時寫入 AI 描述；原描述非空時保留原文並略過描述更新，仍可繼續新增及核對標籤。未來若有明確管理區段，才可評估安全合併。

### FR-04｜資料保存與復原

- SQLite 可保存工作條件、候選項目、AI 摘要與逐張寫入回讀結果；原圖與完整 OCR 原文不得寫入工作資料庫或容器磁碟。
- 工作需以 NAS 位址、空間與 Photos item ID 識別照片；不得宣稱具有跨 NAS、跨 item ID 的永久照片識別，除非相應映射機制已實作並驗證。
- 可下載逐張結果報告。撤銷功能只能移除本工具記錄為本次新增的標籤，並須先讀回確認；不得用原始檔雜湊承諾還原照片檔案位元組。
- 背景工作需持續提供進度。服務重啟後應能從持久化狀態恢復或提供明確的核對流程；只存在記憶體中的狀態不符合正式批次工作需求。

### NFR-01｜安全、隱私與可用性

- NAS 密碼與 OTP 不得保存到資料庫、日誌或瀏覽器儲存；Photos API session 由伺服器端管理，並限定在登入帳號權限內。
- Web UI 正式對外使用時必須經 HTTPS；直接使用 HTTP 僅限可信任 LAN 或 SSH tunnel。
- 原圖會從 Synology Photos 傳送到設定的 MLX 分析服務。視覺模型在 Mac-mini 執行；OCR 引擎依 `MLX_OCR_ENGINE` 設定。若使用 Baidu OCR，文件內容會送往 Baidu 服務處理，不能描述為完全本機 OCR；部署前需告知並取得使用者同意，或改用本機 OCR 引擎。
- 對照片格式、Photos API 版本與空間類型建立驗證矩陣；API 不支援、格式未驗證或權限不足時，停用相應寫入並顯示原因。
- 批次工作需處理限流、短暫 NAS 斷線、閘道逾時與服務重啟；進度查詢不能依賴保持一個長時間 HTTP 請求。
- 所有顯示的總數、進度與成功數需來自可核對的候選快照和 Photos API 讀回結果。

## Photos API 寫入與格式支援

本專案以 Synology Photos API 作為標籤與描述的寫入介面。Photos API 可能更新照片檔案 metadata；唯讀掛載只能防止容器直接改寫掛載檔，不能保證 NAS 套件不會因 API 寫入而改變檔案位元組。

已驗證的範圍需以實測記錄為準：目前曾對指定的 JPG 與 HEIC 照片測試標籤新增／移除及讀回；這不等於所有 JPG、HEIC、共享空間或 Description 寫入都已通過驗證。上線前需逐一驗證目標 DSM／Synology Photos 版本、個人與共享空間、標籤與描述 API、讀回結果及原檔變化，未驗證的組合不得列為正式支援。

## 目前資料模型與實作界線

目前 SQLite 儲存 AI 標記工作、每張候選的分析／審核／寫入結果，以及 Photo Tagger 新增標籤的 provenance ledger。程式尚未實作 README 舊版提到的永久 `asset_id`、`visual_fingerprint`、跨 item ID 對應或完整 OCR 結果索引；本文件不再把這些能力當成現有功能。


## UX Mockup v1.1（UX-Deck 視覺 × 確認後的導覽）

以 [UX-Deck 的 Synology Photo Tagger mockup](https://wenchiehlee-ux.github.io/UX-Deck/showcases.html#synology-photo-tagger) 為最終 UX 參考。完整採用松鼠品牌、紫／琥珀色、字體、按鈕、卡片、標籤 chips、狀態 badge、圓角、陰影與間距。主要導覽為「照片庫、建立工作、工作結果、設定」；**照片庫是入口，不設獨立總覽頁**，原總覽的服務狀態放在設定。API 探索只放在設定的診斷區。

照片庫採橫向清單，縮圖桌面版至少 144 × 108 px、窄螢幕至少 112 × 84 px；此處篩選只作用於顯示清單，單張 AI 分析從照片卡片啟動。建立工作提供「AI 標記」與「批次更改標籤」兩種工作類型；AI 標記頁呈現照片空間、地點、日期區間、既有標籤及候選上限等條件，與照片庫篩選互相獨立。UC 編號只用於需求文件，不顯示在 UI。Faces／Scenes／Pets 不屬於目前範圍。工作模式預設分析成功後自動寫入並讀回核對，可選 dry run。

使用者選定照片範圍後，可啟動預設的自動處理，或選擇 dry run。自動處理會分析有效候選照片，透過 Synology Photos API 寫入描述與標籤，再讀回驗證；不要求逐張人工核准。失敗或不適合寫入的項目會略過並列出原因。

### UX 對齊決議

| 決策問題 | UX-Deck 方案 | 現有頁面／其他選項 | 狀態 |
| --- | --- | --- | --- |
| 1. 採用 UX-Deck 視覺設計的哪些部分？ | 松鼠圖示、Vision Violet `#8b5cf6`、Acorn Amber `#f59e0b`、柔光表面 `#faf5ff`；Inter、JetBrains Mono、Noto Sans TC；按鈕、卡片、chips、badge、圓角、陰影與間距。 | 已決定完整採用 UX-Deck 的品牌識別及介面元件樣式。 | **已決定：完整採用 UX-Deck 視覺系統。** |
| 2. 主要導覽採哪種資訊架構？ | UX-Deck：Photo Feed、Faces、Scenes、Pets、Queue、Taxonomy 分頁；Settings 作獨立入口。 | 照片庫、建立工作、工作結果、設定；照片庫為入口，不設總覽頁。 | **已定稿：照片庫、建立工作、工作結果、設定。** API 探索固定放 Settings。 |
| 3. UX-Deck 的內容模組如何放進目前導覽？ | Photo Feed、Faces、Scenes、Pets、Queue、Taxonomy 是獨立分頁。 | Photo Feed 對應「照片庫」、Queue 對應「工作結果」、Taxonomy 對應照片庫中的標籤盤點；建立工作提供 AI 標記與批次標籤更名。Faces／Scenes／Pets 不屬於目前 UC-01／02／04 範圍，不加入本階段導覽或篩選。 | **已決定：目前範圍不納入 Faces／Scenes／Pets。** |
| 4. 照片清單採網格還是清單？ | UX-Deck 採相片卡片網格。 | 採橫向清單卡片，套用 UX-Deck 的視覺元件。 | **已決定採橫向清單。** 縮圖桌面版至少 144 × 108 px、窄螢幕至少 112 × 84 px，保留照片比例及主要主體。 |
| 5. 卡片與頂部狀態顯示哪些資訊？ | UX-Deck 展示 AI 模型在線、標記數與信心資訊。 | 顯示實際服務連線狀態、候選數、工作進度／結果與 Photos API 讀回狀態；不顯示模型信心、準確率或其他模型 metrics。 | **已決定：不顯示模型 metrics。** 已從目前工作分支的工作結果卡片移除信心值；已發佈的 v0.4.5 頁面仍保留原畫面。 |

以下是對齊時不可改變的產品界線：Synology Photos API 是標籤與描述的寫入介面；不可直接寫 Photos 資料庫或 XMP sidecar。原圖送往部署設定中的 MLX 分析服務；若 OCR 使用 Baidu，需清楚說明資料會送往外部服務。UX-Deck 展示稿中的「雲端相片庫」、CLIP／Ollama、PostgreSQL／XMP 及固定準確率不能直接視為本專案已驗證的功能或架構。

### 1. 建立工作

```text
┌────────────── 建立 AI 標記工作 ──────────────┐
│ 照片空間      [個人空間 ▼]                   │
│ 地點          [不限地點 ▼]                   │
│ 拍攝日期      [開始日期] 至 [結束日期]        │
│ 既有標籤      [選取一或多個標籤 ▼]            │
│ 候選照片      1,248 張                       │
│                                               │
│ AI 處理       ☑ 補充描述  ☑ 標籤              │
│ 標籤策略      優先沿用空間既有標籤；           │
│               沒有合適標籤時建立相關標籤       │
│                                               │
│ 寫入模式      ● 分析成功後自動寫入並讀回驗證   │
│               ○ Dry run（只分析與產生報告）    │
│                                               │
│                         [開始工作]             │
└───────────────────────────────────────────────┘
```

建立工作時保存空間、篩選條件與候選照片 ID 快照。畫面需顯示候選數量；若 API 分頁或掃描上限使結果不完整，開始前明確提示並在工作記錄中標示。缺少篩選所需 metadata 的照片不列入候選。按下「開始工作」即開始所選模式，不再出現逐張或批次寫入確認視窗。

候選清單需在啟動工作前提供可辨識的照片預覽，採最終 mockup 的橫向清單項目，並套用 UX-Deck 的按鈕、卡片、標籤 chips 與狀態 badge 樣式。桌面版縮圖至少 **144 × 108 px**，窄螢幕至少 **112 × 84 px**；保留照片比例，避免裁掉人物或主要內容。縮圖需與檔名、拍攝日期、地點及既有標籤一起呈現，讓使用者能檢查篩選結果。

```text
┌──────────────────── 候選照片（1,248 張）───────────────────┐
│ ┌──────────────┐  IMG_1297.HEIC                              │
│ │              │  2026-06-26 · 犬山市、日本                  │
│ │ 大縮圖       │  既有標籤：Mandy Lin、旅遊                  │
│ │ ≥144×108     │  [描述預覽] [AI 分析狀態]                    │
│ └──────────────┘                                             │
│ ─────────────────────────────────────────────────────────── │
│ ┌──────────────┐  IMG_1298.HEIC                              │
│ │              │  2026-06-26 · 犬山市、日本                  │
│ │ 大縮圖       │  既有標籤：家庭、旅遊                       │
│ │ ≥144×108     │  [描述預覽] [AI 分析狀態]                    │
│ └──────────────┘                                             │
└─────────────────────────────────────────────────────────────┘
```

### 2. 執行進度與結果

```text
┌────────────── 建立工作 · AI 標記：日本照片 ───┐
│ 狀態：處理中                                  │
│ 已完成  416 / 1,248                           │
│ 分析中 12   已寫入並驗證 381                   │
│ 略過 29    失敗 6                              │
│                                               │
│ [全部] [處理中] [已驗證] [略過] [失敗]         │
│                                               │
│ [縮圖] 描述：庭園中的日式城堡…                 │
│       標籤：日本城堡、庭園、戶外                │
│       狀態：已寫入，Photos API 讀回一致        │
│                                               │
│ [縮圖] 分析結果無有效描述或標籤                 │
│       狀態：已略過 · 無有效 AI 結果             │
│                                               │
│ [下載工作報告]       [重試失敗項目]             │
└───────────────────────────────────────────────┘
```

執行中持續顯示進度；每張照片分別記錄分析、寫入與讀回狀態。只有 Photos API 讀回符合預期才列為「已驗證」。分析失敗、無有效輸出、權限不足或 API 錯誤都不得列為成功，應保留可理解的原因並允許安全重試。Dry run 使用相同候選範圍與分析流程，但每張結果標示「預覽，未寫入」，且不得呼叫 Photos API 寫入端點。

結果清單以縮圖呈現描述、標籤與處理狀態。既有標籤不重複新增；人物姓名只能使用 Synology Photos 已辨識的人物 metadata。若照片已有 Description，而 Photos API 無法安全保留原文並合併本工具內容，跳過該照片並說明原因，不得覆蓋原描述。完整 OCR 原文不得存入工作資料庫或報告；健康文件不產生診斷或健康風險判斷。

### 3. 報告與復原

工作報告提供工作條件、候選數量、完成／略過／失敗統計，以及逐張照片的處理結果。重試前重新讀取 Photos API 現況，避免重複建立標籤或重複覆寫描述。復原只移除本工具本次新增且可辨識的標籤；不承諾還原照片檔案位元組，也不撤回已寫入的 Description。服務重啟後依持久化工作狀態恢復；若狀態不足以判斷是否已寫入，標示「需核對」並先比對 Photos API，不直接重做。

### 4. 設定與 API 診斷

```text
┌──────────────────── 設定 ────────────────────┐
│ NAS 連線                                      │
│ 狀態：已連線   DSM：[已連線的 NAS 位址]       │
│ 照片空間：個人空間、共享空間                  │
│                                               │
│ 診斷工具                                      │
│ Synology Photos API                           │
│ [探索 API 模組]                               │
│                                               │
│ 最近結果：找到 N 個 Photos API 模組            │
│ 個人空間模組：…                               │
│ 共享空間模組：…                               │
└───────────────────────────────────────────────┘
```

「探索 API 模組」只用於設定與故障診斷，不會執行照片分析或寫入。一般照片工作直接使用服務端取得的 API catalog，不要求使用者先進入設定或手動探索。

本 UX 定義的是目標流程。v0.4.12 將每日排程改為透過 Photos API 日期篩選查詢執行日與前一日的照片，避免由最新照片開始掃描整個資料庫。v0.4.11 已發佈至 Docker Hub 並部署至 NAS，並將 UX-Deck Lucide squirrel 設為瀏覽器 favicon。v0.4.9 將側欄明確分成「照片庫、建立工作、工作結果、設定」：照片庫只負責瀏覽與單張操作；批次 AI 標記與批次標籤更名都由建立工作啟動；兩類工作的進度與結果集中在工作結果。v0.4.10 擴充候選上限至 1000 張，並加入每日 AI 標記排程與 Synology 受信任裝置登入。

## 目前頁面盤點與 Production TODO

以下盤點涵蓋已部署的 v0.4.8、v0.4.9、v0.4.10 功能及仍需驗證的工作。UX 方向已定稿；Production TODO 列出尚未完成的產品化項目。

| 頁面／區域 | 目前行為 | Production TODO |
| --- | --- | --- |
| 全站導覽與狀態 | v0.4.8 的照片瀏覽、AI 標記、工作結果與設定入口仍容易讓「照片清單」和「AI 標記工作」的用途混淆。 | v0.4.9 改為「照片庫、建立工作、工作結果、設定」；照片庫篩選只影響畫面清單，批次工作使用各自的條件；建立工作可切換 AI 標記或批次更改標籤。 |
| NAS 連線與 API 診斷 | 首頁按鈕呼叫 `/api/discover`，列出 `SYNO.Foto.*` 與 `SYNO.FotoTeam.*` 模組；登入流程會再次查詢 API catalog。 | 一般流程直接顯示 NAS 可連線狀態、登入狀態與可用空間，不要求先探索 API。將模組清單、重新探索與連線診斷移至「設定」；避免重複查詢並保留故障排查能力。 |
| 登入 | 使用者輸入帳號、密碼與選填 OTP；NAS session 在伺服器端記憶體，瀏覽器簽章 session 有效期間較長。 | 定義登出、session 過期與容器重啟後的清楚狀態；確保錯誤訊息與日誌不洩漏憑證。正式對外入口需 HTTPS，部署文件要反映實際 TLS 拓撲。 |
| 照片庫 | 支援個人／共享空間、日本地點或標籤篩選、照片預覽、metadata 及單張 AI 分析。 | v0.4.9 明確說明此處篩選只作用於畫面清單；批次 AI 條件需在建立工作中設定。 |
| 單張 AI 分析 | 目前工作分支在有效分析後自動透過 Photos API 寫入並讀回；已有描述會保留並略過描述更新。 | 將錯誤狀態與批次工作結果一致化；單張流程目前沒有獨立 dry run，預覽不寫入由 AI 標記工作提供。 |
| 建立工作 | AI 標記支援條件快照、自動寫入及 Dry run；v0.4.8 會略過已有 Photo Tagger AI 描述或 AI 標籤的照片。 | v0.4.9 將批次標籤更名也納入工作類型選擇；照片庫現有清單不會自動成為 AI 標記條件。 |
| 工作結果與復原 | 顯示 AI 標記工作的描述、標籤、自動寫入／Dry run 狀態與讀回結果；批次標籤更名原先只在建立區顯示進度。 | v0.4.9 將批次標籤更名進度與完成摘要同步顯示在工作結果。工作記錄持久化與中斷調和仍待改進。 |
| API／版本支援 | API catalog 動態探索；指定 JPG 與 HEIC 曾實測標籤 add/remove/readback。 | 在 DSM 7.4.1、Synology Photos 1.9.1-928 上驗證個人與共享空間、描述與標籤寫入、格式、讀回與原檔變化；不支援或未驗證的組合需在 UI 中阻止或明確標示。 |
| OCR 與敏感文件 | OCR 細節與除錯資訊可能顯示於單張分析結果；結果不寫入照片或工作資料庫。 | Production 預設顯示必要摘要，避免把完整 OCR 原文放入一般工作報告或持久化紀錄；標示 OCR 引擎與資料傳輸目的地，限制診斷、身分證號等敏感內容被寫成描述或標籤。 |

### Production 轉換順序

1. 將 API 探索與模組清單移至「設定」的診斷區；一般工作流程直接提供連線狀態，不要求手動探索。
2. 擴充候選條件與快照，覆蓋 UC-01、UC-02、UC-04，並呈現總數與不完整狀態。**目前分支已加入日期起訖與多標籤工作快照條件，且在分析前顯示候選縮圖與掃描完整性；候選快照目前在按下「預覽候選並建立快照」後才產生，完整候選總數與開始前預覽仍待補齊。**
3. **目前分支已完成核心流程**：一般照片描述與標籤分析、自動寫入／dry run、Photos API 讀回核對；既有描述非空時保留並略過描述更新。仍需目標 NAS 驗證、逐張狀態報告及中斷恢復。
4. 補齊中斷工作自動讀回調和、權限與錯誤狀態、OCR 隱私處理及 DSM／Photos 相容性驗證；目前已有 SQLite 持久化及安全標示中斷寫入的基礎處理。
5. 完成 UX Mockup v1.1 的 UX-Deck 視覺系統與橫向照片清單；未支援功能需明確標示，再更新版本說明與部署文件。導覽骨架與 API 探索 Settings 區已開始實作。

v0.4.12 將每日排程的查詢範圍設為執行日與前一日，並使用 Photos `Browse.Item list_with_filter` 的拍攝日期篩選；個人及共享空間均沿用對應的 Photos API 模組。日期解讀依 Photos 的無時區拍攝時間格式處理。v0.4.11 的 Docker Hub 與 NAS 部署已確認 `/health` 回報正確版本，favicon 連結與 SVG 資源均成功回應；定期登入金鑰的唯讀掛載檢查亦通過。

## 參考實作

- [eleonne/synology-tagger](https://github.com/eleonne/synology-tagger)：以機器學習擴充 Synology Photos 搜尋的開源實作。它將分類結果寫入 Synology Photos 的 `general_tag` 與 `many_unit_has_many_general_tag` 資料表；本專案僅將其作為設計參考，仍採 metadata-first 策略，不直接寫入 Synology Photos 內部資料庫。
- [zeichensatz/SynologyPhotosAPI](https://github.com/zeichensatz/SynologyPhotosAPI)：Synology Photos API 的非官方探索文件，供 API 探測與整合設計參考；內容尚不完整，實際支援的 API 與參數仍須在目標 NAS 上驗證。
- [Photon](https://github.com/komoot/photon)：以 OpenStreetMap 資料提供反向地理查詢；Photo Tagger 僅在使用者查看帶有「產品」標籤的單張照片時查詢附近商店，並顯示 [OpenStreetMap attribution](https://www.openstreetmap.org/copyright)。

## 目前 AI 標記工作範圍

v0.4.26 加入 UC-06 唯讀旅行工作 API，可由授權客戶端建立及啟動 UC-05 住宿分析、讀取進度與下載報告；獲授 `travel:map_lookup` scope 時，也可直接查指定住宿候選的公開地圖。API 沒有任何 Synology Photos 寫入權限。

UC-01 至 UC-06 是目標產品需求。下表列出 v0.4.26 的功能狀態及尚待完成項目：

| 使用案例 | v0.4.26 功能狀態 | 尚缺的主要能力 |
| --- | --- | --- |
| UC-01 日本地點 | 支援日本候選快照、一般 AI 分析、自動寫入及 Dry run | 目標 NAS 實測與格式／空間相容性核對 |
| UC-02 日期區間 | 支援拍攝日期篩選、快照、批次分析、自動寫入及 Dry run | 目標 NAS 驗證日期 metadata 與結果 |
| UC-03 健檢範例 | 單張分析會自動寫入有效描述與標籤；既有描述會保留 | 敏感 OCR 欄位排除、隱私流程與目標 NAS 驗證 |
| UC-04 已標籤照片 | 支援多個既有標籤條件及整批 enrichment | 目標 NAS 驗證標籤詞彙重用、新標籤建立與讀回 |
| UC-05 旅行住宿辨識 | MVP：本機目錄選片、固定快照、GPS／時間群組代表照 MLX 取樣、跨日群組、人工核對日期、公開地圖查詢、Markdown／JSON 報告 | 訂房生命週期、既有 MLX 結果重用、群組樣本自動擴充、無 GPS 照片連結與歷史旅宿核實；詳見 [功能規格](#uc-05-旅行住宿辨識與歷史重建) |
| UC-06 外部 AI 工作管理 API | v0.4.26 提供唯讀旅行工作建立／啟動／進度／報告及 scope 保護的公開地圖查詢 | 暫停續跑、一般 AI 分析與任何 Photos 寫入權限；詳見 [功能規格](#uc-06-外部-ai-工作管理-api) |

本機 metadata catalog 與工作資料分存在同一個持久化 volume 的獨立 SQLite 檔案。AI 工作提供最多 1000 張候選、一般照片分析、自動寫入／dry run 與 Photos API 讀回核對。v0.4.23 將 `Photo Tagger AI v1` 作為 AI 標記設定版本，與 Docker 映像版本分開。一般 AI 寫入只有在內容寫入成功且 Photos API 讀回核對版本標記後，才記錄目前版本；Dry run 與單純批次更名不會加版本標記。新版新增獨立的「升級 AI 標記版本」工作，可選擇 Photo Tagger 可確認的 AI 成功紀錄、指定較舊版標記，或依地點／日期／既有標籤篩選尚無任何版本標記的照片。升級會重新分析並依一般工作規則寫入與核對；非空描述仍保留，不會被覆寫。候選數量受工作上限限制，超過上限可再建立工作處理後續候選。版本標記存在 Synology Photos；可確認的 AI 成功紀錄存在本機 SQLite，並按 NAS 帳號與空間隔離。舊版資料庫中無法判斷是 AI 寫入或單純更名的紀錄會標示為來源不明，不會用作 AI 升級或略過依據；這些歷史照片可改用篩選來源處理。v0.4.8 將一般工作略過條件限定為 Photo Tagger AI 描述或標籤成功寫入紀錄，單純標籤更名不會觸發略過。服務啟動時會把分析中項目標示為失敗、寫入中項目標示為需核對，避免不確定狀態自動重試；尚未實作透過 Photos API 自動調和中斷前後狀態。

正式上線前仍須完成中斷工作自動調和、格式／空間／API 版本相容矩陣，以及外部 OCR 資料傳輸告知。影片標註、跨全庫無限制掃描與直接寫入 Synology Photos 資料庫不在支援範圍內。

## UC-05 旅行住宿辨識與歷史重建

**狀態：** v0.4.25 提供唯讀 MVP；首批以日本歷史旅行照片驗證，功能設計不限制國家。報告中的飯店均是候選線索，不等於已確認入住。

### v0.4.25 已實作範圍

- 在「建立工作」選「旅行住宿辨識」，選照片空間、國家、日期區間與最多 1,000 張上限。至少要指定國家或日期條件，避免全庫掃描。
- 只查詢所選 NAS 帳號／空間已完整同步的本機 metadata catalog；未完整同步時拒絕建工作並提示。最多檢視 10,000 筆符合 metadata 的照片；超出時顯示快照不完整及縮小範圍的提示。依住宿相關既有標籤／描述、缺少描述與 GPS 排序。
- 工作固定照片 ID、縮圖與必要 metadata，使用既有 Synology Photos API 單張讀取原圖，送至私有 MLX `/photo-analyze`。住宿線索分類為飯店招牌／外觀、客房、浴室、飯店早餐、房卡、訂房文件、房內窗景、非住宿或無法辨識。
- 結果只保存清理後的飯店名稱、城市、線索類型、簡短描述與理由；不保存模型原文或 OCR 原文。旅行住宿工作不會呼叫 Photos API 寫入，人工操作只標示照片線索「確認」或「排除」。
- 依同一國家、相鄰拍攝日期間隔不超過 14 日產生旅行群組建議；可編輯群組名稱並確認／排除。這是供人工核對的時間分組線索，不代表已確認為同一趟旅行。
- 在每個飯店候選卡片中，可手動輸入住退房日期及確認狀態。日期不會從照片拍攝日期自動推論。
- 在 Web UI 中，每次查詢前需勾選同意並按「查詢公開地圖候選」。UC-06 外部 API 可在 Token 獲授 `travel:map_lookup` scope 後直接呼叫查詢端點。兩種方式都只傳送飯店名稱、城市與國家至 OpenStreetMap Nominatim；不傳照片、精確 GPS 或 NAS 帳號。結果快取 24 小時、每秒最多發出一個新查詢、顯示 attribution。若 OSM 資料有 website 標籤，提供連結給使用者自行核對；OSM 結果不等於官方確認。
- 以旅行群組與相同飯店名稱彙整照片證據，提供 Markdown 與 JSON 報告下載。報告保留地圖來源、人工核對狀態及未確認欄位的 null 值。

### 目標與工作流程

1. 在「建立工作」新增「旅行住宿辨識」類型；輸入國家、日期區間、空間及候選上限，先用本機 metadata catalog 搜尋既有描述、標籤與 GPS。未同步或不完整時明確提示。
2. 優先分析有住宿線索、缺少 AI 描述、或舊版描述不足的照片；使用私有 MLX 圖像分析與固定候選快照，顯示逐張進度，避免全庫無限制掃描。MVP 不呼叫 OCR；後續若支援入住文件 OCR，必須只抽必要欄位且不可保存原文。
3. 輸出每張照片的住宿證據類型：飯店外觀／招牌、客房與浴室、房卡（只保留飯店名稱）、早餐餐廳、入住文件／訂房憑證（只抽取必要飯店與日期欄位）、窗外景觀。標記「非住宿」或「無法辨識」亦為有效結果。
4. 將同趟旅行內相近 GPS、名稱、日期及室內／外觀證據聚合為住宿候選；允許同趟多間飯店、無 GPS 照片及缺日。區分照片拍攝日期與實際入住／退房日期，保留時區與時間不確定性，不以清晨或夜間單張照片判定住宿。**MVP 以同一國家且日期相鄰不超過 14 日的照片建立可人工確認的時間群組，還不會依 GPS 軌跡自動串接無 GPS 照片。**
5. 以使用者每次明確同意後的公開地圖查詢協助核對名稱、地址及座標；若 OSM 有 website 標籤可由使用者開啟官網。歷史更名及營業年代仍需人工查證；候選不足時保留未知，同地點多間飯店並列待核對。**OSM 查詢結果不是住宿或官方名稱的自動確認。**
6. 在「工作結果」提供住宿線索照片、人工確認／排除及 Markdown／JSON 報告，供 Llm-Cli-APIServer 整理 ChatGPT repo 的 `travels/日本住宿歷史總表.md`。報告匯出不自動推送外部 repo。

### P0 新需求：多重訂房、取消與實際入住判定

**狀態：已同意需求，待實作。** v0.4.29 已能接收獨立外部證據事件，但尚未提供逐筆訂房生命週期、衝突判斷與照片關聯。

使用者在旅行前可能同時預訂多間可免費取消的飯店，亦可能取消後重新預訂同一飯店。不得將訂房確認視為入住，也不得以飯店名稱為單位套用取消狀態。

- 旅行助手（Llm-Cli-APIServer）依照片旅行日期搜尋 Gmail，包含旅行前較早的訂房、改期、取消以及旅行後的退房證據；依 OTA／飯店訂房識別關聯事件，而非只比對名稱或郵件日期。保留飯店、城市、預定住退日期及最小必要來源參考。
- 可選相容 External Evidence API 的目標新增 `booking_key`（由旅行助手以具密鑰 HMAC 對來源平台／帳號／訂房識別產生穩定不透明識別；不傳原始訂單號或密鑰）、`event_at`（事件時間含時區或明確未知）、事件類型及來源參考。新訂單使用獨立 key；明確的原訂單改期沿用同一 key。
- 逐筆保留訂房確認、變更、付款／退款、取消、入住及退房事件；按事件時間及可驗證的因果關係重建 `booking_status`（booked、modified、cancelled、unknown 等），重送須冪等、亂序匯入結果須一致。缺 key、時間不明或事件矛盾時標示待人工核對，不猜測取消對象。
- 取消僅影響其對應訂房；其他同飯店或重疊日期的訂房仍獨立有效。付款與訂房確認均不證明入住；取消紀錄與實際入住證據矛盾時保留雙方並標示衝突，不自動排除。
- 另行判定 `stay_status`（unknown、possible、needs_review、confirmed、excluded），綜合 Gmail 實際入住／退房證據、照片 OCR／AI、GPS、拍攝日期及人工核對。多筆重疊有效訂房無充分證據時並列候選，不強制選取一間；實際住退日期不得直接照抄預訂日期。
- UI 與 Markdown／JSON 報告須區分預訂日期、實際入住日期、逐筆訂房狀態、住宿狀態與理由，保留來源及不確定性；取消的候選仍可稽核。最終確認由人工完成，不自動修改 Synology Photos 標籤、照片或旅行 repo。Gmail 授權與原始郵件只留在旅行助手層。

驗收案例（使用合成資料）：

| 情境 | 預期結果 |
| --- | --- |
| 同飯店 A 訂單取消、B 訂單重新預訂 | A cancelled；B 保持有效 |
| 同期預訂飯店 A、B，僅取消 A | 不影響 B；仍未證明入住 B |
| 同一訂單改期、重送或亂序收到取消 | 依事件重建一致狀態，不重複計數 |
| 多間未取消飯店、僅有訂房或付款證據 | 並列待確認，不自動判定入住 |
| 入住／退房郵件與 GPS、照片一致 | 提供實際住宿日期與候選，供人工確認 |
| 取消與入住證據矛盾、缺少訂房識別 | 保留衝突與未知，不誤合併或排除 |

### P0 新需求：GPS-first 住宿聚類與 MLX 呼叫量最佳化

**狀態：部分實作。** UC-05 建工作時會先在本機依 GPS 距離（初始 75 公尺）與拍攝時間（最多相差 48 小時）分群。過渡版曾依既有住宿標籤／描述選出每群 1–3 張代表照；新版預設所有照片保留於快照且略過 MLX。缺 GPS 或缺拍攝時間的照片不會與其他照片合群。工作結果顯示群組數、GPS 照片數、代表樣本數、預估分析減量及工作項目的實際分析嘗試／失敗數（不等同 MLX 服務端實際執行次數）。此為保守的首輪取樣，尚未實測校準，也不代表群組已確認為住宿地點。

新版 metadata-only 路徑建立工作即進入待核對，預設零 MLX、零原圖下載；既有工作仍保留其原分析策略。外部證據可提供經查證的飯店 latitude／longitude，於本機以 75 公尺距離及住宿日期比對照片，日期重疊而無座標僅為待確認候選。尚未完成逐筆訂房生命週期、既有 AI 重用或例外 MLX 授權流程。

**P0 最終策略：Zero MLX by Default（預設零呼叫路徑已實作；其他功能待完成）。** 預設只使用 GPS、Gmail 訂房生命週期及 EXIF 時間建立住宿候選，重用既有相容 AI 標記；不下載原圖、不呼叫 MLX。僅當特定照片預期能提供新的、足以解決飯店身份或入住證據缺口的資訊時，才經使用者同意追加有限 MLX 分析。一般客房／浴室／窗景分類或沒有可辨識文字的 OCR 不構成追加理由；證據不足時保留待確認。

1. 從完整同步的 catalog 讀取旅行範圍內 EXIF 時間、GPS、既有描述／標籤；保留來源與定位精度（若有），不下載原圖。
2. 本機以地理距離及時間聚類（可配置半徑，初始假設 50–100 m，須以實測校準），結合跨日、清晨／夜間重複出現及停留線索，產生住宿地點候選。單次路過不等於入住；密集市區相鄰飯店不得僅靠半徑合併。
3. 由旅行助手在自身層以 Gmail 訂房／入住／退房日期及飯店地址或座標比對聚類，保留取消與衝突；公開地圖查詢遵循既有授權與隱私限制，只傳飯店名稱、城市、國家，不傳照片 GPS。
4. **過渡基準：**每群依既有住宿標籤／描述選 1–3 張樣本；新 metadata-only 工作不送任何樣本至 MLX。初始半徑 75 公尺、最多相差 48 小時；缺 GPS 或拍攝時間不合群。群組數、GPS 覆蓋、樣本數與預估分析減量會顯示在工作結果，工作項目嘗試與失敗數會在分析後統計。**尚未實作：**重用既有相容 AI 結果、可配置半徑、依 booking/GPS 信心跳過 MLX，以及不確定時動態擴充樣本。工作項目嘗試數不保證等同 MLX 服務端實際執行數。
5. 缺 GPS 的照片可按時間鄰近、可信的既有照片線索連結候選，但需標記推論來源；GPS 缺漏、漂移、地址衝突或跨日證據不足時不得硬判，必要時使用 MLX／OCR 補充。OCR 為輔助而非必要條件。
6. 報告須顯示掃描 metadata 筆數、GPS 覆蓋率、聚類數、候選與代表樣本、實際 MLX 呼叫／重試次數、快取重用數、未分析原因、失敗數及對照基準節省比例。保留逐張證據、人工確認與唯讀保障。

驗收目標（尚未量測，需以相同固定候選快照做 A/B 驗證）：

| 指標 | 目標 |
| --- | --- |
| MLX 呼叫量 | 預設 0 次、原圖下載 0 次；例外須記錄證據缺口、預期資訊增益、授權及實際呼叫／重試量 |
| 正確性 | 名古屋與京都大阪已知住宿均應保留為候選；不得將取消訂房或鄰近飯店誤認為入住 |
| 無飯店名稱照片 | GPS、時間與入住證據一致時仍可產生可核對候選 |
| 缺 GPS／位置衝突 | 明確列為待確認，允許有限 MLX 補充；若預算用盡仍未知，報告明列 |
| 效能 | 比較端到端耗時、原圖下載數與 MLX 成本；不得以略過必要證據換取節省 |

驗收以實際住宿飯店與住退日期的正確性、候選召回率、誤判率、未知率及每間有效辨識住宿的 MLX 成本為主，不以分析照片數作為成功指標。固定每群 1–3 張的現有做法僅為過渡基準，不是最終預設策略；不能因證據不足就盲目追加 MLX。現有逐張分析工作保留作為基準，不中斷或覆寫。

### P0 新需求：EXIF Signature Detection & Temporal GPS Inference

**狀態：2026-11-22 使用者同意，待實作。** 目的為補足 B612 等第三方相機 App 的 GPS 缺漏，維持零 MLX、零 OCR，不使用浮水印影像辨識。

- 優先使用原始 GPS。僅對無 GPS 的 JPEG 讀取本機檔頭及 EXIF，不解碼像素、不下載原圖至外部服務。現有 metadata-only 路徑維持零原圖下載；若本機檔頭不可讀，保留未知。
- 初始 B612 歷史樣本 signature：1920×2560 或 2560×1920、JFIF 1.01、EXIF big-endian（MM）、APP13 `Photoshop 3.0`、缺 Camera Make/Model 與 GPS。這些均非 B612 專屬標記；組合吻合僅記為 `suspected_b612`／signature match，不宣稱已證明 App 來源。規則須版本化並以已知正反例校準。
- 改採 Temporal-Spatial Stay Inference（時間／空間停留區間推估）：GPS 與無 GPS 照片不必成對拍攝，不假設一對一對應，也不以最近時間照片直接代替位置。依同一可信來源的多個獨立原始 GPS 錨點建立候選停留區間，記錄起訖時間、空間範圍、最大錨點間隔及位置衝突；區間不得跨越已知移動或證據中斷。
- 無 GPS 照片的可信拍攝時間落在候選停留區間內時，才列為位置候選；即使前後錨點相近也不能證明全程未離開。單側錨點不足以建立區間，時間不足或位置衝突則保留 unknown。初始 PoC 可測試 10 分鐘最大間隔、30 m 空間直徑等參數，須盲測校準，不視為已驗證的高信心門檻。
- 來源政策：Mandy 的 iPhone 可使用 B612 和原生相機；WJLee 的 iPhone 僅使用原生相機（使用者提供的歷史使用習慣，非單張照片來源證明）。同裝置證據優先；不同裝置僅在另有可信共同停留證據時列為候選，不以相同備份目錄或同行假設證明共處。
- 時間政策：不以檔案修改時間冒充拍攝時間；無可信時間或時區資訊時保留未知。不得因 +1 小時（或其他偏移）提高近鄰配對數而認定時區錯誤；僅在獨立時間證據支持時校正並記錄原值、偏移、依據及適用期間，不預設整趟旅行固定偏移。
- 保存 `gps_source`（original/inferred/unknown）、候選停留區間與位置範圍、原始錨點照片 ID、來源／共同停留證據、時間不確定性、規則版本及信心等級；推估結果不得再作為定位錨點，不覆寫原始 EXIF/GPS。推估結果僅作住宿輔助候選；現有 75 m 自動標籤寫入仍只接受原始 GPS，推估寫入需另行核准及驗收。
- 驗收：使用 2018/2019 歷史無 GPS 照片及合成正反例，測量 signature 誤判、停留區間候選覆蓋率、錯誤地點歸屬率與定位誤差（遮蔽已知 GPS 做盲測）。測試不成對照片、不規則拍攝、離開後返回、長間隔、來源混用、不同裝置分開行動、時區錯誤及原始 GPS 保護；不得以增加配對數作為時區校正或準確率驗收依據。MLX/OCR 呼叫均須為 0；真實私人照片不得提交產品 repo。

### P0 最終資料責任：旅行助手確認後直接寫入旅行紀錄

**已同意需求，待完成整合。** Photo Tagger 是唯讀照片證據服務；旅行助手是住宿事實核對與旅行紀錄寫入層。正常流程不要求將飯店座標、Gmail 訂房事件或已確認住宿再次匯入 Photo Tagger。

- Photo Tagger 提供 GPS／時間群組、各群拍攝日期範圍、照片數、證據參考及零 MLX 統計。現有外部 API 不回傳精確照片 GPS；待新增獨立、明確授權的最小必要群組位置摘要或本機比對介面，禁止未授權釋出位置。
- 旅行助手在自身層查核 Gmail 訂房生命週期、公開飯店地址／座標與照片群組位置及日期；只在必要且經同意時查公開地圖，不對地圖服務傳送私人照片 GPS。保留取消、衝突及未知狀態。
- 旅行助手顯示住宿名稱、分店、地址、住退日期、來源與不確定性，交使用者逐項確認。未確認不得寫成住宿事實，也不因同名取消而排除其他訂房。
- 使用者確認並授權後，旅行助手直接更新 ChatGPT repo 的 `travels/` 對應旅行紀錄及住宿總表，保留可追溯來源、確認狀態與日期，避免重複項目；不必反向同步飯店座標或最終住宿到 Photo Tagger。
- v0.4.29/30 External Evidence API 與本機座標比對仍保留為可選相容功能，不是最終流程的必要步驟。不得因此修改 Synology Photos 原圖、標籤或描述。

驗收：使用同一旅行資料，在不匯入飯店座標、不呼叫 MLX、不下載原圖的情況下，由旅行助手完成核對並待人工確認；確認後寫入旅行 repo，重送不重複新增。未獲確認時只輸出待核對候選。照片標籤寫入另依下列獨立授權流程，不屬於唯讀分析工作。

### P0 新需求：人工確認住宿後的照片標籤寫入

**狀態：2026-11-22 使用者同意；預覽及新增標籤 API 已實作（尚未上線），批次撤回與持久稽核待完成。** 住宿事實仍由旅行助手及旅行 repo 管理；唯讀分析不修改照片。獨立、明確授權的住宿標籤寫入流程須同時符合：

1. 飯店名稱、分店及住退日期已由使用者確認。
2. 照片拍攝日期（飯店當地日期）在入住至退房日之間（含首尾）。
3. 照片有效 GPS 與經核實的飯店座標之大圓直線距離 ≤ 75 公尺。缺 GPS、日期或飯店座標、超出範圍、定位衝突或多飯店重疊未釐清均不得自動寫入。

- 預覽列出確切照片 ID、檔名、日期、距離及擬新增標籤 `Hotel: <飯店名稱>`；寫入前重新核對相同條件，僅新增不存在的標籤，重送冪等。
- 不改原始照片、EXIF、GPS、時間、描述、既有標籤；不下載原圖、不呼叫 MLX。不把住宿期間所有照片一律標記飯店。
- 若外部 API 提供寫入，須使用獨立且預設關閉的最小權限 scope，與唯讀 token 分離，支援逐筆追蹤、寫入後驗證及僅撤回本次新增標籤。
- 驗收：大平原飯店 2018-06-21～22 的 `IMG_9099.JPG`（約 30 m）與 `IMG_9100.JPG`（約 33 m）應符合；75 m 邊界納入、超出或缺 GPS 排除；原標籤保持、重複請求不新增重複標籤。無命中照片仍保留已確認住宿紀錄。

API：`POST /api/v1/hotel-tags/preview` 和 `POST /api/v1/hotel-tags/apply`，僅 HTTPS、個人空間。設定與其他 Token 不同且至少 32 字元的 `PHOTO_TAGGER_HOTEL_TAG_API_TOKEN`，以及 `PHOTO_TAGGER_HOTEL_TAG_WRITE_ENABLED=true` 才授權 `travel:hotel_tag_write`，預設關閉。POST JSON 需 `confirmed:true`、`hotel_name`、`check_in`、`check_out`、`latitude`、`longitude`、`photo_ids`（1–100 個唯一 ID）。預覽回傳逐筆距離、資格、原因與 `expires`、`preview_token`；apply 須帶相同資料及這兩個欄位（15 分鐘內），重新讀回即時 metadata，變動則拒絕或跳過。結果逐筆區分 added／already_present／skipped／changed／unverified。只新增標籤，既有不同 Hotel 標籤衝突時跳過；旅行助手須先釐清重疊住宿。未提供自動撤回端點，不宣稱支援批次撤回。

### 證據分級與輸出格式

| 等級 | 判定條件 |
| --- | --- |
| 已確認 | 可辨識的入住憑證或人工確認，且飯店名稱與位置一致 |
| 照片佐證／高度可能 | 招牌或客房證據與 GPS、跨日活動或可核對的飯店資料一致；仍不等同訂房已確認 |
| 待確認 | 僅道路／GPS 或單張外觀，資料矛盾、缺少定位、飯店名稱無法辨識 |
| 排除 | 商場、餐廳、景點、路過飯店等無住宿證據 |

完整目標格式中的旅行群組 ID、飯店原名／當期名稱、現名（若更名）、地址、入住／退房日期、地址來源連結及分析版本尚未在 MVP 產生；未確認欄位應輸出 null／待確認。MVP 報告提供照片 ID、檔名、拍攝日期、catalog 地點、住宿線索、人工線索狀態及簡短描述。MVP 不顯示模型信心值，也不將同飯店名稱視為已核實的同一住宿。

### 安全與驗收

- 個人／共享空間及 NAS 帳號隔離；沿用唯讀照片存取、既有登入與 API 授權，分析預設 Dry run，不覆寫既有描述。若未來提供標籤寫入，須獨立確認並透過 Photos API 讀回核對。
- 原圖不持久化於工作資料庫或匯出 repo；不保存房號、門鎖碼、QR 碼、訂單編號、姓名、證件、帳密或 OCR 原文。入住文件優先私有 MLX 分析；外部 OCR 或外部地理查詢須先明確告知並取得同意，僅傳必要欄位。
- 測試：已知飯店正例、只有餐廳／路過的反例、多飯店同一趟、無 GPS、歷史更名、錯誤時區、重複照片、分頁與中斷續跑、帳號隔離、敏感欄位遮蔽、匯出一致性。
- 首批以已核實的飯店招牌、入住畫面與客房照片作正例，以只有 GPS、曾更名飯店及路過飯店作待核對候選，再處理其他歷史日期群組。驗收不得以推測填補所有未知飯店；真實個人旅行證據不得提交產品原始碼 repo。

公開地圖查詢使用 [Nominatim 使用政策](https://operations.osmfoundation.org/policies/nominatim/)所述的使用者觸發查詢、明確 User-Agent、快取、每秒最多一筆及 attribution 要求。使用者每次查詢均可略過；不會批次或背景查詢。

## UC-06 外部 AI 工作管理 API

**狀態：** v0.4.26 提供唯讀旅行工作 MVP。它讓 Llm-Cli-APIServer 等授權客戶端建立、啟動、監控及下載 UC-05 工作結果，不必使用瀏覽器登入；不擴張現有唯讀 Metadata Token 權限。

### MVP 啟用方式

- 產生獨立 Token：`python3 -c 'import secrets; print(secrets.token_urlsafe(48))'`，將相同值存入本機 `.env` 的 `PHOTO_TAGGER_JOB_API_TOKEN` 與 Container Manager repo 的 GitHub Actions secret。`.env` 權限應為 `600`；兩處都不得提交 Git 或寫入日誌。部署 workflow 將 Token 寫入 NAS `.env` 後重建容器。Token 至少 32 字元，必須與 `PHOTO_TAGGER_API_TOKEN` 不同；空白／缺少 Token 時 API 停用。
- 外部 API 固定綁定目前已註冊受信任裝置的 NAS 帳號，MVP 只允許其個人空間。建立與啟動工作前需有完整同步的本機 metadata catalog 及可用的 NAS 受信任工作階段。
- 目前部署預設授予 `travel:map_lookup`。此 scope 代表使用者同意 API 把明確指定的候選飯店名稱、城市與國家傳送到 Nominatim；不需 Web UI checkbox。每次 API 請求只查指定候選，沿用 24 小時快取、全服務每秒一筆新查詢上限與 attribution，不會背景批次查詢。若要停用地圖查詢，從 `PHOTO_TAGGER_JOB_API_SCOPES` 移除此 scope 並重建容器。
- API 僅接受 HTTPS 與 `Authorization: Bearer <PHOTO_TAGGER_JOB_API_TOKEN>`，每 Token 每分鐘最多 60 個請求。Metadata Token、無效 Token、scope 不足、跨 owner 的工作 ID 都會被拒絕。API 報告不回傳照片原圖或照片精確 GPS。

### 已實作的唯讀端點

| 方法／路徑 | 行為 |
| --- | --- |
| POST `/api/v1/jobs` | 只接受 `travel_stay` 與 `personal`；需 `Idempotency-Key`（8–128 字元），重複 key 和相同內容回傳原工作，不同內容回傳 409 |
| POST `/api/v1/jobs/{job_id}/start` | 啟動旅行住宿分析；重複 start 在工作執行中會回傳目前狀態 |
| GET `/api/v1/jobs/{job_id}` | 回傳 owner 範圍內的狀態、逐張分析結果、群組與住宿候選；不回傳照片原圖、GPS 或縮圖內部快取鍵 |
| GET `/api/v1/jobs/{job_id}/report?format=json` 或 `format=markdown` | 下載已清理的旅行報告 |
| POST `/api/v1/jobs/{job_id}/lodging-candidates/{candidate_key}/map-search` | 需 `travel:analyze` 與 `travel:map_lookup`；直接查指定候選並回傳候選、attribution 及隱私說明 |

建立工作的 JSON 欄位為 `work_type`（固定 `travel_stay`）、`space`（固定 `personal`）、`country`、`date_from`、`date_to`、`max_candidates`。地圖查詢可傳 `hotel_name` 與 `city` 覆寫候選值；國家取自工作條件。API 不會自動查詢所有候選，也不會寫入 Synology Photos。

呼叫範例（以 Llm-Cli-APIServer 的受保護環境變數提供 Token）：

```sh
curl --fail-with-body -X POST "$PHOTO_TAGGER_API_URL/api/v1/jobs" \
  -H "Authorization: Bearer $PHOTO_TAGGER_JOB_API_TOKEN" \
  -H 'Idempotency-Key: japan-trip-2026-11-v1' \
  -H 'Content-Type: application/json' \
  -d '{"work_type":"travel_stay","space":"personal","country":"日本","date_from":"2026-11-01","date_to":"2026-11-07","max_candidates":100}'

curl --fail-with-body -X POST "$PHOTO_TAGGER_API_URL/api/v1/jobs/$JOB_ID/start" \
  -H "Authorization: Bearer $PHOTO_TAGGER_JOB_API_TOKEN"

curl --fail-with-body "$PHOTO_TAGGER_API_URL/api/v1/jobs/$JOB_ID" \
  -H "Authorization: Bearer $PHOTO_TAGGER_JOB_API_TOKEN"

curl --fail-with-body "$PHOTO_TAGGER_API_URL/api/v1/jobs/$JOB_ID/report?format=markdown" \
  -H "Authorization: Bearer $PHOTO_TAGGER_JOB_API_TOKEN"
```

若 Token 獲授 `travel:map_lookup`，Client 可對回傳的住宿候選逐筆呼叫 `POST /api/v1/jobs/$JOB_ID/lodging-candidates/$CANDIDATE_KEY/map-search`，JSON body 可提供 `hotel_name` 與 `city`。同一個 Idempotency-Key 必須重用於完全相同的建立請求；不同條件請使用新 key。

### 權限與安全

- 專用工作 API Token 與既有 `PHOTO_TAGGER_API_TOKEN` 分離；Token 空白時預設停用，HTTPS only、最少 32 字元高熵 Token，不得提交 Git 或記錄明文。
- 權限分開：`travel:analyze`（UC-05 唯讀分析）、`travel:map_lookup`（代表使用者同意 API 將飯店名稱、城市與國家送至 OpenStreetMap Nominatim 查詢）、`ai:analyze`（一般 AI dry run）、`ai:write`（實際標記／描述寫入，獨立啟用與明確確認）。唯讀 Token 不可寫入照片或執行一般 AI 寫入工作；沒有 `travel:map_lookup` 的 Token 不可查公開地圖。
- 綁定既有受信任裝置與固定 NAS 帳號／個人空間；每個工作建立、狀態、結果與控制操作都驗證 owner 及 scope。不提供 NAS session、原圖、帳密或敏感 OCR 原文。
- 使用既有工作引擎、固定候選快照、工作上限及持久化狀態。限制併發與速率；用 idempotency key 避免重複建立及重複寫入；寫入工作必須先 dry run 並確認同一快照及影響項目。
- `travel:map_lookup` 可讓外部 API 直接發起公開地圖查詢，不需瀏覽器 checkbox；Token 設定／授權時即代表使用者同意傳送上述欄位。每次 API 呼叫只查指定住宿候選，不傳照片、精確 GPS 或 NAS 帳號；沿用 24 小時快取、全服務每秒最多一筆新 Nominatim 請求及 attribution。不得在背景或未經 API 呼叫時批次查詢；OSM 結果仍只是地點線索，不代表實際入住或官方核實。

### API 契約與後續階段

| 方法／路徑 | 行為 |
| --- | --- |
| POST `/api/v1/jobs` | 已實作：建立限定 `travel_stay`、個人空間的旅行工作；需 `Idempotency-Key` |
| POST `/api/v1/jobs/{job_id}/start` | 已實作：啟動唯讀旅行住宿分析 |
| GET `/api/v1/jobs/{job_id}` | 已實作：讀取工作狀態、逐張結果、群組與住宿候選 |
| POST `/api/v1/jobs/{job_id}/lodging-candidates/{candidate_key}/map-search` | 已實作：需 `travel:map_lookup`；直接查指定候選並回傳 attribution |
| GET `/api/v1/jobs/{job_id}/report?format=json` 或 `markdown` | 已實作：下載已清理報告 |
| POST `/api/v1/jobs/{job_id}/pause`、`resume` | 後續階段 |
| 一般 AI 分析／Photos 寫入 | 後續評估；目前 API 不提供 |

錯誤應明確區分未啟用、無效 Token、scope 不足、catalog 未完整同步、日期／上限無效、NAS 受信任登入不可用、工作不存在或非本帳號、併發與速率限制；不回傳敏感資訊。

### 開發順序與驗收

1. v0.4.26 MVP：提供 UC-05 唯讀工作建立、啟動、進度、報告及受 `travel:map_lookup` scope 保護的單筆公開地圖查詢；後續再加入暫停及續跑，最後才評估一般 AI 標記寫入。
2. 用日本歷史旅行日期區間（例如一週）驗證候選選取、MLX 分析、旅行群組與報告；每日均衡取樣、無 GPS 照片處理、異名／同名飯店分離、non_lodging 排除及敏感欄位過濾列入 UC-05 改善驗收。Web UI 查詢仍須逐筆 checkbox 同意；API 查詢須先授予 `travel:map_lookup` scope，並由每次 API 呼叫明確觸發。
3. 發佈前驗證既有 Metadata Token 無法建立工作、跨 owner 拒絕、scope 不足、重複請求、敏感資訊遮蔽及未啟用時的拒絕行為。
4. 先於測試環境驗證，再部署；以 Llm-Cli-APIServer 實際建立唯讀工作並取得報告，才標示 UC-06 發佈完成。取得報告後由使用者另行授權更新旅行 repo。

## Docker 版本與部署

本機 metadata catalog 提供查詢介面。使用者可分別同步個人空間與共享空間；服務每頁列出最多 100 張照片，再以 Photos API 批次取得 EXIF、描述、GPS／地址、標籤與 Synology Photos 人物，保存至 `/data/app/photo-catalog.sqlite3`。同步可在容器重新啟動後續跑；只有完整同步才更新「最近完成」時間。每個 NAS 帳號與空間的資料以帳號雜湊隔離。catalog 只保存 metadata，不下載或保存原圖；查詢結果的縮圖仍由已登入的 Photos API 即時代理，並不存入 catalog。同步目前涵蓋照片項目，不含影片。由於 Photos API 使用 offset 分頁，若掃描時 NAS 照片庫同時新增項目，請在新增完成後再次同步；catalog 不會自動刪除 NAS 上已不存在的舊項目，避免把分頁位移誤判為刪除。

### 如何查詢本機 catalog

1. 登入 Photo Tagger，在「照片庫」展開「本機 metadata 目錄」，選擇個人或共享空間，再按「同步完整目錄」。首次同步會逐頁讀取該空間照片；服務中斷或容器重啟後，再按「繼續同步」。需要更新全庫資料時，可在完成後再次按「重新同步完整目錄」。
2. 同步後在同一區塊輸入條件。多個條件會以 AND 組合：關鍵字搜尋檔名、描述、相機與鏡頭；國家和地點對 metadata 欄位做部分比對；標籤與人物採完整名稱比對；日期區間依台灣時區的拍攝日期判斷，起訖日期都包含。結果依拍攝時間由新到舊排序，每頁 24 張。
3. 若要在容器內用 Python 直接唯讀查詢，可執行下列指令。程式會提示輸入同步時使用的 NAS 帳號，帳號只用來選取自己的 catalog 分區，不會寫入資料庫；查詢不會連線 NAS，也不會修改 catalog。

```sh
docker exec -it SYNOLOGY-PHOTO-TAGGER python /app/scripts/query_photo_catalog.py \
  --space personal --date-from 2026-01-01 --date-to 2026-11-30 --tag '產品'
```

可用條件為 `--keyword`、`--date-from`、`--date-to`、`--country`、`--location`、`--tag`、`--person`、`--space`、`--limit` 與 `--offset`。關鍵字、國家、地點為部分比對；標籤與人物為完整名稱比對。輸出是 JSON，包含已收錄 metadata、查詢筆數及同步狀態。容器內 DB 路徑為 `/data/app/photo-catalog.sqlite3`。

v0.4.19 在「照片候選清單」的單張 metadata，以及已成功寫入且 AI 建議含「產品」的「工作結果」卡片中提供拍攝地點附近店家入口；只有使用者展開區塊時，才向 Photos API 核對照片目前仍有「產品」標籤，再依 GPS 呼叫 Photon／OpenStreetMap 查找 500 公尺內的商店候選。清單合併同址同名的重複地圖項目，顯示繁體中文譯名、原始地圖名稱、店家類型與約略距離，並附 OSM attribution。翻譯只把公開店名與類型送到私有 MLX `/exec`；不傳照片或座標。OSM 查詢結果只在 Photo Tagger 記憶體中快取 6 小時，不會寫入 Synology Photos，也不代表購買店家。查詢失敗或翻譯無結果時保留地圖原名。

v0.4.17 將連線提醒改為條件式：只有瀏覽器透過非 loopback 的 HTTP 存取時顯示；HTTPS 與 localhost／loopback（包含 SSH tunnel）不顯示。正式部署會拒絕使用 HTTP 的 `SYNOLOGY_URL`，確保伺服器到 NAS API 使用已驗證的 HTTPS。

v0.4.16 修正拍攝日期篩選：Synology Photos 要求將 `time` 與 `item_type` 作為頂層 JSON 編碼欄位傳入 `list_with_filter`。舊版將條件包在未支援的 `filter` 欄位中，NAS 靜默忽略日期篩選，並回傳整個資料庫；工作掃描最新 4,000 項後因此錯誤顯示 0 張。已在 NAS 唯讀實測 2024-01-08 至 2024-12-31 篩選回傳 3,336 張，且找到 `IMG_2500.JPG`（拍攝日期 2024-08-05）。

v0.4.15 修補 Docker Scout 標示可修補的高風險相依套件：升級 `cryptography`、`jaraco-context`、`setuptools`、`wheel`，並以官方 Tailscale v1.104.5 原始碼建置 `tailscale`／`tailscaled`，將 `klauspost/compress` 與 `golang.org/x/net` 固定至已修補版。v0.4.14 因 setuptools vendored 副本仍帶有舊版 wheel 與 jaraco-context 而未部署。Scout 於 2026-11-07 對 amd64／arm64 複掃確認可修補 Critical／High 為 0；每個架構仍有 4 項未修補 High（zlib：CVE-2026-76844、CVE-2026-85091；u-root：CVE-2020-7665、CVE-2020-7669）、7 Medium、41 Low 與 1 unknown。

v0.4.13 加強容器執行安全：Gunicorn 以非 root UID/GID 執行，照片資料夾保持唯讀掛載，Web 埠預設只綁 NAS loopback；正式部署要求 HTTPS，並將 MLX 與 Tailscale 金鑰改由 host secret 檔唯讀提供。Compose 另限制記憶體與程序數，並移除不需要的 `NET_RAW` capability。舊 SQLite 與排程密文會在啟動時遷移至 `/data/app`，保留既有排程與工作資料。

v0.4.8 已發佈：預設略過有 Photo Tagger AI 描述或 AI 標籤成功寫入紀錄的照片；單純批次更名標籤不計入略過。被略過照片不會進入 AI 分析，也不會寫入描述或其他標籤。

v0.4.9 將照片清單改為「照片庫」，移除登入區的步驟編號，並把 AI 標記與批次更改標籤整合到「建立工作」的工作類型切換器。v0.4.10 加入候選上限 500、800、1000 張選項，以及每天依指定時間執行的定期 AI 標記；排程可在使用者登出後執行，容器重啟後可復原 NAS 登入。排程加密金鑰由 NAS 部署流程建立，唯讀掛載到容器。v0.4.11 將 UX-Deck Lucide squirrel 設為瀏覽器 favicon。v0.4.12 讓每日排程透過 Photos API 日期篩選只查詢執行日與前一日的照片。照片庫篩選只影響目前顯示清單；AI 標記工作仍在建立工作區獨立設定條件。批次更改標籤的進度及完成摘要會同步顯示在「工作結果」。

歷史版本 v0.4.7。本版把 AI 標記工作從購物判斷改為一般照片描述與標籤，加入自動寫入、Dry run 及 Photos API 讀回核對；有效結果不需逐張確認。單張 AI 分析也會自動寫入有效結果。若照片已有描述，保留原文並略過描述更新；標籤可新增及核對。Docker Hub 與 NAS Compose 均使用 `v0.4.7`。以下保留歷史功能摘要：v0.4.0 新增 AI 標記工作：依個人或共享空間、日本地點及既有標籤建立固定候選快照；逐張分析購物情境，展示縮圖、判斷理由與信心分數；人工可接受、略過，或選擇目前空間的既有標籤／新增「購物」標籤。只有人工接受後再按「寫入已接受項目」才會透過 Photos API 寫入，並逐張讀回核對。工作可下載 JSON 報告、安全重跑分析失敗項目，或撤銷該工作實際新增的標籤。標籤寫入可能改變照片原檔 metadata；撤銷只移除工作新增的標籤，不會復原檔案位元組或其他 metadata。候選最多 300 張、最多掃描 40 頁；達上限時工作會註明快照不完整。工作資料與報告存在 `/data/photo-tagger.sqlite3`，Compose named volume `tagger-data` 會跨容器重建保留；原圖與 OCR 原文不會存進工作資料庫。v0.4.1 讓瀏覽器登入在閒置 12 小時內持續有效；簽章金鑰自動保存於 `tagger-data` volume，不保存 NAS 密碼或 OTP。容器重啟會清除記憶體中的 NAS API session，屆時仍需重新登入。v0.4.2 的照片候選清單會標出 Photo Tagger 成功新增且目前仍存在的標籤，來源包含單張寫入與標記工作；已撤銷的工作標籤會排除。v0.4.3 的 AI 標籤規則明確區分「證件」與「文件」：「證件」只指用途在辨識或證明持有人身分的正式證件；一般報告、表格、收據或檢驗單，即使含姓名或編號，也歸為「文件」或更具體的內容。v0.4.4 新增批次更改標籤：從目前空間選擇已存在的來源與目標標籤，掃描來源標籤的所有照片並先顯示影響筆數，再一次確認執行；服務以每批最多 25 張分段處理，每張先新增並讀回確認目標標籤，再移除來源標籤並讀回核對。中途結果不確定的項目會標示需人工核對。v0.4.5 將標籤批次更改移到背景工作執行，瀏覽器以短輪詢顯示進度及逐張異常，避免整批 Photos API 請求被閘道逾時；工作狀態存在服務記憶體中，容器重啟後若狀態遺失，重新掃描來源標籤即可核對尚未完成的照片。Docker Hub Repository overview 的同步稿位於 [`DOCKERHUB.md`](DOCKERHUB.md)。

此版本提供繁體中文 Web 首頁、Photos API 瀏覽、單張照片 AI 分析預覽，以及 AI 標記工作。使用者可在 UI 輸入 NAS 帳密（支援選填 OTP），登入後切換個人空間／共享空間，以分頁方式查看照片 ID、檔名、拍攝時間、地點及既有標籤；縮圖由本站代理顯示，metadata 按需從 Photos API 取得。候選清單可依日本地點與既有標籤篩選。登入工作階段和篩選索引只保存在服務程序記憶體中；工作快照、分析摘要、審核結果及 Photos 寫入回讀狀態保存在 SQLite named volume。

點選照片卡片的「本機 AI 分析」後，服務以 Synology Photos API 讀取單張原圖，記憶體暫存後以單一 `/photo-analyze` 請求上傳到 Tailscale 私有網路中的 Mac-mini MLX。若視覺分析判斷內容為掃描文件，Mac-mini 會用同一份請求暫存影像接續 OCR，無須再從 Photo Tagger 重傳。HEIC/HEIF 會在 Mac-mini 轉成暫存 JPEG，供視覺分析和 OCR 共用。原圖與 OCR 結果不寫入容器磁碟、Synology Photos 或照片檔案。描述、標籤與 OCR 文字僅顯示在候選清單。每張原圖限制 30 MiB；超出上限需先使用其他工作流程處理。

日本篩選依 `additional.address.country` 回傳值比對；沒有國家地點資料的照片不會列入結果。原圖分析只在使用者逐張點選後執行，不會自動掃描相簿。

1. 複製 `.env.example` 為 `.env`，填入 NAS 的 DSM 根網址、照片目錄路徑，並依設定將 MLX API key 與 Tailscale reusable auth key 放在 host secret 檔（預設位於 `${NAS_DOCKER_ROOT}/mlx-server-api-key` 與 `${NAS_DOCKER_ROOT}/tailscale-authkey`）。金鑰不得放進 `.env` 或提交到 Git。MLX API key 必須與 Mac-mini 部署所用的值相同。Tailscale 節點狀態會保存在 Docker named volume，容器重建後沿用同一節點身分。MLX 請求透過 `MLX_HTTP_PROXY` 指定的本機 HTTP proxy 連入 Tailnet；Synology Photos API 流量不經 proxy。`MLX_SERVER_URL` 預設為 `http://mac-mini.tail28f10.ts.net:5001`。NAS 的 `SYNOLOGY_URL` 必須使用可由容器連線且 TLS 憑證可驗證的網址；此 NAS 可使用 `https://wenchiehlee.synology.me:7778`。
2. 執行 `docker compose up -d --build`。
3. 本機 HTTP 開發可瀏覽 `http://localhost:5056`；NAS 正式部署預設只監聽 `127.0.0.1:5056`，請透過 DSM HTTPS 反向代理存取。部署 workflow 會設定 `APP_HTTPS_ONLY=true`，拒絕經 HTTP 登入。
4. 按「探索 Photos API」確認模組後，在登入區輸入有 Synology Photos 權限的 NAS 帳號與密碼；有啟用雙重驗證時輸入當次 OTP。然後選擇空間並載入照片清單。
5. 先選一張照片按「本機 AI 分析」，確認單張建議流程可用。
6. 若要批次建立購物標籤，套用空間、地點及標籤篩選後，在「AI 標記工作」建立工作並先檢視固定候選快照。
7. 按「分析尚未完成的照片」後逐張查看縮圖和證據；接受時可選擇現有標籤或「購物」。最後按「寫入已接受項目」才會開始寫入。工作詳情可下載報告、重跑失敗分析或撤銷工作新增的標籤。

本機開發的 Compose 範例會關閉 HTTPS 強制檢查以供 `localhost` 使用；不要將此設定用於公開網路。正式 NAS 部署只允許經 DSM HTTPS 反向代理登入，並以 loopback 綁定限制直接連線。NAS API 端連線會驗證 TLS 憑證，不支援關閉驗證。

Compose 預設將個人空間 `/volume1/homes/wjlee/Photos` 唯讀掛載至容器的 `/Photos`。AI 分析使用 Photos API，不讀取該掛載路徑。Tailscale 使用 userspace networking 和只綁定容器 loopback 的 HTTP proxy，不需要 `NET_ADMIN`、`NET_RAW` 或 `/dev/net/tun`。`publish-image.yml` 可由 GitHub Actions 手動觸發，將多架構映像發佈至 `wenchiehlee1020/synology-photo-tagger`；需要設定 `DOCKERHUB_USERNAME` 與 `DOCKERHUB_TOKEN` repository secrets。

### v0.4.10 定期工作與受信任裝置

定期 AI 標記需要 DSM 支援的 Synology `SYNO.API.Auth` v6 受信任裝置登入。第一次登入時勾選「註冊此裝置供定期工作登入」，並輸入當次密碼與 OTP；Photo Tagger 會註冊 `Synology-Photo-Tagger` 裝置識別碼。TOTP 不會保存。為了讓 DSM 可在沒有 OTP 的情況下核發登入工作階段，NAS 密碼會與裝置識別碼一起使用 Fernet 加密，密文保存在 `/data/nas-schedule-credentials.enc`。

DSM 登入 API 文件說明 v6 可註冊裝置識別碼，之後以同一裝置名稱和 ID 登入時略過 OTP：[Synology DSM Login Web API Guide](https://global.download.synology.com/download/Document/Software/DeveloperGuide/Os/DSM/All/enu/DSM_Login_Web_API_Guide_enu.pdf)。

加密金鑰必須由管理者在 NAS 主機建立一次，不能放在 `.env`、Git 或 `tagger-data` volume。範例：

```sh
mkdir -p /volume1/docker/synology-photo-tagger
umask 077
python3 -c 'import base64,secrets; print(base64.urlsafe_b64encode(secrets.token_bytes(32)).decode())' > /volume1/docker/synology-photo-tagger/nas-schedule-key
chmod 600 /volume1/docker/synology-photo-tagger/nas-schedule-key
```

將 `.env` 的 `NAS_SCHEDULE_KEY_SOURCE` 指向這個檔案，再重新建立容器。Compose 會將檔案唯讀掛載到 `/run/secrets/nas-schedule-key`；唯讀掛載不會加密主機上的來源檔，因此應限制主機檔案權限並納入 NAS 備份保護。遺失金鑰會使既有密文無法解密；請先移除此服務保存的裝置資料，再以新金鑰重新註冊。DSM 可從帳號的雙重驗證受信任裝置管理頁撤銷該裝置。按「移除此服務的排程登入資料」只刪除 Photo Tagger 內的密文，不會撤銷 DSM 裝置授權。

### Debug shell

需要直接進入容器執行 `/bin/sh` 或 `/bin/bash` 時，將 `.env` 的 `DEBUG_SHELL` 設為 `true`。先在 `DEBUG_SSH_DIR` 指向的 NAS 目錄建立 `authorized_keys`，放入可信任的 SSH **公鑰**，再重新建立容器。SSH 僅接受公鑰；主機端 debug 埠只綁定 `127.0.0.1`，不會直接暴露在區網。從遠端電腦先建立 NAS SSH port-forward，再連線至容器：

```sh
ssh -N -L 2223:127.0.0.1:2223 <NAS-username>@<NAS-host>
ssh -i <private-key> -p 2223 root@127.0.0.1
```

若使用不同 `DEBUG_SSH_PORT`，請同步調整第一行本機轉送埠與第二行連線埠。完成除錯後將 `DEBUG_SHELL` 設回 `false` 並重新建立容器；一般模式不會啟動容器內的 SSH server。

### 唯讀 Metadata API（Llm-Cli-APIServer）

此介面預設停用。管理者在本專案和 Llm-Cli-APIServer 的 .env 設定相同的 `PHOTO_TAGGER_API_TOKEN`（至少 32 字元，建議用 `python3 -c 'import secrets; print(secrets.token_urlsafe(48))'` 產生），並於 Photo Tagger 設定頁註冊受信任裝置供排程登入。設定持有人即為 API 查詢的個人照片空間帳號。請保護 Token，不得提交 Git；更換帳號時應旋轉 Token。重建容器後才會套用設定。

Llm-Cli-APIServer 的 `PHOTO_TAGGER_API_URL` 設為 Photo Tagger 的 HTTPS 根網址（不是 DSM 網址）。呼叫：
`GET /api/v1/metadata/photos?date_from=2026-11-12&date_to=2026-11-19&offset=0&limit=50`
並送出 `Authorization: Bearer <token>` header。只允許 HTTPS、個人空間、最長 31 日區間及每頁 100 張。回傳拍攝時間、地點、GPS、描述與標籤，不回傳影像或人物辨識名單。依 next_offset 和 has_more 逐頁讀取；缺少日期或超出日期範圍的項目不回傳。未啟用、未註冊受信任裝置回傳 503；無效 Token 回傳 401。此 API 不提供寫入操作或 NAS session。

### v0.4.27 — Metadata Catalog 同步修正

詳細 metadata 請求沿用單張照片查詢已使用的欄位，移除額外的 `orientation_original` 請求，並分為最多 20 張的批次；NAS 拒絕批次或回傳不完整時拆分查詢。同步失敗會顯示階段、offset 和 NAS 錯誤代碼（若有）；未完成頁面不會標記完成，可由原 checkpoint 繼續。此變更不修改原始照片或標籤。

### v0.4.28 — UC-06 Catalog API

沿用原有 HTTPS Job Bearer Token、每分鐘 60 次請求限制及受信任 NAS 帳號；僅個人空間。新增獨立 scopes，可透過 PHOTO_TAGGER_JOB_API_SCOPES 撤銷。

| Method | Endpoint | Scope |
|---|---|---|
| GET | /api/v1/catalog/status | catalog:read |
| POST | /api/v1/catalog/sync | catalog:sync |
| GET | /api/v1/catalog/sync/{run_id} | catalog:read |

POST JSON 為 {"space":"personal"}，回傳 202 與 run_id；同步已執行則回 409，請查狀態避免重複觸發。失敗或中斷後可 POST 續跑。狀態包含 scanned_count、photo_count、next_offset、status、error 及 last_success_at；run_id 路由只查目前工作，未知或舊 ID 回 404。只在 status=complete 後建立旅行住宿工作。同步只寫入本機 metadata catalog，不修改照片或標籤，也不啟動 MLX。若受信任登入失效，需重新註冊；不要求或回傳帳密。

### v0.4.29 — External Evidence API（UC-05/06）

旅行助手在外部查閱 Gmail 或旅行 repo，僅送出最小結構化住宿事實；Photo Tagger 不持有 Gmail 認證、不接收郵件原文、訂單號、房號或入住密碼。GET /api/v1/jobs/{job_id}/external-evidence 需 travel:analyze；POST 同一路徑另需 travel:evidence_write（明確授權才開啟）。沿用 HTTPS、Job Bearer Token、帳號隔離及速率限制。

POST JSON: {"source":"gmail","evidence_type":"booking_confirmation","hotel_name":"Example Hotel","country":"Japan","city":"Kyoto","check_in":"2026-11-12","check_out":"2026-11-16","booking_status":"booked","source_reference":"opaque-message-id","verification_status":"verified"}

支援 booking_confirmation/booked、check_in_confirmation/checked_in、checkout_confirmation/checked_out、cancellation/cancelled；source 為 gmail 或 travel_repo，地址可選。證據日期須與工作範圍重疊。重送完全相同的正規化證據回 200，新增回 201；取消／改訂保留不同來源事件。所有證據仍為 needs_review，verified 是客戶端查證聲明，不能自動證明實際入住。UI、JSON／Markdown 報告均獨立列出外部證據，不覆蓋 AI 結果或照片標籤。自動衝突判斷與照片關聯留待後續。
