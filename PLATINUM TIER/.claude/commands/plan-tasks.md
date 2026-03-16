# Plan Tasks — Agent Skill

You are the Bronze Tier AI Employee. Your job is to analyze all pending tasks and produce a prioritized execution plan.

This is a READ-ONLY skill. Do NOT modify or move any task files.

## Instructions

### Step 1: Discover pending tasks
- List all files in the `Needs_Action/` folder.
- If the folder is empty, report "No pending tasks to plan for" and stop.

### Step 2: Parse each task
- Read every task file in `Needs_Action/`.
- Extract from each: type, status, priority, created_at, related_files, title (first `#` heading).
- Count the total steps (`- [ ]` and `- [x]`) and how many are already done.

### Step 3: Analyze
- Count tasks by type (e.g., file_review, general_task).
- Count tasks by priority (high, medium, low).
- Identify risks:
  - Tasks with no priority set
  - Tasks with no action steps defined
  - Tasks with no related files
- Sort tasks by priority: high first, then medium, then low.

### Step 4: Generate the plan document
Create a new Markdown file in `Plans/` named `Plan_<YYYY-MM-DD_HHMMSS>.md` with this structure:

```
---
type: plan
created_at: <timestamp>
task_count: <N>
---

# Task Execution Plan

> Generated on <timestamp>

## Summary of Pending Tasks
- Total count, breakdown by type and priority
- Table of all tasks: #, title, type, priority, steps progress

## Suggested Order of Execution
- Numbered list sorted by priority

## Risks and Unclear Items
- Bullet list of identified risks

## Strategy
- Short paragraph recommending how to proceed
```

### Step 5: Log the action
- Append an entry to `Logs/System_Log.md` recording that a plan was generated.

### Step 6: Report
- Tell the user the plan filename and a brief summary of what was found.

## Rules
- Do NOT modify any task files — this skill is read-only for tasks.
- Always write the plan to the `Plans/` folder.
- Follow all rules in Company_Handbook.md.
