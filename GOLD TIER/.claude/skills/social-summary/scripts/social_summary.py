"""
social_summary.py — Social Media Post Log Manager
Part of the Silver Tier AI Employee vault.

Usage:
  --log --platform PLATFORM --content CONTENT [--date DATE]
  --list [--platform PLATFORM] [--limit N]
  --report
  --stats
"""

import argparse
import os
import re
import sys
import datetime
from dataclasses import dataclass

# Windows cp1252 safety
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
VAULT_ROOT  = os.path.abspath(os.path.join(_SCRIPT_DIR, "..", "..", "..", ".."))
REPORTS_DIR = os.path.join(VAULT_ROOT, "Reports")
SOCIAL_LOG  = os.path.join(REPORTS_DIR, "Social_Log.md")
ACTIONS_LOG = os.path.join(VAULT_ROOT, "Logs", "actions.log")


@dataclass
class Post:
    date: str      # "YYYY-MM-DD HH:MM:SS UTC"
    platform: str  # e.g. "LinkedIn"
    content: str   # full post text


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _now_utc() -> str:
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")


def _log_action(message: str) -> None:
    """Append a timestamped line to actions.log (best-effort)."""
    try:
        os.makedirs(os.path.dirname(ACTIONS_LOG), exist_ok=True)
        ts = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
        with open(ACTIONS_LOG, "a", encoding="utf-8", errors="replace") as f:
            f.write(f"[{ts}] [social-summary] {message}\n")
    except Exception:
        pass


def _parse_posts(text: str) -> list:
    """
    Parse Post objects from the detail blocks in Social_Log.md.

    Each block looks like:
        ### YYYY-MM-DD HH:MM:SS UTC -- PLATFORM\n\nCONTENT\n\n---
    """
    pattern = re.compile(
        r"###\s+(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2} UTC)\s+--\s+(.+?)\n\n(.*?)\n\n---",
        re.DOTALL,
    )
    posts = []
    for m in pattern.finditer(text):
        posts.append(Post(
            date=m.group(1).strip(),
            platform=m.group(2).strip(),
            content=m.group(3).strip(),
        ))
    return posts


def _preview(content: str, width: int = 80) -> str:
    """Return first `width` chars, replacing newlines with spaces."""
    single = content.replace("\n", " ")
    if len(single) > width:
        return single[:width - 3] + "..."
    return single


def _platform_summary(posts: list) -> dict:
    """Return {platform: {"count": N, "last": "YYYY-MM-DD"}} dict."""
    summary = {}
    for p in posts:
        key = p.platform
        date_only = p.date[:10]
        if key not in summary:
            summary[key] = {"count": 0, "last": date_only}
        summary[key]["count"] += 1
        if date_only > summary[key]["last"]:
            summary[key]["last"] = date_only
    return summary


# ---------------------------------------------------------------------------
# File builders
# ---------------------------------------------------------------------------

def _build_file(posts: list) -> str:
    """Build the full Social_Log.md content from a list of Post objects."""
    now = _now_utc()
    total = len(posts)

    # Front matter
    created = posts[0].date if posts else now
    lines = [
        "---",
        "type: social_log",
        f"created_at: {created}",
        f"last_updated: {now}",
        f"total_posts: {total}",
        "---",
        "",
        "# Social Media Post Log",
        "",
        f"> Last updated: {now} | AI Employee System",
        "",
    ]

    # Platform Summary table
    summary = _platform_summary(posts)
    lines += [
        "## Platform Summary",
        "",
        "| Platform | Posts | Last Posted |",
        "|----------|-------|-------------|",
    ]
    if summary:
        for platform, data in sorted(summary.items()):
            lines.append(f"| {platform} | {data['count']} | {data['last']} |")
    else:
        lines.append("| — | 0 | — |")
    lines.append("")

    # Post History table
    lines += [
        "## Post History",
        "",
        "| Date                 | Platform | Content Preview                          |",
        "|----------------------|----------|------------------------------------------|",
    ]
    for p in posts:
        date_col = p.date[:16] + " UTC"
        prev = _preview(p.content, 42)
        lines.append(f"| {date_col} | {p.platform:<8} | {prev:<42} |")
    lines.append("")

    # Detail blocks
    for p in posts:
        lines += [
            "---",
            "",
            f"### {p.date} -- {p.platform}",
            "",
            p.content,
            "",
        ]
    lines.append("---")
    lines.append("")

    return "\n".join(lines)


def _read_or_init() -> tuple:
    """
    Return (text, posts).
    If file does not exist, return ("", []).
    """
    if not os.path.exists(SOCIAL_LOG):
        return ("", [])
    with open(SOCIAL_LOG, "r", encoding="utf-8", errors="replace") as f:
        text = f.read()
    posts = _parse_posts(text)
    return (text, posts)


def _write_atomic(content: str) -> None:
    """Write content to SOCIAL_LOG atomically via a .tmp file."""
    os.makedirs(REPORTS_DIR, exist_ok=True)
    tmp = SOCIAL_LOG + ".tmp"
    with open(tmp, "w", encoding="utf-8", errors="replace") as f:
        f.write(content)
    os.replace(tmp, SOCIAL_LOG)


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------

def cmd_log(platform: str, content: str, date: str | None) -> int:
    """Append a new post entry to Social_Log.md."""
    if not platform:
        print("ERROR: --platform is required with --log", file=sys.stderr)
        return 1
    if not content:
        print("ERROR: --content is required with --log", file=sys.stderr)
        return 1

    post_date = date if date else _now_utc()
    # Normalise platform name: capitalise first letter
    platform = platform.strip()
    if platform:
        platform = platform[0].upper() + platform[1:]

    _, posts = _read_or_init()
    new_post = Post(date=post_date, platform=platform, content=content.strip())
    posts.append(new_post)

    file_content = _build_file(posts)
    _write_atomic(file_content)

    _log_action(f"Logged post to {platform} (total posts: {len(posts)})")
    print(f"SUCCESS: Post logged to {SOCIAL_LOG}")
    print(f"  Platform : {platform}")
    print(f"  Date     : {post_date}")
    print(f"  Preview  : {_preview(content, 60)}")
    return 0


def cmd_list(platform_filter: str | None, limit: int) -> int:
    """Print a table of recent posts."""
    _, posts = _read_or_init()

    if platform_filter:
        pf = platform_filter.strip().lower()
        posts = [p for p in posts if p.platform.lower() == pf]

    posts = posts[-limit:]  # most recent N

    if not posts:
        print("No posts found.")
        return 0

    # Header
    header = f"{'Date':<22} {'Platform':<12} {'Preview'}"
    sep    = "-" * 22 + " " + "-" * 12 + " " + "-" * 50
    print(header)
    print(sep)
    for p in posts:
        date_col = p.date[:16] + " UTC"
        print(f"{date_col:<22} {p.platform:<12} {_preview(p.content, 50)}")
    print(f"\n{len(posts)} post(s) shown.")
    return 0


def cmd_report() -> int:
    """Print full markdown report to stdout."""
    _, posts = _read_or_init()
    if not posts:
        print("No posts recorded yet.")
        return 0

    summary = _platform_summary(posts)
    now = _now_utc()

    print("# Social Media Post Report")
    print(f"\nGenerated: {now}")
    print(f"Total posts: {len(posts)}\n")

    print("## Platform Summary\n")
    print(f"{'Platform':<15} {'Posts':>6} {'Last Posted'}")
    print("-" * 35)
    for platform, data in sorted(summary.items()):
        print(f"{platform:<15} {data['count']:>6} {data['last']}")

    print("\n## Post History\n")
    print(f"{'Date':<22} {'Platform':<12} {'Preview'}")
    print("-" * 90)
    for p in posts:
        date_col = p.date[:16] + " UTC"
        print(f"{date_col:<22} {p.platform:<12} {_preview(p.content, 50)}")

    print("\n## Full Post Content\n")
    for p in posts:
        print(f"### {p.date} -- {p.platform}")
        print()
        print(p.content)
        print()
        print("-" * 60)
        print()

    return 0


def cmd_stats() -> int:
    """Print platform breakdown counts."""
    _, posts = _read_or_init()
    if not posts:
        print("No posts recorded yet.")
        return 0

    summary = _platform_summary(posts)
    print("Platform Post Counts")
    print("-" * 30)
    for platform, data in sorted(summary.items(), key=lambda x: -x[1]["count"]):
        print(f"  {platform:<20} {data['count']:>4}")
    print("-" * 30)
    print(f"  {'TOTAL':<20} {len(posts):>4}")
    return 0


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> int:
    parser = argparse.ArgumentParser(
        description="Social Media Post Log Manager",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--log",    action="store_true", help="Log a new post")
    mode.add_argument("--list",   action="store_true", help="List recent posts")
    mode.add_argument("--report", action="store_true", help="Full report")
    mode.add_argument("--stats",  action="store_true", help="Platform counts")

    parser.add_argument("--platform", help="Platform name (e.g. LinkedIn)")
    parser.add_argument("--content",  help="Full post content text")
    parser.add_argument("--date",     help="Override post date (YYYY-MM-DD HH:MM:SS UTC)")
    parser.add_argument("--limit",    type=int, default=20, help="Max rows for --list (default 20)")

    args = parser.parse_args()

    if args.log:
        return cmd_log(args.platform or "", args.content or "", args.date)
    elif args.list:
        return cmd_list(args.platform, args.limit)
    elif args.report:
        return cmd_report()
    elif args.stats:
        return cmd_stats()

    parser.print_help()
    return 1


if __name__ == "__main__":
    sys.exit(main())
