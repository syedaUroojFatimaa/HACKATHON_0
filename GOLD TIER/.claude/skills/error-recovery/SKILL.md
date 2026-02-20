# error-recovery

Automatic error detection, quarantine, and retry system for failed vault tasks.

Monitors `Needs_Action/` every scheduler cycle. Any task file that remains
unprocessed for longer than the stuck threshold is automatically quarantined,
logged, and retried — up to three times — before being marked exhausted.

## Failure Lifecycle

```
Needs_Action/task.md
       |
       | (stuck >= 15 min)
       v
[QUARANTINE] ──► Errors/task.md        (front-matter annotated)
                 Logs/errors.log       (structured entry)
                 Logs/actions.log      (audit trail)
                 Logs/.error_recovery_state.json
       |
       | (5 min later — retry)
       v
Needs_Action/task.md   (status reset to pending, attempt counter incremented)
       |
       | (if stuck again — attempt 2, then 3)
       v
[EXHAUSTED] ──► Errors/task.md         (status: error_exhausted)
                Manual review required
```

## Usage

```bash
# Scheduler mode: scan + retry in one call
python .claude/skills/error-recovery/scripts/error_recovery.py --run

# Scan Needs_Action/ only (no retries)
python .claude/skills/error-recovery/scripts/error_recovery.py --scan

# Process pending retries from Errors/ only
python .claude/skills/error-recovery/scripts/error_recovery.py --retry

# Manually quarantine a specific file
python .claude/skills/error-recovery/scripts/error_recovery.py \
  --log-error --file task_foo.md --reason "planner crashed"

# Status dashboard
python .claude/skills/error-recovery/scripts/error_recovery.py --status

# Full report with recent errors.log entries
python .claude/skills/error-recovery/scripts/error_recovery.py --report
```

## Modes

| Flag | Description |
|------|-------------|
| `--run` | Scan + retry combined — called automatically by scheduler every cycle |
| `--scan` | Scan `Needs_Action/` and quarantine any files stuck >= threshold |
| `--retry` | Check `Errors/` and move eligible files back to `Needs_Action/` |
| `--log-error` | Manually quarantine a file with a reason (for use by other skills) |
| `--status` | Show quarantine counts, next retry times, exhausted files |
| `--report` | Full report: status + last 20 `errors.log` entries |

## `--log-error` flags

| Flag | Required | Description |
|------|----------|-------------|
| `--file` | Yes | Filename to quarantine |
| `--reason` | Yes | Human-readable failure reason |
| `--src` | No | Source folder (default: `Needs_Action`) |

## Configuration

Edit the constants at the top of `error_recovery.py`:

| Constant | Default | Description |
|----------|---------|-------------|
| `STUCK_THRESHOLD_MINUTES` | `15` | Minutes in `Needs_Action/` before a file is "stuck" |
| `RETRY_DELAY_SECONDS` | `300` | Seconds (5 min) to wait before retrying |
| `MAX_RETRIES` | `3` | Maximum retry attempts before exhaustion |

## File Annotations

When a file is quarantined, these fields are injected into its YAML front-matter:

```yaml
status: error
error_reason: stuck (17 min in Needs_Action)
error_quarantined_at: 2026-02-19 18:30:00 UTC
error_attempt: 1
error_retry_at: 2026-02-19 18:35:00 UTC
```

When retried:
```yaml
status: pending
error_attempt: 2
error_last_retry: 2026-02-19 18:35:10 UTC
error_retry_at: 2026-02-19 18:40:10 UTC
```

When exhausted:
```yaml
status: error_exhausted
error_exhausted_at: 2026-02-19 18:50:00 UTC
error_note: max retries reached - manual review required
```

## Output Files

| File | Description |
|------|-------------|
| `Errors/*.md` | Quarantined task files (annotated front-matter) |
| `Logs/errors.log` | Structured log: QUARANTINE / RETRY / EXHAUSTED / WARN entries |
| `Logs/actions.log` | Audit trail (same format as other vault skills) |
| `Logs/.error_recovery_state.json` | State: quarantined + exhausted dicts with metadata |

### errors.log format

```
[YYYY-MM-DD HH:MM:SS UTC] [QUARANTINE  ] file=task_foo.md | reason=stuck (17 min) | attempt=1/3 | retry_at=...
[YYYY-MM-DD HH:MM:SS UTC] [RETRY       ] file=task_foo.md | attempt=2/3 | moved_to=Needs_Action/task_foo.md
[YYYY-MM-DD HH:MM:SS UTC] [EXHAUSTED   ] file=task_foo.md | attempts=3/3 | file remains in Errors/
```

## Scheduler Integration

`error-recovery` is wired into the Silver Scheduler as **Step 5** of every cycle:

```
Scheduler cycle (run_ai_employee.py):
  Step 1  Inbox scan
  Step 2  Task planner
  Step 3  Process tasks
  Step 4  Check approvals
  Step 5  Error recovery       ← this skill  (every cycle)
  Step 6  CEO Briefing         (weekly)
  Step 7  Log rotation
```

The scheduler calls `error_recovery.py --run`, which performs scan + retry in one pass.
If the skill file is missing, the scheduler silently continues — zero impact on existing behaviour.

## Resolving Exhausted Files

Files in `Errors/` marked `error_exhausted` require manual attention:

1. Open the file in `Errors/` and read the `error_reason` field.
2. Fix the underlying cause (e.g., malformed front-matter, missing dependency).
3. Move the file back to `Needs_Action/` manually.
4. Delete its entry from `Logs/.error_recovery_state.json` → `"exhausted"` dict to clear the record.

## Notes

- Pure stdlib — no pip installs required.
- State file is written atomically (`os.replace`) to prevent corruption on crash.
- All file moves preserve content; `shutil.move` is used for cross-device safety.
- Filename collisions in `Errors/` are handled by appending a timestamp suffix.
- All stdout output is ASCII-safe for Windows cp1252 terminals.
