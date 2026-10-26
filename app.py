from __future__ import annotations

import importlib.metadata
import io
import json
import os
import secrets
import threading
import time
import uuid
from dataclasses import dataclass
from urllib.parse import urlsplit

import requests
from flask import Flask, Response, copy_current_request_context, jsonify, render_template, request, session

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
APP_VERSION = os.environ.get("APP_VERSION", "v0.3.9")
MLX_SERVER_URL = os.environ.get(
    "MLX_SERVER_URL", "http://mac-mini.tail28f10.ts.net:5001"
).strip().rstrip("/")
MLX_HTTP_PROXY = os.environ.get("MLX_HTTP_PROXY", "").strip()
MLX_SERVER_API_KEY = os.environ.get("MLX_SERVER_API_KEY", "").strip()
MLX_MODEL = os.environ.get("MLX_MODEL", "mlx-gemma4").strip() or "mlx-gemma4"
MLX_OCR_ENGINE = os.environ.get("MLX_OCR_ENGINE", "baidu").strip().lower() or "baidu"
MLX_TIMEOUT_SECONDS = max(30, int(os.environ.get("MLX_TIMEOUT_SECONDS", "900")))
MAX_PHOTO_ANALYSIS_BYTES = 30 * 1024 * 1024
PHOTO_ANALYSIS_PROMPT = """請用繁體中文客觀分析照片，並且只輸出一個合法 JSON 物件，不要加 Markdown 或其他文字：
{"description":"一至兩句簡潔、只描述畫面可見事實的內容","tags":["3 至 8 個適合搜尋的短標籤"]}
標籤只根據可見內容；若照片明確呈現購物情境才加入「購物」。不要推測人物身分、健康、年齡等敏感特徵；不確定時省略。"""


@dataclass
class NasSession:
    client: requests.Session
    sid: str
    api_prefix: str
    api_catalog: dict
    last_used: float


@dataclass
class JapanSearch:
    photos: list[dict]
    source_offset: int = 0
    complete: bool = False
    last_used: float = 0.0


@dataclass
class PhotoLibraryIndex:
    photos: list[dict]
    source_offset: int = 0
    complete: bool = False
    last_used: float = 0.0


_nas_sessions: dict[str, NasSession] = {}
_nas_sessions_lock = threading.Lock()
_japan_searches: dict[tuple[str, str], JapanSearch] = {}
_japan_searches_lock = threading.Lock()
_photo_library_indexes: dict[tuple[str, str], PhotoLibraryIndex] = {}
_photo_library_indexes_lock = threading.Lock()
_photo_analysis_jobs: dict[str, dict] = {}
_photo_analysis_jobs_lock = threading.Lock()
PHOTO_ANALYSIS_JOB_TTL_SECONDS = 900
PHOTO_ANALYSIS_MAX_ACTIVE_JOBS = 4


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
    thumbnail = additional.get("thumbnail") if isinstance(additional.get("thumbnail"), dict) else {}
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
        "thumbnail_cache_key": thumbnail.get("cache_key"),
        "thumbnail_unit_id": thumbnail.get("unit_id"),
        "thumbnail_ready": thumbnail.get("m") == "ready" or thumbnail.get("sm") == "ready",
        "thumbnail_size": "m" if thumbnail.get("m") == "ready" else "sm",
        "tags": [tag.get("name") for tag in tags if isinstance(tag, dict) and tag.get("name")],
    }


def item_metadata(item: dict) -> dict:
    additional = item.get("additional") if isinstance(item.get("additional"), dict) else {}
    exif = additional.get("exif") if isinstance(additional.get("exif"), dict) else {}
    address = additional.get("address") if isinstance(additional.get("address"), dict) else {}
    gps = additional.get("gps") if isinstance(additional.get("gps"), dict) else {}
    resolution = additional.get("resolution") if isinstance(additional.get("resolution"), dict) else {}
    tags = additional.get("tag") if isinstance(additional.get("tag"), list) else []
    people_value = additional.get("person")
    if isinstance(people_value, list):
        people = people_value
    elif isinstance(people_value, dict):
        nested_people = people_value.get("list")
        people = nested_people if isinstance(nested_people, list) else [people_value]
    else:
        people = []
    person_names = []
    for person in people:
        if isinstance(person, str):
            name = person
        elif isinstance(person, dict):
            name = person.get("name") or person.get("person_name")
        else:
            name = None
        if isinstance(name, str) and name.strip() and name.strip().lower() != "unnamed":
            person_names.append(name.strip())
    return {
        "description": additional.get("description"),
        "camera": exif.get("camera"),
        "lens": exif.get("lens"),
        "aperture": exif.get("aperture"),
        "exposure_time": exif.get("exposure_time"),
        "focal_length": exif.get("focal_length"),
        "iso": exif.get("iso"),
        "orientation": additional.get("orientation"),
        "width": resolution.get("width"),
        "height": resolution.get("height"),
        "filesize": item.get("filesize"),
        "latitude": gps.get("latitude"),
        "longitude": gps.get("longitude"),
        "city": address.get("city"),
        "country": address.get("country"),
        "tags": [tag.get("name") for tag in tags if isinstance(tag, dict) and tag.get("name")],
        "people": list(dict.fromkeys(person_names)),
    }


def detect_photo_format(image: bytes) -> tuple[str, str, str] | None:
    """Return display name, MIME type and extension for supported photo bytes."""
    if image.startswith(b"\xff\xd8\xff"):
        return "JPEG", "image/jpeg", "jpg"
    if image.startswith(b"\x89PNG\r\n\x1a\n"):
        return "PNG", "image/png", "png"
    if image.startswith(b"RIFF") and image[8:12] == b"WEBP":
        return "WebP", "image/webp", "webp"
    if len(image) >= 12 and image[4:8] == b"ftyp" and image[8:12] in {
        b"heic", b"heix", b"hevc", b"hevx", b"heif", b"mif1", b"msf1",
    }:
        return "HEIC/HEIF", "image/heic", "heic"
    return None


def parse_photo_analysis(output: str) -> dict | None:
    """Extract a safe, bounded description and tag list from model JSON output."""
    text = output.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[-1]
        if text.endswith("```"):
            text = text[:-3].strip()
    candidates = [text]
    start, end = text.find("{"), text.rfind("}")
    if start >= 0 and end > start:
        candidates.append(text[start : end + 1])
    parsed = None
    for candidate in candidates:
        try:
            parsed = json.loads(candidate)
            break
        except ValueError:
            continue
    if not isinstance(parsed, dict):
        return None
    description = parsed.get("description")
    raw_tags = parsed.get("tags")
    tags = []
    if isinstance(raw_tags, list):
        for tag in raw_tags:
            if isinstance(tag, str) and tag.strip():
                tags.append(tag.strip()[:80])
            if len(tags) >= 8:
                break
    if not (isinstance(description, str) and description.strip()) and not tags:
        return None
    return {
        "description": description.strip()[:1000] if isinstance(description, str) else "",
        "tags": tags,
    }


def is_japan(photo: dict) -> bool:
    country = str(photo.get("country") or "").strip().casefold()
    return country == "jp" or "japan" in country or "日本" in country


def photo_library_index(token: str, space: str) -> PhotoLibraryIndex:
    cache_key = (token, space)
    now = time.monotonic()
    with _photo_library_indexes_lock:
        expired = [
            key for key, value in _photo_library_indexes.items()
            if now - value.last_used > SESSION_TTL_SECONDS
        ]
        for key in expired:
            _photo_library_indexes.pop(key, None)
        index = _photo_library_indexes.get(cache_key)
        if index is None:
            index = PhotoLibraryIndex(photos=[], last_used=now)
            _photo_library_indexes[cache_key] = index
        index.last_used = now
        return index


def scan_photo_library_page(
    nas: NasSession, api_name: str, url: str, version: int, index: PhotoLibraryIndex
) -> None:
    # Keep only one NAS page in flight for an index, even if the browser polls quickly.
    with _photo_library_indexes_lock:
        if index.complete:
            return
        payload = post_synology(
            nas.client,
            url,
            {
                "api": api_name,
                "version": version,
                "method": "list",
                "offset": index.source_offset,
                "limit": MAX_PAGE_SIZE,
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
        index.photos.extend(item_summary(item) for item in items if isinstance(item, dict))
        index.source_offset += len(items)
        index.complete = len(items) < MAX_PAGE_SIZE
        index.last_used = time.monotonic()


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
        app_version=APP_VERSION,
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
    return jsonify({"status": "ok", "service": "synology-photo-tagger", "version": APP_VERSION})


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
            with _japan_searches_lock:
                _japan_searches.pop((old_token, "personal"), None)
                _japan_searches.pop((old_token, "shared"), None)
            with _photo_library_indexes_lock:
                _photo_library_indexes.pop((old_token, "personal"), None)
                _photo_library_indexes.pop((old_token, "shared"), None)
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
        with _japan_searches_lock:
            _japan_searches.pop((token, "personal"), None)
            _japan_searches.pop((token, "shared"), None)
        with _photo_library_indexes_lock:
            _photo_library_indexes.pop((token, "personal"), None)
            _photo_library_indexes.pop((token, "shared"), None)
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
        country_filter = request.args.get("country", "").strip().lower()
        tag_filter = request.args.get("tag", "").strip()
        if tag_filter:
            token = session.get("nas_session_token")
            if not token:
                return jsonify({"ok": False, "error": "登入工作階段已失效，請重新登入。"}), 401
            index = photo_library_index(token, space)

            def matches_filter(photo: dict) -> bool:
                if country_filter == "japan" and not is_japan(photo):
                    return False
                photo_tags = photo.get("tags", [])
                if tag_filter == "__untagged__":
                    return not photo_tags
                return any(
                    str(name) == tag_filter
                    for name in photo_tags
                )

            matches = [photo for photo in index.photos if matches_filter(photo)]
            if len(matches) < offset + limit and not index.complete:
                scan_photo_library_page(nas, api_name, url, version, index)
                matches = [photo for photo in index.photos if matches_filter(photo)]
            photos = matches[offset:offset + limit]
            scanning = not index.complete and len(matches) < offset + limit
            return jsonify(
                {
                    "ok": True,
                    "space": space,
                    "offset": offset,
                    "limit": limit,
                    "next_offset": offset + len(photos),
                    "has_more": len(matches) > offset + limit or not index.complete,
                    "page_count": len(photos),
                    "photos": photos,
                    "scanning": scanning,
                    "search_complete": index.complete,
                    "scanned_count": index.source_offset,
                    "total_found": len(matches),
                    "tag_filter": tag_filter,
                }
            )
        if country_filter == "japan":
            token = session.get("nas_session_token")
            if not token:
                return jsonify({"ok": False, "error": "登入工作階段已失效，請重新登入。"}), 401
            cache_key = (token, space)
            with _japan_searches_lock:
                now = time.monotonic()
                expired = [
                    key for key, value in _japan_searches.items()
                    if now - value.last_used > SESSION_TTL_SECONDS
                ]
                for key in expired:
                    _japan_searches.pop(key, None)
                search = _japan_searches.get(cache_key)
                if search is None:
                    search = JapanSearch(photos=[], last_used=now)
                    _japan_searches[cache_key] = search
                search.last_used = now

                # Advance one source page per request so large libraries remain responsive.
                if not search.complete and len(search.photos) < offset + limit:
                    batch_size = MAX_PAGE_SIZE
                    payload = post_synology(
                        nas.client,
                        url,
                        {
                            "api": api_name,
                            "version": version,
                            "method": "list",
                            "offset": search.source_offset,
                            "limit": batch_size,
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
                    for item in items:
                        if not isinstance(item, dict):
                            continue
                        photo = item_summary(item)
                        if is_japan(photo):
                            search.photos.append(photo)
                    search.source_offset += len(items)
                    if len(items) < batch_size:
                        search.complete = True
                photos = search.photos[offset:offset + limit]
                scan_needed = len(search.photos) < offset + limit and not search.complete
                return jsonify(
                    {
                        "ok": True,
                        "space": space,
                        "offset": offset,
                        "limit": limit,
                        "next_offset": offset + len(photos),
                        "has_more": len(search.photos) > offset + limit or not search.complete,
                        "page_count": len(photos),
                        "photos": photos,
                        "scanning": scan_needed,
                        "search_complete": search.complete,
                        "scanned_count": search.source_offset,
                        "total_found": len(search.photos),
                    }
                )

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


@app.get("/api/photos/tags")
def list_photo_tags():
    nas = current_nas_session()
    if not nas:
        return jsonify({"ok": False, "error": "請先登入 Synology Photos。"}), 401
    space = request.args.get("space", "personal")
    if space not in {"personal", "shared"}:
        return jsonify({"ok": False, "error": "空間類型無效。"}), 400
    token = session.get("nas_session_token")
    if not token:
        return jsonify({"ok": False, "error": "登入工作階段已失效，請重新登入。"}), 401
    api_name = "SYNO.Foto.Browse.Item" if space == "personal" else "SYNO.FotoTeam.Browse.Item"
    try:
        url, version = api_endpoint(nas, api_name)
        index = photo_library_index(token, space)
        scan_photo_library_page(nas, api_name, url, version, index)
        tags = sorted(
            {
                str(tag).strip()
                for photo in index.photos
                for tag in photo.get("tags", [])
                if str(tag).strip()
            },
            key=str.casefold,
        )
        return jsonify(
            {
                "ok": True,
                "space": space,
                "tags": tags,
                "scanning": not index.complete,
                "scanned_count": index.source_offset,
                "complete": index.complete,
            }
        )
    except SynologyApiError as exc:
        status = 502 if exc.error_code is None else 403
        return jsonify({"ok": False, "error": str(exc), "error_code": exc.error_code}), status


@app.get("/api/photos/<int:photo_id>/metadata")
def photo_metadata(photo_id: int):
    nas = current_nas_session()
    if not nas:
        return jsonify({"ok": False, "error": "請先登入 Synology Photos。"}), 401
    space = request.args.get("space", "personal")
    if space not in {"personal", "shared"}:
        return jsonify({"ok": False, "error": "空間類型無效。"}), 400

    api_name = "SYNO.Foto.Browse.Item" if space == "personal" else "SYNO.FotoTeam.Browse.Item"
    try:
        url, version = api_endpoint(nas, api_name)
        payload = post_synology(
            nas.client,
            url,
            {
                "api": api_name,
                "version": version,
                "method": "get",
                "id": json.dumps([photo_id], separators=(",", ":")),
                "additional": json.dumps(
                    ["exif", "description", "orientation", "resolution", "gps", "address", "tag", "person"],
                    separators=(",", ":"),
                ),
                "_sid": nas.sid,
            },
        )
        data = payload.get("data")
        items = data.get("list") if isinstance(data, dict) else None
        if not isinstance(items, list) or not items or not isinstance(items[0], dict):
            return jsonify({"ok": False, "error": "Photos API 沒有回傳這張照片的詳細資料。"}), 404
        item = items[0]
        return jsonify({"ok": True, "photo_id": photo_id, "metadata": item_metadata(item)})
    except SynologyApiError as exc:
        status = 502 if exc.error_code is None else 403
        return jsonify({"ok": False, "error": str(exc), "error_code": exc.error_code}), status


@app.get("/api/photos/<int:photo_id>/thumbnail")
def photo_thumbnail(photo_id: int):
    nas = current_nas_session()
    if not nas:
        return jsonify({"ok": False, "error": "請先登入 Synology Photos。"}), 401
    space = request.args.get("space", "personal")
    cache_key = request.args.get("cache_key", "")
    size = request.args.get("size", "m")
    if space not in {"personal", "shared"}:
        return jsonify({"ok": False, "error": "空間類型無效。"}), 400
    if not cache_key or len(cache_key) > 80 or not all(
        part.isdigit() for part in cache_key.split("_", 1)
    ) or "_" not in cache_key:
        return jsonify({"ok": False, "error": "縮圖識別碼格式無效。"}), 400
    if size not in {"m", "sm"}:
        return jsonify({"ok": False, "error": "縮圖尺寸無效。"}), 400

    api_name = "SYNO.Foto.Thumbnail" if space == "personal" else "SYNO.FotoTeam.Thumbnail"
    try:
        url, version = api_endpoint(nas, api_name)
    except SynologyApiError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 502

    try:
        response = nas.client.get(
            url,
            params={
                "api": api_name,
                "version": version,
                "method": "get",
                "mode": "download",
                "id": photo_id,
                "cache_key": cache_key,
                "type": "unit",
                "size": size,
                "_sid": nas.sid,
            },
            timeout=(4, 20),
        )
        response.raise_for_status()
        image = response.content
    except requests.exceptions.SSLError:
        return jsonify({"ok": False, "error": "NAS TLS 憑證驗證失敗。"}), 502
    except requests.exceptions.Timeout:
        return jsonify({"ok": False, "error": "讀取照片縮圖逾時。"}), 504
    except requests.exceptions.RequestException:
        return jsonify({"ok": False, "error": "無法讀取照片縮圖。"}), 502

    signatures = (
        (b"\xff\xd8\xff", "image/jpeg"),
        (b"\x89PNG\r\n\x1a\n", "image/png"),
        (b"GIF87a", "image/gif"),
        (b"GIF89a", "image/gif"),
        (b"RIFF", "image/webp"),
    )
    content_type = next(
        (mime for signature, mime in signatures if image.startswith(signature)), None
    )
    if content_type == "image/webp" and image[8:12] != b"WEBP":
        content_type = None
    if not content_type:
        return jsonify({"ok": False, "error": "NAS 尚未提供可用的照片縮圖。"}), 404
    result = Response(image, mimetype=content_type)
    result.headers["X-Content-Type-Options"] = "nosniff"
    return result


@app.get("/api/photos/<int:photo_id>/original-check")
def photo_original_check(photo_id: int):
    """Read an original Photo item as a stream and return only format/size metadata."""
    nas = current_nas_session()
    if not nas:
        return jsonify({"ok": False, "error": "請先登入 Synology Photos。"}), 401
    space = request.args.get("space", "personal")
    cache_key = request.args.get("cache_key", "")
    if space not in {"personal", "shared"}:
        return jsonify({"ok": False, "error": "空間類型無效。"}), 400
    if cache_key and (
        len(cache_key) > 80
        or "_" not in cache_key
        or not all(part.isdigit() for part in cache_key.split("_", 1))
    ):
        return jsonify({"ok": False, "error": "原檔識別碼格式無效。"}), 400

    api_name = "SYNO.Foto.Download" if space == "personal" else "SYNO.FotoTeam.Download"
    try:
        url, version = api_endpoint(nas, api_name)
        unit_id = request.args.get("unit_id", str(photo_id))
        if not unit_id.isdigit():
            return jsonify({"ok": False, "error": "原檔項目識別碼格式無效。"}), 400
        if not cache_key:
            browse_api = "SYNO.Foto.Browse.Item" if space == "personal" else "SYNO.FotoTeam.Browse.Item"
            browse_url, browse_version = api_endpoint(nas, browse_api)
            item_payload = post_synology(
                nas.client,
                browse_url,
                {
                    "api": browse_api,
                    "version": browse_version,
                    "method": "get",
                    "id": json.dumps([photo_id], separators=(",", ":")),
                    "additional": json.dumps(["thumbnail"], separators=(",", ":")),
                    "_sid": nas.sid,
                },
            )
            item_data = item_payload.get("data")
            items = item_data.get("list") if isinstance(item_data, dict) else None
            item = items[0] if isinstance(items, list) and items and isinstance(items[0], dict) else {}
            additional = item.get("additional") if isinstance(item.get("additional"), dict) else {}
            thumbnail = additional.get("thumbnail") if isinstance(additional.get("thumbnail"), dict) else {}
            cache_key = thumbnail.get("cache_key", "")
            resolved_unit_id = thumbnail.get("unit_id")
            if isinstance(resolved_unit_id, int):
                unit_id = str(resolved_unit_id)
            if not cache_key:
                return jsonify(
                    {
                        "ok": False,
                        "error": "Synology Photos 尚未提供這張照片的原檔識別資料，請稍後重試。",
                    }
                ), 404
    except SynologyApiError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 502

    response = None
    try:
        response = nas.client.get(
            url,
            params={
                "api": api_name,
                "version": version,
                "method": "download",
                "cache_key": cache_key,
                "unit_id": json.dumps([int(unit_id)], separators=(",", ":")),
                "_sid": nas.sid,
            },
            stream=True,
            timeout=(4, 30),
        )
        response.raise_for_status()
        upstream_type = response.headers.get("Content-Type", "").split(";", 1)[0].lower()
        if "json" in upstream_type or "text/plain" in upstream_type:
            try:
                payload = response.json()
            except ValueError:
                payload = None
            if isinstance(payload, dict) and not payload.get("success", True):
                return jsonify(
                    {
                        "ok": False,
                        "error": "Synology Photos 拒絕原檔讀取。",
                        "error_code": api_error(payload),
                    }
                ), 502

        byte_count = 0
        prefix = bytearray()
        for chunk in response.iter_content(chunk_size=64 * 1024):
            if not chunk:
                continue
            byte_count += len(chunk)
            if len(prefix) < 32:
                prefix.extend(chunk[: 32 - len(prefix)])
    except requests.exceptions.SSLError:
        return jsonify({"ok": False, "error": "NAS TLS 憑證驗證失敗。"}), 502
    except requests.exceptions.Timeout:
        return jsonify({"ok": False, "error": "讀取原檔逾時。"}), 504
    except requests.exceptions.HTTPError as exc:
        status = exc.response.status_code if exc.response is not None else "未知"
        return jsonify({"ok": False, "error": f"NAS 回傳 HTTP {status}。"}), 502
    except requests.exceptions.RequestException:
        return jsonify({"ok": False, "error": "無法讀取照片原檔。"}), 502
    finally:
        if response is not None:
            response.close()

    header = bytes(prefix)
    detected_format = None
    if header.startswith(b"\xff\xd8\xff"):
        detected_format = "JPEG"
    elif len(header) >= 12 and header[4:8] == b"ftyp" and header[8:12] in {
        b"heic", b"heix", b"hevc", b"hevx", b"heif", b"mif1", b"msf1",
    }:
        detected_format = "HEIC/HEIF"
    elif header.startswith(b"\x89PNG\r\n\x1a\n"):
        detected_format = "PNG"

    if not byte_count or detected_format is None:
        return jsonify(
            {
                "ok": False,
                "error": "Photos API 有回應，但內容不是可辨識的 JPEG、HEIC/HEIF 或 PNG 原檔。",
                "bytes_read": byte_count,
                "content_type": upstream_type,
            }
        ), 502
    return jsonify({
        "ok": True,
        "photo_id": photo_id,
        "space": space,
        "api": api_name,
        "api_version": version,
        "format": detected_format,
        "bytes_read": byte_count,
        "content_type": upstream_type or None,
        "signature_hex": header[:16].hex(),
        "stored": False,
        "image_returned": False,
    })


@app.post("/api/photos/<int:photo_id>/analyze")
def photo_analyze(photo_id: int):
    """Queue a read-only photo analysis so browser-facing requests stay short."""
    if not current_nas_session():
        return jsonify({"ok": False, "error": "請先登入 Synology Photos。"}), 401
    if not MLX_SERVER_API_KEY:
        return jsonify({"ok": False, "error": "尚未設定本機 MLX API key。"}), 503

    now = time.time()
    with _photo_analysis_jobs_lock:
        expired_ids = [
            task_id for task_id, task in _photo_analysis_jobs.items()
            if task.get("finished_at") and now - task["finished_at"] > PHOTO_ANALYSIS_JOB_TTL_SECONDS
        ]
        for task_id in expired_ids:
            _photo_analysis_jobs.pop(task_id, None)
        active_count = sum(task.get("status") in {"queued", "running"} for task in _photo_analysis_jobs.values())
        if active_count >= PHOTO_ANALYSIS_MAX_ACTIVE_JOBS:
            return jsonify({"ok": False, "error": "目前分析工作較多，請稍後再試。"}), 503
        task_id = uuid.uuid4().hex
        _photo_analysis_jobs[task_id] = {"status": "queued", "created_at": now, "finished_at": None}

    worker_context = copy_current_request_context(
        lambda: _run_photo_analysis_job(task_id, photo_id)
    )
    try:
        thread = threading.Thread(
            target=worker_context,
            name=f"photo-analysis-{task_id[:8]}",
            daemon=True,
        )
        thread.start()
    except Exception:
        with _photo_analysis_jobs_lock:
            _photo_analysis_jobs.pop(task_id, None)
        app.logger.exception("Could not start photo analysis job")
        return jsonify({"ok": False, "error": "無法啟動照片分析工作。"}), 503

    return jsonify({"ok": True, "task_id": task_id, "status": "queued"}), 202


def _run_photo_analysis_job(task_id: str, photo_id: int) -> None:
    with _photo_analysis_jobs_lock:
        task = _photo_analysis_jobs.get(task_id)
        if task is not None:
            task["status"] = "running"
    try:
        result = _perform_photo_analysis(photo_id)
        status_code = 200
        if isinstance(result, tuple):
            response, status_code = result
        else:
            response = result
        payload = response.get_json(silent=True) if isinstance(response, Response) else None
        if not isinstance(payload, dict):
            payload = {"ok": False, "error": "照片分析服務回傳格式無效。"}
            status_code = 502
        successful = 200 <= status_code < 300 and payload.get("ok") is True
        with _photo_analysis_jobs_lock:
            task = _photo_analysis_jobs.get(task_id)
            if task is not None:
                task.update({
                    "status": "complete" if successful else "failed",
                    "result": payload,
                    "finished_at": time.time(),
                })
    except Exception:
        app.logger.exception("Unexpected photo analysis job failure")
        with _photo_analysis_jobs_lock:
            task = _photo_analysis_jobs.get(task_id)
            if task is not None:
                task.update({
                    "status": "failed",
                    "result": {"ok": False, "error": "照片分析失敗。"},
                    "finished_at": time.time(),
                })


@app.get("/api/photo-analysis/<task_id>")
def photo_analysis_job_status(task_id: str):
    """Return the result of a queued photo-analysis job."""
    if not current_nas_session():
        return jsonify({"ok": False, "error": "請先登入 Synology Photos。"}), 401
    if len(task_id) != 32 or any(char not in "0123456789abcdef" for char in task_id):
        return jsonify({"ok": False, "error": "分析工作識別碼格式無效。"}), 400
    now = time.time()
    with _photo_analysis_jobs_lock:
        task = _photo_analysis_jobs.get(task_id)
        if task and task.get("finished_at") and now - task["finished_at"] > PHOTO_ANALYSIS_JOB_TTL_SECONDS:
            _photo_analysis_jobs.pop(task_id, None)
            task = None
        if task is None:
            return jsonify({"ok": False, "error": "找不到分析工作，或工作結果已逾期。"}), 404
        return jsonify({
            "ok": True,
            "status": task["status"],
            "result": task.get("result"),
        })


def _perform_photo_analysis(photo_id: int):
    """Stream one NAS original to the private MLX server and return suggestions only."""
    nas = current_nas_session()
    if not nas:
        return jsonify({"ok": False, "error": "請先登入 Synology Photos。"}), 401
    if not MLX_SERVER_API_KEY:
        return jsonify({"ok": False, "error": "尚未設定本機 MLX API key。"}), 503

    space = request.args.get("space", "personal")
    cache_key = request.args.get("cache_key", "")
    unit_id = request.args.get("unit_id", str(photo_id))
    if space not in {"personal", "shared"}:
        return jsonify({"ok": False, "error": "空間類型無效。"}), 400
    if cache_key and (
        len(cache_key) > 80
        or "_" not in cache_key
        or not all(part.isdigit() for part in cache_key.split("_", 1))
    ):
        return jsonify({"ok": False, "error": "照片識別資料格式無效。"}), 400
    if not unit_id.isdigit():
        return jsonify({"ok": False, "error": "照片項目識別碼格式無效。"}), 400

    download_api = "SYNO.Foto.Download" if space == "personal" else "SYNO.FotoTeam.Download"
    browse_api = "SYNO.Foto.Browse.Item" if space == "personal" else "SYNO.FotoTeam.Browse.Item"
    known_people: list[str] = []
    try:
        download_url, download_version = api_endpoint(nas, download_api)
        browse_url, browse_version = api_endpoint(nas, browse_api)
        item_payload = post_synology(
            nas.client,
            browse_url,
            {
                "api": browse_api,
                "version": browse_version,
                "method": "get",
                "id": json.dumps([photo_id], separators=(",", ":")),
                "additional": json.dumps(
                    ["exif", "description", "orientation", "resolution", "gps", "address", "tag", "person", "thumbnail"],
                    separators=(",", ":"),
                ),
                "_sid": nas.sid,
            },
        )
        item_data = item_payload.get("data")
        items = item_data.get("list") if isinstance(item_data, dict) else None
        item = items[0] if isinstance(items, list) and items and isinstance(items[0], dict) else {}
        additional = item.get("additional") if isinstance(item.get("additional"), dict) else {}
        known_people = item_metadata(item).get("people", [])
        thumbnail = additional.get("thumbnail") if isinstance(additional.get("thumbnail"), dict) else {}
        if not cache_key:
            cache_key = thumbnail.get("cache_key", "")
        resolved_unit_id = thumbnail.get("unit_id")
        if isinstance(resolved_unit_id, int):
            unit_id = str(resolved_unit_id)
        if not cache_key:
            return jsonify({"ok": False, "error": "Synology Photos 尚未提供這張照片的原檔識別資料。"}), 404
    except SynologyApiError as exc:
        status = 502 if exc.error_code is None else 403
        return jsonify({"ok": False, "error": str(exc), "error_code": exc.error_code}), status

    nas_response = None
    image_buffer = bytearray()
    upstream_type = ""
    try:
        nas_response = nas.client.get(
            download_url,
            params={
                "api": download_api,
                "version": download_version,
                "method": "download",
                "cache_key": cache_key,
                "unit_id": json.dumps([int(unit_id)], separators=(",", ":")),
                "_sid": nas.sid,
            },
            stream=True,
            timeout=(4, 60),
        )
        nas_response.raise_for_status()
        upstream_type = nas_response.headers.get("Content-Type", "").split(";", 1)[0].lower()
        content_length = nas_response.headers.get("Content-Length")
        if content_length and content_length.isdigit() and int(content_length) > MAX_PHOTO_ANALYSIS_BYTES:
            return jsonify({"ok": False, "error": "原始照片超過 30 MiB 分析上限。"}), 413
        if "json" in upstream_type or "text/plain" in upstream_type:
            try:
                payload = nas_response.json()
            except ValueError:
                payload = None
            if isinstance(payload, dict) and not payload.get("success", True):
                return jsonify({"ok": False, "error": "Synology Photos 拒絕原檔讀取。", "error_code": api_error(payload)}), 502
        for chunk in nas_response.iter_content(chunk_size=256 * 1024):
            if not chunk:
                continue
            if len(image_buffer) + len(chunk) > MAX_PHOTO_ANALYSIS_BYTES:
                return jsonify({"ok": False, "error": "原始照片超過 30 MiB 分析上限。"}), 413
            image_buffer.extend(chunk)
    except requests.exceptions.SSLError:
        return jsonify({"ok": False, "error": "NAS TLS 憑證驗證失敗。"}), 502
    except requests.exceptions.Timeout:
        return jsonify({"ok": False, "error": "讀取原檔逾時。"}), 504
    except requests.exceptions.HTTPError as exc:
        status = exc.response.status_code if exc.response is not None else "未知"
        return jsonify({"ok": False, "error": f"NAS 回傳 HTTP {status}。"}), 502
    except requests.exceptions.RequestException:
        return jsonify({"ok": False, "error": "無法讀取照片原檔。"}), 502
    finally:
        if nas_response is not None:
            nas_response.close()

    image_bytes = bytes(image_buffer)
    image_type = detect_photo_format(image_bytes)
    if not image_bytes or image_type is None:
        return jsonify({
            "ok": False,
            "error": "Photos API 回傳的原檔格式不支援；目前支援 JPEG、PNG、WebP 與 HEIC/HEIF。",
            "content_type": upstream_type or None,
        }), 415

    image_format, mime_type, extension = image_type
    analysis_prompt = PHOTO_ANALYSIS_PROMPT
    if known_people:
        analysis_prompt += (
            "\n已確認的人物姓名（來自 Synology Photos metadata，並非視覺推測）："
            + "、".join(known_people)
            + "。若畫面中有人物，description 必須使用這些已確認姓名描述照片中的人物，"
            "不要以「一位男士／女士」等泛稱取代已提供的姓名。不可根據外貌猜測姓名，"
            "也不可在多人時推斷哪個姓名對應哪張臉；若無法安全地把姓名對應到特定人物，"
            "可在描述中自然提及已標記姓名，但不要指派個別外貌或動作。"
        )
    try:
        mlx_response = requests.post(
            f"{MLX_SERVER_URL}/photo-analyze",
            headers={"X-API-Key": MLX_SERVER_API_KEY, "X-App-Name": "Synology-Photo-Tagger"},
            data={"prompt": analysis_prompt, "model": MLX_MODEL, "ocr_engine": MLX_OCR_ENGINE},
            files={"file": (f"photo-{photo_id}.{extension}", io.BytesIO(image_bytes), mime_type)},
            timeout=(8, MLX_TIMEOUT_SECONDS),
            allow_redirects=False,
            proxies=(
                {"http": MLX_HTTP_PROXY, "https": MLX_HTTP_PROXY}
                if MLX_HTTP_PROXY
                else None
            ),
        )
        mlx_response.raise_for_status()
        result = mlx_response.json()
    except requests.exceptions.Timeout:
        return jsonify({"ok": False, "error": "本機 MLX 分析逾時，請稍後重試。"}), 504
    except requests.exceptions.HTTPError as exc:
        response = exc.response
        try:
            error_payload = response.json() if response is not None else {}
        except ValueError:
            error_payload = {}
        message = error_payload.get("error") if isinstance(error_payload, dict) else None
        status = response.status_code if response is not None else 502
        if status not in {400, 401, 413, 415, 503, 504}:
            status = 502
        return jsonify({"ok": False, "error": message or "本機 MLX 分析服務回報錯誤。"}), status
    except requests.exceptions.RequestException:
        return jsonify({"ok": False, "error": "無法連線 Mac-mini 本機 MLX 分析服務。"}), 502
    except ValueError:
        return jsonify({"ok": False, "error": "MLX 分析服務回傳格式無效。"}), 502

    output = result.get("output") if isinstance(result, dict) else None
    if not isinstance(output, str) or not output.strip():
        return jsonify({"ok": False, "error": "MLX 分析服務沒有回傳分析內容。"}), 502
    analysis = parse_photo_analysis(output)
    ocr_result = None
    api_ocr = result.get("ocr") if isinstance(result, dict) else None
    if isinstance(api_ocr, dict):
        ocr_result = api_ocr
    return jsonify({
        "ok": True,
        "photo_id": photo_id,
        "space": space,
        "format": image_format,
        "bytes_sent": len(image_bytes),
        "analysis": analysis,
        "people": known_people,
        "ocr": ocr_result,
        "output": output,
        "model": result.get("model"),
        "converted": bool(result.get("converted")),
        "elapsed_s": result.get("elapsed_s"),
        "saved": False,
        "written_to_photos": False,
    })


@app.get("/api/photo-ocr/<task_id>")
def photo_ocr_status(task_id: str):
    """Poll OCR task state without keeping the browser request open."""
    if not current_nas_session():
        return jsonify({"ok": False, "error": "請先登入 Synology Photos。"}), 401
    if not MLX_SERVER_API_KEY:
        return jsonify({"ok": False, "error": "尚未設定本機 MLX API key。"}), 503
    if len(task_id) != 32 or any(char not in "0123456789abcdef" for char in task_id):
        return jsonify({"ok": False, "error": "OCR 工作識別碼格式無效。"}), 400

    try:
        response = requests.get(
            f"{MLX_SERVER_URL}/photo-analyze/ocr-status/{task_id}",
            headers={"X-API-Key": MLX_SERVER_API_KEY},
            timeout=(4, 12),
            allow_redirects=False,
            proxies=(
                {"http": MLX_HTTP_PROXY, "https": MLX_HTTP_PROXY}
                if MLX_HTTP_PROXY
                else None
            ),
        )
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, dict) or payload.get("status") not in {
            "queued", "running", "complete", "failed",
        }:
            return jsonify({"ok": False, "error": "OCR 狀態回應格式無效。"}), 502
        return jsonify({"ok": True, "status": payload["status"], "ocr": payload.get("ocr")})
    except requests.exceptions.Timeout:
        return jsonify({"ok": False, "error": "查詢 OCR 狀態逾時，請稍後重試。"}), 504
    except requests.exceptions.HTTPError as exc:
        status = exc.response.status_code if exc.response is not None else 502
        return jsonify({"ok": False, "error": "找不到 OCR 工作或工作已逾期。"}), status
    except (requests.exceptions.RequestException, ValueError):
        return jsonify({"ok": False, "error": "無法查詢 Mac-mini OCR 工作狀態。"}), 502
