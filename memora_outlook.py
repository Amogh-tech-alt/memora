"""
memora_outlook.py
Location: F:\\AI_PROJECTS\\MemorA\\memora_outlook.py

Scans Outlook.com / Hotmail / Live / Office365 emails
and indexes them into MemorA database.
Uses Microsoft Graph API - free.

Setup (one time):
  1. Go to https://portal.azure.com
  2. Azure Active Directory -> App registrations -> New registration
  3. Name: MemorA, Accounts: Personal Microsoft accounts
  4. Add redirect URI: http://localhost:8080
  5. API permissions -> Add -> Microsoft Graph -> Delegated
     -> Mail.Read -> Add
  6. Certificates & secrets -> New client secret -> Copy value
  7. Overview -> Copy Application (client) ID
  8. Paste both into F:\\AI_DEPLOY\\Configs\\Secrets\\.env:
     OUTLOOK_CLIENT_ID=paste_here
     OUTLOOK_CLIENT_SECRET=paste_here
"""

import os
import sys
import json
import datetime
import webbrowser
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs, urlencode
import requests

sys.path.insert(0, r"F:\AI_PROJECTS\MemorA")

CLIENT_ID     = os.getenv("OUTLOOK_CLIENT_ID", "")
CLIENT_SECRET = os.getenv("OUTLOOK_CLIENT_SECRET", "")
REDIRECT_URI  = "http://localhost:8080"
TOKEN_PATH    = r"F:\AI_DEPLOY\Configs\Secrets\outlook_token.json"
REPORT_PATH   = r"F:\AI_DATA\MemorA\outlook_scan_report.json"
SCOPE         = "https://graph.microsoft.com/Mail.Read offline_access"
AUTH_URL      = "https://login.microsoftonline.com/common/oauth2/v2.0/authorize"
TOKEN_URL     = "https://login.microsoftonline.com/common/oauth2/v2.0/token"
GRAPH_URL     = "https://graph.microsoft.com/v1.0"
MAX_EMAILS    = 1000

_auth_code = None


class AuthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        global _auth_code
        params = parse_qs(urlparse(self.path).query)
        _auth_code = params.get("code", [None])[0]
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"<h2>MemorA: Outlook connected! You can close this tab.</h2>")

    def log_message(self, *args):
        pass


def get_auth_code():
    global _auth_code
    _auth_code = None
    params = {
        "client_id":     CLIENT_ID,
        "response_type": "code",
        "redirect_uri":  REDIRECT_URI,
        "scope":         SCOPE,
        "response_mode": "query",
    }
    url = AUTH_URL + "?" + urlencode(params)
    print("  Opening browser for Outlook login...")
    webbrowser.open(url)
    server = HTTPServer(("localhost", 8080), AuthHandler)
    server.timeout = 120
    server.handle_request()
    return _auth_code


def get_token_from_code(code):
    resp = requests.post(TOKEN_URL, data={
        "client_id":     CLIENT_ID,
        "client_secret": CLIENT_SECRET,
        "code":          code,
        "redirect_uri":  REDIRECT_URI,
        "grant_type":    "authorization_code",
        "scope":         SCOPE,
    })
    return resp.json()


def refresh_token(refresh_tok):
    resp = requests.post(TOKEN_URL, data={
        "client_id":     CLIENT_ID,
        "client_secret": CLIENT_SECRET,
        "refresh_token": refresh_tok,
        "grant_type":    "refresh_token",
        "scope":         SCOPE,
    })
    return resp.json()


def load_token():
    if os.path.exists(TOKEN_PATH):
        with open(TOKEN_PATH, "r") as f:
            return json.load(f)
    return None


def save_token(token_data):
    token_data["saved_at"] = datetime.datetime.now().isoformat()
    with open(TOKEN_PATH, "w") as f:
        json.dump(token_data, f, indent=2)


def get_access_token():
    if not CLIENT_ID:
        print("  OUTLOOK_CLIENT_ID not set in .env")
        print("  See setup instructions at top of this file.")
        return None

    token = load_token()

    if token:
        saved = datetime.datetime.fromisoformat(token.get("saved_at", "2000-01-01"))
        expires_in = token.get("expires_in", 3600)
        age = (datetime.datetime.now() - saved).total_seconds()
        if age < expires_in - 60:
            return token["access_token"]
        if token.get("refresh_token"):
            print("  Refreshing Outlook token...")
            new_token = refresh_token(token["refresh_token"])
            if "access_token" in new_token:
                save_token(new_token)
                return new_token["access_token"]

    code = get_auth_code()
    if not code:
        print("  Login failed or timed out.")
        return None
    token_data = get_token_from_code(code)
    if "access_token" not in token_data:
        print("  Token error: " + str(token_data))
        return None
    save_token(token_data)
    print("  Outlook login successful.")
    return token_data["access_token"]


def graph_get(access_token, endpoint, params=None):
    headers = {"Authorization": "Bearer " + access_token, "Accept": "application/json"}
    url = GRAPH_URL + endpoint
    resp = requests.get(url, headers=headers, params=params or {})
    if resp.status_code == 200:
        return resp.json()
    return None


def categorise(subject, sender, body):
    text = (subject + " " + sender + " " + (body or "")).lower()
    cats = []
    rules = {
        "bank":       ["bank", "hdfc", "sbi", "icici", "axis", "statement", "account"],
        "insurance":  ["insurance", "policy", "premium", "claim", "mediclaim", "lic"],
        "tax":        ["itr", "income tax", "tds", "form 16", "refund"],
        "gst":        ["gst", "gstin", "tax invoice"],
        "salary":     ["salary", "payslip", "payroll", "ctc"],
        "shopping":   ["order", "invoice", "amazon", "flipkart", "delivered"],
        "travel":     ["ticket", "booking", "pnr", "flight", "hotel", "irctc"],
        "medical":    ["hospital", "medical", "prescription", "report", "doctor"],
        "government": ["aadhaar", "pan", "passport", "voter", "uidai"],
        "utility":    ["electricity", "water", "gas", "broadband", "bill"],
        "finance":    ["mutual fund", "sip", "demat", "dividend", "portfolio"],
        "loan":       ["loan", "emi", "outstanding", "due date"],
    }
    for cat, keywords in rules.items():
        for kw in keywords:
            if kw in text:
                cats.append(cat)
                break
    return ",".join(cats) if cats else "email"


def scan_outlook(max_emails=MAX_EMAILS):
    from dotenv import load_dotenv
    load_dotenv(r"F:\AI_DEPLOY\Configs\Secrets\.env")

    global CLIENT_ID, CLIENT_SECRET
    CLIENT_ID     = os.getenv("OUTLOOK_CLIENT_ID", "")
    CLIENT_SECRET = os.getenv("OUTLOOK_CLIENT_SECRET", "")

    print()
    print("  MemorA Outlook Scanner")
    print("  " + "-" * 44)

    access_token = get_access_token()
    if not access_token:
        return {"error": "auth_failed", "indexed": 0}

    # Get user email
    me = graph_get(access_token, "/me")
    email_addr = me.get("mail") or me.get("userPrincipalName", "outlook") if me else "outlook"
    print(f"  Connected: {email_addr}")

    from memora_db import init_db, upsert_file, get_conn
    init_db()

    # Load existing
    conn = get_conn()
    existing = set(
        row[0] for row in
        conn.cursor().execute(
            "SELECT path FROM files WHERE drive='Outlook'"
        ).fetchall()
    )
    conn.close()
    print(f"  Previously indexed: {len(existing)} emails")

    indexed = 0
    skipped = 0
    attachments = 0
    errors = 0
    report_data = []

    next_url = None
    params = {
        "$top": 50,
        "$select": "id,subject,from,receivedDateTime,bodyPreview,hasAttachments",
        "$orderby": "receivedDateTime desc",
    }

    while indexed + skipped < max_emails:
        if next_url:
            data = graph_get(access_token, "", {}) or {}
            headers = {"Authorization": "Bearer " + access_token}
            resp = requests.get(next_url, headers=headers)
            data = resp.json() if resp.status_code == 200 else {}
        else:
            data = graph_get(access_token, "/me/messages", params) or {}

        messages = data.get("value", [])
        if not messages:
            break

        for msg in messages:
            msg_id   = msg.get("id", "")
            path     = f"outlook://{email_addr}/{msg_id}"

            if path in existing:
                skipped += 1
                continue

            try:
                subject  = msg.get("subject", "No Subject")[:200]
                sender   = msg.get("from", {}).get("emailAddress", {}).get("address", "")
                date_str = msg.get("receivedDateTime", "")[:10]
                snippet  = msg.get("bodyPreview", "")[:300]
                has_att  = msg.get("hasAttachments", False)
                cats     = categorise(subject, sender, snippet)

                record = {
                    "path":       path,
                    "filename":   subject,
                    "ext":        ".email",
                    "type":       "email",
                    "categories": cats,
                    "size":       0,
                    "size_hr":    "email",
                    "modified":   date_str,
                    "drive":      "Outlook",
                    "folder":     email_addr,
                    "content":    f"From: {sender} | {snippet}",
                    "hash":       msg_id,
                    "indexed_at": datetime.datetime.now().isoformat(),
                }
                upsert_file(record)
                indexed += 1

                # Fetch attachments if any
                if has_att:
                    att_data = graph_get(
                        access_token,
                        f"/me/messages/{msg_id}/attachments",
                        {"$select": "name,size,contentType"}
                    ) or {}
                    for att in att_data.get("value", []):
                        att_name = att.get("name", "attachment")
                        att_size = att.get("size", 0)
                        att_path = f"outlook://{email_addr}/{msg_id}/att/{att_name}"
                        ext = os.path.splitext(att_name)[1].lower()
                        att_record = {
                            "path":       att_path,
                            "filename":   att_name,
                            "ext":        ext,
                            "type":       "document" if ext in [".pdf",".doc",".docx",".xls",".xlsx"] else "other",
                            "categories": cats + ",attachment",
                            "size":       att_size,
                            "size_hr":    f"{att_size//1024} KB" if att_size > 1024 else f"{att_size} B",
                            "modified":   date_str,
                            "drive":      "Outlook",
                            "folder":     f"Outlook/{email_addr}",
                            "content":    f"Attachment from: {sender} | {subject}",
                            "hash":       att_path,
                            "indexed_at": datetime.datetime.now().isoformat(),
                        }
                        upsert_file(att_record)
                        attachments += 1

                report_data.append({
                    "subject": subject, "sender": sender,
                    "date": date_str, "categories": cats,
                    "attachments": 1 if has_att else 0,
                })

                if (indexed + skipped) % 50 == 0:
                    print(f"    Progress: {indexed} new, {skipped} skipped...")

            except Exception:
                errors += 1

        next_url = data.get("@odata.nextLink")
        if not next_url:
            break

    report = {
        "scanned_at":  datetime.datetime.now().isoformat(),
        "email":       email_addr,
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
    print("  OUTLOOK SCAN COMPLETE")
    print(f"  Account     : {email_addr}")
    print(f"  New emails  : {indexed}")
    print(f"  Attachments : {attachments}")
    print(f"  Cached      : {skipped}")
    print("  ============================================")
    return report


def revoke_access():
    if os.path.exists(TOKEN_PATH):
        os.remove(TOKEN_PATH)
        print("  Outlook disconnected.")
    else:
        print("  No Outlook token found.")


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "revoke":
        revoke_access()
    else:
        scan_outlook()
