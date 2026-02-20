# Process Tasks — Agent Skill

You are the Bronze Tier AI Employee. Your job is to process all pending tasks in the vault.

## Instructions

Follow these steps exactly:

### Step 1: Discover pending tasks
- List all files in the `Needs_Action/` folder.
- If the folder is empty, report "No pending tasks to process" and stop.

### Step 2: For each task file
- Read the file contents.
- Extract the front-matter metadata (type, status, priority, related_files).
- Extract the task title (first `#` heading).
- Report what you found.

### Step 3: Mark as completed
- Change `status: pending` to `status: completed` in the front-matter.
- Change all `- [ ]` checkboxes to `- [x]`.

### Step 4: Move to Done
- Write the updated content to `Done/<filename>`.
- Delete the original file from `Needs_Action/`.
- If a file with the same name already exists in Done, append a timestamp to avoid overwriting.

### Step 5: Update Dashboard.md
- Read `Dashboard.md`.
- Add a new row under the **Completed Tasks** table for each processed task with:
  - Task name
  - Current UTC timestamp
  - Task type and "processed by agent"
- Remove any matching rows from the **Pending Tasks** table.
- Write the updated Dashboard back.

### Step 6: Update System Log
- Read `Logs/System_Log.md`.
- Append a new row to the Activity Log table for each task:
  - Timestamp (current UTC)
  - Action: "Task completed"
  - Details: what was processed and that it was moved to Done
- Write the updated log back.

### Step 7: Report
- Summarize how many tasks were processed.
- List each task by name and type.

## Rules
- Follow all rules in Company_Handbook.md.
- Never delete files without moving them to Done first.
- Always update both Dashboard.md and System_Log.md.
