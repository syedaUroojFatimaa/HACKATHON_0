"""
log_manager.py — Bronze Tier Log Rotation

Prevents log files from growing forever by checking their size
and rotating them when they exceed 1 MB.

Rotation means:
  1. Rename the oversized file with a date suffix (e.g. System_Log_2026-01-29.md)
  2. Create a fresh empty file with the original name so logging can continue.

Monitored files:
  - Logs/System_Log.md
  - Logs/watcher_errors.log

No external dependencies — uses only the Python standard library.

Usage:
    python log_manager.py
"""

import os
from datetime import datetime, timezone


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
LOGS_DIR = os.path.join(SCRIPT_DIR, "Logs")

# Maximum file size in bytes before rotation kicks in.
# 1 MB = 1,048,576 bytes.
MAX_SIZE_BYTES = 1 * 1024 * 1024

# Each entry is a tuple: (file path, header for the fresh replacement).
# The header is written into the new empty file so it keeps the expected
# Markdown structure. Plain-text logs get a simple title line instead.
LOG_FILES = [
    (
        os.path.join(LOGS_DIR, "System_Log.md"),
        # Fresh header that matches the original System_Log.md structure.
        (
            "# System Log\n"
            "\n"
            "> Chronological record of all significant activity in the vault.\n"
            "\n"
            "---\n"
            "\n"
            "## Activity Log\n"
            "\n"
            "| Timestamp | Action | Details |\n"
            "|-----------|--------|---------|"
        ),
    ),
    (
        os.path.join(LOGS_DIR, "watcher_errors.log"),
        # Plain-text logs just need a title line.
        "# Watcher Error Log",
    ),
]


# ---------------------------------------------------------------------------
# Rotation logic
# ---------------------------------------------------------------------------

def get_archive_path(original_path):
    """
    Build the archive filename by inserting today's date before the extension.

    Example:
        System_Log.md  -->  System_Log_2026-01-29.md

    If an archive with that name already exists (ran twice in one day),
    append an incrementing number to avoid overwriting it.
    """
    directory = os.path.dirname(original_path)
    basename = os.path.basename(original_path)

    # Split "System_Log.md" into ("System_Log", ".md").
    name, ext = os.path.splitext(basename)
    date_stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    archive_name = f"{name}_{date_stamp}{ext}"
    archive_path = os.path.join(directory, archive_name)

    # Handle the edge case where the archive already exists.
    counter = 2
    while os.path.exists(archive_path):
        archive_name = f"{name}_{date_stamp}_{counter}{ext}"
        archive_path = os.path.join(directory, archive_name)
        counter += 1

    return archive_path


def rotate_log(file_path, fresh_header):
    """
    Rotate a single log file:
      1. Rename the current file to an archive name with today's date.
      2. Create a new file at the original path with the fresh header.
    """
    archive_path = get_archive_path(file_path)

    # Rename the old file to the archive path.
    os.rename(file_path, archive_path)
    print(f"  [ARCHIVED]  {os.path.basename(file_path)}  -->  {os.path.basename(archive_path)}")

    # Create a fresh replacement with the proper header.
    with open(file_path, "w", encoding="utf-8") as f:
        f.write(fresh_header + "\n")
    print(f"  [CREATED]   Fresh {os.path.basename(file_path)}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    print("=" * 50)
    print("  Bronze Tier — Log Manager")
    print("=" * 50)
    print(f"  Max size : {MAX_SIZE_BYTES / (1024 * 1024):.0f} MB")
    print(f"  Logs dir : {LOGS_DIR}")
    print("=" * 50)
    print()

    rotated_count = 0

    for file_path, fresh_header in LOG_FILES:
        basename = os.path.basename(file_path)

        # Skip files that don't exist yet (e.g. watcher_errors.log is only
        # created when an error actually occurs).
        if not os.path.exists(file_path):
            print(f"  [SKIP]  {basename}  (file does not exist)")
            continue

        # Check the file size.
        size_bytes = os.path.getsize(file_path)
        size_kb = size_bytes / 1024

        if size_bytes > MAX_SIZE_BYTES:
            print(f"  [ROTATE]  {basename}  ({size_kb:.1f} KB > {MAX_SIZE_BYTES // 1024} KB limit)")
            rotate_log(file_path, fresh_header)
            rotated_count += 1
        else:
            print(f"  [OK]    {basename}  ({size_kb:.1f} KB — within limit)")

    print()
    if rotated_count:
        print(f"Done. Rotated {rotated_count} file(s).")
    else:
        print("Done. All logs are within the size limit. No rotation needed.")


if __name__ == "__main__":
    main()
