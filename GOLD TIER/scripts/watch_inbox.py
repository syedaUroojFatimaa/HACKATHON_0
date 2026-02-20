"""
watch_inbox.py — Vault Watcher Agent Skill

Continuously monitors the Inbox folder for new .md files.
When one appears, it:
  1. Logs detection to logs/actions.log
  2. Creates a task file in Needs_Action/
  3. Triggers the processing pipeline (process_tasks.py)
  4. Records the file in a persistent ledger to prevent duplicate processing

Usage:
    python scripts/watch_inbox.py
    python scripts/watch_inbox.py --interval 20
    python scripts/watch_inbox.py --inbox path/to/Inbox

Press Ctrl+C to stop.
"""

import argparse
import json
import os
import signal
import subprocess
import sys
import time
from datetime import datetime, timezone

# ---------------------------------------------------------------------------
# Path setup
# ---------------------------------------------------------------------------

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
VAULT_ROOT = os.path.dirname(SCRIPT_DIR)  # one level up from scripts/

LOGS_DIR = os.path.join(VAULT_ROOT, "Logs")
ACTIONS_LOG = os.path.join(LOGS_DIR, "actions.log")
STATE_FILE = os.path.join(LOGS_DIR, ".watcher_state.json")

NEEDS_ACTION_DIR = os.path.join(VAULT_ROOT, "Needs_Action")
PROCESS_TASKS_SCRIPT = os.path.join(VAULT_ROOT, "process_tasks.py")

DEFAULT_INBOX = os.path.join(VAULT_ROOT, "Inbox")
MIN_INTERVAL = 10
MAX_INTERVAL = 30
DEFAULT_INTERVAL = 15

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

def _now_str():
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")


def log_action(message):
    """Append a timestamped line to logs/actions.log and echo to stdout."""
    entry = f"[{_now_str()}] {message}"
    print(entry)
    try:
        os.makedirs(LOGS_DIR, exist_ok=True)
        with open(ACTIONS_LOG, "a", encoding="utf-8") as f:
            f.write(entry + "\n")
    except OSError as err:
        print(f"[WARNING] Could not write to actions.log: {err}")

# ---------------------------------------------------------------------------
# State ledger — persistent across restarts
# ---------------------------------------------------------------------------

def load_state():
    """Load the processed-file ledger from disk. Returns a dict {filename: timestamp}."""
    if not os.path.isfile(STATE_FILE):
        return {}
    try:
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return {}


def save_state(state):
    """Persist the ledger to disk."""
    os.makedirs(LOGS_DIR, exist_ok=True)
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2)

# ---------------------------------------------------------------------------
# Task creation (mirrors file_watcher.py logic)
# ---------------------------------------------------------------------------

def create_task_file(filename):
    """Create a structured Markdown task in Needs_Action/ for a new Inbox file."""
    now = datetime.now(timezone.utc)
    timestamp = now.strftime("%Y-%m-%d %H:%M:%S UTC")

    safe_name = filename.replace(".", "_").replace(" ", "_")
    task_filename = f"task_{safe_name}.md"
    task_path = os.path.join(NEEDS_ACTION_DIR, task_filename)

    content = f"""---
type: file_review
status: pending
priority: medium
created_at: {timestamp}
related_files: ["{filename}"]
---

# Review Inbox File: {filename}

## Description
A new file `{filename}` was detected in the Inbox folder and needs review.
Determine what action is required and process accordingly.

## Steps
- [ ] Open and review the contents of `{filename}`
- [ ] Decide what action is needed (archive, respond, escalate, etc.)
- [ ] Move the completed task to Done

## Notes
- Source: Inbox
- Detected by: vault-watcher skill (watch_inbox.py)
"""

    os.makedirs(NEEDS_ACTION_DIR, exist_ok=True)
    with open(task_path, "w", encoding="utf-8") as f:
        f.write(content)

    return task_filename

# ---------------------------------------------------------------------------
# Processing pipeline trigger
# ---------------------------------------------------------------------------

def trigger_processing():
    """Run process_tasks.py to handle all pending tasks in Needs_Action/."""
    if not os.path.isfile(PROCESS_TASKS_SCRIPT):
        log_action(f"[ERROR] process_tasks.py not found at {PROCESS_TASKS_SCRIPT}")
        return False

    try:
        result = subprocess.run(
            [sys.executable, PROCESS_TASKS_SCRIPT],
            cwd=VAULT_ROOT,
            capture_output=True,
            text=True,
            timeout=60,
        )
        if result.returncode == 0:
            log_action("Processing pipeline completed successfully.")
        else:
            log_action(f"[ERROR] process_tasks.py exited with code {result.returncode}")
            if result.stderr:
                log_action(f"  stderr: {result.stderr.strip()}")
        return result.returncode == 0
    except subprocess.TimeoutExpired:
        log_action("[ERROR] process_tasks.py timed out (60s limit).")
        return False
    except OSError as err:
        log_action(f"[ERROR] Could not launch process_tasks.py: {err}")
        return False

# ---------------------------------------------------------------------------
# Inbox scanning
# ---------------------------------------------------------------------------

def scan_inbox(inbox_dir):
    """Return a set of .md filenames currently in the Inbox folder."""
    try:
        return {
            f for f in os.listdir(inbox_dir)
            if f.lower().endswith(".md") and os.path.isfile(os.path.join(inbox_dir, f))
        }
    except FileNotFoundError:
        os.makedirs(inbox_dir, exist_ok=True)
        return set()

# ---------------------------------------------------------------------------
# Graceful shutdown
# ---------------------------------------------------------------------------

_shutdown_requested = False


def _handle_signal(signum, frame):
    global _shutdown_requested
    _shutdown_requested = True

# ---------------------------------------------------------------------------
# Main loop
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Vault Watcher — monitor Inbox for new .md files")
    parser.add_argument(
        "--interval",
        type=int,
        default=DEFAULT_INTERVAL,
        help=f"Poll interval in seconds ({MIN_INTERVAL}-{MAX_INTERVAL}, default {DEFAULT_INTERVAL})",
    )
    parser.add_argument(
        "--inbox",
        type=str,
        default=DEFAULT_INBOX,
        help="Path to the Inbox folder to monitor",
    )
    args = parser.parse_args()

    interval = max(MIN_INTERVAL, min(MAX_INTERVAL, args.interval))
    inbox_dir = os.path.abspath(args.inbox)

    # Register signal handlers for graceful shutdown.
    signal.signal(signal.SIGINT, _handle_signal)
    signal.signal(signal.SIGTERM, _handle_signal)

    # Ensure required directories exist.
    for d in [inbox_dir, NEEDS_ACTION_DIR, LOGS_DIR]:
        os.makedirs(d, exist_ok=True)

    # Load persistent state.
    state = load_state()

    print("=" * 55)
    print("  Vault Watcher — Inbox Monitor")
    print("=" * 55)
    print(f"  Inbox    : {inbox_dir}")
    print(f"  Tasks    : {NEEDS_ACTION_DIR}")
    print(f"  Log      : {ACTIONS_LOG}")
    print(f"  State    : {STATE_FILE}")
    print(f"  Interval : {interval}s")
    print("=" * 55)

    log_action("Vault watcher started.")

    # Snapshot current inbox contents so we don't reprocess on first run.
    existing = scan_inbox(inbox_dir)
    new_on_startup = existing - set(state.keys())
    if new_on_startup:
        log_action(f"Found {len(new_on_startup)} unprocessed .md file(s) on startup — processing now.")
    elif existing:
        log_action(f"{len(existing)} existing .md file(s) already tracked — skipping.")
    else:
        log_action("Inbox is empty. Waiting for new .md files...")

    # If there are files present on startup that haven't been processed, handle them.
    files_to_process = sorted(new_on_startup)

    while not _shutdown_requested:
        # Process any pending files (from startup or from this poll cycle).
        if files_to_process:
            for filename in files_to_process:
                if filename in state:
                    continue  # safety check

                log_action(f"New file detected: {filename}")

                try:
                    task_name = create_task_file(filename)
                    log_action(f"Task created: {task_name}")
                except OSError as err:
                    log_action(f"[ERROR] Failed to create task for '{filename}': {err}")
                    continue

                success = trigger_processing()

                state[filename] = _now_str()
                save_state(state)

                if success:
                    log_action(f"Completed processing for: {filename}")
                else:
                    log_action(f"Processing finished with errors for: {filename}")

            files_to_process = []

        # Sleep in small increments so we can respond to shutdown signals quickly.
        for _ in range(interval):
            if _shutdown_requested:
                break
            time.sleep(1)

        if _shutdown_requested:
            break

        # Poll for new files.
        current = scan_inbox(inbox_dir)
        new_files = sorted(current - set(state.keys()))
        if new_files:
            files_to_process = new_files

    # Shutdown.
    save_state(state)
    log_action("Vault watcher stopped.")
    print("\n[STOPPED] Watcher shut down gracefully.")


if __name__ == "__main__":
    main()
