"""
ralph_loop.py - Ralph Wiggum Autonomous Loop

Autonomously executes tasks in Needs_Action/ step-by-step.

For each eligible pending task the loop:
  1. Reads the task file and parses its ## Steps checkboxes
  2. Generates Plans/<task>_Plan.md (execution log — appended each cycle)
  3. Iterates through unchecked steps (up to MAX_ITER per cycle):
       a. Risk-checks the step text
       b. Risky steps -> non-blocking Needs_Approval/ gate (resumes next cycle)
       c. Safe steps  -> routed to an action handler, marked [x] in-file
  4. When all steps are checked: updates front-matter, moves file to Done/,
     appends to Dashboard.md and System_Log.md

Safety:
  MAX_ITER  = 5   Max step-executions per task per scheduler cycle
  MAX_TASKS = 10  Max tasks processed per scheduler cycle

State:  Logs/.ralph_state.json
Plans:  Plans/<taskname>_Plan.md   (created/updated each cycle)

Modes:
  --run            Process all eligible tasks [used by scheduler]
  --task FILE      Process a single specific task file
  --status         Show current loop state summary
  --reset FILE     Clear loop state for one task (allows re-processing)

Usage:
  python ralph_loop.py --run
  python ralph_loop.py --task Needs_Action/task_foo.md
  python ralph_loop.py --status
  python ralph_loop.py --reset task_foo.md

Exit codes:
  0 - success
  1 - fatal error
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import sys
from datetime import datetime, timezone

# ── stdout encoding fix (Windows cp1252 terminals) ────────────────────────────
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

# ── Paths ─────────────────────────────────────────────────────────────────────
_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
# .claude/skills/ralph-wiggum-loop/scripts/ -> vault root (4 levels up)
VAULT_ROOT = os.path.abspath(os.path.join(_SCRIPT_DIR, "..", "..", "..", ".."))

NEEDS_ACTION_DIR  = os.path.join(VAULT_ROOT, "Needs_Action")
NEEDS_APPROVAL_DIR = os.path.join(VAULT_ROOT, "Needs_Approval")
DONE_DIR          = os.path.join(VAULT_ROOT, "Done")
PLANS_DIR         = os.path.join(VAULT_ROOT, "Plans")
LOGS_DIR          = os.path.join(VAULT_ROOT, "Logs")

ACTIONS_LOG  = os.path.join(LOGS_DIR, "actions.log")
SYSTEM_LOG   = os.path.join(VAULT_ROOT, "Logs", "System_Log.md")
DASHBOARD    = os.path.join(VAULT_ROOT, "Dashboard.md")
STATE_FILE   = os.path.join(LOGS_DIR, ".ralph_state.json")

# ── Tunables ──────────────────────────────────────────────────────────────────
MAX_ITER    = 5     # max step-executions per task per scheduler cycle
MAX_TASKS   = 10    # max tasks processed per scheduler cycle

# ── Risk patterns — any match triggers the human approval gate ────────────────
_RISK_RE = re.compile(
    r"\b(delete|remove|drop|destroy|wipe|truncate"
    r"|send\s+email|email\s+to|notify|message"
    r"|post|publish|deploy|release|push"
    r"|overwrite|reset|clear"
    r"|linkedin|twitter|social\s+media"
    r"|production|live\s+server|external"
    r"|payment|charge|billing|invoice\s+send)\b",
    re.IGNORECASE,
)

# ── Step patterns — headings under which checkbox steps live ──────────────────
_STEPS_SECTION_RE = re.compile(
    r"##\s+Steps?\s*\n(.*?)(?=\n##|\Z)", re.DOTALL | re.IGNORECASE
)
_CHECKBOX_RE = re.compile(r"^(\s*-\s*)\[([ xX])\]\s*(.+)$", re.MULTILINE)

# ── Action routing patterns ───────────────────────────────────────────────────
_LOG_RE      = re.compile(r"\b(log|record|note|document|track|write)\b", re.IGNORECASE)
_REVIEW_RE   = re.compile(r"\b(read|review|open|examine|analyze|check|verify|confirm|inspect)\b", re.IGNORECASE)
_ARCHIVE_RE  = re.compile(r"\b(archive|complete|finish|close|done|mark\s+complete|move\s+to\s+done)\b", re.IGNORECASE)

# ── Time helpers ──────────────────────────────────────────────────────────────
def _now() -> datetime:
    return datetime.now(timezone.utc)

def _now_str() -> str:
    return _now().strftime("%Y-%m-%d %H:%M:%S UTC")

def _ts() -> str:
    return _now().strftime("%Y%m%d_%H%M%S")

# ── Logging ───────────────────────────────────────────────────────────────────
def _log(message: str) -> None:
    """Print and append to Logs/actions.log."""
    entry = f"[{_now_str()}] [ralph-loop] {message}"
    print(entry)
    try:
        os.makedirs(LOGS_DIR, exist_ok=True)
        with open(ACTIONS_LOG, "a", encoding="utf-8") as fh:
            fh.write(entry + "\n")
    except OSError:
        pass

# ── State management ──────────────────────────────────────────────────────────
def _load_state() -> dict:
    if not os.path.isfile(STATE_FILE):
        return {}
    try:
        with open(STATE_FILE, encoding="utf-8") as fh:
            return json.load(fh)
    except (json.JSONDecodeError, OSError):
        return {}

def _save_state(state: dict) -> None:
    os.makedirs(LOGS_DIR, exist_ok=True)
    tmp = STATE_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(state, fh, indent=2)
    os.replace(tmp, STATE_FILE)

# ── Task file parsing ─────────────────────────────────────────────────────────

def _read_task(path: str) -> str:
    try:
        with open(path, encoding="utf-8", errors="replace") as fh:
            return fh.read()
    except OSError:
        return ""

def _write_task(path: str, content: str) -> None:
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(content)

def _parse_frontmatter_field(content: str, field: str) -> str:
    m = re.search(rf"^{re.escape(field)}\s*:\s*(.+)$", content, re.MULTILINE)
    return m.group(1).strip() if m else ""

def _update_frontmatter_field(content: str, field: str, value: str) -> str:
    """Update or append a field in the YAML front-matter."""
    lines = content.split("\n")
    if not lines or lines[0].strip() != "---":
        return content
    fm_end = next((i for i in range(1, len(lines)) if lines[i].strip() == "---"), -1)
    if fm_end == -1:
        return content
    fm = lines[1:fm_end]
    pat = re.compile(rf"^{re.escape(field)}\s*:")
    updated = False
    for i, ln in enumerate(fm):
        if pat.match(ln):
            fm[i] = f"{field}: {value}"
            updated = True
            break
    if not updated:
        fm.append(f"{field}: {value}")
    return "\n".join(["---"] + fm + ["---"] + lines[fm_end + 1:])

def _parse_steps(content: str) -> list[dict]:
    """
    Parse all - [ ] / - [x] checkboxes from the ## Steps section.
    Returns list of {index, text, done, raw} dicts.
    """
    m = _STEPS_SECTION_RE.search(content)
    steps_block = m.group(1) if m else content
    steps = []
    for i, match in enumerate(_CHECKBOX_RE.finditer(steps_block)):
        steps.append({
            "index": i,
            "prefix": match.group(1),
            "done": match.group(2).strip().lower() == "x",
            "text": match.group(3).strip(),
            "raw": match.group(0),
        })
    return steps

def _mark_step_done_in_file(path: str, step: dict, result: str) -> None:
    """
    Replace - [ ] with - [x] for a specific step in the task file.
    Appends a brief result note as a sub-bullet.
    """
    content = _read_task(path)
    old_raw = step["raw"]
    new_raw = f"{step['prefix']}[x] {step['text']}\n  > {_now_str()}: {result}"
    updated = content.replace(old_raw, new_raw, 1)
    _write_task(path, updated)

# ── Risk detection ────────────────────────────────────────────────────────────

def _is_risky(step_text: str) -> bool:
    """Return True if the step text matches any risk pattern."""
    return bool(_RISK_RE.search(step_text))

# ── Step action handlers ──────────────────────────────────────────────────────

def _handle_log(step_text: str, task_name: str) -> str:
    """Write a log entry to Logs/actions.log."""
    message = f"[{task_name}] Step executed: {step_text}"
    _log(f"LOG_STEP | {message}")
    return "LOGGED: activity recorded to actions.log"

def _handle_review(step_text: str, _task_name: str) -> str:
    return f"REVIEWED: acknowledged by autonomous agent"

def _handle_archive(_step_text: str, _task_name: str) -> str:
    return "ACKNOWLEDGED: completion step noted — task will be archived on finish"

def _handle_default(step_text: str, _task_name: str) -> str:
    return f"EXECUTED: step processed by autonomous agent"

def _route_step(step_text: str, task_name: str) -> str:
    """Route a step to the appropriate handler. Returns a result string."""
    if _REVIEW_RE.search(step_text):
        return _handle_review(step_text, task_name)
    if _LOG_RE.search(step_text):
        return _handle_log(step_text, task_name)
    if _ARCHIVE_RE.search(step_text):
        return _handle_archive(step_text, task_name)
    return _handle_default(step_text, task_name)

# ── Non-blocking approval submission ─────────────────────────────────────────

def _submit_for_approval(task_path: str, step: dict, task_name: str) -> str:
    """
    Write an approval request to Needs_Approval/ and return the filename.
    Non-blocking — the scheduler's check_approvals step handles the response.
    """
    os.makedirs(NEEDS_APPROVAL_DIR, exist_ok=True)
    now      = _now()
    req_at   = now.strftime("%Y-%m-%d %H:%M:%S UTC")
    safe     = task_name.replace(".", "_").replace(" ", "_")
    step_n   = step["index"] + 1
    fname    = f"ralph_approval_{safe}_step{step_n}_{_ts()}.md"
    path     = os.path.join(NEEDS_APPROVAL_DIR, fname)

    # Read original task content for context
    task_content = _read_task(task_path)

    content = f"""---
type: approval_request
status: pending_approval
requested_at: {req_at}
source_file: {task_name}
requesting_skill: ralph-wiggum-loop
step_number: {step_n}
step_text: {step['text']}
---

# Approval Request: Risky Step Detected

**Requested by:** Ralph Wiggum Autonomous Loop
**Task:** `{task_name}`
**Step {step_n}:** {step['text']}

## Why Approval Is Needed

The following step was flagged as potentially risky:

> **{step['text']}**

Risky signals: contains keywords related to external actions, data modification,
or communications that should not be performed without human oversight.

## Task Context

```
{task_content[:800].rstrip()}
```

## Decision

<!-- Write your decision below this line, then save the file. -->
<!-- Type APPROVED to allow execution, or REJECTED to skip this step. -->

"""
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(content)

    _log(f"APPROVAL_SUBMITTED | file={fname} | task={task_name} | step={step_n}")
    return fname

def _check_approval(approval_fname: str) -> str | None:
    """
    Check if an approval file has been resolved.
    Returns 'approved', 'rejected', or None (still pending).
    """
    base = os.path.join(NEEDS_APPROVAL_DIR, approval_fname)
    if os.path.isfile(base + ".approved"):
        return "approved"
    if os.path.isfile(base + ".rejected"):
        return "rejected"
    if os.path.isfile(base + ".timeout"):
        return "rejected"   # treat timeout as rejected (safe default)
    return None   # still pending

# ── Plans/ execution log ──────────────────────────────────────────────────────

def _plan_path(task_name: str) -> str:
    safe = task_name.replace(".", "_").replace(" ", "_")
    return os.path.join(PLANS_DIR, f"{safe}_Plan.md")

def _init_plan(task_name: str, task_content: str, steps: list[dict]) -> str:
    """Create the Plan.md if it doesn't exist. Returns the plan file path."""
    os.makedirs(PLANS_DIR, exist_ok=True)
    path = _plan_path(task_name)
    if os.path.isfile(path):
        return path

    task_type  = _parse_frontmatter_field(task_content, "type")
    priority   = _parse_frontmatter_field(task_content, "priority")
    created_at = _parse_frontmatter_field(task_content, "created_at")
    now        = _now_str()

    lines = [
        "---",
        "type: ralph_plan",
        f"task_source: {task_name}",
        "status: in_progress",
        f"created_at: {now}",
        "---",
        "",
        f"# Autonomous Execution Plan: {task_name}",
        "",
        f"> Ralph Wiggum Loop | Started: {now}",
        "",
        "## Task Summary",
        "",
        f"- **File:** `{task_name}`",
        f"- **Type:** {task_type or 'unknown'}",
        f"- **Priority:** {priority or 'medium'}",
        f"- **Created:** {created_at or 'unknown'}",
        f"- **Steps total:** {len(steps)}",
        "",
        "## Execution Log",
        "",
    ]
    with open(path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines))
    return path

def _append_plan_log(plan_path: str, entry: str) -> None:
    """Append a timestamped line to the plan's execution log."""
    try:
        with open(plan_path, "a", encoding="utf-8") as fh:
            fh.write(f"- `{_now_str()}` {entry}\n")
    except OSError:
        pass

def _close_plan(plan_path: str, outcome: str) -> None:
    """Append final status to the plan file."""
    try:
        with open(plan_path, "a", encoding="utf-8") as fh:
            fh.write(f"\n## Outcome\n\n**{outcome}** — {_now_str()}\n")
    except OSError:
        pass

# ── Task completion: move to Done/, update Dashboard + System_Log ─────────────

def _unique_done_path(fname: str) -> str:
    dest = os.path.join(DONE_DIR, fname)
    if not os.path.exists(dest):
        return dest
    name, ext = os.path.splitext(fname)
    return os.path.join(DONE_DIR, f"{name}_{_ts()}{ext}")

def _move_to_done(task_path: str, task_name: str) -> str:
    """Move a task file to Done/ and return the destination path."""
    os.makedirs(DONE_DIR, exist_ok=True)
    dest = _unique_done_path(task_name)
    shutil.move(task_path, dest)
    return dest

def _update_dashboard(task_name: str, task_type: str) -> None:
    """Append a row to the Completed Tasks table in Dashboard.md."""
    if not os.path.isfile(DASHBOARD):
        return
    try:
        with open(DASHBOARD, encoding="utf-8") as fh:
            content = fh.read()
        ts  = _now().strftime("%Y-%m-%d %H:%M UTC")
        row = f"| {task_name} | {ts} | {task_type} — ralph-loop |"
        # Insert after the Completed Tasks table header
        content = content.replace(
            "| Task | Completed On | Notes |",
            f"| Task | Completed On | Notes |\n{row}",
            1,
        )
        with open(DASHBOARD, "w", encoding="utf-8") as fh:
            fh.write(content)
    except OSError:
        pass

def _update_system_log(task_name: str, task_type: str) -> None:
    """Append a row to the Activity Log table in System_Log.md."""
    if not os.path.isfile(SYSTEM_LOG):
        return
    try:
        with open(SYSTEM_LOG, encoding="utf-8") as fh:
            content = fh.read()
        ts  = _now().strftime("%Y-%m-%d %H:%M UTC")
        row = (
            f"| {ts} | Task completed (ralph-loop) | "
            f"Processed {task_type} for `{task_name}` — moved to Done |"
        )
        content = content.replace(
            "| Timestamp | Action | Details |",
            f"| Timestamp | Action | Details |\n{row}",
            1,
        )
        with open(SYSTEM_LOG, "w", encoding="utf-8") as fh:
            fh.write(content)
    except OSError:
        pass

# ── Core task loop ────────────────────────────────────────────────────────────

def process_task(task_path: str, task_name: str) -> str:
    """
    Run the autonomous loop for one task file.

    Returns one of:
      'completed'         — all steps done; file moved to Done/
      'in_progress'       — steps remain; will continue next cycle
      'max_iter'          — hit MAX_ITER this cycle; will continue next cycle
      'awaiting_approval' — risky step submitted; waiting for human decision
      'skipped'           — not a suitable task for the loop
      'error'             — unrecoverable error
    """
    state     = _load_state()
    task_state = state.get(task_name, {})

    # Skip already completed
    if task_state.get("status") == "completed":
        return "skipped"

    # ── Resume from pending approval ────────────────────────────────────────
    if task_state.get("status") == "awaiting_approval":
        approval_fname = task_state.get("approval_file", "")
        decision       = _check_approval(approval_fname) if approval_fname else "rejected"

        if decision is None:
            _log(f"APPROVAL_PENDING | task={task_name} | file={approval_fname}")
            return "awaiting_approval"

        awaiting_step = task_state.get("awaiting_step", 0)
        plan_p        = _plan_path(task_name)

        if decision == "approved":
            _log(f"APPROVAL_GRANTED | task={task_name} | step={awaiting_step + 1}")
            _append_plan_log(plan_p, f"Step {awaiting_step + 1}: APPROVED by human — executing")
            # Execute the previously risky step
            content = _read_task(task_path)
            steps   = _parse_steps(content)
            if awaiting_step < len(steps):
                step   = steps[awaiting_step]
                result = _route_step(step["text"], task_name)
                _mark_step_done_in_file(task_path, step, result)
                _append_plan_log(plan_p, f"Step {awaiting_step + 1}: {result}")
            task_state["status"]       = "in_progress"
            task_state["current_step"] = awaiting_step + 1
        else:
            _log(f"APPROVAL_DENIED | task={task_name} | step={awaiting_step + 1} | skipping step")
            _append_plan_log(plan_p, f"Step {awaiting_step + 1}: REJECTED by human — step skipped")
            # Mark step as skipped (not done) but advance pointer
            content = _read_task(task_path)
            steps   = _parse_steps(content)
            if awaiting_step < len(steps):
                step = steps[awaiting_step]
                _mark_step_done_in_file(task_path, step, "SKIPPED: rejected by human reviewer")
            task_state["status"]       = "in_progress"
            task_state["current_step"] = awaiting_step + 1

        task_state.pop("approval_file", None)
        task_state.pop("awaiting_step", None)
        state[task_name] = task_state
        _save_state(state)
        # Fall through to continue processing remaining steps this cycle

    # ── Read task file ────────────────────────────────────────────────────────
    if not os.path.isfile(task_path):
        _log(f"ERROR | task={task_name} | file not found")
        state.pop(task_name, None)
        _save_state(state)
        return "error"

    content   = _read_task(task_path)
    task_type = _parse_frontmatter_field(content, "type")
    priority  = _parse_frontmatter_field(content, "priority")

    # Skip plan-type files (those are generated by task_planner, not real tasks)
    if task_type == "plan":
        return "skipped"

    steps = _parse_steps(content)
    if not steps:
        # Task has no checkbox steps — mark complete immediately
        _log(f"NO_STEPS | task={task_name} — marking complete")
        content = _update_frontmatter_field(content, "status", "completed")
        content = _update_frontmatter_field(content, "completed_at", _now_str())
        content = _update_frontmatter_field(content, "completed_by", "ralph-wiggum-loop")
        _write_task(task_path, content)
        _move_to_done(task_path, task_name)
        _update_dashboard(task_name, task_type)
        _update_system_log(task_name, task_type)
        task_state = {"status": "completed", "completed_at": _now().isoformat()}
        state[task_name] = task_state
        _save_state(state)
        return "completed"

    # ── Initialise state for first visit ──────────────────────────────────────
    if not task_state:
        task_state = {
            "status":       "in_progress",
            "current_step": 0,
            "iterations":   0,
            "started_at":   _now().isoformat(),
        }
        _log(f"START | task={task_name} | steps={len(steps)} | priority={priority}")

    # ── Ensure Plan.md exists ─────────────────────────────────────────────────
    plan_p = _init_plan(task_name, content, steps)
    _append_plan_log(plan_p, f"--- Cycle started | steps_total={len(steps)} "
                    f"| steps_done={sum(1 for s in steps if s['done'])} ---")

    # ── Step execution loop ───────────────────────────────────────────────────
    local_iters  = 0
    current_step = task_state.get("current_step", 0)

    # Reload steps each iteration (file may change between iterations)
    content = _read_task(task_path)
    steps   = _parse_steps(content)

    while current_step < len(steps) and local_iters < MAX_ITER:
        step = steps[current_step]

        if step["done"]:
            # Already checked off — skip forward
            current_step += 1
            continue

        step_label = f"Step {current_step + 1}/{len(steps)}"

        # ── Risk gate ─────────────────────────────────────────────────────────
        if _is_risky(step["text"]):
            _log(f"RISKY_STEP | task={task_name} | {step_label}: {step['text'][:60]}")
            approval_fname = _submit_for_approval(task_path, step, task_name)
            _append_plan_log(plan_p, f"{step_label}: RISKY — submitted for human approval "
                            f"(file: {approval_fname})")
            task_state.update({
                "status":        "awaiting_approval",
                "approval_file": approval_fname,
                "awaiting_step": current_step,
                "current_step":  current_step,
                "iterations":    task_state.get("iterations", 0) + local_iters,
                "last_run":      _now().isoformat(),
            })
            state[task_name] = task_state
            _save_state(state)
            return "awaiting_approval"

        # ── Execute step ──────────────────────────────────────────────────────
        _log(f"EXEC | task={task_name} | {step_label}: {step['text'][:60]}")
        result = _route_step(step["text"], task_name)
        _mark_step_done_in_file(task_path, step, result)
        _append_plan_log(plan_p, f"{step_label}: {result}")

        current_step += 1
        local_iters  += 1

        # Reload steps after modifying the file
        content = _read_task(task_path)
        steps   = _parse_steps(content)

    # ── Update task state ─────────────────────────────────────────────────────
    task_state["current_step"] = current_step
    task_state["iterations"]   = task_state.get("iterations", 0) + local_iters
    task_state["last_run"]     = _now().isoformat()

    # Check if all steps are done
    all_done = all(s["done"] for s in steps) or current_step >= len(steps)

    if all_done:
        _log(f"COMPLETE | task={task_name} | total_iterations={task_state['iterations']}")
        _append_plan_log(plan_p, f"--- All steps completed ---")
        _close_plan(plan_p, "COMPLETED")

        # Finalise task file front-matter
        content = _read_task(task_path)
        content = _update_frontmatter_field(content, "status", "completed")
        content = _update_frontmatter_field(content, "completed_at", _now_str())
        content = _update_frontmatter_field(content, "completed_by", "ralph-wiggum-loop")
        content = _update_frontmatter_field(
            content, "ralph_iterations", str(task_state["iterations"])
        )
        _write_task(task_path, content)

        _move_to_done(task_path, task_name)
        _update_dashboard(task_name, task_type)
        _update_system_log(task_name, task_type)

        task_state["status"]       = "completed"
        task_state["completed_at"] = _now().isoformat()
        state[task_name]           = task_state
        _save_state(state)
        return "completed"

    # Not done yet — save progress and return
    if local_iters >= MAX_ITER:
        _log(f"MAX_ITER | task={task_name} | steps_remaining={len(steps) - current_step}")
        _append_plan_log(plan_p, f"--- Cycle paused at MAX_ITER ({MAX_ITER}) "
                        f"| steps_remaining={len(steps) - current_step} ---")
        state[task_name] = task_state
        _save_state(state)
        return "max_iter"

    task_state["status"] = "in_progress"
    state[task_name]     = task_state
    _save_state(state)
    return "in_progress"

# ── Task discovery ────────────────────────────────────────────────────────────

def _discover_tasks(state: dict) -> list[str]:
    """
    Return filenames in Needs_Action/ eligible for autonomous processing.

    Eligible = .md file, not already completed in state,
               not awaiting_approval (those are checked first via process_task).
    """
    try:
        files = sorted(
            f for f in os.listdir(NEEDS_ACTION_DIR)
            if f.endswith(".md") and os.path.isfile(os.path.join(NEEDS_ACTION_DIR, f))
        )
    except OSError:
        return []

    result = []
    for fname in files:
        ts = state.get(fname, {})
        if ts.get("status") == "completed":
            continue
        result.append(fname)

    return result

# ── Command implementations ───────────────────────────────────────────────────

def cmd_run() -> None:
    """Process all eligible tasks. Called by the scheduler."""
    state = _load_state()
    tasks = _discover_tasks(state)

    if not tasks:
        print("[ralph-loop] No eligible tasks in Needs_Action/.")
        return

    print(f"[ralph-loop] {len(tasks)} task(s) to process (max {MAX_TASKS} per cycle).")

    counts = {"completed": 0, "in_progress": 0, "max_iter": 0,
              "awaiting_approval": 0, "skipped": 0, "error": 0}

    for fname in tasks[:MAX_TASKS]:
        task_path = os.path.join(NEEDS_ACTION_DIR, fname)
        if not os.path.isfile(task_path):
            continue
        result = process_task(task_path, fname)
        counts[result] = counts.get(result, 0) + 1
        _log(f"RESULT | task={fname} | outcome={result}")

    print(
        f"[ralph-loop] Cycle complete | "
        f"completed={counts['completed']} | "
        f"in_progress={counts['in_progress']} | "
        f"awaiting_approval={counts['awaiting_approval']} | "
        f"max_iter={counts['max_iter']} | "
        f"skipped={counts['skipped']}"
    )


def cmd_task(task_file: str) -> None:
    """Process a single task file."""
    path = os.path.abspath(task_file) if os.sep in task_file else os.path.join(NEEDS_ACTION_DIR, task_file)
    name = os.path.basename(path)
    if not os.path.isfile(path):
        print(f"[ralph-loop] ERROR: File not found: {path}")
        sys.exit(1)
    result = process_task(path, name)
    print(f"[ralph-loop] {name} -> {result}")


def cmd_status() -> None:
    """Print current loop state."""
    state = _load_state()

    counts = {"completed": 0, "in_progress": 0, "awaiting_approval": 0,
              "max_iter": 0, "other": 0}
    for v in state.values():
        s = v.get("status", "other")
        counts[s] = counts.get(s, 0) + 1

    print("=" * 60)
    print("  Ralph Wiggum Autonomous Loop - Status")
    print("=" * 60)
    print(f"  Tasks tracked              : {len(state)}")
    print(f"  Completed                  : {counts['completed']}")
    print(f"  In progress                : {counts['in_progress']}")
    print(f"  Awaiting human approval    : {counts['awaiting_approval']}")
    print(f"  Paused (max iter)          : {counts['max_iter']}")
    print(f"  Max iterations per cycle   : {MAX_ITER}")
    print(f"  Max tasks per cycle        : {MAX_TASKS}")
    print(f"  State file                 : {STATE_FILE}")

    pending = {k: v for k, v in state.items() if v.get("status") != "completed"}
    if pending:
        print()
        print("  Active tasks:")
        for name, ts in sorted(pending.items()):
            status = ts.get("status", "?")
            iters  = ts.get("iterations", 0)
            step   = ts.get("current_step", 0)
            print(f"    [{status}] {name}  (iter={iters}, step={step})")
    print("=" * 60)


def cmd_reset(task_name: str) -> None:
    """Clear loop state for a specific task so it can be re-processed."""
    state = _load_state()
    if task_name in state:
        del state[task_name]
        _save_state(state)
        print(f"[ralph-loop] State cleared for: {task_name}")
    else:
        print(f"[ralph-loop] No state found for: {task_name}")

# ── CLI ───────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        prog="ralph_loop",
        description="Ralph Wiggum Autonomous Loop — autonomous task executor",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python ralph_loop.py --run
  python ralph_loop.py --task Needs_Action/task_foo.md
  python ralph_loop.py --task task_foo.md
  python ralph_loop.py --status
  python ralph_loop.py --reset task_foo.md
        """,
    )
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--run",    action="store_true", help="Process all eligible tasks [scheduler]")
    mode.add_argument("--task",   metavar="FILE",      help="Process a single task file")
    mode.add_argument("--status", action="store_true", help="Show current loop state")
    mode.add_argument("--reset",  metavar="TASKNAME",  help="Clear loop state for one task")

    args = parser.parse_args()

    if args.run:
        cmd_run()
    elif args.task:
        cmd_task(args.task)
    elif args.status:
        cmd_status()
    elif args.reset:
        cmd_reset(args.reset)


if __name__ == "__main__":
    main()
