# twitter-post

Post text content to Twitter/X using Twitter API v2.
This skill is **ready to activate** — add credentials to `.env` to enable posting.

---

## Usage

```bash
# Post a tweet
python .claude/skills/twitter-post/scripts/post_twitter.py \
  --text "Your tweet content here (max 280 chars)"

# Check configuration status and setup instructions
python .claude/skills/twitter-post/scripts/post_twitter.py --status
```

---

## Inputs

| Flag | Required | Description |
|------|----------|-------------|
| `--text TEXT` | Yes (or --status) | Tweet content (max 280 characters) |
| `--status` | Yes (or --text) | Check configuration and print setup instructions |

---

## Output

### When posting succeeds:
```
SUCCESS: Tweet posted
  Tweet ID : 1234567890123456789
  URL      : https://twitter.com/i/web/status/1234567890123456789
  Length   : 42 / 280 chars
```

### When not configured:
```
STATUS: NOT CONFIGURED
Missing environment variables: TWITTER_API_KEY, TWITTER_API_SECRET, ...

To activate this skill:
  1. Go to https://developer.twitter.com/en/portal/projects-and-apps
  ...
```

---

## Environment Variables (required to activate)

Add these to your `.env` file:

```
TWITTER_API_KEY=your_api_key
TWITTER_API_SECRET=your_api_secret
TWITTER_ACCESS_TOKEN=your_access_token
TWITTER_ACCESS_SECRET=your_access_token_secret
```

### How to get these credentials:
1. Go to https://developer.twitter.com/en/portal/projects-and-apps
2. Create a new App (or use an existing one)
3. Set app permissions to **"Read and Write"**
4. Under **"Keys and Tokens"**, generate:
   - API Key and Secret
   - Access Token and Secret (for your account)
5. Add all four values to `.env`

---

## Dependencies

```bash
pip install tweepy
```

Verify installation:
```bash
python -c "import tweepy; print('tweepy', tweepy.__version__)"
```

---

## Integration with social-summary

After a successful post, log it for tracking:

```bash
# Post the tweet
python .claude/skills/twitter-post/scripts/post_twitter.py \
  --text "Your tweet"

# If exit code 0, log it
python .claude/skills/social-summary/scripts/social_summary.py \
  --log --platform Twitter --content "Your tweet"
```

---

## Exit Codes

| Code | Meaning |
|------|---------|
| `0` | Success (tweet posted OR status displayed) |
| `1` | Error (not configured, tweepy missing, API error, tweet too long) |

---

## Logs

Every post attempt (success or failure) is appended to `Logs/actions.log`:

```
[2026-02-20 12:00:00 UTC] [twitter-post] Tweet posted | id=... | chars=42 | preview=...
```

---

## Notes

- Tweet limit is 280 characters (enforced before API call)
- Skill exits 0 with "STATUS: NOT CONFIGURED" message when credentials are absent — it will NOT crash the scheduler
- Twitter API v2 is used (not v1.1); requires a Developer account at https://developer.twitter.com
