#!/usr/bin/env python3
"""Trainer Central -> Dashboard automation.
Drive (.txt files) -> Claude analysis -> POST /api/entries. Run on a schedule."""
import io, json, logging, os, re, sqlite3, sys, time
from datetime import datetime, timezone
from logging.handlers import RotatingFileHandler
from pathlib import Path

import requests
from anthropic import Anthropic
from dotenv import load_dotenv
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload

BASE = Path(__file__).resolve().parent
load_dotenv(BASE / ".env")

SCOPES = ["https://www.googleapis.com/auth/drive.readonly"]
FOLDER_ID = os.getenv("DRIVE_FOLDER_ID", "")
MY_NAME = os.getenv("MY_NAME", "upendarduggineni")
MY_EMAIL = os.getenv("MY_EMAIL", "upendarduggineni24@gmail.com")
API_BASE = os.getenv("API_BASE", "https://trainer-central-assigments-api.onrender.com").rstrip("/")
DASH_KEY = os.getenv("DASHBOARD_API_KEY", "")
MODEL = os.getenv("CLAUDE_MODEL", "claude-sonnet-5-5")
TIMEOUT = 90          # Render free tier can take ~1 min to wake
MAX_CHARS = 20000     # max email text sent to Claude

(BASE / "logs").mkdir(exist_ok=True)
log = logging.getLogger("tc")
log.setLevel(logging.INFO)
_fmt = logging.Formatter("%(asctime)s %(levelname)s %(message)s")
for h in (RotatingFileHandler(BASE / "logs" / "run.log", maxBytes=1_000_000, backupCount=5),
          logging.StreamHandler()):
    h.setFormatter(_fmt)
    log.addHandler(h)


# ---------- state (duplicate prevention) ----------
def db():
    con = sqlite3.connect(BASE / "state.db")
    con.execute("""CREATE TABLE IF NOT EXISTS processed(
        file_id TEXT PRIMARY KEY, name TEXT, outcome TEXT, entry_id TEXT, at TEXT)""")
    return con


def mark(con, fid, name, outcome, entry_id=None):
    con.execute("INSERT OR REPLACE INTO processed VALUES(?,?,?,?,?)",
                (fid, name, outcome, str(entry_id) if entry_id else None,
                 datetime.now(timezone.utc).isoformat()))
    con.commit()


# ---------- Google Drive ----------
def authorise():
    flow = InstalledAppFlow.from_client_secrets_file(str(BASE / "credentials.json"), SCOPES)
    creds = flow.run_local_server(port=0)
    (BASE / "token.json").write_text(creds.to_json())
    print("Drive authorised. token.json saved.")


def drive_service():
    tok = BASE / "token.json"
    if not tok.exists():
        raise RuntimeError("token.json missing - run `python app.py --auth` once")
    creds = Credentials.from_authorized_user_file(str(tok), SCOPES)
    if not creds.valid:
        creds.refresh(Request())
        tok.write_text(creds.to_json())
    return build("drive", "v3", credentials=creds, cache_discovery=False)


def with_retry(fn, what, tries=3):
    for i in range(1, tries + 1):
        try:
            return fn()
        except Exception as e:
            log.warning("%s failed (attempt %d/%d): %s", what, i, tries, e)
            if i == tries:
                raise
            time.sleep(2 * i)


def list_txt_files(svc):
    files, token = [], None
    q = f"'{FOLDER_ID}' in parents and trashed=false and name contains '.txt'"
    while True:
        r = with_retry(lambda: svc.files().list(
            q=q, fields="nextPageToken, files(id,name,mimeType,modifiedTime)",
            pageSize=200, pageToken=token, orderBy="modifiedTime desc").execute(),
            "Drive list")
        files += [f for f in r.get("files", []) if f["name"].lower().endswith(".txt")]
        token = r.get("nextPageToken")
        if not token:
            return files


def read_file(svc, fid):
    def go():
        buf = io.BytesIO()
        dl = MediaIoBaseDownload(buf, svc.files().get_media(fileId=fid))
        done = False
        while not done:
            _, done = dl.next_chunk()
        return buf.getvalue().decode("utf-8", errors="replace")
    return with_retry(go, f"Drive read {fid}")


# ---------- Claude analysis ----------
def analyze(client, fname, text):
    system = (BASE / "prompt.txt").read_text().replace("{MY_NAME}", MY_NAME).replace("{MY_EMAIL}", MY_EMAIL)

    def go():
        msg = client.messages.create(
            model=MODEL, max_tokens=800, system=system,
            messages=[{"role": "user",
                       "content": f"File name: {fname}\n\n<email>\n{text[:MAX_CHARS]}\n</email>"}])
        raw = "".join(b.text for b in msg.content if b.type == "text")
        m = re.search(r"\{.*\}", raw, re.S)
        if not m:
            raise ValueError("no JSON in Claude reply")
        d = json.loads(m.group(0))
        if not isinstance(d.get("is_mine"), bool):
            raise ValueError("is_mine missing or not boolean")
        return d
    return with_retry(go, f"Claude analysis {fname}")


def build_text(d, fid, fname):
    parts = [f"Assignment: {d.get('assignment_name') or 'Unknown'}",
             f"Submitted: {d.get('submission_time') or 'Unknown'}",
             f"Status: {d.get('status') or 'Unknown'}"]
    if d.get("other_details"):
        parts.append(f"Details: {d['other_details']}")
    parts.append(f"[drive-file:{fid}] {fname}")   # marker used for remote duplicate check
    return "\n".join(parts)[:10000]


# ---------- Dashboard API ----------
def hdrs():
    h = {"Content-Type": "application/json"}
    if DASH_KEY:
        h["x-api-key"] = DASH_KEY
    return h


def wake_api():
    for i in range(1, 4):
        try:
            r = requests.get(f"{API_BASE}/health", timeout=TIMEOUT)
            log.info("API health: %s", r.status_code)
            if r.ok:
                return True
        except requests.RequestException as e:
            log.warning("health attempt %d failed: %s", i, e)
        time.sleep(5)
    return False


def remote_blob():
    try:
        r = requests.get(f"{API_BASE}/api/entries", headers=hdrs(), timeout=TIMEOUT)
        r.raise_for_status()
        return json.dumps(r.json())
    except Exception as e:
        log.warning("could not read existing entries (local DB still prevents duplicates): %s", e)
        return ""


def push(text):
    """POST with retries. Returns (ok, entry_id_or_error)."""
    payload = {"text": text, "sender": MY_NAME}
    for i in range(1, 4):
        try:
            r = requests.post(f"{API_BASE}/api/entries", json=payload, headers=hdrs(), timeout=TIMEOUT)
            if r.status_code in (200, 201):
                body = r.json() if r.content else {}
                eid = body.get("id") or body.get("entry_id") if isinstance(body, dict) else None
                log.info("POST ok: %s id=%s", r.status_code, eid)
                return True, eid
            log.error("POST %s: %s", r.status_code, r.text[:300])
            if r.status_code < 500 and r.status_code != 429:
                return False, f"HTTP {r.status_code}"   # bad payload/auth: retrying won't help
        except requests.RequestException as e:
            log.warning("POST attempt %d failed: %s", i, e)
        time.sleep(5 * i)
    return False, "retries exhausted"


# ---------- main run ----------
def run():
    stats = dict(seen=0, new=0, matched=0, pushed=0, skipped=0, errors=0)
    log.info("===== run start =====")
    if not FOLDER_ID or not os.getenv("ANTHROPIC_API_KEY"):
        log.error("DRIVE_FOLDER_ID or ANTHROPIC_API_KEY not set")
        return 1
    con = db()
    try:
        svc = drive_service()
        files = list_txt_files(svc)
    except Exception as e:
        log.error("Drive unreachable: %s", e)
        return 1
    stats["seen"] = len(files)
    done = {r[0] for r in con.execute("SELECT file_id FROM processed")}
    todo = [f for f in files if f["id"] not in done]
    stats["new"] = len(todo)
    log.info("files seen=%d, new=%d", len(files), len(todo))

    client = Anthropic()
    api_ready, blob = None, None
    for f in todo:
        fid, name = f["id"], f["name"]
        try:
            text = read_file(svc, fid)
            if not text.strip():
                log.info("%s: empty, skipped", name); mark(con, fid, name, "empty"); stats["skipped"] += 1
                continue
            d = analyze(client, name, text)
            if not d["is_mine"]:
                log.info("%s: not mine (%s)", name, d.get("reason")); mark(con, fid, name, "not_mine")
                stats["skipped"] += 1
                continue
            stats["matched"] += 1
            log.info("%s: MATCH (%s)", name, d.get("assignment_name"))
            if api_ready is None:
                api_ready = wake_api()
                blob = remote_blob() if api_ready else ""
            if not api_ready:
                log.error("API unreachable; %s will be retried next run", name); stats["errors"] += 1
                continue
            if f"[drive-file:{fid}]" in (blob or ""):
                log.info("%s: already on dashboard, not re-posting", name); mark(con, fid, name, "pushed")
                continue
            ok, res = push(build_text(d, fid, name))
            if ok:
                mark(con, fid, name, "pushed", res); stats["pushed"] += 1
            else:
                stats["errors"] += 1   # not marked -> retried next run
        except Exception as e:
            log.exception("error on %s: %s", name, e)
            stats["errors"] += 1
    log.info("run summary: %s", stats)
    log.info("===== run end =====")
    return 0


if __name__ == "__main__":
    if "--auth" in sys.argv:
        authorise()
    else:
        sys.exit(run())
