"""
watch_gmail.py — Gmail Watcher Agent Skill

Monitors a Gmail inbox via IMAP for new unread emails.
For each new email, creates a .md task file in Inbox/ so the
vault-watcher or scheduler can pick it up.

Requires environment variables:
  EMAIL_ADDRESS    — Gmail address
  EMAIL_PASSWORD   — Gmail App Password

Usage:
    python watch_gmail.py --once           # single check
    python watch_gmail.py --daemon         # continuous poll
    python watch_gmail.py --daemon --interval 120
"""

import argparse
import email
import email.header
import email.utils
import imaplib
import json
import os
import re
import signal
import sys
import time
from datetime import datetime, timezone

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
VAULT_ROOT = os.path.abspath(os.path.join(SCRIPT_DIR, "..", "..", "..", ".."))

INBOX_DIR = os.path.join(VAULT_ROOT, "Inbox")
LOGS_DIR = os.path.join(VAULT_ROOT, "Logs")
ACTIONS_LOG = os.path.join(LOGS_DIR, "actions.log")
STATE_FILE = os.path.join(LOGS_DIR, ".gmail_watcher_state.json")

IMAP_HOST = "imap.gmail.com"
IMAP_PORT = 993
DEFAULT_INTERVAL = 60

_shutdown = False


def _sig(s, f):
    global _shutdown
    _shutdown = True


def _now():
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")


def log(msg):
    entry = f"[{_now()}] [gmail-watcher] {msg}"
    print(entry)
    try:
        os.makedirs(LOGS_DIR, exist_ok=True)
        with open(ACTIONS_LOG, "a", encoding="utf-8") as f:
            f.write(entry + "\n")
    except OSError:
        pass


def load_state():
    if not os.path.isfile(STATE_FILE):
        return {"seen_ids": []}
    try:
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return {"seen_ids": []}


def save_state(state):
    os.makedirs(LOGS_DIR, exist_ok=True)
    # Keep only last 500 message IDs to prevent unbounded growth.
    state["seen_ids"] = state["seen_ids"][-500:]
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2)


def decode_header_value(raw):
    """Decode a potentially encoded email header."""
    if not raw:
        return ""
    parts = email.header.decode_header(raw)
    decoded = []
    for data, charset in parts:
        if isinstance(data, bytes):
            decoded.append(data.decode(charset or "utf-8", errors="replace"))
        else:
            decoded.append(data)
    return " ".join(decoded)


def safe_filename(text, max_len=50):
    """Convert text to a filesystem-safe filename."""
    text = re.sub(r"[^\w\s\-]", "", text)
    text = re.sub(r"\s+", "_", text.strip())
    return text[:max_len] if text else "untitled"


def get_body(msg):
    """Extract plain-text body from an email message."""
    if msg.is_multipart():
        for part in msg.walk():
            ct = part.get_content_type()
            if ct == "text/plain" and "attachment" not in str(part.get("Content-Disposition", "")):
                payload = part.get_payload(decode=True)
                if payload:
                    charset = part.get_content_charset() or "utf-8"
                    return payload.decode(charset, errors="replace")
    else:
        payload = msg.get_payload(decode=True)
        if payload:
            charset = msg.get_content_charset() or "utf-8"
            return payload.decode(charset, errors="replace")
    return "(no plain-text body)"


def fetch_new_emails():
    """
    Connect to Gmail IMAP, fetch UNSEEN emails, create task files.
    Returns count of new emails processed.
    """
    addr = os.environ.get("EMAIL_ADDRESS", "").strip()
    pw = os.environ.get("EMAIL_PASSWORD", "").strip()

    if not addr:
        log("[ERROR] EMAIL_ADDRESS not set.")
        return -1
    if not pw:
        log("[ERROR] EMAIL_PASSWORD not set.")
        return -1

    state = load_state()
    os.makedirs(INBOX_DIR, exist_ok=True)

    try:
        mail = imaplib.IMAP4_SSL(IMAP_HOST, IMAP_PORT)
        mail.login(addr, pw)
    except imaplib.IMAP4.error as e:
        log(f"[ERROR] IMAP login failed: {e}")
        return -1
    except OSError as e:
        log(f"[ERROR] Connection failed: {e}")
        return -1

    try:
        mail.select("INBOX")
        status, data = mail.search(None, "UNSEEN")
        if status != "OK":
            log("[ERROR] IMAP search failed.")
            return 0

        msg_ids = data[0].split()
        if not msg_ids:
            log("No new emails.")
            return 0

        created = 0
        for msg_id in msg_ids:
            msg_id_str = msg_id.decode()

            # Skip if already processed (safety net beyond UNSEEN flag).
            if msg_id_str in state["seen_ids"]:
                continue

            status, msg_data = mail.fetch(msg_id, "(RFC822)")
            if status != "OK":
                continue

            raw = msg_data[0][1]
            msg = email.message_from_bytes(raw)

            subject = decode_header_value(msg.get("Subject", "No Subject"))
            sender = decode_header_value(msg.get("From", "Unknown"))
            date = msg.get("Date", "Unknown")
            body = get_body(msg)

            # Create task file in Inbox/.
            safe_subj = safe_filename(subject)
            timestamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
            task_filename = f"email_{safe_subj}_{timestamp}.md"
            task_path = os.path.join(INBOX_DIR, task_filename)

            content = f"""---
type: email_review
status: pending
priority: medium
created_at: {_now()}
related_files: []
source: gmail
---

# Email: {subject}

## Metadata
- **From:** {sender}
- **Date:** {date}
- **Subject:** {subject}

## Body

{body.strip()}

## Steps
- [ ] Read and review this email
- [ ] Decide action needed (reply, forward, archive, escalate)
- [ ] Complete processing

## Notes
- Fetched by gmail-watcher from {addr}
"""

            try:
                with open(task_path, "w", encoding="utf-8") as f:
                    f.write(content)
                log(f"Email -> task: {task_filename} (from: {sender})")
                created += 1
            except OSError as e:
                log(f"[ERROR] Failed to write {task_filename}: {e}")

            state["seen_ids"].append(msg_id_str)

        save_state(state)
        mail.close()
        mail.logout()
        return created

    except Exception as e:
        log(f"[ERROR] IMAP error: {e}")
        try:
            mail.logout()
        except Exception:
            pass
        return -1


def main():
    parser = argparse.ArgumentParser(description="Gmail Watcher — monitor inbox for new emails")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--once", action="store_true", help="Check once then exit")
    group.add_argument("--daemon", action="store_true", help="Poll continuously")
    parser.add_argument("--interval", type=int, default=DEFAULT_INTERVAL,
                        help=f"Poll interval in seconds (default {DEFAULT_INTERVAL})")
    args = parser.parse_args()

    signal.signal(signal.SIGINT, _sig)
    signal.signal(signal.SIGTERM, _sig)

    print("=" * 55)
    print("  Gmail Watcher — Email Monitor")
    print("=" * 55)

    if args.once:
        log("Single check started.")
        count = fetch_new_emails()
        if count < 0:
            sys.exit(1)
        log(f"Done. {count} new email(s) processed.")
        return

    # Daemon mode.
    interval = max(30, args.interval)
    log(f"Daemon started (interval: {interval}s).")

    while not _shutdown:
        count = fetch_new_emails()
        if count >= 0:
            log(f"Check complete: {count} new email(s).")

        for _ in range(interval):
            if _shutdown:
                break
            time.sleep(1)

    log("Gmail watcher stopped.")


if __name__ == "__main__":
    main()
