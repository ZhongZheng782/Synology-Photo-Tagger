# Synology Photo Tagger

> 以 Apple Silicon 上的 MLX 視覺模型，為 Synology Photos 補上可搜尋、可攜且可驗證的 AI 標籤。

## 目標

這個專案讓使用者先利用 Synology Photos 已有的資料（地點、日期、資料夾、相簿與既有標籤）精準選出候選照片，再以本機 AI 理解影像內容，將可靠的結果寫成可長期保留的照片標籤。

成功不只是「AI 看得懂照片」，而是能在 Synology Photos 中自然搜尋，例如搜尋 `購物`、`寺廟`、`夜景` 或 `美食`，並且標籤不會被綁死在某一個資料庫或單一 AI 模型。

## 核心原則

1. **照片檔優先**：支援的圖片格式以 `XMP:Subject` 作為權威標籤欄位；需要相容其他相片軟體時，可同步寫入 `IPTC:Keywords`。
2. **Synology Photos 目錄只負責選片**：優先透過 Photos API 取得候選媒體與既有資訊；必要時才以內部資料庫做唯讀查詢。絕不直接寫入 Synology Photos 的資料庫。
3. **本機、可撤銷、可重跑**：每張照片由本專案的永久 `asset_id` 管理；模型輸出、分析版本與寫入結果均保留在本專案狀態庫，讓標籤可以審核、撤銷與重新產生。
4. **保留人工標籤**：AI 只新增或更新自己管理的標籤，不能覆寫使用者原有的標籤、描述、評分或拍攝資訊。
5. **詞彙受控**：模型不直接產生無限多同義詞；它先判斷概念與信心分數，再映射成固定、可搜尋的標籤，例如 `shopping` → `購物`。

## 使用案例

### UC-01｜依地點挑選，再判斷「購物」

**使用者故事**

> 我想找出所有地點在日本的照片，讓 AI 只替真正與購物有關的照片加入 `購物` 標籤。

**流程**

1. 從 Synology Photos 目錄篩出地點國家為日本的照片。
2. 以相片 ID、原檔路徑、修改時間與現有標籤建立候選工作清單。
3. MLX 視覺模型檢查每張照片是否有購物情境，例如商店貨架、商品、價格標籤、購物袋、百貨櫃位或收據。
4. 模型回傳結構化結果：是否為購物、信心分數、可解釋的視覺證據。
5. 高信心結果寫入 `購物`，低信心結果加入人工複核清單；不確定或不符合者不改檔。
6. 寫入後確認 Synology Photos 能以 `購物` 搜尋到該照片。

**建議閾值**

| 判定 | 動作 |
| --- | --- |
| 信心分數 ≥ 0.85 | 自動新增 `購物` |
| 0.60–0.84 | 建立待複核清單，不自動寫入 |
| < 0.60 | 不新增標籤 |

**驗收條件**

- 不是每張「在日本」的照片都被標為 `購物`。
- 已有人工作標籤的照片仍可被 AI 補標，而不會被略過或覆寫。
- 每筆變更都能追溯到模型版本、信心分數與處理時間。

### UC-02｜依日期區間找出證件與身分證照片

**使用者故事**

> 我想選擇一段日期期間的照片，請 AI 找出其中的證件照或台灣身分證照片，並為它們加上 `證件` 或 `身分證` 標籤，方便日後在 Synology Photos 搜尋。

**流程**

1. 使用者指定拍攝日期區間；Synology Photos 目錄只回傳該期間的候選照片。
2. MLX 視覺模型可在本機以 OCR／Vision 辨識文件類型，並依 taxonomy 只擷取白名單關鍵欄位；完整 OCR 原文只用於本次推論，完成後即丟棄。
3. 程式將分類結果映射為固定標籤：
   - 清楚可辨識的台灣身分證：新增 `證件` 與 `身分證`。
   - 其他官方或機構核發、可用於識別身分的文件：新增 `證件`。
   - 收據、票券、信用卡、會員卡、一般表單或無法確定的文件：不自動加標籤。
4. 高信心結果才寫入原始照片的 metadata；其餘列為待人工複核。
5. 寫入後可在 Synology Photos 搜尋 `證件` 取得全部證件類照片，或搜尋 `身分證` 縮小至台灣身分證。

**建議閾值**

| 判定 | 動作 |
| --- | --- |
| `身分證` 且信心分數 ≥ 0.98 | 自動新增 `證件`、`身分證` |
| `證件` 且信心分數 ≥ 0.95 | 自動新增 `證件` |
| 低於門檻或類型不確定 | 僅建立本機待複核項目，不寫入標籤 |

**隱私與安全規則**

- 推論只能在本機 MLX 執行；不得上傳影像或文件內容至雲端服務。
- 完整 OCR 原文不保存；僅將 taxonomy 白名單允許的結構化欄位寫入本專案的 scrambled DB，例如文件類型、發證機關或到期日。姓名、完整證號與其他未明確啟用的欄位預設不保存。
- 待複核清單不得產生可公開分享的縮圖、報告或連結。
- 不改變影像像素，不刪除既有 metadata，也不覆寫使用者原有標籤。

### UC-03｜依日期區間找出健康量測與醫療文件照片

**使用者故事**

> 我想選擇一段日期期間的照片，找出血壓或心率截圖、量測儀器照片，以及藥袋、處方箋、收據與健檢報告；並讓 Synology Photos 能搜尋 `健檢`、`血壓` 或 `心率`。

**流程**

1. 使用者指定拍攝日期區間；Synology Photos 目錄只回傳該期間的候選照片。
2. MLX Vision 先判斷是否為健康量測或醫療文件；對候選照片在本機進行 OCR，只擷取 taxonomy 白名單允許的關鍵欄位。
3. 程式將分類結果映射為固定標籤：
   - 血壓畫面或血壓機螢幕：新增 `健檢`、`血壓`；可擷取收縮壓、舒張壓、脈搏與量測時間。
   - 心率畫面或量測裝置截圖：新增 `健檢`、`心率`；可擷取 bpm 與量測時間。
   - 藥袋、處方箋、收據、健檢報告或健檢中心文件：新增 `健檢`。
4. 高信心結果才寫入標籤，並將允許的結構化欄位寫入 scrambled DB；其餘列為待人工複核。
5. 完整 OCR 原文不保存。日後查詢數值或產生摘要時直接讀 DB；只有影像內容、模型或 taxonomy 版本變更時才重新 OCR，單純寫入標籤或 Description 不會觸發重跑。

**建議閾值**

| 判定 | 動作 |
| --- | --- |
| 血壓或心率量測畫面，信心分數 ≥ 0.95 | 自動新增對應標籤並擷取白名單欄位 |
| 其他醫療文件，信心分數 ≥ 0.95 | 自動新增 `健檢` |
| 0.75–0.94 | 建立本機待複核項目，不自動寫入 |
| < 0.75 或類型不確定 | 不新增標籤 |

**隱私與安全規則**

- 推論只能在本機 MLX 執行；不得將影像、文件內容或健康資料上傳至雲端服務。
- scrambled DB 只保存照片識別、最新 `binary_hash`、分類結果、信心分數、模型／taxonomy 版本，以及啟用的結構化欄位；不保存完整 OCR 原文。
- 不對量測數值做醫療診斷或風險判讀；它們只用於個人檢索與整理。
- 待複核清單不得產生可公開分享的縮圖、報告或連結；使用者可先執行 dry run 確認範圍。

### UC-04｜已標籤照片的補充描述與資料庫索引

**使用者故事**

> 已經有 AI 標籤的照片，我想再執行一次 enrichment pass：依其標籤與 taxonomy 擷取需要的資料，更新 Synology Photos 的 Description 與本專案 DB，之後不必重新 OCR。

**流程與規則**

1. 從 Synology Photos API 找出具有本工具管理之標籤的照片，例如 `購物`、`證件`、`身分證`、`健檢`、`血壓`、`心率`；未標籤照片不納入此流程。
2. 依每個 taxonomy concept 執行相應的 Vision／OCR extraction；只有白名單欄位可寫入 scrambled DB。
3. 對可支援寫入 Description 的照片，寫入一行可搜尋的簡短 AI 摘要，例如 `AI Index: type=blood_pressure; sys=118; dia=76; pulse=68`。
4. Description 以可辨識的工具管理區塊更新：保留使用者原有描述，只替換本工具先前寫入的區塊，避免重複附加或覆寫人工內容。
5. 專案 DB 以 `asset_id`、Synology item ID、影像指紋、分析模型與 taxonomy 版本判斷是否可直接重用既有結果；單純 metadata 變動時不重新 OCR。
6. 寫入前提供 dry run、變更預覽與待複核清單；使用者可選擇只更新 DB、只更新 Description 或兩者皆更新。
7. DB 必須為 `asset_id`、Synology item ID、taxonomy concept、標籤、量測時間與數值欄位建立索引；相同照片的既有結果可直接查詢，讓日期區間、類型與數值範圍搜尋不需重新 OCR，也不需掃描整個 Synology 相簿。

### UC-05｜補齊既有相片庫，但不重複處理

**使用者故事**

> 我想分批處理多年相片庫；新照片日後也能加入流程，但已處理且原檔未變的照片不應再次耗費推論時間。

**規則**

- 工作狀態以 `asset_id`、Synology item ID、影像指紋、分析模型與 taxonomy 版本判定；檔案路徑與完整檔案雜湊僅作同步與版本偵測，不是永久身分。
- 影像內容變更、模型升級或 taxonomy 變更後，可明確選擇重新處理；單純新增標籤、更新 Description、改名或搬移照片時不重跑 AI。
- 既有非 AI 標籤不是「已完成」的唯一依據。

### UC-06｜人工複核與安全回復

**使用者故事**

> 我希望先看過不確定的結果，再決定是否寫入；如果模型誤標，也能只移除 AI 加入的標籤。

**規則**

- 複核清單必須顯示縮圖、建議標籤、信心分數與判斷證據。
- 只記錄並撤銷本工具新增的標籤，絕不刪除使用者原有資料。
- 在批次寫入前提供預覽（dry run）與可匯出的變更報告。

## 格式與儲存策略

| 媒體類型 | 標籤與摘要寫入位置 | 原因 |
| --- | --- | --- |
| JPG / JPEG / PNG / CR2 | `XMP:Subject`；必要時鏡像 `IPTC:Keywords`；`EXIF:ImageDescription` | 標籤與短 Description 可跟隨原檔，並可被 Synology Photos 搜尋。 |
| HEIC / CR3 / X3F | Synology Photos 標籤／Description adapter + scrambled DB | 不假設標籤或 Description 能可靠回寫到原檔。 |
| 影片 | Synology Photos 標籤／Description adapter + scrambled DB | General tag 與 Description 不會回寫到原始影片。 |

> Synology Photos 內部資料庫可協助找出候選媒體，但不是本工具的標籤寫入目標。

## 照片身分、檔案版本與分析紀錄

本工具不以完整檔案雜湊作為照片的永久身分：寫入 XMP、IPTC 或 Description 後，檔案位元組可能改變，即使影像內容完全相同。

| 欄位 | 用途 | metadata 寫入後是否變動 |
| --- | --- | --- |
| `asset_id` | 本工具產生的永久主鍵；標籤、分析與 extraction 全部連到它 | 否 |
| `library_scope` + `synology_item_id` | 日常與 Synology Photos 快速對應；區分個人與共享空間 | 通常否 |
| `original_path` | 找回原檔與同步用途，不能作為唯一身分 | 可能 |
| `binary_hash` | 完整檔案版本偵測；判斷原檔是否被修改 | 會 |
| `visual_fingerprint` | 由影像內容產生的 pHash 或 embedding；協助比對搬移、改名或 metadata 重寫後是否仍為同一影像 | 通常否 |
| `tagger_write_version` | 識別本工具最後一次 metadata／Description 寫入 | 會更新 |

### 對應與同步規則

1. 匯入候選照片時，先以 `library_scope` + `synology_item_id` 對應既有 `asset_id`。
2. 如 Synology item ID 不可用或照片重新匯入，才以 `visual_fingerprint`、拍攝時間、尺寸等資訊比對；可確認為同一影像時，更新 item ID 與路徑，而非建立新照片。
3. 寫入標籤或 Description 後，更新最新 `binary_hash` 和 `tagger_write_version`，但不改變 `asset_id`，也不建立新的 AI 分析結果。
4. Live Photo 以 Synology Photos 顯示的一個 logical item 對應一個 `asset_id`；其 HEIC／JPEG 與 MOV 為附屬媒體，不各自建立使用者可見的標籤記錄。

### 何時建立新的分析版本

「更新索引或 metadata」與「重新跑 Vision／OCR」是兩種不同操作。只有下列情況建立新的 analysis version：

| 事件 | 重新跑 Vision／OCR | 動作 |
| --- | --- | --- |
| 第一次處理新照片 | 是 | 建立第一筆分析紀錄 |
| 影像內容被裁切、修圖、替換，或 `visual_fingerprint` 明顯不同 | 是 | 建立新的分析版本 |
| 模型、prompt、OCR pipeline 或 taxonomy 規則更新 | 視受影響的 concept | 只重跑相關分類／擷取任務 |
| 前次失敗、低信心、人工判定錯誤，或使用者強制重跑 | 是 | 建立新的分析版本 |
| 檔案改名、移動、Synology item ID 更新 | 否 | 更新對應關係 |
| 本工具或使用者更新標籤、Description、拍攝日期、地點或相簿 | 否 | 同步 metadata／候選範圍／索引 |

同一 `asset_id` 可有多筆分析版本；系統只標記一筆為目前有效（`current`），以便比較模型或 taxonomy 更新前後結果，並可撤銷新版標籤決策。

## UX Mockup（草案）

每次建立工作只選擇**一個** AI 任務；工作具有獨立的候選範圍、門檻、預覽、複核與撤銷紀錄。使用者可日後建立下一個工作，或由工作佇列依序執行多個工作，但不同 taxonomy 不混在同一次判定中。

### 1. 建立 AI 標記工作

```text
┌──────────── 建立 AI 標記工作 ────────────┐
│ 1. 選取照片範圍                           │
│    來源：○ 自訂條件  ● Synology 條件相簿  │
│          ○ 一般相簿                         │
│    條件相簿：[2026 日本旅行            ▼]  │
│    目前包含：1,248 張照片                   │
│                                            │
│ 2. 選擇 AI 任務（一次一項）                │
│    [購物]  [證件／身分證]  [健康與健檢]   │
│                                            │
│ 3. 寫入方式                                │
│    ○ 僅建立預覽（dry run）                 │
│    ● 高信心自動寫入；其餘送人工複核         │
│                                            │
│                 [建立預覽]                 │
└────────────────────────────────────────────┘
```

條件相簿是照片範圍的來源之一。建立工作時，系統記錄相簿名稱與 `album_id`，並讀取**當下**成員建立不可變的候選 snapshot；工作完成前，即使條件相簿自動加入或移除照片，也不改變本次處理範圍。下次建立工作時才讀取最新成員。

「購物」工作只判斷並建議加入 `購物`；「證件／身分證」與「健康與健檢」分別在獨立工作中處理，避免把不同類型的判斷、信心門檻與隱私欄位混在一起。

### 2. 預覽與確認寫入

```text
┌──────────── 預覽：日本購物照片 ──────────┐
│ 候選 1,248  建議寫入 86  待複核 21         │
│                                            │
│ [全部] [建議寫入] [待複核] [略過]           │
│                                            │
│ [縮圖 A]  購物 97%  證據：貨架、價格標籤   │
│ [縮圖 B]  購物 91%  證據：購物袋、商品     │
│ [縮圖 C]  購物 68%  狀態：送人工複核       │
│                                            │
│ 將新增：`購物` 86 張                      │
│ 不覆寫：人工標籤與使用者 Description        │
│                                            │
│ [返回修改條件]              [確認寫入]      │
└────────────────────────────────────────────┘
```

預覽以實際照片縮圖呈現；可點開原圖，並逐張接受、拒絕或送入人工複核。縮圖僅由 NAS／本機流程提供，不上傳至雲端。

### 3. 人工複核與回復

人工複核頁須提供 `接受`、`拒絕`、`改為其他受控標籤` 與批次操作；每筆均顯示縮圖、建議、信心分數與判斷證據。工作紀錄頁可「撤銷本次工作」，且只移除本工具寫入的標籤與 Description 管理區塊。

健康工作首頁只顯示分類標籤與可搜尋摘要；完整 OCR 原文不顯示也不保存。更精確的日期、類型與數值範圍查詢由本工具的 scrambled DB 索引完成。

## 參考實作

- [eleonne/synology-tagger](https://github.com/eleonne/synology-tagger)：以機器學習擴充 Synology Photos 搜尋的開源實作。它將分類結果寫入 Synology Photos 的 `general_tag` 與 `many_unit_has_many_general_tag` 資料表；本專案僅將其作為設計參考，仍採 metadata-first 策略，不直接寫入 Synology Photos 內部資料庫。
- [zeichensatz/SynologyPhotosAPI](https://github.com/zeichensatz/SynologyPhotosAPI)：Synology Photos API 的非官方探索文件，供 API 探測與整合設計參考；內容尚不完整，實際支援的 API 與參數仍須在目標 NAS 上驗證。

## MVP 範圍

第一個可驗證版本只完成 UC-01：

- 選出「地點在日本」的支援圖片。
- 以 MLX 視覺模型判斷 `購物`。
- 高信心結果寫入可攜 metadata。
- 產生處理報告與待複核清單。
- 驗證標籤在 Synology Photos 中可搜尋。

暫不納入：影片標註、任意自然語言 taxonomy、大量舊相片全庫掃描，以及任何直接寫入 Synology Photos 資料庫的做法。

## Docker 開發版

目前程式版本為 **v0.3.17**，包含容器內 Tailscale userspace proxy、私有 MLX 照片分析、文件 OCR、Synology Photos 人物與地點上下文、唯讀標籤盤點，以及需要明確確認的 JPG／HEIC Photos API 寫入驗證。標籤盤點與 AI 詞彙提示依目前登入者及所選空間讀取既有標籤。API 寫入驗證只作用於指定的 JPG ID 82153 與 HEIC ID 82155：先透過 GeneralTag API 建立唯一臨時標籤並取得標籤 ID，再加入照片、讀回確認、移除標籤，最後透過 Photos API 下載原檔比對 SHA-256；Synology Photos 仍可能改變原檔內容或修改時間。失敗回應包含 Synology API 錯誤碼、參數名稱與原因（若 NAS 有回傳），以及操作資訊。一般照片瀏覽與 AI 分析維持唯讀，AI 建議不會自動寫回。映像發佈後，NAS Compose 將使用 `v0.3.17` 標籤。Docker Hub Repository overview 的同步稿位於 [`DOCKERHUB.md`](DOCKERHUB.md)。

此版本提供繁體中文 Web 首頁、唯讀 Photos API 瀏覽與單張照片 AI 分析預覽。使用者可在 UI 輸入 NAS 帳密（支援選填 OTP），登入後切換個人空間／共享空間，以分頁方式查看照片 ID、檔名、拍攝時間、地點及既有標籤；縮圖由本站代理顯示，metadata 按需從 Photos API 取得。候選清單可依日本地點與既有標籤篩選。登入工作階段和篩選索引只保存在服務程序記憶體中。

點選照片卡片的「本機 AI 分析」後，服務以 Synology Photos API 讀取單張原圖，記憶體暫存後以單一 `/photo-analyze` 請求上傳到 Tailscale 私有網路中的 Mac-mini MLX。若視覺分析判斷內容為掃描文件，Mac-mini 會用同一份請求暫存影像接續 OCR，無須再從 Photo Tagger 重傳。HEIC/HEIF 會在 Mac-mini 轉成暫存 JPEG，供視覺分析和 OCR 共用。原圖與 OCR 結果不寫入容器磁碟、Synology Photos 或照片檔案。描述、標籤與 OCR 文字僅顯示在候選清單。每張原圖限制 30 MiB；超出上限需先使用其他工作流程處理。

日本篩選依 `additional.address.country` 回傳值比對；沒有國家地點資料的照片不會列入結果。原圖分析只在使用者逐張點選後執行，不會自動掃描相簿。

1. 複製 `.env.example` 為 `.env`，填入 NAS 的 DSM 根網址、照片目錄路徑、`MLX_SERVER_API_KEY`，以及 Tailscale 管理後台建立的專用 reusable auth key `TAILSCALE_AUTHKEY`。MLX API key 必須與 Mac-mini 部署所用的值相同；兩者都不要提交到 Git。Tailscale 節點狀態會保存在 Docker named volume，容器重建後沿用同一節點身分。MLX 請求透過 `MLX_HTTP_PROXY` 指定的本機 HTTP proxy 連入 Tailnet；Synology Photos API 流量不經 proxy。`MLX_SERVER_URL` 預設為 `http://mac-mini.tail28f10.ts.net:5001`。NAS 的 `SYNOLOGY_URL` 必須使用可由容器連線且 TLS 憑證可驗證的網址；此 NAS 可使用 `https://wenchiehlee.synology.me:7778`。
2. 執行 `docker compose up -d --build`。
3. 瀏覽 `http://NAS_IP:5056`；可用 `WEB_PORT` 調整對外埠號。
4. 按「探索 Photos API」確認模組後，在登入區輸入有 Synology Photos 權限的 NAS 帳號與密碼；有啟用雙重驗證時輸入當次 OTP。然後選擇空間並載入照片清單。
5. 先選一張照片按「本機 AI 分析」，確認描述與標籤建議後再決定後續工作流程；本版本不會把建議寫回 Synology Photos。

直接使用 HTTP 埠時，登入密碼會在瀏覽器與 Web UI 之間傳送；只應在可信任的 LAN 或 SSH tunnel 中使用。需要跨不可信網路存取時，應先透過 DSM 反向代理或其他 TLS 終端提供 HTTPS，再登入。NAS API 端連線會驗證 TLS 憑證，不支援關閉驗證。

Compose 預設將個人空間 `/volume1/homes/wjlee/Photos` 唯讀掛載至容器的 `/Photos`。AI 分析使用 Photos API，不讀取該掛載路徑。Tailscale 使用 userspace networking 和只綁定容器 loopback 的 HTTP proxy，不需要 `NET_ADMIN`、`NET_RAW` 或 `/dev/net/tun`。`publish-image.yml` 可由 GitHub Actions 手動觸發，將多架構映像發佈至 `wenchiehlee1020/synology-photo-tagger`；需要設定 `DOCKERHUB_USERNAME` 與 `DOCKERHUB_TOKEN` repository secrets。

### Debug shell

需要直接進入容器執行 `/bin/sh` 或 `/bin/bash` 時，將 `.env` 的 `DEBUG_SHELL` 設為 `true`。先在 `DEBUG_SSH_DIR` 指向的 NAS 目錄建立 `authorized_keys`，放入可信任的 SSH **公鑰**，再重新建立容器。SSH 僅接受公鑰；主機端 debug 埠只綁定 `127.0.0.1`，不會直接暴露在區網。從遠端電腦先建立 NAS SSH port-forward，再連線至容器：

```sh
ssh -N -L 2223:127.0.0.1:2223 <NAS-username>@<NAS-host>
ssh -i <private-key> -p 2223 root@127.0.0.1
```

若使用不同 `DEBUG_SSH_PORT`，請同步調整第一行本機轉送埠與第二行連線埠。完成除錯後將 `DEBUG_SHELL` 設回 `false` 並重新建立容器；一般模式不會啟動容器內的 SSH server。
