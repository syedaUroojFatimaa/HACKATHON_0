# vault-file-manager

Move task files between vault workflow folders: `Inbox/`, `Needs_Action/`, `Done/`.

## Usage
```bash
# Move a file between folders
python .claude/skills/vault-file-manager/scripts/move_task.py \
  --file "task_report.md" --from Inbox --to Needs_Action

# List files in a folder
python .claude/skills/vault-file-manager/scripts/move_task.py --list Inbox

# Archive all completed tasks from Needs_Action to Done
python .claude/skills/vault-file-manager/scripts/move_task.py --archive
```

## Inputs
| Flag | Required | Description |
|------|----------|-------------|
| `--file` | Yes* | Filename to move |
| `--from` | Yes* | Source folder (`Inbox`, `Needs_Action`, `Done`) |
| `--to` | Yes* | Destination folder |
| `--list` | No | List files in a folder |
| `--archive` | No | Move all Needs_Action files to Done |

## Output
Prints `MOVED: <file> from <src> to <dst>` or `ERROR: <reason>`.
All actions logged to `logs/actions.log`.

## Exit Codes
- `0` — success
- `1` — error (file not found, invalid folder)

## Notes
- Never overwrites — appends timestamp suffix on collision.
- Auto-creates missing folders.
- Standard library only.
