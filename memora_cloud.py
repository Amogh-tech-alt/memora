"""
memora_cloud.py
Main web app for Render.com deployment.
Multi-user with login, file upload, search, bills, vault, expiry.
Run locally: python memora_cloud.py
Deploy: pushed to GitHub, auto-deploys on Render
"""

import os
import sys
import json
import datetime
import shutil
import tempfile
from pathlib import Path

from fastapi import FastAPI, Request, UploadFile, File, Form, Cookie
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
import uvicorn

sys.path.insert(0, os.path.dirname(__file__))
from memora_cloud_db import (
    create_user, login_user, get_user_by_id,
    upsert_file, search_files, get_stats, increment_open,
    add_bill, get_bills, mark_paid, delete_bill,
    get_upcoming_bills,
    add_expiry, get_expiry, get_expiring_soon, delete_expiry,
    save_credential, get_credentials, delete_credential,
)

app  = FastAPI(title="MemorA")
PORT = int(os.environ.get("PORT", 7000))

# Simple in-memory session store (replace with Redis for production)
SESSIONS: dict = {}

FILE_CATEGORIES = {
    "identity":  ["aadhaar","aadhar","pan","passport","voter","driving","licence"],
    "finance":   ["bank","statement","invoice","receipt","salary","tax","itr","form16"],
    "insurance": ["insurance","policy","premium","mediclaim","lic","claim"],
    "property":  ["property","deed","flat","house","land","registry"],
    "health":    ["health","medical","hospital","prescription","lab","blood"],
    "education": ["certificate","degree","marksheet","transcript","college"],
    "work":      ["offer","appointment","payslip","experience","joining"],
    "legal":     ["agreement","contract","affidavit","notary","moa","aoa"],
    "vehicle":   ["vehicle","car","rc","pollution","puc","challan"],
    "gst":       ["gst","gstin","gstr","invoice","eway"],
    "media":     [".jpg",".jpeg",".png",".mp4",".mov"],
}


def categorise_file(filename: str, content: str = "") -> str:
    text = (filename + " " + content).lower()
    matched = []
    for cat, keywords in FILE_CATEGORIES.items():
        for kw in keywords:
            if kw in text:
                matched.append(cat)
                break
    return ",".join(matched) if matched else "document"


def extract_text(filepath: str, ext: str) -> str:
    try:
        if ext == ".pdf":
            import pdfplumber
            with pdfplumber.open(filepath) as pdf:
                return " ".join(
                    p.extract_text() or "" for p in pdf.pages[:3]
                )[:1000]
        elif ext in [".docx", ".doc"]:
            import docx
            doc = docx.Document(filepath)
            return " ".join(p.text for p in doc.paragraphs[:20])[:1000]
        elif ext in [".txt", ".csv"]:
            with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
                return f.read()[:1000]
        elif ext in [".xlsx", ".xls"]:
            import openpyxl
            wb = openpyxl.load_workbook(filepath, read_only=True, data_only=True)
            ws = wb.active
            vals = []
            for row in list(ws.iter_rows(values_only=True))[:5]:
                vals.extend([str(c) for c in row if c])
            return " ".join(vals)[:500]
    except Exception:
        pass
    return ""


def get_user_from_session(request: Request) -> dict | None:
    token = request.cookies.get("memora_token")
    if not token or token not in SESSIONS:
        return None
    session = SESSIONS[token]
    if datetime.datetime.now() > session["expires"]:
        del SESSIONS[token]
        return None
    return session


def require_login(request: Request):
    user = get_user_from_session(request)
    if not user:
        return None
    return user


# ── HTML PAGES ────────────────────────────────────────────────

LOGIN_PAGE = """<!DOCTYPE html>
<html lang="en"><head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>MemorA - Login</title>
<style>
*{box-sizing:border-box;margin:0;padding:0}
body{background:#0f0f14;color:#e8e6f0;font-family:'Segoe UI',Arial,sans-serif;
  display:flex;align-items:center;justify-content:center;min-height:100vh}
.box{background:#1a1a24;border:1px solid #2e2e4a;border-radius:16px;padding:36px;width:380px}
.logo{display:flex;align-items:center;gap:12px;margin-bottom:28px;justify-content:center}
.logo-icon{width:44px;height:44px;border-radius:10px;
  background:linear-gradient(135deg,#534AB7,#1D9E75);
  display:flex;align-items:center;justify-content:center;
  font-size:22px;font-weight:800;color:white}
.logo-text{font-size:24px;font-weight:700}
.logo-text span:first-child{color:#a89ef5}
.logo-text span:last-child{color:#4dd9a0}
.tagline{text-align:center;color:#8885a0;font-size:12px;margin-bottom:28px}
.tabs{display:flex;gap:0;margin-bottom:24px;border:1px solid #2e2e4a;border-radius:8px;overflow:hidden}
.tab{flex:1;padding:9px;text-align:center;cursor:pointer;font-size:13px;
  color:#8885a0;transition:all .15s;background:transparent;border:none}
.tab.active{background:#7c6fdf;color:white}
.fg{margin-bottom:14px}
.fg label{display:block;font-size:11px;color:#8885a0;margin-bottom:4px}
.fg input{width:100%;padding:10px 12px;background:#0f0f14;border:1px solid #2e2e4a;
  border-radius:8px;color:#e8e6f0;font-size:14px;outline:none}
.fg input:focus{border-color:#7c6fdf}
.btn{width:100%;padding:11px;background:#7c6fdf;border:none;border-radius:8px;
  color:white;font-size:14px;font-weight:600;cursor:pointer;margin-top:6px}
.btn:hover{background:#6a5fcc}
.err{color:#e05555;font-size:12px;margin-top:8px;text-align:center}
.ok{color:#1db87a;font-size:12px;margin-top:8px;text-align:center}
</style></head><body>
<div class="box">
  <div class="logo">
    <div class="logo-icon">M</div>
    <div class="logo-text"><span>Memor</span><span>A</span></div>
  </div>
  <div class="tagline">Your Personal AI Memory — find anything instantly</div>
  <div class="tabs">
    <button class="tab active" onclick="showTab('login',this)">Login</button>
    <button class="tab" onclick="showTab('signup',this)">Sign Up</button>
  </div>

  <div id="login-form">
    <div class="fg"><label>Email</label><input id="le" type="email" placeholder="your@email.com"></div>
    <div class="fg"><label>Password</label><input id="lp" type="password" placeholder="••••••••"></div>
    <button class="btn" onclick="doLogin()">Login</button>
    <div id="lerr" class="err"></div>
  </div>

  <div id="signup-form" style="display:none">
    <div class="fg"><label>Full Name</label><input id="sn" placeholder="Your name"></div>
    <div class="fg"><label>Email</label><input id="se" type="email" placeholder="your@email.com"></div>
    <div class="fg"><label>Password</label><input id="sp" type="password" placeholder="min 6 characters"></div>
    <button class="btn" onclick="doSignup()">Create Account</button>
    <div id="serr" class="err"></div>
    <div id="sok" class="ok"></div>
  </div>
</div>
<script>
function showTab(tab, btn){
  document.getElementById('login-form').style.display  = tab==='login'  ? 'block':'none';
  document.getElementById('signup-form').style.display = tab==='signup' ? 'block':'none';
  document.querySelectorAll('.tab').forEach(b=>b.classList.remove('active'));
  btn.classList.add('active');
}
async function doLogin(){
  const e=document.getElementById('le').value.trim();
  const p=document.getElementById('lp').value;
  const r=await fetch('/api/login',{method:'POST',headers:{'Content-Type':'application/json'},
    body:JSON.stringify({email:e,password:p})}).then(r=>r.json());
  if(r.ok) window.location='/app';
  else document.getElementById('lerr').textContent=r.error||'Login failed';
}
async function doSignup(){
  const n=document.getElementById('sn').value.trim();
  const e=document.getElementById('se').value.trim();
  const p=document.getElementById('sp').value;
  if(!n||!e||!p){document.getElementById('serr').textContent='All fields required';return;}
  if(p.length<6){document.getElementById('serr').textContent='Password min 6 characters';return;}
  const r=await fetch('/api/signup',{method:'POST',headers:{'Content-Type':'application/json'},
    body:JSON.stringify({name:n,email:e,password:p})}).then(r=>r.json());
  if(r.ok){document.getElementById('sok').textContent='Account created! Logging in...';
    setTimeout(()=>window.location='/app',1500);}
  else document.getElementById('serr').textContent=r.error||'Signup failed';
}
document.addEventListener('keydown',e=>{if(e.key==='Enter')doLogin();});
</script></body></html>"""


def build_app_page(user: dict) -> str:
    name  = user.get("name", "User")
    email = user.get("email", "")
    return f"""<!DOCTYPE html>
<html lang="en"><head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>MemorA</title>
<style>
*{{box-sizing:border-box;margin:0;padding:0}}
body{{background:#0f0f14;color:#e8e6f0;font-family:'Segoe UI',Arial,sans-serif;min-height:100vh}}
.hdr{{background:#1a1a24;border-bottom:1px solid #2e2e4a;padding:12px 24px;
  display:flex;align-items:center;gap:14px;position:sticky;top:0;z-index:100}}
.logo{{display:flex;align-items:center;gap:10px}}
.li{{width:38px;height:38px;border-radius:9px;
  background:linear-gradient(135deg,#534AB7,#1D9E75);
  display:flex;align-items:center;justify-content:center;
  font-size:18px;font-weight:800;color:white;flex-shrink:0}}
.lt span:first-child{{color:#a89ef5;font-size:19px;font-weight:700}}
.lt span:last-child{{color:#4dd9a0;font-size:19px;font-weight:700}}
.ls{{font-size:10px;color:#8885a0}}
.hdr-r{{margin-left:auto;display:flex;align-items:center;gap:8px;flex-wrap:wrap}}
.tab{{padding:6px 13px;border-radius:7px;border:1px solid #2e2e4a;
  background:transparent;color:#8885a0;font-size:12px;cursor:pointer;transition:all .15s}}
.tab.active,.tab:hover{{background:#7c6fdf;border-color:#7c6fdf;color:white}}
.user-info{{font-size:11px;color:#8885a0}}
.logout{{padding:6px 12px;border-radius:7px;border:1px solid #2e2e4a;
  background:transparent;color:#e05555;font-size:12px;cursor:pointer}}
.srch-wrap{{padding:18px 24px 0}}
.sbox{{display:flex;gap:8px;background:#1a1a24;border:2px solid #2e2e4a;
  border-radius:13px;padding:4px 6px 4px 16px;transition:border-color .2s}}
.sbox:focus-within{{border-color:#7c6fdf}}
.sbox input{{flex:1;background:transparent;border:none;outline:none;
  color:#e8e6f0;font-size:16px;padding:8px 0}}
.sbox input::placeholder{{color:#8885a0}}
.sbtn{{padding:8px 18px;background:#7c6fdf;border:none;border-radius:9px;
  color:white;font-size:13px;font-weight:600;cursor:pointer}}
.sbtn:hover{{background:#6a5fcc}}
.qtags{{display:flex;gap:6px;flex-wrap:wrap;padding:10px 24px 0}}
.qt{{padding:3px 10px;border-radius:14px;font-size:11px;cursor:pointer;
  border:1px solid #2e2e4a;color:#8885a0;background:transparent;transition:all .15s}}
.qt:hover{{border-color:#7c6fdf;color:#a89ef5}}
.upload-bar{{padding:10px 24px;display:flex;align-items:center;gap:8px}}
.upload-btn{{padding:7px 14px;background:#1a1a24;border:1px dashed #2e2e4a;
  border-radius:8px;color:#8885a0;font-size:12px;cursor:pointer;transition:all .15s}}
.upload-btn:hover{{border-color:#7c6fdf;color:#a89ef5}}
.cnt{{padding:14px 24px}}
.fc{{background:#1a1a24;border:1px solid #2e2e4a;border-radius:11px;
  padding:12px 14px;margin-bottom:8px;transition:border-color .15s}}
.fc:hover{{border-color:rgba(124,111,223,.4)}}
.fn{{font-size:14px;font-weight:600;margin-bottom:4px}}
.fp{{font-size:11px;color:#8885a0;margin-bottom:5px}}
.fmeta{{display:flex;gap:5px;flex-wrap:wrap;margin-bottom:5px}}
.ftag{{padding:2px 7px;border-radius:5px;font-size:10px;font-weight:500}}
.ttype{{background:rgba(124,111,223,.15);color:#a89ef5}}
.tcat{{background:rgba(29,184,122,.15);color:#4dd9a0}}
.tsz{{background:rgba(136,133,160,.1);color:#8885a0}}
.tdt{{background:rgba(136,133,160,.1);color:#8885a0}}
.fprev{{font-size:11px;color:#8885a0;line-height:1.5;margin-top:4px}}
.fbtns{{display:flex;gap:5px;margin-top:8px}}
.fb{{padding:4px 10px;border-radius:6px;border:1px solid #2e2e4a;
  background:transparent;color:#8885a0;font-size:11px;cursor:pointer;transition:all .15s}}
.fb:hover{{border-color:#7c6fdf;color:#a89ef5}}
.fb.open{{background:#7c6fdf;border-color:#7c6fdf;color:white}}
.fci{{width:32px;height:32px;border-radius:7px;display:flex;align-items:center;
  justify-content:center;font-size:10px;font-weight:700;flex-shrink:0}}
.ipdf{{background:rgba(224,85,85,.2);color:#e05555}}
.idoc{{background:rgba(124,111,223,.2);color:#a89ef5}}
.iimg{{background:rgba(29,184,122,.2);color:#4dd9a0}}
.ioth{{background:rgba(136,133,160,.12);color:#8885a0}}
.fct{{display:flex;gap:10px;align-items:flex-start}}
.fci-info{{flex:1;min-width:0}}
.pgn{{display:flex;gap:5px;justify-content:center;margin-top:12px;flex-wrap:wrap}}
.pg{{padding:5px 11px;border-radius:7px;border:1px solid #2e2e4a;
  background:transparent;color:#8885a0;font-size:12px;cursor:pointer}}
.pg.act,.pg:hover{{background:#7c6fdf;border-color:#7c6fdf;color:white}}
.sg{{display:grid;grid-template-columns:repeat(3,1fr);gap:8px;margin-bottom:14px}}
.sc{{background:#1a1a24;border:1px solid #2e2e4a;border-radius:10px;padding:12px;text-align:center}}
.sn{{font-size:22px;font-weight:700;color:#a89ef5}}
.sl{{font-size:10px;color:#8885a0;margin-top:2px}}
.form-box{{background:#1a1a24;border:1px solid #2e2e4a;border-radius:11px;
  padding:14px;margin-bottom:12px}}
.fg2 label{{display:block;font-size:11px;color:#8885a0;margin-bottom:3px}}
.fg2 input,.fg2 select{{width:100%;padding:8px 10px;background:#0f0f14;
  border:1px solid #2e2e4a;border-radius:7px;color:#e8e6f0;font-size:13px;outline:none}}
.fg2 input:focus,.fg2 select:focus{{border-color:#7c6fdf}}
.fg2 select option{{background:#1a1a24}}
.fgrid{{display:grid;grid-template-columns:1fr 1fr;gap:8px;margin-bottom:8px}}
.save{{padding:8px 16px;background:#1db87a;border:none;border-radius:7px;
  color:white;font-size:13px;font-weight:600;cursor:pointer}}
.save:hover{{background:#18a06a}}
.cancel{{padding:8px 16px;background:transparent;border:1px solid #2e2e4a;
  border-radius:7px;color:#8885a0;font-size:13px;cursor:pointer}}
.bill-card{{background:#1a1a24;border:1px solid #2e2e4a;border-radius:10px;
  padding:11px 13px;margin-bottom:6px;display:flex;align-items:center;gap:10px}}
.bill-name{{font-size:13px;font-weight:600}}
.bill-meta{{font-size:11px;color:#8885a0;margin-top:2px}}
.bpaid{{background:rgba(34,197,94,.15);color:#22c55e;padding:2px 7px;
  border-radius:10px;font-size:10px;font-weight:600}}
.bpending{{background:rgba(240,160,32,.15);color:#f0a020;padding:2px 7px;
  border-radius:10px;font-size:10px;font-weight:600}}
.exp-card{{background:#1a1a24;border:1px solid rgba(240,160,32,.3);border-radius:10px;
  padding:11px 13px;margin-bottom:6px;display:flex;justify-content:space-between;align-items:center}}
.cred-card{{background:#1a1a24;border:1px solid #2e2e4a;border-radius:10px;
  padding:11px 13px;margin-bottom:6px;display:flex;justify-content:space-between;align-items:center}}
.alert-bar{{background:rgba(240,160,32,.1);border:1px solid rgba(240,160,32,.25);
  border-radius:9px;padding:9px 13px;margin-bottom:12px;font-size:12px;color:#f0a020}}
.empty{{text-align:center;padding:50px;color:#8885a0}}
.empty h3{{font-size:15px;margin-bottom:8px;color:#e8e6f0}}
.empty p{{font-size:12px;line-height:1.7}}
.upload-progress{{font-size:12px;color:#4dd9a0;margin-top:6px}}
@media(max-width:600px){{.hdr{{flex-wrap:wrap}}.fgrid{{grid-template-columns:1fr}}.sg{{grid-template-columns:1fr 1fr}}}}
</style></head><body>

<div class="hdr">
  <div class="logo">
    <div class="li">M</div>
    <div><div class="lt"><span>Memor</span><span>A</span></div>
    <div class="ls">Your Personal AI Memory</div></div>
  </div>
  <div class="hdr-r">
    <button class="tab active" onclick="showTab('search',this)">Search</button>
    <button class="tab" onclick="showTab('bills',this)">Bills</button>
    <button class="tab" onclick="showTab('expiry',this)">Expiry</button>
    <button class="tab" onclick="showTab('vault',this)">Vault</button>
    <button class="tab" onclick="showTab('stats',this)">Stats</button>
    <span class="user-info">{name}</span>
    <button class="logout" onclick="logout()">Logout</button>
  </div>
</div>

<div id="tab-search">
  <div class="srch-wrap">
    <div class="sbox">
      <input id="si" type="text" placeholder="Search your files — PAN, insurance, bank, salary..."
             onkeydown="if(event.key==='Enter')doSearch()">
      <button class="sbtn" onclick="doSearch()">Search</button>
    </div>
  </div>
  <div class="qtags">
    <span class="qt" onclick="qs('PAN')">PAN</span>
    <span class="qt" onclick="qs('aadhaar')">Aadhaar</span>
    <span class="qt" onclick="qs('insurance')">Insurance</span>
    <span class="qt" onclick="qs('bank')">Bank</span>
    <span class="qt" onclick="qs('salary')">Salary</span>
    <span class="qt" onclick="qs('ITR')">ITR</span>
    <span class="qt" onclick="qs('property')">Property</span>
    <span class="qt" onclick="qs('photo')">Photos</span>
    <span class="qt" onclick="qs('certificate')">Certificate</span>
    <span class="qt" onclick="qs('loan')">Loan</span>
  </div>
  <div class="upload-bar">
    <input type="file" id="upfile" multiple style="display:none" onchange="uploadFiles()">
    <button class="upload-btn" onclick="document.getElementById('upfile').click()">+ Upload Documents</button>
    <div id="up-progress" class="upload-progress"></div>
  </div>
  <div class="cnt">
    <div id="alert-area"></div>
    <div id="res-meta" style="display:none;font-size:13px;color:#8885a0;margin-bottom:10px"></div>
    <div id="results">
      <div class="empty">
        <h3>Welcome to MemorA, {name}</h3>
        <p>Upload your documents using the button above.<br>
        Then search for anything — PAN, insurance, bank statements,<br>
        certificates, salary slips — all in one place.</p>
      </div>
    </div>
    <div id="pgn" class="pgn"></div>
  </div>
</div>

<div id="tab-bills" style="display:none">
  <div style="padding:14px 24px">
    <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:12px">
      <div style="font-size:15px;font-weight:600">Bills Tracker</div>
      <button class="save" onclick="toggleAddBill()">+ Add Bill</button>
    </div>
    <div id="bill-form" style="display:none" class="form-box">
      <div style="font-size:12px;font-weight:500;margin-bottom:10px;color:#a89ef5">Add Bill</div>
      <div class="fgrid">
        <div class="fg2"><label>Name</label><input id="bN" placeholder="Electricity Bill"></div>
        <div class="fg2"><label>Category</label>
          <select id="bC"><option>Utilities</option><option>Loan / EMI</option>
          <option>Insurance</option><option>Education</option><option>Rent</option>
          <option>Medical</option><option>Subscription</option><option>Other</option></select></div>
        <div class="fg2"><label>Amount (Rs)</label><input id="bA" type="number" placeholder="1500"></div>
        <div class="fg2"><label>Due Day</label><input id="bD" type="number" min="1" max="31" placeholder="5"></div>
        <div class="fg2"><label>Frequency</label>
          <select id="bF"><option>monthly</option><option>quarterly</option>
          <option>yearly</option><option>one-time</option></select></div>
        <div class="fg2"><label>Account</label><input id="bAc" placeholder="HDFC ****1234"></div>
      </div>
      <button class="save" onclick="saveBill()">Save</button>
      <button class="cancel" onclick="toggleAddBill()" style="margin-left:8px">Cancel</button>
    </div>
    <div id="bill-summary" style="margin-bottom:12px"></div>
    <div id="bill-list"></div>
  </div>
</div>

<div id="tab-expiry" style="display:none">
  <div style="padding:14px 24px">
    <div style="font-size:15px;font-weight:600;margin-bottom:12px">Expiry Tracker</div>
    <div class="form-box">
      <div class="fgrid">
        <div class="fg2"><label>Document Name</label><input id="eN" placeholder="Car Insurance"></div>
        <div class="fg2"><label>Type</label><input id="eT" placeholder="insurance / passport / RC"></div>
        <div class="fg2"><label>Expiry Date</label><input id="eD" type="date"></div>
        <div class="fg2"><label>Notes</label><input id="eNo" placeholder="Policy No: xxx"></div>
      </div>
      <button class="save" onclick="saveExpiry()">Add Reminder</button>
    </div>
    <div id="exp-list"></div>
  </div>
</div>

<div id="tab-vault" style="display:none">
  <div style="padding:14px 24px">
    <div style="font-size:15px;font-weight:600;margin-bottom:6px">Secure Vault</div>
    <div style="font-size:11px;color:#8885a0;margin-bottom:12px">Encrypted on server. Only you can see your data.</div>
    <div class="form-box">
      <div class="fgrid">
        <div class="fg2"><label>Label</label><input id="cL" placeholder="Gmail Work"></div>
        <div class="fg2"><label>Category</label>
          <select id="cC"><option>email</option><option>bank</option><option>government</option>
          <option>investment</option><option>social</option><option>work</option><option>other</option></select></div>
        <div class="fg2"><label>Username / ID</label><input id="cU" placeholder="your@email.com"></div>
        <div class="fg2"><label>Password</label><input id="cP" type="password" placeholder="••••••••"></div>
        <div class="fg2"><label>Website</label><input id="cW" placeholder="https://gmail.com"></div>
        <div class="fg2"><label>Notes</label><input id="cNo" placeholder="linked phone etc."></div>
      </div>
      <button class="save" onclick="saveCred()">Save Securely</button>
    </div>
    <div id="vault-list"></div>
  </div>
</div>

<div id="tab-stats" style="display:none">
  <div style="padding:14px 24px" id="stats-cnt"></div>
</div>

<script>
let allRes=[], curPage=0;
const PAGE=8;

async function doSearch(){{
  const q=document.getElementById('si').value.trim();
  if(!q)return;
  document.getElementById('results').innerHTML='<div style="padding:20px;color:#8885a0;font-size:13px">Searching...</div>';
  document.getElementById('res-meta').style.display='none';
  showTab('search',null);
  const data=await fetch('/api/search?q='+encodeURIComponent(q)).then(r=>r.json());
  allRes=data.results||[];
  curPage=0;
  const m=document.getElementById('res-meta');
  m.style.display='block';
  m.innerHTML='<strong style="color:#4dd9a0">'+allRes.length+'</strong> results for "'+q+'"';
  renderPage();
}}
function qs(t){{document.getElementById('si').value=t;doSearch();}}

function renderPage(){{
  const start=curPage*PAGE, chunk=allRes.slice(start,start+PAGE);
  const el=document.getElementById('results');
  if(!allRes.length){{el.innerHTML='<div class="empty"><h3>Nothing found</h3><p>Try a different keyword or upload the document first.</p></div>';return;}}
  el.innerHTML=chunk.map((f,i)=>buildCard(f,start+i+1)).join('');
  const total=Math.ceil(allRes.length/PAGE);
  let pg='';
  for(let p=0;p<total;p++)pg+='<button class="pg'+(p===curPage?' act':'')+'" onclick="goPage('+p+')">'+(p+1)+'</button>';
  document.getElementById('pgn').innerHTML=pg;
}}
function goPage(p){{curPage=p;renderPage();window.scrollTo(0,0);}}

function getIcon(type,ext){{
  if(ext==='.pdf')return{{cls:'ipdf',lbl:'PDF'}};
  if(type==='image')return{{cls:'iimg',lbl:'IMG'}};
  if(type==='document')return{{cls:'idoc',lbl:'DOC'}};
  return{{cls:'ioth',lbl:(ext||'?').replace('.','').toUpperCase().slice(0,3)}};
}}
function esc(s){{return s.replace(/\\\\/g,'\\\\\\\\').replace(/'/g,"\\\\'");}}

function buildCard(f,n){{
  const ic=getIcon(f.type,f.ext);
  const cats=(f.categories||'').split(',').slice(0,2).join(', ');
  const prev=(f.content||'').replace(/\\s+/g,' ').trim().slice(0,100);
  return '<div class="fc"><div class="fct">'+
    '<div class="fci '+ic.cls+'">'+ic.lbl+'</div>'+
    '<div class="fci-info">'+
    '<div class="fn">'+f.filename+'</div>'+
    '<div class="fmeta">'+
    '<span class="ftag ttype">'+(f.type||'')+'</span>'+
    '<span class="ftag tcat">'+cats+'</span>'+
    '<span class="ftag tsz">'+(f.size_hr||'')+'</span>'+
    '<span class="ftag tdt">'+(f.modified||'').slice(0,10)+'</span>'+
    '</div>'+(prev?'<div class="fprev">'+prev+'...</div>':'')+
    '</div></div>'+
    '<div class="fbtns">'+
    '<button class="fb" onclick="tagFile('+f.id+')">+ Tag</button>'+
    '</div></div>';
}}

async function uploadFiles(){{
  const files=document.getElementById('upfile').files;
  if(!files.length)return;
  const prog=document.getElementById('up-progress');
  prog.textContent='Uploading '+files.length+' file(s)...';
  const fd=new FormData();
  for(const f of files)fd.append('files',f);
  const r=await fetch('/api/upload',{{method:'POST',body:fd}}).then(r=>r.json());
  prog.textContent=r.message||'Done';
  setTimeout(()=>prog.textContent='',3000);
}}

async function tagFile(id){{
  const tag=prompt('Enter tag:');
  if(!tag)return;
  await fetch('/api/tag?id='+id+'&tag='+encodeURIComponent(tag));
}}

// Bills
function toggleAddBill(){{const el=document.getElementById('bill-form');el.style.display=el.style.display==='none'?'block':'none';}}
async function saveBill(){{
  const b={{name:document.getElementById('bN').value.trim(),
    category:document.getElementById('bC').value,
    amount:parseFloat(document.getElementById('bA').value)||0,
    due_day:parseInt(document.getElementById('bD').value)||1,
    frequency:document.getElementById('bF').value,
    account:document.getElementById('bAc').value}};
  if(!b.name){{alert('Name required');return;}}
  await fetch('/api/add_bill',{{method:'POST',headers:{{'Content-Type':'application/json'}},body:JSON.stringify(b)}});
  toggleAddBill();loadBills();
}}
async function payBill(id,name){{
  const amt=prompt('Amount paid for '+name+' (Rs):');
  if(!amt)return;
  await fetch('/api/pay_bill',{{method:'POST',headers:{{'Content-Type':'application/json'}},
    body:JSON.stringify({{id,amount:parseFloat(amt)||0,mode:'UPI'}})}});
  loadBills();
}}
async function delBill(id){{if(!confirm('Delete?'))return;await fetch('/api/del_bill?id='+id,{{method:'DELETE'}});loadBills();}}
async function loadBills(){{
  const data=await fetch('/api/bills').then(r=>r.json());
  const bills=data.bills||[];
  const upcoming=data.upcoming||[];
  let html='';
  if(upcoming.length){{
    html+='<div class="alert-bar">Due soon: ';
    html+=upcoming.map(b=>b.name+' ('+b.due_day+')').join(', ');
    html+='</div>';
  }}
  const total=bills.reduce((s,b)=>s+(b.amount||0),0);
  html+='<div class="sg" style="margin-bottom:12px">'+
    '<div class="sc"><div class="sn">Rs '+total.toLocaleString('en-IN')+'</div><div class="sl">Monthly Total</div></div>'+
    '<div class="sc"><div class="sn">'+bills.filter(b=>b.status==='paid').length+'</div><div class="sl">Paid</div></div>'+
    '<div class="sc"><div class="sn">'+bills.filter(b=>b.status!=='paid').length+'</div><div class="sl">Pending</div></div></div>';
  bills.forEach(b=>{{
    html+='<div class="bill-card">'+
      '<div style="flex:1"><div class="bill-name">'+b.name+'</div>'+
      '<div class="bill-meta">Day '+b.due_day+' · '+b.frequency+(b.account?' · '+b.account:'')+'</div></div>'+
      '<div style="text-align:right;margin-right:8px">'+
      '<div style="font-size:14px;font-weight:700">Rs '+(b.amount||0).toLocaleString('en-IN')+'</div>'+
      '<span class="'+(b.status==='paid'?'bpaid':'bpending')+'">'+b.status+'</span></div>'+
      (b.status!=='paid'?'<button class="fb open" style="background:#7c6fdf;border-color:#7c6fdf;color:white" onclick="payBill('+b.id+',\\''+b.name.replace(/'/g,"\\\\'")+'\')">Pay</button>':'')+
      '<button class="fb" onclick="delBill('+b.id+')" style="margin-left:4px">Del</button></div>';
  }});
  document.getElementById('bill-list').innerHTML=html||'<div class="empty"><h3>No bills yet</h3><p>Add your monthly bills to track and get due date alerts.</p></div>';
}}

// Expiry
async function saveExpiry(){{
  const b={{doc_name:document.getElementById('eN').value.trim(),
    doc_type:document.getElementById('eT').value,
    expiry_date:document.getElementById('eD').value,
    notes:document.getElementById('eNo').value}};
  if(!b.doc_name||!b.expiry_date){{alert('Name and date required');return;}}
  await fetch('/api/add_expiry',{{method:'POST',headers:{{'Content-Type':'application/json'}},body:JSON.stringify(b)}});
  loadExpiry();
}}
async function delExpiry(id){{await fetch('/api/del_expiry?id='+id,{{method:'DELETE'}});loadExpiry();}}
async function loadExpiry(){{
  const data=await fetch('/api/expiry').then(r=>r.json());
  const items=data.all||[];
  const today=new Date().toISOString().slice(0,10);
  document.getElementById('exp-list').innerHTML=items.map(e=>{{
    const diff=Math.ceil((new Date(e.expiry_date)-new Date())/86400000);
    const col=diff<0?'#e05555':diff<=30?'#f0a020':'#4dd9a0';
    const lbl=diff<0?'Expired '+Math.abs(diff)+'d ago':diff===0?'Today':diff+' days left';
    return '<div class="exp-card">'+
      '<div><div style="font-size:13px;font-weight:600">'+e.doc_name+'</div>'+
      '<div style="font-size:11px;color:#8885a0;margin-top:2px">'+(e.doc_type||'')+
      (e.notes?' — '+e.notes:'')+'</div></div>'+
      '<div style="text-align:right">'+
      '<div style="font-size:14px;font-weight:700;color:'+col+'">'+e.expiry_date+'</div>'+
      '<div style="font-size:10px;color:#8885a0;margin-top:2px">'+lbl+'</div>'+
      '<button class="fb" style="margin-top:4px" onclick="delExpiry('+e.id+')">Remove</button>'+
      '</div></div>';
  }}).join('')||'<div class="empty"><h3>No expiry dates</h3><p>Add insurance, passport, RC renewal dates.</p></div>';
}}

// Vault
async function saveCred(){{
  const b={{label:document.getElementById('cL').value.trim(),
    category:document.getElementById('cC').value,
    username:document.getElementById('cU').value,
    password:document.getElementById('cP').value,
    url:document.getElementById('cW').value,
    notes:document.getElementById('cNo').value}};
  if(!b.label){{alert('Label required');return;}}
  await fetch('/api/save_cred',{{method:'POST',headers:{{'Content-Type':'application/json'}},body:JSON.stringify(b)}});
  loadVault();
}}
async function delCred(id){{if(!confirm('Delete?'))return;await fetch('/api/del_cred?id='+id,{{method:'DELETE'}});loadVault();}}
function showPw(id,pw){{const el=document.getElementById('pw'+id);el.textContent=el.textContent==='Show'?pw:'Show';}}
async function loadVault(){{
  const data=await fetch('/api/credentials').then(r=>r.json());
  const creds=data.credentials||[];
  if(!creds.length){{document.getElementById('vault-list').innerHTML='<div class="empty"><h3>Vault empty</h3><p>Save your email IDs, bank logins, government portal passwords.</p></div>';return;}}
  const grouped={{}};
  creds.forEach(c=>{{(grouped[c.category]=grouped[c.category]||[]).push(c);}});
  let html='';
  for(const[cat,items] of Object.entries(grouped)){{
    html+='<div style="font-size:10px;font-weight:600;color:#8885a0;text-transform:uppercase;letter-spacing:.5px;margin:10px 0 5px">'+cat+'</div>';
    items.forEach(c=>{{
      html+='<div class="cred-card">'+
        '<div><div style="font-size:13px;font-weight:600">'+c.label+'</div>'+
        '<div style="font-size:11px;color:#8885a0;margin-top:2px">'+c.username+(c.url?' · '+c.url:'')+'</div>'+
        (c.notes?'<div style="font-size:10px;color:#8885a0;margin-top:2px">'+c.notes+'</div>':'')+
        '</div><div style="display:flex;gap:5px;align-items:center">'+
        '<span id="pw'+c.id+'" onclick="showPw('+c.id+',\\''+c.password.replace(/'/g,"\\\\'")+'\\')" style="font-size:11px;color:#8885a0;cursor:pointer;padding:3px 7px;border:1px solid #2e2e4a;border-radius:5px">Show</span>'+
        '<button class="fb" onclick="delCred('+c.id+')">Del</button></div></div>';
    }});
  }}
  document.getElementById('vault-list').innerHTML=html;
}}

// Stats
async function loadStats(){{
  const data=await fetch('/api/stats').then(r=>r.json());
  const s=data.stats;
  let html='<div class="sg">'+
    '<div class="sc"><div class="sn">'+(s.total||0)+'</div><div class="sl">Files</div></div>'+
    '<div class="sc"><div class="sn">'+Object.keys(s.by_type||{{}}).length+'</div><div class="sl">Types</div></div>'+
    '<div class="sc"><div class="sn">'+Object.keys(s.by_drive||{{}}).length+'</div><div class="sl">Sources</div></div></div>';
  html+='<div class="form-box"><div style="font-size:12px;font-weight:500;margin-bottom:10px">By type</div>';
  Object.entries(s.by_type||{{}}).sort((a,b)=>b[1]-a[1]).forEach(([t,c])=>{{
    const pct=Math.min(100,c/(s.total||1)*100*3);
    html+='<div style="display:flex;align-items:center;gap:8px;margin-bottom:6px;font-size:12px">'+
      '<span style="min-width:90px;color:#8885a0">'+t+'</span>'+
      '<div style="flex:1;height:4px;background:#2e2e4a;border-radius:2px">'+
      '<div style="width:'+pct+'%;height:100%;background:#7c6fdf;border-radius:2px"></div></div>'+
      '<span style="min-width:40px;text-align:right">'+c+'</span></div>';
  }});
  html+='</div>';
  document.getElementById('stats-cnt').innerHTML=html;
}}

// Tab control
function showTab(tab,btn){{
  ['search','bills','expiry','vault','stats'].forEach(t=>{{
    const el=document.getElementById('tab-'+t);
    if(el)el.style.display=t===tab?'block':'none';
  }});
  if(btn){{document.querySelectorAll('.tab').forEach(b=>b.classList.remove('active'));btn.classList.add('active');}}
  if(tab==='bills')loadBills();
  if(tab==='expiry')loadExpiry();
  if(tab==='vault')loadVault();
  if(tab==='stats')loadStats();
}}

async function logout(){{await fetch('/api/logout',{{method:'POST'}});window.location='/';}}

// Check expiry on load
async function init(){{
  const data=await fetch('/api/expiry').then(r=>r.json());
  const expiring=data.expiring||[];
  if(expiring.length){{
    document.getElementById('alert-area').innerHTML=
      '<div class="alert-bar">⚠ '+expiring.length+' document(s) expiring soon — '+
      '<span style="cursor:pointer;text-decoration:underline" onclick="showTab(\'expiry\',null)">View</span></div>';
  }}
}}
init();
</script></body></html>"""


# ── AUTH ROUTES ───────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
async def root(request: Request):
    user = get_user_from_session(request)
    if user:
        return RedirectResponse("/app")
    return HTMLResponse(LOGIN_PAGE)


@app.post("/api/signup")
async def signup(request: Request):
    d = await request.json()
    result = create_user(
        d.get("email",""), d.get("name",""), d.get("password","")
    )
    if result["ok"]:
        # Auto login after signup
        login_result = login_user(d.get("email",""), d.get("password",""))
        if login_result["ok"]:
            token = login_result["token"]
            SESSIONS[token] = {
                "user_id": login_result["user_id"],
                "name":    login_result["name"],
                "email":   login_result["email"],
                "expires": datetime.datetime.now() + datetime.timedelta(days=30),
            }
            resp = JSONResponse({"ok": True})
            resp.set_cookie("memora_token", token, max_age=2592000, httponly=True)
            return resp
    return JSONResponse(result)


@app.post("/api/login")
async def login(request: Request):
    d = await request.json()
    result = login_user(d.get("email",""), d.get("password",""))
    if not result["ok"]:
        return JSONResponse(result)
    token = result["token"]
    SESSIONS[token] = {
        "user_id": result["user_id"],
        "name":    result["name"],
        "email":   result["email"],
        "expires": datetime.datetime.now() + datetime.timedelta(days=30),
    }
    resp = JSONResponse({"ok": True})
    resp.set_cookie("memora_token", token, max_age=2592000, httponly=True)
    return resp


@app.post("/api/logout")
async def logout(request: Request):
    token = request.cookies.get("memora_token")
    if token and token in SESSIONS:
        del SESSIONS[token]
    resp = JSONResponse({"ok": True})
    resp.delete_cookie("memora_token")
    return resp


@app.get("/app", response_class=HTMLResponse)
async def app_page(request: Request):
    user = get_user_from_session(request)
    if not user:
        return RedirectResponse("/")
    return HTMLResponse(build_app_page(user))


# ── FILE ROUTES ───────────────────────────────────────────────

@app.post("/api/upload")
async def upload_files(request: Request, files: list[UploadFile] = File(...)):
    user = get_user_from_session(request)
    if not user:
        return JSONResponse({"ok": False, "error": "Not logged in"})

    user_id = user["user_id"]
    indexed = 0
    errors  = 0

    for file in files:
        try:
            suffix = Path(file.filename).suffix.lower()
            with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
                shutil.copyfileobj(file.file, tmp)
                tmp_path = tmp.name

            content = extract_text(tmp_path, suffix)
            os.unlink(tmp_path)

            size = file.size or 0
            cats = categorise_file(file.filename, content)

            record = {
                "path":       f"upload://{user_id}/{file.filename}",
                "filename":   file.filename,
                "ext":        suffix,
                "type":       "document" if suffix in [".pdf",".doc",".docx",".xls",".xlsx",".txt"] else
                              "image" if suffix in [".jpg",".jpeg",".png",".gif"] else
                              "video" if suffix in [".mp4",".mov",".avi"] else "other",
                "categories": cats,
                "size":       size,
                "size_hr":    f"{size//1024} KB" if size > 1024 else f"{size} B",
                "modified":   datetime.date.today().isoformat(),
                "drive":      "upload",
                "folder":     "Uploaded Files",
                "content":    content,
                "hash":       file.filename,
                "source":     "upload",
            }
            upsert_file(user_id, record)
            indexed += 1
        except Exception:
            errors += 1

    return JSONResponse({
        "ok": True,
        "message": f"{indexed} file(s) uploaded and indexed. Ready to search!"
    })


@app.get("/api/search")
async def api_search(request: Request, q: str = ""):
    user = get_user_from_session(request)
    if not user:
        return JSONResponse({"results": []})
    results = search_files(user["user_id"], q, limit=100)
    return JSONResponse({"results": results, "count": len(results)})


@app.get("/api/tag")
async def api_tag(request: Request, id: int = 0, tag: str = ""):
    user = get_user_from_session(request)
    if not user:
        return JSONResponse({"ok": False})
    increment_open(user["user_id"], id)
    return JSONResponse({"ok": True})


@app.get("/api/stats")
async def api_stats(request: Request):
    user = get_user_from_session(request)
    if not user:
        return JSONResponse({"stats": {}})
    return JSONResponse({"stats": get_stats(user["user_id"])})


# ── BILLS ROUTES ──────────────────────────────────────────────

@app.post("/api/add_bill")
async def api_add_bill(request: Request):
    user = get_user_from_session(request)
    if not user:
        return JSONResponse({"ok": False})
    d = await request.json()
    add_bill(user["user_id"], d["name"], d.get("category","Other"),
             d.get("amount",0), d.get("due_day",1),
             d.get("frequency","monthly"), 0,
             d.get("account",""), d.get("notes",""))
    return JSONResponse({"ok": True})


@app.get("/api/bills")
async def api_bills(request: Request):
    user = get_user_from_session(request)
    if not user:
        return JSONResponse({"bills": []})
    uid = user["user_id"]
    return JSONResponse({
        "bills":    get_bills(uid),
        "upcoming": get_upcoming_bills(uid, 7),
    })


@app.post("/api/pay_bill")
async def api_pay_bill(request: Request):
    user = get_user_from_session(request)
    if not user:
        return JSONResponse({"ok": False})
    d = await request.json()
    mark_paid(user["user_id"], d["id"], d.get("amount",0), d.get("mode","UPI"))
    return JSONResponse({"ok": True})


@app.delete("/api/del_bill")
async def api_del_bill(request: Request, id: int):
    user = get_user_from_session(request)
    if not user:
        return JSONResponse({"ok": False})
    delete_bill(user["user_id"], id)
    return JSONResponse({"ok": True})


# ── EXPIRY ROUTES ─────────────────────────────────────────────

@app.post("/api/add_expiry")
async def api_add_expiry(request: Request):
    user = get_user_from_session(request)
    if not user:
        return JSONResponse({"ok": False})
    d = await request.json()
    add_expiry(user["user_id"], d["doc_name"], d["expiry_date"],
               d.get("doc_type",""), d.get("notes",""))
    return JSONResponse({"ok": True})


@app.get("/api/expiry")
async def api_expiry(request: Request):
    user = get_user_from_session(request)
    if not user:
        return JSONResponse({"all": [], "expiring": []})
    uid = user["user_id"]
    return JSONResponse({
        "all":      get_expiry(uid),
        "expiring": get_expiring_soon(uid, 30),
    })


@app.delete("/api/del_expiry")
async def api_del_expiry(request: Request, id: int):
    user = get_user_from_session(request)
    if not user:
        return JSONResponse({"ok": False})
    delete_expiry(user["user_id"], id)
    return JSONResponse({"ok": True})


# ── VAULT ROUTES ──────────────────────────────────────────────

@app.post("/api/save_cred")
async def api_save_cred(request: Request):
    user = get_user_from_session(request)
    if not user:
        return JSONResponse({"ok": False})
    d = await request.json()
    save_credential(user["user_id"], d["label"], d.get("username",""),
                    d.get("password",""), d.get("category","other"),
                    d.get("url",""), d.get("notes",""))
    return JSONResponse({"ok": True})


@app.get("/api/credentials")
async def api_creds(request: Request):
    user = get_user_from_session(request)
    if not user:
        return JSONResponse({"credentials": []})
    return JSONResponse({"credentials": get_credentials(user["user_id"])})


@app.delete("/api/del_cred")
async def api_del_cred(request: Request, id: int):
    user = get_user_from_session(request)
    if not user:
        return JSONResponse({"ok": False})
    delete_credential(user["user_id"], id)
    return JSONResponse({"ok": True})


if __name__ == "__main__":
    print("\n  MemorA Cloud starting...")
    print(f"  Open browser: http://localhost:{PORT}")
    print("  Press Ctrl+C to stop\n")
    uvicorn.run(app, host="0.0.0.0", port=PORT, log_level="warning")
