"""
process_tasks.py — Bronze Tier "Process Tasks" Agent Skill

Reads every task file in Needs_Action/, marks it as completed,
moves it to Done/, then updates Dashboard.md and System_Log.md.

Usage:
    python process_tasks.py
"""

import os
import re
import shutil
from datetime import datetime, timezone


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
NEEDS_ACTION_DIR = os.path.join(SCRIPT_DIR, "Needs_Action")
DONE_DIR = os.path.join(SCRIPT_DIR, "Done")
DASHBOARD_PATH = os.path.join(SCRIPT_DIR, "Dashboard.md")
SYSTEM_LOG_PATH = os.path.join(SCRIPT_DIR, "Logs", "System_Log.md")


# ---------------------------------------------------------------------------
# Step 1 — Discover task files in Needs_Action
# ---------------------------------------------------------------------------

def get_task_files():
    """Return a sorted list of filenames in the Needs_Action folder."""
    try:
        files = [f for f in os.listdir(NEEDS_ACTION_DIR)
                 if os.path.isfile(os.path.join(NEEDS_ACTION_DIR, f))]
        return sorted(files)
    except FileNotFoundError:
        print("[WARNING] Needs_Action folder not found.")
        return []


# ---------------------------------------------------------------------------
# Step 2 — Read and parse a task file
# ---------------------------------------------------------------------------

def parse_task(filepath):
    """
    Read a task file and extract its front-matter fields.
    Returns a dict with keys like 'type', 'status', 'filename', etc.
    Also returns the full raw content for later modification.
    """
    with open(filepath, "r", encoding="utf-8") as f:
        content = f.read()

    metadata = {}

    # Extract YAML-style front matter between --- delimiters.
    front_matter_match = re.search(r"^---\s*\n(.*?)\n---", content, re.DOTALL)
    if front_matter_match:
        for line in front_matter_match.group(1).splitlines():
            if ":" in line:
                key, value = line.split(":", 1)
                metadata[key.strip()] = value.strip()

    # Derive a human-readable filename for dashboard/log display.
    # Priority: source_file > first entry in related_files > task filename.
    if "filename" not in metadata:
        if "source_file" in metadata:
            metadata["filename"] = metadata["source_file"]
        elif "related_files" in metadata:
            # related_files looks like: ["notes.txt"] — extract first entry.
            rf_match = re.search(r'"([^"]+)"', metadata["related_files"])
            if rf_match:
                metadata["filename"] = rf_match.group(1)
        if "filename" not in metadata:
            # Fallback: derive from task filepath (strip "task_" prefix, etc.)
            metadata["filename"] = os.path.basename(filepath)

    return metadata, content


# ---------------------------------------------------------------------------
# Step 3 — Mark the task as completed inside the file
# ---------------------------------------------------------------------------

def mark_completed(content):
    """
    Update the task file content:
      - Change 'status: pending' to 'status: completed'
      - Check off all Markdown checkboxes: [ ] -> [x]
    Returns the modified content string.
    """
    # Update front-matter status.
    content = content.replace("status: pending", "status: completed", 1)

    # Check off every checkbox in the body.
    content = content.replace("- [ ]", "- [x]")

    return content


# ---------------------------------------------------------------------------
# Step 4 — Move the completed task file to Done
# ---------------------------------------------------------------------------

def move_to_done(task_filename, updated_content):
    """
    Write the updated (completed) content into Done/ and remove the
    original from Needs_Action/.
    """
    source = os.path.join(NEEDS_ACTION_DIR, task_filename)
    destination = os.path.join(DONE_DIR, task_filename)

    # If a file with the same name already exists in Done, add a timestamp
    # suffix so we never overwrite previous work.
    if os.path.exists(destination):
        name, ext = os.path.splitext(task_filename)
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
        destination = os.path.join(DONE_DIR, f"{name}_{timestamp}{ext}")

    # Write the updated content to Done.
    with open(destination, "w", encoding="utf-8") as f:
        f.write(updated_content)

    # Remove the original from Needs_Action.
    os.remove(source)

    return os.path.basename(destination)


# ---------------------------------------------------------------------------
# Step 5 — Update Dashboard.md
# ---------------------------------------------------------------------------

def update_dashboard(completed_tasks):
    """
    For each completed task:
      - Add a row under "Completed Tasks"
      - Remove its row from "Pending Tasks" if present
    """
    with open(DASHBOARD_PATH, "r", encoding="utf-8") as f:
        content = f.read()

    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    # --- Remove the placeholder row if it's still there ---
    content = content.replace(
        "| *(no completed tasks yet)* | — | — |\n", ""
    )

    # --- Build new completed-task rows ---
    new_rows = ""
    for task in completed_tasks:
        filename = task.get("filename", "unknown")
        task_type = task.get("type", "task")
        new_rows += f"| {filename} | {now} | {task_type} — processed by agent |\n"

    # Insert the new rows right after the Completed Tasks table header.
    # The header line is: |------|--------------|-------|
    completed_header = "|------|--------------|-------|\n"
    content = content.replace(
        completed_header,
        completed_header + new_rows,
        1  # Only replace the first occurrence (the Completed table).
    )

    # --- Clean up Pending Tasks ---
    # Remove rows for any file that was just completed.
    for task in completed_tasks:
        filename = task.get("filename", "unknown")
        # Match any table row that contains this filename.
        pattern = rf"\| *{re.escape(filename)} *\|[^\n]*\n"
        # Only search in the Pending section (before "## Completed Tasks").
        pending_section_end = content.find("## Completed Tasks")
        if pending_section_end != -1:
            pending_section = content[:pending_section_end]
            cleaned = re.sub(pattern, "", pending_section)
            content = cleaned + content[pending_section_end:]

    with open(DASHBOARD_PATH, "w", encoding="utf-8") as f:
        f.write(content)


# ---------------------------------------------------------------------------
# Step 6 — Append to System_Log.md
# ---------------------------------------------------------------------------

def update_system_log(completed_tasks):
    """Add one log entry per completed task to the Activity Log table."""
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    new_entries = ""
    for task in completed_tasks:
        filename = task.get("filename", "unknown")
        task_type = task.get("type", "task")
        new_entries += (
            f"| {now} | Task completed | "
            f"Processed {task_type} for `{filename}` — moved to Done. |\n"
        )

    with open(SYSTEM_LOG_PATH, "r", encoding="utf-8") as f:
        content = f.read()

    # Append new rows at the end of the file (end of the table).
    content = content.rstrip("\n") + "\n" + new_entries

    with open(SYSTEM_LOG_PATH, "w", encoding="utf-8") as f:
        f.write(content)


# ---------------------------------------------------------------------------
# Main — orchestrate the full workflow
# ---------------------------------------------------------------------------

def main():
    print("=" * 50)
    print("  Bronze Tier — Process Tasks")
    print("=" * 50)

    task_files = get_task_files()

    if not task_files:
        print("\n[INFO] No task files found in Needs_Action. Nothing to process.")
        return

    print(f"\n[INFO] Found {len(task_files)} task(s) to process.\n")

    completed_tasks = []

    for task_filename in task_files:
        filepath = os.path.join(NEEDS_ACTION_DIR, task_filename)

        # Read and parse the task.
        metadata, content = parse_task(filepath)
        print(f"  [READ]      {task_filename}")
        print(f"              type={metadata.get('type', '?')}  "
              f"status={metadata.get('status', '?')}  "
              f"file={metadata.get('filename', '?')}")

        # Mark it as completed.
        updated_content = mark_completed(content)
        print(f"  [COMPLETED] status -> completed, checkboxes checked")

        # Move to Done.
        done_name = move_to_done(task_filename, updated_content)
        print(f"  [MOVED]     Needs_Action -> Done/{done_name}")
        print()

        # Collect metadata for dashboard/log updates.
        completed_tasks.append(metadata)

    # Update Dashboard and System Log once with all results.
    update_dashboard(completed_tasks)
    print("[UPDATED] Dashboard.md")

    update_system_log(completed_tasks)
    print("[UPDATED] Logs/System_Log.md")

    print(f"\nDone. {len(completed_tasks)} task(s) processed successfully.")


if __name__ == "__main__":
    main()
