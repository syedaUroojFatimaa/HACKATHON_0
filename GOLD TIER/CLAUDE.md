# Gold Tier AI Employee — Obsidian Vault

## Project Overview

This is an Obsidian vault that acts as the workspace for a **Gold Tier** AI Employee.
Claude Code is the AI agent that reads from and writes to this vault to manage tasks autonomously.
All AI functionality is implemented as **Agent Skills** — self-contained, executable modules.

**Primary outbound channel: Email (Gmail)**
Social media skills (Twitter, Facebook) are implemented and ready to activate via `.env` credentials.
LinkedIn skills exist but are **dormant** — email is used instead.

---

## Vault Structure

```
/Inbox              — Drop zone for new files. Watchers detect them here.
/Needs_Action       — Tasks awaiting processing. Structured Markdown files.
/Needs_Approval     — Human-in-the-loop gate. Files wait for APPROVED/REJECTED.
/Done               — Completed tasks (archived with metadata).
/Errors             — Quarantined stuck tasks (auto-moved by error-recovery).
/Logs               — System_Log.md, actions.log, ai_employee.log, state files.
/Plans              — Generated planning documents and the task template.
/Reports            — CEO_Weekly.md, Social_Log.md (generated outputs).
/Accounting         — Current_Month.md markdown accounting ledger.
/scripts            — Core orchestration scripts.
/mcp                — MCP server implementations (business-mcp, odoo-mcp).
/mcp_servers        — Legacy email MCP server (kept for compatibility).
/.claude/skills     — Agent Skill definitions and scripts (16 skills).
/.claude/commands   — Slash command definitions for Claude Code.
```

---

## Key Files

- **Dashboard.md** — Central overview showing pending and completed tasks.
- **Company_Handbook.md** — Operating rules the AI agent must follow.
- **Architecture.md** — Full system architecture and lessons learned.
- **Logs/System_Log.md** — Chronological record of all vault activity.
- **Logs/actions.log** — Detailed action log for all skills.
- **Logs/ai_employee.log** — Scheduler-specific log (rotated at 5 MB).
- **Plans/task_template.md** — Standard template for new task files.
- **Reports/CEO_Weekly.md** — Latest weekly executive briefing.
- **Reports/Social_Log.md** — Persistent log of all social media posts.
- **.env** — Environment variables for all service credentials.

---

## Operational Rules (from Company Handbook)

1. **Always log important actions.** Record every meaningful action in `Logs/System_Log.md`.
2. **Never take destructive actions without confirmation.** Ask before deleting or overwriting.
3. **Move completed tasks to Done.** Update Dashboard.md when tasks move.
4. **Keep task files structured.** Use front-matter (type, status, priority, created_at, related_files).
5. **If unsure, ask for clarification.** Do not guess or assume intent.

---

## Agent Skills

### Slash Commands (`.claude/commands/`)

| Command | Purpose |
|---------|---------|
| `/process-tasks` | Read tasks from Needs_Action, mark completed, move to Done, update Dashboard and Log |
| `/plan-tasks` | Analyze pending tasks and generate a prioritized execution plan in Plans/ |
| `/watch-inbox` | Start the file system watcher that monitors Inbox for new files |
| `/rotate-logs` | Check log file sizes and rotate any that exceed the size limit |

### Agent Skills (`.claude/skills/`) — 16 skills total

#### Core Vault
| Skill | Script | Purpose |
|-------|--------|---------|
| **vault-watcher** | `scripts/watch_inbox.py` | Monitor Inbox/ for new .md files, create tasks |
| **task-planner** | `scripts/task_planner.py` | Analyze inbox files, generate step-by-step execution plans |
| **silver-scheduler** | `scripts/run_ai_employee.py` | Central orchestrator — full cycle every 300s |
| **vault-file-manager** | `move_task.py` | Move files between Inbox/, Needs_Action/, Done/ |
| **human-approval** | `request_approval.py` | Human-in-the-loop gate for sensitive actions |
| **ralph-wiggum-loop** | `ralph_loop.py` | Autonomous step-by-step task executor with safety gates |
| **error-recovery** | `error_recovery.py` | Detect and quarantine stuck tasks, retry up to 3x |

#### Communication (Email — primary channel)
| Skill | Script | Purpose |
|-------|--------|---------|
| **gmail-send** | `send_email.py` | Send real emails via Gmail SMTP |
| **gmail-watcher** | `watch_gmail.py` | Monitor Gmail inbox, create tasks from new emails |

#### Social Media
| Skill | Script | Status | Purpose |
|-------|--------|--------|---------|
| **social-summary** | `social_summary.py` | Active | Log all social posts to Reports/Social_Log.md |
| **twitter-post** | `post_twitter.py` | Ready* | Post to Twitter/X via API v2 (tweepy) |
| **facebook-post** | `post_facebook.py` | Ready* | Post to Facebook Page via Meta Graph API |
| **linkedin-post** | `post_linkedin.py` | Dormant | LinkedIn browser automation (not in use) |
| **linkedin-auto-post** | `auto_post.py` | Dormant | Auto-generate + LinkedIn post (not in use) |

(*) Ready to activate: add credentials to .env. Run `--status` flag for instructions.

#### Business Intelligence
| Skill | Script | Purpose |
|-------|--------|---------|
| **accounting-manager** | `accounting_manager.py` | Markdown ledger — income/expense tracking |
| **ceo-briefing** | `ceo_briefing.py` | Weekly executive briefing → Reports/CEO_Weekly.md |

### MCP Servers

| Server | Location | Protocol | Purpose |
|--------|----------|----------|---------|
| **business-mcp** (v2.0.0) | `mcp/business_mcp/server.py` | JSON-RPC/stdio | Email send + activity logging. Production-ready with retry, rate-limit, thread-safe rotation. |
| **odoo-mcp** (v1.0.0) | `mcp/odoo_mcp/server.py` | JSON-RPC/stdio | Odoo Community accounting — 6 tools: health_check, get_invoices, create_invoice, get_vendor_bills, accounting_summary, create_journal_entry |
| **email-server** (legacy) | `mcp_servers/email_server.py` | JSON-RPC/stdio | Legacy Gmail SMTP wrapper (kept for compatibility) |

---

## Scheduling

| Method | Command |
|--------|---------|
| **Daemon mode** | `python scripts/run_ai_employee.py --daemon --interval 300` |
| **Single run** | `python scripts/run_ai_employee.py --once` |
| **OS scheduler** | `python scripts/setup_scheduler.py --install --interval 5` |
| **Status** | `python scripts/run_ai_employee.py --status` |

### Scheduler Cycle (every 300s)
1. Inbox scan → Needs_Action/
2. Task planning → Plans/
3. Ralph loop → step execution with safety gates
4. Process tasks → Done/
5. Approval resolution → Needs_Approval/
6. Error recovery → Errors/
7. CEO briefing (weekly gate) → Reports/CEO_Weekly.md
8. Log rotation

---

## Task File Format

Every task in Needs_Action/ follows this structure:

```markdown
---
type: file_review
status: pending
priority: medium
created_at: YYYY-MM-DD HH:MM:SS UTC
related_files: ["filename"]
---

# Task Title

## Description
What needs to be done.

## Steps
- [ ] Step 1
- [ ] Step 2

## Notes
Additional context.
```

---

## Environment Variables

Set these in `.env` or your shell environment:

### Required (active features)
| Variable | Required By | Purpose |
|----------|-------------|---------|
| `EMAIL_ADDRESS` | gmail-send, gmail-watcher, business-mcp | Gmail address |
| `EMAIL_PASSWORD` | gmail-send, gmail-watcher, business-mcp | Gmail App Password |
| `ODOO_DB` | odoo-mcp | Odoo database name |
| `ODOO_PASSWORD` | odoo-mcp | Odoo admin password |

### Optional (Odoo defaults)
| Variable | Default | Purpose |
|----------|---------|---------|
| `ODOO_URL` | `http://localhost:8069` | Odoo server URL |
| `ODOO_USERNAME` | `admin` | Odoo login username |

### To activate social media skills
| Variable | Required By | Purpose |
|----------|-------------|---------|
| `TWITTER_API_KEY` | twitter-post | Twitter App API key |
| `TWITTER_API_SECRET` | twitter-post | Twitter App API secret |
| `TWITTER_ACCESS_TOKEN` | twitter-post | Twitter account access token |
| `TWITTER_ACCESS_SECRET` | twitter-post | Twitter account access secret |
| `FACEBOOK_PAGE_ID` | facebook-post | Facebook Page ID |
| `FACEBOOK_ACCESS_TOKEN` | facebook-post | Facebook Page access token |

### Dormant (LinkedIn — not in active use)
| Variable | Required By | Purpose |
|----------|-------------|---------|
| `LINKEDIN_EMAIL` | linkedin-post, linkedin-auto-post | LinkedIn login (dormant skills) |
| `LINKEDIN_PASSWORD` | linkedin-post, linkedin-auto-post | LinkedIn password (dormant skills) |

---

## How Claude Code Interacts with the Vault

- **Reading:** Claude Code reads task files from Needs_Action/, Dashboard.md for status, System_Log.md for history.
- **Writing:** Claude Code writes completed tasks to Done/, updates Dashboard.md, appends to System_Log.md, generates reports in Plans/ and Reports/.
- **Approvals:** Sensitive actions are submitted to Needs_Approval/ and block until a human writes APPROVED or REJECTED.
- **External actions:** Email via business-mcp or gmail-send skill. Accounting via odoo-mcp. Social posts via twitter-post or facebook-post skills (when configured).
- **All reads/writes** go through Claude Code's native file tools (Read, Write, Edit, Glob).

---

## Architecture Reference

See **Architecture.md** at vault root for:
- Full system architecture diagram
- Component catalogue
- Data flow walkthrough
- Design decisions
- Lessons learned
- Gold Tier requirements coverage
