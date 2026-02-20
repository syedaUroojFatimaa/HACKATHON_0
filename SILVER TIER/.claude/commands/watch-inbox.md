# Watch Inbox — Agent Skill

You are the Bronze Tier AI Employee. Your job is to start the file system watcher that monitors the Inbox folder for new files.

## Instructions

### Step 1: Verify the environment
- Check that `file_watcher.py` exists in the project root.
- Check that the `Inbox/`, `Needs_Action/`, and `Logs/` folders exist.
- If any folder is missing, create it.

### Step 2: Start the watcher
- Run `python file_watcher.py` in the background.
- The watcher polls `Inbox/` every 5 seconds for new files.
- When a new file is detected, it automatically creates a structured task file in `Needs_Action/`.

### Step 3: Report
- Confirm that the watcher has started.
- Tell the user:
  - Drop files into `Inbox/` to trigger task creation.
  - Run `/process-tasks` to process tasks after they are created.
  - The watcher runs until manually stopped.

### Step 4: Log the action
- Append an entry to `Logs/System_Log.md` recording that the watcher was started.

## Rules
- Follow all rules in Company_Handbook.md.
- The watcher should run as a background process so the user can continue working.
