"""
memora_daily_sync.py
Location: F:\\AI_PROJECTS\\MemorA\\memora_daily_sync.py

Runs every day automatically via Windows Task Scheduler.
Syncs Gmail + Outlook + local file changes into MemorA.
Runs silently in background.
"""

import os
import sys
import json
import datetime

sys.path.insert(0, r"F:\AI_PROJECTS\MemorA")

LOG_PATH = r"F:\AI_DATA\MemorA\daily_sync_log.json"


def log(msg):
    print(f"  [{datetime.datetime.now().strftime('%H:%M:%S')}] {msg}")


def run_gmail_sync():
    try:
        log("Starting Gmail sync...")
        from memora_gmail import scan_gmail
        result = scan_gmail(max_emails=500)
        indexed = result.get("indexed", 0)
        att     = result.get("attachments", 0)
        log(f"Gmail done: {indexed} new emails, {att} attachments")
        return {"ok": True, "indexed": indexed, "attachments": att}
    except Exception as e:
        log(f"Gmail error: {e}")
        return {"ok": False, "error": str(e)}


def run_outlook_sync():
    try:
        from dotenv import load_dotenv
        load_dotenv(r"F:\AI_DEPLOY\Configs\Secrets\.env")
        client_id = os.getenv("OUTLOOK_CLIENT_ID", "")
        if not client_id or client_id == "paste_here":
            log("Outlook not configured — skipping")
            return {"ok": False, "error": "not_configured"}

        log("Starting Outlook sync...")
        from memora_outlook import scan_outlook
        result = scan_outlook(max_emails=500)
        indexed = result.get("indexed", 0)
        att     = result.get("attachments", 0)
        log(f"Outlook done: {indexed} new emails, {att} attachments")
        return {"ok": True, "indexed": indexed, "attachments": att}
    except Exception as e:
        log(f"Outlook error: {e}")
        return {"ok": False, "error": str(e)}


def run_local_scan():
    try:
        log("Starting local file delta scan...")
        from memora_scanner import scan_drives
        result = scan_drives()
        total = len(result) if result else 0
        log(f"Local scan done: {total} files total")
        return {"ok": True, "total": total}
    except Exception as e:
        log(f"Local scan error: {e}")
        return {"ok": False, "error": str(e)}


def save_log(results):
    history = []
    if os.path.exists(LOG_PATH):
        try:
            with open(LOG_PATH, "r") as f:
                history = json.load(f)
        except Exception:
            history = []

    entry = {
        "date":    datetime.date.today().isoformat(),
        "time":    datetime.datetime.now().strftime("%H:%M"),
        "results": results,
    }
    history = [h for h in history if h.get("date") != entry["date"]]
    history.insert(0, entry)
    history = history[:30]  # keep 30 days

    os.makedirs(os.path.dirname(LOG_PATH), exist_ok=True)
    with open(LOG_PATH, "w") as f:
        json.dump(history, f, indent=2)


def run_daily_sync(gmail=True, outlook=True, local=True):
    print()
    print("  MemorA Daily Sync")
    print("  " + "=" * 44)
    print(f"  Date: {datetime.date.today()}")
    print()

    results = {}

    if gmail:
        results["gmail"]   = run_gmail_sync()
        print()

    if outlook:
        results["outlook"] = run_outlook_sync()
        print()

    if local:
        results["local"]   = run_local_scan()
        print()

    save_log(results)

    print("  " + "=" * 44)
    print("  Daily sync complete.")
    print(f"  Log saved: {LOG_PATH}")
    print()
    return results


if __name__ == "__main__":
    run_daily_sync()
