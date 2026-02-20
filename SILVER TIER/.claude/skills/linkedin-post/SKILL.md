# linkedin-post

Create real LinkedIn text posts using Playwright browser automation.

## Usage
```bash
python .claude/skills/linkedin-post/scripts/post_linkedin.py \
  --text "Excited to share our latest update! #AI #Automation"
```

## Environment Variables (required)
- `LINKEDIN_EMAIL` — LinkedIn login email
- `LINKEDIN_PASSWORD` — LinkedIn login password

## Inputs
| Flag | Required | Description |
|------|----------|-------------|
| `--text` | Yes | Post content (text, hashtags, mentions) |
| `--headless` | No | Run browser in headless mode (default: true) |

## Output
Prints `SUCCESS: LinkedIn post published` or `ERROR: <reason>`.

## Exit Codes
- `0` — posted successfully
- `1` — error (login failed, post failed, timeout)

## Dependencies
- `playwright` (`pip install playwright && playwright install chromium`)

## Notes
- Uses Chromium via Playwright for real browser interaction.
- Handles LinkedIn's dynamic DOM for login and post creation.
- 30-second timeouts on all navigation actions.
