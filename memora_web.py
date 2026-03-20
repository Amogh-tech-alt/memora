"""
memora_web.py  v4  self-contained
Location: F:\\AI_PROJECTS\\MemorA\\memora_web.py

No imports from other files. Everything built in.
Auto-migrates from JSON on first run.
Runs at http://localhost:7000
"""

import os, sys, json, sqlite3, base64, datetime

DB_PATH   = r"F:\AI_DATA\MemorA\memora.db"
JSON_PATH = r"F:\AI_DATA\MemorA\scan_index.json"

try:
    from fastapi import FastAPI, Request
    from fastapi.responses import HTMLResponse, JSONResponse
    import uvicorn
except ImportError:
    os.system("pip install fastapi uvicorn --quiet")
    from fastapi import FastAPI, Request
    from fastapi.responses import HTMLResponse, JSONResponse
    import uvicorn

app = FastAPI()


def get_conn():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_conn()
    c = conn.cursor()
    c.execute("""CREATE TABLE IF NOT EXISTS files (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        path TEXT UNIQUE NOT NULL, filename TEXT NOT NULL,
        ext TEXT, type TEXT, categories TEXT,
        size INTEGER, size_hr TEXT, modified TEXT,
        drive TEXT, folder TEXT, content TEXT,
        file_hash TEXT, indexed_at TEXT,
        open_count INTEGER DEFAULT 0,
        last_opened TEXT, tags TEXT DEFAULT '')""")
    c.execute("""CREATE TABLE IF NOT EXISTS bills (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL, category TEXT, amount REAL,
        due_day INTEGER, frequency TEXT DEFAULT 'monthly',
        auto_debit INTEGER DEFAULT 0, last_paid TEXT,
        last_amount REAL, status TEXT DEFAULT 'pending',
        account TEXT, notes TEXT, added_at TEXT, updated_at TEXT)""")
    c.execute("""CREATE TABLE IF NOT EXISTS bill_payments (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        bill_id INTEGER, amount REAL, paid_date TEXT, mode TEXT, reference TEXT)""")
    c.execute("""CREATE TABLE IF NOT EXISTS credentials (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        label TEXT, category TEXT, username TEXT, password TEXT,
        url TEXT, notes TEXT, added_at TEXT, updated_at TEXT)""")
    c.execute("""CREATE TABLE IF NOT EXISTS expiry (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        doc_name TEXT, doc_type TEXT, file_path TEXT,
        expiry_date TEXT, notes TEXT, added_at TEXT)""")
    for idx in [
        "CREATE INDEX IF NOT EXISTS idx_fn  ON files(filename)",
        "CREATE INDEX IF NOT EXISTS idx_pt  ON files(path)",
        "CREATE INDEX IF NOT EXISTS idx_tp  ON files(type)",
        "CREATE INDEX IF NOT EXISTS idx_oc  ON files(open_count DESC)",
        "CREATE INDEX IF NOT EXISTS idx_fld ON files(folder)",
    ]:
        c.execute(idx)
    conn.commit()
    count = c.execute("SELECT COUNT(*) FROM files").fetchone()[0]
    conn.close()
    if count == 0:
        _migrate()
    return count


def _migrate():
    if not os.path.exists(JSON_PATH):
        print("  No JSON index found — run scanner first")
        return
    print("  Migrating JSON index to SQLite database...")
    with open(JSON_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)
    files = data.get("files", [])
    conn = get_conn()
    c = conn.cursor()
    done = 0
    for rec in files:
        try:
            cats = rec.get("categories", [])
            if isinstance(cats, list):
                cats = ",".join(cats)
            c.execute("""INSERT OR IGNORE INTO files
                (path,filename,ext,type,categories,size,size_hr,
                 modified,drive,folder,content,file_hash,indexed_at)
                VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)""", (
                rec.get("path",""), rec.get("filename",""),
                rec.get("ext",""), rec.get("type","other"), cats,
                rec.get("size",0), rec.get("size_hr",""),
                rec.get("modified",""), rec.get("drive",""),
                rec.get("folder",""), rec.get("content",""),
                rec.get("hash",""), rec.get("indexed_at","")))
            done += 1
            if done % 2000 == 0:
                conn.commit()
                print(f"    {done} migrated...")
        except Exception:
            pass
    conn.commit()
    conn.close()
    print(f"  Migration complete: {done} files")


SMART = {
    "pan":         ["pan","pancard","nsdl"],
    "aadhaar":     ["aadhaar","aadhar","adhar","uid","uidai"],
    "insurance":   ["insurance","policy","premium","mediclaim","lic"],
    "bank":        ["bank","statement","passbook","ifsc","cheque"],
    "itr":         ["itr","tax return","form16","form 16","26as","tds"],
    "gst":         ["gst","gstin","gstr","eway"],
    "property":    ["property","deed","flat","house","land","registry","sale deed"],
    "health":      ["health","medical","hospital","prescription","lab","report"],
    "salary":      ["salary","payslip","ctc","offer letter","appointment"],
    "loan":        ["loan","emi","home loan","noc","outstanding"],
    "photo":       ["jpg","jpeg","png","photo","picture"],
    "video":       ["mp4","mov","avi","video"],
    "certificate": ["certificate","degree","diploma","marksheet","transcript"],
    "invoice":     ["invoice","bill","receipt","payment"],
    "voter":       ["voter","election","epic"],
    "dl":          ["driving licence","dl","driving license"],
    "pf":          ["pf","epf","uan","provident fund"],
    "mutual fund": ["mutual fund","sip","nav","folio","cas","amfi"],
    "demat":       ["demat","cdsl","nsdl","holdings","shares"],
    "rent":        ["rent","rental","lease","tenancy"],
    "school":      ["school","fee","report card","cbse","icse"],
    "car":         ["car","vehicle","rc","puc","pollution","rto"],
    "passport":    ["passport","visa","ecr"],
    "document":    ["pdf","docx","doc","word","document"],
    "image":       ["jpg","jpeg","png","gif","bmp","image","photo"],
    "spreadsheet": ["xls","xlsx","csv","excel","spreadsheet"],
    "software":    ["exe","msi","setup","install","software"],
}

PROFILES = {
    "personal":   ["pan","aadhaar","passport","insurance","bank","property","vehicle","health","family"],
    "government": ["aadhaar","pan","tan","gst","passport","voter","driving","rc","itr","pf","uan","epf"],
    "finance":    ["itr","tax","form16","tds","gst","bank","salary","loan","emi","mutual fund","sip","demat","invoice"],
    "ca":         ["itr","form16","tds","gst","audit","balance sheet","ledger","80c","capital gain"],
    "trader":     ["invoice","gst","purchase order","stock","vendor","delivery","eway"],
    "doctor":     ["prescription","lab","hospital","medical","patient","registration","mbbs"],
    "engineer":   ["drawing","tender","specification","site","completion","bom"],
    "legal":      ["moa","aoa","roc","affidavit","contract","deed","court","power of attorney"],
    "academic":   ["marksheet","degree","thesis","research","publication","scholarship"],
}


def do_search(query, profile=None, limit=100):
    conn = get_conn()
    c = conn.cursor()
    q = query.lower().strip()
    terms = list({q} | set(SMART.get(q, [])))
    if profile and profile in PROFILES:
        terms += PROFILES[profile][:6]
    terms = list(set(t for t in terms if t))[:20]

    conds, params = [], []
    for t in terms:
        like = f"%{t}%"
        conds.append(
            "(LOWER(filename) LIKE ? OR LOWER(path) LIKE ? OR LOWER(content) LIKE ? OR LOWER(categories) LIKE ?)"
        )
        params.extend([like, like, like, like])

    where = " OR ".join(conds)
    ml = f"%{q}%"
    sql = f"""SELECT *,
        (CASE WHEN LOWER(filename) LIKE ? THEN 100 ELSE 0 END +
         CASE WHEN LOWER(path)     LIKE ? THEN 50  ELSE 0 END +
         CASE WHEN LOWER(content)  LIKE ? THEN 30  ELSE 0 END +
         open_count * 3) as score
      FROM files WHERE {where}
      ORDER BY score DESC, open_count DESC, modified DESC LIMIT ?"""
    rows = c.execute(sql, [ml, ml, ml] + params + [limit]).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def profile_search(profile, query="", limit=100):
    kws = PROFILES.get(profile, [])
    if not kws:
        return do_search(query or profile, limit=limit)
    conn = get_conn()
    c = conn.cursor()
    conds, params = [], []
    for kw in kws[:10]:
        like = f"%{kw}%"
        conds.append("(LOWER(filename) LIKE ? OR LOWER(path) LIKE ? OR LOWER(content) LIKE ?)")
        params.extend([like, like, like])
    where = " OR ".join(conds)
    if query:
        ql = f"%{query.lower()}%"
        sql = f"SELECT * FROM files WHERE ({where}) AND (LOWER(filename) LIKE ? OR LOWER(path) LIKE ?) ORDER BY open_count DESC, modified DESC LIMIT ?"
        rows = c.execute(sql, params + [ql, ql, limit]).fetchall()
    else:
        sql = f"SELECT * FROM files WHERE ({where}) ORDER BY open_count DESC, modified DESC LIMIT ?"
        rows = c.execute(sql, params + [limit]).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_stats():
    conn = get_conn()
    c = conn.cursor()
    total = c.execute("SELECT COUNT(*) FROM files").fetchone()[0]
    by_type = dict(c.execute("SELECT type, COUNT(*) FROM files GROUP BY type").fetchall())
    by_drive = dict(c.execute("SELECT drive, COUNT(*) FROM files GROUP BY drive").fetchall())
    conn.close()
    return {"total": total, "by_type": by_type, "by_drive": by_drive}


def _enc(t, k="memora2025"):
    if not t: return ""
    kb = (k * (len(t)//len(k)+1)).encode()
    return base64.b64encode(bytes([ord(ch) ^ kb[i] for i, ch in enumerate(t)])).decode()

def _dec(t, k="memora2025"):
    if not t: return ""
    try:
        enc = base64.b64decode(t.encode())
        kb = (k * (len(enc)//len(k)+1)).encode()
        return "".join([chr(b ^ kb[i]) for i, b in enumerate(enc)])
    except:
        return t


HTML = r"""<!DOCTYPE html>
<html lang="en"><head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>MemorA - Your Personal AI Memory</title>
<style>
:root{--bg:#0f0f14;--surf:#1a1a24;--surf2:#22223a;--bdr:#2e2e4a;
--purple:#7c6fdf;--pl:#a89ef5;--teal:#1db87a;--tl:#4dd9a0;
--amber:#f0a020;--red:#e05555;--green:#22c55e;--text:#e8e6f0;--muted:#8885a0}
*{box-sizing:border-box;margin:0;padding:0}
body{background:var(--bg);color:var(--text);font-family:'Segoe UI',Arial,sans-serif}
.hdr{background:var(--surf);border-bottom:1px solid var(--bdr);padding:12px 24px;display:flex;align-items:center;gap:14px;position:sticky;top:0;z-index:100}
.logo{width:40px;height:40px;border-radius:10px;background:linear-gradient(135deg,#534AB7,#1D9E75);display:flex;align-items:center;justify-content:center;font-size:20px;font-weight:800;color:white;flex-shrink:0}
.ltxt{font-size:20px;font-weight:700}
.lsub{font-size:10px;color:var(--muted)}
.hdr-r{margin-left:auto;display:flex;gap:6px;flex-wrap:wrap}
.tab{padding:7px 14px;border-radius:8px;border:1px solid var(--bdr);background:transparent;color:var(--muted);font-size:12px;cursor:pointer;transition:all .15s}
.tab.on,.tab:hover{background:var(--purple);border-color:var(--purple);color:white}
.sw{padding:16px 24px 0}
.sb{display:flex;gap:8px;background:var(--surf);border:2px solid var(--bdr);border-radius:14px;padding:4px 6px 4px 16px;transition:border-color .2s}
.sb:focus-within{border-color:var(--purple)}
.sb input{flex:1;background:transparent;border:none;outline:none;color:var(--text);font-size:17px;padding:9px 0}
.sb input::placeholder{color:var(--muted)}
.sbtn{padding:9px 20px;background:var(--purple);border:none;border-radius:10px;color:white;font-size:13px;font-weight:600;cursor:pointer}
.sbtn:hover{background:#6a5fcc}
.qw{display:flex;gap:6px;flex-wrap:wrap;padding:12px 24px 0}
.qt{padding:4px 11px;border-radius:16px;font-size:11px;cursor:pointer;border:1px solid var(--bdr);color:var(--muted);background:transparent;transition:all .15s}
.qt:hover{border-color:var(--purple);color:var(--pl)}
.main{display:grid;grid-template-columns:200px 1fr;min-height:calc(100vh - 148px)}
.side{border-right:1px solid var(--bdr);padding:14px 12px}
.st{font-size:10px;font-weight:600;color:var(--muted);text-transform:uppercase;letter-spacing:.6px;margin:12px 0 5px}
.si{padding:6px 10px;border-radius:7px;cursor:pointer;font-size:12px;color:var(--muted);transition:all .15s;margin-bottom:1px;display:flex;align-items:center;gap:6px}
.si:hover,.si.on{background:rgba(124,111,223,.15);color:var(--pl)}
.dot{width:7px;height:7px;border-radius:2px;flex-shrink:0}
.cnt{padding:16px 20px}
.rmeta{font-size:13px;color:var(--muted);margin-bottom:12px}
.fc{background:var(--surf);border:1px solid var(--bdr);border-radius:12px;padding:13px 15px;margin-bottom:8px;transition:border-color .15s}
.fc:hover{border-color:rgba(124,111,223,.4)}
.ft{display:flex;align-items:flex-start;gap:11px}
.fi{width:34px;height:34px;border-radius:7px;display:flex;align-items:center;justify-content:center;font-size:11px;font-weight:700;flex-shrink:0}
.idoc{background:rgba(124,111,223,.2);color:var(--pl)}
.iimg{background:rgba(29,184,122,.2);color:var(--tl)}
.ivid{background:rgba(240,160,32,.2);color:var(--amber)}
.ixls{background:rgba(29,184,122,.12);color:var(--teal)}
.ipdf{background:rgba(224,85,85,.2);color:var(--red)}
.ioth{background:rgba(136,133,160,.12);color:var(--muted)}
.fn{font-size:14px;font-weight:600;cursor:pointer;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.fn:hover{color:var(--pl)}
.fp{font-size:11px;color:var(--muted);margin-top:2px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.fm{display:flex;gap:5px;margin-top:5px;flex-wrap:wrap}
.ftg{padding:2px 7px;border-radius:5px;font-size:10px;font-weight:500}
.tt{background:rgba(124,111,223,.15);color:var(--pl)}
.tc{background:rgba(29,184,122,.15);color:var(--tl)}
.ts{background:rgba(136,133,160,.1);color:var(--muted)}
.fpv{font-size:11px;color:var(--muted);margin-top:5px;line-height:1.5}
.fba{display:flex;gap:5px;margin-top:9px;flex-wrap:wrap}
.fb{padding:5px 11px;border-radius:6px;border:1px solid var(--bdr);background:transparent;color:var(--muted);font-size:11px;cursor:pointer;transition:all .15s}
.fb:hover{border-color:var(--purple);color:var(--pl)}
.fbop{background:var(--purple);border-color:var(--purple);color:white}
.fbop:hover{background:#6a5fcc}
.pgn{display:flex;gap:6px;justify-content:center;margin-top:14px;flex-wrap:wrap}
.pg{padding:5px 12px;border-radius:7px;border:1px solid var(--bdr);background:transparent;color:var(--muted);font-size:12px;cursor:pointer}
.pg.on,.pg:hover{background:var(--purple);border-color:var(--purple);color:white}
.sg{display:grid;grid-template-columns:repeat(4,1fr);gap:8px;margin-bottom:16px}
.sc{background:var(--surf);border:1px solid var(--bdr);border-radius:10px;padding:12px;text-align:center}
.sn{font-size:22px;font-weight:700;color:var(--pl)}
.sl{font-size:10px;color:var(--muted);margin-top:3px}
.fbox{background:var(--surf);border:1px solid var(--bdr);border-radius:12px;padding:16px;margin-bottom:14px}
.fg{margin-bottom:10px}
.fg label{display:block;font-size:11px;color:var(--muted);margin-bottom:3px}
.fg input,.fg select,.fg textarea{width:100%;padding:8px 11px;background:var(--bg);border:1px solid var(--bdr);border-radius:7px;color:var(--text);font-size:13px;outline:none}
.fg input:focus,.fg select:focus{border-color:var(--purple)}
.fg select option{background:var(--surf2)}
.fgrid{display:grid;grid-template-columns:1fr 1fr;gap:10px}
.save{padding:9px 18px;background:var(--teal);border:none;border-radius:8px;color:white;font-size:13px;font-weight:600;cursor:pointer}
.save:hover{background:#18a06a}
.bc{background:var(--surf);border:1px solid var(--bdr);border-radius:10px;padding:12px 14px;margin-bottom:7px;display:flex;align-items:center;gap:12px}
.bi{flex:1;min-width:0}.bn{font-size:13px;font-weight:600}.bm{font-size:11px;color:var(--muted);margin-top:2px}
.br{text-align:right;flex-shrink:0}.ba{font-size:15px;font-weight:700}
.bs{padding:3px 8px;border-radius:12px;font-size:10px;font-weight:600}
.bp{background:rgba(34,197,94,.15);color:var(--green)}.bpd{background:rgba(240,160,32,.15);color:var(--amber)}
.ec{background:var(--surf);border:1px solid rgba(240,160,32,.3);border-radius:10px;padding:12px 14px;margin-bottom:7px;display:flex;justify-content:space-between;align-items:center}
.cc{background:var(--surf);border:1px solid var(--bdr);border-radius:10px;padding:11px 14px;margin-bottom:6px;display:flex;justify-content:space-between;align-items:center}
.pw{font-size:11px;color:var(--muted);cursor:pointer;padding:4px 8px;border:1px solid var(--bdr);border-radius:5px}
.pw:hover{border-color:var(--purple);color:var(--pl)}
.empty{text-align:center;padding:50px;color:var(--muted)}
.empty h3{font-size:15px;margin-bottom:8px;color:var(--text)}
.empty p{font-size:12px;line-height:1.7}
.ov{display:none;position:fixed;top:0;left:0;right:0;bottom:0;background:rgba(0,0,0,.75);z-index:200;align-items:flex-start;justify-content:center;padding-top:60px}
.ov.show{display:flex}
.modal{background:var(--surf);border:1px solid var(--bdr);border-radius:14px;padding:20px;width:680px;max-height:75vh;overflow-y:auto}
.mttl{font-size:15px;font-weight:600;margin-bottom:14px;display:flex;justify-content:space-between;align-items:center}
@media(max-width:700px){.main{grid-template-columns:1fr}.side{display:none}.sg{grid-template-columns:1fr 1fr}}
</style></head><body>

<div class="hdr">
  <div class="logo">M</div>
  <div><div class="ltxt"><span style="color:#a89ef5">Memor</span><span style="color:#4dd9a0">A</span></div>
  <div class="lsub">Your Personal AI Memory</div></div>
  <div class="hdr-r">
    <button class="tab on" onclick="showTab('search',this)">Search</button>
    <button class="tab" onclick="showTab('recent',this)">Recent</button>
    <button class="tab" onclick="showTab('bills',this)">Bills</button>
    <button class="tab" onclick="showTab('expiry',this)">Expiry</button>
    <button class="tab" onclick="showTab('vault',this)">Vault</button>
    <button class="tab" onclick="showTab('stats',this)">Stats</button>
  </div>
</div>

<div id="tab-search">
  <div class="sw">
    <div class="sb">
      <input id="si" type="text" placeholder="Type anything — PAN, aadhaar, insurance, ITR, salary..."
             onkeydown="if(event.key==='Enter')doSearch()">
      <button class="sbtn" onclick="doSearch()">Search</button>
    </div>
  </div>
  <div class="qw">
    <span class="qt" onclick="qs('pan')">PAN</span>
    <span class="qt" onclick="qs('aadhaar')">Aadhaar</span>
    <span class="qt" onclick="qs('insurance')">Insurance</span>
    <span class="qt" onclick="qs('itr')">ITR / Tax</span>
    <span class="qt" onclick="qs('bank')">Bank</span>
    <span class="qt" onclick="qs('salary')">Salary</span>
    <span class="qt" onclick="qs('property')">Property</span>
    <span class="qt" onclick="qs('loan')">Loan / EMI</span>
    <span class="qt" onclick="qs('photo')">Photos</span>
    <span class="qt" onclick="qs('video')">Videos</span>
    <span class="qt" onclick="qs('gst')">GST</span>
    <span class="qt" onclick="qs('passport')">Passport</span>
    <span class="qt" onclick="qs('certificate')">Certificates</span>
    <span class="qt" onclick="qs('voter')">Voter ID</span>
    <span class="qt" onclick="qs('dl')">Driving Licence</span>
    <span class="qt" onclick="qs('mutual fund')">Mutual Fund</span>
    <span class="qt" onclick="qs('pf')">PF / EPF</span>
    <span class="qt" onclick="qs('rent')">Rent</span>
    <span class="qt" onclick="qs('school')">School</span>
    <span class="qt" onclick="qs('car')">Vehicle</span>
    <span class="qt" onclick="qs('document')">All Docs</span>
    <span class="qt" onclick="qs('image')">All Images</span>
  </div>
  <div class="main">
    <div class="side">
      <div class="st">File Types</div>
      <div class="si" onclick="qs('document')"><div class="dot" style="background:var(--purple)"></div>Documents</div>
      <div class="si" onclick="qs('image')"><div class="dot" style="background:var(--teal)"></div>Images</div>
      <div class="si" onclick="qs('video')"><div class="dot" style="background:var(--amber)"></div>Videos</div>
      <div class="si" onclick="qs('spreadsheet')"><div class="dot" style="background:var(--teal)"></div>Spreadsheets</div>
      <div class="si" onclick="qs('software')"><div class="dot" style="background:var(--muted)"></div>Software</div>
      <div class="st">Profiles</div>
      <div class="si" onclick="sp('personal')"><div class="dot" style="background:var(--teal)"></div>Personal</div>
      <div class="si" onclick="sp('government')"><div class="dot" style="background:var(--amber)"></div>Government</div>
      <div class="si" onclick="sp('finance')"><div class="dot" style="background:var(--green)"></div>Finance</div>
      <div class="si" onclick="sp('ca')"><div class="dot" style="background:var(--purple)"></div>CA / Tax</div>
      <div class="si" onclick="sp('trader')"><div class="dot" style="background:var(--amber)"></div>Trader</div>
      <div class="si" onclick="sp('doctor')"><div class="dot" style="background:var(--red)"></div>Doctor</div>
      <div class="si" onclick="sp('engineer')"><div class="dot" style="background:var(--muted)"></div>Engineer</div>
      <div class="si" onclick="sp('legal')"><div class="dot" style="background:var(--purple)"></div>Legal / CS</div>
      <div class="si" onclick="sp('academic')"><div class="dot" style="background:var(--teal)"></div>Academic</div>
      <div class="st">Quick</div>
      <div class="si" onclick="loadRecent()"><div class="dot" style="background:var(--teal)"></div>Recently Opened</div>
      <div class="si" onclick="loadFreq()"><div class="dot" style="background:var(--amber)"></div>Most Used</div>
    </div>
    <div class="cnt">
      <div id="rmeta" class="rmeta" style="display:none"></div>
      <div id="results">
        <div class="empty"><h3>What are you looking for?</h3>
          <p>Search across all your drives D E F G<br>Click a quick tag or type anything.<br>Click a Profile to browse that category.</p>
        </div>
      </div>
      <div id="pgn" class="pgn"></div>
    </div>
  </div>
</div>

<div id="tab-bills" style="display:none"><div style="padding:16px 24px">
  <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:14px">
    <div style="font-size:16px;font-weight:600">Bills and Expenses</div>
    <button class="save" onclick="tbf()">+ Add Bill</button>
  </div>
  <div id="bform" style="display:none"><div class="fbox"><div class="fgrid">
    <div class="fg"><label>Bill Name</label><input id="bN" placeholder="BESCOM Electricity"></div>
    <div class="fg"><label>Category</label><select id="bCt">
      <option>Utilities</option><option>Loan / EMI</option><option>Insurance</option>
      <option>Education</option><option>Household Staff</option><option>Rent</option>
      <option>Subscriptions</option><option>Tax / Filing</option><option>Vehicle</option>
      <option>Medical</option><option>Other</option>
    </select></div>
    <div class="fg"><label>Amount (Rs)</label><input id="bA" type="number" placeholder="1500"></div>
    <div class="fg"><label>Due Day of Month</label><input id="bD" type="number" min="1" max="31" placeholder="5"></div>
    <div class="fg"><label>Frequency</label><select id="bF">
      <option>monthly</option><option>quarterly</option><option>half-yearly</option><option>yearly</option><option>one-time</option>
    </select></div>
    <div class="fg"><label>Auto Debit</label><select id="bAD"><option value="0">No</option><option value="1">Yes</option></select></div>
    <div class="fg"><label>Account</label><input id="bAc" placeholder="HDFC ****1234"></div>
    <div class="fg"><label>Notes</label><input id="bNt" placeholder="optional"></div>
  </div>
  <button class="save" onclick="saveBill()">Save</button>
  <button style="padding:9px 16px;background:transparent;border:1px solid var(--bdr);border-radius:8px;color:var(--muted);cursor:pointer;margin-left:8px" onclick="tbf()">Cancel</button>
  </div></div>
  <div id="bsummary" style="margin-bottom:16px"></div>
  <div id="blist"></div>
</div></div>

<div id="tab-expiry" style="display:none"><div style="padding:16px 24px">
  <div style="font-size:16px;font-weight:600;margin-bottom:14px">Document Expiry Tracker</div>
  <div class="fbox" style="margin-bottom:16px"><div class="fgrid">
    <div class="fg"><label>Document Name</label><input id="eN" placeholder="Car Insurance TATA AIG"></div>
    <div class="fg"><label>Type</label><input id="eT" placeholder="insurance / passport / RC / DL"></div>
    <div class="fg"><label>Expiry Date</label><input id="eD" type="date"></div>
    <div class="fg"><label>Notes</label><input id="eNt" placeholder="Policy No: xxxxxxxx"></div>
  </div>
  <button class="save" onclick="saveExpiry()">Add Reminder</button></div>
  <div id="elist"></div>
</div></div>

<div id="tab-vault" style="display:none"><div style="padding:16px 24px">
  <div style="font-size:16px;font-weight:600;margin-bottom:6px">Secure Vault</div>
  <div style="font-size:12px;color:var(--muted);margin-bottom:14px">Encrypted on your machine only. Never sent anywhere.</div>
  <div class="fbox" style="margin-bottom:16px"><div class="fgrid">
    <div class="fg"><label>Label</label><input id="cL" placeholder="Gmail Work"></div>
    <div class="fg"><label>Category</label><select id="cCt">
      <option>email</option><option>bank</option><option>government</option>
      <option>investment</option><option>insurance</option><option>social</option>
      <option>work</option><option>shopping</option><option>other</option>
    </select></div>
    <div class="fg"><label>Username / Email / ID</label><input id="cU" placeholder="your@email.com"></div>
    <div class="fg"><label>Password / PIN</label><input id="cP" type="password" placeholder="••••••••"></div>
    <div class="fg"><label>Website / App</label><input id="cW" placeholder="https://gmail.com"></div>
    <div class="fg"><label>Notes</label><input id="cNt" placeholder="linked phone: 9876543210"></div>
  </div>
  <button class="save" onclick="saveCred()">Save Securely</button></div>
  <div id="vlist"></div>
</div></div>

<div id="tab-stats" style="display:none"><div style="padding:16px 24px" id="stats-c"></div></div>

<div class="ov" id="fov"><div class="modal">
  <div class="mttl"><span id="fttl">Files in folder</span>
  <button style="background:transparent;border:none;color:var(--muted);font-size:20px;cursor:pointer;line-height:1" onclick="cfov()">x</button></div>
  <div id="fres"></div>
</div></div>

<script>
let allR=[], curPg=0;
const PG=8;

async function doSearch(){
  const q=document.getElementById('si').value.trim(); if(!q)return;
  document.getElementById('results').innerHTML='<div style="padding:20px;color:var(--muted)">Searching...</div>';
  const d=await fetch('/api/search?q='+encodeURIComponent(q)).then(r=>r.json());
  allR=d.results||[]; curPg=0; renderPg();
  const m=document.getElementById('rmeta');
  m.style.display='block';
  m.innerHTML='<strong style="color:var(--tl)">'+allR.length+'</strong> results for "'+q+'"';
}

function qs(t){document.getElementById('si').value=t; doSearch();}

async function sp(p){
  document.getElementById('results').innerHTML='<div style="padding:20px;color:var(--muted)">Loading '+p+'...</div>';
  const d=await fetch('/api/profile_search?profile='+encodeURIComponent(p)).then(r=>r.json());
  allR=d.results||[]; curPg=0; renderPg();
  const m=document.getElementById('rmeta');
  m.style.display='block';
  m.innerHTML='<strong style="color:var(--tl)">'+allR.length+'</strong> files in <span style="color:var(--pl)">'+p+'</span> profile';
}

function ic(type,ext){
  if(ext==='.pdf')return{c:'ipdf',l:'PDF'};
  if(type==='document')return{c:'idoc',l:'DOC'};
  if(type==='image')return{c:'iimg',l:'IMG'};
  if(type==='video')return{c:'ivid',l:'VID'};
  if(type==='spreadsheet')return{c:'ixls',l:'XLS'};
  return{c:'ioth',l:(ext||'?').replace('.','').toUpperCase().slice(0,3)||'?'};
}
function ej(s){return(s||'').replace(/\\/g,'\\\\').replace(/'/g,"\\'")}

function card(f){
  const i=ic(f.type,f.ext);
  const sp=(f.path||'').length>60?'...'+(f.path||'').slice(-57):f.path||'';
  const pv=(f.content||'').replace(/\s+/g,' ').trim().slice(0,100);
  return '<div class="fc"><div class="ft">'+
    '<div class="fi '+i.c+'">'+i.l+'</div>'+
    '<div style="flex:1;min-width:0">'+
    '<div class="fn" onclick="opf(\''+ej(f.path)+'\')">'+f.filename+'</div>'+
    '<div class="fp">'+sp+'</div>'+
    '<div class="fm">'+
    '<span class="ftg tt">'+f.type+'</span>'+
    '<span class="ftg ts">'+(f.size_hr||'')+'</span>'+
    '<span class="ftg ts">'+(f.modified||'').slice(0,10)+'</span>'+
    (f.open_count>0?'<span class="ftg" style="background:rgba(240,160,32,.12);color:var(--amber)">'+f.open_count+'x</span>':'')+
    '</div>'+(pv?'<div class="fpv">'+pv+'...</div>':'')+
    '</div></div>'+
    '<div class="fba">'+
    '<button class="fb fbop" onclick="opf(\''+ej(f.path)+'\')">Open File</button>'+
    '<button class="fb" onclick="brf(\''+ej(f.folder||'')+'\',\''+ej(f.path)+'\')">Browse Folder</button>'+
    '<button class="fb" onclick="tgf(\''+ej(f.path)+'\')">+ Tag</button>'+
    '</div></div>';
}

function renderPg(){
  const s=curPg*PG, ch=allR.slice(s,s+PG);
  document.getElementById('results').innerHTML=allR.length?ch.map(card).join(''):
    '<div class="empty"><h3>Nothing found</h3><p>Try a shorter word or check spelling.<br>Example: type "pan" not "pan card image"</p></div>';
  const tot=Math.ceil(allR.length/PG);
  document.getElementById('pgn').innerHTML=tot>1?Array.from({length:tot},(_,p)=>
    '<button class="pg'+(p===curPg?' on':'')+'" onclick="gp('+p+')">'+(p+1)+'</button>').join(''):'';
}
function gp(p){curPg=p;renderPg();window.scrollTo(0,140);}

async function opf(path){if(!path)return;await fetch('/api/open?path='+encodeURIComponent(path));}

async function brf(folder,cur){
  if(!folder){alert('Folder path not available');return;}
  document.getElementById('fttl').textContent='Files in: '+folder;
  document.getElementById('fres').innerHTML='<div style="padding:20px;color:var(--muted)">Loading...</div>';
  document.getElementById('fov').classList.add('show');
  const d=await fetch('/api/folder_files?folder='+encodeURIComponent(folder)).then(r=>r.json());
  const files=d.files||[];
  document.getElementById('fres').innerHTML=files.length?files.map(f=>{
    const i=ic(f.type,f.ext),isC=f.path===cur;
    return '<div class="fc" style="'+(isC?'border-color:var(--purple)':'')+'">'+
      '<div class="ft"><div class="fi '+i.c+'">'+i.l+'</div>'+
      '<div style="flex:1;min-width:0">'+
      '<div class="fn" onclick="opf(\''+ej(f.path)+'\')">'+f.filename+(isC?' <span style="font-size:10px;color:var(--pl)">this file</span>':'')+'</div>'+
      '<div class="fm"><span class="ftg tt">'+f.type+'</span><span class="ftg ts">'+(f.size_hr||'')+'</span></div>'+
      '</div></div><div class="fba"><button class="fb fbop" onclick="opf(\''+ej(f.path)+'\')">Open</button></div></div>';
  }).join(''):'<div class="empty"><h3>No indexed files in this folder</h3></div>';
}
function cfov(){document.getElementById('fov').classList.remove('show');}
async function tgf(p){const t=prompt('Enter tag:');if(!t)return;await fetch('/api/tag?path='+encodeURIComponent(p)+'&tag='+encodeURIComponent(t));doSearch();}

async function loadRecent(){
  const d=await fetch('/api/recent').then(r=>r.json());
  allR=d.files||[];curPg=0;renderPg();
  const m=document.getElementById('rmeta');m.style.display='block';
  m.innerHTML='<strong style="color:var(--tl)">'+allR.length+'</strong> recently opened files';
}
async function loadFreq(){
  const d=await fetch('/api/frequent').then(r=>r.json());
  allR=d.files||[];curPg=0;renderPg();
  const m=document.getElementById('rmeta');m.style.display='block';
  m.innerHTML='<strong style="color:var(--tl)">'+allR.length+'</strong> most used files';
}

// Bills
function tbf(){const e=document.getElementById('bform');e.style.display=e.style.display==='none'?'block':'none';}
async function saveBill(){
  const b={name:document.getElementById('bN').value.trim(),category:document.getElementById('bCt').value,
    amount:parseFloat(document.getElementById('bA').value)||0,due_day:parseInt(document.getElementById('bD').value)||1,
    frequency:document.getElementById('bF').value,auto_debit:parseInt(document.getElementById('bAD').value),
    account:document.getElementById('bAc').value,notes:document.getElementById('bNt').value};
  if(!b.name){alert('Name required');return;}
  await fetch('/api/add_bill',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(b)});
  tbf();loadBills();
}
async function payBill(id,name){
  const a=prompt('Amount paid for '+name+' (Rs):');if(!a)return;
  const m=prompt('Mode (UPI/Cash/NetBanking/Card):','UPI');
  await fetch('/api/pay_bill',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({id,amount:parseFloat(a),mode:m||'UPI'})});
  loadBills();
}
async function delBill(id){if(!confirm('Delete?'))return;await fetch('/api/del_bill?id='+id,{method:'DELETE'});loadBills();}
async function loadBills(){
  const[bd,sd]=await Promise.all([fetch('/api/bills').then(r=>r.json()),fetch('/api/bill_summary').then(r=>r.json())]);
  const bills=bd.bills||[],s=sd.summary||{};
  document.getElementById('bsummary').innerHTML=
    '<div class="sg">'+
    '<div class="sc"><div class="sn">Rs '+(s.total_due||0).toLocaleString('en-IN')+'</div><div class="sl">Monthly Total</div></div>'+
    '<div class="sc"><div class="sn">Rs '+(s.total_paid||0).toLocaleString('en-IN')+'</div><div class="sl">Paid This Month</div></div>'+
    '<div class="sc"><div class="sn">'+bills.filter(b=>b.status==='paid').length+'</div><div class="sl">Paid</div></div>'+
    '<div class="sc"><div class="sn">'+bills.filter(b=>b.status==='pending').length+'</div><div class="sl">Pending</div></div></div>';
  const grp={};bills.forEach(b=>{(grp[b.category]=grp[b.category]||[]).push(b);});
  let h='';
  for(const[cat,items] of Object.entries(grp)){
    h+='<div style="font-size:11px;font-weight:600;color:var(--muted);text-transform:uppercase;margin:12px 0 6px">'+cat+'</div>';
    items.forEach(b=>{
      h+='<div class="bc"><div class="bi"><div class="bn">'+b.name+(b.auto_debit?' AUTO':'')+'</div>'+
        '<div class="bm">Day '+b.due_day+' '+b.frequency+(b.account?' · '+b.account:'')+'</div></div>'+
        '<div class="br"><div class="ba">Rs '+(b.amount||0).toLocaleString('en-IN')+'</div>'+
        '<span class="bs '+(b.status==='paid'?'bp':'bpd')+'">'+b.status+'</span></div>'+
        '<div style="display:flex;gap:5px;margin-left:8px">'+
        (b.status!=='paid'?'<button class="fb fbop" onclick="payBill('+b.id+',\''+b.name.replace(/'/g,"\\'")+'\')">Pay</button>':'')+
        '<button class="fb" onclick="delBill('+b.id+')">Del</button></div></div>';
    });
  }
  document.getElementById('blist').innerHTML=h||'<div class="empty"><h3>No bills yet</h3><p>Click + Add Bill to start tracking.</p></div>';
}

// Expiry
async function saveExpiry(){
  const b={doc_name:document.getElementById('eN').value.trim(),doc_type:document.getElementById('eT').value,
    expiry_date:document.getElementById('eD').value,notes:document.getElementById('eNt').value};
  if(!b.doc_name||!b.expiry_date){alert('Name and date required');return;}
  await fetch('/api/add_expiry',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(b)});
  loadExpiry();
}
async function delExpiry(id){await fetch('/api/del_expiry?id='+id,{method:'DELETE'});loadExpiry();}
async function loadExpiry(){
  const d=await fetch('/api/expiry').then(r=>r.json());
  document.getElementById('elist').innerHTML=(d.all||[]).map(e=>{
    const diff=Math.ceil((new Date(e.expiry_date)-new Date())/86400000);
    const col=diff<0?'var(--red)':diff<=30?'var(--amber)':'var(--tl)';
    const lbl=diff<0?'Expired '+Math.abs(diff)+'d ago':diff===0?'Today':''+diff+' days left';
    return '<div class="ec"><div><div style="font-size:13px;font-weight:600">'+e.doc_name+'</div>'+
      '<div style="font-size:11px;color:var(--muted);margin-top:2px">'+e.doc_type+(e.notes?' — '+e.notes:'')+'</div></div>'+
      '<div style="text-align:right"><div style="font-size:14px;font-weight:700;color:'+col+'">'+e.expiry_date+'</div>'+
      '<div style="font-size:10px;color:var(--muted)">'+lbl+'</div>'+
      '<button class="fb" style="margin-top:4px;font-size:10px" onclick="delExpiry('+e.id+')">Remove</button></div></div>';
  }).join('')||'<div class="empty"><h3>No expiry dates</h3><p>Add insurance, passport, RC, DL renewal dates above.</p></div>';
}

// Vault
async function saveCred(){
  const b={label:document.getElementById('cL').value.trim(),category:document.getElementById('cCt').value,
    username:document.getElementById('cU').value,password:document.getElementById('cP').value,
    url:document.getElementById('cW').value,notes:document.getElementById('cNt').value};
  if(!b.label){alert('Label required');return;}
  await fetch('/api/save_cred',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(b)});
  loadVault();
}
async function delCred(id){if(!confirm('Delete?'))return;await fetch('/api/del_cred?id='+id,{method:'DELETE'});loadVault();}
async function loadVault(){
  const d=await fetch('/api/credentials').then(r=>r.json());
  const creds=d.credentials||[];
  if(!creds.length){document.getElementById('vlist').innerHTML='<div class="empty"><h3>Vault empty</h3><p>Save email IDs, bank logins, portal passwords securely.</p></div>';return;}
  const grp={};creds.forEach(c=>{(grp[c.category]=grp[c.category]||[]).push(c);});
  let h='';
  for(const[cat,items] of Object.entries(grp)){
    h+='<div style="font-size:10px;font-weight:600;color:var(--muted);text-transform:uppercase;margin:12px 0 6px">'+cat+'</div>';
    items.forEach(c=>{
      h+='<div class="cc"><div><div style="font-size:13px;font-weight:600">'+c.label+'</div>'+
        '<div style="font-size:11px;color:var(--muted);margin-top:2px">'+c.username+(c.url?' · '+c.url:'')+'</div>'+
        (c.notes?'<div style="font-size:10px;color:var(--muted);margin-top:2px">'+c.notes+'</div>':'')+
        '</div><div style="display:flex;gap:6px;align-items:center">'+
        '<span class="pw" id="pw'+c.id+'" onclick="tpw('+c.id+',\''+c.password.replace(/'/g,"\\'")+'\')" >Show</span>'+
        '<button class="fb" onclick="delCred('+c.id+')" style="font-size:10px;padding:4px 8px">Del</button></div></div>';
    });
  }
  document.getElementById('vlist').innerHTML=h;
}
function tpw(id,pw){const e=document.getElementById('pw'+id);e.textContent=e.textContent==='Show'?pw:'Show';}

// Stats
async function loadStats(){
  const d=await fetch('/api/stats').then(r=>r.json());
  const s=d.stats||{};
  let h='<div class="sg">'+
    '<div class="sc"><div class="sn">'+(s.total||0).toLocaleString()+'</div><div class="sl">Files Indexed</div></div>';
  Object.entries(s.by_drive||{}).slice(0,3).forEach(([dr,cnt])=>{
    h+='<div class="sc"><div class="sn">'+cnt.toLocaleString()+'</div><div class="sl">'+dr+'</div></div>';
  });
  h+='</div><div class="fbox"><div style="font-size:13px;font-weight:500;margin-bottom:12px">By file type</div>';
  Object.entries(s.by_type||{}).sort((a,b)=>b[1]-a[1]).forEach(([t,c])=>{
    const pct=Math.min(100,c/(s.total||1)*100*3);
    h+='<div style="display:flex;align-items:center;gap:8px;margin-bottom:6px;font-size:12px">'+
      '<span style="min-width:100px;color:var(--muted)">'+t+'</span>'+
      '<div style="flex:1;height:5px;background:var(--bdr);border-radius:3px"><div style="width:'+pct+'%;height:100%;background:var(--purple);border-radius:3px"></div></div>'+
      '<span style="min-width:55px;text-align:right">'+c.toLocaleString()+'</span></div>';
  });
  h+='</div>';
  document.getElementById('stats-c').innerHTML=h;
}

function showTab(t,btn){
  ['search','bills','expiry','vault','stats'].forEach(x=>{
    const el=document.getElementById('tab-'+x);if(el)el.style.display=x===t?'block':'none';
  });
  document.querySelectorAll('.tab').forEach(b=>b.classList.remove('on'));
  if(btn)btn.classList.add('on');
  if(t==='bills')loadBills();
  if(t==='expiry')loadExpiry();
  if(t==='vault')loadVault();
  if(t==='stats')loadStats();
  if(t==='recent'){loadRecent();document.querySelectorAll('.tab')[0].classList.add('on');}
}

loadStats();
</script></body></html>"""


@app.get("/", response_class=HTMLResponse)
async def home():
    return HTML


@app.get("/api/search")
async def api_search(q: str = "", profile: str = None):
    return {"results": do_search(q, profile=profile, limit=100)}


@app.get("/api/profile_search")
async def api_profile(profile: str = "", q: str = ""):
    return {"results": profile_search(profile, q)}


@app.get("/api/folder_files")
async def api_folder(folder: str = ""):
    conn = get_conn()
    rows = conn.cursor().execute(
        "SELECT * FROM files WHERE folder=? ORDER BY filename", (folder,)
    ).fetchall()
    conn.close()
    return {"files": [dict(r) for r in rows]}


@app.get("/api/recent")
async def api_recent():
    conn = get_conn()
    rows = conn.cursor().execute(
        "SELECT * FROM files WHERE last_opened IS NOT NULL ORDER BY last_opened DESC LIMIT 20"
    ).fetchall()
    conn.close()
    return {"files": [dict(r) for r in rows]}


@app.get("/api/frequent")
async def api_frequent():
    conn = get_conn()
    rows = conn.cursor().execute(
        "SELECT * FROM files WHERE open_count>0 ORDER BY open_count DESC LIMIT 20"
    ).fetchall()
    conn.close()
    return {"files": [dict(r) for r in rows]}


@app.get("/api/stats")
async def api_stats():
    return {"stats": get_stats()}


@app.get("/api/open")
async def api_open(path: str):
    try:
        conn = get_conn()
        c = conn.cursor()
        c.execute(
            "UPDATE files SET open_count=open_count+1, last_opened=? WHERE path=?",
            (datetime.datetime.now().isoformat(), path))
        conn.commit()
        conn.close()
        if os.name == "nt":
            os.startfile(path)
        return {"ok": True}
    except Exception as e:
        return {"ok": False, "error": str(e)}


@app.get("/api/tag")
async def api_tag(path: str, tag: str):
    conn = get_conn()
    c = conn.cursor()
    row = c.execute("SELECT tags FROM files WHERE path=?", (path,)).fetchone()
    if row:
        tags = [t for t in (row[0] or "").split(",") if t]
        if tag not in tags:
            tags.append(tag)
        c.execute("UPDATE files SET tags=? WHERE path=?", (",".join(tags), path))
        conn.commit()
    conn.close()
    return {"ok": True}


@app.post("/api/add_bill")
async def api_add_bill(request: Request):
    d = await request.json()
    now = datetime.datetime.now().isoformat()
    conn = get_conn()
    c = conn.cursor()
    c.execute("""INSERT INTO bills (name,category,amount,due_day,frequency,
        auto_debit,account,notes,status,added_at,updated_at) VALUES (?,?,?,?,?,?,?,?,'pending',?,?)""",
        (d["name"], d.get("category","Other"), d.get("amount",0), d.get("due_day",1),
         d.get("frequency","monthly"), d.get("auto_debit",0),
         d.get("account",""), d.get("notes",""), now, now))
    conn.commit()
    conn.close()
    return {"ok": True}


@app.get("/api/bills")
async def api_bills():
    conn = get_conn()
    rows = conn.cursor().execute("SELECT * FROM bills ORDER BY due_day").fetchall()
    conn.close()
    return {"bills": [dict(r) for r in rows]}


@app.post("/api/pay_bill")
async def api_pay_bill(request: Request):
    d = await request.json()
    today = datetime.date.today().isoformat()
    now = datetime.datetime.now().isoformat()
    conn = get_conn()
    c = conn.cursor()
    c.execute("UPDATE bills SET status='paid',last_paid=?,last_amount=?,updated_at=? WHERE id=?",
              (today, d.get("amount",0), now, d["id"]))
    c.execute("INSERT INTO bill_payments (bill_id,amount,paid_date,mode) VALUES (?,?,?,?)",
              (d["id"], d.get("amount",0), today, d.get("mode","UPI")))
    conn.commit()
    conn.close()
    return {"ok": True}


@app.delete("/api/del_bill")
async def api_del_bill(id: int):
    conn = get_conn()
    c = conn.cursor()
    c.execute("DELETE FROM bills WHERE id=?", (id,))
    c.execute("DELETE FROM bill_payments WHERE bill_id=?", (id,))
    conn.commit()
    conn.close()
    return {"ok": True}


@app.get("/api/bill_summary")
async def api_bill_summary():
    conn = get_conn()
    c = conn.cursor()
    ms = datetime.date.today().replace(day=1).isoformat()
    paid = c.execute("SELECT COALESCE(SUM(amount),0) FROM bill_payments WHERE paid_date>=?", (ms,)).fetchone()[0]
    total = c.execute("SELECT COALESCE(SUM(amount),0) FROM bills WHERE frequency='monthly'").fetchone()[0]
    conn.close()
    return {"summary": {"total_paid": paid, "total_due": total}}


@app.get("/api/expiry")
async def api_expiry():
    conn = get_conn()
    c = conn.cursor()
    today = datetime.date.today()
    dl = (today + datetime.timedelta(days=30)).isoformat()
    exp = c.execute("SELECT * FROM expiry WHERE expiry_date<=? AND expiry_date>=? ORDER BY expiry_date",
                    (dl, today.isoformat())).fetchall()
    all_e = c.execute("SELECT * FROM expiry ORDER BY expiry_date").fetchall()
    conn.close()
    return {"expiring": [dict(r) for r in exp], "all": [dict(r) for r in all_e]}


@app.post("/api/add_expiry")
async def api_add_expiry(request: Request):
    d = await request.json()
    conn = get_conn()
    conn.cursor().execute(
        "INSERT INTO expiry (doc_name,doc_type,file_path,expiry_date,notes,added_at) VALUES (?,?,?,?,?,?)",
        (d["doc_name"], d.get("doc_type",""), "", d["expiry_date"],
         d.get("notes",""), datetime.datetime.now().isoformat()))
    conn.commit()
    conn.close()
    return {"ok": True}


@app.delete("/api/del_expiry")
async def api_del_expiry(id: int):
    conn = get_conn()
    conn.cursor().execute("DELETE FROM expiry WHERE id=?", (id,))
    conn.commit()
    conn.close()
    return {"ok": True}


@app.get("/api/credentials")
async def api_creds():
    conn = get_conn()
    rows = conn.cursor().execute("SELECT * FROM credentials ORDER BY category,label").fetchall()
    conn.close()
    result = []
    for row in rows:
        d = dict(row)
        d["password"] = _dec(d.get("password", ""))
        result.append(d)
    return {"credentials": result}


@app.post("/api/save_cred")
async def api_save_cred(request: Request):
    d = await request.json()
    now = datetime.datetime.now().isoformat()
    conn = get_conn()
    conn.cursor().execute(
        "INSERT INTO credentials (label,category,username,password,url,notes,added_at,updated_at) VALUES (?,?,?,?,?,?,?,?)",
        (d["label"], d.get("category","other"), d.get("username",""),
         _enc(d.get("password","")), d.get("url",""), d.get("notes",""), now, now))
    conn.commit()
    conn.close()
    return {"ok": True}


@app.delete("/api/del_cred")
async def api_del_cred(id: int):
    conn = get_conn()
    conn.cursor().execute("DELETE FROM credentials WHERE id=?", (id,))
    conn.commit()
    conn.close()
    return {"ok": True}


if __name__ == "__main__":
    print("\n  MemorA v4 starting...")
    total = init_db()
    if total == 0:
        total = get_conn().cursor().execute("SELECT COUNT(*) FROM files").fetchone()[0]
    print(f"  {total:,} files ready")
    print("  Open browser: http://localhost:7000")
    print("  Press Ctrl+C to stop\n")
    uvicorn.run(app, host="127.0.0.1", port=7000, log_level="warning")
