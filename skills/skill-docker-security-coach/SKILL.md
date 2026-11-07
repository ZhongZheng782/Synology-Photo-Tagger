---
name: skill-docker-security-coach
description: Coach Docker and Node.js container security audits, Docker Scout CVE checklists, hardening recipes, and vulnerability remediation in Traditional Chinese. Use for reviewing image and base OS vulnerabilities, dependencies, container privilege boundaries, supply chains, and secrets handling.
---

# Docker 容器安全教練 (v1.1.0)

以結構化查核清單、威脅模型分析與可驗證修復建議，協助評估與加固 Docker 容器及 Node.js 執行環境之安全性。預設繁體中文（zh-TW），優先指出關鍵弱點與修復配方，再提供詳細技術原理解析。

## 任務入口

先辨識使用者的安全審計需求，只展開相關流程；不必因單一套件弱點而重構整個映像檔架構。

| 使用者任務 | 核心入口 | 主要交付物 |
|---|---|---|
| **全面安全審計與健康檢查** | 執行自動化審計腳本 → 分層分析 | 結構化 Markdown 審計報告、安全評分 (0-100) 與待修項目 |
| **Node.js 執行階段與版本生命週期** | 執行階段安全查核 → Active LTS 遷移 | Node.js 版本建議、`NODE_ENV` 配置、記憶體與程序限制 |
| **npm 套件相依與供應鏈防護** | 供應鏈審計 → `npm audit` / `overrides` | 鎖定版本清單、生命週期腳本隔離（`--ignore-scripts`）、漏洞修復配方 |
| **容器權限與特權邊界加固** | 權限邊界審查 → 最小特權原則 | 移除 `privileged` 方案、CapAdd/CapDrop 精準授權、非 root 用戶配置 |
| **MCP Engine / 終端執行防護** | 沙盒與命令注入防護 | 命令參數陣列化、目錄穿越校驗、Desktop Commander 隔離 |
| **機密資訊與日誌隔離** | 機密外洩檢查 → `.env` / CI Secrets 治理 | 明文機密替換、日誌 Token 遮罩（Masking）、Volume 掛載權限 |

---

## 核心架構與安全分層

```text
Layer 1: Runtime (Base OS & Node.js Engine)
Layer 2: Supply Chain (Dependencies, Package Locks & CLI versions)
Layer 3: Privileges (User ID, Capabilities, Device Mappings)
Layer 4: Execution (Process Invocation, Path Validation & Sandboxing)
Layer 5: Secrets & Observability (Environment Variables & Log Masking)
```

本技能採用階層式縱深防禦（Defense-in-Depth）模型，各層次職責明確：
1. **Runtime（執行層）**：底層 Linux/Debian slim 映像檔、Node.js LTS 版本支援與 `NODE_ENV` 模式。
2. **Supply Chain（供應鏈層）**：npm 相依套件版本固定、lockfile 完整性、`npm ci --ignore-scripts` 阻絕投毒。
3. **Privileges（權限層）**：落實最小特權（PoLP），避免濫用 `privileged: true`，精準配置 Linux Capabilities（如 `NET_ADMIN`）。
4. **Execution（執行防護層）**：MCP Engine 與 CLI 命令執行之參數陣列化傳遞，嚴防 Shell Injection 與 Path Traversal。
5. **Secrets & Observability（機密與觀測層）**：機密資訊動態注入，防止日誌或版控洩漏 Token。

---

## 核心查核清單 (Security Checklists)

### 1. Node.js 執行階段安全 (Runtime Security)
- [ ] **LTS 生命週期遵循**：使用當前 Active LTS 版本（如 Node.js 22.x），避免使用已停止維護或進入維護週期的版本（如 Node.js 20.x 或更早）。
- [ ] **生產環境模式**：在 Dockerfile 顯式宣告 `ENV NODE_ENV=production`，關閉開發除錯資訊並優化效能。
- [ ] **記憶體限制 (OOM 防護)**：在 Node.js 啟動參數中指定 `--max-old-space-size=<MB>`，避免內存異常造成 Docker host 崩潰。
- [ ] **除錯端口隔離**：嚴格禁止在生產容器中開啟 `--inspect` 或 `--inspect-brk`。

### 2. 套件與供應鏈安全 (Supply Chain Security)
- [ ] **全域 CLI 鎖定精確版號**：禁止使用 `npm i -g <pkg>@latest`，必須固定版號（如 `@openai/codex@0.167.0`）避免不可預期的破壞性更新或投毒。
- [ ] **阻斷惡意生命週期腳本**：在 Dockerfile 建置時一律採用 `npm ci --ignore-scripts`，阻止第三方套件在安裝時執行惡意代碼。
- [ ] **嚴格使用 Lockfile**：提交並維護 `package-lock.json`，禁止直接使用 `npm install` 浮動解析版本。
- [ ] **相依性漏洞管理**：定期執行 `npm audit`；遇無法立即升級的主套件時，在 `package.json` 的 `overrides` 欄位強制鎖定修復後的子依賴版本。

### 3. 容器特權與權限邊界 (Privileges & Capabilities)
- [ ] **非 Root 用戶運行**：在 Dockerfile 末端或 Service 配置中指定 `USER node` 或專屬服務帳號，避免以 `root` 身分常駐運行。
- [ ] **避免 `privileged: true`**：除非必要，絕不給予全特權模式。若僅需 Tailscale 虛擬網卡，只需配置：
  ```yaml
  cap_add:
    - NET_ADMIN
  devices:
    - /dev/net/tun:/dev/net/tun
  ```
- [ ] **唯讀根檔案系統 (Read-only RootFS)**：評估將容器設為 `read_only: true`，僅對必要的暫存目錄（如 `/tmp`、`/app/data`）以 `tmpfs` 或 volume 掛載。

### 4. MCP Engine 與命令執行防護 (Execution & Sandboxing)
- [ ] **防範 Shell Injection**：執行子行程（Child Process）時，禁用 `child_process.exec(cmd_string)` 拼接指令；必須改用 `execFile` 或 `spawn` 並以參數陣列形式傳遞。
- [ ] **目錄穿越防護 (Path Traversal)**：MCP 存取本地檔案時，必須透過 `path.resolve()` 正規化路徑，並驗證目標路徑是否處於授權目錄樹內。
- [ ] **執行逾時防護**：所有外部 CLI 調用必須設定明確的 Timeout 上限（例如 120 秒），防止惡意輸入掛起程序。

### 5. 機密資訊與觀測安全 (Secrets & Logging)
- [ ] **禁止在 Dockerfile / Compose 硬編碼機密**：API Key、密碼與 Auth Token 一律以 `.env`、Docker Secrets 或 GitHub Secrets 注入。
- [ ] **日誌脫敏 (Token Masking)**：容器輸出日誌時，需過濾並遮蔽包含 `API_KEY`、`AUTHKEY`、Bearer Token 等關鍵欄位。
- [ ] **排除非必要檔案**：透過 `.dockerignore` 排除 `.env`、`.git`、`node_modules` 與金鑰快取目錄。

### 6. 映像檔 CVE 清單 (Docker Scout)

對正式映像檔及候選版本執行 Docker Scout。先看完整報告，再聚焦可修補的 Critical/High；不可只看總分或只檢查最新 tag。把每筆發現記錄到報告，直到修補後的新映像重新掃描完成。

```bash
# 完整 CVE 清單，保留 Scout 的套件、版本、嚴重度、修補版本與映像資訊
docker scout cves --format markdown IMAGE:TAG

# 先處理可修補的 Critical / High
docker scout cves --only-fixed --only-severity critical,high IMAGE:TAG

# 區分 base image 與應用程式層的套件
docker scout cves --only-base IMAGE:TAG
docker scout cves --ignore-base IMAGE:TAG

# 將新舊映像比較，檢查修補後新增或消失的弱點
docker scout compare IMAGE:NEW_TAG --to IMAGE:OLD_TAG --ignore-unchanged
```

對多架構映像，至少分別掃描部署會使用的每個平台（例如 `--platform linux/amd64` 與 `--platform linux/arm64`），並記下掃描的 tag、digest、平台及日期。也要掃描所有仍在部署或可被拉取使用的版本 tag；舊 tag 不會因為新 tag 修好了就自動消失。

每筆 CVE 至少記錄：

| 欄位 | 要記錄的內容 |
|---|---|
| 嚴重度與 CVE | Scout 顯示的 severity、CVE/GHSA、CVSS（若有） |
| 套件 | 名稱、ecosystem/type、偵測版本、套件位於哪一層或檔案路徑 |
| 影響範圍 | 受影響映像 tag/digest、平台、base image 或應用程式相依 |
| 修補資訊 | 是否有修補、受影響版本範圍、上游固定版本 |
| 處理結果 | 升級來源與版本、複掃結果；或暫緩理由、緩解措施、責任人與下次檢查日期 |

處理規則：

- **有修補版本**：先判斷套件來自應用相依、OS 套件、base image 或隨附的第三方二進位檔，再升級正確來源；重建映像並複掃，不以改版號或隱藏 Scout 結果當成修補。
- **沒有修補版本**：保留為開放項目；查閱套件維護者、作業系統安全公告及 CVE 範圍，記錄是否存在可驗證的 backport、受影響功能是否可達，以及暫行緩解和重查日期。不要只因程式目前未呼叫套件就標成不受影響。
- **多映像結果**：確認每個受影響 tag 是否仍部署；若保留舊版供回復，列入清單並說明舊版弱點仍存在。
- **VEX 或例外**：只在有可核對的依賴路徑、程式碼路徑或供應商聲明時使用；說明證據與適用的 image digest。例外不會移除套件或修補漏洞。
- **驗收**：新映像的 fixable Critical/High 已消失，或逐項有明確、可追蹤的例外處理；`docker scout compare` 確認套件變更符合預期。未修補的 unfixed CVE 仍需出現在報告中。

Docker Scout 指令與欄位以官方文件為準：[docker scout cves](https://docs.docker.com/reference/cli/docker/scout/cves/)、[Docker Scout image analysis](https://docs.docker.com/scout/explore/analysis/)、[Docker Scout exceptions](https://docs.docker.com/scout/explore/exceptions/)。

---

## 自動化審計工具

本技能隨附專屬自動化審計指令碼，可一鍵對當前專案進行規範掃描並生成結構化報告：

```bash
# 預設執行全項審計並以 Markdown 表格輸出
python skills/skill-docker-security-coach/scripts/audit_docker_security.py

# 以 JSON 格式輸出（適合 CI/CD 自動化整合）
python skills/skill-docker-security-coach/scripts/audit_docker_security.py --json
```

---

## 常用加固配方 (Hardening Recipes)

### 配方 A：以非 Root 身分運行 Node.js / Python
```dockerfile
# 建立專屬服務帳號
RUN groupadd -r appgroup && useradd -r -g appgroup -d /app -s /sbin/nologin appuser \
    && chown -R appuser:appgroup /app

USER appuser
```

### 配方 B：精確取代 `privileged: true` 的 Tailscale 配置
```yaml
services:
  app-service:
    # 移除 privileged: true
    cap_add:
      - NET_ADMIN
      - NET_RAW
    devices:
      - /dev/net/tun:/dev/net/tun
```

### 配方 C：Package.json 漏洞修復 Overrides
```json
{
  "overrides": {
    "@hono/node-server": ">=2.1.3",
    "brace-expansion": ">=5.0.12",
    "braces": ">=3.0.3"
  }
}
```
