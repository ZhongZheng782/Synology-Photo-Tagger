"""Persistent, read-only local catalog for Synology Photos metadata."""

from __future__ import annotations

import json
import os
import sqlite3
import time
import uuid
from datetime import date, datetime, time as datetime_time, timedelta, timezone
from pathlib import Path


PAGE_SIZE = 100
DETAIL_BATCH_SIZE = 100
MAX_QUERY_LIMIT = 100


def default_catalog_path() -> str:
    configured = os.environ.get("PHOTO_CATALOG_DB_PATH", "").strip()
    if configured:
        return configured
    job_db = os.environ.get("TAGGER_DB_PATH", "/data/app/photo-tagger.sqlite3")
    return str(Path(job_db).with_name("photo-catalog.sqlite3"))


CATALOG_DB_PATH = default_catalog_path()


def connect_catalog(path: str = CATALOG_DB_PATH, *, readonly: bool = False) -> sqlite3.Connection:
    target = Path(path)
    if readonly:
        connection = sqlite3.connect(f"file:{target.resolve()}?mode=ro", uri=True, timeout=30)
    else:
        target.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        connection = sqlite3.connect(path, timeout=30)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    connection.execute("PRAGMA busy_timeout = 30000")
    return connection


def initialize_catalog(path: str = CATALOG_DB_PATH) -> None:
    with connect_catalog(path) as db:
        db.executescript(
            """
            CREATE TABLE IF NOT EXISTS photo_catalog (
                owner_key TEXT NOT NULL,
                space TEXT NOT NULL,
                photo_id INTEGER NOT NULL,
                filename TEXT NOT NULL,
                item_type TEXT,
                taken_time REAL,
                filesize INTEGER,
                folder_id TEXT,
                indexed_time REAL,
                live_type TEXT,
                owner_user_id TEXT,
                description TEXT,
                camera TEXT,
                lens TEXT,
                aperture TEXT,
                exposure_time TEXT,
                focal_length TEXT,
                iso TEXT,
                orientation TEXT,
                orientation_original TEXT,
                width INTEGER,
                height INTEGER,
                latitude REAL,
                longitude REAL,
                country TEXT,
                state TEXT,
                county TEXT,
                city TEXT,
                district TEXT,
                town TEXT,
                village TEXT,
                route TEXT,
                landmark TEXT,
                geocoding_id TEXT,
                exif_json TEXT NOT NULL DEFAULT '{}',
                resolution_json TEXT NOT NULL DEFAULT '{}',
                gps_json TEXT NOT NULL DEFAULT '{}',
                address_json TEXT NOT NULL DEFAULT '{}',
                thumbnail_cache_key TEXT,
                thumbnail_unit_id TEXT,
                thumbnail_ready INTEGER NOT NULL DEFAULT 0,
                thumbnail_size TEXT NOT NULL DEFAULT 'sm',
                metadata_synced_at REAL NOT NULL,
                last_seen_run_id TEXT NOT NULL,
                missing_runs INTEGER NOT NULL DEFAULT 0,
                is_deleted INTEGER NOT NULL DEFAULT 0,
                PRIMARY KEY (owner_key, space, photo_id)
            );
            CREATE INDEX IF NOT EXISTS photo_catalog_time
                ON photo_catalog(owner_key, space, is_deleted, taken_time DESC);
            CREATE INDEX IF NOT EXISTS photo_catalog_location
                ON photo_catalog(owner_key, space, is_deleted, country, city);
            CREATE INDEX IF NOT EXISTS photo_catalog_filename
                ON photo_catalog(owner_key, space, filename);
            CREATE TABLE IF NOT EXISTS photo_catalog_tags (
                owner_key TEXT NOT NULL,
                space TEXT NOT NULL,
                photo_id INTEGER NOT NULL,
                tag_id TEXT,
                tag_name TEXT NOT NULL,
                PRIMARY KEY (owner_key, space, photo_id, tag_name),
                FOREIGN KEY (owner_key, space, photo_id)
                    REFERENCES photo_catalog(owner_key, space, photo_id) ON DELETE CASCADE
            );
            CREATE INDEX IF NOT EXISTS photo_catalog_tags_name
                ON photo_catalog_tags(owner_key, space, tag_name, photo_id);
            CREATE TABLE IF NOT EXISTS photo_catalog_people (
                owner_key TEXT NOT NULL,
                space TEXT NOT NULL,
                photo_id INTEGER NOT NULL,
                person_id TEXT,
                person_name TEXT NOT NULL,
                PRIMARY KEY (owner_key, space, photo_id, person_name),
                FOREIGN KEY (owner_key, space, photo_id)
                    REFERENCES photo_catalog(owner_key, space, photo_id) ON DELETE CASCADE
            );
            CREATE INDEX IF NOT EXISTS photo_catalog_people_name
                ON photo_catalog_people(owner_key, space, person_name, photo_id);
            CREATE TABLE IF NOT EXISTS photo_catalog_sync (
                owner_key TEXT NOT NULL,
                space TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'idle',
                run_id TEXT,
                next_offset INTEGER NOT NULL DEFAULT 0,
                scanned_count INTEGER NOT NULL DEFAULT 0,
                started_at REAL,
                updated_at REAL NOT NULL,
                last_success_at REAL,
                error TEXT,
                PRIMARY KEY (owner_key, space)
            );
            """
        )
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass


def mark_running_syncs_interrupted(path: str = CATALOG_DB_PATH) -> None:
    with connect_catalog(path) as db:
        db.execute(
            "UPDATE photo_catalog_sync SET status='interrupted', error='服務重新啟動；可繼續同步。', updated_at=? "
            "WHERE status='running'",
            (time.time(),),
        )


def _json(value: object) -> str:
    return json.dumps(value if isinstance(value, (dict, list)) else {}, ensure_ascii=False, separators=(",", ":"))


def _number(value: object) -> float | None:
    try:
        return float(value) if value is not None and value != "" else None
    except (TypeError, ValueError):
        return None


def _integer(value: object) -> int | None:
    number = _number(value)
    return int(number) if number is not None else None


def _person_rows(value: object) -> list[tuple[str | None, str]]:
    if isinstance(value, dict):
        people = value.get("list")
        people = people if isinstance(people, list) else [value]
    elif isinstance(value, list):
        people = value
    else:
        people = []
    result = []
    for person in people:
        if isinstance(person, str):
            name, person_id = person.strip(), None
        elif isinstance(person, dict):
            name = str(person.get("name") or person.get("person_name") or "").strip()
            raw_id = person.get("id", person.get("person_id"))
            person_id = str(raw_id) if raw_id is not None else None
        else:
            continue
        if name and name.lower() != "unnamed":
            result.append((person_id, name))
    return list(dict.fromkeys(result))


def _catalog_record(summary: dict, detail: dict, owner_key: str, space: str, run_id: str) -> tuple[dict, list, list]:
    additional = detail.get("additional") if isinstance(detail.get("additional"), dict) else {}
    summary_additional = summary.get("additional") if isinstance(summary.get("additional"), dict) else {}
    # Some DSM builds omit list-only thumbnail cache information from get; preserve the list values.
    merged = dict(summary_additional)
    merged.update(additional)
    exif = merged.get("exif") if isinstance(merged.get("exif"), dict) else {}
    resolution = merged.get("resolution") if isinstance(merged.get("resolution"), dict) else {}
    gps = merged.get("gps") if isinstance(merged.get("gps"), dict) else {}
    address = merged.get("address") if isinstance(merged.get("address"), dict) else {}
    thumbnail = merged.get("thumbnail") if isinstance(merged.get("thumbnail"), dict) else {}
    tags_value = merged.get("tag") if isinstance(merged.get("tag"), list) else []
    tags = []
    for tag in tags_value:
        if not isinstance(tag, dict):
            continue
        name = tag.get("name")
        if isinstance(name, str) and name.strip():
            tag_id = tag.get("id", tag.get("tag_id"))
            tags.append((str(tag_id) if tag_id is not None else None, name.strip()))
    people = _person_rows(merged.get("person"))
    taken_time = _number(detail.get("time", summary.get("time")))
    if taken_time is not None and taken_time > 1e12:
        taken_time /= 1000
    record = {
        "owner_key": owner_key,
        "space": space,
        "photo_id": _integer(detail.get("id", summary.get("id"))),
        "filename": str(detail.get("filename") or summary.get("filename") or "（未命名）"),
        "item_type": detail.get("type", summary.get("type")),
        "taken_time": taken_time,
        "filesize": _integer(detail.get("filesize", summary.get("filesize"))),
        "folder_id": str(detail.get("folder_id", summary.get("folder_id"))) if detail.get("folder_id", summary.get("folder_id")) is not None else None,
        "indexed_time": _number(detail.get("indexed_time", summary.get("indexed_time"))),
        "live_type": str(detail.get("live_type", summary.get("live_type"))) if detail.get("live_type", summary.get("live_type")) is not None else None,
        "owner_user_id": str(detail.get("owner_user_id", summary.get("owner_user_id"))) if detail.get("owner_user_id", summary.get("owner_user_id")) is not None else None,
        "description": merged.get("description") if isinstance(merged.get("description"), str) else None,
        "camera": exif.get("camera"),
        "lens": exif.get("lens"),
        "aperture": exif.get("aperture"),
        "exposure_time": exif.get("exposure_time"),
        "focal_length": exif.get("focal_length"),
        "iso": exif.get("iso"),
        "orientation": str(merged.get("orientation")) if merged.get("orientation") is not None else None,
        "orientation_original": str(merged.get("orientation_original")) if merged.get("orientation_original") is not None else None,
        "width": _integer(resolution.get("width")),
        "height": _integer(resolution.get("height")),
        "latitude": _number(gps.get("latitude")),
        "longitude": _number(gps.get("longitude")),
        "country": address.get("country"),
        "state": address.get("state"),
        "county": address.get("county"),
        "city": address.get("city"),
        "district": address.get("district"),
        "town": address.get("town"),
        "village": address.get("village"),
        "route": address.get("route"),
        "landmark": address.get("landmark"),
        "geocoding_id": str(merged.get("geocoding_id")) if merged.get("geocoding_id") is not None else None,
        "exif_json": _json(exif),
        "resolution_json": _json(resolution),
        "gps_json": _json(gps),
        "address_json": _json(address),
        "thumbnail_cache_key": thumbnail.get("cache_key"),
        "thumbnail_unit_id": str(thumbnail.get("unit_id")) if thumbnail.get("unit_id") is not None else None,
        "thumbnail_ready": int(thumbnail.get("m") == "ready" or thumbnail.get("sm") == "ready"),
        "thumbnail_size": "m" if thumbnail.get("m") == "ready" else "sm",
        "metadata_synced_at": time.time(),
        "last_seen_run_id": run_id,
        "missing_runs": 0,
        "is_deleted": 0,
    }
    return record, tags, people


def begin_sync(owner_key: str, space: str, path: str = CATALOG_DB_PATH) -> tuple[str, int, int, bool]:
    now = time.time()
    with connect_catalog(path) as db:
        db.execute("BEGIN IMMEDIATE")
        state = db.execute(
            "SELECT * FROM photo_catalog_sync WHERE owner_key=? AND space=?", (owner_key, space)
        ).fetchone()
        if state and state["status"] == "running":
            db.rollback()
            return state["run_id"] or "", int(state["next_offset"]), int(state["scanned_count"]), False
        if state and state["status"] in {"interrupted", "failed"} and state["run_id"]:
            run_id = state["run_id"]
            offset = int(state["next_offset"])
            scanned = int(state["scanned_count"])
            db.execute(
                "UPDATE photo_catalog_sync SET status='running', error=NULL, updated_at=? WHERE owner_key=? AND space=?",
                (now, owner_key, space),
            )
        else:
            run_id = uuid.uuid4().hex
            offset = 0
            scanned = 0
            db.execute(
                "INSERT INTO photo_catalog_sync(owner_key,space,status,run_id,next_offset,scanned_count,started_at,updated_at,error) "
                "VALUES(?,?, 'running', ?,0,0,?,?,NULL) ON CONFLICT(owner_key,space) DO UPDATE SET "
                "status='running',run_id=excluded.run_id,next_offset=0,scanned_count=0,started_at=excluded.started_at,updated_at=excluded.updated_at,error=NULL",
                (owner_key, space, run_id, now, now),
            )
        db.commit()
    return run_id, offset, scanned, True


def save_sync_batch(owner_key: str, space: str, run_id: str, records: list[tuple[dict, list, list]],
                    next_offset: int, scanned_count: int, path: str = CATALOG_DB_PATH) -> None:
    if not records:
        return
    columns = list(records[0][0])
    placeholders = ",".join("?" for _ in columns)
    updates = ",".join(f"{column}=excluded.{column}" for column in columns if column not in {"owner_key", "space", "photo_id"})
    sql = f"INSERT INTO photo_catalog({','.join(columns)}) VALUES({placeholders}) ON CONFLICT(owner_key,space,photo_id) DO UPDATE SET {updates}"
    now = time.time()
    with connect_catalog(path) as db:
        db.execute("BEGIN IMMEDIATE")
        for record, tags, people in records:
            if not isinstance(record.get("photo_id"), int):
                continue
            db.execute(sql, [record[column] for column in columns])
            photo_id = record["photo_id"]
            db.execute("DELETE FROM photo_catalog_tags WHERE owner_key=? AND space=? AND photo_id=?", (owner_key, space, photo_id))
            db.executemany(
                "INSERT OR IGNORE INTO photo_catalog_tags(owner_key,space,photo_id,tag_id,tag_name) VALUES(?,?,?,?,?)",
                [(owner_key, space, photo_id, tag_id, name) for tag_id, name in tags],
            )
            db.execute("DELETE FROM photo_catalog_people WHERE owner_key=? AND space=? AND photo_id=?", (owner_key, space, photo_id))
            db.executemany(
                "INSERT OR IGNORE INTO photo_catalog_people(owner_key,space,photo_id,person_id,person_name) VALUES(?,?,?,?,?)",
                [(owner_key, space, photo_id, person_id, name) for person_id, name in people],
            )
        db.execute(
            "UPDATE photo_catalog_sync SET next_offset=?,scanned_count=?,updated_at=?,status='running',error=NULL "
            "WHERE owner_key=? AND space=? AND run_id=?",
            (next_offset, scanned_count, now, owner_key, space, run_id),
        )


def finish_sync(owner_key: str, space: str, run_id: str, next_offset: int, scanned_count: int,
                path: str = CATALOG_DB_PATH) -> None:
    now = time.time()
    with connect_catalog(path) as db:
        db.execute("BEGIN IMMEDIATE")
        db.execute(
            "UPDATE photo_catalog SET missing_runs=missing_runs+1 "
            "WHERE owner_key=? AND space=? AND last_seen_run_id<>? AND is_deleted=0",
            (owner_key, space, run_id),
        )
        db.execute(
            "UPDATE photo_catalog SET is_deleted=1 WHERE owner_key=? AND space=? AND missing_runs>=2",
            (owner_key, space),
        )
        db.execute(
            "UPDATE photo_catalog_sync SET status='complete',next_offset=?,scanned_count=?,updated_at=?,last_success_at=?,error=NULL "
            "WHERE owner_key=? AND space=? AND run_id=?",
            (next_offset, scanned_count, now, now, owner_key, space, run_id),
        )


def fail_sync(owner_key: str, space: str, run_id: str, error: str,
              path: str = CATALOG_DB_PATH) -> None:
    with connect_catalog(path) as db:
        db.execute(
            "UPDATE photo_catalog_sync SET status='failed',error=?,updated_at=? WHERE owner_key=? AND space=? AND run_id=?",
            (str(error)[:500], time.time(), owner_key, space, run_id),
        )


def sync_status(owner_key: str, space: str, path: str = CATALOG_DB_PATH, *, readonly: bool = False) -> dict:
    with connect_catalog(path, readonly=readonly) as db:
        state = db.execute(
            "SELECT * FROM photo_catalog_sync WHERE owner_key=? AND space=?", (owner_key, space)
        ).fetchone()
        count = db.execute(
            "SELECT COUNT(*) FROM photo_catalog WHERE owner_key=? AND space=? AND is_deleted=0",
            (owner_key, space),
        ).fetchone()[0]
    if not state:
        return {"status": "empty", "photo_count": count, "scanned_count": 0, "next_offset": 0}
    return {
        "status": state["status"], "photo_count": count,
        "scanned_count": int(state["scanned_count"]), "next_offset": int(state["next_offset"]),
        "started_at": state["started_at"], "updated_at": state["updated_at"],
        "last_success_at": state["last_success_at"], "error": state["error"],
        "run_id": state["run_id"],
    }


def _date_epoch_bounds(date_from: str | None, date_to: str | None) -> tuple[float | None, float | None]:
    start = end = None
    if date_from:
        start_day = date.fromisoformat(date_from)
        local_tz = timezone(timedelta(hours=8), name="Asia/Taipei")
        start = datetime.combine(start_day, datetime_time.min, tzinfo=local_tz).timestamp()
    if date_to:
        end_day = date.fromisoformat(date_to)
        local_tz = timezone(timedelta(hours=8), name="Asia/Taipei")
        end = datetime.combine(end_day + timedelta(days=1), datetime_time.min, tzinfo=local_tz).timestamp() - 1
    return start, end


def query_catalog(owner_key: str, space: str, *, keyword: str = "", date_from: str = "", date_to: str = "",
                  country: str = "", location: str = "", tag: str = "", person: str = "",
                  item_type: str = "", limit: int = 48, offset: int = 0,
                  path: str = CATALOG_DB_PATH, readonly: bool = False) -> dict:
    start, end = _date_epoch_bounds(date_from or None, date_to or None)
    where = ["p.owner_key=?", "p.space=?", "p.is_deleted=0"]
    params: list[object] = [owner_key, space]
    if start is not None:
        where.append("p.taken_time>=?")
        params.append(start)
    if end is not None:
        where.append("p.taken_time<=?")
        params.append(end)
    if country.strip():
        where.append("LOWER(COALESCE(p.country,'')) LIKE ?")
        params.append(f"%{country.strip().casefold()}%")
    if location.strip():
        where.append("(LOWER(COALESCE(p.city,'')) LIKE ? OR LOWER(COALESCE(p.state,'')) LIKE ? OR LOWER(COALESCE(p.county,'')) LIKE ? OR LOWER(COALESCE(p.district,'')) LIKE ? OR LOWER(COALESCE(p.town,'')) LIKE ? OR LOWER(COALESCE(p.village,'')) LIKE ? OR LOWER(COALESCE(p.route,'')) LIKE ? OR LOWER(COALESCE(p.landmark,'')) LIKE ?)")
        needle = f"%{location.strip().casefold()}%"
        params.extend([needle] * 8)
    if keyword.strip():
        where.append("(LOWER(p.filename) LIKE ? OR LOWER(COALESCE(p.description,'')) LIKE ? OR LOWER(COALESCE(p.camera,'')) LIKE ? OR LOWER(COALESCE(p.lens,'')) LIKE ?)")
        needle = f"%{keyword.strip().casefold()}%"
        params.extend([needle] * 4)
    if tag.strip():
        where.append("EXISTS (SELECT 1 FROM photo_catalog_tags t WHERE t.owner_key=p.owner_key AND t.space=p.space AND t.photo_id=p.photo_id AND LOWER(t.tag_name)=?)")
        params.append(tag.strip().casefold())
    if person.strip():
        where.append("EXISTS (SELECT 1 FROM photo_catalog_people n WHERE n.owner_key=p.owner_key AND n.space=p.space AND n.photo_id=p.photo_id AND LOWER(n.person_name)=?)")
        params.append(person.strip().casefold())
    if item_type.strip():
        where.append("LOWER(COALESCE(p.item_type,''))=?")
        params.append(item_type.strip().casefold())
    clause = " AND ".join(where)
    max_limit = min(max(int(limit), 1), MAX_QUERY_LIMIT)
    page_offset = max(int(offset), 0)
    with connect_catalog(path, readonly=readonly) as db:
        total = db.execute(f"SELECT COUNT(*) FROM photo_catalog p WHERE {clause}", params).fetchone()[0]
        rows = db.execute(
            f"SELECT p.* FROM photo_catalog p WHERE {clause} ORDER BY p.taken_time DESC, p.photo_id DESC LIMIT ? OFFSET ?",
            [*params, max_limit, page_offset],
        ).fetchall()
        keys = [(row["owner_key"], row["space"], row["photo_id"]) for row in rows]
        ids = [key[2] for key in keys]
        tags_by_id: dict[int, list[str]] = {}
        people_by_id: dict[int, list[str]] = {}
        if ids:
            marks = ",".join("?" for _ in ids)
            tag_rows = db.execute(
                f"SELECT photo_id,tag_name FROM photo_catalog_tags WHERE owner_key=? AND space=? AND photo_id IN ({marks}) ORDER BY tag_name COLLATE NOCASE",
                [owner_key, space, *ids],
            ).fetchall()
            people_rows = db.execute(
                f"SELECT photo_id,person_name FROM photo_catalog_people WHERE owner_key=? AND space=? AND photo_id IN ({marks}) ORDER BY person_name COLLATE NOCASE",
                [owner_key, space, *ids],
            ).fetchall()
            for tag_row in tag_rows:
                tags_by_id.setdefault(tag_row["photo_id"], []).append(tag_row["tag_name"])
            for person_row in people_rows:
                people_by_id.setdefault(person_row["photo_id"], []).append(person_row["person_name"])
    photos = []
    for row in rows:
        item = dict(row)
        item["tags"] = tags_by_id.get(row["photo_id"], [])
        item["people"] = people_by_id.get(row["photo_id"], [])
        photos.append(item)
    return {"photos": photos, "total": int(total), "offset": page_offset, "limit": max_limit, "has_more": page_offset + len(photos) < total}
