# gmail-watcher

Monitor a Gmail inbox via IMAP for new unread emails and create task files in `Inbox/` for each one.

## Usage
```bash
# Watch continuously (default: poll every 60 seconds)
python .claude/skills/gmail-watcher/scripts/watch_gmail.py --daemon

# Single check then exit
python .claude/skills/gmail-watcher/scripts/watch_gmail.py --once

# Custom poll interval
python .claude/skills/gmail-watcher/scripts/watch_gmail.py --daemon --interval 120
```

## Environment Variables (required)
- `EMAIL_ADDRESS` — Gmail address
- `EMAIL_PASSWORD` — Gmail App Password

## Output
Creates `.md` files in `Inbox/` with email subject, sender, date, and body.
All actions logged to `Logs/actions.log`.

## Exit Codes
- `0` — success
- `1` — error (auth failure, connection issue)

## Notes
- Uses IMAP4_SSL on port 993 (Gmail standard).
- Only fetches UNSEEN emails to avoid duplicates.
- Marks fetched emails as SEEN on Gmail so they aren't re-fetched.
- State tracked in `Logs/.gmail_watcher_state.json`.
- Standard library only (`imaplib`, `email`).
