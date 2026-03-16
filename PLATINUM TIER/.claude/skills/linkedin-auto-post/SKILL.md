# linkedin-auto-post

Automatically generate and publish business-focused LinkedIn posts to drive engagement and sales. Reads topic files from `Inbox/` or accepts direct input, builds professional posts with hooks/CTAs/hashtags, and publishes via the `linkedin-post` skill.

## Usage
```bash
# Generate and post about a topic
python .claude/skills/linkedin-auto-post/scripts/auto_post.py \
  --topic "AI automation for small businesses"

# Generate from a file in Inbox
python .claude/skills/linkedin-auto-post/scripts/auto_post.py \
  --file Inbox/product_launch.md

# Preview only (don't post)
python .claude/skills/linkedin-auto-post/scripts/auto_post.py \
  --topic "productivity tips" --preview

# Use a specific post style
python .claude/skills/linkedin-auto-post/scripts/auto_post.py \
  --topic "our new feature" --style story
```

## Environment Variables (required for posting)
- `LINKEDIN_EMAIL` — LinkedIn login email
- `LINKEDIN_PASSWORD` — LinkedIn login password

## Post Styles
- `tip` — Actionable business tip with numbered steps
- `story` — Personal narrative with a business lesson
- `announcement` — Product/service announcement with CTA
- `insight` — Industry insight with data-backed perspective

## Output
Generated post saved to `Logs/linkedin_posts.log`.
Prints `SUCCESS: Post published` or `PREVIEW: <post content>`.

## Notes
- Posts are capped at 1300 characters (LinkedIn optimal length).
- Includes trending hashtags relevant to topic.
- Requires `playwright` for actual posting.
