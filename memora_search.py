"""
memora_search.py  v2
Location: F:\\AI_PROJECTS\\MemorA\\memora_search.py

Paginated results - fits screen. Press Enter to see more.
Better detection for PAN, Aadhaar, insurance, documents.
"""

import os
import json
import sys
import subprocess
from pathlib import Path
from dotenv import load_dotenv
from colorama import Fore, Style, init

load_dotenv(r"F:\AI_DEPLOY\Configs\Secrets\.env")
init(autoreset=True)

INDEX_FILE = r"F:\AI_DATA\MemorA\scan_index.json"
PAGE_SIZE  = 5   # results per screen

# ── SMART KEYWORD MAP ─────────────────────────────────────────
# When user types these short words, we expand the search
SMART_KEYWORDS = {
    "pan":        ["pan", "pan card", "pancard", "income tax", "nsdl", "pan no"],
    "aadhaar":    ["aadhaar", "aadhar", "adhar", "uid", "uidai", "biometric"],
    "insurance":  ["insurance", "policy", "insur", "mediclaim", "premium", "irda", "lic"],
    "car":        ["car", "vehicle", "rc book", "registration", "pollution", "puc", "rto"],
    "passport":   ["passport", "travel document", "visa", "immigration"],
    "bank":       ["bank", "account", "ifsc", "statement", "passbook", "cheque"],
    "property":   ["property", "flat", "house", "land", "deed", "registry", "sale deed"],
    "health":     ["health", "medical", "hospital", "prescription", "lab", "blood", "report"],
    "salary":     ["salary", "payslip", "payroll", "ctc", "offer letter", "appointment"],
    "tax":        ["tax", "itr", "form 16", "form16", "income tax", "tds", "gst"],
    "photo":      ["jpg", "jpeg", "png", "image", "photo", "picture", "selfie"],
    "video":      ["mp4", "mov", "avi", "video", "movie", "clip"],
    "certificate":["certificate", "certifi", "degree", "diploma", "marksheet", "transcript"],
}


def load_index():
    if not os.path.exists(INDEX_FILE):
        print(Fore.RED + "\n  No index found.")
        print(Fore.RED + "  Run RUN_MEMORA_SCAN.bat first.\n")
        return []
    with open(INDEX_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)
    return data.get("files", [])


def expand_query(query):
    """Expand short keywords into full search terms."""
    q = query.lower().strip()
    expanded = [q]
    for key, synonyms in SMART_KEYWORDS.items():
        if q == key or q in synonyms:
            expanded.extend(synonyms)
    return list(set(expanded))


def smart_search(query, files, max_results=50):
    terms = expand_query(query)
    scored = []

    for f in files:
        score = 0
        fname    = f.get("filename", "").lower()
        fpath    = f.get("path", "").lower()
        fcontent = f.get("content", "").lower()
        fcats    = " ".join(f.get("categories", [])).lower()
        ftype    = f.get("type", "").lower()
        fext     = f.get("ext", "").lower()

        search_blob = fname + " " + fpath + " " + fcontent + " " + fcats

        for term in terms:
            # Exact filename match — top score
            if term in fname:
                score += 100
            # In path
            if term in fpath:
                score += 40
            # In content (extracted text)
            if term in fcontent:
                score += 30
            # In categories
            if term in fcats:
                score += 20
            # Extension match
            if term in fext:
                score += 50

        # Boost personal document types
        if ftype in ["document", "image"] and score > 0:
            score += 10

        if score > 0:
            scored.append((score, f))

    scored.sort(key=lambda x: x[0], reverse=True)
    return [f for _, f in scored[:max_results]]


def print_result(f, index):
    """Print one result — compact, fits screen width."""
    fname    = f.get("filename", "")
    fpath    = f.get("path", "")
    ftype    = f.get("type", "other")
    fext     = f.get("ext", "")
    size     = f.get("size_hr", "")
    modified = f.get("modified", "")[:10]
    cats     = ", ".join(f.get("categories", ["uncategorised"]))
    preview  = f.get("content", "").replace("\n", " ").strip()[:120]

    print(Fore.YELLOW + f"\n  [{index}]  " + Fore.WHITE + Style.BRIGHT + fname)
    # Trim path to fit screen
    short_path = fpath if len(fpath) <= 70 else "..." + fpath[-67:]
    print(Fore.CYAN  + "       " + short_path)
    print(Fore.WHITE + f"       {ftype} {fext}  |  {size}  |  {modified}  |  {cats}")
    if preview:
        print(Fore.WHITE + "       " + Fore.WHITE + preview[:100] + ("..." if len(preview) >= 100 else ""))


def paginate(results, query):
    """Show results PAGE_SIZE at a time. Press Enter for more."""
    total = len(results)
    page  = 0

    while True:
        start = page * PAGE_SIZE
        end   = start + PAGE_SIZE
        chunk = results[start:end]

        if not chunk:
            break

        print(Fore.CYAN + "\n  " + "=" * 50)
        print(Fore.GREEN + f"  Results {start+1}-{min(end,total)} of {total}  |  query: '{query}'")
        print(Fore.CYAN + "  " + "=" * 50)

        for i, f in enumerate(chunk, start + 1):
            print_result(f, i)

        # Bottom controls
        print(Fore.CYAN + "\n  " + "-" * 50)
        if end < total:
            remaining = total - end
            print(Fore.WHITE + f"  [Enter]  next {min(PAGE_SIZE, remaining)} results")
        print(Fore.WHITE +  "  [number] open file    [f+number] open folder")
        print(Fore.WHITE +  "  [q]      back to search")
        print(Fore.CYAN + "  " + "-" * 50)

        choice = input(Fore.YELLOW + "\n  > ").strip().lower()

        if choice == "q" or choice == "":
            if choice == "q":
                return results  # back to search
            # Empty = next page
            if end < total:
                page += 1
            else:
                print(Fore.GREEN + "  End of results.")
                input(Fore.WHITE + "  Press Enter to search again...")
                return results

        elif choice.startswith("f"):
            try:
                idx = int(choice[1:]) - 1
                if 0 <= idx < total:
                    open_folder(results[idx]["path"])
            except Exception:
                pass

        else:
            try:
                n = int(choice)
                if 1 <= n <= total:
                    open_file(results[n-1]["path"])
            except Exception:
                pass

    return results


def open_file(filepath):
    try:
        if sys.platform == "win32":
            os.startfile(filepath)
        print(Fore.GREEN + "\n  Opening: " + filepath)
    except Exception as e:
        print(Fore.RED + "  Error: " + str(e))
        print(Fore.WHITE + "  File path: " + filepath)


def open_folder(filepath):
    try:
        folder = str(Path(filepath).parent)
        subprocess.Popen('explorer "' + folder + '"')
        print(Fore.GREEN + "\n  Opening folder: " + folder)
    except Exception as e:
        print(Fore.RED + "  Error: " + str(e))


def show_stats(files):
    total = len(files)
    by_type  = {}
    by_drive = {}
    by_cat   = {}

    for f in files:
        t = f.get("type", "other")
        by_type[t] = by_type.get(t, 0) + 1
        d = f.get("drive", "?")
        by_drive[d] = by_drive.get(d, 0) + 1
        for c in f.get("categories", ["uncategorised"]):
            by_cat[c] = by_cat.get(c, 0) + 1

    print(Fore.CYAN + "\n  " + "=" * 50)
    print(Fore.GREEN + f"  Total files indexed: {total:,}")
    print(Fore.CYAN + "\n  By drive:")
    for d, c in sorted(by_drive.items()):
        bar = "#" * min(30, c // 50)
        print(Fore.WHITE + f"    {d}  {bar}  {c:,}")
    print(Fore.CYAN + "\n  By file type:")
    for t, c in sorted(by_type.items(), key=lambda x: -x[1])[:8]:
        print(Fore.WHITE + "    " + t.ljust(14) + str(c))
    print(Fore.CYAN + "\n  Top categories found:")
    for cat, c in sorted(by_cat.items(), key=lambda x: -x[1])[:12]:
        print(Fore.WHITE + "    " + cat.ljust(20) + str(c))
    print(Fore.CYAN + "  " + "=" * 50)


def print_header(total, last_scan):
    print(Fore.CYAN + Style.BRIGHT + """
  +------------------------------------------+
  |   MemorA  -  Find Anything               |
  |   All your files. One search. Instant.   |
  +------------------------------------------+""")
    print(Fore.GREEN + f"\n  {total:,} files indexed   last scan: {last_scan}")
    print(Fore.WHITE + "\n  Type anything to search. Examples:")
    print(Fore.WHITE + "    PAN       aadhaar    insurance    car")
    print(Fore.WHITE + "    photo     salary     certificate  bank")
    print(Fore.WHITE + "    or type any filename, word, or phrase")
    print(Fore.WHITE + "\n  Commands:")
    print(Fore.WHITE + "    stats  -  see full breakdown of indexed files")
    print(Fore.WHITE + "    quit   -  exit MemorA")
    print(Fore.CYAN  + "\n  " + "-" * 50)


def main():
    files = load_index()
    if not files:
        return

    total     = len(files)
    last_scan = "unknown"
    try:
        with open(INDEX_FILE, "r") as f:
            meta = json.load(f)
            last_scan = meta.get("last_updated", "")[:16]
    except Exception:
        pass

    print_header(total, last_scan)

    while True:
        try:
            query = input(Fore.YELLOW + "\n  Search: ").strip()
        except (KeyboardInterrupt, EOFError):
            break

        if not query:
            continue

        if query.lower() == "quit":
            print(Fore.CYAN + "\n  Goodbye.\n")
            break

        if query.lower() == "stats":
            show_stats(files)
            continue

        print(Fore.WHITE + f"\n  Searching {total:,} files...")
        results = smart_search(query, files)

        if not results:
            print(Fore.RED + f"\n  Nothing found for '{query}'")
            print(Fore.WHITE + "  Tips:")
            print(Fore.WHITE + "    - Try a shorter word  e.g. 'pan' not 'pan card image'")
            print(Fore.WHITE + "    - Try the file extension  e.g. 'pdf' or 'jpg'")
            print(Fore.WHITE + "    - Run scan again if file was added recently")
            continue

        print(Fore.GREEN + f"  Found {len(results)} result(s) for '{query}'")
        paginate(results, query)


if __name__ == "__main__":
    main()
