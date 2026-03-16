"""
social_poster.py — Local-Only Social Media Poster

Posts social media drafts created by Cloud worker.
ONLY runs on Local machine (has access to API tokens).

Security:
- Uses .env for API tokens (never synced to Cloud)
- Tokens stored in sessions/ (never synced)
- Only Local can post to social platforms
- Logs all posts for audit

Usage:
    python scripts/social_poster.py --post approval_file.md
    python scripts/social_poster.py --test
    python scripts/social_poster.py --pending
"""

import os
import re
import sys
import argparse
import json
from datetime import datetime, timezone
from pathlib import Path


# ============================================================================
# Configuration
# ============================================================================

SCRIPT_DIR = Path(__file__).parent
VAULT_ROOT = SCRIPT_DIR.parent

# Local-only folders (never synced)
SESSIONS_DIR = VAULT_ROOT / "sessions"
LOGS_DIR = VAULT_ROOT / "Logs"

# Ensure directories exist
SESSIONS_DIR.mkdir(parents=True, exist_ok=True)
LOGS_DIR.mkdir(parents=True, exist_ok=True)

# Log file
SOCIAL_LOG = LOGS_DIR / "social_poster.log"


# ============================================================================
# Logging
# ============================================================================

def log(message: str, level: str = "INFO"):
    """Log to console and social_poster.log"""
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    entry = f"[{timestamp}] [{level}] {message}"
    print(entry)
    
    try:
        with open(SOCIAL_LOG, "a", encoding="utf-8") as f:
            f.write(entry + "\n")
    except OSError as e:
        print(f"[ERROR] Could not write to log: {e}")


# ============================================================================
# Platform Configuration
# ============================================================================

def get_twitter_config() -> dict:
    """Get Twitter API configuration from .env"""
    return {
        "api_key": os.environ.get("TWITTER_API_KEY", ""),
        "api_secret": os.environ.get("TWITTER_API_SECRET", ""),
        "access_token": os.environ.get("TWITTER_ACCESS_TOKEN", ""),
        "access_token_secret": os.environ.get("TWITTER_ACCESS_TOKEN_SECRET", ""),
    }


def get_linkedin_config() -> dict:
    """Get LinkedIn API configuration from .env"""
    return {
        "access_token": os.environ.get("LINKEDIN_ACCESS_TOKEN", ""),
        "organization_id": os.environ.get("LINKEDIN_ORG_ID", ""),
    }


def check_twitter_config() -> bool:
    """Check if Twitter is configured"""
    config = get_twitter_config()
    if not all([config["api_key"], config["api_secret"]]):
        log("Twitter API not configured in .env", "WARN")
        return False
    return True


def check_linkedin_config() -> bool:
    """Check if LinkedIn is configured"""
    config = get_linkedin_config()
    if not config["access_token"]:
        log("LinkedIn API not configured in .env", "WARN")
        return False
    return True


# ============================================================================
# Twitter Posting
# ============================================================================

def post_to_twitter(text: str, media_paths: list = None) -> bool:
    """Post to Twitter/X"""
    try:
        # Try to import tweepy
        import tweepy
        
        config = get_twitter_config()
        
        # Authenticate
        client = tweepy.Client(
            consumer_key=config["api_key"],
            consumer_secret=config["api_secret"],
            access_token=config["access_token"],
            access_token_secret=config["access_token_secret"],
        )
        
        # Post tweet
        log("Posting to Twitter...")
        
        if media_paths:
            # Upload media first
            media_ids = []
            for media_path in media_paths:
                media = client.media_upload(filename=media_path)
                media_ids.append(media.media_id)
            
            response = client.create_tweet(text=text, media_ids=media_ids)
        else:
            response = client.create_tweet(text=text)
        
        tweet_id = response.data["id"]
        log(f"Tweet posted successfully! ID: {tweet_id}")
        log(f"URL: https://twitter.com/status/{tweet_id}")
        
        return True
        
    except ImportError:
        log("tweepy not installed. Run: pip install tweepy", "ERROR")
        return False
    except Exception as e:
        log(f"Twitter post failed: {e}", "ERROR")
        return False


# ============================================================================
# LinkedIn Posting
# ============================================================================

def post_to_linkedin(text: str, organization_id: str = None) -> bool:
    """Post to LinkedIn"""
    try:
        import requests
        
        config = get_linkedin_config()
        access_token = config["access_token"]
        org_id = organization_id or config["organization_id"]
        
        # LinkedIn API endpoint
        url = "https://api.linkedin.com/v2/shares"
        
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
            "X-Restli-Protocol-Version": "2.0.0",
        }
        
        # Build post content
        post_data = {
            "text": {
                "text": text
            },
            "distribution": {
                "feedDistribution": "MAIN_FEED",
                "targetEntities": [],
                "thirdPartyDistributionChannels": [],
            },
        }
        
        # Add organization if posting to company page
        if org_id:
            post_data["owner"] = f"urn:li:organization:{org_id}"
        
        log("Posting to LinkedIn...")
        response = requests.post(url, headers=headers, json=post_data)
        
        if response.status_code in [200, 201]:
            log("LinkedIn post successful!")
            return True
        else:
            log(f"LinkedIn post failed: {response.status_code} - {response.text}", "ERROR")
            return False
            
    except ImportError:
        log("requests not installed. Run: pip install requests", "ERROR")
        return False
    except Exception as e:
        log(f"LinkedIn post failed: {e}", "ERROR")
        return False


# ============================================================================
# Approval Processing
# ============================================================================

def parse_social_approval(filepath: Path) -> dict:
    """Parse social media approval file"""
    with open(filepath, "r", encoding="utf-8") as f:
        content = f.read()
    
    data = {
        "platform": "general",
        "content": "",
        "metadata": {}
    }
    
    # Parse front matter
    if "---" in content:
        parts = content.split("---")
        if len(parts) >= 3:
            front_matter = parts[1]
            for line in front_matter.split("\n"):
                if ":" in line:
                    key, value = line.split(":", 1)
                    key = key.strip().lower()
                    value = value.strip().strip('"').strip("'")
                    data["metadata"][key] = value
    
    data["platform"] = data["metadata"].get("platform", "general")
    
    # Extract content from draft section
    content_match = re.search(r'Content.*?\n\n(.*?)(?:---|\Z)', content, re.DOTALL | re.IGNORECASE)
    if content_match:
        data["content"] = content_match.group(1).strip()
    else:
        # Fallback: use everything after front matter
        if len(parts) >= 3:
            data["content"] = parts[2].strip()
    
    return data


def process_social_approval(filepath: Path, auto_post: bool = False) -> bool:
    """Process a social media approval file and post"""
    log(f"Processing social approval: {filepath.name}")
    
    data = parse_social_approval(filepath)
    
    log(f"Platform: {data['platform']}")
    log(f"Content length: {len(data['content'])} chars")
    
    if not data["content"]:
        log("No content found in approval file", "ERROR")
        return False
    
    if auto_post:
        success = False
        
        if data["platform"].lower() == "twitter":
            if check_twitter_config():
                success = post_to_twitter(data["content"])
        elif data["platform"].lower() == "linkedin":
            if check_linkedin_config():
                success = post_to_linkedin(data["content"])
        else:
            log(f"Unknown platform: {data['platform']}", "ERROR")
            return False
        
        if success:
            update_approval_status(filepath, "posted")
        else:
            log("Failed to post", "ERROR")
        
        return success
    else:
        log("Preview mode - not posting")
        print("\n--- POST PREVIEW ---")
        print(f"Platform: {data['platform']}")
        print(f"\n{data['content'][:500]}...")
        print("--- END PREVIEW ---\n")
        return True


def update_approval_status(filepath: Path, status: str):
    """Update approval file with posted status"""
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            content = f.read()
        
        content = re.sub(
            r'^(status:\s*).*$',
            f'\\g<1>{status}',
            content,
            flags=re.MULTILINE
        )
        
        timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
        if "posted_at:" not in content:
            content = content.replace(
                f"status: {status}",
                f"status: {status}\nposted_at: {timestamp}"
            )
        
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(content)
        
        log(f"Updated approval status to: {status}")
        
    except Exception as e:
        log(f"Failed to update approval status: {e}", "ERROR")


# ============================================================================
# Commands
# ============================================================================

def run_post(approval_file: str):
    """Post from approval file"""
    filepath = Path(approval_file)
    if not filepath.exists():
        log(f"Approval file not found: {filepath}", "ERROR")
        return False
    
    return process_social_approval(filepath, auto_post=True)


def run_preview(approval_file: str):
    """Preview without posting"""
    filepath = Path(approval_file)
    if not filepath.exists():
        log(f"Approval file not found: {filepath}", "ERROR")
        return False
    
    return process_social_approval(filepath, auto_post=False)


def run_pending():
    """Process all pending social approvals"""
    pending_dir = VAULT_ROOT / "Pending_Approval" / "social"
    if not pending_dir.exists():
        log("No pending social approvals found")
        return True
    
    processed = 0
    for f in pending_dir.glob("approval_*.md"):
        if process_social_approval(f, auto_post=True):
            processed += 1
    
    log(f"Processed {processed} pending post(s)")
    return True


def run_test():
    """Post test message"""
    log("Testing social media posting...")
    
    test_content = f"Test post from AI Employee - {datetime.now().strftime('%Y-%m-%d %H:%M')}"
    
    twitter_ok = check_twitter_config()
    linkedin_ok = check_linkedin_config()
    
    if twitter_ok:
        log("Twitter: Configured")
    else:
        log("Twitter: Not configured")
    
    if linkedin_ok:
        log("LinkedIn: Configured")
    else:
        log("LinkedIn: Not configured")
    
    if not twitter_ok and not linkedin_ok:
        log("No platforms configured. Add API tokens to .env", "ERROR")
        return False
    
    return True


# ============================================================================
# Entry Point
# ============================================================================

def main():
    parser = argparse.ArgumentParser(description="Local Social Media Poster")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--post", metavar="FILE", help="Post from approval file")
    group.add_argument("--preview", metavar="FILE", help="Preview without posting")
    group.add_argument("--pending", action="store_true", help="Process all pending")
    group.add_argument("--test", action="store_true", help="Test configuration")
    group.add_argument("--check", action="store_true", help="Check platform config")
    
    args = parser.parse_args()
    
    if args.check:
        print("Twitter:", "Configured" if check_twitter_config() else "Not configured")
        print("LinkedIn:", "Configured" if check_linkedin_config() else "Not configured")
        return 0
    
    elif args.post:
        return 0 if run_post(args.post) else 1
    
    elif args.preview:
        return 0 if run_preview(args.preview) else 1
    
    elif args.pending:
        return 0 if run_pending() else 1
    
    elif args.test:
        return 0 if run_test() else 1


if __name__ == "__main__":
    sys.exit(main())
