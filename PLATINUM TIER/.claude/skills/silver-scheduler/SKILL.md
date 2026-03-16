# Silver Scheduler Skill

## Name
silver-scheduler

## Description
Central orchestrator that runs the vault-watcher and task-planner skills in a timed loop. Each cycle scans `Inbox/` for new files, creates tasks, generates execution plans, and processes everything through to `Done/`. Supports daemon mode (continuous), single execution, and a status dashboard. Includes lock-file protection against duplicate instances and automatic log rotation at 5 MB.

## Trigger
Manual start via command line.

## Usage

```bash
# Daemon mode — run continuously (default interval: 5 minutes)
python scripts/run_ai_employee.py --daemon

# Daemon with custom interval (seconds)
python scripts/run_ai_employee.py --daemon --interval 120

# Single execution — one cycle then exit
python scripts/run_ai_employee.py --once

# Status — show inbox count, pending tasks, completed tasks, approvals
python scripts/run_ai_employee.py --status
```

## Behavior

### Daemon mode (`--daemon`)
1. **Acquire lock** — write PID to `logs/.scheduler.lock`. If a lock already exists with a running PID, abort to prevent duplicates. Stale locks (dead PID) are cleaned automatically.
2. **Per-cycle workflow** (repeats every `--interval` seconds):
   a. **Inbox scan** — detect new files in `Inbox/`, create task files in `Needs_Action/` (vault-watcher logic).
   b. **Plan** — invoke `task_planner.py` to analyze unprocessed `.md` inbox files and generate execution plans in `Needs_Action/`.
   c. **Process** — invoke `process_tasks.py` to mark tasks complete, move to `Done/`, update Dashboard and System_Log.
   d. **Log rotation** — if `logs/ai_employee.log` exceeds 5 MB, archive it.
3. **Shutdown** — on `SIGINT`/`SIGTERM`, release the lock file and log shutdown.

### Single execution (`--once`)
Run one complete cycle (steps a–d above), then exit. No lock file is held beyond the run.

### Status (`--status`)
Print a snapshot of the vault:
- Inbox file count
- Needs_Action pending tasks
- Needs_Approval pending approvals
- Done completed tasks
- Last log entries

## Log Rotation

| Setting | Value |
|---------|-------|
| Log file | `logs/ai_employee.log` |
| Max size | 5 MB (5,242,880 bytes) |
| Archive format | `ai_employee_<YYYY-MM-DD>.log` (counter suffix if duplicate) |

## Lock File

| File | Purpose |
|------|---------|
| `logs/.scheduler.lock` | Contains the PID of the running scheduler. Prevents duplicate instances. Removed on clean shutdown. Stale locks (dead PID) are auto-cleaned on startup. |

## Configuration

| Parameter | Default | Notes |
|-----------|---------|-------|
| `--interval` | 300 | Seconds between cycles (daemon mode) |
| `--daemon` | — | Run continuously |
| `--once` | — | Single cycle then exit |
| `--status` | — | Show vault status snapshot |

## Dependencies

- Python 3.8+
- Standard library only.
- Requires in vault root: `process_tasks.py`
- Requires in `scripts/`: `task_planner.py`, `watch_inbox.py`

## Files

| Path | Role |
|------|------|
| `.claude/skills/silver-scheduler/SKILL.md` | This skill definition |
| `scripts/run_ai_employee.py` | Scheduler entry point |
| `logs/ai_employee.log` | Scheduler-specific log (rotated at 5 MB) |
| `logs/.scheduler.lock` | PID lock file for singleton enforcement |
