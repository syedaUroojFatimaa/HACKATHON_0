# Silver Tier AI Employee — Obsidian Vault

## Project Overview

This is an Obsidian vault that acts as the workspace for a **Silver Tier** AI Employee.
Claude Code is the AI agent that reads from and writes to this vault to manage tasks autonomously.
All AI functionality is implemented as **Agent Skills** — self-contained, executable modules.

## Vault Structure

```
/Inbox              — Drop zone for new files. Watchers detect them here.
/Needs_Action       — Tasks awaiting processing. Structured Markdown files.
/Needs_Approval     — Human-in-the-loop gate. Files wait for APPROVED/REJECTED.
/Done               — Completed tasks (archived with metadata).
/Logs               — System_Log.md, actions.log, ai_employee.log, state files.
/Plans              — Generated planning documents and the task template.
/scripts            — Silver Tier orchestration scripts.
/mcp_servers        — MCP server implementations (email).
/.claude/skills     — Agent Skill definitions and embedded scripts.
/.claude/commands   — Slash command definitions for Claude Code.
```

## Key Files

- **Dashboard.md** — Central overview showing pending and completed tasks.
- **Company_Handbook.md** — Operating rules the AI agent must follow.
- **Logs/System_Log.md** — Chronological record of all vault activity.
- **Logs/actions.log** — Detailed action log for all skills.
- **Logs/ai_employee.log** — Scheduler-specific log (rotated at 5 MB).
- **Plans/task_template.md** — Standard template for new task files.
- **.env** — Environment variables for email and LinkedIn credentials.

## Operational Rules (from Company Handbook)

1. **Always log important actions.** Record every meaningful action in `Logs/System_Log.md`.
2. **Never take destructive actions without confirmation.** Ask before deleting or overwriting.
3. **Move completed tasks to Done.** Update Dashboard.md when tasks move.
4. **Keep task files structured.** Use front-matter (type, status, priority, created_at, related_files).
5. **If unsure, ask for clarification.** Do not guess or assume intent.

## Agent Skills

### Slash Commands (`.claude/commands/`)

| Command | Purpose |
|---------|---------|
| `/process-tasks` | Read tasks from Needs_Action, mark completed, move to Done, update Dashboard and Log |
| `/plan-tasks` | Analyze pending tasks and generate a prioritized execution plan in Plans/ |
| `/watch-inbox` | Start the file system watcher that monitors Inbox for new files |
| `/rotate-logs` | Check log file sizes and rotate any that exceed the size limit |

### Agent Skills (`.claude/skills/`)

| Skill | Script | Purpose |
|-------|--------|---------|
| **vault-watcher** | `scripts/watch_inbox.py` | Monitor Inbox/ for new .md files, create tasks |
| **task-planner** | `scripts/task_planner.py` | Analyze inbox files, generate step-by-step execution plans |
| **silver-scheduler** | `scripts/run_ai_employee.py` | Central orchestrator — runs watcher + planner + processor + approvals in a loop |
| **human-approval** | `.claude/skills/human-approval/scripts/request_approval.py` | Human-in-the-loop gate for sensitive actions |
| **vault-file-manager** | `.claude/skills/vault-file-manager/scripts/move_task.py` | Move files between Inbox/, Needs_Action/, Done/ |
| **gmail-send** | `.claude/skills/gmail-send/scripts/send_email.py` | Send real emails via Gmail SMTP |
| **gmail-watcher** | `.claude/skills/gmail-watcher/scripts/watch_gmail.py` | Monitor Gmail inbox, create tasks from new emails |
| **linkedin-post** | `.claude/skills/linkedin-post/scripts/post_linkedin.py` | Publish LinkedIn posts via Playwright browser automation |
| **linkedin-auto-post** | `.claude/skills/linkedin-auto-post/scripts/auto_post.py` | Generate business content and auto-post to LinkedIn |

### MCP Servers (`mcp_servers/`)

| Server | Protocol | Purpose |
|--------|----------|---------|
| **email-server** | JSON-RPC over stdio | MCP server wrapping Gmail SMTP — configured in `.claude/settings.json` |

## Scheduling

| Method | Command |
|--------|---------|
| **Daemon mode** | `python scripts/run_ai_employee.py --daemon --interval 300` |
| **Single run** | `python scripts/run_ai_employee.py --once` |
| **OS scheduler** | `python scripts/setup_scheduler.py --install --interval 5` |
| **Status** | `python scripts/run_ai_employee.py --status` |

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

## Environment Variables

Set these in `.env` or your shell environment:

| Variable | Required By | Purpose |
|----------|-------------|---------|
| `EMAIL_ADDRESS` | gmail-send, gmail-watcher, MCP server | Gmail address |
| `EMAIL_PASSWORD` | gmail-send, gmail-watcher, MCP server | Gmail App Password |
| `LINKEDIN_EMAIL` | linkedin-post, linkedin-auto-post | LinkedIn login email |
| `LINKEDIN_PASSWORD` | linkedin-post, linkedin-auto-post | LinkedIn login password |

## How Claude Code Interacts with the Vault

- **Reading:** Claude Code reads task files from Needs_Action/, reads Dashboard.md for status overview, reads System_Log.md for history.
- **Writing:** Claude Code writes completed tasks to Done/, updates Dashboard.md tables, appends entries to System_Log.md, generates plan documents in Plans/.
- **Approvals:** Sensitive actions are submitted to Needs_Approval/ and block until a human writes APPROVED or REJECTED.
- **External actions:** Email sending via MCP server or gmail-send skill. LinkedIn posting via linkedin-post skill.
- All reads and writes go through Claude Code's native file tools (Read, Write, Edit, Glob).
