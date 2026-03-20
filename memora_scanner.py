"""
memora_scanner.py  v2
Location: F:\\AI_PROJECTS\\MemorA\\memora_scanner.py

Scans D, E, F, G drives. Pure ASCII output - no encoding issues.
Reads PDFs, Word, Excel, images. Smart auto-categorisation.
Saves index to F:\\AI_DATA\\MemorA\\scan_index.json
"""

import os
import json
import datetime
import hashlib
from pathlib import Path

DRIVES_TO_SCAN = ["D:\\", "E:\\", "F:\\", "G:\\"]
OUTPUT_PATH    = r"F:\AI_DATA\MemorA"
INDEX_FILE     = r"F:\AI_DATA\MemorA\scan_index.json"

SKIP_FOLDERS = {
    "windows", "program files", "program files (x86)",
    "programdata", "appdata", "$recycle.bin",
    "system volume information", "node_modules", ".git",
    "__pycache__", ".venv", "venv", "agent_env",
    "site-packages", "dist-info", "temp", "tmp",
    "$windows.~bt", "recovery"
}

FILE_TYPES = {
    "document":     [".pdf", ".doc", ".docx", ".txt", ".rtf", ".odt"],
    "spreadsheet":  [".xls", ".xlsx", ".csv", ".ods"],
    "presentation": [".ppt", ".pptx", ".odp"],
    "image":        [".jpg", ".jpeg", ".png", ".gif", ".bmp", ".tiff", ".webp", ".heic"],
    "video":        [".mp4", ".mov", ".avi", ".mkv", ".wmv", ".flv", ".m4v", ".3gp"],
    "audio":        [".mp3", ".wav", ".aac", ".flac", ".m4a", ".ogg"],
    "archive":      [".zip", ".rar", ".7z", ".tar", ".gz"],
    "software":     [".exe", ".msi", ".dmg", ".apk", ".iso"],
    "data":         [".json", ".xml", ".yaml", ".yml", ".sql", ".db", ".sqlite"],
    "code":         [".py", ".js", ".html", ".css", ".java", ".cpp", ".cs", ".php"],
    "email":        [".eml", ".msg", ".pst"],
}

CATEGORIES = {
    "identity":    ["aadhaar", "aadhar", "pan", "passport", "voter", "driving", "licence", "uid"],
    "insurance":   ["insurance", "policy", "premium", "claim", "mediclaim", "lic", "irda"],
    "finance":     ["bank", "statement", "invoice", "receipt", "salary", "tax", "itr", "form16"],
    "property":    ["property", "deed", "flat", "house", "land", "registry", "agreement", "rent"],
    "vehicle":     ["vehicle", "car", "bike", "rc", "pollution", "puc", "challan", "service"],
    "health":      ["health", "medical", "prescription", "report", "hospital", "doctor", "lab"],
    "education":   ["certificate", "degree", "marksheet", "transcript", "college", "school"],
    "work":        ["offer letter", "appointment", "salary", "payslip", "experience", "joining"],
    "legal":       ["agreement", "contract", "affidavit", "notary", "legal", "court"],
    "family":      ["family", "birth", "death", "marriage", "wedding"],
    "travel":      ["ticket", "boarding", "hotel", "booking", "visa", "travel"],
    "software":    ["setup", "install", "software", "application"],
    "media":       ["photo", "video", "image", "picture", "album"],
}

MAX_EXTRACT_SIZE = 50 * 1024 * 1024


def get_file_type(ext):
    ext = ext.lower()
    for ftype, exts in FILE_TYPES.items():
        if ext in exts:
            return ftype
    return "other"


def auto_categorise(filepath):
    text = filepath.lower()
    matched = []
    for cat, keywords in CATEGORIES.items():
        for kw in keywords:
            if kw in text:
                matched.append(cat)
                break
    return matched if matched else ["uncategorised"]


def file_hash(filepath):
    try:
        h = hashlib.md5()
        with open(filepath, "rb") as f:
            h.update(f.read(8192))
        return h.hexdigest()[:12]
    except Exception:
        return "unknown"


def extract_text_pdf(filepath):
    try:
        import pdfplumber
        parts = []
        with pdfplumber.open(filepath) as pdf:
            for page in pdf.pages[:5]:
                t = page.extract_text()
                if t:
                    parts.append(t[:500])
        return " ".join(parts)[:2000]
    except Exception:
        return ""


def extract_text_docx(filepath):
    try:
        import docx
        doc = docx.Document(filepath)
        text = " ".join([p.text for p in doc.paragraphs[:20]])
        return text[:2000]
    except Exception:
        return ""


def extract_text_xlsx(filepath):
    try:
        import openpyxl
        import warnings
        warnings.filterwarnings("ignore")
        wb = openpyxl.load_workbook(filepath, read_only=True, data_only=True)
        ws = wb.active
        values = []
        for row in list(ws.iter_rows(values_only=True))[:10]:
            for cell in row:
                if cell:
                    values.append(str(cell))
        return " ".join(values)[:1000]
    except Exception:
        return ""


def extract_text_txt(filepath):
    try:
        with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
            return f.read(2000)
    except Exception:
        return ""


def extract_image_meta(filepath):
    try:
        import warnings
        warnings.filterwarnings("ignore")
        from PIL import Image
        img = Image.open(filepath)
        return str(img.format) + " " + str(img.size[0]) + "x" + str(img.size[1]) + "px"
    except Exception:
        return ""


def extract_content(filepath, file_type, ext, size):
    if size > MAX_EXTRACT_SIZE:
        return ""
    try:
        if ext == ".pdf":
            return extract_text_pdf(filepath)
        elif ext in [".docx", ".doc"]:
            return extract_text_docx(filepath)
        elif ext in [".xlsx", ".xls"]:
            return extract_text_xlsx(filepath)
        elif ext in [".txt", ".csv", ".rtf"]:
            return extract_text_txt(filepath)
        elif file_type == "image":
            return extract_image_meta(filepath)
    except Exception:
        pass
    return ""


def should_skip(folder_name):
    return folder_name.lower() in SKIP_FOLDERS


def save_index(results):
    os.makedirs(OUTPUT_PATH, exist_ok=True)
    data = {
        "last_updated": datetime.datetime.now().isoformat(),
        "total_files":  len(results),
        "files":        results
    }
    with open(INDEX_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def scan_drives():
    os.makedirs(OUTPUT_PATH, exist_ok=True)

    # Load existing cache
    existing = {}
    if os.path.exists(INDEX_FILE):
        try:
            with open(INDEX_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            existing = {item["path"]: item for item in data.get("files", [])}
            print("  Loaded " + str(len(existing)) + " cached records - scanning for changes only")
        except Exception:
            existing = {}

    results   = []
    skipped   = 0
    new_files = 0
    errors    = 0

    print("")
    print("  Scanning drives: " + ", ".join(DRIVES_TO_SCAN))
    print("  This may take 30-60 minutes for 50,000+ files.")
    print("  You can use your PC normally while this runs.")
    print("")

    for drive in DRIVES_TO_SCAN:
        if not os.path.exists(drive):
            print("  Skipping " + drive + " - not found")
            continue

        print("  Scanning " + drive + "...")
        file_count = 0

        for root, dirs, files in os.walk(drive):
            dirs[:] = [d for d in dirs if not should_skip(d)]

            for filename in files:
                try:
                    filepath = os.path.join(root, filename)
                    ext      = Path(filename).suffix.lower()
                    stat     = os.stat(filepath)
                    size     = stat.st_size
                    modified = datetime.datetime.fromtimestamp(stat.st_mtime).isoformat()
                    ftype    = get_file_type(ext)
                    cats     = auto_categorise(filepath)

                    # Use cache if unchanged
                    if filepath in existing:
                        old = existing[filepath]
                        if old.get("modified") == modified and old.get("size") == size:
                            results.append(old)
                            skipped += 1
                            continue

                    content = extract_content(filepath, ftype, ext, size)

                    if size < 1048576:
                        size_hr = str(round(size / 1024, 1)) + " KB"
                    else:
                        size_hr = str(round(size / 1048576, 1)) + " MB"

                    record = {
                        "path":       filepath,
                        "filename":   filename,
                        "ext":        ext,
                        "type":       ftype,
                        "categories": cats,
                        "size":       size,
                        "size_hr":    size_hr,
                        "modified":   modified,
                        "drive":      drive,
                        "folder":     root,
                        "content":    content,
                        "hash":       file_hash(filepath),
                        "indexed_at": datetime.datetime.now().isoformat()
                    }

                    results.append(record)
                    new_files  += 1
                    file_count += 1

                    if file_count % 500 == 0:
                        print("    " + drive + " " + str(file_count) + " files scanned...")
                        save_index(results)

                except Exception:
                    errors += 1

        print("  " + drive + " done - " + str(file_count) + " new/changed files")
        print("")

    save_index(results)

    print("  ================================================")
    print("  SCAN COMPLETE")
    print("  Total files indexed : " + str(len(results)))
    print("  New / updated       : " + str(new_files))
    print("  Unchanged (cached)  : " + str(skipped))
    print("  Errors skipped      : " + str(errors))
    print("  Index saved to      : " + INDEX_FILE)
    print("  ================================================")
    print("")
    return results


if __name__ == "__main__":
    scan_drives()
