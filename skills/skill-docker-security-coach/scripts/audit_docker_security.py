#!/usr/bin/env python3
"""Docker & Node.js 容器安全稽核與加固腳本 (Docker Security Audit & Coach)

自動掃描專案內的 Dockerfile、docker-compose.yml 與 Node.js 相依性，
輸出安全查核清單評估與加固建議報告。

用法：
    python scripts/audit_docker_security.py
    python scripts/audit_docker_security.py --root-dir . --json
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

__version__ = "1.0.0"


@dataclass
class AuditFinding:
    rule_id: str
    title: str
    category: str  # Runtime, SupplyChain, Privileges, Execution, Secrets
    severity: str  # Critical, High, Medium, Low, Info
    status: str    # PASS, FAIL, WARN, SKIP
    description: str
    file_path: str = ""
    line_number: int = 0
    recommendation: str = ""


@dataclass
class AuditReport:
    project_root: str
    timestamp: str
    summary: dict[str, int] = field(default_factory=dict)
    findings: list[AuditFinding] = field(default_factory=list)
    score: int = 100


class DockerSecurityAuditor:
    def __init__(self, root_dir: Path):
        self.root_dir = root_dir.resolve()
        self.findings: list[AuditFinding] = []

    def audit_dockerfile(self, dockerfile_path: Path) -> None:
        if not dockerfile_path.exists():
            return

        rel_path = str(dockerfile_path.relative_to(self.root_dir))
        content = dockerfile_path.read_text(encoding="utf-8", errors="ignore")
        lines = content.splitlines()

        # 1. 檢查是否使用 npm i -g @latest
        npm_latest_pattern = re.compile(r"npm\s+(?:i|install)\s+-[gG]\s+([^\s]+@latest)")
        has_npm_latest = False
        for idx, line in enumerate(lines, 1):
            m = npm_latest_pattern.search(line)
            if m:
                has_npm_latest = True
                self.findings.append(AuditFinding(
                    rule_id="DSC-001",
                    title="全域 npm 套件未鎖定版本號（使用 @latest）",
                    category="SupplyChain",
                    severity="Medium",
                    status="FAIL",
                    file_path=rel_path,
                    line_number=idx,
                    description=f"發現全域安裝套件採用 `@latest`: `{m.group(1)}`，可能引入破壞性變更或面臨供應鏈投毒風險。",
                    recommendation="改為鎖定具體版本號（如 `@openai/codex@0.167.0`）或使用 lockfile / hash 鎖定。",
                ))
        if not has_npm_latest:
            self.findings.append(AuditFinding(
                rule_id="DSC-001",
                title="全域 npm 套件版本鎖定",
                category="SupplyChain",
                severity="Medium",
                status="PASS",
                file_path=rel_path,
                description="未發現採用 @latest 之全域 npm 安裝。",
            ))

        # 2. 檢查 Node.js 版本 (Node 20 vs 22)
        has_node_install = False
        for idx, line in enumerate(lines, 1):
            if "setup_20.x" in line or "node:20" in line:
                has_node_install = True
                self.findings.append(AuditFinding(
                    rule_id="DSC-002",
                    title="Node.js 20 進入維護/EOL 週期，建議規劃升級",
                    category="Runtime",
                    severity="Low",
                    status="WARN",
                    file_path=rel_path,
                    line_number=idx,
                    description="偵測到使用 Node.js 20.x 安裝來源。Node.js 20 即將或已進入維護週期。",
                    recommendation="建議規劃升級至當前 Active LTS 版本（如 Node.js 22 LTS）。",
                ))
                break
            elif "setup_22.x" in line or "node:22" in line:
                has_node_install = True
                self.findings.append(AuditFinding(
                    rule_id="DSC-002",
                    title="Node.js 使用當前 Active LTS 版本",
                    category="Runtime",
                    severity="Low",
                    status="PASS",
                    file_path=rel_path,
                    line_number=idx,
                    description="使用 Node.js 22.x LTS 版本。",
                ))
                break

        # 3. 檢查 npm ci --ignore-scripts
        has_npm_ci_ignore = False
        has_npm_install = False
        for idx, line in enumerate(lines, 1):
            if "npm ci" in line:
                has_npm_install = True
                if "--ignore-scripts" in line:
                    has_npm_ci_ignore = True
            elif "npm i" in line or "npm install" in line:
                has_npm_install = True

        if has_npm_ci_ignore:
            self.findings.append(AuditFinding(
                rule_id="DSC-003",
                title="已啟用 npm ci --ignore-scripts 阻擋惡意生命週期腳本",
                category="SupplyChain",
                severity="High",
                status="PASS",
                file_path=rel_path,
                description="npm ci 使用了 --ignore-scripts，能有效防範第三方套件 preinstall/postinstall 惡意代碼注入。",
            ))
        elif has_npm_install:
            self.findings.append(AuditFinding(
                rule_id="DSC-003",
                title="npm 安裝未包含 --ignore-scripts",
                category="SupplyChain",
                severity="High",
                status="WARN",
                file_path=rel_path,
                description="npm 套件安裝未配置 --ignore-scripts，可能執行第三方依賴的生命週期腳本。",
                recommendation="建議在 npm ci 加入 --ignore-scripts 參數。",
            ))

        # 4. 檢查容器執行用戶 (USER 宣告)
        has_user_directive = any(line.strip().startswith("USER ") for line in lines)
        if not has_user_directive:
            self.findings.append(AuditFinding(
                rule_id="DSC-004",
                title="容器以 root 身分運行（未宣告 USER 指令）",
                category="Privileges",
                severity="Medium",
                status="WARN",
                file_path=rel_path,
                description="Dockerfile 中未發現 USER 指令，容器將以預設 root 權限執行所有應用程序與 Node/Python 指令。",
                recommendation="若無需 root 特權操作，建議宣告非 root 用戶（例如 USER node 或專屬 appuser）。",
            ))
        else:
            self.findings.append(AuditFinding(
                rule_id="DSC-004",
                title="容器指定非 root 用戶運行",
                category="Privileges",
                severity="Medium",
                status="PASS",
                file_path=rel_path,
                description="Dockerfile 已配置非 root USER 指令。",
            ))

        # 5. 檢查 NODE_ENV
        has_node_env = any("NODE_ENV" in line for line in lines)
        if not has_node_env:
            self.findings.append(AuditFinding(
                rule_id="DSC-005",
                title="未顯式設置 NODE_ENV=production",
                category="Runtime",
                severity="Low",
                status="WARN",
                file_path=rel_path,
                description="未設定 NODE_ENV=production，部分 Node.js 庫在開發模式下可能輸出多餘的除錯日誌或降低效能。",
                recommendation="在 Dockerfile 中加入 ENV NODE_ENV=production。",
            ))
        else:
            self.findings.append(AuditFinding(
                rule_id="DSC-005",
                title="已配置 NODE_ENV",
                category="Runtime",
                severity="Low",
                status="PASS",
                file_path=rel_path,
                description="Dockerfile 已顯式設置 NODE_ENV 環境變數。",
            ))

    def audit_docker_compose(self, compose_path: Path) -> None:
        if not compose_path.exists():
            return

        rel_path = str(compose_path.relative_to(self.root_dir))
        content = compose_path.read_text(encoding="utf-8", errors="ignore")
        lines = content.splitlines()

        # 1. 檢查 privileged: true
        has_privileged = False
        for idx, line in enumerate(lines, 1):
            if re.search(r"^\s*privileged:\s*true", line):
                has_privileged = True
                self.findings.append(AuditFinding(
                    rule_id="DSC-006",
                    title="容器配置 privileged: true 權限過大",
                    category="Privileges",
                    severity="High",
                    status="WARN",
                    file_path=rel_path,
                    line_number=idx,
                    description="容器啟用 privileged: true 會授權訪問宿主機幾乎所有設備，顯著增加容器逃逸風險。",
                    recommendation="若僅為 Tailscale 虛擬網卡需求，建議移除 privileged，僅保留 cap_add: [NET_ADMIN] 與 /dev/net/tun 設備映射。",
                ))
                break
        if not has_privileged:
            self.findings.append(AuditFinding(
                rule_id="DSC-006",
                title="未啟用 privileged 特權模式",
                category="Privileges",
                severity="High",
                status="PASS",
                file_path=rel_path,
                description="容器未開啟 privileged 特權模式。",
            ))

        # 2. 檢查是否有明文機密寫入 docker-compose
        secret_keys = ["API_KEY", "PASSWORD", "SECRET", "AUTHKEY", "TOKEN"]
        exposed_secrets = []
        for idx, line in enumerate(lines, 1):
            stripped = line.strip()
            for k in secret_keys:
                # 排除 ${VAR} 這種變數參照形式
                pattern = rf'^\s*-\s*{k}=([^${{}}\s]+)'
                m = re.search(pattern, stripped)
                if m and len(m.group(1)) > 3:
                    exposed_secrets.append((idx, k, m.group(1)[:3] + "***"))

        if exposed_secrets:
            for idx, k, masked in exposed_secrets:
                self.findings.append(AuditFinding(
                    rule_id="DSC-007",
                    title="Compose 文件內含明文機密",
                    category="Secrets",
                    severity="High",
                    status="FAIL",
                    file_path=rel_path,
                    line_number=idx,
                    description=f"在環境變數配置中發現寫入明文機密 `{k}={masked}`。",
                    recommendation="改用 .env 文件或 Docker secrets / CI Secrets 動態傳入，避免簽入版控。",
                ))
        else:
            self.findings.append(AuditFinding(
                rule_id="DSC-007",
                title="未在 Compose 檔案發現硬編碼明文機密",
                category="Secrets",
                severity="High",
                status="PASS",
                file_path=rel_path,
                description="機密設定皆以 ${VAR} 格式或環境變數注入。",
            ))

    def audit_node_dependencies(self, mcp_dir: Path) -> None:
        package_json = mcp_dir / "package.json"
        if not package_json.exists():
            return

        rel_path = str(package_json.relative_to(self.root_dir))
        try:
            data = json.loads(package_json.read_text(encoding="utf-8"))
        except Exception:
            return

        overrides = data.get("overrides", {})
        if overrides:
            self.findings.append(AuditFinding(
                rule_id="DSC-008",
                title="已配置 npm overrides 安全修補規則",
                category="SupplyChain",
                severity="Medium",
                status="PASS",
                file_path=rel_path,
                description=f"已配置 {len(overrides)} 項安全版本強制覆寫規則（overrides）。",
            ))

        # 嘗試執行本機 npm audit (唯讀)
        try:
            res = subprocess.run(
                ["npm", "audit", "--json"],
                cwd=str(mcp_dir),
                capture_output=True,
                text=True,
                timeout=15,
                shell=(sys.platform == "win32"),
            )
            audit_data = json.loads(res.stdout) if res.stdout else {}
            vulnerabilities = audit_data.get("metadata", {}).get("vulnerabilities", {})
            total_vulns = sum(vulnerabilities.values())
            crit = vulnerabilities.get("critical", 0)
            high = vulnerabilities.get("high", 0)
            mod = vulnerabilities.get("moderate", 0)

            if crit > 0 or high > 0:
                self.findings.append(AuditFinding(
                    rule_id="DSC-009",
                    title="發現 Critical / High 等級 npm 相依弱點",
                    category="SupplyChain",
                    severity="High",
                    status="FAIL",
                    file_path=rel_path,
                    description=f"npm audit 檢測出 {crit} critical, {high} high 弱點。",
                    recommendation="執行 npm audit fix 或於 package.json overrides 指定修復版本。",
                ))
            elif mod > 0:
                self.findings.append(AuditFinding(
                    rule_id="DSC-009",
                    title="發現 Moderate 等級 npm 相依弱點",
                    category="SupplyChain",
                    severity="Medium",
                    status="WARN",
                    file_path=rel_path,
                    description=f"npm audit 檢測出 {mod} 項 moderate 弱點。",
                    recommendation="檢視 advisory 內容並評估是否透過 overrides 或更新套件修復。",
                ))
            else:
                self.findings.append(AuditFinding(
                    rule_id="DSC-009",
                    title="npm audit 檢查通過（無已知弱點）",
                    category="SupplyChain",
                    severity="Medium",
                    status="PASS",
                    file_path=rel_path,
                    description="npm 相依套件庫中未發現已知弱點。",
                ))
        except Exception:
            # 若 npm 無法執行則跳過
            pass

    def run_all(self) -> AuditReport:
        self.findings.clear()

        # 1. Dockerfile
        self.audit_dockerfile(self.root_dir / "Dockerfile")

        # 2. docker-compose.yml
        self.audit_docker_compose(self.root_dir / "docker-compose.yml")

        # 3. Node.js MCP Engine
        self.audit_node_dependencies(self.root_dir / "mcp")

        # 計算評分與統計
        counts = {"PASS": 0, "WARN": 0, "FAIL": 0, "SKIP": 0}
        score = 100
        for f in self.findings:
            counts[f.status] = counts.get(f.status, 0) + 1
            if f.status == "FAIL":
                deduction = {"Critical": 30, "High": 20, "Medium": 10, "Low": 5}.get(f.severity, 5)
                score -= deduction
            elif f.status == "WARN":
                deduction = {"Critical": 15, "High": 10, "Medium": 5, "Low": 2}.get(f.severity, 2)
                score -= deduction

        score = max(0, min(100, score))

        from datetime import datetime, timezone, timedelta
        tz_tw = timezone(timedelta(hours=8))
        ts_now = datetime.now(tz_tw).strftime("%Y-%m-%d %H:%M:%S CST")

        return AuditReport(
            project_root=str(self.root_dir),
            timestamp=ts_now,
            summary=counts,
            findings=self.findings,
            score=score,
        )


def format_markdown_report(report: AuditReport) -> str:
    md = []
    md.append("# 🛡️ Docker & Node.js 容器安全審計報告")
    md.append("")
    md.append(f"- **專案路徑**：`{report.project_root}`")
    md.append(f"- **審計時間**：{report.timestamp}")
    md.append(f"- **安全評分**：**{report.score} / 100**")
    md.append("")

    summary = report.summary
    md.append("### 📊 審計摘要統計")
    md.append(f"| ✅ PASS 通過 | ⚠️ WARN 警告 | ❌ FAIL 失敗 | 總檢查項 |")
    md.append(f"| :---: | :---: | :---: | :---: |")
    total = sum(summary.values())
    md.append(f"| {summary.get('PASS', 0)} | {summary.get('WARN', 0)} | {summary.get('FAIL', 0)} | {total} |")
    md.append("")

    md.append("### 🔍 詳細審計項目清單")
    md.append("| 狀態 | 規則編號 | 分類 | 嚴重度 | 標題與說明 | 加固建議 |")
    md.append("| :---: | :--- | :--- | :---: | :--- | :--- |")

    icons = {"PASS": "✅ PASS", "WARN": "⚠️ WARN", "FAIL": "❌ FAIL", "SKIP": "⚪ SKIP"}
    for f in report.findings:
        st = icons.get(f.status, f.status)
        loc = f" (`{f.file_path}:{f.line_number}`)" if f.line_number else (f" (`{f.file_path}`)" if f.file_path else "")
        desc = f"**{f.title}**{loc}<br>{f.description}"
        rec = f.recommendation if f.recommendation else "-"
        md.append(f"| {st} | `{f.rule_id}` | {f.category} | {f.severity} | {desc} | {rec} |")

    md.append("")
    md.append("---")
    md.append("> *Generated by skill-docker-security-coach audit engine.*")
    return "\n".join(md)


def main():
    parser = argparse.ArgumentParser(description="Docker & Node.js 容器安全審計工具")
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    parser.add_argument("--root-dir", type=Path, default=Path.cwd(), help="專案根目錄")
    parser.add_argument("--json", action="store_true", help="以 JSON 格式輸出")
    args = parser.parse_args()

    auditor = DockerSecurityAuditor(args.root_dir)
    report = auditor.run_all()

    if args.json:
        print(json.dumps(asdict(report), ensure_ascii=False, indent=2))
    else:
        print(format_markdown_report(report))


if __name__ == "__main__":
    main()
