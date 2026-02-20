"""
post_facebook.py — Facebook Page Post Skill
Part of the Gold Tier AI Employee vault.

Posts text content to a Facebook Page using the Meta Graph API.
No pip dependencies — uses stdlib http.client only.
Gracefully reports NOT CONFIGURED when credentials are absent.

Usage:
  python post_facebook.py --text "Your post here"
  python post_facebook.py --status          # Check configuration + instructions
"""

import argparse
import datetime
import http.client
import json
import os
import sys
import urllib.parse

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
VAULT_ROOT  = os.path.abspath(os.path.join(_SCRIPT_DIR, "..", "..", "..", ".."))
ACTIONS_LOG = os.path.join(VAULT_ROOT, "Logs", "actions.log")

GRAPH_HOST    = "graph.facebook.com"
GRAPH_VERSION = "v19.0"
TIMEOUT_S     = 30

_REQUIRED_VARS = ["FACEBOOK_PAGE_ID", "FACEBOOK_ACCESS_TOKEN"]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _now_utc() -> str:
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")


def _load_dotenv() -> None:
    env_path = os.path.join(VAULT_ROOT, ".env")
    if not os.path.isfile(env_path):
        return
    with open(env_path, encoding="utf-8", errors="replace") as fh:
        for line in fh:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, _, v = line.partition("=")
                os.environ.setdefault(k.strip(), v.strip())


def _log_action(message: str) -> None:
    """Append timestamped entry to actions.log (best-effort)."""
    try:
        os.makedirs(os.path.dirname(ACTIONS_LOG), exist_ok=True)
        ts = _now_utc()
        with open(ACTIONS_LOG, "a", encoding="utf-8", errors="replace") as fh:
            fh.write(f"[{ts}] [facebook-post] {message}\n")
    except Exception:
        pass


def _missing_vars() -> list:
    return [v for v in _REQUIRED_VARS if not os.environ.get(v)]


def _graph_post(page_id: str, token: str, message: str) -> tuple:
    """
    POST message to a Facebook Page feed via Meta Graph API.
    Returns (http_status_code, response_dict).
    """
    path = f"/{GRAPH_VERSION}/{page_id}/feed"
    body = urllib.parse.urlencode({
        "message":      message,
        "access_token": token,
    })
    headers = {"Content-Type": "application/x-www-form-urlencoded"}

    conn = http.client.HTTPSConnection(GRAPH_HOST, timeout=TIMEOUT_S)
    try:
        conn.request("POST", path, body=body, headers=headers)
        resp = conn.getresponse()
        raw  = resp.read().decode("utf-8", errors="replace")
        return resp.status, json.loads(raw)
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------

def cmd_status() -> int:
    """Print configuration status and setup instructions."""
    missing = _missing_vars()
    if missing:
        print("STATUS: NOT CONFIGURED")
        print(f"Missing environment variables: {', '.join(missing)}")
        print()
        print("To activate this skill:")
        print("  1. Go to https://developers.facebook.com and create an App")
        print("  2. Add the 'Pages API' product to your App")
        print("  3. Generate a Page Access Token:")
        print("     - Go to Graph API Explorer")
        print("     - Select your App and Page")
        print("     - Add permission: pages_manage_posts")
        print("     - Generate and copy the token")
        print("  4. Find your Page ID:")
        print("     - Go to your Facebook Page -> About -> Page ID")
        print("  5. Add to your .env file:")
        print("       FACEBOOK_PAGE_ID=your_page_id")
        print("       FACEBOOK_ACCESS_TOKEN=your_page_access_token")
        print("  6. No pip installs required (uses stdlib)")
        print()
        print("Once configured, test with:")
        print("  python post_facebook.py --text \"Hello from AI Employee!\"")
        return 0

    print("STATUS: CONFIGURED")
    print("All required environment variables are present.")
    print("No additional dependencies required (stdlib only).")
    return 0


def cmd_post(text: str) -> int:
    """Post a message to the configured Facebook Page."""
    text = text.strip()

    if not text:
        print("ERROR: Post text cannot be empty.", file=sys.stderr)
        return 1

    missing = _missing_vars()
    if missing:
        print(
            "ERROR: Facebook not configured. "
            "Run --status for setup instructions.",
            file=sys.stderr,
        )
        _log_action(f"ERROR - not configured, missing: {', '.join(missing)}")
        return 1

    page_id = os.environ["FACEBOOK_PAGE_ID"].strip()
    token   = os.environ["FACEBOOK_ACCESS_TOKEN"].strip()

    try:
        status, data = _graph_post(page_id, token, text)
    except Exception as exc:
        _log_action(f"ERROR - network/parse failure: {exc}")
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    if status == 200 and "id" in data:
        post_id = data["id"]
        _log_action(
            f"Facebook post published | page={page_id} | post_id={post_id} | "
            f"preview={text[:60].replace(chr(10), ' ')}"
        )
        print("SUCCESS: Facebook post published")
        print(f"  Post ID  : {post_id}")
        print(f"  Page ID  : {page_id}")
        return 0

    # Extract error message from Meta's response
    err_msg = (
        data.get("error", {}).get("message")
        or data.get("error", {}).get("error_user_msg")
        or str(data)
    )
    _log_action(f"ERROR posting to Facebook page {page_id}: {err_msg}")
    print(f"ERROR: {err_msg}", file=sys.stderr)
    return 1


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> int:
    _load_dotenv()

    parser = argparse.ArgumentParser(
        description="Facebook Page Post Skill — post to a Facebook Page via Meta Graph API",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--text",   help="Post content")
    group.add_argument("--status", action="store_true",
                       help="Check configuration status and setup instructions")

    args = parser.parse_args()

    if args.status:
        return cmd_status()
    return cmd_post(args.text)


if __name__ == "__main__":
    sys.exit(main())
