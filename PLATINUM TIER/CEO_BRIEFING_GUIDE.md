# CEO Weekly Briefing Guide

## Overview

The CEO Weekly Briefing is an automated report generated every Sunday that provides a comprehensive summary of business activities including:

- ✅ Revenue summary
- ✅ Completed tasks
- ✅ Pending approvals
- ✅ Issues and errors
- ✅ Inbox status

---

## Output Location

Briefings are saved to:
```
/Vault/Briefings/YYYY-MM-DD_CEO_Briefing.md
```

Example:
```
Briefings/2026-03-16_CEO_Briefing.md
```

---

## Schedule

| Setting | Value |
|---------|-------|
| **Frequency** | Weekly |
| **Day** | Sunday |
| **Time** | 8:00 AM |
| **Task Name** | `PlatinumTierCEOBriefing` |

---

## Setup

### Step 1: Run Setup (as Administrator)

```cmd
cd "C:\Users\Dell\Desktop\Hackathon_0\PLATINUM TIER"
scripts\setup_ceo_briefing.bat
```

### Step 2: Verify Installation

```cmd
schtasks /Query /TN "PlatinumTierCEOBriefing"
```

### Step 3: Test Generation

```cmd
REM Generate first briefing manually
python ceo_briefing.py --generate

REM Or use the batch script
scripts\run_ceo_briefing_now.bat
```

### Step 4: Verify Output

```cmd
REM Check Briefings folder
dir Briefings

REM View latest briefing
type Briefings\*_CEO_Briefing.md
```

---

## Briefing Content

### Executive Summary

| Metric | This Week | Status |
|--------|-----------|--------|
| Tasks Completed | 15 | 🟢 |
| Revenue | $5,250.00 | 🟢 |
| Pending Approvals | 3 | 🟢 |
| Issues | 0 | 🟢 |

### Revenue Summary

- **Total Revenue:** Sum of all payments/invoices
- **By Category:** Breakdown by service type
- **Recent Transactions:** Last 10 payments
- **Pending Revenue:** Expected income

### Completed Tasks

Groups completed tasks by type:
- Email processed
- Social posts published
- General tasks completed
- Files reviewed

### Pending Approvals

Lists all items awaiting human approval:
- Email drafts
- Social media posts
- General decisions

### Pending Tasks

Shows tasks in queue by priority:
- High priority (action needed)
- Medium priority
- Low priority

### Issues & Errors

Detects and reports:
- Error log entries
- Stuck tasks (>24h in progress)
- System errors

### Inbox Status

Shows unprocessed files in Inbox folder.

---

## Commands

### Generate Briefing

```cmd
REM Generate this week's briefing
python ceo_briefing.py --generate

REM Force regenerate (even if exists)
python ceo_briefing.py --force

REM Preview without saving
python ceo_briefing.py --preview
```

### Check Status

```cmd
REM Check if already generated
python ceo_briefing.py --check

REM View briefing history
python ceo_briefing.py --history
```

### Batch Scripts

```cmd
REM Generate now
scripts\run_ceo_briefing_now.bat

REM Disable auto-generation
scripts\disable_ceo_briefing.bat

REM Re-enable (as Admin)
scripts\enable_ceo_briefing.bat
```

### Task Scheduler Commands

```cmd
REM View task
schtasks /Query /TN "PlatinumTierCEOBriefing"

REM Run manually
schtasks /Run /TN "PlatinumTierCEOBriefing"

REM Delete task
schtasks /Delete /TN "PlatinumTierCEOBriefing" /F
```

---

## Data Sources

| Source | Data Extracted |
|--------|----------------|
| `Done/` | Completed task files |
| `Approved/` | Approved email/social tasks |
| `Accounting/` | Revenue and payments |
| `Pending_Approval/` | Awaiting approval |
| `Needs_Action/` | Pending tasks |
| `Errors/` | Error files |
| `Logs/watcher_errors.log` | Watcher errors |
| `In_Progress/` | Stuck tasks detection |
| `Inbox/` | Unprocessed files |

---

## Revenue Tracking

### Setup Revenue Files

Create revenue tracking files in `Accounting/`:

**Example: `Accounting/revenue_2026.md`**
```markdown
---
type: revenue
year: 2026
---

# Revenue Log

## March 2026

| Date | Client | Amount | Category |
|------|--------|--------|----------|
| 2026-03-01 | Client A | $500.00 | Consulting |
| 2026-03-05 | Client B | $1,200.00 | Development |
```

**Example: `Accounting/payments_received/payment_001.md`**
```markdown
---
type: payment
amount: 500.00
category: consulting
client: Client A
date: 2026-03-01
---

# Payment Received

Payment from Client A for consulting services.
```

### Revenue Categories

The briefing automatically categorizes revenue:
- Consulting
- Development
- Products
- Services
- Uncategorized

---

## Example Briefing Output

```markdown
---
type: ceo_briefing
period: 2026-03-10 to 2026-03-16
generated_at: 2026-03-16 08:00:00 UTC
week_number: 11
year: 2026
---

# CEO Weekly Briefing

> **Period:** 2026-03-10 to 2026-03-16
> **Generated:** 2026-03-16 08:00:00 UTC
> **Week:** 11 of 2026

---

## Executive Summary

| Metric | This Week | Status |
|--------|-----------|--------|
| Tasks Completed | 12 | 🟢 |
| Revenue | $3,450.00 | 🟢 |
| Pending Approvals | 2 | 🟢 |
| Issues | 1 | 🔴 |

---

## Revenue Summary

### Total Revenue: $3,450.00

### Revenue by Category

| Category | Amount |
|----------|--------|
| Consulting | $2,000.00 |
| Development | $1,450.00 |

### Recent Transactions

| Date | File | Amount | Category |
|------|------|--------|----------|
| 2026-03-15 | payment_005.md | $750.00 | Development |
| 2026-03-14 | payment_004.md | $500.00 | Consulting |

---

## Completed Tasks

### Email (5)

| File | Source | Completed |
|------|--------|-----------|
| approval_customer_inquiry.md | Approved/email | 2026-03-15 |

### Social (3)

| File | Source | Completed |
|------|--------|-----------|
| approval_linkedin_post.md | Approved/social | 2026-03-14 |

---

## Pending Approvals

**2 items awaiting approval**

| File | Channel | Category | Created |
|------|---------|----------|---------|
| approval_proposal.md | email | business | 2026-03-15 |

### ⚠️ Action Required

Please review and approve/reject the items above.

---

## Issues & Errors

**1 issue(s) detected**

### Stuck Task (1)

- `task_large_project.md` stuck in local zone for 48h

### 🔧 Recommended Actions

1. Review error logs in `Logs/` folder
2. Check stuck tasks in `In_Progress/` folder
3. Run health check: `python watchdog.py --status`

---

## Key Metrics Summary

```
Week:           2026-03-10 to 2026-03-16
Tasks Done:     12
Revenue:        $3,450.00
Pending:        2 approvals, 5 tasks
Issues:         1
Inbox:          0 files
```

---

*Generated automatically by ceo_briefing.py*
```

---

## Troubleshooting

### Briefing Not Generated

```cmd
REM Check if task exists
schtasks /Query /TN "PlatinumTierCEOBriefing"

REM Run manually
schtasks /Run /TN "PlatinumTierCEOBriefing"

REM Check logs
type Logs\ceo_briefing.log
```

### No Revenue Data

Ensure revenue files exist in `Accounting/`:
```cmd
dir Accounting\payments_received
dir Accounting\revenue*.md
```

### Empty Completed Tasks

Check that completed tasks are being moved to `Done/`:
```cmd
dir Done
dir Approved\email
dir Approved\social
```

### Permission Errors

Run as Administrator:
```cmd
REM Re-setup the task
scripts\setup_ceo_briefing.bat
```

---

## Customization

### Change Schedule Day/Time

Edit `scripts\setup_ceo_briefing.bat`:
```batch
set "SCHEDULE_DAY=SUNDAY"
set "SCHEDULE_TIME=08:00"
```

Then re-run:
```cmd
scripts\setup_ceo_briefing.bat
```

### Modify Briefing Content

Edit `ceo_briefing.py` to:
- Add new metrics
- Change report format
- Add custom sections

### Briefing Retention

To auto-archive old briefings:
```cmd
REM Create archive folder
mkdir Briefings\Archive

REM Move briefings older than 90 days
forfiles /p Briefings /s /m *_CEO_Briefing.md /d -90 /c "cmd /c move @path Briefings\Archive"
```

---

## Integration

### Email Delivery

To email the briefing automatically:

```python
# Add to ceo_briefing.py after save_briefing()
send_email_briefing(filepath)
```

### Slack/Teams Notification

```batch
REM In run_ceo_briefing.bat, after generation
curl -X POST -H 'Content-type: application/json' ^
  --data "{\"text\":\"Weekly CEO Briefing generated!\"}" ^
  https://hooks.slack.com/services/YOUR/WEBHOOK/URL
```

### Dashboard Integration

The briefing can be parsed for dashboard metrics:
```python
import re

with open("Briefings/latest_CEO_Briefing.md") as f:
    content = f.read()

# Extract revenue
revenue_match = re.search(r'Revenue:.*\$(\d+)', content)
revenue = float(revenue_match.group(1)) if revenue_match else 0
```

---

## Best Practices

1. **Review briefings weekly** - Every Monday morning
2. **Address pending approvals** - Clear the queue
3. **Track revenue trends** - Compare week-over-week
4. **Monitor issues** - Fix recurring problems
5. **Archive old briefings** - Keep recent 12 weeks accessible

---

## Quick Reference

| Task | Command |
|------|---------|
| Setup auto-generation | `scripts\setup_ceo_briefing.bat` (Admin) |
| Generate now | `python ceo_briefing.py --generate` |
| View history | `python ceo_briefing.py --history` |
| Check status | `python ceo_briefing.py --check` |
| Disable | `scripts\disable_ceo_briefing.bat` |
| Enable | `scripts\enable_ceo_briefing.bat` (Admin) |

---

## File Locations

| File | Purpose |
|------|---------|
| `ceo_briefing.py` | Main briefing generator |
| `Briefings/` | Generated briefings |
| `scripts/setup_ceo_briefing.bat` | Task Scheduler setup |
| `scripts/run_ceo_briefing_now.bat` | Manual trigger |
| `Logs/ceo_briefing.log` | Generation log |
