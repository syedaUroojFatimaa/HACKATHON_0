"""
request_approval.py — Human-in-the-loop approval gate.

Creates an approval request in Needs_Approval/, blocks until the human
writes APPROVED or REJECTED in the Decision section, then renames the
file with .approved / .rejected / .timeout and exits.

Exit codes: 0=approved, 1=rejected, 2=timeout, 3=error.

Usage:
    python request_approval.py --submit Needs_Action/Plan.md
    python request_approval.py --file Needs_Approval/approval_Plan.md
    python request_approval.py --watch
"""

import argparse
import os
import re
import signal
import sys
import time
from datetime import datetime, timezone, timedelta

EXIT_APPROVED = 0
EXIT_REJECTED = 1
EXIT_TIMEOUT = 2
EXIT_ERROR = 3

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
VAULT_ROOT = os.path.abspath(os.path.join(SCRIPT_DIR, "..", "..", "..", ".."))

NEEDS_APPROVAL_DIR = os.path.join(VAULT_ROOT, "Needs_Approval")
LOGS_DIR = os.path.join(VAULT_ROOT, "Logs")
ACTIONS_LOG = os.path.join(LOGS_DIR, "actions.log")

DEFAULT_TIMEOUT = 3600
DEFAULT_POLL = 5

_HTML_COMMENT = re.compile(r"<!--.*?-->", re.DOTALL)
_DECISION_HEADING = re.compile(r"##\s+Decision\b.*$", re.MULTILINE)
_APPROVED = re.compile(r"\bAPPROVED\b", re.IGNORECASE)
_REJECTED = re.compile(r"\bREJECTED\b", re.IGNORECASE)

_shutdown = False


def _sig(s, f):
    global _shutdown
    _shutdown = True


def _now():
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")


def log(msg):
    entry = f"[{_now()}] [human-approval] {msg}"
    print(entry)
    try:
        os.makedirs(LOGS_DIR, exist_ok=True)
        with open(ACTIONS_LOG, "a", encoding="utf-8") as fh:
            fh.write(entry + "\n")
    except OSError:
        pass


def read_decision(path):
    """Return 'approved', 'rejected', or None."""
    try:
        with open(path, "r", encoding="utf-8") as f:
            content = f.read()
    except OSError:
        return None
    m = _DECISION_HEADING.search(content)
    if not m:
        return None
    text = _HTML_COMMENT.sub("", content[m.start():])
    if _APPROVED.search(text):
        return "approved"
    if _REJECTED.search(text):
        return "rejected"
    return None


def update_status(path, status):
    try:
        with open(path, "r", encoding="utf-8") as f:
            c = f.read()
        c = re.sub(r"^(status:\s*).*$", rf"\g<1>{status}", c, count=1, flags=re.MULTILINE)
        with open(path, "w", encoding="utf-8") as f:
            f.write(c)
    except OSError:
        pass


def rename(path, suffix):
    new = path + suffix
    try:
        os.rename(path, new)
    except OSError as e:
        log(f"Rename failed: {e}")
        return path
    return new


def build_request(source, description=None, timeout_s=DEFAULT_TIMEOUT):
    name = os.path.basename(source)
    try:
        with open(source, "r", encoding="utf-8") as f:
            body = f.read()
    except OSError as e:
        log(f"Cannot read {source}: {e}")
        return None, None

    now = datetime.now(timezone.utc)
    req_at = now.strftime("%Y-%m-%d %H:%M:%S UTC")
    exp_at = (now + timedelta(seconds=timeout_s)).strftime("%Y-%m-%d %H:%M:%S UTC")
    desc = description or f"Review `{name}` and decide."
    safe = name.replace(".", "_").replace(" ", "_")

    content = f"""---
type: approval_request
status: pending_approval
requested_at: {req_at}
timeout_at: {exp_at}
source_file: {name}
---

# Approval Request: {name}

## Description
{desc}

## Source Content

{body.rstrip()}

## Decision
<!-- Write your decision below this line, then save the file. -->

"""
    return f"approval_{safe}.md", content


def wait(path, timeout_s=DEFAULT_TIMEOUT, poll_s=DEFAULT_POLL):
    fname = os.path.basename(path)
    deadline = time.monotonic() + timeout_s
    log(f"Waiting for decision: {fname} (timeout {timeout_s}s)")

    while time.monotonic() < deadline and not _shutdown:
        if not os.path.isfile(path):
            log(f"File disappeared: {fname}")
            return EXIT_ERROR
        d = read_decision(path)
        if d == "approved":
            update_status(path, "approved")
            rename(path, ".approved")
            log(f"APPROVED: {fname}")
            return EXIT_APPROVED
        if d == "rejected":
            update_status(path, "rejected")
            rename(path, ".rejected")
            log(f"REJECTED: {fname}")
            return EXIT_REJECTED
        time.sleep(poll_s)

    update_status(path, "timeout")
    rename(path, ".timeout")
    log(f"TIMEOUT: {fname}")
    return EXIT_TIMEOUT


def watch(timeout_s=DEFAULT_TIMEOUT, poll_s=DEFAULT_POLL):
    log("Watch mode started.")
    while not _shutdown:
        try:
            pending = sorted(
                f for f in os.listdir(NEEDS_APPROVAL_DIR)
                if f.endswith(".md") and not any(
                    f.endswith(s) for s in (".approved", ".rejected", ".timeout")
                ) and os.path.isfile(os.path.join(NEEDS_APPROVAL_DIR, f))
            )
        except FileNotFoundError:
            pending = []

        for fname in pending:
            if _shutdown:
                break
            fp = os.path.join(NEEDS_APPROVAL_DIR, fname)
            d = read_decision(fp)
            if d == "approved":
                update_status(fp, "approved")
                rename(fp, ".approved")
                log(f"APPROVED: {fname}")
            elif d == "rejected":
                update_status(fp, "rejected")
                rename(fp, ".rejected")
                log(f"REJECTED: {fname}")

        for _ in range(poll_s):
            if _shutdown:
                break
            time.sleep(1)

    log("Watch mode stopped.")


def main():
    parser = argparse.ArgumentParser(description="Human Approval Gate")
    grp = parser.add_mutually_exclusive_group(required=True)
    grp.add_argument("--submit", metavar="FILE", help="Submit file for approval")
    grp.add_argument("--file", metavar="FILE", help="Monitor existing approval file")
    grp.add_argument("--watch", action="store_true", help="Watch Needs_Approval/ folder")
    parser.add_argument("--description", default=None)
    parser.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT)
    parser.add_argument("--poll", type=int, default=DEFAULT_POLL)
    args = parser.parse_args()

    signal.signal(signal.SIGINT, _sig)
    signal.signal(signal.SIGTERM, _sig)
    os.makedirs(NEEDS_APPROVAL_DIR, exist_ok=True)

    if args.submit:
        src = os.path.abspath(args.submit)
        if not os.path.isfile(src):
            log(f"File not found: {src}")
            sys.exit(EXIT_ERROR)
        afn, acontent = build_request(src, args.description, args.timeout)
        if not afn:
            sys.exit(EXIT_ERROR)
        ap = os.path.join(NEEDS_APPROVAL_DIR, afn)
        with open(ap, "w", encoding="utf-8") as f:
            f.write(acontent)
        log(f"Submitted: {afn}")
        sys.exit(wait(ap, args.timeout, args.poll))

    if args.file:
        fp = os.path.abspath(args.file)
        if not os.path.isfile(fp):
            log(f"File not found: {fp}")
            sys.exit(EXIT_ERROR)
        sys.exit(wait(fp, args.timeout, args.poll))

    if args.watch:
        watch(args.timeout, args.poll)


if __name__ == "__main__":
    main()
