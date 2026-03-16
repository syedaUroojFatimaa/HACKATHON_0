"""
accounting_manager.py — Accounting Manager Agent Skill

Maintains the vault ledger at Accounting/Current_Month.md.
Records income and expense entries, generates weekly breakdowns,
and produces income/expense totals on demand.

Ledger file: Accounting/Current_Month.md  (auto-created if missing)
Actions log: Logs/actions.log

Usage:
    # Add a transaction
    python accounting_manager.py --add --type income  --amount 1500.00 --description "Client payment"
    python accounting_manager.py --add --type expense --amount  200.00 --description "GitHub Pro"

    # Reports
    python accounting_manager.py --summary          # totals: income / expense / net
    python accounting_manager.py --weekly           # week-by-week breakdown
    python accounting_manager.py --report           # full report (totals + weekly)
    python accounting_manager.py --list             # raw ledger rows

Exit codes:
    0 — success
    1 — validation or I/O error
"""

from __future__ import annotations

import argparse
import os
import re
import sys
import threading
from datetime import date, datetime, timezone, timedelta
from decimal import Decimal, InvalidOperation

# ──────────────────────────────────────────────────────────────────────────────
# Paths
# ──────────────────────────────────────────────────────────────────────────────

_SCRIPT_DIR  = os.path.dirname(os.path.abspath(__file__))
# .claude/skills/accounting-manager/scripts/ → vault root (4 levels up)
VAULT_ROOT   = os.path.abspath(os.path.join(_SCRIPT_DIR, "..", "..", "..", ".."))
ACCT_DIR     = os.path.join(VAULT_ROOT, "Accounting")
LEDGER_FILE  = os.path.join(ACCT_DIR, "Current_Month.md")
ACTIONS_LOG  = os.path.join(VAULT_ROOT, "Logs", "actions.log")

# ──────────────────────────────────────────────────────────────────────────────
# Thread safety
# ──────────────────────────────────────────────────────────────────────────────

_ledger_lock = threading.Lock()

# ──────────────────────────────────────────────────────────────────────────────
# Constants
# ──────────────────────────────────────────────────────────────────────────────

VALID_TYPES   = {"income", "expense"}
DIVIDER       = "---"
LEDGER_HEADER = "## Ledger"
SUMMARY_HEADER = "## Summary"
TABLE_SEP_RE  = re.compile(r"^\|\s*[-:]+[\s|]")  # matches |-----|-----| rows

# ──────────────────────────────────────────────────────────────────────────────
# Logging
# ──────────────────────────────────────────────────────────────────────────────

def _log_action(message: str) -> None:
    """Append a timestamped line to Logs/actions.log (best-effort)."""
    try:
        os.makedirs(os.path.dirname(ACTIONS_LOG), exist_ok=True)
        ts = _now_str()
        with open(ACTIONS_LOG, "a", encoding="utf-8") as fh:
            fh.write(f"[{ts}] [accounting-manager] {message}\n")
    except OSError:
        pass

# ──────────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────────

def _now_str() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")


def _today() -> str:
    return date.today().strftime("%Y-%m-%d")


def _month_label() -> str:
    return datetime.now(timezone.utc).strftime("%B %Y")


def _month_key() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m")


def _fmt_amount(amount: Decimal) -> str:
    """Format a Decimal as $1,234.56 (negative shown as -$1,234.56)."""
    sign = "-" if amount < 0 else ""
    return f"{sign}${abs(amount):,.2f}"


def _parse_amount(raw: str) -> Decimal:
    """Parse a user-supplied amount string. Raises ValueError on bad input."""
    cleaned = raw.strip().lstrip("$").replace(",", "")
    try:
        value = Decimal(cleaned)
    except InvalidOperation:
        raise ValueError(f"Invalid amount: '{raw}' — use a number like 1500 or 1500.00")
    if value < 0:
        raise ValueError("Amount must be positive. Use --type to indicate income/expense.")
    return value.quantize(Decimal("0.01"))


def _iso_week_label(d: date) -> str:
    """Return 'Week N  (Mon DD – Mon DD)' covering the ISO week of d."""
    iso_year, iso_week, _ = d.isocalendar()
    # Monday of this ISO week
    monday = date.fromisocalendar(iso_year, iso_week, 1)
    sunday = monday + timedelta(days=6)
    return f"Week {iso_week:02d}  ({monday.strftime('%b %d')} to {sunday.strftime('%b %d')})"


# ──────────────────────────────────────────────────────────────────────────────
# Ledger file management
# ──────────────────────────────────────────────────────────────────────────────

def _default_ledger_content() -> str:
    month  = _month_label()
    key    = _month_key()
    now    = _now_str()
    return (
        f"---\n"
        f"type: accounting\n"
        f"month: {key}\n"
        f"created_at: {now}\n"
        f"last_updated: {now}\n"
        f"---\n\n"
        f"# Accounting — {month}\n\n"
        f"{LEDGER_HEADER}\n\n"
        f"| Date       | Type    | Amount    | Description |\n"
        f"|------------|---------|-----------|-------------|\n\n"
        f"{DIVIDER}\n\n"
        f"{SUMMARY_HEADER}\n\n"
        f"> *Run `--summary` or `--report` to generate totals.*\n"
    )


def _ensure_ledger() -> None:
    """Create Accounting/Current_Month.md with default content if missing."""
    os.makedirs(ACCT_DIR, exist_ok=True)
    if not os.path.isfile(LEDGER_FILE):
        with open(LEDGER_FILE, "w", encoding="utf-8") as fh:
            fh.write(_default_ledger_content())
        _log_action(f"Created ledger: {LEDGER_FILE}")


def _read_ledger() -> str:
    with open(LEDGER_FILE, "r", encoding="utf-8") as fh:
        return fh.read()


def _write_ledger(content: str) -> None:
    with open(LEDGER_FILE, "w", encoding="utf-8") as fh:
        fh.write(content)

# ──────────────────────────────────────────────────────────────────────────────
# Ledger parsing
# ──────────────────────────────────────────────────────────────────────────────

def _parse_rows(content: str) -> list[dict]:
    """
    Extract all data rows from the ledger table.
    Returns list of dicts: {date, type, amount (Decimal), description}
    """
    rows = []
    in_ledger = False
    header_seen = False
    separator_seen = False

    for line in content.splitlines():
        stripped = line.strip()

        if stripped == LEDGER_HEADER:
            in_ledger = True
            continue

        # Stop at next top-level section
        if in_ledger and stripped.startswith("## ") and stripped != LEDGER_HEADER:
            break
        if in_ledger and stripped == DIVIDER:
            break

        if not in_ledger:
            continue

        if stripped.startswith("|"):
            if not header_seen:
                header_seen = True
                continue
            if TABLE_SEP_RE.match(stripped):
                separator_seen = True
                continue
            if not separator_seen:
                continue

            # Data row
            parts = [c.strip() for c in stripped.strip("|").split("|")]
            if len(parts) < 4:
                continue
            date_str, type_str, amount_str, desc = parts[0], parts[1], parts[2], parts[3]
            amount_str = amount_str.lstrip("$").replace(",", "").strip()
            try:
                amount = Decimal(amount_str).quantize(Decimal("0.01"))
                rows.append({
                    "date":        date_str,
                    "type":        type_str.lower(),
                    "amount":      amount,
                    "description": desc,
                })
            except InvalidOperation:
                pass  # skip malformed rows

    return rows

# ──────────────────────────────────────────────────────────────────────────────
# Operations
# ──────────────────────────────────────────────────────────────────────────────

def add_entry(entry_type: str, amount: Decimal, description: str) -> None:
    """Append one transaction row to the ledger table and refresh the summary."""
    entry_type = entry_type.lower().strip()
    if entry_type not in VALID_TYPES:
        print(f"ERROR: --type must be 'income' or 'expense', got '{entry_type}'")
        sys.exit(1)
    if not description.strip():
        print("ERROR: --description must not be empty.")
        sys.exit(1)

    today     = _today()
    amt_str   = f"{amount:.2f}"
    new_row   = f"| {today} | {entry_type:<7} | {amt_str:>9} | {description.strip()} |\n"

    with _ledger_lock:
        _ensure_ledger()
        content = _read_ledger()

        # Insert the new row just before the blank line / divider after the table
        lines   = content.splitlines(keepends=True)
        insert_at = None
        in_ledger = False
        header_seen = False
        sep_seen = False

        for i, line in enumerate(lines):
            stripped = line.strip()
            if stripped == LEDGER_HEADER:
                in_ledger = True
                continue
            if in_ledger:
                if stripped.startswith("## ") and stripped != LEDGER_HEADER:
                    insert_at = i
                    break
                if stripped == DIVIDER:
                    insert_at = i
                    break
                if stripped.startswith("|"):
                    if not header_seen:
                        header_seen = True
                        continue
                    if TABLE_SEP_RE.match(stripped):
                        sep_seen = True
                        continue
                    if sep_seen:
                        insert_at = i + 1  # after last data row

        if insert_at is None:
            # Append at end
            lines.append(new_row)
        else:
            lines.insert(insert_at, new_row)

        # Update front-matter last_updated
        new_lines = []
        for line in lines:
            if line.startswith("last_updated:"):
                new_lines.append(f"last_updated: {_now_str()}\n")
            else:
                new_lines.append(line)

        _write_ledger("".join(new_lines))

    _log_action(f"ADD {entry_type} | amount={amt_str} | desc={description.strip()}")
    print(f"SUCCESS: Added {entry_type} entry")
    print(f"  Date:        {today}")
    print(f"  Type:        {entry_type}")
    print(f"  Amount:      {_fmt_amount(amount)}")
    print(f"  Description: {description.strip()}")
    print(f"  Ledger:      {LEDGER_FILE}")

    # Auto-refresh summary in the file
    _write_summary_section()


def _calc_totals(rows: list[dict]) -> tuple[Decimal, Decimal, Decimal]:
    """Return (total_income, total_expenses, net)."""
    total_income   = sum((r["amount"] for r in rows if r["type"] == "income"),   Decimal("0.00"))
    total_expenses = sum((r["amount"] for r in rows if r["type"] == "expense"),  Decimal("0.00"))
    net            = total_income - total_expenses
    return total_income, total_expenses, net


def _calc_weekly(rows: list[dict]) -> list[dict]:
    """
    Group rows by ISO week.
    Returns list of dicts sorted by week start:
      {label, income, expenses, net}
    """
    weeks: dict[tuple, dict] = {}

    for row in rows:
        try:
            d = date.fromisoformat(row["date"])
        except ValueError:
            continue
        iso = d.isocalendar()[:2]  # (iso_year, iso_week)
        if iso not in weeks:
            weeks[iso] = {"label": _iso_week_label(d), "income": Decimal("0"), "expenses": Decimal("0")}
        if row["type"] == "income":
            weeks[iso]["income"] += row["amount"]
        elif row["type"] == "expense":
            weeks[iso]["expenses"] += row["amount"]

    result = []
    for iso_key in sorted(weeks):
        w = weeks[iso_key]
        w["net"] = w["income"] - w["expenses"]
        result.append(w)
    return result


def _build_summary_block(rows: list[dict]) -> str:
    """Build the full ## Summary section as a Markdown string."""
    now = _now_str()
    total_income, total_expenses, net = _calc_totals(rows)
    weekly = _calc_weekly(rows)

    # Totals table
    net_fmt = _fmt_amount(net)
    totals_md = (
        "### Totals\n\n"
        "| Category       | Amount       |\n"
        "|----------------|--------------|\n"
        f"| Total Income   | {_fmt_amount(total_income):>12} |\n"
        f"| Total Expenses | {_fmt_amount(total_expenses):>12} |\n"
        f"| **Net**        | **{net_fmt}** |\n"
    )

    # Weekly table
    if weekly:
        weekly_rows = ""
        for w in weekly:
            weekly_rows += (
                f"| {w['label']:<34} | {_fmt_amount(w['income']):>10} | "
                f"{_fmt_amount(w['expenses']):>10} | {_fmt_amount(w['net']):>10} |\n"
            )
        weekly_md = (
            "\n### Weekly Breakdown\n\n"
            "| Week                               |     Income |   Expenses |        Net |\n"
            "|------------------------------------|------------|------------|------------|\n"
            + weekly_rows
        )
    else:
        weekly_md = "\n### Weekly Breakdown\n\n> *No entries yet.*\n"

    return (
        f"{SUMMARY_HEADER}\n\n"
        f"> Last updated: {now}\n\n"
        f"{totals_md}"
        f"{weekly_md}"
    )


def _write_summary_section() -> None:
    """Replace the ## Summary section in the ledger file with fresh numbers."""
    with _ledger_lock:
        _ensure_ledger()
        content = _read_ledger()
        rows    = _parse_rows(content)
        summary = _build_summary_block(rows)

        lines      = content.splitlines(keepends=True)
        new_lines  = []
        skip       = False

        for line in lines:
            if line.strip() == SUMMARY_HEADER:
                skip = True
                new_lines.append(summary + "\n")
                continue
            if skip:
                # Keep skipping until we hit the next ## section or EOF
                if line.strip().startswith("## ") and line.strip() != SUMMARY_HEADER:
                    skip = False
                    new_lines.append(line)
                # else discard old summary lines
            else:
                new_lines.append(line)

        _write_ledger("".join(new_lines))


# ──────────────────────────────────────────────────────────────────────────────
# Report commands
# ──────────────────────────────────────────────────────────────────────────────

def cmd_list() -> None:
    _ensure_ledger()
    rows = _parse_rows(_read_ledger())
    if not rows:
        print("No entries in ledger yet.")
        return
    print(f"{'Date':<12} {'Type':<8} {'Amount':>10}  Description")
    print("-" * 60)
    for r in rows:
        amt = _fmt_amount(r["amount"])
        print(f"{r['date']:<12} {r['type']:<8} {amt:>10}  {r['description']}")
    print(f"\n{len(rows)} transaction(s) total.")


def cmd_summary() -> None:
    _ensure_ledger()
    rows = _parse_rows(_read_ledger())
    total_income, total_expenses, net = _calc_totals(rows)

    print("=" * 45)
    print(f"  Accounting Summary - {_month_label()}")
    print("=" * 45)
    print(f"  Total Income    : {_fmt_amount(total_income):>12}")
    print(f"  Total Expenses  : {_fmt_amount(total_expenses):>12}")
    print(f"  {'-' * 30}")
    print(f"  Net             : {_fmt_amount(net):>12}")
    print(f"  Transactions    : {len(rows)}")
    print("=" * 45)

    _write_summary_section()
    _log_action(f"SUMMARY | income={total_income} | expenses={total_expenses} | net={net}")


def cmd_weekly() -> None:
    _ensure_ledger()
    rows   = _parse_rows(_read_ledger())
    weekly = _calc_weekly(rows)

    print("=" * 70)
    print(f"  Weekly Breakdown - {_month_label()}")
    print("=" * 70)
    if not weekly:
        print("  No entries yet.")
    else:
        print(f"  {'Week':<36} {'Income':>10}  {'Expenses':>10}  {'Net':>10}")
        print(f"  {'-' * 66}")
        for w in weekly:
            print(
                f"  {w['label']:<36} {_fmt_amount(w['income']):>10}  "
                f"{_fmt_amount(w['expenses']):>10}  {_fmt_amount(w['net']):>10}"
            )
    print("=" * 70)

    _write_summary_section()
    _log_action("WEEKLY report generated")


def cmd_report() -> None:
    _ensure_ledger()
    rows = _parse_rows(_read_ledger())
    total_income, total_expenses, net = _calc_totals(rows)
    weekly = _calc_weekly(rows)

    print("=" * 70)
    print(f"  Accounting Report - {_month_label()}")
    print(f"  Generated: {_now_str()}")
    print("=" * 70)

    # Totals
    print()
    print("  TOTALS")
    print(f"  {'-' * 40}")
    print(f"  Total Income    : {_fmt_amount(total_income):>12}")
    print(f"  Total Expenses  : {_fmt_amount(total_expenses):>12}")
    print(f"  Net             : {_fmt_amount(net):>12}")
    print(f"  Transactions    : {len(rows)}")

    # Weekly
    print()
    print("  WEEKLY BREAKDOWN")
    print(f"  {'-' * 66}")
    if not weekly:
        print("  No entries yet.")
    else:
        print(f"  {'Week':<36} {'Income':>10}  {'Expenses':>10}  {'Net':>10}")
        print(f"  {'-' * 66}")
        for w in weekly:
            print(
                f"  {w['label']:<36} {_fmt_amount(w['income']):>10}  "
                f"{_fmt_amount(w['expenses']):>10}  {_fmt_amount(w['net']):>10}"
            )

    # Ledger
    if rows:
        print()
        print("  LEDGER")
        print(f"  {'-' * 66}")
        print(f"  {'Date':<12} {'Type':<8} {'Amount':>10}  Description")
        print(f"  {'-' * 66}")
        for r in rows:
            print(f"  {r['date']:<12} {r['type']:<8} {_fmt_amount(r['amount']):>10}  {r['description']}")

    print()
    print("=" * 70)
    print(f"  Ledger file: {LEDGER_FILE}")
    print("=" * 70)

    _write_summary_section()
    _log_action(f"REPORT | income={total_income} | expenses={total_expenses} | net={net}")


# ──────────────────────────────────────────────────────────────────────────────
# CLI
# ──────────────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        prog="accounting_manager",
        description="Accounting Manager — maintain vault ledger and generate reports.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python accounting_manager.py --add --type income  --amount 1500    --description "Client payment"
  python accounting_manager.py --add --type expense --amount 49.99   --description "Notion subscription"
  python accounting_manager.py --summary
  python accounting_manager.py --weekly
  python accounting_manager.py --report
  python accounting_manager.py --list
        """,
    )

    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--add",     action="store_true", help="Add a new transaction to the ledger")
    mode.add_argument("--summary", action="store_true", help="Print total income / expense / net")
    mode.add_argument("--weekly",  action="store_true", help="Print week-by-week breakdown")
    mode.add_argument("--report",  action="store_true", help="Full report: totals + weekly + ledger")
    mode.add_argument("--list",    action="store_true", help="List all raw ledger rows")

    # --add flags
    parser.add_argument("--type",        choices=["income", "expense"], help="Transaction type")
    parser.add_argument("--amount",      type=str,                      help="Amount (e.g. 1500 or 1500.00)")
    parser.add_argument("--description", type=str, default="",          help="Short description")

    args = parser.parse_args()

    if args.add:
        if not args.type:
            parser.error("--add requires --type (income or expense)")
        if not args.amount:
            parser.error("--add requires --amount")
        try:
            amount = _parse_amount(args.amount)
        except ValueError as exc:
            print(f"ERROR: {exc}")
            sys.exit(1)
        add_entry(args.type, amount, args.description or "")

    elif args.summary:
        cmd_summary()

    elif args.weekly:
        cmd_weekly()

    elif args.report:
        cmd_report()

    elif args.list:
        cmd_list()


if __name__ == "__main__":
    main()
