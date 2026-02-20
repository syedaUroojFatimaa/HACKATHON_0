"""
task_planner.py — Task Planner Agent Skill

Reads new .md files from Inbox/, analyzes their content, generates a
step-by-step execution plan in Needs_Action/, then triggers the
vault-file-manager (process_tasks.py) to archive the completed plan
in Done/.

Idempotent: a persistent JSON ledger prevents duplicate processing.

Usage:
    python scripts/task_planner.py                       # all unprocessed
    python scripts/task_planner.py --file Inbox/note.md  # single file
    python scripts/task_planner.py --plan-only           # skip archive step
"""

import argparse
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone

# ---------------------------------------------------------------------------
# Path setup
# ---------------------------------------------------------------------------

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
VAULT_ROOT = os.path.dirname(SCRIPT_DIR)

LOGS_DIR = os.path.join(VAULT_ROOT, "Logs")
ACTIONS_LOG = os.path.join(LOGS_DIR, "actions.log")
STATE_FILE = os.path.join(LOGS_DIR, ".planner_state.json")

INBOX_DIR = os.path.join(VAULT_ROOT, "Inbox")
NEEDS_ACTION_DIR = os.path.join(VAULT_ROOT, "Needs_Action")
PROCESS_TASKS_SCRIPT = os.path.join(VAULT_ROOT, "process_tasks.py")

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

def _now_str():
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")


def log_action(message):
    """Append a timestamped line to logs/actions.log and echo to stdout."""
    entry = f"[{_now_str()}] [task-planner] {message}"
    print(entry)
    try:
        os.makedirs(LOGS_DIR, exist_ok=True)
        with open(ACTIONS_LOG, "a", encoding="utf-8") as f:
            f.write(entry + "\n")
    except OSError as err:
        print(f"[WARNING] Could not write to actions.log: {err}")

# ---------------------------------------------------------------------------
# State ledger
# ---------------------------------------------------------------------------

def load_state():
    """Load {filename: {planned_at, plan_file}} from disk."""
    if not os.path.isfile(STATE_FILE):
        return {}
    try:
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return {}


def save_state(state):
    os.makedirs(LOGS_DIR, exist_ok=True)
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2)

# ---------------------------------------------------------------------------
# Content analysis
# ---------------------------------------------------------------------------

# Keywords used to classify document type.
_DOC_TYPE_PATTERNS = [
    ("meeting_notes",  r"\b(meeting|standup|sync|retro|retrospective|agenda|minutes)\b"),
    ("proposal",       r"\b(proposal|propose|RFC|design doc)\b"),
    ("report",         r"\b(report|summary|analysis|findings|results)\b"),
    ("request",        r"\b(request|please|could you|can you|need|require)\b"),
    ("review",         r"\b(review|feedback|PR|pull request|code review)\b"),
    ("todo_list",      r"\b(todo|to-do|task list|checklist)\b"),
]

# Keywords that signal high priority.
_PRIORITY_KEYWORDS = re.compile(
    r"\b(urgent|asap|critical|blocker|blocking|immediately|high.priority|p0|p1)\b",
    re.IGNORECASE,
)

# Patterns for extracting action items.
# Handles: - [ ] item, TODO: item, - TODO: item, ACTION: item, TASK: item
_ACTION_PATTERNS = re.compile(
    r"(?:^|\n)\s*(?:-\s*)?(?:\[[ x]\]\s*|(?:TODO|ACTION|TASK)\s*:?\s*)(.+)",
    re.IGNORECASE,
)

# Pattern for questions.
_QUESTION_PATTERN = re.compile(r"^.*\?\s*$", re.MULTILINE)

# Headings.
_HEADING_PATTERN = re.compile(r"^(#{1,6})\s+(.+)$", re.MULTILINE)

# References: URLs, file paths, @mentions.
_URL_PATTERN = re.compile(r"https?://[^\s\)>\]]+")
_FILE_REF_PATTERN = re.compile(r"(?<!\w)[\w./\\-]+\.(?:md|py|js|ts|json|yaml|yml|txt|csv|pdf|docx|png|jpg)\b")
_MENTION_PATTERN = re.compile(r"@[\w.-]+")


def analyze_content(text):
    """
    Analyze raw Markdown content and return an analysis dict.
    """
    analysis = {}

    # --- Word count ---
    words = text.split()
    analysis["word_count"] = len(words)

    # --- Document type ---
    detected_types = []
    text_lower = text.lower()
    for doc_type, pattern in _DOC_TYPE_PATTERNS:
        if re.search(pattern, text_lower):
            detected_types.append(doc_type)
    analysis["doc_type"] = detected_types[0] if detected_types else "general_notes"
    analysis["doc_type_all"] = detected_types or ["general_notes"]

    # --- Priority detection ---
    priority_hits = _PRIORITY_KEYWORDS.findall(text)
    if priority_hits:
        analysis["priority"] = "high"
        analysis["priority_signals"] = list(set(h.lower() for h in priority_hits))
    else:
        analysis["priority"] = "medium"
        analysis["priority_signals"] = []

    # --- Headings ---
    headings = []
    for match in _HEADING_PATTERN.finditer(text):
        level = len(match.group(1))
        title = match.group(2).strip()
        headings.append({"level": level, "title": title})
    analysis["headings"] = headings

    # --- Action items ---
    actions = [m.strip() for m in _ACTION_PATTERNS.findall(text) if m.strip()]
    analysis["action_items"] = actions

    # --- Questions ---
    raw_questions = [m.strip() for m in _QUESTION_PATTERN.findall(text) if m.strip() and not m.strip().startswith("#")]
    # Strip leading list markers (- , * , numbers) so output doesn't double up.
    cleaned_questions = []
    for q in raw_questions:
        q = re.sub(r"^[-*]\s*", "", q)
        q = re.sub(r"^\d+[.)]\s*", "", q)
        if q:
            cleaned_questions.append(q)
    analysis["questions"] = cleaned_questions

    # --- References ---
    urls = list(set(_URL_PATTERN.findall(text)))
    file_refs = list(set(_FILE_REF_PATTERN.findall(text)))
    mentions = list(set(_MENTION_PATTERN.findall(text)))
    analysis["urls"] = urls
    analysis["file_refs"] = file_refs
    analysis["mentions"] = mentions

    return analysis

# ---------------------------------------------------------------------------
# Plan generation
# ---------------------------------------------------------------------------

def generate_plan(source_filename, content, analysis):
    """
    Build a structured Markdown plan document from the analysis results.
    Returns (plan_filename, plan_content).
    """
    now = datetime.now(timezone.utc)
    timestamp = now.strftime("%Y-%m-%d %H:%M:%S UTC")
    priority = analysis["priority"]
    doc_type = analysis["doc_type"]

    safe_name = source_filename.replace(".", "_").replace(" ", "_")
    plan_filename = f"Plan_{safe_name}.md"

    lines = []

    # --- Front-matter ---
    lines.append("---")
    lines.append("type: plan")
    lines.append("status: pending")
    lines.append(f"priority: {priority}")
    lines.append(f"created_at: {timestamp}")
    lines.append(f"source_file: {source_filename}")
    file_refs = analysis.get("file_refs", [])
    related = [source_filename] + file_refs[:5]
    lines.append(f'related_files: {json.dumps(related)}')
    lines.append("---")
    lines.append("")

    # --- Title ---
    lines.append(f"# Execution Plan: {source_filename}")
    lines.append("")
    lines.append(f"> Auto-generated by task-planner on {timestamp}")
    lines.append("")

    # --- Content Summary ---
    lines.append("## Content Summary")
    lines.append("")
    lines.append(f"- **Source file:** `{source_filename}`")
    lines.append(f"- **Document type:** {doc_type}")
    lines.append(f"- **Word count:** {analysis['word_count']}")
    lines.append(f"- **Sections:** {len(analysis['headings'])}")
    lines.append(f"- **Action items found:** {len(analysis['action_items'])}")
    lines.append(f"- **Open questions:** {len(analysis['questions'])}")
    lines.append("")

    if analysis["headings"]:
        lines.append("**Document structure:**")
        lines.append("")
        for h in analysis["headings"]:
            indent = "  " * (h["level"] - 1)
            lines.append(f"{indent}- {h['title']}")
        lines.append("")

    # --- Extracted Action Items ---
    if analysis["action_items"]:
        lines.append("## Extracted Action Items")
        lines.append("")
        for item in analysis["action_items"]:
            lines.append(f"- {item}")
        lines.append("")

    # --- Identified Questions ---
    if analysis["questions"]:
        lines.append("## Identified Questions")
        lines.append("")
        for q in analysis["questions"]:
            lines.append(f"- {q}")
        lines.append("")

    # --- Step-by-Step Execution Plan ---
    lines.append("## Steps")
    lines.append("")
    step = 0

    # Step: Review the source document.
    step += 1
    lines.append(f"- [ ] **Step {step}:** Open and read `{source_filename}` in full")

    # Steps from extracted action items.
    for item in analysis["action_items"]:
        step += 1
        lines.append(f"- [ ] **Step {step}:** {item}")

    # Steps for answering questions.
    if analysis["questions"]:
        step += 1
        lines.append(f"- [ ] **Step {step}:** Resolve open questions ({len(analysis['questions'])} found)")

    # Steps for referenced files.
    if analysis["file_refs"]:
        step += 1
        refs_str = ", ".join(f"`{r}`" for r in analysis["file_refs"][:5])
        lines.append(f"- [ ] **Step {step}:** Review referenced files: {refs_str}")

    # Step: final review & archive.
    step += 1
    lines.append(f"- [ ] **Step {step}:** Verify all actions are complete and archive")
    lines.append("")

    # --- Priority & Risk Assessment ---
    lines.append("## Priority & Risk Assessment")
    lines.append("")
    lines.append(f"- **Assigned priority:** {priority}")
    if analysis["priority_signals"]:
        signals = ", ".join(f"*{s}*" for s in analysis["priority_signals"])
        lines.append(f"- **Reason:** High-priority keywords detected: {signals}")
    else:
        lines.append("- **Reason:** No urgency signals detected; defaulting to medium.")
    lines.append("")

    risks = []
    if analysis["word_count"] > 1000:
        risks.append("Long document — may need multiple review passes.")
    if not analysis["action_items"]:
        risks.append("No explicit action items found — plan steps are inferred.")
    if len(analysis["questions"]) > 3:
        risks.append(f"Many open questions ({len(analysis['questions'])}) — clarification may be needed before execution.")
    if not risks:
        risks.append("No significant risks identified.")

    for r in risks:
        lines.append(f"- {r}")
    lines.append("")

    # --- References ---
    if analysis["urls"] or analysis["file_refs"] or analysis["mentions"]:
        lines.append("## References")
        lines.append("")
        if analysis["urls"]:
            for u in analysis["urls"]:
                lines.append(f"- {u}")
        if analysis["file_refs"]:
            for f_ref in analysis["file_refs"]:
                lines.append(f"- `{f_ref}`")
        if analysis["mentions"]:
            for m in analysis["mentions"]:
                lines.append(f"- {m}")
        lines.append("")

    # --- Notes ---
    lines.append("## Notes")
    lines.append("")
    lines.append(f"- Generated from: `Inbox/{source_filename}`")
    lines.append("- Planner: task-planner skill (`scripts/task_planner.py`)")
    lines.append("")

    return plan_filename, "\n".join(lines)

# ---------------------------------------------------------------------------
# Vault-file-manager integration
# ---------------------------------------------------------------------------

def trigger_archive():
    """Invoke process_tasks.py to mark plans complete and move to Done/."""
    if not os.path.isfile(PROCESS_TASKS_SCRIPT):
        log_action(f"[ERROR] process_tasks.py not found at {PROCESS_TASKS_SCRIPT}")
        return False

    try:
        result = subprocess.run(
            [sys.executable, PROCESS_TASKS_SCRIPT],
            cwd=VAULT_ROOT,
            capture_output=True,
            text=True,
            timeout=60,
        )
        if result.returncode == 0:
            log_action("Vault-file-manager: plan archived to Done/ successfully.")
        else:
            log_action(f"[ERROR] process_tasks.py exited with code {result.returncode}")
            if result.stderr:
                log_action(f"  stderr: {result.stderr.strip()}")
        return result.returncode == 0
    except subprocess.TimeoutExpired:
        log_action("[ERROR] process_tasks.py timed out (60s limit).")
        return False
    except OSError as err:
        log_action(f"[ERROR] Could not launch process_tasks.py: {err}")
        return False

# ---------------------------------------------------------------------------
# Inbox scanning
# ---------------------------------------------------------------------------

def scan_inbox(inbox_dir):
    """Return a sorted list of .md filenames in the inbox."""
    try:
        return sorted(
            f for f in os.listdir(inbox_dir)
            if f.lower().endswith(".md") and os.path.isfile(os.path.join(inbox_dir, f))
        )
    except FileNotFoundError:
        return []

# ---------------------------------------------------------------------------
# Core: plan a single file
# ---------------------------------------------------------------------------

def plan_file(filepath, state, plan_only=False):
    """
    Analyze a single .md file and generate an execution plan.
    Returns True on success, False on failure.
    """
    filename = os.path.basename(filepath)

    # Idempotency check.
    if filename in state:
        log_action(f"Skipped (already planned): {filename}")
        return True

    if not os.path.isfile(filepath):
        log_action(f"[ERROR] File not found: {filepath}")
        return False

    # Read content.
    log_action(f"Reading: {filename}")
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            content = f.read()
    except OSError as err:
        log_action(f"[ERROR] Cannot read {filename}: {err}")
        return False

    if not content.strip():
        log_action(f"[WARNING] File is empty, generating minimal plan: {filename}")

    # Analyze.
    log_action(f"Analyzing content of {filename} ({len(content.split())} words)")
    analysis = analyze_content(content)

    # Generate plan.
    plan_filename, plan_content = generate_plan(filename, content, analysis)
    plan_path = os.path.join(NEEDS_ACTION_DIR, plan_filename)

    os.makedirs(NEEDS_ACTION_DIR, exist_ok=True)
    try:
        with open(plan_path, "w", encoding="utf-8") as f:
            f.write(plan_content)
    except OSError as err:
        log_action(f"[ERROR] Cannot write plan {plan_filename}: {err}")
        return False

    log_action(f"Plan created: Needs_Action/{plan_filename}")

    # Archive via vault-file-manager.
    if not plan_only:
        log_action("Triggering vault-file-manager to archive plan...")
        trigger_archive()

    # Record in ledger.
    state[filename] = {
        "planned_at": _now_str(),
        "plan_file": plan_filename,
    }
    save_state(state)

    log_action(f"Done planning: {filename}")
    return True

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Task Planner — analyze Inbox .md files and generate execution plans"
    )
    parser.add_argument(
        "--file",
        type=str,
        default=None,
        help="Process a single file (path relative to vault root or absolute)",
    )
    parser.add_argument(
        "--inbox",
        type=str,
        default=INBOX_DIR,
        help="Inbox directory to scan (default: Inbox/)",
    )
    parser.add_argument(
        "--plan-only",
        action="store_true",
        help="Generate plans but skip the archive step (no move to Done/)",
    )
    args = parser.parse_args()

    print("=" * 55)
    print("  Task Planner — Analyze & Plan")
    print("=" * 55)

    state = load_state()

    if args.file:
        # Single-file mode.
        filepath = os.path.abspath(args.file)
        log_action(f"Single-file mode: {filepath}")
        success = plan_file(filepath, state, plan_only=args.plan_only)
        if success:
            print(f"\nPlan generated successfully.")
        else:
            print(f"\nPlanning failed. Check logs/actions.log for details.")
            sys.exit(1)
    else:
        # Scan inbox for all unprocessed .md files.
        inbox_dir = os.path.abspath(args.inbox)
        log_action(f"Scanning inbox: {inbox_dir}")
        files = scan_inbox(inbox_dir)

        unprocessed = [f for f in files if f not in state]

        if not unprocessed:
            log_action("No new .md files to plan.")
            print("\nNothing to do.")
            return

        log_action(f"Found {len(unprocessed)} new file(s) to plan.")

        success_count = 0
        fail_count = 0

        for filename in unprocessed:
            filepath = os.path.join(inbox_dir, filename)
            if plan_file(filepath, state, plan_only=args.plan_only):
                success_count += 1
            else:
                fail_count += 1

        log_action(f"Batch complete: {success_count} planned, {fail_count} failed.")
        print(f"\nDone. {success_count} plan(s) created, {fail_count} failure(s).")


if __name__ == "__main__":
    main()
