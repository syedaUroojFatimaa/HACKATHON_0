"""
setup_scheduler.py — Register the Silver Scheduler with the OS.

On Windows: Creates a Windows Task Scheduler task.
On Linux/Mac: Generates a crontab entry.

Usage:
    python scripts/setup_scheduler.py --install          # register with OS scheduler
    python scripts/setup_scheduler.py --uninstall        # remove OS scheduler entry
    python scripts/setup_scheduler.py --status           # check if registered
    python scripts/setup_scheduler.py --interval 5       # run every N minutes (default 5)
"""

import argparse
import os
import platform
import subprocess
import sys

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
VAULT_ROOT = os.path.dirname(SCRIPT_DIR)
SCHEDULER_SCRIPT = os.path.join(SCRIPT_DIR, "run_ai_employee.py")
PYTHON_PATH = sys.executable

TASK_NAME = "SilverTierAIEmployee"

# ---------------------------------------------------------------------------
# Windows Task Scheduler
# ---------------------------------------------------------------------------

def win_install(interval_minutes):
    """Create a Windows Task Scheduler task that runs every N minutes."""
    cmd = [
        "schtasks", "/create",
        "/tn", TASK_NAME,
        "/tr", f'"{PYTHON_PATH}" "{SCHEDULER_SCRIPT}" --once',
        "/sc", "MINUTE",
        "/mo", str(interval_minutes),
        "/f",  # force overwrite if exists
    ]

    try:
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode == 0:
            print(f"SUCCESS: Task '{TASK_NAME}' created.")
            print(f"  Runs every {interval_minutes} minute(s).")
            print(f"  Command: python {SCHEDULER_SCRIPT} --once")
            print(f"\n  To view: schtasks /query /tn {TASK_NAME}")
            print(f"  To remove: python scripts/setup_scheduler.py --uninstall")
            return True
        else:
            print(f"ERROR: schtasks failed: {result.stderr.strip()}")
            return False
    except FileNotFoundError:
        print("ERROR: schtasks command not found. Run as Administrator.")
        return False


def win_uninstall():
    """Remove the Windows Task Scheduler task."""
    cmd = ["schtasks", "/delete", "/tn", TASK_NAME, "/f"]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode == 0:
            print(f"SUCCESS: Task '{TASK_NAME}' removed.")
            return True
        else:
            print(f"ERROR: {result.stderr.strip()}")
            return False
    except FileNotFoundError:
        print("ERROR: schtasks command not found.")
        return False


def win_status():
    """Check if the task exists in Windows Task Scheduler."""
    cmd = ["schtasks", "/query", "/tn", TASK_NAME, "/fo", "LIST"]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode == 0:
            print(f"REGISTERED: Task '{TASK_NAME}' is active.\n")
            print(result.stdout.strip())
            return True
        else:
            print(f"NOT REGISTERED: Task '{TASK_NAME}' does not exist.")
            return False
    except FileNotFoundError:
        print("ERROR: schtasks command not found.")
        return False

# ---------------------------------------------------------------------------
# Linux/Mac Cron
# ---------------------------------------------------------------------------

def _cron_line(interval_minutes):
    return f"*/{interval_minutes} * * * * {PYTHON_PATH} {SCHEDULER_SCRIPT} --once  # {TASK_NAME}"


def unix_install(interval_minutes):
    """Add a crontab entry."""
    new_line = _cron_line(interval_minutes)

    try:
        result = subprocess.run(["crontab", "-l"], capture_output=True, text=True)
        existing = result.stdout if result.returncode == 0 else ""
    except FileNotFoundError:
        print("ERROR: crontab command not found.")
        return False

    # Remove old entry if present.
    lines = [l for l in existing.strip().splitlines() if TASK_NAME not in l]
    lines.append(new_line)
    new_crontab = "\n".join(lines) + "\n"

    try:
        proc = subprocess.run(["crontab", "-"], input=new_crontab, capture_output=True, text=True)
        if proc.returncode == 0:
            print(f"SUCCESS: Cron entry added.")
            print(f"  Runs every {interval_minutes} minute(s).")
            print(f"  Entry: {new_line}")
            print(f"\n  To view: crontab -l")
            print(f"  To remove: python scripts/setup_scheduler.py --uninstall")
            return True
        else:
            print(f"ERROR: crontab failed: {proc.stderr.strip()}")
            return False
    except FileNotFoundError:
        print("ERROR: crontab command not found.")
        return False


def unix_uninstall():
    """Remove the crontab entry."""
    try:
        result = subprocess.run(["crontab", "-l"], capture_output=True, text=True)
        if result.returncode != 0:
            print("No crontab found.")
            return True
    except FileNotFoundError:
        print("ERROR: crontab command not found.")
        return False

    lines = [l for l in result.stdout.strip().splitlines() if TASK_NAME not in l]
    new_crontab = "\n".join(lines) + "\n" if lines else ""

    proc = subprocess.run(["crontab", "-"], input=new_crontab, capture_output=True, text=True)
    if proc.returncode == 0:
        print(f"SUCCESS: Cron entry for '{TASK_NAME}' removed.")
        return True
    else:
        print(f"ERROR: {proc.stderr.strip()}")
        return False


def unix_status():
    """Check if cron entry exists."""
    try:
        result = subprocess.run(["crontab", "-l"], capture_output=True, text=True)
        if result.returncode == 0 and TASK_NAME in result.stdout:
            for line in result.stdout.splitlines():
                if TASK_NAME in line:
                    print(f"REGISTERED: {line}")
            return True
        else:
            print(f"NOT REGISTERED: No cron entry for '{TASK_NAME}'.")
            return False
    except FileNotFoundError:
        print("ERROR: crontab command not found.")
        return False

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Register Silver Scheduler with OS task scheduler")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--install", action="store_true", help="Register scheduler task")
    group.add_argument("--uninstall", action="store_true", help="Remove scheduler task")
    group.add_argument("--status", action="store_true", help="Check registration status")
    parser.add_argument("--interval", type=int, default=5,
                        help="Run interval in minutes (default: 5)")
    args = parser.parse_args()

    is_windows = platform.system() == "Windows"

    print("=" * 55)
    print(f"  Silver Scheduler — OS Registration ({'Windows' if is_windows else 'Unix'})")
    print("=" * 55)

    if args.install:
        interval = max(1, args.interval)
        if is_windows:
            ok = win_install(interval)
        else:
            ok = unix_install(interval)
        sys.exit(0 if ok else 1)

    if args.uninstall:
        if is_windows:
            ok = win_uninstall()
        else:
            ok = unix_uninstall()
        sys.exit(0 if ok else 1)

    if args.status:
        if is_windows:
            ok = win_status()
        else:
            ok = unix_status()
        sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
