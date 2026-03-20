"""
migrate_to_db.py
Location: F:\\AI_PROJECTS\\MemorA\\migrate_to_db.py

Run once - moves your existing scan_index.json into the new SQLite database.
Safe to run multiple times - skips already migrated files.
"""

import os
import json
import sys

sys.path.insert(0, r"F:\AI_PROJECTS\MemorA")
from memora_db import init_db, upsert_file, get_total_count

JSON_FILE = r"F:\AI_DATA\MemorA\scan_index.json"
DB_PATH   = r"F:\AI_DATA\MemorA\memora.db"


def migrate():
    print("  MemorA - Migrating JSON index to SQLite database...")

    # Init DB
    init_db()

    if not os.path.exists(JSON_FILE):
        print("  No JSON index found - starting fresh. Run RUN_MEMORA_SCAN.bat first.")
        return

    print("  Loading JSON index...")
    with open(JSON_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)

    files = data.get("files", [])
    total = len(files)
    print("  Found " + str(total) + " files in JSON index")

    migrated = 0
    for i, record in enumerate(files):
        try:
            r = {
                "path":       record.get("path", ""),
                "filename":   record.get("filename", ""),
                "ext":        record.get("ext", ""),
                "type":       record.get("type", "other"),
                "categories": ",".join(record.get("categories", ["uncategorised"])),
                "size":       record.get("size", 0),
                "size_hr":    record.get("size_hr", ""),
                "modified":   record.get("modified", ""),
                "drive":      record.get("drive", ""),
                "folder":     record.get("folder", ""),
                "content":    record.get("content", ""),
                "hash":       record.get("hash", ""),
                "indexed_at": record.get("indexed_at", ""),
            }
            if r["path"]:
                upsert_file(r)
                migrated += 1

            if i % 1000 == 0 and i > 0:
                print("  Migrated " + str(i) + " / " + str(total) + "...")

        except Exception as e:
            pass

    final_count = get_total_count()
    print("  Migration complete.")
    print("  Files in database: " + str(final_count))
    print("  Database at: " + DB_PATH)

    # Rename old JSON as backup
    backup = JSON_FILE.replace(".json", "_backup.json")
    if not os.path.exists(backup):
        os.rename(JSON_FILE, backup)
        print("  Old JSON backed up to: " + backup)


if __name__ == "__main__":
    migrate()
