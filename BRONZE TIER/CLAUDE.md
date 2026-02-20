# Bronze Tier AI Employee — Obsidian Vault

## Project Overview

This is an Obsidian vault that acts as the workspace for a Bronze Tier AI Employee.
Claude Code is the AI agent that reads from and writes to this vault to manage tasks autonomously.

## Vault Structure

```
/Inbox          — Drop zone for new files. The file watcher detects them here.
/Needs_Action   — Tasks awaiting processing. Each is a structured Markdown file.
/Done           — Completed tasks (archived with metadata).
/Logs           — System_Log.md (activity journal) and watcher_errors.log.
/Plans          — Generated planning documents and the task template.
```

## Key Files

- **Dashboard.md** — Central overview showing pending and completed tasks.
- **Company_Handbook.md** — Operating rules the AI agent must follow.
- **Logs/System_Log.md** — Chronological record of all vault activity.
- **Plans/task_template.md** — Standard template for new task files.

## Operational Rules (from Company Handbook)

1. **Always log important actions.** Record every meaningful action in `Logs/System_Log.md`.
2. **Never take destructive actions without confirmation.** Ask before deleting or overwriting.
3. **Move completed tasks to Done.** Update Dashboard.md when tasks move.
4. **Keep task files structured.** Use front-matter (type, status, priority, created_at, related_files).
5. **If unsure, ask for clarification.** Do not guess or assume intent.

## Agent Skills (Slash Commands)

All AI functionality is implemented as Agent Skills via `.claude/commands/`:

| Command | Purpose |
|---------|---------|
| `/process-tasks` | Read tasks from Needs_Action, mark completed, move to Done, update Dashboard and Log |
| `/plan-tasks` | Analyze pending tasks and generate a prioritized execution plan in Plans/ |
| `/watch-inbox` | Start the file system watcher that monitors Inbox for new files |
| `/rotate-logs` | Check log file sizes and rotate any that exceed the size limit |

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

## How Claude Code Interacts with the Vault

- **Reading:** Claude Code reads task files from Needs_Action/, reads Dashboard.md for status overview, reads System_Log.md for history.
- **Writing:** Claude Code writes completed tasks to Done/, updates Dashboard.md tables, appends entries to System_Log.md, generates plan documents in Plans/.
- All reads and writes go through Claude Code's native file tools (Read, Write, Edit, Glob).
