from __future__ import annotations

import importlib.metadata
import json
import os
import secrets
import threading
import time
from dataclasses import dataclass
from urllib.parse import urlsplit

import requests
from flask import Flask, jsonify, render_template, request, session

app = Flask(__name__)
app.secret_key = os.environ.get("APP_SECRET_KEY") or secrets.token_hex(32)
app.config.update(
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Strict",
    SESSION_COOKIE_SECURE=os.environ.get("APP_HTTPS_ONLY", "false").lower() == "true",
)

API_INFO_PARAMS = {
    "api": "SYNO.API.Info",
    "version": "1",
    "method": "query",
    "query": "all",
}
API_INFO_PATHS = ("/webapi/query.cgi", "/photo/webapi/query.cgi")
SESSION_TTL_SECONDS = 30 * 60
MAX_PAGE_SIZE = 100


@dataclass
class NasSession:
    client: requests.Session
    sid: str
    api_prefix: str
    api_catalog: dict
    last_used: float


_nas_sessions: dict[str, NasSession] = {}
_nas_sessions_lock = threading.Lock()


class SynologyApiError(Exception):
    def __init__(self, message: str, error_code: int | None = None):
        super().__init__(message)
        self.error_code = error_code


def api_error(payload: object) -> int | None:
    if not isinstance(payload, dict):
        return None
    error = payload.get("error")
    if isinstance(error, dict) and isinstance(error.get("code"), int):
        return error["code"]
    return None


def api_message(payload: object) -> str:
    code = api_error(payload)
    messages = {
        400: "帳號或密碼錯誤",
        401: "帳號已停用",
        402: "帳號沒有執行此操作的權限",
        403: "需要雙重驗證碼",
        404: "雙重驗證碼錯誤或已過期",
        406: "登入嘗試遭拒，請檢查帳號安全設定",
    }
    return messages.get(code, "NAS API 請求失敗")


def post_synology(client: requests.Session, url: str, data: dict) -> dict:
    try:
        response = client.post(url, data=data, timeout=(4, 20))
        response.raise_for_status()
        payload = response.json()
    except requests.exceptions.SSLError as exc:
        raise SynologyApiError("NAS TLS 憑證驗證失敗。") from exc
    except requests.exceptions.Timeout as exc:
        raise SynologyApiError("連線 NAS 逾時。") from exc
    except requests.exceptions.HTTPError as exc:
        status = exc.response.status_code if exc.response is not None else "未知"
        raise SynologyApiError(f"NAS 回傳 HTTP {status}。") from exc
    except requests.exceptions.RequestException as exc:
        raise SynologyApiError("無法連線 NAS。") from exc
    except ValueError as exc:
        raise SynologyApiError("NAS 回應不是有效 JSON。") from exc

    if not isinstance(payload, dict):
        raise SynologyApiError("NAS 回應格式不符預期。")
    if not payload.get("success"):
        raise SynologyApiError(api_message(payload), api_error(payload))
    return payload


def discover_catalog(base_url: str) -> tuple[requests.Session, str, dict]:
    for api_path in API_INFO_PATHS:
        client = requests.Session()
        try:
            response = client.get(
                f"{base_url}{api_path}", params=API_INFO_PARAMS, timeout=(4, 12)
            )
            response.raise_for_status()
            payload = response.json()
        except requests.exceptions.RequestException:
            client.close()
            continue
        except ValueError:
            client.close()
            continue
        if isinstance(payload, dict) and payload.get("success") and isinstance(payload.get("data"), dict):
            path = urlsplit(api_path).path
            return client, path.rsplit("/", 1)[0], payload["data"]
        client.close()
    raise SynologyApiError("找不到可用的 Synology API 查詢端點。")


def current_nas_session() -> NasSession | None:
    token = session.get("nas_session_token")
    if not token:
        return None
    now = time.monotonic()
    with _nas_sessions_lock:
        expired_tokens = [
            key
            for key, value in _nas_sessions.items()
            if now - value.last_used > SESSION_TTL_SECONDS
        ]
        expired_sessions = [_nas_sessions.pop(key) for key in expired_tokens]
        stored = _nas_sessions.get(token)
        if not stored:
            session.pop("nas_session_token", None)
            stored = None
        else:
            stored.last_used = now
    for expired in expired_sessions:
        expired.client.close()
    return stored


def api_endpoint(nas: NasSession, api_name: str) -> tuple[str, int]:
    metadata = nas.api_catalog.get(api_name)
    if not isinstance(metadata, dict):
        raise SynologyApiError(f"NAS 未回報必要模組：{api_name}")
    path = metadata.get("path", "entry.cgi")
    version = metadata.get("maxVersion", 1)
    if not isinstance(path, str) or not isinstance(version, int):
        raise SynologyApiError(f"NAS 回報的模組資料格式不符：{api_name}")
    if path.startswith("/"):
        endpoint = f"{configured_base_url()}{path}"
    elif path.startswith("webapi/") or path.startswith("photo/webapi/"):
        endpoint = f"{configured_base_url()}/{path}"
    else:
        endpoint = f"{configured_base_url()}{nas.api_prefix}/{path}"
    return endpoint, version


def item_summary(item: dict) -> dict:
    additional = item.get("additional") if isinstance(item.get("additional"), dict) else {}
    address = additional.get("address") if isinstance(additional.get("address"), dict) else {}
    gps = additional.get("gps") if isinstance(additional.get("gps"), dict) else {}
    resolution = additional.get("resolution") if isinstance(additional.get("resolution"), dict) else {}
    tags = additional.get("tag") if isinstance(additional.get("tag"), list) else []
    return {
        "id": item.get("id"),
        "filename": item.get("filename") or "（未命名）",
        "type": item.get("type"),
        "time": item.get("time"),
        "filesize": item.get("filesize"),
        "folder_id": item.get("folder_id"),
        "country": address.get("country"),
        "city": address.get("city"),
        "latitude": gps.get("latitude"),
        "longitude": gps.get("longitude"),
        "width": resolution.get("width"),
        "height": resolution.get("height"),
        "tags": [tag.get("name") for tag in tags if isinstance(tag, dict) and tag.get("name")],
    }


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
        logged_in=current_nas_session() is not None,
    )


@app.after_request
def prevent_private_response_caching(response):
    if request.path.startswith("/api/") or request.path == "/":
        response.headers["Cache-Control"] = "no-store"
    return response


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


@app.get("/api/session")
def session_status():
    return jsonify({"authenticated": current_nas_session() is not None})


@app.post("/api/login")
def login():
    body = request.get_json(silent=True) or {}
    username = str(body.get("username", "")).strip()
    password = str(body.get("password", ""))
    otp_code = str(body.get("otp_code", "")).strip()
    base_url = configured_base_url()
    validation_error = validate_base_url(base_url)
    if validation_error:
        return jsonify({"ok": False, "error": validation_error}), 400
    if not username or not password:
        return jsonify({"ok": False, "error": "請輸入 NAS 帳號與密碼。"}), 400

    client = None
    try:
        client, api_prefix, catalog = discover_catalog(base_url)
        auth_info = catalog.get("SYNO.API.Auth", {})
        if not isinstance(auth_info, dict):
            raise SynologyApiError("NAS 未回報 SYNO.API.Auth 登入 API。")
        auth_path = auth_info.get("path", "auth.cgi")
        auth_version = auth_info.get("maxVersion", 3)
        if not isinstance(auth_path, str) or not isinstance(auth_version, int):
            raise SynologyApiError("NAS 回報的登入 API 資料格式不符。")
        if auth_path.startswith("/"):
            auth_url = f"{base_url}{auth_path}"
        else:
            auth_url = f"{base_url}{api_prefix}/{auth_path}"
        data = {
            "api": "SYNO.API.Auth",
            "version": auth_version,
            "method": "login",
            "account": username,
            "passwd": password,
            "session": "SynologyPhotoTagger",
            "format": "sid",
        }
        if otp_code:
            data["otp_code"] = otp_code
        payload = post_synology(client, auth_url, data)
        sid = payload.get("data", {}).get("sid") if isinstance(payload.get("data"), dict) else None
        if not isinstance(sid, str) or not sid:
            raise SynologyApiError("NAS 登入回應沒有 Session ID。")

        old_token = session.get("nas_session_token")
        if old_token:
            with _nas_sessions_lock:
                previous = _nas_sessions.pop(old_token, None)
            if previous:
                previous.client.close()
        token = secrets.token_urlsafe(32)
        with _nas_sessions_lock:
            _nas_sessions[token] = NasSession(
                client=client,
                sid=sid,
                api_prefix=api_prefix,
                api_catalog=catalog,
                last_used=time.monotonic(),
            )
        session.clear()
        session["nas_session_token"] = token
        return jsonify({"ok": True, "message": "NAS 登入成功。"})
    except SynologyApiError as exc:
        if client:
            client.close()
        return jsonify({"ok": False, "error": str(exc), "error_code": exc.error_code}), 502


@app.post("/api/logout")
def logout():
    token = session.pop("nas_session_token", None)
    if token:
        with _nas_sessions_lock:
            nas = _nas_sessions.pop(token, None)
        if nas:
            try:
                auth_url, version = api_endpoint(nas, "SYNO.API.Auth")
                post_synology(
                    nas.client,
                    auth_url,
                    {
                        "api": "SYNO.API.Auth",
                        "version": version,
                        "method": "logout",
                        "session": "SynologyPhotoTagger",
                        "_sid": nas.sid,
                    },
                )
            except SynologyApiError:
                pass
            finally:
                nas.client.close()
    return jsonify({"ok": True})


@app.get("/api/photos")
def list_photos():
    nas = current_nas_session()
    if not nas:
        return jsonify({"ok": False, "error": "請先登入 Synology Photos。"}), 401

    space = request.args.get("space", "personal")
    if space not in {"personal", "shared"}:
        return jsonify({"ok": False, "error": "空間類型無效。"}), 400
    try:
        offset = max(0, int(request.args.get("offset", "0")))
        limit = min(MAX_PAGE_SIZE, max(1, int(request.args.get("limit", "48"))))
    except ValueError:
        return jsonify({"ok": False, "error": "頁碼或每頁筆數格式錯誤。"}), 400

    api_name = "SYNO.Foto.Browse.Item" if space == "personal" else "SYNO.FotoTeam.Browse.Item"
    try:
        url, version = api_endpoint(nas, api_name)
        payload = post_synology(
            nas.client,
            url,
            {
                "api": api_name,
                "version": version,
                "method": "list",
                "offset": offset,
                "limit": limit,
                "type": "photo",
                "sort_by": "takentime",
                "sort_direction": "desc",
                "additional": json.dumps(
                    ["thumbnail", "resolution", "gps", "address", "tag"],
                    separators=(",", ":"),
                ),
                "_sid": nas.sid,
            },
        )
        data = payload.get("data")
        items = data.get("list") if isinstance(data, dict) else None
        if not isinstance(items, list):
            raise SynologyApiError("照片 API 回應中沒有清單資料。")
        photos = [item_summary(item) for item in items if isinstance(item, dict)]
        country_filter = request.args.get("country", "").strip().lower()
        if country_filter == "japan":
            photos = [
                photo
                for photo in photos
                if "japan" in str(photo.get("country") or "").lower()
                or "日本" in str(photo.get("country") or "")
            ]
        return jsonify(
            {
                "ok": True,
                "space": space,
                "offset": offset,
                "limit": limit,
                "next_offset": offset + len(items),
                "has_more": len(items) == limit,
                "page_count": len(photos),
                "photos": photos,
            }
        )
    except SynologyApiError as exc:
        status = 502 if exc.error_code is None else 403
        return jsonify({"ok": False, "error": str(exc), "error_code": exc.error_code}), status
