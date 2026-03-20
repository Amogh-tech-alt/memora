"""
memora_gmail.py
Location: F:\\AI_PROJECTS\\MemorA\\memora_gmail.py

Scans Gmail - indexes emails and attachments into MemorA.
Searches show Gmail results alongside local files.
Read-only. Nothing is sent or deleted.

Setup:
  1. Get credentials.json from https://console.cloud.google.com
  2. Save to F:\\AI_DEPLOY\\Configs\\Secrets\\gmail_credentials.json
  3. Run this file - browser opens for one-time login
  4. Token saved locally - never logs in again
"""

import os
import sys
import json
import datetime
import base64

sys.path.insert(0, r"F:\AI_PROJECTS\MemorA")

CREDS_PATH  = r"F:\AI_DEPLOY\Configs\Secrets\gmail_credentials.json"
TOKEN_PATH  = r"F:\AI_DEPLOY\Configs\Secrets\gmail_token.json"
REPORT_PATH = r"F:\AI_DATA\MemorA\gmail_scan_report.json"
SCOPES      = ["https://www.googleapis.com/auth/gmail.readonly"]
MAX_EMAILS  = 1000


def install_google_libs():
    print("  Installing Google API libraries...")
    os.system(
        '"F:\\AI_TOOLS\\Python_Envs\\agent_env\\Scripts\\pip.exe" '
        'install google-api-python-client google-auth-httplib2 '
        'google-auth-oauthlib --quiet'
    )


def get_service():
    try:
        from google.oauth2.credentials import Credentials
        from google_auth_oauthlib.flow import InstalledAppFlow
        from google.auth.transport.requests import Request
        from googleapiclient.discovery import build
    except ImportError:
        install_google_libs()
        from google.oauth2.credentials import Credentials
        from google_auth_oauthlib.flow import InstalledAppFlow
        from google.auth.transport.requests import Request
        from googleapiclient.discovery import build

    if not os.path.exists(CREDS_PATH):
        print()
        print("  Gmail credentials not found.")
        print("  Please follow these steps:")
        print()
        print("  1. Go to: https://console.cloud.google.com")
        print("  2. Create project named MemorA")
        print("  3. Enable Gmail API")
        print("  4. Create OAuth credentials (Desktop app)")
        print("  5. Download JSON and save to:")
        print("     " + CREDS_PATH)
        print()
        return None

    creds = None
    if os.path.exists(TOKEN_PATH):
        creds = Credentials.from_authorized_user_file(TOKEN_PATH, SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            try:
                from google.auth.transport.requests import Request as GRequest
                creds.refresh(GRequest())
            except Exception:
                creds = None

        if not creds:
            print("  Opening browser for Gmail login (one time only)...")
            flow = InstalledAppFlow.from_client_secrets_file(CREDS_PATH, SCOPES)
            creds = flow.run_local_server(port=0)

        with open(TOKEN_PATH, "w") as f:
            f.write(creds.to_json())
        print("  Login successful. Token saved.")

    return build("gmail", "v1", credentials=creds)


def get_email_address(service):
    try:
        profile = service.users().getProfile(userId="me").execute()
        return profile.get("emailAddress", "gmail")
    except Exception:
        return "gmail"


def decode_body(data):
    try:
        return base64.urlsafe_b64decode(data + "==").decode("utf-8", errors="ignore")[:500]
    except Exception:
        return ""


def parse_message(msg):
    payload  = msg.get("payload", {})
    headers  = {h["name"].lower(): h["value"] for h in payload.get("headers", [])}
    subject  = headers.get("subject", "No Subject")[:200]
    sender   = headers.get("from", "")[:100]
    date_str = headers.get("date", "")[:30]
    msg_id   = msg.get("id", "")
    thread   = msg.get("threadId", "")

    # Parse date
    try:
        import email.utils
        parsed = email.utils.parsedate_tz(date_str)
        if parsed:
            ts = email.utils.mktime_tz(parsed)
            dt = datetime.datetime.fromtimestamp(ts)
            date_iso = dt.date().isoformat()
        else:
            date_iso = datetime.date.today().isoformat()
    except Exception:
        date_iso = datetime.date.today().isoformat()

    # Find attachments
    attachments = []
    parts = payload.get("parts", [])
    if not parts:
        parts = [payload]

    for part in parts:
        filename = part.get("filename", "")
        mime     = part.get("mimeType", "")
        if filename and len(filename) > 0:
            att_id = part.get("body", {}).get("attachmentId", "")
            size   = part.get("body", {}).get("size", 0)
            attachments.append({
                "filename":      filename,
                "mime":          mime,
                "attachment_id": att_id,
                "size":          size,
                "size_hr":       f"{size//1024} KB" if size > 1024 else f"{size} B",
            })

    # Snippet for content preview
    snippet = msg.get("snippet", "")[:300]

    return {
        "msg_id":      msg_id,
        "thread_id":   thread,
        "subject":     subject,
        "sender":      sender,
        "date":        date_iso,
        "snippet":     snippet,
        "attachments": attachments,
    }


def categorise_email(subject, sender, snippet):
    text = (subject + " " + sender + " " + snippet).lower()
    cats = []
    rules = {
        "bank":        ["bank", "hdfc", "sbi", "icici", "axis", "kotak", "statement", "account"],
        "insurance":   ["insurance", "lic", "policy", "premium", "claim", "mediclaim"],
        "tax":         ["itr", "income tax", "tds", "form 16", "refund", "efiling"],
        "gst":         ["gst", "gstin", "tax invoice", "e-invoice"],
        "salary":      ["salary", "payslip", "payroll", "ctc", "increment"],
        "shopping":    ["order", "invoice", "amazon", "flipkart", "delivered", "payment"],
        "travel":      ["ticket", "booking", "pnr", "flight", "hotel", "irctc"],
        "medical":     ["hospital", "medical", "prescription", "report", "doctor", "lab"],
        "government":  ["aadhaar", "pan", "passport", "voter", "uidai", "nsdl", "government"],
        "education":   ["school", "college", "fees", "result", "admit", "certificate"],
        "utility":     ["electricity", "water", "gas", "broadband", "bill", "bescom"],
        "finance":     ["mutual fund", "sip", "demat", "portfolio", "dividend", "nav"],
        "loan":        ["loan", "emi", "home loan", "outstanding", "due"],
    }
    for cat, keywords in rules.items():
        for kw in keywords:
            if kw in text:
                cats.append(cat)
                break
    return ",".join(cats) if cats else "email"


def scan_gmail(max_emails=MAX_EMAILS, label="INBOX"):
    print()
    print("  MemorA Gmail Scanner")
    print("  " + "-" * 44)

    service = get_service()
    if not service:
        return {"error": "credentials_missing", "indexed": 0}

    email_addr = get_email_address(service)
    print(f"  Connected: {email_addr}")

    from memora_db import init_db, upsert_file, get_conn

    init_db()

    # Load existing indexed msg IDs
    conn = get_conn()
    existing = set(
        row[0] for row in
        conn.cursor().execute(
            "SELECT path FROM files WHERE drive='Gmail'"
        ).fetchall()
    )
    conn.close()
    print(f"  Previously indexed: {len(existing)} emails")

    # Fetch email list
    print(f"  Fetching up to {max_emails} emails from {label}...")
    messages = []
    page_token = None

    while len(messages) < max_emails:
        batch = max_emails - len(messages)
        kwargs = {
            "userId": "me",
            "maxResults": min(batch, 500),
            "labelIds": [label],
        }
        if page_token:
            kwargs["pageToken"] = page_token

        result = service.users().messages().list(**kwargs).execute()
        batch_msgs = result.get("messages", [])
        messages.extend(batch_msgs)

        page_token = result.get("nextPageToken")
        if not page_token or not batch_msgs:
            break

    print(f"  Found {len(messages)} emails. Scanning new ones...")

    indexed     = 0
    skipped     = 0
    attachments = 0
    errors      = 0
    report_data = []

    for i, msg_ref in enumerate(messages):
        msg_id  = msg_ref["id"]
        path    = f"gmail://{email_addr}/{msg_id}"

        if path in existing:
            skipped += 1
            continue

        try:
            msg     = service.users().messages().get(
                userId="me", id=msg_id, format="full"
            ).execute()
            parsed  = parse_message(msg)
            cats    = categorise_email(
                parsed["subject"], parsed["sender"], parsed["snippet"]
            )

            # Index main email
            record = {
                "path":       path,
                "filename":   parsed["subject"],
                "ext":        ".email",
                "type":       "email",
                "categories": cats,
                "size":       0,
                "size_hr":    "email",
                "modified":   parsed["date"],
                "drive":      "Gmail",
                "folder":     email_addr,
                "content":    f"From: {parsed['sender']} | {parsed['snippet']}",
                "hash":       msg_id,
                "indexed_at": datetime.datetime.now().isoformat(),
            }
            upsert_file(record)
            indexed += 1

            # Index each attachment separately
            for att in parsed["attachments"]:
                att_path = f"gmail://{email_addr}/{msg_id}/att/{att['filename']}"
                ext = os.path.splitext(att["filename"])[1].lower()
                att_record = {
                    "path":       att_path,
                    "filename":   att["filename"],
                    "ext":        ext,
                    "type":       "document" if ext in [".pdf",".doc",".docx",".xls",".xlsx"] else "other",
                    "categories": cats + ",attachment",
                    "size":       att["size"],
                    "size_hr":    att["size_hr"],
                    "modified":   parsed["date"],
                    "drive":      "Gmail",
                    "folder":     f"Gmail/{email_addr}",
                    "content":    f"Attachment from: {parsed['sender']} | Subject: {parsed['subject']}",
                    "hash":       att_path,
                    "indexed_at": datetime.datetime.now().isoformat(),
                }
                upsert_file(att_record)
                attachments += 1

            report_data.append({
                "subject":     parsed["subject"],
                "sender":      parsed["sender"],
                "date":        parsed["date"],
                "categories":  cats,
                "attachments": len(parsed["attachments"]),
            })

            if (indexed + skipped) % 50 == 0:
                print(f"    Progress: {indexed} new, {skipped} skipped, {attachments} attachments...")

        except Exception as e:
            errors += 1

    # Save scan report
    report = {
        "scanned_at":  datetime.datetime.now().isoformat(),
        "email":       email_addr,
        "label":       label,
        "total_found": len(messages),
        "indexed":     indexed,
        "skipped":     skipped,
        "attachments": attachments,
        "errors":      errors,
        "sample":      report_data[:20],
    }
    os.makedirs(os.path.dirname(REPORT_PATH), exist_ok=True)
    with open(REPORT_PATH, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)

    print()
    print("  ============================================")
    print("  GMAIL SCAN COMPLETE")
    print(f"  Email account  : {email_addr}")
    print(f"  New emails     : {indexed}")
    print(f"  Attachments    : {attachments}")
    print(f"  Already indexed: {skipped}")
    print(f"  Errors skipped : {errors}")
    print(f"  Report saved   : {REPORT_PATH}")
    print()
    print("  Now search in MemorA:")
    print("  'hdfc statement'  -> shows both local files AND Gmail emails")
    print("  'insurance'       -> shows policies from files AND Gmail")
    print("  'attachment pdf'  -> shows all PDF attachments in Gmail")
    print("  ============================================")
    print()

    return report


def revoke_access():
    """Delete token to disconnect Gmail from MemorA."""
    if os.path.exists(TOKEN_PATH):
        os.remove(TOKEN_PATH)
        print("  Gmail disconnected. Token deleted.")
        print("  MemorA can no longer access your Gmail.")
    else:
        print("  No Gmail token found.")


def get_scan_report():
    if os.path.exists(REPORT_PATH):
        with open(REPORT_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    return None


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "revoke":
        revoke_access()
    else:
        scan_gmail()
