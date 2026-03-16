# Git Conflict Handling Guide

## Overview

This guide explains how to prevent and resolve Git merge conflicts in the Platinum Tier AI Employee vault synchronization system.

---

## Architecture

```
┌─────────────────────┐         ┌─────────────────────┐
│   Local Machine     │         │   Cloud/Server      │
│   (Manual Push)     │         │   (Auto Pull)       │
│                     │         │                     │
│   sync.bat push     │ ──────► │  Task Scheduler     │
│                     │   Git   │  (every 2 min)      │
│                     │ ◄────── │                     │
│                     │   Git   │  cloud_pull.bat     │
└─────────────────────┘         └─────────────────────┘
```

---

## Conflict Prevention Strategies

### 1. Directory Separation

| Directory | Sync Direction | Notes |
|-----------|---------------|-------|
| `Inbox/` | Local only | Ignored by Git |
| `Needs_Action/` | Local only | Ignored by Git |
| `Done/` | Local only | Ignored by Git |
| `Logs/` | Local only | Ignored by Git |
| `Plans/` | Local only | Ignored by Git |
| `scripts/` | Both ways | Code changes only |
| `*.py` | Both ways | Code changes only |
| `.env` | Never | Ignored by Git |

### 2. Workflow Rules

**Local Machine (Development):**
- Edit code files (`.py`, `.bat`, `.js`, `.md`)
- Push changes manually with `sync.bat push`
- Pull before pushing to avoid conflicts

**Cloud/Server (Production):**
- Receives changes via auto-pull every 2 minutes
- Never edit code directly on cloud
- Runtime data stays local (not synced)

### 3. Before Pushing (Local)

```cmd
REM Always pull first to get latest changes
sync.bat pull

REM Then push your changes
sync.bat push
```

### 4. Git Ignore Rules

The `.gitignore` file prevents these from being synced:
- `.env` - Environment variables with secrets
- `tokens/` - API tokens
- `sessions/` - Session data
- `Logs/` - Log files
- `Inbox/`, `Needs_Action/`, `Done/` - Task data
- `__pycache__/` - Python cache

---

## Conflict Resolution

### When Conflicts Occur

You'll see output like:
```
CONFLICT (content): Merge conflict in scripts/some_file.py
Automatic merge failed; fix conflicts and then commit the result.
```

### Step 1: Identify Conflicted Files

```cmd
REM Show all conflicted files
git status

REM Or use sync.bat
sync.bat status
```

### Step 2: View the Conflict

```cmd
REM See what's conflicting
git diff -- conflicted_file.py

REM Or open in editor
notepad conflicted_file.py
```

Conflict markers look like:
```python
<<<<<<< HEAD
# Your local version
def process_task():
    print("Local implementation")
=======
# Remote version (from cloud)
def process_task():
    print("Cloud implementation")
>>>>>>> origin/main
```

### Step 3: Choose Resolution Strategy

#### Option A: Accept Remote Version (Cloud is Source of Truth)

Use when cloud has the correct/updated version:

```cmd
git checkout --theirs conflicted_file.py
git add conflicted_file.py
```

#### Option B: Accept Local Version (Keep Your Changes)

Use when your local changes are correct:

```cmd
git checkout --ours conflicted_file.py
git add conflicted_file.py
```

#### Option C: Manual Merge

Edit the file to combine both versions:

```cmd
notepad conflicted_file.py
```

Remove the conflict markers and merge the code:

```python
# After manual merge
def process_task():
    print("Cloud implementation")  # Keep cloud version
    # Additional local enhancement
    log_action("Task processed")
```

Then mark as resolved:

```cmd
git add conflicted_file.py
```

### Step 4: Complete the Merge

```cmd
git commit -m "Resolved merge conflict in conflicted_file.py"
```

### Step 5: Verify

```cmd
sync.bat status
```

---

## Quick Resolution Commands

### Resolve All Conflicts (Prefer Remote)

```cmd
REM Auto-resolve all conflicts, preferring cloud version
call scripts\resolve_conflicts.bat

REM Then commit
git commit -m "Auto-resolved conflicts (preferred remote)"
```

### Abort and Retry

If the merge is too messy:

```cmd
REM Abort the current merge
git merge --abort

REM Pull fresh and try again
sync.bat pull
```

### Nuclear Option (Reset to Remote)

**WARNING: This discards all local changes!**

```cmd
REM Reset to match remote exactly
git fetch origin
git reset --hard origin/main

REM Clean untracked files (careful!)
git clean -fd
```

---

## Troubleshooting

### "Your branch is ahead/behind"

```cmd
REM See the difference
sync.bat status

REM Sync with remote
sync.bat sync
```

### "Permission denied (publickey)"

```cmd
REM For SSH remotes, ensure SSH key is loaded
ssh-add ~/.ssh/id_rsa

REM Or use HTTPS instead of SSH
git remote set-url origin https://github.com/user/repo.git
```

### "Changes would be overwritten by merge"

```cmd
REM Stash your changes first
git stash push -m "Backup before merge"

REM Then pull
sync.bat pull

REM Re-apply your changes
git stash pop
```

### Lock File Conflicts

If PM2 lock files cause issues:

```cmd
REM Remove stale lock files
del Logs\.scheduler.lock 2>nul
del Logs\.watcher_state.json 2>nul
```

---

## Best Practices

### 1. Commit Frequently

```cmd
REM Small, focused commits are easier to merge
git add scripts/specific_file.py
git commit -m "Fix: Specific bug in file_watcher.py"
```

### 2. Pull Before You Push

```cmd
REM Make this a habit
sync.bat pull
sync.bat push
```

### 3. Test After Sync

```cmd
REM After pulling, verify everything works
python scripts\run_ai_employee.py --status
```

### 4. Use Descriptive Messages

```cmd
REM Good
git commit -m "Fix: Handle missing Inbox folder gracefully"

REM Bad
git commit -m "update"
```

### 5. Backup Before Major Changes

```cmd
REM Create a backup branch
git branch backup-before-changes

REM Make your changes...

REM If something goes wrong, restore
git checkout backup-before-changes
```

---

## Command Reference

| Command | Description |
|---------|-------------|
| `sync.bat setup` | Initialize Git repository |
| `sync.bat pull` | Pull changes from remote |
| `sync.bat push` | Push changes to remote |
| `sync.bat sync` | Full sync (pull + push) |
| `sync.bat status` | Show Git status |
| `sync.bat conflicts` | Show conflict help |
| `git status` | Show detailed Git status |
| `git diff` | Show uncommitted changes |
| `git log --oneline` | Show recent commits |
| `git stash` | Temporarily save changes |
| `git checkout --theirs file` | Accept remote version |
| `git checkout --ours file` | Accept local version |
| `git merge --abort` | Cancel current merge |

---

## Emergency Contacts

If conflicts become unmanageable:

1. **Stop the auto-pull task** (on cloud):
   ```cmd
   schtasks /Delete /TN "PlatinumTierCloudPull" /F
   ```

2. **Backup current state**:
   ```cmd
   xcopy /E /I . ..\vault-backup
   ```

3. **Reset and re-sync**:
   ```cmd
   git fetch origin
   git reset --hard origin/main
   sync.bat status
   ```

4. **Re-enable auto-pull**:
   ```cmd
   scripts\setup_cloud_pull.bat
   ```
