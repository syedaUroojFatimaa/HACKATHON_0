# facebook-post

Post text content to a Facebook Page using the Meta Graph API.
This skill is **ready to activate** — add credentials to `.env` to enable posting.
No pip dependencies — uses Python standard library only.

---

## Usage

```bash
# Post to your Facebook Page
python .claude/skills/facebook-post/scripts/post_facebook.py \
  --text "Your Facebook post content here"

# Check configuration status and setup instructions
python .claude/skills/facebook-post/scripts/post_facebook.py --status
```

---

## Inputs

| Flag | Required | Description |
|------|----------|-------------|
| `--text TEXT` | Yes (or --status) | Post content |
| `--status` | Yes (or --text) | Check configuration and print setup instructions |

---

## Output

### When posting succeeds:
```
SUCCESS: Facebook post published
  Post ID  : 123456789012345_987654321098765
  Page ID  : 123456789012345
```

### When not configured:
```
STATUS: NOT CONFIGURED
Missing environment variables: FACEBOOK_PAGE_ID, FACEBOOK_ACCESS_TOKEN

To activate this skill:
  1. Go to https://developers.facebook.com and create an App
  ...
```

---

## Environment Variables (required to activate)

Add these to your `.env` file:

```
FACEBOOK_PAGE_ID=your_facebook_page_id
FACEBOOK_ACCESS_TOKEN=your_page_access_token
```

### How to get these credentials:
1. Go to https://developers.facebook.com and create an App
2. Add the **Pages API** product to your App
3. Open **Graph API Explorer** (Tools menu)
4. Select your App, then select your Page in the "User or Page" dropdown
5. Add permission: **`pages_manage_posts`**
6. Click **"Generate Access Token"** and copy it
7. Find your Page ID: go to your Facebook Page -> About -> scroll to "Page ID"
8. Add both values to `.env`

**Note:** Page Access Tokens expire. For long-lived tokens:
- Use the Token Debugger at https://developers.facebook.com/tools/debug/accesstoken/
- Exchange for a long-lived token (valid ~60 days) via the API

---

## Dependencies

None — uses only Python standard library (`http.client`, `urllib`, `json`).

---

## Integration with social-summary

After a successful post, log it for tracking:

```bash
# Post to Facebook
python .claude/skills/facebook-post/scripts/post_facebook.py \
  --text "Your post content"

# If exit code 0, log it
python .claude/skills/social-summary/scripts/social_summary.py \
  --log --platform Facebook --content "Your post content"
```

---

## Exit Codes

| Code | Meaning |
|------|---------|
| `0` | Success (post published OR status displayed) |
| `1` | Error (not configured, network failure, API error) |

---

## Logs

Every post attempt (success or failure) is appended to `Logs/actions.log`:

```
[2026-02-20 12:00:00 UTC] [facebook-post] Facebook post published | page=... | post_id=...
```

---

## Extending to Instagram

Instagram Business posting uses the same Meta Graph API credentials. To post to Instagram:

1. Connect your Instagram Business account to your Facebook Page
2. Add permission: `instagram_basic`, `instagram_content_publish`
3. Use endpoint: `POST /{ig-user-id}/media` then `/{ig-user-id}/media_publish`

This can be added to `post_facebook.py` as an `--instagram` flag or as a separate `instagram-post` skill.

---

## Notes

- Skill exits 0 with "STATUS: NOT CONFIGURED" when credentials are absent — will NOT crash the scheduler
- Meta Graph API version used: v19.0 (update `GRAPH_VERSION` constant to upgrade)
- No pip dependencies (stdlib `http.client` handles HTTPS)
