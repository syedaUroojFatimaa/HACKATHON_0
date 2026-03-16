# gmail-send

Send real emails via Gmail SMTP.

## Usage
```bash
python .claude/skills/gmail-send/scripts/send_email.py \
  --to "recipient@example.com" \
  --subject "Subject line" \
  --body "Email body text"
```

## Environment Variables (required)
- `EMAIL_ADDRESS` — Gmail address (sender)
- `EMAIL_PASSWORD` — Gmail App Password (not account password)

## Inputs
| Flag | Required | Description |
|------|----------|-------------|
| `--to` | Yes | Recipient email address |
| `--subject` | Yes | Email subject line |
| `--body` | Yes | Plain-text email body |
| `--cc` | No | CC recipient |

## Output
Prints `SUCCESS: Email sent to <address>` or `ERROR: <reason>`.

## Exit Codes
- `0` — sent successfully
- `1` — error (missing env vars, SMTP failure, invalid address)

## Notes
- Uses TLS on port 587 (Gmail SMTP standard).
- Generate an App Password at https://myaccount.google.com/apppasswords
- Standard library only (`smtplib`, `email`).
