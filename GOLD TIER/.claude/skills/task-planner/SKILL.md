# Task Planner Skill

## Name
task-planner

## Description
Reads new `.md` files from the `Inbox/` folder, analyzes their content, and generates a structured step-by-step execution plan placed in `Needs_Action/`. After plan creation, it triggers the vault-file-manager (`process_tasks.py`) to mark the plan complete and move it to `Done/`. All actions are logged to `logs/actions.log`. A persistent state ledger guarantees idempotent, exactly-once processing.

## Trigger
- **Manual:** `python scripts/task_planner.py`
- **Single file:** `python scripts/task_planner.py --file Inbox/my_note.md`
- **Called by vault-watcher:** The watcher can invoke this script instead of (or in addition to) the default processing pipeline.
- **Scheduler (cron / Task Scheduler):** Safe to call on a schedule — the state ledger prevents duplicate work.

## Usage

```bash
# Process all unprocessed .md files in Inbox (default)
python scripts/task_planner.py

# Process a single specific file
python scripts/task_planner.py --file Inbox/meeting_notes.md

# Custom inbox path
python scripts/task_planner.py --inbox path/to/Inbox

# Skip the vault-file-manager step (plan only, no move to Done)
python scripts/task_planner.py --plan-only
```

## Behavior

### 1. Scan
Discover all `.md` files in `Inbox/`. Skip any file already recorded in the state ledger (`logs/.planner_state.json`).

### 2. Analyze
For each new file, read its full Markdown content and extract:

| Signal | How detected |
|--------|-------------|
| **Document type** | Keyword patterns (meeting, report, request, todo, notes, proposal, review) |
| **Priority** | Keywords like *urgent*, *ASAP*, *critical*, *important*, *high priority* |
| **Action items** | Lines containing TODO, ACTION, TASK, or unchecked checkboxes `- [ ]` |
| **Questions** | Lines ending with `?` |
| **Headings** | All `#`-level headings for structural overview |
| **References** | File paths, URLs, `@mentions` |
| **Word count** | Total words for effort estimation |

### 3. Plan
Generate a `Plan_<safe_filename>.md` with:
- YAML front-matter (`type: plan`, `status: pending`, `priority`, `created_at`, `source_file`, `related_files`)
- **Content Summary** — type, word count, section overview
- **Extracted Action Items** — verbatim from source
- **Identified Questions** — verbatim from source
- **Step-by-Step Execution Plan** — actionable checklist steps derived from the analysis
- **Priority & Risk Assessment** — assigned priority with reasoning
- **References** — extracted links, files, mentions

The plan file is written to `Needs_Action/`.

### 4. Archive (vault-file-manager integration)
Unless `--plan-only` is passed, invoke `process_tasks.py` which:
1. Marks the plan's status as `completed` and checks off all steps.
2. Moves the plan from `Needs_Action/` to `Done/`.
3. Updates `Dashboard.md` and `Logs/System_Log.md`.

### 5. Record
Write the filename + timestamp to the state ledger so the same file is never processed again.

## State Management

| File | Purpose |
|------|---------|
| `logs/.planner_state.json` | `{filename: {planned_at, plan_file}}` — exactly-once ledger |

The state ledger is separate from the vault-watcher's ledger so both skills can operate independently or together without interference.

## Logs

| File | Written by |
|------|-----------|
| `logs/actions.log` | This script — every detection, analysis, plan creation, and archive step |
| `Logs/System_Log.md` | `process_tasks.py` — updated when the plan moves to Done |

## Configuration

| Parameter | Default | Notes |
|-----------|---------|-------|
| `--inbox` | `Inbox/` (relative to vault root) | Directory to scan for `.md` files |
| `--file` | *(none)* | Process a single file instead of scanning the inbox |
| `--plan-only` | `false` | Generate the plan but skip the vault-file-manager archive step |

## Dependencies

- Python 3.8+
- Standard library only (no external packages).
- Requires `process_tasks.py` in the vault root for the archive step.

## Files

| Path | Role |
|------|------|
| `.claude/skills/task-planner/SKILL.md` | This skill definition |
| `scripts/task_planner.py` | Planner script entry point |
