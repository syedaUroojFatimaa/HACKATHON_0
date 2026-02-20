# Rotate Logs — Agent Skill

You are the Bronze Tier AI Employee. Your job is to check log file sizes and rotate any that have grown too large.

## Instructions

### Step 1: Check log files
Inspect the following files in `Logs/`:
- `System_Log.md`
- `watcher_errors.log` (may not exist — that's fine, skip it)

For each file that exists, check its size.

### Step 2: Decide whether to rotate
- The size limit is **1 MB** (1,048,576 bytes).
- If a file is under the limit, report it as OK and skip it.
- If a file exceeds the limit, rotate it.

### Step 3: Rotate oversized files
To rotate a file:
1. Read its current contents.
2. Write those contents to an archive file named `<original_name>_<YYYY-MM-DD>.<ext>` in the same `Logs/` folder.
3. Replace the original file with a fresh header:
   - For `System_Log.md`: recreate with the standard header, table headings, and an empty table.
   - For `watcher_errors.log`: recreate with just `# Watcher Error Log`.
4. If an archive with the same date already exists, append `_2`, `_3`, etc.

### Step 4: Report
- List each log file checked, its size, and whether it was rotated or OK.
- If any files were rotated, mention the archive filenames.

### Step 5: Log the action
- If any rotation happened, append an entry to the (now fresh) `Logs/System_Log.md`.

## Rules
- Follow all rules in Company_Handbook.md.
- Never delete log data — always archive before replacing.
