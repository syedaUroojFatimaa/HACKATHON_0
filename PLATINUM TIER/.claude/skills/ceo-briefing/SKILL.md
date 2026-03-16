# ceo-briefing

Generate a CEO-ready weekly executive briefing at `Reports/CEO_Weekly.md`.

Aggregates live data from across the vault: completed tasks, emails sent, pending
approvals, financial totals, and scheduler health — all from the past 7 days.

## Usage

```bash
# Force-generate immediately
python .claude/skills/ceo-briefing/scripts/ceo_briefing.py --now

# Generate only if 7+ days since last run  (used by scheduler — runs automatically)
python .claude/skills/ceo-briefing/scripts/ceo_briefing.py --check

# Preview the report in the terminal without writing any files
python .claude/skills/ceo-briefing/scripts/ceo_briefing.py --preview
```

## Modes

| Flag | Description |
|------|-------------|
| `--now` | Force-generate the briefing immediately |
| `--check` | Generate only if 7 days have passed since last run (scheduler-safe) |
| `--preview` | Print the full report to stdout; no files written |

## Output Files

| File | Description |
|------|-------------|
| `Reports/CEO_Weekly.md` | Always the latest briefing (overwritten weekly) |
| `Reports/CEO_Weekly_YYYY-WNN.md` | Immutable dated archive (e.g. `CEO_Weekly_2026-W08.md`) |

## Report Sections

### 1. Tasks Completed This Week
Table of files moved to `Done/` in the past 7 days, including task type and completion timestamp.

### 2. Emails Sent This Week
Emails recorded in `Logs/actions.log` and `Logs/business.log` within the past 7 days — time, recipient, subject, status.

### 3. Pending Approvals
All `.md` files in `Needs_Approval/` awaiting a human decision, with age in days.
Includes a reminder to open and write `APPROVED` or `REJECTED`.

### 4. Financial Summary (Current Month)
Total income, total expenses, and net cashflow from `Accounting/Current_Month.md`.
Requires the `accounting-manager` skill to be active.

### 5. System Health
Scheduler status (running/stopped), last cycle time, folder counts (Inbox / Needs_Action / Needs_Approval / Done), and log file sizes.

## Scheduling (Auto-Run)

The briefing is wired into the Silver Scheduler (`scripts/run_ai_employee.py`) as **Step 5** of every cycle. The `--check` gate means it generates exactly once per 7-day rolling window regardless of cycle frequency.

```
Scheduler cycle:
  Step 1  Inbox scan
  Step 2  Task planner
  Step 3  Process tasks
  Step 4  Check approvals
  Step 5  CEO Briefing (weekly)   ← this skill
  Step 6  Log rotation
```

To trigger immediately without waiting for the scheduler:
```bash
python .claude/skills/ceo-briefing/scripts/ceo_briefing.py --now
```

## State File

`Logs/.ceo_briefing_state.json` — tracks last run time and summary stats.

```json
{
  "last_run": "2026-02-19T18:00:00+00:00",
  "week": "2026-W08",
  "tasks": 12,
  "emails": 3,
  "approvals": 1
}
```

Delete this file to force the next `--check` call to regenerate immediately.

## Exit Codes

| Code | Meaning |
|------|---------|
| `0` | Success (or not yet due in `--check` mode) |
| `1` | Error writing report |

## Notes

- Pure stdlib — no pip installs required.
- All output to stdout is ASCII-safe (no Unicode box characters).
- Report files are written as UTF-8 Markdown.
- Vault data is read with `errors='replace'` so corrupt log lines never crash the skill.
- The scheduler integration is non-breaking: if the skill is missing, the scheduler logs nothing and continues normally.
