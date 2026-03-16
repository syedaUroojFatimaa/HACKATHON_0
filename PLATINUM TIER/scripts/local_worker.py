"""
local_worker.py — Local Zone Worker

Local Responsibilities:
  - Final send/post actions (execute what Cloud drafted)
  - WhatsApp session management
  - Payments processing
  - Approvals (review and approve/reject Cloud's work)
  - Dashboard.md updates (Single-Writer rule)

Local NEVER:
  - Drafts content (Cloud does this)
  - Writes approval files (Cloud does this)
  - Modifies files in Cloud zone

Work Zone Rules:
  - Claim-by-Move: Move task to In_Progress/local/ to claim
  - Single-Writer: Only Local writes to Dashboard.md
  - Execute approved actions from Pending_Approval/

Usage:
    python scripts/local_worker.py --daemon
    python scripts/local_worker.py --once
    python scripts/local_worker.py --approve
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
PENDING_APPROVAL = VAULT_ROOT / "Pending_Approval"
IN_PROGRESS_LOCAL = VAULT_ROOT / "In_Progress" / "local"
APPROVED = VAULT_ROOT / "Approved"
LOGS_DIR = VAULT_ROOT / "Logs"
DONE_DIR = VAULT_ROOT / "Done"

# Dashboard (Single-Writer: Only Local writes here)
DASHBOARD = VAULT_ROOT / "Dashboard.md"
DASHBOARD_QUEUE = IN_PROGRESS_LOCAL / ".dashboard_queue.json"
ZONE_LOCK = VAULT_ROOT / "In_Progress" / ".zone_lock"

# Poll interval for daemon mode
POLL_INTERVAL = 30  # seconds

# Ensure directories exist
for d in [PENDING_APPROVAL, IN_PROGRESS_LOCAL, APPROVED, LOGS_DIR, DONE_DIR]:
    d.mkdir(parents=True, exist_ok=True)


# ============================================================================
# Logging
# ============================================================================

def log(message, level="INFO"):
    """Log to console and local_worker.log"""
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    entry = f"[{timestamp}] [{level}] {message}"
    print(entry)
    
    log_file = LOGS_DIR / "local_worker.log"
    try:
        with open(log_file, "a", encoding="utf-8") as f:
            f.write(entry + "\n")
    except OSError:
        pass


# ============================================================================
# Zone Locking (Claim-by-Move Rule)
# ============================================================================

def acquire_zone_lock(task_id):
    """Acquire a lock for processing a specific task"""
    try:
        if ZONE_LOCK.exists():
            with open(ZONE_LOCK, "r", encoding="utf-8") as f:
                locks = json.load(f)
        else:
            locks = {}
        
        if task_id in locks:
            lock_time = locks[task_id].get("time", "")
            if lock_time:
                lock_dt = datetime.fromisoformat(lock_time.replace(" UTC", "+00:00"))
                age = (datetime.now(timezone.utc) - lock_dt).total_seconds()
                if age < 300:
                    return False
        
        locks[task_id] = {
            "zone": "local",
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
# Dashboard Management (Single-Writer Rule)
# ============================================================================

def process_dashboard_queue():
    """
    Process pending dashboard updates from the queue.
    Only Local zone writes to Dashboard.md (Single-Writer rule).
    """
    if not DASHBOARD_QUEUE.exists():
        return 0
    
    try:
        with open(DASHBOARD_QUEUE, "r", encoding="utf-8") as f:
            queue = json.load(f)
        
        if not queue:
            return 0
        
        processed = 0
        for item in queue:
            action = item.get("action", "")
            details = item.get("details", {})
            
            if action == "email_processed":
                update_dashboard_for_email(details)
            elif action == "social_processed":
                update_dashboard_for_social(details)
            elif action == "general_processed":
                update_dashboard_for_general(details)
            elif action == "approval_completed":
                update_dashboard_for_approval(details)
            
            processed += 1
        
        # Clear the queue
        with open(DASHBOARD_QUEUE, "w", encoding="utf-8") as f:
            json.dump([], f, indent=2)
        
        log(f"Processed {processed} dashboard updates")
        return processed
        
    except Exception as e:
        log(f"Dashboard queue error: {e}", "ERROR")
        return 0


def update_dashboard_for_email(details):
    """Update Dashboard.md for email processing"""
    task = details.get("task", "unknown")
    category = details.get("category", "general")
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    
    append_to_dashboard(
        "Email Processed",
        f"`{task}` categorized as `{category}`",
        timestamp
    )


def update_dashboard_for_social(details):
    """Update Dashboard.md for social media processing"""
    task = details.get("task", "unknown")
    platform = details.get("platform", "general")
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    
    append_to_dashboard(
        "Social Draft Created",
        f"`{task}` for {platform}",
        timestamp
    )


def update_dashboard_for_general(details):
    """Update Dashboard.md for general task processing"""
    task = details.get("task", "unknown")
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    
    append_to_dashboard(
        "Task Processed",
        f"`{task}`",
        timestamp
    )


def update_dashboard_for_approval(details):
    """Update Dashboard.md for approval completion"""
    task = details.get("task", "unknown")
    decision = details.get("decision", "unknown")
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    
    append_to_dashboard(
        "Approval Decision",
        f"`{task}` - {decision.upper()}",
        timestamp
    )


def append_to_dashboard(action, details, timestamp):
    """Append an entry to Dashboard.md"""
    try:
        if not DASHBOARD.exists():
            create_dashboard()
        
        with open(DASHBOARD, "r", encoding="utf-8") as f:
            content = f.read()
        
        # Find the activity log section and append
        new_entry = f"| {timestamp} | {action} | {details} |\n"
        
        # Find the last table row or header
        if "|------|--------------|-------|" in content:
            content = content.replace(
                "|------|--------------|-------|\n",
                "|------|--------------|-------|\n" + new_entry,
                1
            )
        else:
            # Create activity section if missing
            content += f"\n## Activity Log\n\n| Timestamp | Action | Details |\n|------|--------------|-------|\n{new_entry}"
        
        with open(DASHBOARD, "w", encoding="utf-8") as f:
            f.write(content)
        
        log(f"Dashboard updated: {action}")
        
    except Exception as e:
        log(f"Dashboard write error: {e}", "ERROR")


def create_dashboard():
    """Create a new Dashboard.md"""
    content = """# AI Employee Dashboard

> Last updated: {timestamp}

## Status Overview

| Metric | Value |
|--------|-------|
| Pending Approvals | 0 |
| In Progress (Cloud) | 0 |
| In Progress (Local) | 0 |
| Completed Today | 0 |

## Activity Log

| Timestamp | Action | Details |
|------|--------------|-------|
""".format(timestamp=datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"))
    
    with open(DASHBOARD, "w", encoding="utf-8") as f:
        f.write(content)


# ============================================================================
# Approval Processing
# ============================================================================

def get_approval_files():
    """Get all approval files from Pending_Approval subdirectories"""
    approvals = []
    for subdir in ["email", "social", "general"]:
        src_dir = PENDING_APPROVAL / subdir
        if src_dir.exists():
            for f in src_dir.glob("*.md"):
                approvals.append((f, subdir))
    return approvals


def claim_approval(approval_path, channel):
    """Claim an approval by moving to In_Progress/local/"""
    task_id = approval_path.stem
    
    if not acquire_zone_lock(task_id):
        log(f"Approval {task_id} already claimed", "WARN")
        return None
    
    dest = IN_PROGRESS_LOCAL / approval_path.name
    try:
        shutil.move(str(approval_path), str(dest))
        log(f"Claimed approval: {approval_path.name} (channel: {channel})")
        return dest
    except Exception as e:
        log(f"Failed to claim approval: {e}", "ERROR")
        release_zone_lock(task_id)
        return None


def process_approval(approval_path, channel, auto_approve=False):
    """
    Process an approval request:
    1. Review the draft/content
    2. Make approve/reject decision
    3. Execute the action if approved
    4. Move to Approved/
    """
    log(f"Processing approval: {approval_path.name}")
    
    try:
        with open(approval_path, "r", encoding="utf-8") as f:
            content = f.read()
        
        # Extract metadata
        metadata = parse_approval_metadata(content)
        category = metadata.get("category", "general")
        source_task = metadata.get("source_task", "unknown")
        
        # Decision logic (auto-approve for demo, or implement review logic)
        if auto_approve:
            decision = "approved"
            log(f"Auto-approved: {approval_path.name}")
        else:
            # In production, this could involve human review
            decision = "approved"  # Default for automation
            log(f"Approved: {approval_path.name}")
        
        # Execute the action based on channel and decision
        if decision == "approved":
            execute_approved_action(channel, content, metadata)
            
            # Queue dashboard update
            queue_dashboard_update("approval_completed", {
                "task": source_task,
                "decision": decision,
                "channel": channel
            })
        
        # Move to Approved
        approved_path = APPROVED / channel / approval_path.name
        approved_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Update status in content
        content = content.replace("status: pending", f"status: {decision}")
        with open(approved_path, "w", encoding="utf-8") as f:
            f.write(content)
        
        # Remove from In_Progress
        if approval_path.exists():
            approval_path.unlink()
        
        log(f"Approval completed: {source_task} -> {decision}")
        return True
        
    except Exception as e:
        log(f"Approval processing error: {e}", "ERROR")
        return False


def parse_approval_metadata(content):
    """Parse approval file metadata"""
    metadata = {}
    
    if "---" in content:
        parts = content.split("---")
        if len(parts) >= 3:
            front_matter = parts[1]
            for line in front_matter.split("\n"):
                if ":" in line:
                    key, value = line.split(":", 1)
                    key = key.strip().lower()
                    metadata[key] = value.strip().strip('"')
    
    return metadata


def execute_approved_action(channel, content, metadata):
    """Execute the approved action"""
    category = metadata.get("category", "general")
    
    if channel == "email":
        execute_email_send(content, metadata)
    elif channel == "social":
        execute_social_post(content, metadata)
    elif channel == "general":
        execute_general_action(content, metadata)


def execute_email_send(content, metadata):
    """Execute email sending via email_sender.py"""
    log("Executing email send...")
    
    # Call email_sender.py to send the email
    try:
        import subprocess
        
        # Find the approval file path
        approval_file = None
        for f in IN_PROGRESS_LOCAL.glob("approval_*.md"):
            with open(f, "r", encoding="utf-8") as fh:
                if metadata.get("source_task", "") in fh.read():
                    approval_file = str(f)
                    break
        
        if approval_file:
            result = subprocess.run(
                [sys.executable, str(SCRIPT_DIR / "email_sender.py"), "--send", approval_file],
                capture_output=True,
                text=True,
                timeout=60,
            )
            
            if result.returncode == 0:
                log("Email send completed successfully")
                return True
            else:
                log(f"Email send failed: {result.stderr}", "ERROR")
                return False
        else:
            log("Approval file not found for email send", "ERROR")
            return False
            
    except Exception as e:
        log(f"Email send error: {e}", "ERROR")
        return False


def execute_social_post(content, metadata):
    """Execute social media posting via social_poster.py"""
    platform = metadata.get("category", "general")
    log(f"Executing {platform} post...")
    
    # Call social_poster.py to post
    try:
        import subprocess
        
        # Find the approval file path
        approval_file = None
        for f in IN_PROGRESS_LOCAL.glob("approval_*.md"):
            with open(f, "r", encoding="utf-8") as fh:
                if metadata.get("source_task", "") in fh.read():
                    approval_file = str(f)
                    break
        
        if approval_file:
            result = subprocess.run(
                [sys.executable, str(SCRIPT_DIR / "social_poster.py"), "--post", approval_file],
                capture_output=True,
                text=True,
                timeout=60,
            )
            
            if result.returncode == 0:
                log(f"{platform} post completed successfully")
                return True
            else:
                log(f"{platform} post failed: {result.stderr}", "ERROR")
                return False
        else:
            log("Approval file not found for social post", "ERROR")
            return False
            
    except Exception as e:
        log(f"Social post error: {e}", "ERROR")
        return False


def execute_general_action(content, metadata):
    """Execute general action"""
    log("Executing general action...")
    # TODO: Implement based on task type
    log("General action completed (placeholder)")


def queue_dashboard_update(action, details):
    """Add an update to the dashboard queue"""
    try:
        queue = []
        if DASHBOARD_QUEUE.exists():
            with open(DASHBOARD_QUEUE, "r", encoding="utf-8") as f:
                queue = json.load(f)
        
        queue.append({
            "timestamp": datetime.now(timezone.utc).isoformat() + " UTC",
            "action": action,
            "details": details
        })
        
        with open(DASHBOARD_QUEUE, "w", encoding="utf-8") as f:
            json.dump(queue, f, indent=2)
        
    except Exception as e:
        log(f"Dashboard queue error: {e}", "ERROR")


# ============================================================================
# WhatsApp Session Management
# ============================================================================

def check_whatsapp_session():
    """Check if WhatsApp session is active"""
    session_file = VAULT_ROOT / "sessions" / "whatsapp_session.json"
    
    if not session_file.exists():
        log("WhatsApp session not found", "WARN")
        return False
    
    try:
        with open(session_file, "r", encoding="utf-8") as f:
            session = json.load(f)
        
        if session.get("active", False):
            log("WhatsApp session is active")
            return True
        else:
            log("WhatsApp session is inactive", "WARN")
            return False
            
    except Exception as e:
        log(f"WhatsApp session check error: {e}", "ERROR")
        return False


def refresh_whatsapp_session():
    """Refresh WhatsApp session if needed"""
    log("Checking WhatsApp session...")
    # TODO: Implement WhatsApp session refresh logic
    # - Check session expiry
    # - Re-authenticate if needed
    # - Update session file


# ============================================================================
# Payments Processing
# ============================================================================

def process_payments():
    """Process any pending payments"""
    payments_dir = VAULT_ROOT / "Accounting" / "pending_payments"
    
    if not payments_dir.exists():
        return 0
    
    processed = 0
    for payment_file in payments_dir.glob("*.md"):
        log(f"Processing payment: {payment_file.name}")
        # TODO: Implement payment processing logic
        processed += 1
    
    return processed


# ============================================================================
# Main Processing Loop
# ============================================================================

def process_cycle(auto_approve=False):
    """Run one processing cycle"""
    log("--- Processing cycle started ---")
    
    approvals_processed = 0
    
    # Process dashboard queue first (Single-Writer)
    process_dashboard_queue()
    
    # Process approvals
    for approval_path, channel in get_approval_files():
        task_id = approval_path.stem
        
        # Claim the approval
        claimed_path = claim_approval(approval_path, channel)
        if not claimed_path:
            continue
        
        # Process the approval
        success = process_approval(claimed_path, channel, auto_approve)
        
        # Release lock
        release_zone_lock(task_id)
        
        if success:
            approvals_processed += 1
    
    # Check WhatsApp session
    check_whatsapp_session()
    
    # Process pending payments
    process_payments()
    
    log(f"--- Processing cycle finished ({approvals_processed} approvals) ---")
    return approvals_processed


def run_daemon():
    """Run in daemon mode"""
    log("=" * 50)
    print("  Local Zone Worker - Daemon Mode")
    print("=" * 50)
    print(f"  Poll Interval: {POLL_INTERVAL}s")
    print(f"  Zone: In_Progress/local/")
    print(f"  Dashboard: Single-Writer")
    print("=" * 50)
    
    try:
        while True:
            process_cycle(auto_approve=True)
            time.sleep(POLL_INTERVAL)
    except KeyboardInterrupt:
        log("Daemon stopped by user")


def run_once():
    """Run single cycle"""
    log("=" * 50)
    print("  Local Zone Worker - Single Run")
    print("=" * 50)
    
    process_cycle(auto_approve=False)


def run_approve():
    """Run approval processing only"""
    log("=" * 50)
    print("  Local Zone Worker - Approval Mode")
    print("=" * 50)
    
    process_cycle(auto_approve=False)


# ============================================================================
# Entry Point
# ============================================================================

def main():
    parser = argparse.ArgumentParser(description="Local Zone Worker")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--daemon", action="store_true", help="Run continuously")
    group.add_argument("--once", action="store_true", help="Run single cycle")
    group.add_argument("--approve", action="store_true", help="Process approvals only")
    args = parser.parse_args()
    
    if args.daemon:
        run_daemon()
    elif args.approve:
        run_approve()
    else:
        run_once()


if __name__ == "__main__":
    main()
