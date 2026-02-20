"""
post_twitter.py — Twitter/X Post Skill
Part of the Gold Tier AI Employee vault.

Posts text content to Twitter/X using Twitter API v2 via tweepy.
Gracefully reports NOT CONFIGURED when credentials are absent.

Usage:
  python post_twitter.py --text "Your tweet here"
  python post_twitter.py --status          # Check configuration + instructions
"""

import argparse
import datetime
import os
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
VAULT_ROOT  = os.path.abspath(os.path.join(_SCRIPT_DIR, "..", "..", "..", ".."))
ACTIONS_LOG = os.path.join(VAULT_ROOT, "Logs", "actions.log")

# Twitter API v2 limits
TWEET_MAX_CHARS = 280

# Required env vars
_REQUIRED_VARS = [
    "TWITTER_API_KEY",
    "TWITTER_API_SECRET",
    "TWITTER_ACCESS_TOKEN",
    "TWITTER_ACCESS_SECRET",
]


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
            fh.write(f"[{ts}] [twitter-post] {message}\n")
    except Exception:
        pass


def _missing_vars() -> list:
    return [v for v in _REQUIRED_VARS if not os.environ.get(v)]


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
        print("  1. Go to https://developer.twitter.com/en/portal/projects-and-apps")
        print("  2. Create a new App — set permissions to 'Read and Write'")
        print("  3. Generate API Key, API Secret, Access Token, Access Secret")
        print("  4. Add to your .env file:")
        for var in _REQUIRED_VARS:
            print(f"       {var}=your_value_here")
        print("  5. Install tweepy:  pip install tweepy")
        print()
        print("Once configured, test with:")
        print("  python post_twitter.py --text \"Hello from AI Employee!\"")
        return 0

    print("STATUS: CONFIGURED")
    print("All required environment variables are present.")
    print()
    try:
        import tweepy  # noqa: F401
        print("tweepy : installed")
    except ImportError:
        print("tweepy : NOT installed  ->  run: pip install tweepy")
    return 0


def cmd_post(text: str) -> int:
    """Post a tweet to Twitter/X."""
    text = text.strip()

    if not text:
        print("ERROR: Tweet text cannot be empty.", file=sys.stderr)
        return 1

    if len(text) > TWEET_MAX_CHARS:
        print(
            f"ERROR: Tweet is {len(text)} characters — "
            f"Twitter limit is {TWEET_MAX_CHARS}.",
            file=sys.stderr,
        )
        return 1

    missing = _missing_vars()
    if missing:
        print(
            "ERROR: Twitter not configured. "
            "Run --status for setup instructions.",
            file=sys.stderr,
        )
        _log_action(f"ERROR - not configured, missing: {', '.join(missing)}")
        return 1

    try:
        import tweepy
    except ImportError:
        print("ERROR: tweepy not installed. Run: pip install tweepy", file=sys.stderr)
        _log_action("ERROR - tweepy not installed")
        return 1

    try:
        client = tweepy.Client(
            consumer_key=os.environ["TWITTER_API_KEY"],
            consumer_secret=os.environ["TWITTER_API_SECRET"],
            access_token=os.environ["TWITTER_ACCESS_TOKEN"],
            access_token_secret=os.environ["TWITTER_ACCESS_SECRET"],
        )
        response = client.create_tweet(text=text)
        tweet_id = response.data["id"]

        _log_action(
            f"Tweet posted | id={tweet_id} | chars={len(text)} | "
            f"preview={text[:60].replace(chr(10), ' ')}"
        )
        print("SUCCESS: Tweet posted")
        print(f"  Tweet ID : {tweet_id}")
        print(f"  URL      : https://twitter.com/i/web/status/{tweet_id}")
        print(f"  Length   : {len(text)} / {TWEET_MAX_CHARS} chars")
        return 0

    except Exception as exc:
        _log_action(f"ERROR posting tweet: {exc}")
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> int:
    _load_dotenv()

    parser = argparse.ArgumentParser(
        description="Twitter/X Post Skill — post tweets via Twitter API v2",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--text",   help=f"Tweet content (max {TWEET_MAX_CHARS} chars)")
    group.add_argument("--status", action="store_true",
                       help="Check configuration status and setup instructions")

    args = parser.parse_args()

    if args.status:
        return cmd_status()
    return cmd_post(args.text)


if __name__ == "__main__":
    sys.exit(main())
