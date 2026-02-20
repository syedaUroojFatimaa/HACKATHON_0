"""
auto_post.py — LinkedIn Auto-Post Agent Skill

Generates professional business-focused LinkedIn posts from a topic
or file, then publishes via the linkedin-post skill (Playwright).

Supports multiple post styles: tip, story, announcement, insight.

Usage:
    python auto_post.py --topic "AI for small business" --style tip
    python auto_post.py --file Inbox/launch.md --preview
"""

import argparse
import os
import random
import subprocess
import sys
import textwrap
from datetime import datetime, timezone

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
VAULT_ROOT = os.path.abspath(os.path.join(SCRIPT_DIR, "..", "..", "..", ".."))
LOGS_DIR = os.path.join(VAULT_ROOT, "Logs")
POSTS_LOG = os.path.join(LOGS_DIR, "linkedin_posts.log")
LINKEDIN_POST_SCRIPT = os.path.join(
    VAULT_ROOT, ".claude", "skills", "linkedin-post", "scripts", "post_linkedin.py"
)

MAX_POST_LENGTH = 1300

# ---------------------------------------------------------------------------
# Post templates by style
# ---------------------------------------------------------------------------

TEMPLATES = {
    "tip": textwrap.dedent("""\
        {hook}

        Here are {count} things I've learned about {topic}:

        {numbered_points}

        The bottom line: {takeaway}

        {cta}

        {hashtags}"""),

    "story": textwrap.dedent("""\
        {hook}

        {story_body}

        The lesson? {takeaway}

        {cta}

        {hashtags}"""),

    "announcement": textwrap.dedent("""\
        {hook}

        We're excited to share: {topic}.

        What this means for you:
        {bullet_points}

        {cta}

        {hashtags}"""),

    "insight": textwrap.dedent("""\
        {hook}

        {insight_body}

        Here's what smart teams are doing differently:
        {numbered_points}

        {takeaway}

        {cta}

        {hashtags}"""),
}

# Content building blocks
HOOKS = {
    "tip": [
        "Stop doing {topic} the hard way.",
        "Most people get {topic} wrong. Here's why.",
        "I spent years figuring out {topic}. Save yourself the time.",
        "{topic} doesn't have to be complicated.",
    ],
    "story": [
        "Last year, we almost gave up on {topic}.",
        "I used to think {topic} was impossible for small teams.",
        "A client asked me about {topic}. My answer surprised them.",
        "3 months ago, everything changed when we rethought {topic}.",
    ],
    "announcement": [
        "Big news for anyone who cares about {topic}.",
        "We've been working on something exciting around {topic}.",
        "This is the update on {topic} you've been waiting for.",
    ],
    "insight": [
        "The {topic} landscape is shifting fast. Here's what I'm seeing.",
        "Everyone is talking about {topic}. Few understand what's really happening.",
        "The data on {topic} tells an interesting story.",
    ],
}

CTAS = [
    "What's your experience with this? Drop a comment below.",
    "Agree or disagree? I'd love to hear your perspective.",
    "Follow for more insights like this. Repost if this resonated.",
    "Save this for later. Share with someone who needs to see it.",
    "DM me if you want to discuss how this applies to your business.",
]

BASE_HASHTAGS = ["#Business", "#Productivity", "#Growth", "#Innovation"]

TOPIC_HASHTAGS = {
    "ai": ["#AI", "#ArtificialIntelligence", "#MachineLearning", "#FutureOfWork"],
    "automation": ["#Automation", "#Efficiency", "#Digital", "#Tech"],
    "sales": ["#Sales", "#Revenue", "#B2B", "#Pipeline"],
    "marketing": ["#Marketing", "#DigitalMarketing", "#Branding", "#ContentMarketing"],
    "leadership": ["#Leadership", "#Management", "#TeamBuilding", "#Culture"],
    "startup": ["#Startup", "#Entrepreneurship", "#VC", "#ScaleUp"],
}


def pick_hashtags(topic, max_tags=5):
    """Select relevant hashtags based on topic keywords."""
    tags = set(random.sample(BASE_HASHTAGS, min(2, len(BASE_HASHTAGS))))
    topic_lower = topic.lower()
    for keyword, keyword_tags in TOPIC_HASHTAGS.items():
        if keyword in topic_lower:
            tags.update(random.sample(keyword_tags, min(2, len(keyword_tags))))
    return " ".join(list(tags)[:max_tags])


def generate_points(topic, count=3):
    """Generate numbered action points."""
    patterns = [
        f"Start with a clear goal for {topic} — specificity wins.",
        f"Automate the repetitive parts of {topic} before scaling.",
        f"Measure what matters. Vanity metrics kill {topic} momentum.",
        f"Talk to your customers weekly. They know more about {topic} than you think.",
        f"Build systems, not just habits. {topic.capitalize()} needs infrastructure.",
        f"Ship fast, iterate faster. Perfectionism is the enemy of {topic}.",
        f"Document everything about {topic}. Future you will thank present you.",
        f"Invest in your team's skills around {topic}. ROI is compounding.",
    ]
    selected = random.sample(patterns, min(count, len(patterns)))
    return "\n".join(f"{i+1}. {p}" for i, p in enumerate(selected))


def generate_bullets(topic, count=3):
    """Generate bullet points for announcements."""
    patterns = [
        f"Faster workflows around {topic}",
        f"Less manual effort, more strategic focus on {topic}",
        f"Better results with data-driven {topic}",
        f"Seamless integration into your existing {topic} stack",
        f"Real-time insights into your {topic} performance",
    ]
    selected = random.sample(patterns, min(count, len(patterns)))
    return "\n".join(f"-> {p}" for p in selected)


def generate_post(topic, style="tip", source_content=None):
    """
    Generate a LinkedIn post.
    Returns the post text (capped at MAX_POST_LENGTH).
    """
    hook = random.choice(HOOKS.get(style, HOOKS["tip"])).format(topic=topic)
    cta = random.choice(CTAS)
    hashtags = pick_hashtags(topic)
    takeaway = f"When you get {topic} right, everything else follows."
    count = random.choice([3, 4, 5])

    template_vars = {
        "hook": hook,
        "topic": topic,
        "cta": cta,
        "hashtags": hashtags,
        "takeaway": takeaway,
        "count": count,
        "numbered_points": generate_points(topic, count),
        "bullet_points": generate_bullets(topic),
    }

    if style == "story":
        if source_content:
            # Use the first ~300 chars of source content as story body.
            body = source_content.strip()[:300]
            if len(source_content.strip()) > 300:
                body += "..."
        else:
            body = (
                f"We were struggling with {topic}. Deadlines slipping, team burning out. "
                f"Then we made one change: we stopped treating {topic} as an afterthought "
                f"and built a real system around it. Within 90 days, everything shifted."
            )
        template_vars["story_body"] = body

    if style == "insight":
        template_vars["insight_body"] = (
            f"The way businesses approach {topic} is changing rapidly. "
            f"What worked 2 years ago is already outdated. The leaders in this "
            f"space aren't just adapting — they're building entirely new playbooks."
        )

    template = TEMPLATES.get(style, TEMPLATES["tip"])
    post = template.format(**template_vars)

    # Trim to max length.
    if len(post) > MAX_POST_LENGTH:
        post = post[:MAX_POST_LENGTH - 3].rsplit("\n", 1)[0] + "\n..."

    return post.strip()


def log_post(post_text, topic, style, published):
    """Log the generated post."""
    os.makedirs(LOGS_DIR, exist_ok=True)
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    status = "PUBLISHED" if published else "PREVIEW"
    entry = f"\n{'='*60}\n[{now}] [{status}] Style: {style} | Topic: {topic}\n{'='*60}\n{post_text}\n"
    try:
        with open(POSTS_LOG, "a", encoding="utf-8") as f:
            f.write(entry)
    except OSError:
        pass


def publish(post_text):
    """Publish via linkedin-post skill. Returns (success, message)."""
    if not os.path.isfile(LINKEDIN_POST_SCRIPT):
        return False, f"linkedin-post script not found at {LINKEDIN_POST_SCRIPT}"

    try:
        result = subprocess.run(
            [sys.executable, LINKEDIN_POST_SCRIPT, "--text", post_text],
            capture_output=True, text=True, timeout=120,
        )
        if result.returncode == 0:
            return True, "Post published to LinkedIn."
        else:
            stderr = result.stderr.strip() or result.stdout.strip()
            return False, f"Post failed: {stderr}"
    except subprocess.TimeoutExpired:
        return False, "Publish timed out (120s)."
    except OSError as e:
        return False, f"Could not launch publisher: {e}"


def main():
    parser = argparse.ArgumentParser(description="LinkedIn Auto-Post — generate & publish business posts")
    parser.add_argument("--topic", type=str, help="Post topic")
    parser.add_argument("--file", type=str, help="Read topic/content from a file")
    parser.add_argument("--style", choices=["tip", "story", "announcement", "insight"],
                        default="tip", help="Post style (default: tip)")
    parser.add_argument("--preview", action="store_true", help="Preview only, don't publish")
    args = parser.parse_args()

    if not args.topic and not args.file:
        parser.error("Provide --topic or --file")

    source_content = None
    topic = args.topic

    if args.file:
        path = os.path.abspath(args.file)
        if not os.path.isfile(path):
            print(f"ERROR: File not found: {path}")
            sys.exit(1)
        with open(path, "r", encoding="utf-8") as f:
            source_content = f.read()
        if not topic:
            # Extract first heading or first line as topic.
            for line in source_content.splitlines():
                line = line.strip().lstrip("#").strip()
                if line:
                    topic = line[:80]
                    break
            if not topic:
                topic = os.path.basename(path)

    print("=" * 55)
    print("  LinkedIn Auto-Post Generator")
    print("=" * 55)
    print(f"  Topic: {topic}")
    print(f"  Style: {args.style}")
    print(f"  Mode:  {'Preview' if args.preview else 'Publish'}")
    print("=" * 55)
    print()

    post_text = generate_post(topic, args.style, source_content)

    print(post_text)
    print()
    print(f"({len(post_text)} characters)")
    print()

    if args.preview:
        log_post(post_text, topic, args.style, published=False)
        print("PREVIEW: Post generated but not published. Use without --preview to post.")
        return

    success, message = publish(post_text)
    log_post(post_text, topic, args.style, published=success)

    if success:
        print(f"SUCCESS: {message}")
    else:
        print(f"ERROR: {message}")
        sys.exit(1)


if __name__ == "__main__":
    main()
