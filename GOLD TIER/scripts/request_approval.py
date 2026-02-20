"""
request_approval.py — Human Approval Agent Skill

Gates AI execution behind explicit human sign-off.

Modes:
  --submit <file>   Copy file into Needs_Approval/ and block until decision.
  --file <path>     Wait for decision on an existing approval request.
  --watch           Monitor the entire Needs_Approval/ folder continuously.

The human opens the approval file and writes APPROVED or REJECTED in the
Decision section. The script detects the change, renames the file with the
appropriate suffix (.approved, .rejected, .timeout), and exits.

Exit codes: 0 = approved, 1 = rejected, 2 = timeout, 3 = error.

Usage:
    python scripts/request_approval.py --submit Needs_Action/Plan.md
    python scripts/request_approval.py --file Needs_Approval/approval_Plan.md
    python scripts/request_approval.py --watch
"""

import argparse
import os
import re
import signal
import sys
import time
from datetime import datetime, timezone, timedelta

# ---------------------------------------------------------------------------
# Exit codes
# ---------------------------------------------------------------------------

EXIT_APPROVED = 0
EXIT_REJECTED = 1
EXIT_TIMEOUT = 2
EXIT_ERROR = 3

# ---------------------------------------------------------------------------
# Path setup
# ---------------------------------------------------------------------------

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
VAULT_ROOT = os.path.dirname(SCRIPT_DIR)

NEEDS_APPROVAL_DIR = os.path.join(VAULT_ROOT, "Needs_Approval")
LOGS_DIR = os.path.join(VAULT_ROOT, "Logs")
ACTIONS_LOG = os.path.join(LOGS_DIR, "actions.log")

DEFAULT_TIMEOUT = 3600   # 1 hour
DEFAULT_POLL = 5          # seconds

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

def _now_str():
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")


def log_action(message):
    """Append a timestamped line to logs/actions.log and echo to stdout."""
    entry = f"[{_now_str()}] [human-approval] {message}"
    print(entry)
    try:
        os.makedirs(LOGS_DIR, exist_ok=True)
        with open(ACTIONS_LOG, "a", encoding="utf-8") as f:
            f.write(entry + "\n")
    except OSError as err:
        print(f"[WARNING] Could not write to actions.log: {err}")

# ---------------------------------------------------------------------------
# Approval request template
# ---------------------------------------------------------------------------

def build_approval_request(source_path, description=None, timeout_seconds=DEFAULT_TIMEOUT):
    """
    Read a source file and wrap its content in an approval-request template.
    Returns (approval_filename, approval_content).
    """
    source_name = os.path.basename(source_path)

    try:
        with open(source_path, "r", encoding="utf-8") as f:
            source_content = f.read()
    except OSError as err:
        log_action(f"[ERROR] Cannot read source file {source_path}: {err}")
        return None, None

    now = datetime.now(timezone.utc)
    requested_at = now.strftime("%Y-%m-%d %H:%M:%S UTC")
    timeout_at = (now + timedelta(seconds=timeout_seconds)).strftime("%Y-%m-%d %H:%M:%S UTC")

    safe_name = source_name.replace(".", "_").replace(" ", "_")
    approval_filename = f"approval_{safe_name}.md"

    desc_line = description if description else f"Review the contents of `{source_name}` and decide whether to approve or reject."

    content = f"""---
type: approval_request
status: pending_approval
requested_at: {requested_at}
timeout_at: {timeout_at}
source_file: {source_name}
---

# Approval Request: {source_name}

## Description
{desc_line}

## Source Content

{source_content.rstrip()}

## Decision
<!-- Write your decision below this line, then save the file. -->

"""
    return approval_filename, content

# ---------------------------------------------------------------------------
# Decision detection
# ---------------------------------------------------------------------------

_DECISION_SECTION = re.compile(
    r"##\s+Decision\b.*$",
    re.MULTILINE,
)

# Match APPROVED / REJECTED as standalone words (case-insensitive), but only
# after the ## Decision heading so we don't false-match on source content.
_APPROVED_PATTERN = re.compile(r"\bAPPROVED\b", re.IGNORECASE)
_REJECTED_PATTERN = re.compile(r"\bREJECTED\b", re.IGNORECASE)


_HTML_COMMENT = re.compile(r"<!--.*?-->", re.DOTALL)


def read_decision(filepath):
    """
    Read the approval file and check for a decision.
    Returns "approved", "rejected", or None.
    """
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            content = f.read()
    except OSError:
        return None

    # Find the ## Decision section.
    match = _DECISION_SECTION.search(content)
    if not match:
        return None

    # Only scan text after the Decision heading, with HTML comments stripped
    # so template instructions never cause a false positive.
    decision_text = content[match.start():]
    decision_text = _HTML_COMMENT.sub("", decision_text)

    if _APPROVED_PATTERN.search(decision_text):
        return "approved"
    if _REJECTED_PATTERN.search(decision_text):
        return "rejected"

    return None

# ---------------------------------------------------------------------------
# Status update in front-matter
# ---------------------------------------------------------------------------

def update_status(filepath, new_status):
    """Update the front-matter status field in-place."""
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            content = f.read()
    except OSError:
        return

    content = re.sub(
        r"^(status:\s*).*$",
        rf"\g<1>{new_status}",
        content,
        count=1,
        flags=re.MULTILINE,
    )

    try:
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(content)
    except OSError as err:
        log_action(f"[WARNING] Could not update status in {filepath}: {err}")

# ---------------------------------------------------------------------------
# File renaming
# ---------------------------------------------------------------------------

def rename_with_suffix(filepath, suffix):
    """
    Rename a file by appending a suffix: file.md -> file.md.approved
    Returns the new path.
    """
    new_path = filepath + suffix
    try:
        os.rename(filepath, new_path)
    except OSError as err:
        log_action(f"[ERROR] Could not rename {filepath} -> {new_path}: {err}")
        return filepath
    return new_path

# ---------------------------------------------------------------------------
# Single-file polling loop
# ---------------------------------------------------------------------------

def wait_for_decision(filepath, timeout_seconds=DEFAULT_TIMEOUT, poll_seconds=DEFAULT_POLL):
    """
    Block until the human writes APPROVED or REJECTED, or until timeout.
    Returns exit code: 0 (approved), 1 (rejected), 2 (timeout).
    """
    filename = os.path.basename(filepath)
    deadline = time.monotonic() + timeout_seconds

    log_action(f"Waiting for decision on: {filename} (timeout: {timeout_seconds}s)")

    while time.monotonic() < deadline:
        if _shutdown_requested:
            log_action(f"Shutdown requested while waiting on: {filename}")
            return EXIT_ERROR

        if not os.path.isfile(filepath):
            log_action(f"[WARNING] File disappeared: {filename}")
            return EXIT_ERROR

        decision = read_decision(filepath)

        if decision == "approved":
            update_status(filepath, "approved")
            new_path = rename_with_suffix(filepath, ".approved")
            log_action(f"APPROVED: {filename} -> {os.path.basename(new_path)}")
            return EXIT_APPROVED

        if decision == "rejected":
            update_status(filepath, "rejected")
            new_path = rename_with_suffix(filepath, ".rejected")
            log_action(f"REJECTED: {filename} -> {os.path.basename(new_path)}")
            return EXIT_REJECTED

        time.sleep(poll_seconds)

    # Timeout reached.
    update_status(filepath, "timeout")
    new_path = rename_with_suffix(filepath, ".timeout")
    log_action(f"TIMEOUT: {filename} -> {os.path.basename(new_path)} (after {timeout_seconds}s)")
    return EXIT_TIMEOUT

# ---------------------------------------------------------------------------
# Watch mode
# ---------------------------------------------------------------------------

def get_pending_files():
    """Return a list of .md files in Needs_Approval/ that have no decision suffix."""
    try:
        return sorted(
            f for f in os.listdir(NEEDS_APPROVAL_DIR)
            if f.endswith(".md")
            and not f.endswith(".approved")
            and not f.endswith(".rejected")
            and not f.endswith(".timeout")
            and os.path.isfile(os.path.join(NEEDS_APPROVAL_DIR, f))
        )
    except FileNotFoundError:
        return []


def parse_timeout_from_file(filepath):
    """
    Read the timeout_at field from front-matter and return seconds remaining.
    Returns None if not parseable.
    """
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            content = f.read(1024)  # front-matter is near the top
    except OSError:
        return None

    match = re.search(r"^timeout_at:\s*(.+)$", content, re.MULTILINE)
    if not match:
        return None

    try:
        timeout_at = datetime.strptime(match.group(1).strip(), "%Y-%m-%d %H:%M:%S UTC")
        timeout_at = timeout_at.replace(tzinfo=timezone.utc)
        remaining = (timeout_at - datetime.now(timezone.utc)).total_seconds()
        return max(0, remaining)
    except ValueError:
        return None


def watch_folder(timeout_seconds=DEFAULT_TIMEOUT, poll_seconds=DEFAULT_POLL):
    """
    Continuously monitor Needs_Approval/ for pending files.
    Processes each file's decision or timeout individually.
    """
    log_action(f"Watch mode started. Monitoring: {NEEDS_APPROVAL_DIR}")
    log_action(f"Default timeout: {timeout_seconds}s, poll: {poll_seconds}s")

    while not _shutdown_requested:
        pending = get_pending_files()

        for filename in pending:
            if _shutdown_requested:
                break

            filepath = os.path.join(NEEDS_APPROVAL_DIR, filename)

            # Use per-file timeout if available, otherwise the default.
            file_timeout = parse_timeout_from_file(filepath)
            if file_timeout is not None:
                if file_timeout <= 0:
                    # Already past deadline.
                    update_status(filepath, "timeout")
                    new_path = rename_with_suffix(filepath, ".timeout")
                    log_action(f"TIMEOUT (expired): {filename} -> {os.path.basename(new_path)}")
                    continue
                effective_timeout = file_timeout
            else:
                effective_timeout = timeout_seconds

            decision = read_decision(filepath)

            if decision == "approved":
                update_status(filepath, "approved")
                new_path = rename_with_suffix(filepath, ".approved")
                log_action(f"APPROVED: {filename} -> {os.path.basename(new_path)}")
                continue

            if decision == "rejected":
                update_status(filepath, "rejected")
                new_path = rename_with_suffix(filepath, ".rejected")
                log_action(f"REJECTED: {filename} -> {os.path.basename(new_path)}")
                continue

            # No decision yet — file stays pending, will check again next cycle.

        # Sleep between scan cycles.
        for _ in range(poll_seconds):
            if _shutdown_requested:
                break
            time.sleep(1)

    log_action("Watch mode stopped.")

# ---------------------------------------------------------------------------
# Graceful shutdown
# ---------------------------------------------------------------------------

_shutdown_requested = False


def _handle_signal(signum, _frame):
    global _shutdown_requested
    _shutdown_requested = True

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Human Approval Gate — block until APPROVED/REJECTED or timeout"
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument(
        "--submit",
        type=str,
        metavar="FILE",
        help="Path to a source file to submit for approval",
    )
    group.add_argument(
        "--file",
        type=str,
        metavar="FILE",
        help="Path to an existing approval request to monitor",
    )
    group.add_argument(
        "--watch",
        action="store_true",
        help="Monitor the entire Needs_Approval/ folder",
    )

    parser.add_argument(
        "--description",
        type=str,
        default=None,
        help="Custom description for the approval request (used with --submit)",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=DEFAULT_TIMEOUT,
        help=f"Seconds before auto-timeout (default {DEFAULT_TIMEOUT})",
    )
    parser.add_argument(
        "--poll",
        type=int,
        default=DEFAULT_POLL,
        help=f"Seconds between file checks (default {DEFAULT_POLL})",
    )
    args = parser.parse_args()

    signal.signal(signal.SIGINT, _handle_signal)
    signal.signal(signal.SIGTERM, _handle_signal)

    os.makedirs(NEEDS_APPROVAL_DIR, exist_ok=True)
    os.makedirs(LOGS_DIR, exist_ok=True)

    print("=" * 55)
    print("  Human Approval Gate")
    print("=" * 55)

    # --- Submit mode ---
    if args.submit:
        source_path = os.path.abspath(args.submit)
        if not os.path.isfile(source_path):
            log_action(f"[ERROR] Source file not found: {source_path}")
            sys.exit(EXIT_ERROR)

        approval_filename, approval_content = build_approval_request(
            source_path,
            description=args.description,
            timeout_seconds=args.timeout,
        )
        if approval_filename is None:
            sys.exit(EXIT_ERROR)

        approval_path = os.path.join(NEEDS_APPROVAL_DIR, approval_filename)

        try:
            with open(approval_path, "w", encoding="utf-8") as f:
                f.write(approval_content)
        except OSError as err:
            log_action(f"[ERROR] Cannot write approval request: {err}")
            sys.exit(EXIT_ERROR)

        log_action(f"Submitted for approval: {approval_filename}")
        log_action(f"Source: {os.path.basename(source_path)}")
        log_action(f"Human action required: open Needs_Approval/{approval_filename} and write APPROVED or REJECTED in the Decision section.")

        code = wait_for_decision(approval_path, args.timeout, args.poll)
        sys.exit(code)

    # --- Single-file mode ---
    if args.file:
        filepath = os.path.abspath(args.file)
        if not os.path.isfile(filepath):
            log_action(f"[ERROR] File not found: {filepath}")
            sys.exit(EXIT_ERROR)

        code = wait_for_decision(filepath, args.timeout, args.poll)
        sys.exit(code)

    # --- Watch mode ---
    if args.watch:
        watch_folder(args.timeout, args.poll)
        sys.exit(EXIT_APPROVED)


if __name__ == "__main__":
    main()
