"""
move_task.py — Manage task file workflow across vault folders.

Moves files between Inbox/, Needs_Action/, and Done/.
Logs every action to logs/actions.log.

Usage:
    python move_task.py --file task.md --from Inbox --to Needs_Action
    python move_task.py --list Inbox
    python move_task.py --archive
"""

import argparse
import os
import shutil
import sys
from datetime import datetime, timezone

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
# Walk up: scripts/ -> vault-file-manager/ -> skills/ -> .claude/ -> VAULT_ROOT
VAULT_ROOT = os.path.abspath(os.path.join(SCRIPT_DIR, "..", "..", "..", ".."))

VALID_FOLDERS = {"Inbox", "Needs_Action", "Done", "Needs_Approval"}
LOGS_DIR = os.path.join(VAULT_ROOT, "Logs")
ACTIONS_LOG = os.path.join(LOGS_DIR, "actions.log")


def _now_str():
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")


def log_action(message):
    entry = f"[{_now_str()}] [vault-file-manager] {message}"
    print(entry)
    try:
        os.makedirs(LOGS_DIR, exist_ok=True)
        with open(ACTIONS_LOG, "a", encoding="utf-8") as f:
            f.write(entry + "\n")
    except OSError:
        pass


def resolve_folder(name):
    """Map a folder name to its absolute path. Returns None if invalid."""
    if name not in VALID_FOLDERS:
        return None
    path = os.path.join(VAULT_ROOT, name)
    os.makedirs(path, exist_ok=True)
    return path


def safe_destination(dest_dir, filename):
    """Return a path in dest_dir that won't overwrite an existing file."""
    dest = os.path.join(dest_dir, filename)
    if not os.path.exists(dest):
        return dest
    name, ext = os.path.splitext(filename)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
    return os.path.join(dest_dir, f"{name}_{stamp}{ext}")


def move_file(filename, src_name, dst_name):
    """Move a single file between folders. Returns (success, message)."""
    src_dir = resolve_folder(src_name)
    dst_dir = resolve_folder(dst_name)

    if not src_dir:
        return False, f"Invalid source folder: {src_name}. Valid: {', '.join(sorted(VALID_FOLDERS))}"
    if not dst_dir:
        return False, f"Invalid destination folder: {dst_name}. Valid: {', '.join(sorted(VALID_FOLDERS))}"
    if src_name == dst_name:
        return False, "Source and destination are the same folder."

    src_path = os.path.join(src_dir, filename)
    if not os.path.isfile(src_path):
        return False, f"File not found: {src_name}/{filename}"

    dst_path = safe_destination(dst_dir, filename)

    try:
        shutil.move(src_path, dst_path)
    except OSError as err:
        return False, f"Move failed: {err}"

    dst_basename = os.path.basename(dst_path)
    return True, f"MOVED: {filename} from {src_name}/ to {dst_name}/{dst_basename}"


def list_folder(folder_name):
    """List files in a vault folder."""
    folder_dir = resolve_folder(folder_name)
    if not folder_dir:
        print(f"ERROR: Invalid folder: {folder_name}. Valid: {', '.join(sorted(VALID_FOLDERS))}")
        sys.exit(1)

    try:
        files = sorted(
            f for f in os.listdir(folder_dir)
            if os.path.isfile(os.path.join(folder_dir, f))
        )
    except OSError:
        files = []

    print(f"{folder_name}/ ({len(files)} file{'s' if len(files) != 1 else ''}):")
    if files:
        for f in files:
            size = os.path.getsize(os.path.join(folder_dir, f))
            print(f"  {f}  ({size:,} bytes)")
    else:
        print("  (empty)")


def archive_all():
    """Move all files from Needs_Action/ to Done/."""
    na_dir = resolve_folder("Needs_Action")
    try:
        files = sorted(
            f for f in os.listdir(na_dir)
            if os.path.isfile(os.path.join(na_dir, f))
        )
    except OSError:
        files = []

    if not files:
        print("Needs_Action/ is empty. Nothing to archive.")
        return

    moved = 0
    for filename in files:
        success, message = move_file(filename, "Needs_Action", "Done")
        if success:
            log_action(message)
            moved += 1
        else:
            log_action(f"[ERROR] {message}")

    print(f"Archived {moved}/{len(files)} file(s) to Done/.")


def main():
    parser = argparse.ArgumentParser(description="Vault File Manager — move tasks between folders")
    parser.add_argument("--file", type=str, help="Filename to move")
    parser.add_argument("--from", dest="src", type=str, help="Source folder name")
    parser.add_argument("--to", dest="dst", type=str, help="Destination folder name")
    parser.add_argument("--list", dest="list_folder", type=str, metavar="FOLDER",
                        help="List files in a folder")
    parser.add_argument("--archive", action="store_true",
                        help="Move all Needs_Action files to Done")
    args = parser.parse_args()

    if args.list_folder:
        list_folder(args.list_folder)
        return

    if args.archive:
        archive_all()
        return

    if not args.file or not args.src or not args.dst:
        parser.error("--file, --from, and --to are all required for move operations.")

    success, message = move_file(args.file, args.src, args.dst)
    if success:
        log_action(message)
        print(f"SUCCESS: {message}")
    else:
        print(f"ERROR: {message}")
        sys.exit(1)


if __name__ == "__main__":
    main()
