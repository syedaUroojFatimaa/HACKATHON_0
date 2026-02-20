# human-approval

Human-in-the-loop gate for sensitive AI actions. Creates an approval request in `Needs_Approval/`, blocks until a human writes `APPROVED` or `REJECTED`, then returns the result.

## Usage
```bash
# Submit a file for approval (blocks until decision or timeout)
python .claude/skills/human-approval/scripts/request_approval.py \
  --submit Needs_Action/Plan.md --timeout 3600

# Wait on an existing approval file
python .claude/skills/human-approval/scripts/request_approval.py \
  --file Needs_Approval/approval_Plan.md

# Watch entire folder continuously
python .claude/skills/human-approval/scripts/request_approval.py --watch
```

## Inputs
| Flag | Required | Description |
|------|----------|-------------|
| `--submit` | Yes* | Source file to submit for approval |
| `--file` | Yes* | Existing approval file to monitor |
| `--watch` | No | Monitor all files in Needs_Approval/ |
| `--timeout` | No | Seconds before auto-timeout (default: 3600) |
| `--poll` | No | Seconds between checks (default: 5) |

## Output
File renamed to `.approved`, `.rejected`, or `.timeout`.
All actions logged to `logs/actions.log`.

## Exit Codes
- `0` — APPROVED | `1` — REJECTED | `2` — TIMEOUT | `3` — ERROR

## Notes
- Human edits the `## Decision` section in the file.
- HTML comments are stripped before scanning to prevent false matches.
- Standard library only.
