#!/usr/bin/env python3
"""Read-only query tool for the local Photo Tagger metadata catalog."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from photo_catalog import CATALOG_DB_PATH, query_catalog, sync_status


def main() -> int:
    parser = argparse.ArgumentParser(
        description="以唯讀方式查詢 Photo Tagger 本機 catalog；不會連線 NAS 或修改資料。"
    )
    parser.add_argument("--account", help="建立 catalog 時登入 Synology Photos 的帳號")
    parser.add_argument("--space", choices=("personal", "shared"), default="personal")
    parser.add_argument("--keyword", default="", help="檔名、描述、相機或鏡頭的部分文字")
    parser.add_argument("--date-from", default="", help="拍攝日期起始 YYYY-MM-DD")
    parser.add_argument("--date-to", default="", help="拍攝日期結束 YYYY-MM-DD")
    parser.add_argument("--country", default="", help="國家/地區，部分比對")
    parser.add_argument("--location", default="", help="城市、行政區、道路或地標，部分比對")
    parser.add_argument("--tag", default="", help="標籤完整名稱")
    parser.add_argument("--person", default="", help="Synology Photos 人物完整名稱")
    parser.add_argument("--type", dest="item_type", default="", help="例如 photo 或 video")
    parser.add_argument("--limit", type=int, default=48)
    parser.add_argument("--offset", type=int, default=0)
    parser.add_argument("--db", default=CATALOG_DB_PATH, help="catalog SQLite 檔案路徑")
    args = parser.parse_args()

    account = (args.account or input("Synology Photos 帳號（僅用於選擇本機資料，不會保存）: ")).strip()
    base_url = os.environ.get("SYNOLOGY_URL", "").strip().rstrip("/").casefold()
    if not account or not base_url:
        parser.error("必須提供帳號，且容器環境需設定 SYNOLOGY_URL。")
    owner_key = hashlib.sha256(f"{base_url}|{account.casefold()}".encode()).hexdigest()
    try:
        result = query_catalog(
            owner_key,
            args.space,
            keyword=args.keyword,
            date_from=args.date_from,
            date_to=args.date_to,
            country=args.country,
            location=args.location,
            tag=args.tag,
            person=args.person,
            item_type=args.item_type,
            limit=args.limit,
            offset=args.offset,
            path=args.db,
            readonly=True,
        )
        status = sync_status(owner_key, args.space, path=args.db, readonly=True)
    except (OSError, ValueError, sqlite3.Error) as exc:
        print(json.dumps({"error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 2
    for photo in result["photos"]:
        photo.pop("owner_key", None)
        photo.pop("last_seen_run_id", None)
    print(json.dumps({"source": "local_read_only_catalog", "space": args.space, "sync": status, **result}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
