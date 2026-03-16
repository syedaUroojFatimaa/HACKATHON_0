"""
plan_tasks.py — Bronze Tier "Make a Plan for Tasks" Agent Skill

Reads every task file in Needs_Action/, analyzes what's pending,
and generates a structured planning document in Plans/.

This is a READ-ONLY skill — it never modifies or moves task files.
It only creates a new Plan_<timestamp>.md for human review.

Usage:
    python plan_tasks.py
"""

import os
import re
from datetime import datetime, timezone
from collections import Counter


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
NEEDS_ACTION_DIR = os.path.join(SCRIPT_DIR, "Needs_Action")
PLANS_DIR = os.path.join(SCRIPT_DIR, "Plans")


# ---------------------------------------------------------------------------
# Step 1 — Discover and parse task files
# ---------------------------------------------------------------------------

def get_task_files():
    """Return a sorted list of filenames in the Needs_Action folder."""
    try:
        files = [f for f in os.listdir(NEEDS_ACTION_DIR)
                 if os.path.isfile(os.path.join(NEEDS_ACTION_DIR, f))]
        return sorted(files)
    except FileNotFoundError:
        print("[WARNING] Needs_Action folder not found.")
        return []


def parse_task(filepath):
    """
    Read a task file and extract its front-matter metadata.
    Returns a dict with keys like 'type', 'status', 'priority', etc.
    Also extracts the title (first Markdown heading) and the raw content.
    """
    with open(filepath, "r", encoding="utf-8") as f:
        content = f.read()

    metadata = {}

    # Extract YAML-style front matter between --- delimiters.
    front_matter_match = re.search(r"^---\s*\n(.*?)\n---", content, re.DOTALL)
    if front_matter_match:
        for line in front_matter_match.group(1).splitlines():
            if ":" in line:
                key, value = line.split(":", 1)
                metadata[key.strip()] = value.strip()

    # Extract the first Markdown heading as the task title.
    title_match = re.search(r"^#\s+(.+)$", content, re.MULTILINE)
    metadata["title"] = title_match.group(1).strip() if title_match else "Untitled"

    # Count how many steps (checkboxes) the task has.
    unchecked = content.count("- [ ]")
    checked = content.count("- [x]")
    metadata["steps_total"] = unchecked + checked
    metadata["steps_done"] = checked

    return metadata, content


# ---------------------------------------------------------------------------
# Step 2 — Analyze the tasks
# ---------------------------------------------------------------------------

# Priority ranking used to sort tasks. Lower number = do it first.
PRIORITY_ORDER = {"high": 1, "medium": 2, "low": 3}


def analyze_tasks(tasks):
    """
    Given a list of parsed task metadata dicts, produce analysis data:
      - type_counts:     how many tasks of each type
      - priority_counts: how many at each priority level
      - sorted_tasks:    tasks ordered by priority (high first)
      - risks:           list of potential issues found
    """
    type_counts = Counter(t.get("type", "unknown") for t in tasks)
    priority_counts = Counter(t.get("priority", "unset") for t in tasks)

    # Sort by priority (high -> medium -> low -> unset).
    sorted_tasks = sorted(
        tasks,
        key=lambda t: PRIORITY_ORDER.get(t.get("priority", ""), 99)
    )

    # Identify risks and unclear items.
    risks = []

    for t in tasks:
        # Risk: task has no priority set.
        if t.get("priority", "unset") == "unset":
            risks.append(f"`{t.get('title', '?')}` has no priority set.")

        # Risk: task has no steps defined.
        if t.get("steps_total", 0) == 0:
            risks.append(f"`{t.get('title', '?')}` has no action steps.")

        # Risk: related_files is empty.
        related = t.get("related_files", "[]")
        if related in ("[]", ""):
            risks.append(f"`{t.get('title', '?')}` has no related files listed.")

    if not risks:
        risks.append("No risks identified. All tasks appear well-structured.")

    return type_counts, priority_counts, sorted_tasks, risks


# ---------------------------------------------------------------------------
# Step 3 — Generate the plan document
# ---------------------------------------------------------------------------

def build_plan(tasks, type_counts, priority_counts, sorted_tasks, risks):
    """
    Compose the full Markdown content for the plan file.
    """
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    total = len(tasks)

    # --- Header ---
    lines = [
        "---",
        "type: plan",
        f"created_at: {now}",
        f"task_count: {total}",
        "---",
        "",
        "# Task Execution Plan",
        "",
        f"> Generated on {now}",
        "",
    ]

    # --- Summary of pending tasks ---
    lines.append("## Summary of Pending Tasks")
    lines.append("")
    lines.append(f"There are **{total}** task(s) currently in `Needs_Action/`.")
    lines.append("")

    # Breakdown by type.
    lines.append("**By type:**")
    lines.append("")
    for task_type, count in type_counts.most_common():
        lines.append(f"- `{task_type}`: {count}")
    lines.append("")

    # Breakdown by priority.
    lines.append("**By priority:**")
    lines.append("")
    for priority, count in sorted(priority_counts.items(),
                                  key=lambda x: PRIORITY_ORDER.get(x[0], 99)):
        lines.append(f"- {priority}: {count}")
    lines.append("")

    # Individual task table.
    lines.append("| # | Task | Type | Priority | Steps |")
    lines.append("|---|------|------|----------|-------|")
    for i, t in enumerate(tasks, 1):
        title = t.get("title", "Untitled")
        ttype = t.get("type", "?")
        pri = t.get("priority", "unset")
        steps = f"{t.get('steps_done', 0)}/{t.get('steps_total', 0)}"
        lines.append(f"| {i} | {title} | {ttype} | {pri} | {steps} |")
    lines.append("")

    # --- Suggested order of execution ---
    lines.append("## Suggested Order of Execution")
    lines.append("")
    for i, t in enumerate(sorted_tasks, 1):
        title = t.get("title", "Untitled")
        pri = t.get("priority", "unset")
        lines.append(f"{i}. **{title}** (priority: {pri})")
    lines.append("")

    # --- Risks and unclear items ---
    lines.append("## Risks and Unclear Items")
    lines.append("")
    for risk in risks:
        lines.append(f"- {risk}")
    lines.append("")

    # --- Strategy paragraph ---
    lines.append("## Strategy")
    lines.append("")

    # Build a short adaptive strategy based on what we found.
    high_count = priority_counts.get("high", 0)
    strategy_parts = []

    if total == 0:
        strategy_parts.append(
            "No tasks are pending. The queue is clear."
        )
    else:
        strategy_parts.append(
            f"Process the {total} pending task(s) in priority order (high before medium before low)."
        )

        if high_count > 0:
            strategy_parts.append(
                f"{high_count} high-priority task(s) should be addressed immediately."
            )

        if len(risks) > 1 or (len(risks) == 1 and "No risks" not in risks[0]):
            strategy_parts.append(
                "Review the risks listed above before starting execution "
                "to avoid wasted effort on unclear tasks."
            )

        strategy_parts.append(
            "After completing all tasks, run `process_tasks.py` to mark them done, "
            "move them to `Done/`, and update the Dashboard and System Log."
        )

    lines.append(" ".join(strategy_parts))
    lines.append("")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Step 4 — Write the plan file
# ---------------------------------------------------------------------------

def save_plan(content):
    """
    Write the plan to Plans/Plan_<timestamp>.md and return the filename.
    """
    os.makedirs(PLANS_DIR, exist_ok=True)

    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d_%H%M%S")
    plan_filename = f"Plan_{timestamp}.md"
    plan_path = os.path.join(PLANS_DIR, plan_filename)

    with open(plan_path, "w", encoding="utf-8") as f:
        f.write(content)

    return plan_filename


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    print("=" * 50)
    print("  Bronze Tier — Task Planner")
    print("=" * 50)
    print()

    # Discover tasks.
    task_files = get_task_files()

    if not task_files:
        print("[INFO] No task files found in Needs_Action/. Nothing to plan.")
        return

    print(f"[INFO] Found {len(task_files)} task(s) in Needs_Action/.\n")

    # Parse each task file.
    tasks = []
    for filename in task_files:
        filepath = os.path.join(NEEDS_ACTION_DIR, filename)
        metadata, _ = parse_task(filepath)
        metadata["_filename"] = filename
        tasks.append(metadata)
        print(f"  [READ] {filename}")

    print()

    # Analyze.
    type_counts, priority_counts, sorted_tasks, risks = analyze_tasks(tasks)

    # Generate and save the plan.
    plan_content = build_plan(tasks, type_counts, priority_counts, sorted_tasks, risks)
    plan_filename = save_plan(plan_content)

    print(f"[CREATED] Plans/{plan_filename}")
    print()
    print("Plan is ready for review. No tasks were modified.")


if __name__ == "__main__":
    main()
