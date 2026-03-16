"""
cloud_worker.py — Cloud Zone Worker

Cloud Responsibilities:
  - Email triage (read and categorize incoming emails)
  - Draft replies (create email drafts, never send)
  - Draft social posts (create content, never post)
  - Write approval files only (in Pending_Approval/)

Cloud NEVER:
  - Sends emails directly
  - Posts to social media
  - Makes payments
  - Modifies Dashboard.md directly (uses write queue)

Work Zone Rules:
  - Claim-by-Move: Move task to In_Progress/cloud/ to claim
  - Single-Writer: Dashboard writes go to queue for Local
  - Complete-by-Move: Move to Approved/ when done

Usage:
    python scripts/cloud_worker.py --daemon
    python scripts/cloud_worker.py --once
"""

import os
import shutil
import json
import argparse
import time
from datetime import datetime, timezone
from pathlib import Path


# ============================================================================
# Configuration
# ============================================================================

SCRIPT_DIR = Path(__file__).parent
VAULT_ROOT = SCRIPT_DIR.parent

# Work Zone Folders
NEEDS_ACTION = VAULT_ROOT / "Needs_Action"
PENDING_APPROVAL = VAULT_ROOT / "Pending_Approval"
IN_PROGRESS_CLOUD = VAULT_ROOT / "In_Progress" / "cloud"
IN_PROGRESS_LOCAL = VAULT_ROOT / "In_Progress" / "local"
APPROVED = VAULT_ROOT / "Approved"
LOGS_DIR = VAULT_ROOT / "Logs"

# Dashboard write queue (Local is single writer)
DASHBOARD_QUEUE = VAULT_ROOT / "In_Progress" / "local" / ".dashboard_queue.json"
ZONE_LOCK = VAULT_ROOT / "In_Progress" / ".zone_lock"

# Poll interval for daemon mode
POLL_INTERVAL = 30  # seconds

# Ensure directories exist
for d in [NEEDS_ACTION, PENDING_APPROVAL, IN_PROGRESS_CLOUD, 
          IN_PROGRESS_LOCAL, APPROVED, LOGS_DIR]:
    d.mkdir(parents=True, exist_ok=True)


# ============================================================================
# Logging
# ============================================================================

def log(message, level="INFO"):
    """Log to console and cloud_worker.log"""
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    entry = f"[{timestamp}] [{level}] {message}"
    print(entry)
    
    log_file = LOGS_DIR / "cloud_worker.log"
    try:
        with open(log_file, "a", encoding="utf-8") as f:
            f.write(entry + "\n")
    except OSError:
        pass


# ============================================================================
# Zone Locking (Claim-by-Move Rule)
# ============================================================================

def acquire_zone_lock(task_id):
    """
    Acquire a lock for processing a specific task.
    Returns True if lock acquired, False if already claimed.
    """
    try:
        if ZONE_LOCK.exists():
            with open(ZONE_LOCK, "r", encoding="utf-8") as f:
                locks = json.load(f)
        else:
            locks = {}
        
        if task_id in locks:
            # Check if lock is stale (older than 5 minutes)
            lock_time = locks[task_id].get("time", "")
            if lock_time:
                lock_dt = datetime.fromisoformat(lock_time.replace(" UTC", "+00:00"))
                age = (datetime.now(timezone.utc) - lock_dt).total_seconds()
                if age < 300:  # 5 minutes
                    return False
        
        # Acquire lock
        locks[task_id] = {
            "zone": "cloud",
            "time": datetime.now(timezone.utc).isoformat() + " UTC"
        }
        
        with open(ZONE_LOCK, "w", encoding="utf-8") as f:
            json.dump(locks, f, indent=2)
        
        return True
    except Exception as e:
        log(f"Lock acquisition error: {e}", "ERROR")
        return False


def release_zone_lock(task_id):
    """Release the lock for a task"""
    try:
        if ZONE_LOCK.exists():
            with open(ZONE_LOCK, "r", encoding="utf-8") as f:
                locks = json.load(f)
            
            if task_id in locks:
                del locks[task_id]
            
            with open(ZONE_LOCK, "w", encoding="utf-8") as f:
                json.dump(locks, f, indent=2)
    except Exception as e:
        log(f"Lock release error: {e}", "ERROR")


# ============================================================================
# Dashboard Write Queue (Single-Writer Rule)
# ============================================================================

def queue_dashboard_write(action_type, details):
    """
    Queue a dashboard update for Local to process.
    Cloud NEVER writes to Dashboard.md directly.
    """
    try:
        queue = []
        if DASHBOARD_QUEUE.exists():
            with open(DASHBOARD_QUEUE, "r", encoding="utf-8") as f:
                queue = json.load(f)
        
        queue.append({
            "timestamp": datetime.now(timezone.utc).isoformat() + " UTC",
            "zone": "cloud",
            "action": action_type,
            "details": details
        })
        
        with open(DASHBOARD_QUEUE, "w", encoding="utf-8") as f:
            json.dump(queue, f, indent=2)
        
        log(f"Queued dashboard update: {action_type}")
        return True
    except Exception as e:
        log(f"Dashboard queue error: {e}", "ERROR")
        return False


# ============================================================================
# Task Processing
# ============================================================================

def get_task_files():
    """Get all task files from Needs_Action subdirectories"""
    tasks = []
    for subdir in ["email", "social", "general"]:
        src_dir = NEEDS_ACTION / subdir
        if src_dir.exists():
            for f in src_dir.glob("*.md"):
                tasks.append((f, subdir))
    return tasks


def claim_task(task_path, channel):
    """
    Claim a task by moving it to In_Progress/cloud/
    Implements the Claim-by-Move rule.
    """
    task_id = task_path.stem
    
    # Check if already claimed
    if not acquire_zone_lock(task_id):
        log(f"Task {task_id} already claimed", "WARN")
        return None
    
    # Move to cloud work zone
    dest = IN_PROGRESS_CLOUD / task_path.name
    try:
        shutil.move(str(task_path), str(dest))
        log(f"Claimed task: {task_path.name} (channel: {channel})")
        return dest
    except Exception as e:
        log(f"Failed to claim task: {e}", "ERROR")
        release_zone_lock(task_id)
        return None


def process_email_task(task_path):
    """
    Process an email task:
    1. Read and triage the email
    2. Draft a reply (if needed)
    3. Create approval file in Pending_Approval/email/
    """
    log(f"Processing email task: {task_path.name}")
    
    try:
        with open(task_path, "r", encoding="utf-8") as f:
            content = f.read()
        
        # Extract email details from task
        email_data = parse_email_task(content)
        
        # Triage: categorize the email
        category = triage_email(email_data)
        log(f"Email triaged as: {category}")
        
        # Draft reply if needed
        draft_reply = None
        if category in ["inquiry", "support", "business"]:
            draft_reply = draft_email_reply(email_data, category)
            log(f"Drafted reply for email")
        
        # Create approval file
        approval_path = create_approval_file(
            task_path.name,
            "email",
            email_data,
            draft_reply,
            category
        )
        
        # Queue dashboard update
        queue_dashboard_write("email_processed", {
            "task": task_path.name,
            "category": category,
            "draft_created": draft_reply is not None
        })
        
        # Move original task to Approved
        approved_path = APPROVED / "email" / task_path.name
        approved_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(task_path), str(approved_path))
        
        log(f"Email task completed: {task_path.name}")
        return True
        
    except Exception as e:
        log(f"Email processing error: {e}", "ERROR")
        return False


def process_social_task(task_path):
    """
    Process a social media task:
    1. Read the social post request
    2. Draft the post content
    3. Create approval file in Pending_Approval/social/
    """
    log(f"Processing social task: {task_path.name}")
    
    try:
        with open(task_path, "r", encoding="utf-8") as f:
            content = f.read()
        
        # Extract social post details
        social_data = parse_social_task(content)
        
        # Draft the social post
        draft_post = draft_social_post(social_data)
        log(f"Drafted social post")
        
        # Create approval file
        approval_path = create_approval_file(
            task_path.name,
            "social",
            social_data,
            draft_post,
            social_data.get("platform", "general")
        )
        
        # Queue dashboard update
        queue_dashboard_write("social_processed", {
            "task": task_path.name,
            "platform": social_data.get("platform", "general"),
            "draft_created": True
        })
        
        # Move original task to Approved
        approved_path = APPROVED / "social" / task_path.name
        approved_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(task_path), str(approved_path))
        
        log(f"Social task completed: {task_path.name}")
        return True
        
    except Exception as e:
        log(f"Social processing error: {e}", "ERROR")
        return False


def process_general_task(task_path):
    """Process a general task"""
    log(f"Processing general task: {task_path.name}")
    
    try:
        with open(task_path, "r", encoding="utf-8") as f:
            content = f.read()
        
        # Create approval file for general tasks
        approval_path = create_approval_file(
            task_path.name,
            "general",
            {"content": content},
            None,
            "general"
        )
        
        # Queue dashboard update
        queue_dashboard_write("general_processed", {
            "task": task_path.name
        })
        
        # Move to Approved
        approved_path = APPROVED / "general" / task_path.name
        approved_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(task_path), str(approved_path))
        
        log(f"General task completed: {task_path.name}")
        return True
        
    except Exception as e:
        log(f"General processing error: {e}", "ERROR")
        return False


# ============================================================================
# Email Processing Helpers
# ============================================================================

def parse_email_task(content):
    """Parse email task content"""
    data = {
        "from": "",
        "subject": "",
        "body": "",
        "received": ""
    }
    
    # Try to extract from front matter
    if "---" in content:
        parts = content.split("---")
        if len(parts) >= 3:
            front_matter = parts[1]
            for line in front_matter.split("\n"):
                if ":" in line:
                    key, value = line.split(":", 1)
                    key = key.strip().lower()
                    if key in data:
                        data[key] = value.strip().strip('"')
    
    # Extract body (after front matter)
    if len(parts) >= 3:
        data["body"] = parts[2].strip()
    
    return data


def triage_email(email_data):
    """Categorize email by type"""
    subject = email_data.get("subject", "").lower()
    body = email_data.get("body", "").lower()
    
    # Priority keywords
    if any(w in subject for w in ["urgent", "asap", "emergency"]):
        return "urgent"
    
    # Business keywords
    if any(w in subject for w in ["proposal", "contract", "invoice", "payment"]):
        return "business"
    
    # Support keywords
    if any(w in subject for w in ["help", "support", "issue", "problem", "bug"]):
        return "support"
    
    # Inquiry keywords
    if any(w in subject for w in ["question", "inquiry", "info", "pricing"]):
        return "inquiry"
    
    # Spam indicators
    if any(w in subject for w in ["winner", "lottery", "congratulations"]):
        return "spam"
    
    return "other"


def draft_email_reply(email_data, category):
    """Draft a reply email"""
    subject = email_data.get("subject", "")
    
    # Generate appropriate reply based on category
    if category == "urgent":
        return f"""---
type: email_draft
status: pending_approval
priority: high
---

Subject: Re: {subject}

Dear Sender,

Thank you for your urgent message. We have received your communication and 
are treating it as high priority.

A team member will respond with a detailed resolution shortly.

Best regards,
AI Employee
"""
    
    elif category == "support":
        return f"""---
type: email_draft
status: pending_approval
priority: medium
---

Subject: Re: {subject}

Dear Sender,

Thank you for contacting support. We have received your request and are 
looking into the issue you've described.

We will provide a solution or update within 24 hours.

Best regards,
AI Employee
"""
    
    elif category == "inquiry":
        return f"""---
type: email_draft
status: pending_approval
priority: medium
---

Subject: Re: {subject}

Dear Sender,

Thank you for your inquiry. We appreciate your interest and would be happy 
to provide you with the information you need.

Please find the details below, and feel free to reach out if you have 
any additional questions.

Best regards,
AI Employee
"""
    
    elif category == "business":
        return f"""---
type: email_draft
status: pending_approval
priority: medium
---

Subject: Re: {subject}

Dear Sender,

Thank you for your business communication. We have received your message 
and are reviewing the details.

We will respond with a comprehensive reply shortly.

Best regards,
AI Employee
"""
    
    return None


# ============================================================================
# Social Media Processing Helpers
# ============================================================================

def parse_social_task(content):
    """Parse social media task content"""
    data = {
        "platform": "general",
        "topic": "",
        "content": "",
        "tone": "professional"
    }
    
    if "---" in content:
        parts = content.split("---")
        if len(parts) >= 3:
            front_matter = parts[1]
            for line in front_matter.split("\n"):
                if ":" in line:
                    key, value = line.split(":", 1)
                    key = key.strip().lower()
                    if key in data:
                        data[key] = value.strip().strip('"')
    
    return data


def draft_social_post(social_data):
    """Draft a social media post"""
    platform = social_data.get("platform", "general")
    topic = social_data.get("topic", "")
    tone = social_data.get("tone", "professional")
    
    # Platform-specific drafting
    if platform.lower() == "linkedin":
        return f"""---
type: social_draft
platform: linkedin
status: pending_approval
---

# LinkedIn Post Draft

**Topic:** {topic}

**Tone:** {tone}

---

🔹 Professional update related to: {topic}

Key points to cover:
• Industry insight or trend
• Value proposition
• Call to action

#Professional #Industry

---
[Ready for Local review and posting]
"""
    
    elif platform.lower() == "twitter":
        return f"""---
type: social_draft
platform: twitter
status: pending_approval
---

# Twitter Post Draft

**Topic:** {topic}

---

📌 Tweet about {topic}

Keeping it concise and engaging...

#Relevant #Hashtags

---
[Ready for Local review and posting]
"""
    
    else:
        return f"""---
type: social_draft
platform: {platform}
status: pending_approval
---

# Social Post Draft

**Platform:** {platform}
**Topic:** {topic}

---

Content draft for {topic}...

---
[Ready for Local review and posting]
"""


# ============================================================================
# Approval File Creation
# ============================================================================

def create_approval_file(task_name, channel, data, draft, category):
    """
    Create an approval file in Pending_Approval/{channel}/
    This is the ONLY write operation Cloud performs.
    """
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    
    approval_name = f"approval_{task_name}"
    approval_path = PENDING_APPROVAL / channel / approval_name
    approval_path.parent.mkdir(parents=True, exist_ok=True)
    
    content = f"""---
type: approval_request
channel: {channel}
category: {category}
created_at: {timestamp}
source_task: {task_name}
zone: cloud
status: pending
---

# Approval Request

**Channel:** {channel}
**Category:** {category}
**Created:** {timestamp}

---

## Summary

Automated processing completed by Cloud zone.
Human approval required for final action.

---

## Draft Content

{draft if draft else "No draft - action only"}

---

## Required Action

- [ ] Review the draft/content above
- [ ] Approve or reject
- [ ] Local zone will execute final action

---

## Metadata

```json
{json.dumps(data, indent=2)}
```

---

*This file was auto-generated by cloud_worker.py*
*Move to Approved/{channel}/ after approval*
"""
    
    with open(approval_path, "w", encoding="utf-8") as f:
        f.write(content)
    
    log(f"Created approval file: {approval_name}")
    return approval_path


# ============================================================================
# Main Processing Loop
# ============================================================================

def process_cycle():
    """Run one processing cycle"""
    log("--- Processing cycle started ---")
    
    tasks_processed = 0
    
    for task_path, channel in get_task_files():
        task_id = task_path.stem
        
        # Claim the task (move to cloud zone)
        claimed_path = claim_task(task_path, channel)
        if not claimed_path:
            continue
        
        # Process based on channel
        success = False
        if channel == "email":
            success = process_email_task(claimed_path)
        elif channel == "social":
            success = process_social_task(claimed_path)
        else:
            success = process_general_task(claimed_path)
        
        # Release lock
        release_zone_lock(task_id)
        
        if success:
            tasks_processed += 1
    
    log(f"--- Processing cycle finished ({tasks_processed} tasks) ---")
    return tasks_processed


def run_daemon():
    """Run in daemon mode"""
    log("=" * 50)
    print("  Cloud Zone Worker - Daemon Mode")
    print("=" * 50)
    print(f"  Poll Interval: {POLL_INTERVAL}s")
    print(f"  Zone: In_Progress/cloud/")
    print("=" * 50)
    
    try:
        while True:
            process_cycle()
            time.sleep(POLL_INTERVAL)
    except KeyboardInterrupt:
        log("Daemon stopped by user")


def run_once():
    """Run single cycle"""
    log("=" * 50)
    print("  Cloud Zone Worker - Single Run")
    print("=" * 50)
    
    process_cycle()


# ============================================================================
# Entry Point
# ============================================================================

def main():
    parser = argparse.ArgumentParser(description="Cloud Zone Worker")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--daemon", action="store_true", help="Run continuously")
    group.add_argument("--once", action="store_true", help="Run single cycle")
    args = parser.parse_args()
    
    if args.daemon:
        run_daemon()
    else:
        run_once()


if __name__ == "__main__":
    main()
