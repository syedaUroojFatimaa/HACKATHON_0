# social-summary

Maintain a persistent log of every social media post published by the AI Employee.
All entries are stored in `Reports/Social_Log.md` with full content and metadata.

---

## Usage

```bash
python .claude/skills/social-summary/scripts/social_summary.py [MODE] [OPTIONS]
```

---

## Modes

### `--log` — Record a new post

Called by other skills immediately after a successful publish.

```bash
python .claude/skills/social-summary/scripts/social_summary.py \
  --log \
  --platform LinkedIn \
  --content "Excited to share our Q1 results! #AI #Automation"
```

| Flag | Required | Description |
|------|----------|-------------|
| `--platform PLATFORM` | Yes | Platform name (e.g. `LinkedIn`, `Twitter`) |
| `--content CONTENT` | Yes | Full post text |
| `--date DATE` | No | Override timestamp (`YYYY-MM-DD HH:MM:SS UTC`). Defaults to current UTC time. |

Output example:
```
SUCCESS: Post logged to Reports/Social_Log.md
  Platform : LinkedIn
  Date     : 2026-02-20 12:00:00 UTC
  Preview  : Excited to share our Q1 results! #AI #Automation
```

---

### `--list` — Print recent posts as a table

```bash
# All platforms, last 20
python .claude/skills/social-summary/scripts/social_summary.py --list

# Filter by platform, limit to 5
python .claude/skills/social-summary/scripts/social_summary.py --list --platform LinkedIn --limit 5
```

| Flag | Required | Description |
|------|----------|-------------|
| `--platform PLATFORM` | No | Filter to a specific platform |
| `--limit N` | No | Maximum rows to show (default 20) |

---

### `--report` — Full markdown report

Prints platform summary table, post history table, and full content blocks to stdout.

```bash
python .claude/skills/social-summary/scripts/social_summary.py --report
```

---

### `--stats` — Platform breakdown counts only

```bash
python .claude/skills/social-summary/scripts/social_summary.py --stats
```

Output example:
```
Platform Post Counts
------------------------------
  LinkedIn               12
  Twitter                 3
------------------------------
  TOTAL                  15
```

---

## Social_Log.md Format

The log file lives at `Reports/Social_Log.md` and is rewritten atomically on every `--log` call.

```markdown
---
type: social_log
created_at: 2026-02-20 12:00:00 UTC
last_updated: 2026-02-20 14:30:00 UTC
total_posts: 2
---

# Social Media Post Log

> Last updated: 2026-02-20 14:30:00 UTC | AI Employee System

## Platform Summary

| Platform | Posts | Last Posted |
|----------|-------|-------------|
| LinkedIn | 2     | 2026-02-20  |

## Post History

| Date                 | Platform | Content Preview                          |
|----------------------|----------|------------------------------------------|
| 2026-02-20 12:00 UTC | LinkedIn | Excited to share our Q1 results! #AI ... |
| 2026-02-20 14:30 UTC | LinkedIn | New blog post is live! Check it out...   |

---

### 2026-02-20 12:00:00 UTC -- LinkedIn

Excited to share our Q1 results! #AI #Automation

---

### 2026-02-20 14:30:00 UTC -- LinkedIn

New blog post is live! Check it out: https://example.com #Tech

---
```

---

## Integration with Other Skills

The skill is **standalone and decoupled**. After a successful publish, call `--log`:

### linkedin-post

```bash
# Post to LinkedIn
python .claude/skills/linkedin-post/scripts/post_linkedin.py \
  --text "Our latest update is live!"

# If exit code is 0, record it
python .claude/skills/social-summary/scripts/social_summary.py \
  --log --platform LinkedIn --content "Our latest update is live!"
```

### linkedin-auto-post

```bash
# After auto_post.py succeeds, log the generated content
python .claude/skills/social-summary/scripts/social_summary.py \
  --log --platform LinkedIn --content "$GENERATED_CONTENT"
```

Any future platform skill follows the same pattern — call `--log` with the platform name and content after a confirmed publish.

---

## Files Written

| File | Purpose |
|------|---------|
| `Reports/Social_Log.md` | Persistent structured post log |
| `Logs/actions.log` | Action audit trail (`[social-summary]` entries) |

---

## Exit Codes

| Code | Meaning |
|------|---------|
| `0` | Success |
| `1` | Error (missing required argument, file write failure) |

---

## Notes

- `Reports/` directory is created automatically if it does not exist.
- File writes are atomic: data is written to a `.tmp` file and then renamed, preventing corruption on interruption.
- All output is UTF-8 safe with ASCII-only formatting characters for Windows compatibility.
