# ralph-wiggum-loop

Autonomous step-by-step task executor for the Silver Tier AI Employee vault.

When a task appears in `Needs_Action/`, Ralph reads its `## Steps` checkboxes,
executes each step in sequence, and moves the completed task to `Done/` —
all without human intervention, unless a risky step is detected.

## Execution Flow

```
Needs_Action/task.md
       |
       | (scheduler calls ralph_loop.py --run)
       v
[PARSE] read ## Steps checkboxes
       |
       v
[PLAN ] create Plans/<task>_Plan.md (execution log)
       |
       v
for each unchecked step (max MAX_ITER per cycle):
  |
  +--[RISK CHECK]--> risky? --> [SUBMIT] Needs_Approval/<approval>.md
  |                                       (non-blocking; resumes next cycle)
  |
  +--[ROUTE]  review/read  --> _handle_review()   -> acknowledge
  |           log/record   --> _handle_log()      -> write to actions.log
  |           archive/done --> _handle_archive()  -> acknowledge
  |           default      --> _handle_default()  -> acknowledge
  |
  +--[MARK] - [ ] -> - [x]  in task file
       |
       v
all steps done?
  YES -> update front-matter (status: completed)
      -> move to Done/
      -> update Dashboard.md + System_Log.md
      -> Plans/<task>_Plan.md closed with COMPLETED outcome
  NO  -> save progress; continue next cycle
```

## Usage

```bash
# Scheduler mode: process all eligible tasks
python .claude/skills/ralph-wiggum-loop/scripts/ralph_loop.py --run

# Process a single task file
python .claude/skills/ralph-wiggum-loop/scripts/ralph_loop.py --task Needs_Action/task_foo.md
python .claude/skills/ralph-wiggum-loop/scripts/ralph_loop.py --task task_foo.md

# Status dashboard
python .claude/skills/ralph-wiggum-loop/scripts/ralph_loop.py --status

# Clear state for one task (allows re-processing)
python .claude/skills/ralph-wiggum-loop/scripts/ralph_loop.py --reset task_foo.md
```

## Modes

| Flag | Description |
|------|-------------|
| `--run` | Process all eligible tasks in `Needs_Action/` — called by scheduler every cycle |
| `--task FILE` | Process a single specific task file (full path or bare filename) |
| `--status` | Show task counts, active tasks, approval waits, iteration counts |
| `--reset TASKNAME` | Clear loop state for a task so it can be re-processed from scratch |

## Safety Controls

| Control | Value | Description |
|---------|-------|-------------|
| `MAX_ITER` | `5` | Max step-executions per task per scheduler cycle |
| `MAX_TASKS` | `10` | Max tasks processed per scheduler cycle |
| Risk gate | see below | Risky steps pause for human approval before executing |

### Risk Patterns

The following keywords in a step trigger the human approval gate:

| Category | Keywords |
|----------|----------|
| Destructive | `delete`, `remove`, `drop`, `destroy`, `wipe`, `truncate` |
| Communications | `send email`, `email to`, `notify`, `message` |
| Publishing | `post`, `publish`, `deploy`, `release`, `push` |
| Overwrite | `overwrite`, `reset`, `clear` |
| Social/External | `linkedin`, `twitter`, `social media`, `production`, `live server`, `external` |
| Financial | `payment`, `charge`, `billing`, `invoice send` |

## Non-Blocking Approval Gate

When a risky step is detected, Ralph:

1. Writes an approval request to `Needs_Approval/ralph_approval_<task>_step<N>_<ts>.md`
2. Records the filename in `Logs/.ralph_state.json`
3. Returns `awaiting_approval` — the scheduler continues to the next task
4. On the **next scheduler cycle**, the scheduler's `check_approvals` step resolves the file
5. Ralph then resumes: APPROVED → executes the step; REJECTED → skips it

## Step Routing

| Pattern | Handler | Action |
|---------|---------|--------|
| `read / review / open / examine / analyze / check / verify / confirm / inspect` | `_handle_review` | Acknowledged — step marked done |
| `log / record / note / document / track / write` | `_handle_log` | Entry written to `Logs/actions.log` |
| `archive / complete / finish / close / done / mark complete / move to done` | `_handle_archive` | Acknowledged — task archived at completion |
| *(anything else)* | `_handle_default` | Acknowledged by autonomous agent |

## Return Values (`process_task`)

| Value | Meaning |
|-------|---------|
| `completed` | All steps done; file moved to `Done/` |
| `in_progress` | Some steps remain; will continue next cycle |
| `max_iter` | Hit `MAX_ITER` this cycle; will continue next cycle |
| `awaiting_approval` | Risky step submitted; waiting for human decision |
| `skipped` | File has `type: plan` or is already completed — not a real task |
| `error` | Task file not found or unrecoverable failure |

## File Annotations

When a task is completed, these fields are added to its YAML front-matter:

```yaml
status: completed
completed_at: 2026-02-20 12:34:56 UTC
completed_by: ralph-wiggum-loop
ralph_iterations: 3
```

## Output Files

| File | Description |
|------|-------------|
| `Plans/<task>_Plan.md` | Execution log — created on first visit, appended each cycle |
| `Done/<task>.md` | Completed task file (with updated front-matter) |
| `Logs/actions.log` | Audit trail for all step executions |
| `Logs/.ralph_state.json` | State: per-task status, current step, iteration count, approval tracking |

### .ralph_state.json format

```json
{
  "task_foo.md": {
    "status": "in_progress",
    "current_step": 2,
    "iterations": 2,
    "started_at": "2026-02-20T12:00:00+00:00",
    "last_run": "2026-02-20T12:05:00+00:00"
  },
  "task_bar.md": {
    "status": "awaiting_approval",
    "approval_file": "ralph_approval_task_bar_md_step3_20260220_120600.md",
    "awaiting_step": 2,
    "current_step": 2,
    "iterations": 3
  }
}
```

### Plans/<task>_Plan.md format

```markdown
---
type: ralph_plan
task_source: task_foo.md
status: in_progress
created_at: 2026-02-20 12:00:00 UTC
---

# Autonomous Execution Plan: task_foo.md

> Ralph Wiggum Loop | Started: 2026-02-20 12:00:00 UTC

## Task Summary
- **File:** `task_foo.md`
- **Type:** file_review
- **Priority:** medium
- **Steps total:** 3

## Execution Log

- `2026-02-20 12:00:01 UTC` --- Cycle started | steps_total=3 | steps_done=0 ---
- `2026-02-20 12:00:01 UTC` Step 1/3: REVIEWED: acknowledged by autonomous agent
- `2026-02-20 12:00:02 UTC` Step 2/3: EXECUTED: step processed by autonomous agent
- `2026-02-20 12:00:03 UTC` Step 3/3: ACKNOWLEDGED: completion step noted

## Outcome

**COMPLETED** — 2026-02-20 12:00:03 UTC
```

## Scheduler Integration

Ralph is wired into the Silver Scheduler as **Step 3** of every cycle:

```
Scheduler cycle (run_ai_employee.py):
  Step 1  Inbox scan
  Step 2  Task planner
  Step 3  Ralph loop         <- this skill  (every cycle)
  Step 4  Process tasks
  Step 5  Check approvals
  Step 6  Error recovery
  Step 7  CEO Briefing       (weekly)
  Step 8  Log rotation
```

The scheduler calls `ralph_loop.py --run`, which processes all eligible tasks.
If the skill file is missing, the scheduler silently continues — zero impact on existing behaviour.

## Skipped Files

Ralph skips the following task types automatically:

- Files with `type: plan` in front-matter (task_planner artifacts — not real tasks)
- Files whose state entry has `status: completed`
- Files without a `## Steps` section (marked complete immediately with no iterations)

## Configuration

Edit the constants at the top of `ralph_loop.py`:

| Constant | Default | Description |
|----------|---------|-------------|
| `MAX_ITER` | `5` | Max step-executions per task per scheduler cycle |
| `MAX_TASKS` | `10` | Max tasks processed per scheduler cycle |

## Notes

- Pure stdlib — no pip installs required.
- State file written atomically (`os.replace`) to prevent corruption on crash.
- All stdout output is ASCII-safe for Windows cp1252 terminals.
- Plans are distinct from task_planner output: `Plans/<task>_Plan.md` vs `Needs_Action/Plan_<task>.md`.
- Dashboard.md and System_Log.md are updated via simple string replacement on the table headers.
