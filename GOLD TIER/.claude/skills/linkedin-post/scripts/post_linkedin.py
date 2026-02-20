"""
post_linkedin.py — Create real LinkedIn text posts via Playwright.

Requires environment variables:
  LINKEDIN_EMAIL     — LinkedIn login email
  LINKEDIN_PASSWORD  — LinkedIn login password

Requires: pip install playwright && playwright install chromium

Usage:
    python post_linkedin.py --text "Excited about our launch! #AI"
"""

import argparse
import os
import sys
from datetime import datetime, timezone

LINKEDIN_LOGIN_URL = "https://www.linkedin.com/login"
LINKEDIN_FEED_URL = "https://www.linkedin.com/feed/"
NAV_TIMEOUT = 30000  # 30 seconds


def post(text, headless=True):
    """
    Login to LinkedIn and publish a text post.
    Returns (success: bool, message: str).
    """
    email = os.environ.get("LINKEDIN_EMAIL", "").strip()
    password = os.environ.get("LINKEDIN_PASSWORD", "").strip()

    if not email:
        return False, "LINKEDIN_EMAIL environment variable not set."
    if not password:
        return False, "LINKEDIN_PASSWORD environment variable not set."
    if not text.strip():
        return False, "Post text is empty."

    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return False, "Playwright not installed. Run: pip install playwright && playwright install chromium"

    browser = None
    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch(headless=headless)
            context = browser.new_context(
                user_agent=(
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/120.0.0.0 Safari/537.36"
                )
            )
            page = context.new_page()
            page.set_default_timeout(NAV_TIMEOUT)

            # --- Login ---
            page.goto(LINKEDIN_LOGIN_URL, wait_until="networkidle")

            page.fill("#username", email)
            page.fill("#password", password)
            page.click("button[type='submit']")

            # Wait for feed to confirm login succeeded.
            try:
                page.wait_for_url("**/feed/**", timeout=NAV_TIMEOUT)
            except Exception:
                # Check for security challenge or wrong credentials.
                if "checkpoint" in page.url or "challenge" in page.url:
                    return False, "LinkedIn security challenge triggered. Complete it manually first."
                return False, "Login failed. Check LINKEDIN_EMAIL and LINKEDIN_PASSWORD."

            # --- Create post ---
            # Click the "Start a post" button on the feed.
            start_post_btn = page.locator(
                "button.share-box-feed-entry__trigger, "
                "button[class*='artdeco-button--muted']"
            ).first
            start_post_btn.click()

            # Wait for the post editor modal.
            editor = page.locator(
                "div.ql-editor[contenteditable='true'], "
                "div[role='textbox'][contenteditable='true']"
            ).first
            editor.wait_for(state="visible", timeout=NAV_TIMEOUT)

            # Type the post content.
            editor.fill(text)

            # Small pause for DOM to settle.
            page.wait_for_timeout(1000)

            # Click the Post button.
            post_btn = page.locator(
                "button.share-actions__primary-action, "
                "button[class*='share-actions__primary-action']"
            ).first
            post_btn.click()

            # Wait for the modal to close (post submitted).
            page.wait_for_timeout(3000)

            browser.close()
            return True, "LinkedIn post published."

    except Exception as e:
        if browser:
            try:
                browser.close()
            except Exception:
                pass
        return False, f"Playwright error: {e}"


def main():
    parser = argparse.ArgumentParser(description="Post to LinkedIn via browser automation")
    parser.add_argument("--text", required=True, help="Post content")
    parser.add_argument(
        "--headless",
        action="store_true",
        default=True,
        help="Run browser in headless mode (default: true)",
    )
    parser.add_argument(
        "--no-headless",
        action="store_true",
        help="Run browser with visible UI (for debugging)",
    )
    args = parser.parse_args()

    headless = not args.no_headless

    print("Publishing LinkedIn post...")
    success, message = post(args.text, headless=headless)

    if success:
        now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
        print(f"SUCCESS: {message}")
        print(f"  Posted at: {now}")
        preview = args.text[:80] + ("..." if len(args.text) > 80 else "")
        print(f"  Preview:   {preview}")
    else:
        print(f"ERROR: {message}")
        sys.exit(1)


if __name__ == "__main__":
    main()
