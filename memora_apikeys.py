"""
memora_apikeys.py
Location: F:\\AI_PROJECTS\\MemorA\\memora_apikeys.py

API Key and Subscription Tracker for MemorA.
Tracks: API keys, usage, costs, expiry, data limits.
For developers, engineers, and personal subscriptions.
Stores encrypted in MemorA database.
"""

import os
import sys
import sqlite3
import datetime
import base64

sys.path.insert(0, r"F:\AI_PROJECTS\MemorA")

DB_PATH = r"F:\AI_DATA\MemorA\memora.db"

PROVIDERS = [
    "OpenAI", "Anthropic (Claude)", "Google (Gemini)", "Groq",
    "Sarvam AI", "AWS", "Azure", "Google Cloud",
    "GitHub", "GitLab", "Vercel", "Railway",
    "Supabase", "Firebase", "MongoDB Atlas",
    "Twilio", "SendGrid", "Mailgun",
    "Stripe", "Razorpay", "PayU",
    "NewsAPI", "Alpha Vantage", "FRED",
    "OpenWeatherMap", "Mapbox", "Here Maps",
    "Dropbox", "Box", "OneDrive",
    "Notion", "Airtable", "HubSpot",
    "Postman", "RapidAPI", "Other"
]

CATEGORIES = [
    "AI / LLM", "Cloud Compute", "Storage", "Database",
    "Email / SMS", "Payment", "Maps / Location", "Finance / Market",
    "News / Data", "DevOps / CI CD", "Authentication",
    "Personal Subscription", "SaaS Tool", "Other"
]

BILLING_CYCLES = ["monthly", "yearly", "pay-per-use", "one-time", "free"]
UNITS = ["tokens", "requests", "GB", "minutes", "messages", "queries", "credits", "calls", "free"]


def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_api_tables():
    conn = get_conn()
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS api_keys (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            name            TEXT NOT NULL,
            provider        TEXT,
            category        TEXT,
            api_key         TEXT,
            key_preview     TEXT,
            plan            TEXT,
            billing_cycle   TEXT DEFAULT 'monthly',
            cost_per_cycle  REAL DEFAULT 0,
            unit            TEXT DEFAULT 'requests',
            limit_per_cycle REAL DEFAULT 0,
            used_this_cycle REAL DEFAULT 0,
            cycle_reset_day INTEGER DEFAULT 1,
            expiry_date     TEXT,
            status          TEXT DEFAULT 'active',
            notes           TEXT,
            added_at        TEXT,
            updated_at      TEXT
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS api_usage_log (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            api_id     INTEGER,
            used       REAL,
            cost       REAL DEFAULT 0,
            logged_at  TEXT,
            notes      TEXT
        )
    """)
    conn.commit()
    conn.close()


def _enc(text, key="memora2025"):
    if not text:
        return ""
    key_bytes = (key * (len(text) // len(key) + 1)).encode()
    encrypted = bytes([ord(c) ^ key_bytes[i] for i, c in enumerate(str(text))])
    return base64.b64encode(encrypted).decode()


def _dec(text, key="memora2025"):
    if not text:
        return ""
    try:
        encrypted = base64.b64decode(text.encode())
        key_bytes = (key * (len(encrypted) // len(key) + 1)).encode()
        return "".join([chr(b ^ key_bytes[i]) for i, b in enumerate(encrypted)])
    except Exception:
        return text


def add_api_key(name, provider, category, api_key, plan="",
                billing_cycle="monthly", cost=0, unit="requests",
                limit_per_cycle=0, cycle_reset_day=1,
                expiry_date="", notes=""):
    conn = get_conn()
    c = conn.cursor()
    now = datetime.datetime.now().isoformat()
    # Store preview (first 6 + last 4 chars) for display
    preview = ""
    if api_key:
        preview = api_key[:6] + "..." + api_key[-4:] if len(api_key) > 10 else "***"
    c.execute("""
        INSERT INTO api_keys
            (name, provider, category, api_key, key_preview, plan,
             billing_cycle, cost_per_cycle, unit, limit_per_cycle,
             cycle_reset_day, expiry_date, status, notes, added_at, updated_at)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
    """, (name, provider, category, _enc(api_key), preview, plan,
          billing_cycle, cost, unit, limit_per_cycle,
          cycle_reset_day, expiry_date, "active", notes, now, now))
    conn.commit()
    conn.close()


def get_api_keys(category=None):
    conn = get_conn()
    c = conn.cursor()
    if category:
        rows = c.execute(
            "SELECT * FROM api_keys WHERE category=? ORDER BY provider,name",
            (category,)).fetchall()
    else:
        rows = c.execute(
            "SELECT * FROM api_keys ORDER BY category, provider, name").fetchall()
    conn.close()
    result = []
    for row in rows:
        d = dict(row)
        d["api_key_decrypted"] = _dec(d["api_key"])
        result.append(d)
    return result


def update_usage(api_id, used, cost=0, notes=""):
    conn = get_conn()
    c = conn.cursor()
    now = datetime.datetime.now().isoformat()
    c.execute("""
        UPDATE api_keys SET used_this_cycle = used_this_cycle + ?, updated_at = ?
        WHERE id = ?
    """, (used, now, api_id))
    c.execute("""
        INSERT INTO api_usage_log (api_id, used, cost, logged_at, notes)
        VALUES (?,?,?,?,?)
    """, (api_id, used, cost, now, notes))
    conn.commit()
    conn.close()


def reset_cycle(api_id):
    conn = get_conn()
    c = conn.cursor()
    c.execute("UPDATE api_keys SET used_this_cycle=0, updated_at=? WHERE id=?",
              (datetime.datetime.now().isoformat(), api_id))
    conn.commit()
    conn.close()


def delete_api_key(api_id):
    conn = get_conn()
    c = conn.cursor()
    c.execute("DELETE FROM api_keys WHERE id=?", (api_id,))
    c.execute("DELETE FROM api_usage_log WHERE api_id=?", (api_id,))
    conn.commit()
    conn.close()


def get_expiring_apis(days=30):
    conn = get_conn()
    c = conn.cursor()
    today = datetime.date.today()
    deadline = (today + datetime.timedelta(days=days)).isoformat()
    rows = c.execute("""
        SELECT * FROM api_keys
        WHERE expiry_date != '' AND expiry_date IS NOT NULL
          AND expiry_date <= ? AND expiry_date >= ?
        ORDER BY expiry_date
    """, (deadline, today.isoformat())).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_monthly_cost():
    conn = get_conn()
    c = conn.cursor()
    total = c.execute(
        "SELECT COALESCE(SUM(cost_per_cycle),0) FROM api_keys WHERE billing_cycle='monthly' AND status='active'"
    ).fetchone()[0]
    yearly = c.execute(
        "SELECT COALESCE(SUM(cost_per_cycle),0) FROM api_keys WHERE billing_cycle='yearly' AND status='active'"
    ).fetchone()[0]
    count = c.execute("SELECT COUNT(*) FROM api_keys WHERE status='active'").fetchone()[0]
    conn.close()
    return {
        "monthly_cost": total,
        "yearly_cost":  yearly,
        "total_keys":   count,
        "annual_total": total * 12 + yearly,
    }


def get_usage_summary():
    conn = get_conn()
    c = conn.cursor()
    rows = c.execute("""
        SELECT k.name, k.provider, k.unit, k.used_this_cycle, k.limit_per_cycle,
               k.cost_per_cycle, k.billing_cycle,
               CASE WHEN k.limit_per_cycle > 0
                    THEN ROUND(k.used_this_cycle * 100.0 / k.limit_per_cycle, 1)
                    ELSE 0 END as pct_used
        FROM api_keys k
        WHERE k.status = 'active'
        ORDER BY pct_used DESC
    """).fetchall()
    conn.close()
    return [dict(r) for r in rows]


# ── HTML FRAGMENT for the API Keys tab ───────────────────────
API_TAB_HTML = """
<div style="padding:16px 24px" id="apikeys-content">
  <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:14px">
    <div style="font-size:16px;font-weight:600">API Keys & Subscriptions</div>
    <button class="save" onclick="toggleAddApi()">+ Add Key</button>
  </div>

  <div id="api-summary" style="margin-bottom:14px"></div>
  <div id="api-form-wrap" style="display:none;margin-bottom:14px">
    <div class="form-box">
      <div style="font-size:13px;font-weight:500;margin-bottom:12px;color:var(--pl)">Add API Key / Subscription</div>
      <div class="fgrid">
        <div class="fg"><label>Name *</label><input id="akName" placeholder="e.g. Groq AI - Personal"></div>
        <div class="fg"><label>Provider</label>
          <select id="akProv">PROVIDER_OPTIONS</select></div>
        <div class="fg"><label>Category</label>
          <select id="akCat">CATEGORY_OPTIONS</select></div>
        <div class="fg"><label>Plan</label><input id="akPlan" placeholder="Free / Pro / Pay-as-you-go"></div>
        <div class="fg"><label>API Key (encrypted locally)</label>
          <input id="akKey" type="password" placeholder="sk-... or paste key"></div>
        <div class="fg"><label>Billing Cycle</label>
          <select id="akBill">BILLING_OPTIONS</select></div>
        <div class="fg"><label>Cost per Cycle (Rs)</label>
          <input id="akCost" type="number" placeholder="0 if free" value="0"></div>
        <div class="fg"><label>Unit</label>
          <select id="akUnit">UNIT_OPTIONS</select></div>
        <div class="fg"><label>Limit per Cycle</label>
          <input id="akLimit" type="number" placeholder="e.g. 1000000 tokens"></div>
        <div class="fg"><label>Expiry Date</label>
          <input id="akExpiry" type="date"></div>
        <div class="fg" style="grid-column:1/-1"><label>Notes</label>
          <input id="akNotes" placeholder="project, purpose, linked email etc."></div>
      </div>
      <button class="save" onclick="saveApiKey()">Save Key</button>
      <button class="cancel" onclick="toggleAddApi()" style="margin-left:8px">Cancel</button>
    </div>
  </div>

  <div id="api-usage" style="margin-bottom:14px"></div>
  <div id="api-list"></div>
</div>
"""


def build_api_html():
    html = API_TAB_HTML
    html = html.replace("PROVIDER_OPTIONS",
                        "".join([f"<option>{p}</option>" for p in PROVIDERS]))
    html = html.replace("CATEGORY_OPTIONS",
                        "".join([f"<option>{c}</option>" for c in CATEGORIES]))
    html = html.replace("BILLING_OPTIONS",
                        "".join([f"<option>{b}</option>" for b in BILLING_CYCLES]))
    html = html.replace("UNIT_OPTIONS",
                        "".join([f"<option>{u}</option>" for u in UNITS]))
    return html


# Init tables on import
init_api_tables()


if __name__ == "__main__":
    # Quick test
    print("API Keys module ready.")
    cost = get_monthly_cost()
    print(f"Total active keys: {cost['total_keys']}")
    print(f"Monthly cost: Rs {cost['monthly_cost']}")
