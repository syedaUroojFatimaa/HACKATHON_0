# Cloud vs Local Work-Zone Architecture

## Overview

This document describes the separated work-zone architecture that divides responsibilities between Cloud and Local environments to prevent conflicts and ensure clear ownership.

---

## Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────────────┐
│                         VAULT ROOT                                       │
│                                                                          │
│  ┌────────────────────────────────────────────────────────────────┐     │
│  │                    Needs_Action/                                │     │
│  │  ├── email/          ← Email tasks from inbox                  │     │
│  │  ├── social/         ← Social media requests                   │     │
│  │  └── general/        ← Other tasks                             │     │
│  └────────────────────────────────────────────────────────────────┘     │
│                                                                          │
│  ┌────────────────────────────────────────────────────────────────┐     │
│  │                  Pending_Approval/                              │     │
│  │  ├── email/          ← Cloud drafts email replies              │     │
│  │  ├── social/         ← Cloud drafts social posts               │     │
│  │  └── general/        ← Other approvals                         │     │
│  └────────────────────────────────────────────────────────────────┘     │
│                                                                          │
│  ┌────────────────────────────────────────────────────────────────┐     │
│  │                   In_Progress/                                  │     │
│  │  ├── cloud/          ← Cloud-is-working (claimed)              │     │
│  │  │   └── .zone_owner ← "CLOUD"                                 │     │
│  │  └── local/          ← Local-is-working (claimed)              │     │
│  │      ├── .zone_owner ← "LOCAL"                                 │     │
│  │      └── .dashboard_queue.json ← Dashboard write queue         │     │
│  └────────────────────────────────────────────────────────────────┘     │
│                                                                          │
│  ┌────────────────────────────────────────────────────────────────┐     │
│  │                     Approved/                                   │     │
│  │  ├── email/          ← Completed email tasks                   │     │
│  │  ├── social/         ← Completed social tasks                  │     │
│  │  └── general/        ← Completed general tasks                 │     │
│  └────────────────────────────────────────────────────────────────┘     │
│                                                                          │
│  ┌────────────────────────────────────────────────────────────────┐     │
│  │                    Dashboard.md                                 │     │
│  │  ← SINGLE-WRITER: Only Local zone can write here               │     │
│  └────────────────────────────────────────────────────────────────┘     │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## Responsibilities

### Cloud Zone (Server/Remote)

| Responsibility | Description | Output Location |
|----------------|-------------|-----------------|
| **Email Triage** | Read and categorize incoming emails | `Pending_Approval/email/` |
| **Draft Replies** | Create email reply drafts | `Pending_Approval/email/` |
| **Draft Social Posts** | Create social media content | `Pending_Approval/social/` |
| **Write Approval Files** | Create approval request files | `Pending_Approval/` |

**Cloud NEVER:**
- Sends emails directly
- Posts to social media
- Makes payments
- Writes to Dashboard.md directly

### Local Zone (Your Machine)

| Responsibility | Description | Output Location |
|----------------|-------------|-----------------|
| **Final Send/Post** | Execute email sends and social posts | External APIs |
| **WhatsApp Session** | Manage WhatsApp authentication | `sessions/` |
| **Payments** | Process payment requests | `Accounting/` |
| **Approvals** | Review and approve/reject Cloud drafts | `Approved/` |
| **Dashboard Updates** | Write to Dashboard.md (Single-Writer) | `Dashboard.md` |

**Local NEVER:**
- Drafts content (Cloud does this)
- Writes approval files (Cloud does this)
- Modifies files in Cloud zone

---

## Core Rules

### Rule 1: Claim-by-Move

To claim a task for processing, move it to your zone:

```
Needs_Action/email/new_email.md
         ↓ (Cloud claims)
In_Progress/cloud/new_email.md

Pending_Approval/email/draft_001.md
         ↓ (Local claims)
In_Progress/local/draft_001.md
```

**Implementation:**
- Zone locks prevent double-claiming
- Lock files in `In_Progress/.zone_lock`
- Stale locks (>5 min) are auto-released

### Rule 2: Single-Writer for Dashboard.md

Only the Local zone can write to Dashboard.md:

```
┌─────────────┐    Queue Request    ┌─────────────┐
│    Cloud    │ ──────────────────► │    Local    │
│             │                     │             │
│ Processes   │   .dashboard_queue  │  Writes to  │
│ tasks       │   JSON file         │  Dashboard  │
└─────────────┘                     └─────────────┘
```

**Cloud writes to queue:**
```json
// In_Progress/local/.dashboard_queue.json
[
  {
    "timestamp": "2026-03-16T10:30:00 UTC",
    "action": "email_processed",
    "details": {"task": "email_001", "category": "support"}
  }
]
```

**Local processes queue and writes:**
```
Dashboard.md
├── Activity Log
│   └── | 2026-03-16 10:30 | Email Processed | `email_001` |
```

### Rule 3: Approval Flow

```
1. Cloud processes task
         ↓
2. Cloud creates approval file in Pending_Approval/
         ↓
3. Local claims approval (move to In_Progress/local/)
         ↓
4. Local reviews and decides (approve/reject)
         ↓
5. Local executes action (if approved)
         ↓
6. Move to Approved/
```

---

## Folder Structure Creation (Windows CMD)

```cmd
REM Run the setup script
cd "C:\Users\Dell\Desktop\Hackathon_0\PLATINUM TIER"
scripts\setup_workzones.bat
```

**Or create manually:**

```cmd
REM Core work zones
mkdir Needs_Action\email
mkdir Needs_Action\social
mkdir Needs_Action\general

mkdir Pending_Approval\email
mkdir Pending_Approval\social
mkdir Pending_Approval\general

mkdir In_Progress\cloud
mkdir In_Progress\local

mkdir Approved\email
mkdir Approved\social
mkdir Approved\general

REM Legacy folders
mkdir Inbox Done Errors Plans Reports Accounting Logs
```

---

## Processing Logic

### Cloud Worker Flow

```python
# 1. Scan Needs_Action/ for new tasks
tasks = get_task_files()  # From email/, social/, general/

# 2. Claim task (Claim-by-Move)
claimed = claim_task(task_path, channel)
# Moves: Needs_Action/X/task.md → In_Progress/cloud/task.md

# 3. Process based on channel
if channel == "email":
    triage_email(email_data)
    draft = draft_email_reply(email_data)
elif channel == "social":
    draft = draft_social_post(social_data)

# 4. Create approval file (Cloud's ONLY write)
create_approval_file(
    channel=channel,
    draft=draft,
    destination="Pending_Approval/{channel}/"
)

# 5. Queue dashboard update (Single-Writer)
queue_dashboard_write("email_processed", details)

# 6. Move original to Approved
move_to_approved(task_path)
```

### Local Worker Flow

```python
# 1. Process dashboard queue (Single-Writer)
process_dashboard_queue()
# Reads: In_Progress/local/.dashboard_queue.json
# Writes: Dashboard.md

# 2. Scan Pending_Approval/ for approvals
approvals = get_approval_files()

# 3. Claim approval (Claim-by-Move)
claimed = claim_approval(approval_path, channel)
# Moves: Pending_Approval/X/approval.md → In_Progress/local/approval.md

# 4. Review and decide
decision = review_approval(content)  # approve/reject

# 5. Execute if approved
if decision == "approved":
    if channel == "email":
        execute_email_send(draft)
    elif channel == "social":
        execute_social_post(draft)

# 6. Move to Approved
move_to_approved(approval_path)
```

---

## Example Workflow

### Scenario: Email Reply Workflow

#### Step 1: New Email Arrives

```
Inbox/customer_inquiry.md
```

Content:
```markdown
---
type: email
from: customer@example.com
subject: Question about pricing
received: 2026-03-16 09:00:00 UTC
---

Hi, I'd like to know more about your pricing plans.

Thanks,
John
```

#### Step 2: Cloud Claims and Processes

```cmd
REM Cloud worker runs
python scripts\cloud_worker.py --daemon
```

Cloud moves and processes:
```
Inbox/customer_inquiry.md
         ↓
In_Progress/cloud/customer_inquiry.md
         ↓ (processing)
Pending_Approval/email/approval_customer_inquiry.md
```

Approval file created:
```markdown
---
type: approval_request
channel: email
category: inquiry
created_at: 2026-03-16 09:05:00 UTC
source_task: customer_inquiry.md
zone: cloud
status: pending
---

# Approval Request

**Channel:** email
**Category:** inquiry

---

## Draft Content

---
type: email_draft
status: pending_approval
---

Subject: Re: Question about pricing

Dear John,

Thank you for your inquiry about our pricing plans...

Best regards,
AI Employee

---

## Required Action

- [ ] Review the draft
- [ ] Approve or reject
- [ ] Local zone will send email
```

#### Step 3: Local Reviews and Approves

```cmd
REM Local worker runs
python scripts\local_worker.py --approve
```

Local moves and processes:
```
Pending_Approval/email/approval_customer_inquiry.md
         ↓
In_Progress/local/approval_customer_inquiry.md
         ↓ (review + approve)
Approved/email/approval_customer_inquiry.md
```

#### Step 4: Local Executes Send

```python
# Local executes the email send
execute_email_send(draft)
# → Sends via Gmail API
# → Logs action
```

#### Step 5: Dashboard Updated

Dashboard.md now includes:
```markdown
## Activity Log

| Timestamp | Action | Details |
|-----------|--------|---------|
| 2026-03-16 09:05 | Email Processed | `customer_inquiry` categorized as `inquiry` |
| 2026-03-16 09:10 | Approval Decision | `customer_inquiry` - APPROVED |
```

---

## Command Reference

### Setup

```cmd
REM Create work-zone folder structure
scripts\setup_workzones.bat
```

### Cloud Worker

```cmd
REM Run continuously (daemon)
python scripts\cloud_worker.py --daemon

REM Run single cycle
python scripts\cloud_worker.py --once
```

### Local Worker

```cmd
REM Run continuously (daemon)
python scripts\local_worker.py --daemon

REM Run single cycle
python scripts\local_worker.py --once

REM Process approvals only
python scripts\local_worker.py --approve
```

### Status Checks

```cmd
REM Check zone locks
type In_Progress\.zone_lock

REM Check dashboard queue
type In_Progress\local\.dashboard_queue.json

REM View logs
type Logs\cloud_worker.log
type Logs\local_worker.log
```

---

## Zone Lock Format

```json
{
  "task_email_001": {
    "zone": "cloud",
    "time": "2026-03-16T10:30:00+00:00 UTC"
  },
  "approval_draft_002": {
    "zone": "local",
    "time": "2026-03-16T10:32:00+00:00 UTC"
  }
}
```

---

## Dashboard Queue Format

```json
[
  {
    "timestamp": "2026-03-16T10:30:00+00:00 UTC",
    "zone": "cloud",
    "action": "email_processed",
    "details": {
      "task": "customer_inquiry.md",
      "category": "inquiry",
      "draft_created": true
    }
  }
]
```

---

## Error Handling

### Conflict Detection

If a task is already claimed:
```
[WARN] Task task_001 already claimed
[INFO] Lock held by: cloud (2 minutes ago)
```

### Stale Lock Recovery

Locks older than 5 minutes are auto-released:
```
[INFO] Stale lock detected for task_001 (10 minutes old)
[INFO] Lock released - task available for claim
```

### Dashboard Queue Failure

If Dashboard.md write fails:
```
[ERROR] Dashboard write error: Permission denied
[INFO] Queue preserved - will retry next cycle
```

---

## Best Practices

1. **Always run workers in daemon mode** for continuous processing
2. **Monitor zone locks** to detect stuck tasks
3. **Review approval queue** regularly on Local machine
4. **Check dashboard queue** to ensure Cloud→Local communication works
5. **Archive Approved/** periodically to prevent folder bloat

---

## Troubleshooting

### Task Not Being Processed

```cmd
REM Check if task is in correct folder
dir Needs_Action\email
dir Needs_Action\social

REM Check zone locks
type In_Progress\.zone_lock

REM Check worker logs
type Logs\cloud_worker.log
```

### Approval Stuck in Pending

```cmd
REM Check Pending_Approval folder
dir Pending_Approval\email
dir Pending_Approval\social

REM Run local worker manually
python scripts\local_worker.py --approve
```

### Dashboard Not Updating

```cmd
REM Check dashboard queue
type In_Progress\local\.dashboard_queue.json

REM Run local worker to process queue
python scripts\local_worker.py --once
```
