"""
memora_db.py  v4 FINAL
Location: F:\\AI_PROJECTS\\MemorA\\memora_db.py
All fixes built in. No patching needed.
"""

import os
import sqlite3
import datetime
import base64

DB_PATH = r"F:\AI_DATA\MemorA\memora.db"


def get_conn():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = get_conn()
    c = conn.cursor()
    c.execute("""CREATE TABLE IF NOT EXISTS files (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        path TEXT UNIQUE NOT NULL, filename TEXT NOT NULL,
        ext TEXT, type TEXT, categories TEXT,
        size INTEGER, size_hr TEXT, modified TEXT,
        drive TEXT, folder TEXT, content TEXT,
        file_hash TEXT, indexed_at TEXT,
        open_count INTEGER DEFAULT 0, last_opened TEXT, tags TEXT DEFAULT '')""")
    c.execute("""CREATE TABLE IF NOT EXISTS tags (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        file_path TEXT NOT NULL, tag TEXT NOT NULL, added_at TEXT,
        UNIQUE(file_path, tag))""")
    c.execute("""CREATE TABLE IF NOT EXISTS bills (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL, category TEXT, amount REAL, due_day INTEGER,
        frequency TEXT DEFAULT 'monthly', auto_debit INTEGER DEFAULT 0,
        last_paid TEXT, last_amount REAL, status TEXT DEFAULT 'pending',
        account TEXT, notes TEXT, added_at TEXT, updated_at TEXT)""")
    c.execute("""CREATE TABLE IF NOT EXISTS bill_payments (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        bill_id INTEGER, amount REAL, paid_date TEXT,
        mode TEXT, reference TEXT, notes TEXT)""")
    c.execute("""CREATE TABLE IF NOT EXISTS credentials (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        label TEXT NOT NULL, category TEXT, username TEXT,
        password TEXT, url TEXT, notes TEXT, added_at TEXT, updated_at TEXT)""")
    c.execute("""CREATE TABLE IF NOT EXISTS expiry (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        doc_name TEXT NOT NULL, doc_type TEXT, file_path TEXT,
        expiry_date TEXT NOT NULL, notes TEXT, added_at TEXT)""")
    c.execute("""CREATE TABLE IF NOT EXISTS search_history (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        query TEXT NOT NULL, results INTEGER, searched_at TEXT)""")
    for idx in [
        "CREATE INDEX IF NOT EXISTS idx_filename  ON files(filename)",
        "CREATE INDEX IF NOT EXISTS idx_drive     ON files(drive)",
        "CREATE INDEX IF NOT EXISTS idx_type      ON files(type)",
        "CREATE INDEX IF NOT EXISTS idx_ext       ON files(ext)",
        "CREATE INDEX IF NOT EXISTS idx_modified  ON files(modified)",
        "CREATE INDEX IF NOT EXISTS idx_opencount ON files(open_count DESC)",
        "CREATE INDEX IF NOT EXISTS idx_folder    ON files(folder)",
    ]:
        c.execute(idx)
    conn.commit()
    conn.close()
    return DB_PATH


# ── SMART KEYWORDS ────────────────────────────────────────────
SMART_KEYWORDS = {
    "pan":         ["pan", "pancard", "pan card", "nsdl", "income tax", "permanent account"],
    "aadhaar":     ["aadhaar", "aadhar", "adhar", "uid", "uidai"],
    "passport":    ["passport", "ecr", "travel document", "visa"],
    "insurance":   ["insurance", "policy", "premium", "mediclaim", "lic", "claim"],
    "car":         ["car", "vehicle", "rc book", "rc", "puc", "pollution", "rto", "challan"],
    "bank":        ["bank", "account", "ifsc", "statement", "passbook", "cheque"],
    "itr":         ["itr", "tax return", "income tax return", "acknowledgement", "form 16", "26as", "ais"],
    "gst":         ["gst", "gstin", "gstr", "e-invoice", "eway", "tax invoice"],
    "property":    ["property", "flat", "house", "land", "deed", "registry", "sale deed"],
    "health":      ["health", "medical", "hospital", "prescription", "lab", "blood", "report"],
    "salary":      ["salary", "payslip", "ctc", "offer letter", "appointment", "form 16"],
    "loan":        ["loan", "emi", "home loan", "car loan", "personal loan", "noc"],
    "photo":       ["jpg", "jpeg", "png", "image", "photo", "picture"],
    "video":       ["mp4", "mov", "avi", "video", "clip"],
    "certificate": ["certificate", "degree", "diploma", "marksheet", "transcript"],
    "invoice":     ["invoice", "bill", "receipt", "payment", "tax invoice"],
    "voter":       ["voter", "election card", "epic", "voter id"],
    "dl":          ["driving licence", "dl", "driving license", "learner", "rto"],
    "pf":          ["pf", "epf", "uan", "provident fund", "esic"],
    "mutual fund": ["mutual fund", "sip", "nav", "folio", "cas", "amfi"],
    "demat":       ["demat", "dp", "cdsl", "nsdl", "holdings", "portfolio"],
    "rent":        ["rent", "rental", "lease", "tenancy", "landlord"],
    "school":      ["school", "fee", "admit card", "report card", "marksheet", "cbse"],
    "electricity": ["electricity", "electric", "bescom", "msedcl", "power bill"],
    "water":       ["water", "water bill", "bwssb", "municipal water"],
    "emi":         ["emi", "equated monthly", "loan emi", "home emi"],
}

# ── PROFILES ──────────────────────────────────────────────────
PROFILES = {
    "personal": [
        "aadhaar", "aadhar", "pan", "pancard", "passport", "voter",
        "driving licence", "dl", "birth certificate", "marriage certificate",
        "insurance", "mediclaim", "health card", "bank", "account", "statement",
        "property", "deed", "sale deed", "vehicle", "rc", "puc",
        "itr", "tax return", "form 16", "salary", "payslip",
        "photo", "image", "family", "school",
    ],
    "government": [
        "aadhaar", "aadhar", "uid", "pan", "tan", "gst", "gstin", "gstr",
        "passport", "visa", "voter id", "election card", "driving licence",
        "rc book", "registration certificate", "birth certificate",
        "death certificate", "marriage certificate", "caste certificate",
        "income certificate", "domicile", "ration card",
        "ayushman", "cghs", "esi", "esic", "pf", "epf", "uan", "nps",
        "property tax", "house tax", "municipal", "patta",
        "trade licence", "shop establishment", "udyam", "msme",
        "form 16", "form 26as", "ais", "itr", "challan 280",
        "mca", "roc", "din", "dsc", "digital signature",
        "digilocker", "umang",
    ],
    "finance": [
        "itr", "tax return", "form 16", "form 26as", "ais", "tds",
        "advance tax", "challan", "gst", "gstr",
        "bank statement", "passbook", "cancelled cheque",
        "fixed deposit", "fd", "rd", "ppf", "epf", "nps",
        "mutual fund", "sip", "nav", "folio", "cas",
        "demat", "cdsl", "nsdl", "holdings",
        "salary slip", "payslip", "form 16b", "ctc",
        "rent receipt", "hra", "home loan", "emi",
        "insurance premium", "life insurance", "term plan",
        "80c", "80d", "80e", "capital gain", "ltcg", "stcg",
        "dividend", "interest certificate", "invoice", "receipt",
        "audit", "balance sheet", "profit loss",
    ],
    "ca": [
        "itr", "itr1", "itr2", "itr3", "itr4", "form 16", "form 26as",
        "ais", "tds", "tcs", "gst", "gstr1", "gstr3b", "gstr9",
        "balance sheet", "profit loss", "trial balance", "ledger",
        "audit report", "tax audit", "3cd", "3cb",
        "income tax notice", "scrutiny", "advance tax",
        "80c", "80d", "capital gain", "ltcg", "stcg",
        "depreciation", "partnership deed", "moa", "aoa", "roc",
        "invoice", "e-invoice", "e-way bill",
    ],
    "trader": [
        "invoice", "tax invoice", "proforma invoice",
        "purchase order", "po", "delivery challan", "e-way bill",
        "gst", "gstin", "gstr1", "gstr3b", "input credit",
        "stock", "inventory", "vendor", "supplier",
        "payment terms", "credit note", "debit note",
        "ledger", "account statement", "reconciliation",
        "import", "export", "shipping", "customs", "iec",
        "trade licence", "shop establishment", "fssai",
    ],
    "doctor": [
        "prescription", "rx", "medicine", "drug", "tablet",
        "lab report", "blood test", "urine test",
        "x-ray", "xray", "mri", "ct scan", "ultrasound",
        "ecg", "echo", "discharge summary", "hospital bill",
        "doctor", "opd", "medical certificate",
        "health insurance", "mediclaim", "cashless",
        "registration certificate", "mbbs", "md", "nmc",
    ],
    "engineer": [
        "drawing", "autocad", "dwg", "blueprint",
        "structural", "architectural", "tender", "boq",
        "estimate", "specification", "site report",
        "completion certificate", "occupancy certificate",
        "iso", "quality", "testing report",
        "purchase order", "work order", "subcontractor",
    ],
    "legal": [
        "moa", "aoa", "incorporation", "roc", "mca", "cin",
        "board resolution", "agm", "share certificate",
        "contract", "agreement", "mou", "affidavit", "notary",
        "power of attorney", "court order", "judgement",
        "legal notice", "fir", "police", "complaint",
        "property deed", "sale deed", "gift deed", "will",
        "stamp duty", "registration", "rera",
    ],
    "academic": [
        "marksheet", "mark sheet", "scorecard", "degree",
        "diploma", "provisional certificate", "convocation", "transcript",
        "admission letter", "scholarship", "fellowship",
        "research paper", "thesis", "dissertation",
        "publication", "journal", "conference", "patent",
        "grade", "gpa", "sgpa", "cgpa",
        "school leaving", "transfer certificate", "tc",
        "migration certificate", "ugc", "aicte", "naac",
    ],
}

BILL_CATEGORIES = [
    "Utilities", "Loan / EMI", "Insurance", "Education",
    "Household Staff", "Rent", "Subscriptions", "Tax / Filing",
    "Vehicle", "Medical", "Travel", "Entertainment", "Other"
]
BILL_FREQUENCIES = ["monthly", "quarterly", "half-yearly", "yearly", "weekly", "one-time"]


# ── FILE OPERATIONS ───────────────────────────────────────────

def upsert_file(record: dict):
    conn = get_conn()
    c = conn.cursor()
    c.execute("""INSERT INTO files
        (path,filename,ext,type,categories,size,size_hr,
         modified,drive,folder,content,file_hash,indexed_at)
        VALUES (:path,:filename,:ext,:type,:categories,:size,:size_hr,
         :modified,:drive,:folder,:content,:hash,:indexed_at)
        ON CONFLICT(path) DO UPDATE SET
        filename=excluded.filename, ext=excluded.ext,
        type=excluded.type, categories=excluded.categories,
        size=excluded.size, size_hr=excluded.size_hr,
        modified=excluded.modified, content=excluded.content,
        file_hash=excluded.file_hash, indexed_at=excluded.indexed_at""", record)
    conn.commit()
    conn.close()


def get_total_count():
    conn = get_conn()
    n = conn.cursor().execute("SELECT COUNT(*) FROM files").fetchone()[0]
    conn.close()
    return n


def get_stats():
    conn = get_conn()
    c = conn.cursor()
    by_type  = dict(c.execute("SELECT type, COUNT(*) FROM files GROUP BY type").fetchall())
    by_drive = dict(c.execute("SELECT drive, COUNT(*) FROM files GROUP BY drive").fetchall())
    total    = c.execute("SELECT COUNT(*) FROM files").fetchone()[0]
    conn.close()
    return {"total": total, "by_type": by_type, "by_drive": by_drive}


def increment_open_count(path: str):
    conn = get_conn()
    conn.cursor().execute(
        "UPDATE files SET open_count=open_count+1, last_opened=? WHERE path=?",
        (datetime.datetime.now().isoformat(), path))
    conn.commit()
    conn.close()


def get_files_in_folder(folder_path: str):
    conn = get_conn()
    c = conn.cursor()
    rows = c.execute(
        "SELECT * FROM files WHERE folder=? ORDER BY filename", (folder_path,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_recent_files(limit=20):
    conn = get_conn()
    c = conn.cursor()
    rows = c.execute(
        "SELECT * FROM files WHERE last_opened IS NOT NULL ORDER BY last_opened DESC LIMIT ?",
        (limit,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_frequent_files(limit=20):
    conn = get_conn()
    c = conn.cursor()
    rows = c.execute(
        "SELECT * FROM files WHERE open_count > 0 ORDER BY open_count DESC LIMIT ?",
        (limit,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


# ── SEARCH — multi-word AND logic ─────────────────────────────

def search_files(query: str, profile: str = None, limit: int = 100,
                 file_type: str = None, drive: str = None,
                 date_from: str = None, date_to: str = None):
    conn = get_conn()
    c = conn.cursor()
    q = query.lower().strip()

    # Split into words — each word must match somewhere
    words = [w for w in q.split() if len(w) >= 2]
    if not words:
        words = [q] if q else [""]

    # Expand first word with smart keywords
    first_word_terms = [words[0]]
    if words[0] in SMART_KEYWORDS:
        first_word_terms.extend(SMART_KEYWORDS[words[0]])

    # Build AND conditions — every word must appear
    all_conditions = []
    all_params = []

    for i, word in enumerate(words):
        if i == 0:
            # First word: use expanded terms with OR
            term_parts = []
            for term in first_word_terms[:8]:
                like = f"%{term}%"
                term_parts.append(
                    "(LOWER(filename) LIKE ? OR LOWER(path) LIKE ? OR LOWER(content) LIKE ? OR LOWER(categories) LIKE ?)"
                )
                all_params.extend([like, like, like, like])
            all_conditions.append("(" + " OR ".join(term_parts) + ")")
        else:
            # Other words: search in filename, path, content
            like = f"%{word}%"
            all_conditions.append(
                "(LOWER(filename) LIKE ? OR LOWER(path) LIKE ? OR LOWER(content) LIKE ?)"
            )
            all_params.extend([like, like, like])

    where = " AND ".join(all_conditions) if all_conditions else "1=1"

    # Optional filters
    if file_type:
        where += " AND type = ?"
        all_params.append(file_type)
    if drive:
        where += " AND drive = ?"
        all_params.append(drive)
    if date_from:
        where += " AND modified >= ?"
        all_params.append(date_from)
    if date_to:
        where += " AND modified <= ?"
        all_params.append(date_to)

    main_like = f"%{q}%"
    first_like = f"%{words[0]}%"
    sql = f"""
        SELECT *,
          (CASE WHEN LOWER(filename) LIKE ? THEN 100 ELSE 0 END +
           CASE WHEN LOWER(filename) LIKE ? THEN 60  ELSE 0 END +
           CASE WHEN LOWER(path)     LIKE ? THEN 30  ELSE 0 END +
           CASE WHEN LOWER(content)  LIKE ? THEN 20  ELSE 0 END +
           open_count * 3) as score
        FROM files WHERE {where}
        ORDER BY score DESC, open_count DESC, modified DESC LIMIT ?
    """
    rows = c.execute(
        sql, [main_like, first_like, main_like, main_like] + all_params + [limit]
    ).fetchall()
    conn.close()
    log_search(query, len(rows))
    return [dict(r) for r in rows]


def search_profile_only(profile: str, query: str = "", limit: int = 100):
    if profile not in PROFILES:
        return search_files(query, limit=limit)

    conn = get_conn()
    c = conn.cursor()
    cats = PROFILES[profile][:15]

    cat_parts, cat_params = [], []
    for kw in cats:
        like = f"%{kw}%"
        cat_parts.append(
            "(LOWER(filename) LIKE ? OR LOWER(path) LIKE ? OR LOWER(content) LIKE ? OR LOWER(categories) LIKE ?)"
        )
        cat_params.extend([like, like, like, like])

    where = " OR ".join(cat_parts)

    if query:
        words = [w for w in query.lower().split() if len(w) >= 2]
        word_parts, word_params = [], []
        for word in words:
            wl = f"%{word}%"
            word_parts.append("(LOWER(filename) LIKE ? OR LOWER(path) LIKE ? OR LOWER(content) LIKE ?)")
            word_params.extend([wl, wl, wl])
        word_where = " AND ".join(word_parts) if word_parts else "1=1"
        sql = f"SELECT * FROM files WHERE ({where}) AND ({word_where}) ORDER BY open_count DESC, modified DESC LIMIT ?"
        rows = c.execute(sql, cat_params + word_params + [limit]).fetchall()
    else:
        sql = f"SELECT * FROM files WHERE ({where}) ORDER BY open_count DESC, modified DESC LIMIT ?"
        rows = c.execute(sql, cat_params + [limit]).fetchall()

    conn.close()
    return [dict(r) for r in rows]


# ── TAGS ──────────────────────────────────────────────────────

def add_tag(file_path: str, tag: str):
    conn = get_conn()
    c = conn.cursor()
    try:
        c.execute("INSERT OR IGNORE INTO tags (file_path,tag,added_at) VALUES (?,?,?)",
                  (file_path, tag.lower().strip(), datetime.datetime.now().isoformat()))
        existing = c.execute("SELECT tags FROM files WHERE path=?", (file_path,)).fetchone()
        if existing:
            tags = [t for t in (existing[0] or "").split(",") if t]
            if tag not in tags:
                tags.append(tag)
            c.execute("UPDATE files SET tags=? WHERE path=?", (",".join(tags), file_path))
        conn.commit()
        return True
    except Exception:
        return False
    finally:
        conn.close()


# ── BILLS ─────────────────────────────────────────────────────

def add_bill(name, category, amount, due_day, frequency="monthly",
             auto_debit=0, account="", notes=""):
    conn = get_conn()
    c = conn.cursor()
    now = datetime.datetime.now().isoformat()
    c.execute("""INSERT INTO bills
        (name,category,amount,due_day,frequency,auto_debit,account,notes,status,added_at,updated_at)
        VALUES (?,?,?,?,?,?,?,?,'pending',?,?)""",
        (name, category, amount, due_day, frequency, auto_debit, account, notes, now, now))
    conn.commit()
    conn.close()


def get_bills(category=None):
    conn = get_conn()
    c = conn.cursor()
    if category:
        rows = c.execute("SELECT * FROM bills WHERE category=? ORDER BY due_day", (category,)).fetchall()
    else:
        rows = c.execute("SELECT * FROM bills ORDER BY due_day").fetchall()
    conn.close()
    return [dict(r) for r in rows]


def mark_bill_paid(bill_id: int, amount: float, mode: str = "UPI", reference: str = ""):
    conn = get_conn()
    c = conn.cursor()
    today = datetime.date.today().isoformat()
    c.execute("UPDATE bills SET status='paid', last_paid=?, last_amount=?, updated_at=? WHERE id=?",
              (today, amount, datetime.datetime.now().isoformat(), bill_id))
    c.execute("INSERT INTO bill_payments (bill_id,amount,paid_date,mode,reference) VALUES (?,?,?,?,?)",
              (bill_id, amount, today, mode, reference))
    conn.commit()
    conn.close()


def get_upcoming_bills(days=7):
    conn = get_conn()
    c = conn.cursor()
    today = datetime.date.today().day
    upcoming = []
    rows = c.execute("SELECT * FROM bills WHERE status != 'paid'").fetchall()
    for row in rows:
        r = dict(row)
        due = r.get("due_day", 0) or 0
        diff = due - today
        if -2 <= diff <= days:
            r["days_until"] = diff
            upcoming.append(r)
    upcoming.sort(key=lambda x: x.get("days_until", 99))
    conn.close()
    return upcoming


def get_monthly_summary():
    conn = get_conn()
    c = conn.cursor()
    today = datetime.date.today()
    month_start = today.replace(day=1).isoformat()
    rows = c.execute("""SELECT b.category, SUM(p.amount) as total
        FROM bill_payments p JOIN bills b ON p.bill_id=b.id
        WHERE p.paid_date >= ? GROUP BY b.category ORDER BY total DESC""",
        (month_start,)).fetchall()
    total_paid = c.execute(
        "SELECT COALESCE(SUM(amount),0) FROM bill_payments WHERE paid_date >= ?",
        (month_start,)).fetchone()[0]
    total_due = c.execute("SELECT COALESCE(SUM(amount),0) FROM bills").fetchone()[0]
    conn.close()
    return {"by_category": [dict(r) for r in rows], "total_paid": total_paid, "total_due": total_due}


def delete_bill(bill_id: int):
    conn = get_conn()
    c = conn.cursor()
    c.execute("DELETE FROM bills WHERE id=?", (bill_id,))
    c.execute("DELETE FROM bill_payments WHERE bill_id=?", (bill_id,))
    conn.commit()
    conn.close()


# ── EXPIRY ────────────────────────────────────────────────────

def add_expiry(doc_name, expiry_date, doc_type="", file_path="", notes=""):
    conn = get_conn()
    c = conn.cursor()
    c.execute("INSERT INTO expiry (doc_name,doc_type,file_path,expiry_date,notes,added_at) VALUES (?,?,?,?,?,?)",
              (doc_name, doc_type, file_path, expiry_date, notes, datetime.datetime.now().isoformat()))
    conn.commit()
    conn.close()


def get_expiring_soon(days=30):
    conn = get_conn()
    c = conn.cursor()
    today    = datetime.date.today()
    deadline = (today + datetime.timedelta(days=days)).isoformat()
    rows = c.execute(
        "SELECT * FROM expiry WHERE expiry_date <= ? AND expiry_date >= ? ORDER BY expiry_date ASC",
        (deadline, today.isoformat())).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_all_expiry():
    conn = get_conn()
    rows = conn.cursor().execute("SELECT * FROM expiry ORDER BY expiry_date ASC").fetchall()
    conn.close()
    return [dict(r) for r in rows]


def delete_expiry(expiry_id: int):
    conn = get_conn()
    conn.cursor().execute("DELETE FROM expiry WHERE id=?", (expiry_id,))
    conn.commit()
    conn.close()


# ── CREDENTIALS ───────────────────────────────────────────────

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
        key_bytes  = (key * (len(encrypted) // len(key) + 1)).encode()
        return "".join([chr(b ^ key_bytes[i]) for i, b in enumerate(encrypted)])
    except Exception:
        return text


def save_credential(label, username, password, category="general", url="", notes=""):
    conn = get_conn()
    c = conn.cursor()
    now = datetime.datetime.now().isoformat()
    c.execute("""INSERT INTO credentials
        (label,category,username,password,url,notes,added_at,updated_at)
        VALUES (?,?,?,?,?,?,?,?)""",
        (label, category, username, _enc(password), url, notes, now, now))
    conn.commit()
    conn.close()


def get_credentials(category=None):
    conn = get_conn()
    c = conn.cursor()
    if category:
        rows = c.execute("SELECT * FROM credentials WHERE category=? ORDER BY label", (category,)).fetchall()
    else:
        rows = c.execute("SELECT * FROM credentials ORDER BY category,label").fetchall()
    conn.close()
    result = []
    for row in rows:
        d = dict(row)
        d["password"] = _dec(d["password"])
        result.append(d)
    return result


def delete_credential(cred_id: int):
    conn = get_conn()
    conn.cursor().execute("DELETE FROM credentials WHERE id=?", (cred_id,))
    conn.commit()
    conn.close()


# ── SEARCH HISTORY ────────────────────────────────────────────

def log_search(query, results):
    conn = get_conn()
    conn.cursor().execute(
        "INSERT INTO search_history (query,results,searched_at) VALUES (?,?,?)",
        (query, results, datetime.datetime.now().isoformat()))
    conn.commit()
    conn.close()


def get_top_searches(limit=10):
    conn = get_conn()
    rows = conn.cursor().execute(
        "SELECT query, COUNT(*) as count FROM search_history GROUP BY LOWER(query) ORDER BY count DESC LIMIT ?",
        (limit,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


if __name__ == "__main__":
    path = init_db()
    print("MemorA DB: " + path)
    print("Files: " + str(get_total_count()))
