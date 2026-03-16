# Vault Watcher Skill

## Name
vault-watcher

## Description
Continuously monitors the `Inbox/` folder for new `.md` files. When a new Markdown file is detected, it logs the event to `logs/actions.log` and triggers the AI processing workflow (task creation + completion pipeline). Files are tracked to prevent duplicate processing.

## Trigger
Manual start via command line or agent invocation.

## Usage

```bash
# Start the watcher (default: polls every 15 seconds)
python scripts/watch_inbox.py

# Custom poll interval (10-30 seconds)
python scripts/watch_inbox.py --interval 20

# Custom inbox path
python scripts/watch_inbox.py --inbox path/to/Inbox
```

## Behavior

1. **Startup** — Validates that the Inbox, Needs_Action, Done, Logs, and logs directories exist (creates them if missing). Loads the processed-file ledger from `logs/.watcher_state.json`.
2. **Poll loop** — Every N seconds (default 15, range 10-30):
   - Scans `Inbox/` for `.md` files.
   - Skips any file already recorded in the state ledger.
   - For each new file:
     a. Appends a detection entry to `logs/actions.log`.
     b. Invokes the processing pipeline (`process_tasks.py`) which creates a task in `Needs_Action/`, marks it complete, moves it to `Done/`, and updates `Dashboard.md` and `Logs/System_Log.md`.
     c. Records the filename + timestamp in the state ledger to prevent re-processing.
3. **Shutdown** — Handles `SIGINT` / `SIGTERM` gracefully, flushes the state ledger, and logs shutdown.

## State Management

- **Ledger file:** `logs/.watcher_state.json` — JSON object mapping filenames to their first-seen UTC timestamp.
- Guarantees exactly-once processing: a file that has already been recorded is never processed again, even across restarts.

## Logs

| File | Purpose |
|------|---------|
| `logs/actions.log` | Timestamped record of every detected file and processing outcome. |
| `Logs/System_Log.md` | Updated by the processing pipeline (not directly by this script). |

## Configuration

| Parameter | Default | Range / Notes |
|-----------|---------|---------------|
| `--interval` | 15 | 10-30 seconds |
| `--inbox` | `Inbox/` (relative to vault root) | Any valid directory path |

## Dependencies

- Python 3.8+
- Standard library only (no external packages).
- Requires `process_tasks.py` in the vault root for the processing pipeline.

## Files

| Path | Role |
|------|------|
| `.claude/skills/vault-watcher/SKILL.md` | This skill definition. |
| `scripts/watch_inbox.py` | Watcher script entry point. |
