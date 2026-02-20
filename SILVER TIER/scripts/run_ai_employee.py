"""
run_ai_employee.py — Silver Scheduler Agent Skill

Central orchestrator that runs vault-watcher and task-planner in a timed
loop.  Each cycle:
  1. Scans Inbox/ for new files -> creates tasks in Needs_Action/
  2. Runs task_planner.py       -> generates execution plans
  3. Runs process_tasks.py      -> completes tasks and moves to Done/
  4. Checks log size            -> rotates at 5 MB

Modes:
  --daemon   Run continuously (default interval: 5 minutes)
  --once     Single cycle then exit
  --status   Print vault status snapshot

Uses a PID lock file to prevent duplicate instances.

Usage:
    python scripts/run_ai_employee.py --daemon
    python scripts/run_ai_employee.py --daemon --interval 120
    python scripts/run_ai_employee.py --once
    python scripts/run_ai_employee.py --status
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
VAULT_ROOT = os.path.dirname(SCRIPT_DIR)

INBOX_DIR = os.path.join(VAULT_ROOT, "Inbox")
NEEDS_ACTION_DIR = os.path.join(VAULT_ROOT, "Needs_Action")
NEEDS_APPROVAL_DIR = os.path.join(VAULT_ROOT, "Needs_Approval")
DONE_DIR = os.path.join(VAULT_ROOT, "Done")
LOGS_DIR = os.path.join(VAULT_ROOT, "Logs")

AI_LOG = os.path.join(LOGS_DIR, "ai_employee.log")
LOCK_FILE = os.path.join(LOGS_DIR, ".scheduler.lock")
WATCHER_STATE = os.path.join(LOGS_DIR, ".watcher_state.json")

TASK_PLANNER_SCRIPT = os.path.join(SCRIPT_DIR, "task_planner.py")
PROCESS_TASKS_SCRIPT = os.path.join(VAULT_ROOT, "process_tasks.py")

DEFAULT_INTERVAL = 300       # 5 minutes
MAX_LOG_BYTES = 5 * 1024 * 1024  # 5 MB

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

def _now_str():
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")


def log(message, level="INFO"):
    """Write to logs/ai_employee.log and stdout."""
    entry = f"[{_now_str()}] [{level}] {message}"
    print(entry)
    try:
        os.makedirs(LOGS_DIR, exist_ok=True)
        with open(AI_LOG, "a", encoding="utf-8") as f:
            f.write(entry + "\n")
    except OSError as err:
        print(f"[WARNING] Could not write to ai_employee.log: {err}")

# ---------------------------------------------------------------------------
# Lock file — singleton enforcement
# ---------------------------------------------------------------------------

def _pid_alive(pid):
    """Check whether a PID is still running."""
    try:
        os.kill(pid, 0)
        return True
    except (OSError, ProcessLookupError, PermissionError):
        return False


def acquire_lock():
    """
    Write our PID to the lock file.  Returns True on success.
    If another scheduler is already running, returns False.
    """
    os.makedirs(LOGS_DIR, exist_ok=True)

    if os.path.isfile(LOCK_FILE):
        try:
            with open(LOCK_FILE, "r") as f:
                old_pid = int(f.read().strip())
            if _pid_alive(old_pid):
                log(f"Another scheduler is running (PID {old_pid}). Aborting.", "ERROR")
                return False
            else:
                log(f"Stale lock found (PID {old_pid} dead). Cleaning up.", "WARN")
        except (ValueError, OSError):
            log("Corrupt lock file found. Cleaning up.", "WARN")

    with open(LOCK_FILE, "w") as f:
        f.write(str(os.getpid()))
    return True


def release_lock():
    """Remove the lock file."""
    try:
        if os.path.isfile(LOCK_FILE):
            os.remove(LOCK_FILE)
    except OSError:
        pass

# ---------------------------------------------------------------------------
# Log rotation
# ---------------------------------------------------------------------------

def rotate_log_if_needed():
    """Archive ai_employee.log if it exceeds 5 MB."""
    if not os.path.isfile(AI_LOG):
        return

    size = os.path.getsize(AI_LOG)
    if size <= MAX_LOG_BYTES:
        return

    date_stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    name, ext = os.path.splitext(os.path.basename(AI_LOG))
    archive_name = f"{name}_{date_stamp}{ext}"
    archive_path = os.path.join(LOGS_DIR, archive_name)

    counter = 2
    while os.path.exists(archive_path):
        archive_name = f"{name}_{date_stamp}_{counter}{ext}"
        archive_path = os.path.join(LOGS_DIR, archive_name)
        counter += 1

    try:
        os.rename(AI_LOG, archive_path)
        log(f"Log rotated: {archive_name} ({size / (1024*1024):.1f} MB)")
    except OSError as err:
        print(f"[WARNING] Log rotation failed: {err}")

# ---------------------------------------------------------------------------
# Watcher state helpers  (shared with watch_inbox.py)
# ---------------------------------------------------------------------------

def _load_watcher_state():
    if not os.path.isfile(WATCHER_STATE):
        return {}
    try:
        with open(WATCHER_STATE, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return {}


def _save_watcher_state(state):
    os.makedirs(LOGS_DIR, exist_ok=True)
    with open(WATCHER_STATE, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2)

# ---------------------------------------------------------------------------
# Step 1 — Inbox scan  (vault-watcher logic, single pass)
# ---------------------------------------------------------------------------

def scan_inbox():
    """
    Detect new files in Inbox/, create task files in Needs_Action/.
    Returns count of new files processed.
    """
    os.makedirs(INBOX_DIR, exist_ok=True)
    os.makedirs(NEEDS_ACTION_DIR, exist_ok=True)

    state = _load_watcher_state()

    try:
        current_files = {
            f for f in os.listdir(INBOX_DIR)
            if os.path.isfile(os.path.join(INBOX_DIR, f))
        }
    except OSError:
        return 0

    new_files = sorted(current_files - set(state.keys()))
    if not new_files:
        return 0

    created = 0
    for filename in new_files:
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

## Steps
- [ ] Open and review the contents of `{filename}`
- [ ] Decide what action is needed (archive, respond, escalate, etc.)
- [ ] Complete processing and move to Done

## Notes
- Source: Inbox
- Detected by: silver-scheduler (run_ai_employee.py)
"""

        try:
            with open(task_path, "w", encoding="utf-8") as f:
                f.write(content)
            log(f"Inbox -> task created: {task_filename}")
            created += 1
        except OSError as err:
            log(f"Failed to create task for '{filename}': {err}", "ERROR")

        state[filename] = _now_str()

    _save_watcher_state(state)
    return created

# ---------------------------------------------------------------------------
# Step 2 — Task planner  (subprocess call)
# ---------------------------------------------------------------------------

def run_task_planner():
    """Run task_planner.py to analyze inbox .md files and create plans."""
    if not os.path.isfile(TASK_PLANNER_SCRIPT):
        log(f"task_planner.py not found at {TASK_PLANNER_SCRIPT}", "ERROR")
        return False

    try:
        result = subprocess.run(
            [sys.executable, TASK_PLANNER_SCRIPT],
            cwd=VAULT_ROOT,
            capture_output=True,
            text=True,
            timeout=120,
        )
        if result.returncode == 0:
            log("Task planner completed.")
        else:
            log(f"task_planner.py exited with code {result.returncode}", "WARN")
            if result.stderr:
                log(f"  stderr: {result.stderr.strip()}", "WARN")
        return result.returncode == 0
    except subprocess.TimeoutExpired:
        log("task_planner.py timed out (120s).", "ERROR")
        return False
    except OSError as err:
        log(f"Could not launch task_planner.py: {err}", "ERROR")
        return False

# ---------------------------------------------------------------------------
# Step 3 — Process tasks  (subprocess call)
# ---------------------------------------------------------------------------

def run_process_tasks():
    """Run process_tasks.py to complete and archive pending tasks."""
    if not os.path.isfile(PROCESS_TASKS_SCRIPT):
        log(f"process_tasks.py not found at {PROCESS_TASKS_SCRIPT}", "ERROR")
        return False

    try:
        result = subprocess.run(
            [sys.executable, PROCESS_TASKS_SCRIPT],
            cwd=VAULT_ROOT,
            capture_output=True,
            text=True,
            timeout=120,
        )
        if result.returncode == 0:
            log("Process tasks completed.")
        else:
            log(f"process_tasks.py exited with code {result.returncode}", "WARN")
            if result.stderr:
                log(f"  stderr: {result.stderr.strip()}", "WARN")
        return result.returncode == 0
    except subprocess.TimeoutExpired:
        log("process_tasks.py timed out (120s).", "ERROR")
        return False
    except OSError as err:
        log(f"Could not launch process_tasks.py: {err}", "ERROR")
        return False

# ---------------------------------------------------------------------------
# Step 4 — Check approvals (human-approval integration)
# ---------------------------------------------------------------------------

def check_approvals():
    """
    Scan Needs_Approval/ for files with decisions (APPROVED/REJECTED).
    Renames them with the appropriate suffix. Returns count of resolved.
    """
    import re as _re

    _decision_heading = _re.compile(r"##\s+Decision\b.*$", _re.MULTILINE)
    _html_comment = _re.compile(r"<!--.*?-->", _re.DOTALL)
    _approved = _re.compile(r"\bAPPROVED\b", _re.IGNORECASE)
    _rejected = _re.compile(r"\bREJECTED\b", _re.IGNORECASE)

    os.makedirs(NEEDS_APPROVAL_DIR, exist_ok=True)

    try:
        pending = [
            f for f in os.listdir(NEEDS_APPROVAL_DIR)
            if f.endswith(".md")
            and not f.endswith(".approved")
            and not f.endswith(".rejected")
            and not f.endswith(".timeout")
            and os.path.isfile(os.path.join(NEEDS_APPROVAL_DIR, f))
        ]
    except OSError:
        return 0

    resolved = 0
    for filename in sorted(pending):
        filepath = os.path.join(NEEDS_APPROVAL_DIR, filename)
        try:
            with open(filepath, "r", encoding="utf-8") as fh:
                content = fh.read()
        except OSError:
            continue

        m = _decision_heading.search(content)
        if not m:
            continue
        decision_text = _html_comment.sub("", content[m.start():])

        decision = None
        if _approved.search(decision_text):
            decision = "approved"
        elif _rejected.search(decision_text):
            decision = "rejected"

        if decision:
            # Update status in front-matter.
            content = _re.sub(
                r"^(status:\s*).*$", rf"\g<1>{decision}",
                content, count=1, flags=_re.MULTILINE,
            )
            try:
                with open(filepath, "w", encoding="utf-8") as fh:
                    fh.write(content)
                os.rename(filepath, filepath + f".{decision}")
                log(f"Approval resolved: {filename} -> {decision.upper()}")
                resolved += 1
            except OSError as err:
                log(f"Approval rename failed for {filename}: {err}", "WARN")

    return resolved

# ---------------------------------------------------------------------------
# Single cycle
# ---------------------------------------------------------------------------

def run_cycle(cycle_num=0):
    """Execute one full scheduler cycle. Returns a summary dict."""
    label = f"Cycle #{cycle_num}" if cycle_num else "Single run"
    log(f"--- {label} started ---")

    summary = {"inbox_new": 0, "planner_ok": False, "processor_ok": False,
               "approvals_resolved": 0}

    # Step 1: Inbox scan.
    new_count = scan_inbox()
    summary["inbox_new"] = new_count
    if new_count:
        log(f"Inbox scan: {new_count} new file(s) detected.")
    else:
        log("Inbox scan: no new files.")

    # Step 2: Task planner.
    summary["planner_ok"] = run_task_planner()

    # Step 3: Process tasks.
    summary["processor_ok"] = run_process_tasks()

    # Step 4: Check human approvals.
    resolved = check_approvals()
    summary["approvals_resolved"] = resolved
    if resolved:
        log(f"Approvals: {resolved} resolved.")

    # Step 5: Log rotation.
    rotate_log_if_needed()

    log(f"--- {label} finished (new={new_count}, "
        f"planner={'OK' if summary['planner_ok'] else 'FAIL'}, "
        f"processor={'OK' if summary['processor_ok'] else 'FAIL'}, "
        f"approvals={resolved}) ---")

    return summary

# ---------------------------------------------------------------------------
# --status mode
# ---------------------------------------------------------------------------

def _safe_count(directory):
    """Count files in a directory, return 0 if it doesn't exist."""
    try:
        return len([f for f in os.listdir(directory)
                     if os.path.isfile(os.path.join(directory, f))])
    except (FileNotFoundError, OSError):
        return 0


def _pending_approvals():
    """Count .md files in Needs_Approval/ without a decision suffix."""
    try:
        return len([
            f for f in os.listdir(NEEDS_APPROVAL_DIR)
            if f.endswith(".md")
            and not f.endswith(".approved")
            and not f.endswith(".rejected")
            and not f.endswith(".timeout")
            and os.path.isfile(os.path.join(NEEDS_APPROVAL_DIR, f))
        ])
    except (FileNotFoundError, OSError):
        return 0


def show_status():
    """Print a snapshot of the vault state."""
    inbox = _safe_count(INBOX_DIR)
    pending = _safe_count(NEEDS_ACTION_DIR)
    approvals = _pending_approvals()
    done = _safe_count(DONE_DIR)

    # Lock file check.
    scheduler_running = False
    scheduler_pid = None
    if os.path.isfile(LOCK_FILE):
        try:
            with open(LOCK_FILE, "r") as f:
                scheduler_pid = int(f.read().strip())
            scheduler_running = _pid_alive(scheduler_pid)
        except (ValueError, OSError):
            pass

    print("=" * 55)
    print("  Silver Tier AI Employee — Status")
    print("=" * 55)
    print()
    print(f"  Inbox (new files)       : {inbox}")
    print(f"  Needs_Action (pending)  : {pending}")
    print(f"  Needs_Approval (waiting): {approvals}")
    print(f"  Done (completed)        : {done}")
    print()

    if scheduler_running:
        print(f"  Scheduler               : RUNNING (PID {scheduler_pid})")
    else:
        print(f"  Scheduler               : STOPPED")

    print()

    # Show last 5 log lines.
    if os.path.isfile(AI_LOG):
        try:
            with open(AI_LOG, "r", encoding="utf-8") as f:
                lines = f.readlines()
            recent = lines[-5:] if len(lines) >= 5 else lines
            print("  Recent log entries:")
            for line in recent:
                print(f"    {line.rstrip()}")
        except OSError:
            pass
    else:
        print("  (no log file yet)")

    print()
    print("=" * 55)

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
        description="Silver Scheduler — orchestrate vault-watcher and task-planner"
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument(
        "--daemon",
        action="store_true",
        help="Run continuously with a timed loop",
    )
    group.add_argument(
        "--once",
        action="store_true",
        help="Run a single cycle then exit",
    )
    group.add_argument(
        "--status",
        action="store_true",
        help="Show current vault status",
    )

    parser.add_argument(
        "--interval",
        type=int,
        default=DEFAULT_INTERVAL,
        help=f"Seconds between cycles in daemon mode (default {DEFAULT_INTERVAL})",
    )
    args = parser.parse_args()

    signal.signal(signal.SIGINT, _handle_signal)
    signal.signal(signal.SIGTERM, _handle_signal)

    # Ensure core directories exist.
    for d in [INBOX_DIR, NEEDS_ACTION_DIR, DONE_DIR, LOGS_DIR]:
        os.makedirs(d, exist_ok=True)

    # --status: no lock needed, just print and exit.
    if args.status:
        show_status()
        return

    # --once: acquire lock, run one cycle, release.
    if args.once:
        if not acquire_lock():
            sys.exit(1)
        try:
            print("=" * 55)
            print("  Silver Scheduler — Single Run")
            print("=" * 55)
            log("Scheduler started (--once).")
            run_cycle()
            log("Scheduler finished (--once).")
        finally:
            release_lock()
        return

    # --daemon: acquire lock, loop until shutdown.
    if not acquire_lock():
        sys.exit(1)

    interval = max(10, args.interval)

    print("=" * 55)
    print("  Silver Scheduler — Daemon Mode")
    print("=" * 55)
    print(f"  PID      : {os.getpid()}")
    print(f"  Interval : {interval}s ({interval // 60}m {interval % 60}s)")
    print(f"  Log      : {AI_LOG}")
    print(f"  Lock     : {LOCK_FILE}")
    print("=" * 55)

    log(f"Scheduler daemon started (PID {os.getpid()}, interval {interval}s).")

    cycle = 0
    try:
        while not _shutdown_requested:
            cycle += 1
            run_cycle(cycle)

            # Sleep in 1-second increments for responsive shutdown.
            for _ in range(interval):
                if _shutdown_requested:
                    break
                time.sleep(1)
    finally:
        log(f"Scheduler daemon stopped after {cycle} cycle(s).")
        release_lock()
        print("\n[STOPPED] Scheduler shut down gracefully.")


if __name__ == "__main__":
    main()
