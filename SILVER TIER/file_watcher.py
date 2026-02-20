"""
file_watcher.py — Bronze Tier Inbox Watcher

Monitors the "Inbox" folder every 5 seconds.
When a new file appears, it automatically creates a structured
task file in "Needs_Action" so nothing gets missed.

Error handling:
  - Missing folders are created automatically on startup.
  - Errors during the main loop are caught so the script never crashes.
  - All errors are logged to Logs/watcher_errors.log with timestamps.

Usage:
    python file_watcher.py
    (Press Ctrl+C to stop)
"""

import os
import time
import traceback
from datetime import datetime, timezone


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

# Build paths relative to wherever this script lives, so it works on any machine.
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
INBOX_DIR = os.path.join(SCRIPT_DIR, "Inbox")
NEEDS_ACTION_DIR = os.path.join(SCRIPT_DIR, "Needs_Action")
LOGS_DIR = os.path.join(SCRIPT_DIR, "Logs")
ERROR_LOG_PATH = os.path.join(LOGS_DIR, "watcher_errors.log")

# How often (in seconds) we check the Inbox for new files.
POLL_INTERVAL = 5


# ---------------------------------------------------------------------------
# Error logging
# ---------------------------------------------------------------------------

def log_error(message):
    """
    Append a timestamped error message to Logs/watcher_errors.log.

    This makes sure errors are never lost — even if you're not watching
    the terminal, you can check the log file later to see what went wrong.
    """
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    entry = f"[{now}] {message}\n"

    # Print to the console so the user sees it immediately.
    print(f"[ERROR] {message}")

    # Also write to the log file so there's a permanent record.
    # Using "a" (append) mode so we never overwrite previous errors.
    try:
        os.makedirs(LOGS_DIR, exist_ok=True)
        with open(ERROR_LOG_PATH, "a", encoding="utf-8") as f:
            f.write(entry)
    except Exception as log_err:
        # If we can't even write the log, print a warning — but don't crash.
        print(f"[WARNING] Could not write to error log: {log_err}")


# ---------------------------------------------------------------------------
# Folder safety — auto-create missing directories
# ---------------------------------------------------------------------------

def ensure_folders_exist():
    """
    Check that the required folders (Inbox, Needs_Action, Logs) exist.
    If any are missing, create them automatically.

    os.makedirs with exist_ok=True is safe to call even if the folder
    already exists — it simply does nothing in that case.
    """
    for folder_path, label in [
        (INBOX_DIR, "Inbox"),
        (NEEDS_ACTION_DIR, "Needs_Action"),
        (LOGS_DIR, "Logs"),
    ]:
        if not os.path.exists(folder_path):
            os.makedirs(folder_path, exist_ok=True)
            print(f"[SETUP] Created missing folder: {label}/")


# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------

def get_inbox_files():
    """
    Return a set of filenames currently sitting in the Inbox folder.
    We use a set so we can quickly compare what's new vs. what we've
    already processed.
    """
    try:
        return set(os.listdir(INBOX_DIR))
    except FileNotFoundError:
        # If the folder disappears mid-run, recreate it and log the issue.
        log_error(f"Inbox folder disappeared — recreating: {INBOX_DIR}")
        os.makedirs(INBOX_DIR, exist_ok=True)
        return set()


def create_task_file(filename):
    """
    Given the name of a new Inbox file, create a matching Markdown task
    file inside the Needs_Action folder.

    The task filename is prefixed with 'task_' to avoid collisions and
    always ends in '.md' so it renders nicely in any Markdown viewer.
    """
    # Generate a timestamp once so the filename and the content match.
    now = datetime.now(timezone.utc)
    timestamp = now.strftime("%Y-%m-%d %H:%M:%S UTC")

    # Build a filesystem-safe task filename.
    # Example: "report.pdf" -> "task_report_pdf.md"
    safe_name = filename.replace(".", "_").replace(" ", "_")
    task_filename = f"task_{safe_name}.md"
    task_path = os.path.join(NEEDS_ACTION_DIR, task_filename)

    # Compose the Markdown content using the structured task template format.
    # See Plans/task_template.md for the reusable base template.
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
- Detected by: file_watcher.py
"""

    # Write the task file to disk.
    with open(task_path, "w", encoding="utf-8") as f:
        f.write(content)

    print(f"[TASK CREATED] {task_filename}  <--  {filename}")


# ---------------------------------------------------------------------------
# Main loop
# ---------------------------------------------------------------------------

def main():
    """
    Core watcher loop.

    1. Ensure required folders exist (auto-create if missing).
    2. Take a snapshot of the Inbox on startup — these are "already known" files.
    3. Every POLL_INTERVAL seconds, check again.
    4. Any filename that appears in the new snapshot but NOT in 'seen_files'
       is brand-new, so we create a task for it.
    5. Add it to 'seen_files' so we never create a duplicate task.
    6. If anything goes wrong, log the error and keep running.
    """

    # --- Step 1: Make sure all folders are in place before we start. ---
    ensure_folders_exist()

    print("=" * 50)
    print("  Bronze Tier — Inbox Watcher")
    print("=" * 50)
    print(f"  Watching : {INBOX_DIR}")
    print(f"  Tasks to : {NEEDS_ACTION_DIR}")
    print(f"  Errors   : {ERROR_LOG_PATH}")
    print(f"  Interval : every {POLL_INTERVAL}s")
    print("=" * 50)
    print("Press Ctrl+C to stop.\n")

    # Record every file we've already seen so we don't create duplicate tasks.
    seen_files = get_inbox_files()

    if seen_files:
        print(f"[STARTUP] Found {len(seen_files)} existing file(s) in Inbox — skipping them.")
    else:
        print("[STARTUP] Inbox is empty. Waiting for new files...")

    # --- Step 2: Loop forever until the user presses Ctrl+C. ---
    try:
        while True:
            time.sleep(POLL_INTERVAL)

            # Wrap each poll cycle in its own try/except so a single error
            # (e.g. a permission issue on one file) doesn't kill the whole
            # watcher. The loop continues and retries on the next cycle.
            try:
                current_files = get_inbox_files()

                # New files = anything in current snapshot that we haven't seen.
                new_files = current_files - seen_files

                for filename in sorted(new_files):
                    try:
                        create_task_file(filename)
                    except Exception as file_err:
                        # If one file fails, log it and move on to the next.
                        log_error(
                            f"Failed to create task for '{filename}': {file_err}"
                        )

                # Update our memory so these files won't trigger again.
                seen_files = seen_files | current_files

            except Exception as poll_err:
                # Something unexpected went wrong in this poll cycle.
                # Log the full traceback for debugging, then continue.
                log_error(
                    f"Error during poll cycle: {poll_err}\n"
                    f"  Traceback: {traceback.format_exc()}"
                )

    except KeyboardInterrupt:
        # Graceful shutdown when the user presses Ctrl+C.
        print("\n[STOPPED] Watcher shut down.")


# ---------------------------------------------------------------------------
# Entry point — this block runs only when you execute the script directly.
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    main()
