"""
memora_cloud_db.py
Cloud version of MemorA database.
Each user has their own isolated data.
Uses SQLite stored in /data/ (Render persistent disk).
"""

import os
import sqlite3
import datetime
import base64
import hashlib
import secrets

# On Render use /data/ persistent disk, locally use F: drive
if os.path.exists("/data"):
    DB_DIR = "/data/memora"
else:
    DB_DIR = r"F:\AI_DATA\MemorA\cloud"

os.makedirs(DB_DIR, exist_ok=True)

USERS_DB = os.path.join(DB_DIR, "users.db")


def get_users_conn():
    conn = sqlite3.connect(USERS_DB)
    conn.row_factory = sqlite3.Row
    return conn


def get_user_db(user_id: str):
    path = os.path.join(DB_DIR, f"user_{user_id}.db")
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    return conn


def init_users_db():
    conn = get_users_conn()
    c = conn.cursor()
    c.execute("""CREATE TABLE IF NOT EXISTS users (
        id          TEXT PRIMARY KEY,
        email       TEXT UNIQUE NOT NULL,
        name        TEXT,
        password    TEXT NOT NULL,
        plan        TEXT DEFAULT 'free',
        created_at  TEXT,
        last_login  TEXT,
        is_active   INTEGER DEFAULT 1
    )""")
    c.execute("CREATE INDEX IF NOT EXISTS idx_email ON users(email)")
    conn.commit()
    conn.close()


def init_user_db(user_id: str):
    conn = get_user_db(user_id)
    c = conn.cursor()
    c.execute("""CREATE TABLE IF NOT EXISTS files (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        path TEXT, filename TEXT NOT NULL,
        ext TEXT, type TEXT, categories TEXT,
        size INTEGER DEFAULT 0, size_hr TEXT,
        modified TEXT, drive TEXT, folder TEXT,
        content TEXT, file_hash TEXT, indexed_at TEXT,
        open_count INTEGER DEFAULT 0, last_opened TEXT,
        tags TEXT DEFAULT '', source TEXT DEFAULT 'upload'
    )""")
    c.execute("""CREATE TABLE IF NOT EXISTS bills (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL, category TEXT, amount REAL,
        due_day INTEGER, frequency TEXT DEFAULT 'monthly',
        auto_debit INTEGER DEFAULT 0, status TEXT DEFAULT 'pending',
        account TEXT, notes TEXT, added_at TEXT, updated_at TEXT)""")
    c.execute("""CREATE TABLE IF NOT EXISTS bill_payments (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        bill_id INTEGER, amount REAL, paid_date TEXT,
        mode TEXT, reference TEXT)""")
    c.execute("""CREATE TABLE IF NOT EXISTS credentials (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        label TEXT NOT NULL, category TEXT,
        username TEXT, password TEXT,
        url TEXT, notes TEXT, added_at TEXT)""")
    c.execute("""CREATE TABLE IF NOT EXISTS expiry (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        doc_name TEXT NOT NULL, doc_type TEXT,
        expiry_date TEXT NOT NULL, notes TEXT, added_at TEXT)""")
    c.execute("CREATE INDEX IF NOT EXISTS idx_filename ON files(filename)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_type     ON files(type)")
    conn.commit()
    conn.close()


# ── PASSWORD HASHING ─────────────────────────────────────────

def hash_password(password: str) -> str:
    salt = secrets.token_hex(16)
    hashed = hashlib.sha256((salt + password).encode()).hexdigest()
    return salt + ":" + hashed


def verify_password(password: str, stored: str) -> bool:
    try:
        salt, hashed = stored.split(":")
        return hashlib.sha256((salt + password).encode()).hexdigest() == hashed
    except Exception:
        return False


# ── USER OPERATIONS ───────────────────────────────────────────

def create_user(email: str, name: str, password: str) -> dict:
    conn = get_users_conn()
    c = conn.cursor()
    existing = c.execute("SELECT id FROM users WHERE email=?", (email,)).fetchone()
    if existing:
        conn.close()
        return {"ok": False, "error": "Email already registered"}
    user_id = secrets.token_hex(8)
    now = datetime.datetime.now().isoformat()
    c.execute("""INSERT INTO users (id,email,name,password,created_at,last_login)
                 VALUES (?,?,?,?,?,?)""",
              (user_id, email.lower(), name, hash_password(password), now, now))
    conn.commit()
    conn.close()
    init_user_db(user_id)
    return {"ok": True, "user_id": user_id, "email": email, "name": name}


def login_user(email: str, password: str) -> dict:
    conn = get_users_conn()
    c = conn.cursor()
    row = c.execute("SELECT * FROM users WHERE email=? AND is_active=1",
                    (email.lower(),)).fetchone()
    if not row:
        conn.close()
        return {"ok": False, "error": "Email not found"}
    user = dict(row)
    if not verify_password(password, user["password"]):
        conn.close()
        return {"ok": False, "error": "Wrong password"}
    c.execute("UPDATE users SET last_login=? WHERE id=?",
              (datetime.datetime.now().isoformat(), user["id"]))
    conn.commit()
    conn.close()
    token = secrets.token_hex(32)
    return {"ok": True, "token": token, "user_id": user["id"],
            "name": user["name"], "email": user["email"]}


def get_user_by_id(user_id: str) -> dict:
    conn = get_users_conn()
    row = conn.cursor().execute(
        "SELECT id,email,name,plan,created_at FROM users WHERE id=?",
        (user_id,)).fetchone()
    conn.close()
    return dict(row) if row else None


# ── FILE OPERATIONS PER USER ──────────────────────────────────

def upsert_file(user_id: str, record: dict):
    conn = get_user_db(user_id)
    c = conn.cursor()
    c.execute("""INSERT INTO files
        (path,filename,ext,type,categories,size,size_hr,
         modified,drive,folder,content,file_hash,indexed_at,source)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        ON CONFLICT(path) DO UPDATE SET
        filename=excluded.filename, categories=excluded.categories,
        content=excluded.content, indexed_at=excluded.indexed_at""",
        (record.get("path",""), record.get("filename",""),
         record.get("ext",""), record.get("type","other"),
         record.get("categories",""), record.get("size",0),
         record.get("size_hr",""), record.get("modified",""),
         record.get("drive","upload"), record.get("folder",""),
         record.get("content",""), record.get("hash",""),
         datetime.datetime.now().isoformat(),
         record.get("source","upload")))
    conn.commit()
    conn.close()


def search_files(user_id: str, query: str, limit: int = 50) -> list:
    conn = get_user_db(user_id)
    c = conn.cursor()
    words = [w for w in query.lower().split() if len(w) >= 2]
    if not words:
        words = [query.lower()]

    conditions, params = [], []
    for word in words:
        like = f"%{word}%"
        conditions.append(
            "(LOWER(filename) LIKE ? OR LOWER(content) LIKE ? OR LOWER(categories) LIKE ?)"
        )
        params.extend([like, like, like])

    where = " AND ".join(conditions) if conditions else "1=1"
    main_like = f"%{query.lower()}%"
    sql = f"""
        SELECT *,
          (CASE WHEN LOWER(filename) LIKE ? THEN 100 ELSE 0 END +
           CASE WHEN LOWER(content)  LIKE ? THEN 30  ELSE 0 END +
           open_count * 3) as score
        FROM files WHERE {where}
        ORDER BY score DESC, modified DESC LIMIT ?
    """
    rows = c.execute(sql, [main_like, main_like] + params + [limit]).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_stats(user_id: str) -> dict:
    conn = get_user_db(user_id)
    c = conn.cursor()
    total    = c.execute("SELECT COUNT(*) FROM files").fetchone()[0]
    by_type  = dict(c.execute("SELECT type, COUNT(*) FROM files GROUP BY type").fetchall())
    by_drive = dict(c.execute("SELECT drive, COUNT(*) FROM files GROUP BY drive").fetchall())
    conn.close()
    return {"total": total, "by_type": by_type, "by_drive": by_drive}


def increment_open(user_id: str, file_id: int):
    conn = get_user_db(user_id)
    conn.cursor().execute(
        "UPDATE files SET open_count=open_count+1, last_opened=? WHERE id=?",
        (datetime.datetime.now().isoformat(), file_id))
    conn.commit()
    conn.close()


# ── BILLS PER USER ────────────────────────────────────────────

def add_bill(user_id, name, category, amount, due_day,
             frequency="monthly", auto_debit=0, account="", notes=""):
    conn = get_user_db(user_id)
    now = datetime.datetime.now().isoformat()
    conn.cursor().execute("""INSERT INTO bills
        (name,category,amount,due_day,frequency,auto_debit,
         account,notes,status,added_at,updated_at)
        VALUES (?,?,?,?,?,?,?,?,'pending',?,?)""",
        (name,category,amount,due_day,frequency,auto_debit,account,notes,now,now))
    conn.commit()
    conn.close()


def get_bills(user_id: str) -> list:
    conn = get_user_db(user_id)
    rows = conn.cursor().execute("SELECT * FROM bills ORDER BY due_day").fetchall()
    conn.close()
    return [dict(r) for r in rows]


def mark_paid(user_id: str, bill_id: int, amount: float, mode: str = "UPI"):
    conn = get_user_db(user_id)
    c = conn.cursor()
    today = datetime.date.today().isoformat()
    c.execute("UPDATE bills SET status='paid',last_paid=?,last_amount=? WHERE id=?",
              (today, amount, bill_id))
    c.execute("INSERT INTO bill_payments (bill_id,amount,paid_date,mode) VALUES (?,?,?,?)",
              (bill_id, amount, today, mode))
    conn.commit()
    conn.close()


def delete_bill(user_id: str, bill_id: int):
    conn = get_user_db(user_id)
    c = conn.cursor()
    c.execute("DELETE FROM bills WHERE id=?", (bill_id,))
    c.execute("DELETE FROM bill_payments WHERE bill_id=?", (bill_id,))
    conn.commit()
    conn.close()


def get_upcoming_bills(user_id: str, days: int = 7) -> list:
    conn = get_user_db(user_id)
    today = datetime.date.today().day
    rows  = conn.cursor().execute(
        "SELECT * FROM bills WHERE status != 'paid'").fetchall()
    conn.close()
    upcoming = []
    for row in rows:
        r = dict(row)
        diff = (r.get("due_day") or 0) - today
        if -2 <= diff <= days:
            r["days_until"] = diff
            upcoming.append(r)
    return sorted(upcoming, key=lambda x: x.get("days_until", 99))


# ── EXPIRY PER USER ───────────────────────────────────────────

def add_expiry(user_id, doc_name, expiry_date, doc_type="", notes=""):
    conn = get_user_db(user_id)
    conn.cursor().execute(
        "INSERT INTO expiry (doc_name,doc_type,expiry_date,notes,added_at) VALUES (?,?,?,?,?)",
        (doc_name, doc_type, expiry_date, notes, datetime.datetime.now().isoformat()))
    conn.commit()
    conn.close()


def get_expiry(user_id: str) -> list:
    conn = get_user_db(user_id)
    rows = conn.cursor().execute("SELECT * FROM expiry ORDER BY expiry_date").fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_expiring_soon(user_id: str, days: int = 30) -> list:
    conn = get_user_db(user_id)
    today    = datetime.date.today()
    deadline = (today + datetime.timedelta(days=days)).isoformat()
    rows = conn.cursor().execute(
        "SELECT * FROM expiry WHERE expiry_date <= ? AND expiry_date >= ? ORDER BY expiry_date",
        (deadline, today.isoformat())).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def delete_expiry(user_id: str, expiry_id: int):
    conn = get_user_db(user_id)
    conn.cursor().execute("DELETE FROM expiry WHERE id=?", (expiry_id,))
    conn.commit()
    conn.close()


# ── CREDENTIALS PER USER ──────────────────────────────────────

def _enc(text):
    if not text:
        return ""
    key = "memora2025"
    key_bytes = (key * (len(text) // len(key) + 1)).encode()
    encrypted = bytes([ord(c) ^ key_bytes[i] for i, c in enumerate(str(text))])
    return base64.b64encode(encrypted).decode()


def _dec(text):
    if not text:
        return ""
    try:
        key = "memora2025"
        encrypted = base64.b64decode(text.encode())
        key_bytes  = (key * (len(encrypted) // len(key) + 1)).encode()
        return "".join([chr(b ^ key_bytes[i]) for i, b in enumerate(encrypted)])
    except Exception:
        return text


def save_credential(user_id, label, username, password,
                    category="general", url="", notes=""):
    conn = get_user_db(user_id)
    conn.cursor().execute("""INSERT INTO credentials
        (label,category,username,password,url,notes,added_at)
        VALUES (?,?,?,?,?,?,?)""",
        (label, category, username, _enc(password), url, notes,
         datetime.datetime.now().isoformat()))
    conn.commit()
    conn.close()


def get_credentials(user_id: str) -> list:
    conn = get_user_db(user_id)
    rows = conn.cursor().execute(
        "SELECT * FROM credentials ORDER BY category,label").fetchall()
    conn.close()
    result = []
    for row in rows:
        d = dict(row)
        d["password"] = _dec(d["password"])
        result.append(d)
    return result


def delete_credential(user_id: str, cred_id: int):
    conn = get_user_db(user_id)
    conn.cursor().execute("DELETE FROM credentials WHERE id=?", (cred_id,))
    conn.commit()
    conn.close()


# Init on import
init_users_db()
