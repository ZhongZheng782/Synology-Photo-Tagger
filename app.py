from __future__ import annotations

import importlib.metadata
import os
from urllib.parse import urlsplit

import requests
from flask import Flask, jsonify, render_template

app = Flask(__name__)

API_INFO_PARAMS = {
    "api": "SYNO.API.Info",
    "version": "1",
    "method": "query",
    "query": "all",
}
API_INFO_PATHS = ("/webapi/query.cgi", "/photo/webapi/query.cgi")


def configured_base_url() -> str:
    return os.environ.get("SYNOLOGY_URL", "").strip().rstrip("/")


def validate_base_url(base_url: str) -> str | None:
    if not base_url:
        return "尚未設定 NAS 位址。請在 Compose 環境變數設定 SYNOLOGY_URL。"
    parsed = urlsplit(base_url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        return "NAS 位址格式錯誤，請使用 http(s)://主機名稱或 IP[:埠號]。"
    if parsed.username or parsed.password or parsed.query or parsed.fragment:
        return "NAS 位址不可包含帳密、查詢參數或網址片段。"
    if parsed.path not in {"", "/"}:
        return "請填寫 DSM 網址的根位址，不要附加 API 路徑。"
    return None


def sdk_version() -> str:
    try:
        return importlib.metadata.version("synology-api")
    except importlib.metadata.PackageNotFoundError:
        return "未安裝"


@app.get("/")
def index():
    return render_template(
        "index.html",
        base_url=configured_base_url(),
        sdk_version=sdk_version(),
        library_mounted=os.path.isdir("/Photos"),
    )


@app.get("/health")
def health():
    return jsonify({"status": "ok", "service": "synology-photo-tagger"})


@app.post("/api/discover")
def discover():
    base_url = configured_base_url()
    validation_error = validate_base_url(base_url)
    if validation_error:
        return jsonify({"ok": False, "error": validation_error}), 400

    failures = []
    for api_path in API_INFO_PATHS:
        try:
            response = requests.get(
                f"{base_url}{api_path}",
                params=API_INFO_PARAMS,
                timeout=(4, 12),
            )
            response.raise_for_status()
            payload = response.json()
            if (
                not isinstance(payload, dict)
                or not payload.get("success")
                or not isinstance(payload.get("data"), dict)
            ):
                failures.append(f"{api_path}：NAS 回傳的 API 格式不符預期。")
                continue

            modules = payload["data"]
            photos = sorted(name for name in modules if name.startswith("SYNO.Foto."))
            team = sorted(name for name in modules if name.startswith("SYNO.FotoTeam."))
            return jsonify(
                {
                    "ok": True,
                    "endpoint": api_path,
                    "total_modules": len(modules),
                    "photo_modules": photos,
                    "team_modules": team,
                    "sdk_version": sdk_version(),
                }
            )
        except requests.exceptions.SSLError:
            failures.append(f"{api_path}：TLS 憑證驗證失敗。請為 NAS 設定有效憑證。")
        except requests.exceptions.ConnectTimeout:
            failures.append(f"{api_path}：連線逾時，請確認 NAS 位址與埠號。")
        except requests.exceptions.ConnectionError:
            failures.append(f"{api_path}：無法連線，請確認容器可到達 NAS。")
        except requests.exceptions.Timeout:
            failures.append(f"{api_path}：NAS 回應逾時。")
        except requests.exceptions.HTTPError as exc:
            failures.append(f"{api_path}：HTTP {exc.response.status_code}。")
        except (requests.exceptions.RequestException, ValueError):
            failures.append(f"{api_path}：請求失敗或回應不是有效 JSON。")

    return jsonify(
        {
            "ok": False,
            "error": "找不到可用的 Synology API 查詢端點。",
            "details": failures,
        }
    ), 502
