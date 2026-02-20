"""
ceo_briefing.py - CEO Weekly Briefing Skill

Generates Reports/CEO_Weekly.md by aggregating vault activity from the past 7 days.

Sections:
  1. Tasks Completed This Week
  2. Emails Sent This Week
  3. Pending Approvals
  4. Financial Summary (Accounting/Current_Month.md)
  5. System Health

Scheduling state: Logs/.ceo_briefing_state.json  (tracks last run)
Report output  : Reports/CEO_Weekly.md           (always latest)
Archive copy   : Reports/CEO_Weekly_YYYY-WNN.md  (one per week)

Modes:
  --check    Generate only if 7+ days since last run  (for scheduler)
  --now      Force-generate immediately
  --preview  Print the report to stdout without writing any files

Usage:
  python .claude/skills/ceo-briefing/scripts/ceo_briefing.py --check
  python .claude/skills/ceo-briefing/scripts/ceo_briefing.py --now
  python .claude/skills/ceo-briefing/scripts/ceo_briefing.py --preview

Exit codes:
  0 - success (or not yet due in --check mode)
  1 - error
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation

# ── Stdout encoding fix (Windows cp1252 terminals) ───────────────────────────
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

# ── Paths ─────────────────────────────────────────────────────────────────────
_SCRIPT_DIR  = os.path.dirname(os.path.abspath(__file__))
# .claude/skills/ceo-briefing/scripts/ -> vault root (4 levels up)
VAULT_ROOT   = os.path.abspath(os.path.join(_SCRIPT_DIR, "..", "..", "..", ".."))

DONE_DIR     = os.path.join(VAULT_ROOT, "Done")
APPROVAL_DIR = os.path.join(VAULT_ROOT, "Needs_Approval")
INBOX_DIR    = os.path.join(VAULT_ROOT, "Inbox")
ACTION_DIR   = os.path.join(VAULT_ROOT, "Needs_Action")
LOGS_DIR     = os.path.join(VAULT_ROOT, "Logs")
REPORTS_DIR  = os.path.join(VAULT_ROOT, "Reports")
ACCT_DIR     = os.path.join(VAULT_ROOT, "Accounting")

ACTIONS_LOG  = os.path.join(LOGS_DIR, "actions.log")
BUSINESS_LOG = os.path.join(LOGS_DIR, "business.log")
AI_LOG       = os.path.join(LOGS_DIR, "ai_employee.log")
LOCK_FILE    = os.path.join(LOGS_DIR, ".scheduler.lock")
LEDGER_FILE  = os.path.join(ACCT_DIR, "Current_Month.md")

STATE_FILE   = os.path.join(LOGS_DIR, ".ceo_briefing_state.json")
CEO_REPORT   = os.path.join(REPORTS_DIR, "CEO_Weekly.md")

BRIEFING_INTERVAL_DAYS = 7

# ── Load .env ─────────────────────────────────────────────────────────────────
_env_path = os.path.join(VAULT_ROOT, ".env")
if os.path.isfile(_env_path):
    with open(_env_path, encoding="utf-8") as _f:
        for _line in _f:
            _line = _line.strip()
            if _line and not _line.startswith("#") and "=" in _line:
                _k, _, _v = _line.partition("=")
                os.environ.setdefault(_k.strip(), _v.strip())

# ── Helpers ───────────────────────────────────────────────────────────────────

def _now() -> datetime:
    return datetime.now(timezone.utc)


def _now_str() -> str:
    return _now().strftime("%Y-%m-%d %H:%M:%S UTC")


def _fmt_amount(amount: Decimal) -> str:
    sign = "-" if amount < 0 else ""
    return f"{sign}${abs(amount):,.2f}"


def _safe_count(directory: str) -> int:
    try:
        return len([f for f in os.listdir(directory)
                    if os.path.isfile(os.path.join(directory, f))])
    except OSError:
        return 0


def _log_action(message: str) -> None:
    """Append to Logs/actions.log (best-effort)."""
    try:
        os.makedirs(LOGS_DIR, exist_ok=True)
        with open(ACTIONS_LOG, "a", encoding="utf-8") as fh:
            fh.write(f"[{_now_str()}] [ceo-briefing] {message}\n")
    except OSError:
        pass

# ── Scheduling state ──────────────────────────────────────────────────────────

def _load_state() -> dict:
    if not os.path.isfile(STATE_FILE):
        return {}
    try:
        with open(STATE_FILE, encoding="utf-8") as fh:
            return json.load(fh)
    except (json.JSONDecodeError, OSError):
        return {}


def _save_state(state: dict) -> None:
    os.makedirs(LOGS_DIR, exist_ok=True)
    with open(STATE_FILE, "w", encoding="utf-8") as fh:
        json.dump(state, fh, indent=2)


def _is_due() -> bool:
    """Return True if 7+ days have passed since the last briefing (or never run)."""
    state = _load_state()
    last_run = state.get("last_run")
    if not last_run:
        return True
    try:
        last_dt = datetime.fromisoformat(last_run)
        return (_now() - last_dt).days >= BRIEFING_INTERVAL_DAYS
    except (ValueError, TypeError):
        return True

# ── Data collectors ───────────────────────────────────────────────────────────

def _collect_tasks_this_week() -> list[dict]:
    """
    Return Done/ files whose mtime is within the past 7 days.
    Parses front-matter for type/status.
    """
    cutoff = _now() - timedelta(days=7)
    results: list[dict] = []

    if not os.path.isdir(DONE_DIR):
        return results

    try:
        files = sorted(os.listdir(DONE_DIR))
    except OSError:
        return results

    _fm_type   = re.compile(r"^type:\s*(.+)$", re.MULTILINE)
    _fm_status = re.compile(r"^status:\s*(.+)$", re.MULTILINE)

    for fname in files:
        if not fname.endswith(".md"):
            continue
        fpath = os.path.join(DONE_DIR, fname)
        if not os.path.isfile(fpath):
            continue
        try:
            mtime = os.path.getmtime(fpath)
            mtime_dt = datetime.fromtimestamp(mtime, timezone.utc)
        except OSError:
            continue
        if mtime_dt < cutoff:
            continue

        task_type = "unknown"
        status    = "completed"
        try:
            with open(fpath, encoding="utf-8", errors="replace") as fh:
                head = fh.read(1000)
            m = _fm_type.search(head)
            if m:
                task_type = m.group(1).strip()
            m = _fm_status.search(head)
            if m:
                status = m.group(1).strip()
        except OSError:
            pass

        # Friendly display name
        display = fname.replace("task_", "").replace("Plan_", "[Plan] ").replace("_md.md", "").replace("_", " ").strip()
        if len(display) > 55:
            display = display[:52] + "..."

        results.append({
            "file":         fname,
            "display":      display,
            "type":         task_type,
            "status":       status,
            "completed_at": mtime_dt.strftime("%Y-%m-%d %H:%M UTC"),
        })

    return results


def _collect_emails_this_week() -> list[dict]:
    """
    Scan actions.log and business.log for send_email entries in the past 7 days.
    Matches lines like: [TS UTC] ... send_email | to=X | subject=Y | status=Z
    """
    cutoff   = _now() - timedelta(days=7)
    emails: list[dict] = []

    _ts_re  = re.compile(r"^\[(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) UTC\]")
    _data_re = re.compile(
        r"send_email\s*\|\s*to=([^|]+?)\s*\|\s*subject=([^|]+?)\s*\|\s*status=(\w+)"
    )

    for log_path in (ACTIONS_LOG, BUSINESS_LOG):
        if not os.path.isfile(log_path):
            continue
        try:
            with open(log_path, encoding="utf-8", errors="replace") as fh:
                for line in fh:
                    if "send_email" not in line:
                        continue
                    ts_m = _ts_re.match(line)
                    if not ts_m:
                        continue
                    try:
                        ts = datetime.strptime(
                            ts_m.group(1), "%Y-%m-%d %H:%M:%S"
                        ).replace(tzinfo=timezone.utc)
                    except ValueError:
                        continue
                    if ts < cutoff:
                        continue
                    dm = _data_re.search(line)
                    if dm:
                        subj = dm.group(2).strip()
                        if len(subj) > 45:
                            subj = subj[:42] + "..."
                        emails.append({
                            "time":    ts.strftime("%Y-%m-%d %H:%M UTC"),
                            "to":      dm.group(1).strip(),
                            "subject": subj,
                            "status":  dm.group(3).strip(),
                        })
        except OSError:
            pass

    return emails


def _collect_pending_approvals() -> list[dict]:
    """Return .md files in Needs_Approval/ without a decision suffix, with age."""
    results: list[dict] = []
    if not os.path.isdir(APPROVAL_DIR):
        return results

    now = _now()
    try:
        files = sorted(os.listdir(APPROVAL_DIR))
    except OSError:
        return results

    for fname in files:
        if not fname.endswith(".md"):
            continue
        if any(fname.endswith(s) for s in (".approved", ".rejected", ".timeout")):
            continue
        fpath = os.path.join(APPROVAL_DIR, fname)
        if not os.path.isfile(fpath):
            continue
        try:
            mtime    = os.path.getmtime(fpath)
            mtime_dt = datetime.fromtimestamp(mtime, timezone.utc)
            age_days = (now - mtime_dt).days
            age_str  = f"{age_days}d old" if age_days > 0 else "today"
        except OSError:
            age_str = "unknown"

        display = fname[:55] + ("..." if len(fname) > 55 else "")
        results.append({"file": display, "age": age_str})

    return results


def _collect_financial_summary() -> dict:
    """
    Parse Accounting/Current_Month.md ledger rows and compute totals.
    Returns dict with income, expenses, net, transactions, available flag.
    """
    empty = {
        "income": Decimal("0"),
        "expenses": Decimal("0"),
        "net": Decimal("0"),
        "transactions": 0,
        "available": False,
    }
    if not os.path.isfile(LEDGER_FILE):
        return empty

    income   = Decimal("0")
    expenses = Decimal("0")
    count    = 0

    in_ledger    = False
    header_seen  = False
    sep_seen     = False
    _sep_re = re.compile(r"^\|\s*[-:]+")

    try:
        with open(LEDGER_FILE, encoding="utf-8", errors="replace") as fh:
            for line in fh:
                stripped = line.strip()

                if stripped == "## Ledger":
                    in_ledger = True
                    continue

                if not in_ledger:
                    continue

                # Stop at next section or divider
                if stripped.startswith("## ") and stripped != "## Ledger":
                    break
                if stripped == "---":
                    break

                if not stripped.startswith("|"):
                    continue

                if not header_seen:
                    header_seen = True
                    continue
                if _sep_re.match(stripped):
                    sep_seen = True
                    continue
                if not sep_seen:
                    continue

                # Data row: | date | type | amount | description |
                parts = [c.strip() for c in stripped.strip("|").split("|")]
                if len(parts) < 3:
                    continue
                row_type   = parts[1].lower().strip()
                amount_str = parts[2].strip().lstrip("$").replace(",", "")
                try:
                    amount = Decimal(amount_str).quantize(Decimal("0.01"))
                    if row_type == "income":
                        income += amount
                    elif row_type == "expense":
                        expenses += amount
                    count += 1
                except InvalidOperation:
                    pass
    except OSError:
        return empty

    return {
        "income":       income,
        "expenses":     expenses,
        "net":          income - expenses,
        "transactions": count,
        "available":    True,
    }


def _collect_system_health() -> dict:
    """Collect scheduler status, folder counts, log sizes, last cycle time."""

    # Scheduler running?
    scheduler_running = False
    scheduler_pid     = None
    if os.path.isfile(LOCK_FILE):
        try:
            with open(LOCK_FILE) as fh:
                pid = int(fh.read().strip())
            try:
                os.kill(pid, 0)
                scheduler_running = True
                scheduler_pid     = pid
            except OSError:
                pass
        except (ValueError, OSError):
            pass

    # Last completed scheduler cycle from ai_employee.log
    last_cycle = "unknown"
    if os.path.isfile(AI_LOG):
        _cycle_re = re.compile(
            r"^\[(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2} UTC)\].*finished"
        )
        try:
            with open(AI_LOG, encoding="utf-8", errors="replace") as fh:
                for line in reversed(fh.readlines()):
                    m = _cycle_re.match(line)
                    if m:
                        last_cycle = m.group(1)
                        break
        except OSError:
            pass

    # Log file sizes
    def _sz(path: str) -> str:
        try:
            b = os.path.getsize(path)
            return f"{b / 1024:.1f} KB"
        except OSError:
            return "N/A"

    # Pending approvals count (reuse existing collector)
    pending_approvals = len(_collect_pending_approvals())

    return {
        "scheduler_running":  scheduler_running,
        "scheduler_pid":      scheduler_pid,
        "last_cycle":         last_cycle,
        "inbox":              _safe_count(INBOX_DIR),
        "needs_action":       _safe_count(ACTION_DIR),
        "needs_approval":     pending_approvals,
        "done_total":         _safe_count(DONE_DIR),
        "ai_log_size":        _sz(AI_LOG),
        "actions_log_size":   _sz(ACTIONS_LOG),
        "business_log_size":  _sz(BUSINESS_LOG),
    }

# ── Report builder ────────────────────────────────────────────────────────────

def _build_report(
    tasks: list[dict],
    emails: list[dict],
    approvals: list[dict],
    financials: dict,
    health: dict,
) -> str:
    now      = _now()
    iso_year, iso_week, _ = now.isocalendar()
    week_label = f"Week {iso_week}, {now.strftime('%B %Y')}"
    generated  = now.strftime("%Y-%m-%d %H:%M:%S UTC")
    cutoff_str = (now - timedelta(days=7)).strftime("%Y-%m-%d")

    lines: list[str] = []

    # Front-matter
    lines += [
        "---",
        "type: ceo_briefing",
        f"week: {iso_year}-W{iso_week:02d}",
        f"generated_at: {generated}",
        "---",
        "",
        f"# CEO Weekly Briefing - {week_label}",
        "",
        f"> Generated: {generated} | AI Employee System",
        f"> Coverage: {cutoff_str} to {now.strftime('%Y-%m-%d')}",
        "",
        "---",
        "",
    ]

    # ── Section 1: Tasks Completed ────────────────────────────────────────────
    lines += [
        "## 1. Tasks Completed This Week",
        "",
    ]
    if tasks:
        lines += [
            "| Task | Type | Completed |",
            "|------|------|-----------|",
        ]
        for t in tasks:
            lines.append(f"| {t['display']} | {t['type']} | {t['completed_at']} |")
        lines += [
            "",
            f"**Total completed:** {len(tasks)} task(s)",
        ]
    else:
        lines.append("*No tasks completed in the past 7 days.*")

    lines += ["", "---", ""]

    # ── Section 2: Emails Sent ────────────────────────────────────────────────
    lines += [
        "## 2. Emails Sent This Week",
        "",
    ]
    if emails:
        lines += [
            "| Time (UTC) | To | Subject | Status |",
            "|------------|----|---------|--------|",
        ]
        for e in emails:
            lines.append(
                f"| {e['time']} | {e['to']} | {e['subject']} | {e['status']} |"
            )
        lines += [
            "",
            f"**Total sent:** {len(emails)} email(s)",
        ]
    else:
        lines.append("*No emails logged in the past 7 days.*")

    lines += ["", "---", ""]

    # ── Section 3: Pending Approvals ──────────────────────────────────────────
    lines += [
        "## 3. Pending Approvals",
        "",
    ]
    if approvals:
        lines += [
            "| Item | Age |",
            "|------|-----|",
        ]
        for a in approvals:
            lines.append(f"| {a['file']} | {a['age']} |")
        lines += [
            "",
            f"**Awaiting decision:** {len(approvals)} item(s)",
            "",
            "> Action required: open each file in Needs_Approval/ and write APPROVED or REJECTED.",
        ]
    else:
        lines.append("*No items pending approval.*")

    lines += ["", "---", ""]

    # ── Section 4: Financial Summary ──────────────────────────────────────────
    lines += [
        "## 4. Financial Summary (Current Month)",
        "",
    ]
    if financials["available"] and financials["transactions"] > 0:
        net = financials["net"]
        net_fmt = _fmt_amount(net)
        lines += [
            "| Category | Amount |",
            "|----------|--------|",
            f"| Total Income   | {_fmt_amount(financials['income'])} |",
            f"| Total Expenses | {_fmt_amount(financials['expenses'])} |",
            f"| **Net**        | **{net_fmt}** |",
            f"| Transactions   | {financials['transactions']} |",
            "",
        ]
        if net >= 0:
            lines.append(f"> Positive cashflow: {_fmt_amount(net)} ahead this month.")
        else:
            lines.append(f"> Note: expenses exceed income by {_fmt_amount(abs(net))} this month.")
        lines += [
            "",
            "*Source: Accounting/Current_Month.md — run accounting-manager to update.*",
        ]
    elif financials["available"]:
        lines.append("*Accounting ledger exists but contains no entries yet.*")
    else:
        lines.append(
            "*No accounting data found. Run:*  \n"
            "`python .claude/skills/accounting-manager/scripts/accounting_manager.py --add --type income --amount X --description Y`"
        )

    lines += ["", "---", ""]

    # ── Section 5: System Health ──────────────────────────────────────────────
    lines += [
        "## 5. System Health",
        "",
    ]
    sched_status = (
        f"RUNNING (PID {health['scheduler_pid']})"
        if health["scheduler_running"]
        else "STOPPED"
    )
    lines += [
        "| Metric | Value |",
        "|--------|-------|",
        f"| Scheduler | {sched_status} |",
        f"| Last cycle completed | {health['last_cycle']} |",
        f"| Inbox (new files) | {health['inbox']} |",
        f"| Needs_Action (pending) | {health['needs_action']} |",
        f"| Needs_Approval (waiting) | {health['needs_approval']} |",
        f"| Done/ (total files) | {health['done_total']} |",
        f"| ai_employee.log | {health['ai_log_size']} |",
        f"| actions.log | {health['actions_log_size']} |",
        f"| business.log | {health['business_log_size']} |",
    ]

    if not health["scheduler_running"]:
        lines += [
            "",
            "> WARNING: Scheduler is not running. "
            "Start with: `python scripts/run_ai_employee.py --daemon`",
        ]

    lines += [
        "",
        "---",
        "",
        f"*Auto-generated by ceo-briefing skill. "
        f"Next briefing due in {BRIEFING_INTERVAL_DAYS} days.*",
    ]

    return "\n".join(lines) + "\n"

# ── Report writer ─────────────────────────────────────────────────────────────

def _write_report(content: str) -> None:
    """Write CEO_Weekly.md and an archived dated copy."""
    os.makedirs(REPORTS_DIR, exist_ok=True)

    # Always-latest file
    with open(CEO_REPORT, "w", encoding="utf-8") as fh:
        fh.write(content)

    # Dated archive copy
    now = _now()
    iso_year, iso_week, _ = now.isocalendar()
    archive_name = f"CEO_Weekly_{iso_year}-W{iso_week:02d}.md"
    archive_path = os.path.join(REPORTS_DIR, archive_name)
    with open(archive_path, "w", encoding="utf-8") as fh:
        fh.write(content)

# ── Main generate function ────────────────────────────────────────────────────

def generate(verbose: bool = True) -> bool:
    """
    Collect all data, build the report, write to disk, update state.
    Returns True on success.
    """
    if verbose:
        print("[ceo-briefing] Collecting data...")

    tasks      = _collect_tasks_this_week()
    emails     = _collect_emails_this_week()
    approvals  = _collect_pending_approvals()
    financials = _collect_financial_summary()
    health     = _collect_system_health()

    if verbose:
        print(f"[ceo-briefing]   Tasks this week   : {len(tasks)}")
        print(f"[ceo-briefing]   Emails this week  : {len(emails)}")
        print(f"[ceo-briefing]   Pending approvals : {len(approvals)}")
        fin_str = (
            f"income={_fmt_amount(financials['income'])}, "
            f"expenses={_fmt_amount(financials['expenses'])}, "
            f"net={_fmt_amount(financials['net'])}"
            if financials["available"] else "N/A"
        )
        print(f"[ceo-briefing]   Financials        : {fin_str}")
        sched = "RUNNING" if health["scheduler_running"] else "STOPPED"
        print(f"[ceo-briefing]   Scheduler         : {sched}")

    report = _build_report(tasks, emails, approvals, financials, health)

    try:
        _write_report(report)
    except OSError as exc:
        print(f"[ceo-briefing] ERROR: Could not write report: {exc}")
        return False

    now = _now()
    iso_year, iso_week, _ = now.isocalendar()
    _save_state({
        "last_run":   now.isoformat(),
        "week":       f"{iso_year}-W{iso_week:02d}",
        "tasks":      len(tasks),
        "emails":     len(emails),
        "approvals":  len(approvals),
    })

    _log_action(
        f"CEO briefing generated | week={iso_year}-W{iso_week:02d} "
        f"| tasks={len(tasks)} | emails={len(emails)} | approvals={len(approvals)}"
    )

    if verbose:
        print(f"[ceo-briefing] Report written to: {CEO_REPORT}")
        print(f"[ceo-briefing] Archive:           {REPORTS_DIR}/CEO_Weekly_{iso_year}-W{iso_week:02d}.md")

    return True

# ── CLI ───────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        prog="ceo_briefing",
        description="CEO Weekly Briefing - generate Reports/CEO_Weekly.md",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python ceo_briefing.py --check     # generate if 7+ days since last run
  python ceo_briefing.py --now       # force generate now
  python ceo_briefing.py --preview   # print to stdout, no files written
        """,
    )
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument(
        "--check",
        action="store_true",
        help="Generate if 7+ days since last briefing (used by scheduler)",
    )
    mode.add_argument(
        "--now",
        action="store_true",
        help="Force-generate the briefing immediately",
    )
    mode.add_argument(
        "--preview",
        action="store_true",
        help="Print briefing to stdout without writing any files",
    )
    args = parser.parse_args()

    if args.check:
        if _is_due():
            print("[ceo-briefing] Briefing is due. Generating...")
            success = generate()
            sys.exit(0 if success else 1)
        else:
            state = _load_state()
            last  = state.get("last_run", "unknown")
            print(f"[ceo-briefing] Not yet due. Last run: {last}")
            sys.exit(0)

    elif args.now:
        print("[ceo-briefing] Forced generation...")
        success = generate()
        sys.exit(0 if success else 1)

    elif args.preview:
        tasks      = _collect_tasks_this_week()
        emails     = _collect_emails_this_week()
        approvals  = _collect_pending_approvals()
        financials = _collect_financial_summary()
        health     = _collect_system_health()
        report     = _build_report(tasks, emails, approvals, financials, health)
        sys.stdout.write(report)
        sys.stdout.flush()


if __name__ == "__main__":
    main()
