"""
error_recovery.py — Error Recovery Agent Skill

Monitors Needs_Action/ for stuck/failed tasks and applies an automatic
quarantine-and-retry cycle:

  1. DETECT  — Files stuck in Needs_Action/ for >= STUCK_THRESHOLD_MINUTES
               are treated as failed.
  2. LOG     — Structured entry written to Logs/errors.log.
  3. QUARANTINE — File is annotated (front-matter) and moved to Errors/.
  4. RETRY   — After RETRY_DELAY_SECONDS (5 min), file is moved back to
               Needs_Action/ and the scheduler processes it again.
  5. EXHAUST — After MAX_RETRIES (3) failed attempts the file stays in
               Errors/ and is marked exhausted. Manual intervention needed.

State file   : Logs/.error_recovery_state.json
Error log    : Logs/errors.log
Actions log  : Logs/actions.log
Quarantine   : Errors/

Modes:
  --run        Scan for stuck tasks + process all pending retries  [scheduler]
  --scan       Only scan Needs_Action/ and quarantine stuck files
  --retry      Only process pending retries from Errors/
  --log-error  Manually quarantine a specific file with a reason
  --status     Show quarantine/exhausted counts and next retry times
  --report     Full report: status + last 20 errors.log entries

Usage:
  python error_recovery.py --run
  python error_recovery.py --scan
  python error_recovery.py --retry
  python error_recovery.py --log-error --file task_foo.md --reason "planner failed"
  python error_recovery.py --status
  python error_recovery.py --report

Exit codes:
  0 — success
  1 — fatal error (e.g., cannot write state file)
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import sys
from datetime import datetime, timedelta, timezone

# ── stdout encoding fix (Windows cp1252 terminals) ────────────────────────────
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

# ── Paths ─────────────────────────────────────────────────────────────────────
_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
# .claude/skills/error-recovery/scripts/ -> vault root (4 levels up)
VAULT_ROOT = os.path.abspath(os.path.join(_SCRIPT_DIR, "..", "..", "..", ".."))

NEEDS_ACTION_DIR = os.path.join(VAULT_ROOT, "Needs_Action")
ERRORS_DIR       = os.path.join(VAULT_ROOT, "Errors")
LOGS_DIR         = os.path.join(VAULT_ROOT, "Logs")

ERRORS_LOG  = os.path.join(LOGS_DIR, "errors.log")
ACTIONS_LOG = os.path.join(LOGS_DIR, "actions.log")
STATE_FILE  = os.path.join(LOGS_DIR, ".error_recovery_state.json")

# ── Tunables ──────────────────────────────────────────────────────────────────
STUCK_THRESHOLD_MINUTES = 15     # task is "stuck" after this many minutes
RETRY_DELAY_SECONDS     = 300    # 5-minute retry window
MAX_RETRIES             = 3      # attempts before exhaustion

# ── Time helpers ──────────────────────────────────────────────────────────────

def _now() -> datetime:
    return datetime.now(timezone.utc)

def _now_str() -> str:
    return _now().strftime("%Y-%m-%d %H:%M:%S UTC")

def _ts() -> str:
    return _now().strftime("%Y%m%d_%H%M%S")

# ── Logging ───────────────────────────────────────────────────────────────────

def _write_errors_log(entry_type: str, message: str) -> None:
    """
    Append a structured line to Logs/errors.log.
    Format: [YYYY-MM-DD HH:MM:SS UTC] [TYPE] message
    """
    os.makedirs(LOGS_DIR, exist_ok=True)
    line = f"[{_now_str()}] [{entry_type:12s}] {message}"
    try:
        with open(ERRORS_LOG, "a", encoding="utf-8") as fh:
            fh.write(line + "\n")
    except OSError:
        pass
    print(f"[error-recovery] {line}")


def _write_actions_log(message: str) -> None:
    """Append to Logs/actions.log (best-effort)."""
    try:
        with open(ACTIONS_LOG, "a", encoding="utf-8") as fh:
            fh.write(f"[{_now_str()}] [error-recovery] {message}\n")
    except OSError:
        pass

# ── State management ──────────────────────────────────────────────────────────

def _load_state() -> dict:
    if not os.path.isfile(STATE_FILE):
        return {"quarantined": {}, "exhausted": {}}
    try:
        with open(STATE_FILE, encoding="utf-8") as fh:
            data = json.load(fh)
        data.setdefault("quarantined", {})
        data.setdefault("exhausted", {})
        return data
    except (json.JSONDecodeError, OSError):
        return {"quarantined": {}, "exhausted": {}}


def _save_state(state: dict) -> None:
    os.makedirs(LOGS_DIR, exist_ok=True)
    tmp = STATE_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(state, fh, indent=2)
    os.replace(tmp, STATE_FILE)   # atomic on all platforms

# ── Front-matter injection ────────────────────────────────────────────────────

def _inject_frontmatter(content: str, fields: dict) -> str:
    """
    Add or update key-value pairs in the YAML front-matter block.
    Handles files with no front-matter gracefully (prepends one).
    """
    lines = content.split("\n")

    if not lines or lines[0].strip() != "---":
        # No front-matter: prepend a minimal one
        fm = ["---"] + [f"{k}: {v}" for k, v in fields.items()] + ["---", ""]
        return "\n".join(fm) + content

    # Locate the closing ---
    fm_end = -1
    for i in range(1, len(lines)):
        if lines[i].strip() == "---":
            fm_end = i
            break
    if fm_end == -1:
        return content  # malformed front-matter, leave untouched

    fm_body = lines[1:fm_end]

    # Add or update each field
    for k, v in fields.items():
        pat = re.compile(rf"^{re.escape(k)}\s*:")
        updated = False
        for j, line in enumerate(fm_body):
            if pat.match(line):
                fm_body[j] = f"{k}: {v}"
                updated = True
                break
        if not updated:
            fm_body.append(f"{k}: {v}")

    return "\n".join(["---"] + fm_body + ["---"] + lines[fm_end + 1:])


def _read_frontmatter_field(file_path: str, field: str) -> str | None:
    """Read a single field from a file's front-matter. Returns None if absent."""
    try:
        with open(file_path, encoding="utf-8", errors="replace") as fh:
            head = fh.read(3000)
    except OSError:
        return None
    m = re.search(rf"^{re.escape(field)}\s*:\s*(.+)$", head, re.MULTILINE)
    return m.group(1).strip() if m else None

# ── Safe path utilities ───────────────────────────────────────────────────────

def _unique_path(directory: str, filename: str) -> str:
    """Return a path in directory that won't overwrite an existing file."""
    os.makedirs(directory, exist_ok=True)
    dest = os.path.join(directory, filename)
    if not os.path.exists(dest):
        return dest
    name, ext = os.path.splitext(filename)
    return os.path.join(directory, f"{name}_{_ts()}{ext}")

# ── Core operations ───────────────────────────────────────────────────────────

def quarantine_file(original_name: str, src_path: str, reason: str, attempt: int) -> bool:
    """
    Move a file from its current location to Errors/.
    Annotates front-matter with error metadata.
    Logs to errors.log and actions.log.
    Updates state file.
    Returns True on success.
    """
    if not os.path.isfile(src_path):
        _write_errors_log("WARN", f"Quarantine skipped: {original_name} not found at {src_path}")
        return False

    now       = _now()
    retry_at  = now + timedelta(seconds=RETRY_DELAY_SECONDS)

    # Read content
    try:
        with open(src_path, encoding="utf-8", errors="replace") as fh:
            content = fh.read()
    except OSError as exc:
        _write_errors_log("ERROR", f"Cannot read {original_name}: {exc}")
        return False

    # Annotate front-matter
    annotated = _inject_frontmatter(content, {
        "status":               "error",
        "error_reason":         reason,
        "error_quarantined_at": now.strftime("%Y-%m-%d %H:%M:%S UTC"),
        "error_attempt":        str(attempt),
        "error_retry_at":       retry_at.strftime("%Y-%m-%d %H:%M:%S UTC"),
    })

    # Determine destination path (may get timestamp suffix if collision)
    dest_path     = _unique_path(ERRORS_DIR, original_name)
    errors_fname  = os.path.basename(dest_path)

    # Write annotated content then move atomically
    try:
        with open(src_path, "w", encoding="utf-8") as fh:
            fh.write(annotated)
        shutil.move(src_path, dest_path)
    except OSError as exc:
        _write_errors_log("ERROR", f"Failed to move {original_name} to Errors/: {exc}")
        return False

    _write_errors_log(
        "QUARANTINE",
        f"file={original_name} | reason={reason} | "
        f"attempt={attempt}/{MAX_RETRIES} | "
        f"retry_at={retry_at.strftime('%Y-%m-%d %H:%M:%S UTC')}"
    )
    _write_actions_log(f"QUARANTINE | file={original_name} | attempt={attempt} | reason={reason}")

    # Persist to state
    state = _load_state()
    state["quarantined"][original_name] = {
        "original_name":  original_name,
        "errors_filename": errors_fname,
        "quarantined_at": now.isoformat(),
        "retry_at":       retry_at.isoformat(),
        "attempt":        attempt,
        "reason":         reason,
    }
    _save_state(state)
    return True


def retry_file(original_name: str, entry: dict) -> bool:
    """
    Move a quarantined file from Errors/ back to Needs_Action/.
    Updates its front-matter (status → pending, increments attempt counter).
    Logs the retry.
    Returns True on success.
    """
    errors_fname = entry.get("errors_filename", original_name)
    errors_path  = os.path.join(ERRORS_DIR, errors_fname)
    attempt      = entry.get("attempt", 1)
    new_attempt  = attempt + 1

    if not os.path.isfile(errors_path):
        _write_errors_log("WARN", f"Retry skipped: {errors_fname} not found in Errors/")
        # Remove stale entry from state
        state = _load_state()
        state["quarantined"].pop(original_name, None)
        _save_state(state)
        return False

    try:
        with open(errors_path, encoding="utf-8", errors="replace") as fh:
            content = fh.read()
    except OSError as exc:
        _write_errors_log("ERROR", f"Cannot read {errors_fname} for retry: {exc}")
        return False

    now          = _now()
    next_retry   = (now + timedelta(seconds=RETRY_DELAY_SECONDS)).strftime("%Y-%m-%d %H:%M:%S UTC")
    restored     = _inject_frontmatter(content, {
        "status":             "pending",
        "error_attempt":      str(new_attempt),
        "error_last_retry":   now.strftime("%Y-%m-%d %H:%M:%S UTC"),
        "error_retry_at":     next_retry,
    })

    dest_path  = _unique_path(NEEDS_ACTION_DIR, original_name)
    dest_fname = os.path.basename(dest_path)

    try:
        with open(errors_path, "w", encoding="utf-8") as fh:
            fh.write(restored)
        shutil.move(errors_path, dest_path)
    except OSError as exc:
        _write_errors_log("ERROR", f"Failed to move {errors_fname} back to Needs_Action/: {exc}")
        return False

    _write_errors_log(
        "RETRY",
        f"file={original_name} | attempt={new_attempt}/{MAX_RETRIES} | "
        f"moved_to=Needs_Action/{dest_fname}"
    )
    _write_actions_log(f"RETRY | file={original_name} | attempt={new_attempt}")

    # Remove from quarantined state (scan will re-add if it gets stuck again)
    state = _load_state()
    state["quarantined"].pop(original_name, None)
    _save_state(state)
    return True


def exhaust_file(original_name: str, entry: dict) -> None:
    """
    Mark a file as exhausted (max retries exceeded).
    Keeps the file in Errors/ but updates its front-matter.
    Moves the state entry from quarantined → exhausted.
    """
    errors_fname = entry.get("errors_filename", original_name)
    errors_path  = os.path.join(ERRORS_DIR, errors_fname)

    if os.path.isfile(errors_path):
        try:
            with open(errors_path, encoding="utf-8", errors="replace") as fh:
                content = fh.read()
            exhausted = _inject_frontmatter(content, {
                "status":               "error_exhausted",
                "error_exhausted_at":   _now_str(),
                "error_note":           "max retries reached - manual review required",
            })
            with open(errors_path, "w", encoding="utf-8") as fh:
                fh.write(exhausted)
        except OSError:
            pass

    _write_errors_log(
        "EXHAUSTED",
        f"file={original_name} | attempts={entry.get('attempt', MAX_RETRIES)}/{MAX_RETRIES} "
        f"| file remains in Errors/ | manual review required"
    )
    _write_actions_log(f"EXHAUSTED | file={original_name}")

    state = _load_state()
    state["quarantined"].pop(original_name, None)
    state["exhausted"][original_name] = {
        "original_name":  original_name,
        "errors_filename": errors_fname,
        "exhausted_at":   _now().isoformat(),
        "attempts":       entry.get("attempt", MAX_RETRIES),
        "reason":         entry.get("reason", "unknown"),
    }
    _save_state(state)

# ── Command implementations ───────────────────────────────────────────────────

def cmd_scan() -> int:
    """
    Scan Needs_Action/ for files older than STUCK_THRESHOLD_MINUTES.
    Quarantine each stuck file.
    Returns number of files quarantined.
    """
    os.makedirs(NEEDS_ACTION_DIR, exist_ok=True)

    state              = _load_state()
    already_quarantined = set(state["quarantined"].keys())

    threshold = timedelta(minutes=STUCK_THRESHOLD_MINUTES)
    now       = _now()
    count     = 0

    try:
        files = sorted(
            f for f in os.listdir(NEEDS_ACTION_DIR)
            if os.path.isfile(os.path.join(NEEDS_ACTION_DIR, f))
        )
    except OSError as exc:
        _write_errors_log("ERROR", f"Cannot scan Needs_Action/: {exc}")
        return 0

    for fname in files:
        if fname in already_quarantined:
            continue   # already being tracked

        fpath = os.path.join(NEEDS_ACTION_DIR, fname)
        try:
            mtime = os.path.getmtime(fpath)
            age   = now - datetime.fromtimestamp(mtime, timezone.utc)
        except OSError:
            continue

        if age <= threshold:
            continue   # too young — not stuck

        # Determine attempt count from existing front-matter (for re-stuck files)
        raw_attempt = _read_frontmatter_field(fpath, "error_attempt")
        try:
            attempt = int(raw_attempt) + 1 if raw_attempt else 1
        except ValueError:
            attempt = 1

        minutes_old = int(age.total_seconds() / 60)
        reason      = f"stuck ({minutes_old} min in Needs_Action)"
        ok          = quarantine_file(fname, fpath, reason, attempt=attempt)
        if ok:
            count += 1

    label = f"{count} stuck file(s) quarantined" if count else "no stuck files found"
    print(f"[error-recovery] Scan complete: {label}.")
    return count


def cmd_retry() -> int:
    """
    Process all pending retries whose retry_at time has passed.
    Files that exceed MAX_RETRIES are exhausted instead.
    Returns number of files retried (not including exhausted).
    """
    state      = _load_state()
    quarantined = state.get("quarantined", {})
    now        = _now()
    retried    = 0
    exhausted  = 0

    for original_name, entry in list(quarantined.items()):
        retry_at_str = entry.get("retry_at")
        if not retry_at_str:
            continue
        try:
            retry_at = datetime.fromisoformat(retry_at_str)
        except (ValueError, TypeError):
            continue

        if now < retry_at:
            continue   # not yet due

        attempt = entry.get("attempt", 1)

        if attempt >= MAX_RETRIES:
            exhaust_file(original_name, entry)
            exhausted += 1
        else:
            ok = retry_file(original_name, entry)
            if ok:
                retried += 1

    parts = []
    if retried:
        parts.append(f"{retried} retried")
    if exhausted:
        parts.append(f"{exhausted} exhausted")
    label = ", ".join(parts) if parts else "nothing due"
    print(f"[error-recovery] Retry pass complete: {label}.")
    return retried


def cmd_run() -> None:
    """
    Combined scan + retry — called by the scheduler on every cycle.
    Outputs a single summary line to stdout.
    """
    print("[error-recovery] Running error recovery cycle...")
    quarantined_n = cmd_scan()
    retried_n     = cmd_retry()

    state  = _load_state()
    q_n    = len(state["quarantined"])
    ex_n   = len(state["exhausted"])

    print(
        f"[error-recovery] Cycle done | "
        f"newly_quarantined={quarantined_n} | retried={retried_n} | "
        f"in_quarantine={q_n} | exhausted={ex_n}"
    )


def cmd_log_error(filename: str, reason: str, src_folder: str = "Needs_Action") -> None:
    """
    Manually quarantine a specific file with a given reason.
    Use when another skill explicitly detects a failure.
    """
    src_path = os.path.join(VAULT_ROOT, src_folder, filename)

    if not os.path.isfile(src_path):
        _write_errors_log(
            "WARN",
            f"file={filename} | source={src_folder} | reason={reason} | file not found, logging only"
        )
        print(f"[error-recovery] WARNING: {src_folder}/{filename} not found — logged only.")
        return

    state   = _load_state()
    prev    = state["quarantined"].get(filename, {})
    attempt = prev.get("attempt", 0) + 1

    ok = quarantine_file(filename, src_path, reason, attempt=attempt)
    if ok:
        print(f"[error-recovery] Quarantined: {filename} (attempt {attempt}/{MAX_RETRIES})")
    else:
        print(f"[error-recovery] ERROR: Failed to quarantine {filename}")
        sys.exit(1)


def cmd_status() -> None:
    """Print a concise status table."""
    state = _load_state()
    q     = state.get("quarantined", {})
    ex    = state.get("exhausted", {})

    log_lines = 0
    if os.path.isfile(ERRORS_LOG):
        try:
            with open(ERRORS_LOG, encoding="utf-8", errors="replace") as fh:
                log_lines = sum(1 for _ in fh)
        except OSError:
            pass

    print("=" * 60)
    print("  Error Recovery - Status")
    print("=" * 60)
    print(f"  Quarantined (pending retry)  : {len(q)}")
    print(f"  Exhausted (manual review)    : {len(ex)}")
    print(f"  errors.log total lines       : {log_lines}")
    print(f"  Threshold                    : {STUCK_THRESHOLD_MINUTES} min")
    print(f"  Retry delay                  : {RETRY_DELAY_SECONDS // 60} min")
    print(f"  Max retries                  : {MAX_RETRIES}")
    print(f"  Errors/                      : {ERRORS_DIR}")

    if q:
        print()
        print("  Quarantined files:")
        now = _now()
        for name, entry in sorted(q.items()):
            try:
                retry_at = datetime.fromisoformat(entry["retry_at"])
                wait_s   = max(0, (retry_at - now).total_seconds())
                eta      = f"retry in {int(wait_s)}s" if wait_s > 0 else "retry OVERDUE"
            except (ValueError, KeyError):
                eta = "unknown"
            att = entry.get("attempt", 1)
            print(f"    [{att}/{MAX_RETRIES}] {name}  ({eta})")
            print(f"           reason: {entry.get('reason', 'unknown')}")

    if ex:
        print()
        print("  Exhausted files (manual review needed):")
        for name, entry in sorted(ex.items()):
            print(f"    {name}  (attempts: {entry.get('attempts', '?')}) — {entry.get('reason','')}")

    print("=" * 60)


def cmd_report() -> None:
    """Full report: status table + last 20 errors.log entries."""
    cmd_status()

    if not os.path.isfile(ERRORS_LOG):
        print()
        print("  No errors.log yet — no failures recorded.")
        return

    print()
    print("  Recent entries from errors.log (last 20):")
    print("-" * 60)
    try:
        with open(ERRORS_LOG, encoding="utf-8", errors="replace") as fh:
            lines = fh.readlines()
        for line in lines[-20:]:
            print(f"  {line.rstrip()}")
    except OSError as exc:
        print(f"  (cannot read errors.log: {exc})")
    print("-" * 60)

# ── CLI ───────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        prog="error_recovery",
        description="Error Recovery — detect, quarantine, and retry failed vault tasks.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python error_recovery.py --run                                     # scheduler mode
  python error_recovery.py --scan                                    # quarantine only
  python error_recovery.py --retry                                   # process retries only
  python error_recovery.py --log-error --file task_foo.md --reason "planner crashed"
  python error_recovery.py --status
  python error_recovery.py --report
        """,
    )

    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--run",       action="store_true", help="Scan + retry combined [scheduler]")
    mode.add_argument("--scan",      action="store_true", help="Scan for stuck files and quarantine")
    mode.add_argument("--retry",     action="store_true", help="Process pending retries from Errors/")
    mode.add_argument("--log-error", action="store_true", help="Manually quarantine a file")
    mode.add_argument("--status",    action="store_true", help="Show quarantine and exhausted counts")
    mode.add_argument("--report",    action="store_true", help="Full report with recent error log")

    parser.add_argument("--file",   type=str, help="Filename for --log-error")
    parser.add_argument("--reason", type=str, help="Error reason for --log-error")
    parser.add_argument(
        "--src",
        type=str,
        default="Needs_Action",
        help="Source folder for --log-error (default: Needs_Action)",
    )

    args = parser.parse_args()

    if args.run:
        cmd_run()
    elif args.scan:
        cmd_scan()
    elif args.retry:
        cmd_retry()
    elif args.log_error:
        if not args.file or not args.reason:
            parser.error("--log-error requires both --file and --reason")
        cmd_log_error(args.file, args.reason, args.src)
    elif args.status:
        cmd_status()
    elif args.report:
        cmd_report()


if __name__ == "__main__":
    main()
