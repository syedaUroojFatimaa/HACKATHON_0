# accounting-manager

Maintain the vault accounting ledger, log income and expense entries, and generate weekly and monthly financial summaries.

Ledger file: `Accounting/Current_Month.md` (auto-created if missing)
Actions log: `Logs/actions.log`

## Usage

```bash
# Add a transaction
python .claude/skills/accounting-manager/scripts/accounting_manager.py \
  --add --type income --amount 1500.00 --description "Client payment - Acme Corp"

python .claude/skills/accounting-manager/scripts/accounting_manager.py \
  --add --type expense --amount 49.99 --description "Notion subscription"

# Reports
python .claude/skills/accounting-manager/scripts/accounting_manager.py --summary
python .claude/skills/accounting-manager/scripts/accounting_manager.py --weekly
python .claude/skills/accounting-manager/scripts/accounting_manager.py --report
python .claude/skills/accounting-manager/scripts/accounting_manager.py --list
```

## Inputs

| Flag | Required | Description |
|------|----------|-------------|
| `--add` | Mode | Add a new transaction |
| `--summary` | Mode | Print total income / expense / net |
| `--weekly` | Mode | Print week-by-week breakdown |
| `--report` | Mode | Full report: totals + weekly + ledger |
| `--list` | Mode | List all raw ledger rows |
| `--type` | With `--add` | `income` or `expense` |
| `--amount` | With `--add` | Numeric amount (e.g. `1500` or `1500.00`) |
| `--description` | With `--add` | Short description of the transaction |

Exactly one mode flag must be provided per invocation.

## Output

### `--add`
Prints a confirmation and appends one row to the ledger table. Also refreshes the `## Summary` section.

```
SUCCESS: Added income entry
  Date:        2026-02-19
  Type:        income
  Amount:      $1,500.00
  Description: Client payment - Acme Corp
  Ledger:      /path/to/Accounting/Current_Month.md
```

### `--summary`
```
=============================================
  Accounting Summary — February 2026
=============================================
  Total Income    :    $3,200.00
  Total Expenses  :      $649.99
  ──────────────────────────────────────────
  Net             :    $2,550.01
  Transactions    : 5
=============================================
```

### `--weekly`
```
======================================================================
  Weekly Breakdown — February 2026
======================================================================
  Week                               Income     Expenses         Net
  ─────────────────────────────────────────────────────────────────────
  Week 07  (Feb 10 – Feb 16)     $1,200.00      $200.00    $1,000.00
  Week 08  (Feb 17 – Feb 23)     $2,000.00      $449.99    $1,550.01
======================================================================
```

### `--report`
Full combined output: totals + weekly breakdown + all ledger rows.

### `--list`
Tabular view of all raw ledger rows.

## Ledger File Format

`Accounting/Current_Month.md` is a structured Markdown file:

```markdown
---
type: accounting
month: 2026-02
created_at: 2026-02-19 10:00:00 UTC
last_updated: 2026-02-19 12:30:00 UTC
---

# Accounting — February 2026

## Ledger

| Date       | Type    | Amount    | Description                    |
|------------|---------|-----------|--------------------------------|
| 2026-02-19 | income  |   1500.00 | Client payment - Acme Corp     |
| 2026-02-19 | expense |     49.99 | Notion subscription            |

---

## Summary

> Last updated: 2026-02-19 12:30:00 UTC

### Totals
...

### Weekly Breakdown
...
```

The `## Summary` section is always auto-generated and overwritten when any report or `--add` command runs.

## Exit Codes

| Code | Meaning |
|------|---------|
| `0` | Success |
| `1` | Invalid input, missing required flag, or I/O error |

## Notes

- Thread-safe: file writes are protected by `threading.Lock`.
- Amounts are validated with Python `Decimal` — no floating-point rounding errors.
- Weekly grouping follows ISO week numbers (weeks start Monday).
- `Accounting/` directory is created automatically if it does not exist.
- Standard library only — no pip installs required.
- All add operations are logged to `Logs/actions.log`.
