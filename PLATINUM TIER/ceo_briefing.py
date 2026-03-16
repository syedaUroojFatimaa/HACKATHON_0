"""
ceo_briefing.py — Weekly CEO Briefing Generator

Generates a comprehensive weekly briefing every Sunday:
  - Reads /Done folder for completed tasks
  - Reads Accounting data for revenue
  - Summarizes pending approvals and issues
  - Writes to Briefings/YYYY-MM-DD_CEO_Briefing.md

Schedule: Every Sunday at 8:00 AM

Usage:
    python ceo_briefing.py --generate     # Generate this week's briefing
    python ceo_briefing.py --preview      # Preview without saving
    python ceo_briefing.py --check        # Check if already generated
    python ceo_briefing.py --history      # Show briefing history
"""

import os
import re
import json
import argparse
from datetime import datetime, timezone, timedelta
from pathlib import Path
from collections import defaultdict
from typing import Dict, List, Tuple, Optional


# ============================================================================
# Configuration
# ============================================================================

SCRIPT_DIR = Path(__file__).parent
VAULT_ROOT = SCRIPT_DIR.parent

# Folders
DONE_DIR = VAULT_ROOT / "Done"
APPROVED_DIR = VAULT_ROOT / "Approved"
PENDING_APPROVAL_DIR = VAULT_ROOT / "Pending_Approval"
NEEDS_ACTION_DIR = VAULT_ROOT / "Needs_Action"
ACCOUNTING_DIR = VAULT_ROOT / "Accounting"
BRIEFINGS_DIR = VAULT_ROOT / "Briefings"
LOGS_DIR = VAULT_ROOT / "Logs"
INBOX_DIR = VAULT_ROOT / "Inbox"
ERRORS_DIR = VAULT_ROOT / "Errors"

# Ensure directories exist
BRIEFINGS_DIR.mkdir(parents=True, exist_ok=True)
LOGS_DIR.mkdir(parents=True, exist_ok=True)

# Log file
BRIEFING_LOG = LOGS_DIR / "ceo_briefing.log"


# ============================================================================
# Logging
# ============================================================================

def log(message: str, level: str = "INFO"):
    """Log to console and ceo_briefing.log"""
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    entry = f"[{timestamp}] [{level}] {message}"
    print(entry)
    
    try:
        with open(BRIEFING_LOG, "a", encoding="utf-8") as f:
            f.write(entry + "\n")
    except OSError as e:
        print(f"[ERROR] Could not write to log: {e}")


# ============================================================================
# Data Collection
# ============================================================================

def get_week_range() -> Tuple[datetime, datetime]:
    """Get the start and end of the current week (Monday to Sunday)"""
    today = datetime.now(timezone.utc)
    
    # Find last Monday (start of week)
    days_since_monday = today.weekday()
    week_start = today - timedelta(days=days_since_monday)
    week_start = week_start.replace(hour=0, minute=0, second=0, microsecond=0)
    
    # Week end is Sunday 23:59:59
    week_end = week_start + timedelta(days=6, hours=23, minutes=59, seconds=59)
    
    return week_start, week_end


def get_previous_week_range() -> Tuple[datetime, datetime]:
    """Get the start and end of the previous week"""
    today = datetime.now(timezone.utc)
    days_since_monday = today.weekday()
    
    # Previous Monday
    week_start = today - timedelta(days=days_since_monday + 7)
    week_start = week_start.replace(hour=0, minute=0, second=0, microsecond=0)
    
    # Previous Sunday
    week_end = week_start + timedelta(days=6, hours=23, minutes=59, seconds=59)
    
    return week_start, week_end


def parse_task_frontmatter(content: str) -> dict:
    """Parse YAML-style front matter from task file"""
    metadata = {}
    
    if "---" in content:
        parts = content.split("---")
        if len(parts) >= 3:
            front_matter = parts[1]
            for line in front_matter.split("\n"):
                if ":" in line:
                    key, value = line.split(":", 1)
                    key = key.strip().lower()
                    value = value.strip().strip('"').strip("'")
                    metadata[key] = value
    
    return metadata


def get_completed_tasks(week_start: datetime, week_end: datetime) -> List[dict]:
    """Get all tasks completed in the given week from Done/ and Approved/"""
    completed = []
    
    # Check Done/ folder
    if DONE_DIR.exists():
        for f in DONE_DIR.glob("*.md"):
            try:
                with open(f, "r", encoding="utf-8") as file:
                    content = file.read()
                
                metadata = parse_task_frontmatter(content)
                completed_date = None
                
                # Try to get completion date from metadata or file mtime
                if "completed_at" in metadata:
                    try:
                        completed_date = datetime.fromisoformat(
                            metadata["completed_at"].replace(" UTC", "+00:00")
                        )
                    except:
                        pass
                
                if not completed_date:
                    # Use file modification time
                    mtime = f.stat().st_mtime
                    completed_date = datetime.fromtimestamp(mtime, tz=timezone.utc)
                
                # Check if within week range
                if week_start <= completed_date <= week_end:
                    completed.append({
                        "filename": f.name,
                        "type": metadata.get("type", "task"),
                        "status": metadata.get("status", "completed"),
                        "completed_at": completed_date,
                        "source": "Done",
                        "content": content,
                    })
            except Exception as e:
                log(f"Error reading {f.name}: {e}", "WARN")
    
    # Check Approved/ subfolders
    for channel in ["email", "social", "general"]:
        channel_dir = APPROVED_DIR / channel
        if channel_dir.exists():
            for f in channel_dir.glob("*.md"):
                try:
                    with open(f, "r", encoding="utf-8") as file:
                        content = file.read()
                    
                    metadata = parse_task_frontmatter(content)
                    
                    # Use file mtime for approved items
                    mtime = f.stat().st_mtime
                    completed_date = datetime.fromtimestamp(mtime, tz=timezone.utc)
                    
                    if week_start <= completed_date <= week_end:
                        completed.append({
                            "filename": f.name,
                            "type": metadata.get("channel", channel),
                            "status": metadata.get("status", "approved"),
                            "completed_at": completed_date,
                            "source": f"Approved/{channel}",
                            "content": content,
                        })
                except Exception as e:
                    log(f"Error reading {f.name}: {e}", "WARN")
    
    # Sort by completion date
    completed.sort(key=lambda x: x["completed_at"], reverse=True)
    
    return completed


def get_revenue_data(week_start: datetime, week_end: datetime) -> dict:
    """Get revenue data from Accounting/ folder"""
    revenue = {
        "total": 0.0,
        "transactions": [],
        "by_category": defaultdict(float),
        "pending": [],
    }
    
    # Check for revenue/income files
    if ACCOUNTING_DIR.exists():
        # Look for revenue files
        for pattern in ["revenue*.md", "income*.md", "payments*.md", "invoices*.md"]:
            for f in ACCOUNTING_DIR.glob(pattern):
                try:
                    with open(f, "r", encoding="utf-8") as file:
                        content = file.read()
                    
                    # Extract amounts using regex
                    amount_pattern = r'\$?(\d+(?:,\d{3})*(?:\.\d{2})?)'
                    amounts = re.findall(amount_pattern, content)
                    
                    for amount_str in amounts:
                        amount = float(amount_str.replace(",", ""))
                        revenue["total"] += amount
                        revenue["transactions"].append({
                            "file": f.name,
                            "amount": amount,
                            "date": datetime.fromtimestamp(f.stat().st_mtime, tz=timezone.utc),
                        })
                except Exception as e:
                    log(f"Error reading revenue file {f.name}: {e}", "WARN")
        
        # Check for payments received
        payments_dir = ACCOUNTING_DIR / "payments_received"
        if payments_dir.exists():
            for f in payments_dir.glob("*.md"):
                try:
                    with open(f, "r", encoding="utf-8") as file:
                        content = file.read()
                    
                    metadata = parse_task_frontmatter(content)
                    amount = float(metadata.get("amount", "0"))
                    
                    if amount > 0:
                        revenue["total"] += amount
                        category = metadata.get("category", "uncategorized")
                        revenue["by_category"][category] += amount
                        
                        revenue["transactions"].append({
                            "file": f.name,
                            "amount": amount,
                            "category": category,
                            "date": datetime.fromtimestamp(f.stat().st_mtime, tz=timezone.utc),
                        })
                except Exception as e:
                    log(f"Error reading payment file {f.name}: {e}", "WARN")
        
        # Check for pending payments
        pending_dir = ACCOUNTING_DIR / "pending_payments"
        if pending_dir.exists():
            for f in pending_dir.glob("*.md"):
                try:
                    with open(f, "r", encoding="utf-8") as file:
                        content = file.read()
                    
                    metadata = parse_task_frontmatter(content)
                    amount = float(metadata.get("amount", "0"))
                    
                    if amount > 0:
                        revenue["pending"].append({
                            "file": f.name,
                            "amount": amount,
                            "category": metadata.get("category", "uncategorized"),
                        })
                except Exception as e:
                    log(f"Error reading pending file {f.name}: {e}", "WARN")
    
    return revenue


def get_pending_approvals() -> List[dict]:
    """Get all pending approvals"""
    pending = []
    
    if PENDING_APPROVAL_DIR.exists():
        for channel in ["email", "social", "general"]:
            channel_dir = PENDING_APPROVAL_DIR / channel
            if channel_dir.exists():
                for f in channel_dir.glob("*.md"):
                    try:
                        with open(f, "r", encoding="utf-8") as file:
                            content = file.read()
                        
                        metadata = parse_task_frontmatter(content)
                        
                        # Check if already approved/rejected
                        status = metadata.get("status", "pending")
                        if status == "pending":
                            pending.append({
                                "filename": f.name,
                                "channel": channel,
                                "category": metadata.get("category", "general"),
                                "created_at": metadata.get("created_at", "unknown"),
                                "source_task": metadata.get("source_task", "unknown"),
                            })
                    except Exception as e:
                        log(f"Error reading approval {f.name}: {e}", "WARN")
    
    return pending


def get_pending_tasks() -> List[dict]:
    """Get all pending tasks from Needs_Action/"""
    pending = []
    
    if NEEDS_ACTION_DIR.exists():
        for channel in ["email", "social", "general"]:
            channel_dir = NEEDS_ACTION_DIR / channel
            if channel_dir.exists():
                for f in channel_dir.glob("*.md"):
                    try:
                        with open(f, "r", encoding="utf-8") as file:
                            content = file.read()
                        
                        metadata = parse_task_frontmatter(content)
                        
                        pending.append({
                            "filename": f.name,
                            "channel": channel,
                            "type": metadata.get("type", "task"),
                            "priority": metadata.get("priority", "medium"),
                            "created_at": metadata.get("created_at", "unknown"),
                        })
                    except Exception as e:
                        log(f"Error reading task {f.name}: {e}", "WARN")
    
    return pending


def get_issues_and_errors() -> List[dict]:
    """Get issues from Errors/ folder and error logs"""
    issues = []
    
    # Check Errors/ folder
    if ERRORS_DIR.exists():
        for f in ERRORS_DIR.glob("*.md"):
            try:
                mtime = datetime.fromtimestamp(f.stat().st_mtime, tz=timezone.utc)
                issues.append({
                    "filename": f.name,
                    "type": "error_file",
                    "detected_at": mtime,
                })
            except Exception as e:
                log(f"Error reading error file {f.name}: {e}", "WARN")
    
    # Check watcher_errors.log
    watcher_errors = LOGS_DIR / "watcher_errors.log"
    if watcher_errors.exists():
        try:
            with open(watcher_errors, "r", encoding="utf-8") as f:
                lines = f.readlines()
            
            # Get recent errors (last 10)
            recent_errors = lines[-10:] if len(lines) > 10 else lines
            for line in recent_errors:
                if line.strip():
                    issues.append({
                        "filename": "watcher_errors.log",
                        "type": "watcher_error",
                        "message": line.strip(),
                    })
        except Exception as e:
            log(f"Error reading watcher_errors.log: {e}", "WARN")
    
    # Check for stuck tasks (in In_Progress for too long)
    in_progress_dir = VAULT_ROOT / "In_Progress"
    if in_progress_dir.exists():
        for zone in ["cloud", "local"]:
            zone_dir = in_progress_dir / zone
            if zone_dir.exists():
                for f in zone_dir.glob("*.md"):
                    mtime = datetime.fromtimestamp(f.stat().st_mtime, tz=timezone.utc)
                    age = datetime.now(timezone.utc) - mtime
                    if age > timedelta(hours=24):
                        issues.append({
                            "filename": f.name,
                            "type": "stuck_task",
                            "zone": zone,
                            "age_hours": int(age.total_seconds() / 3600),
                        })
    
    return issues


def get_inbox_status() -> dict:
    """Get inbox statistics"""
    status = {"count": 0, "files": []}
    
    if INBOX_DIR.exists():
        files = list(INBOX_DIR.glob("*"))
        status["count"] = len(files)
        status["files"] = [f.name for f in files[:10]]  # First 10 files
    
    return status


# ============================================================================
# Briefing Generation
# ============================================================================

def generate_briefing(week_start: datetime, week_end: datetime) -> str:
    """Generate the CEO briefing content"""
    
    # Collect data
    completed_tasks = get_completed_tasks(week_start, week_end)
    revenue_data = get_revenue_data(week_start, week_end)
    pending_approvals = get_pending_approvals()
    pending_tasks = get_pending_tasks()
    issues = get_issues_and_errors()
    inbox_status = get_inbox_status()
    
    # Week label
    week_label = f"{week_start.strftime('%Y-%m-%d')} to {week_end.strftime('%Y-%m-%d')}"
    
    # Build briefing content
    content = f"""---
type: ceo_briefing
period: {week_label}
generated_at: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}
week_number: {week_start.isocalendar()[1]}
year: {week_start.year}
---

# CEO Weekly Briefing

> **Period:** {week_label}
> **Generated:** {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}
> **Week:** {week_start.isocalendar()[1]} of {week_start.year}

---

## Executive Summary

| Metric | This Week | Status |
|--------|-----------|--------|
| Tasks Completed | {len(completed_tasks)} | {'🟢' if len(completed_tasks) > 0 else '🟡'} |
| Revenue | ${revenue_data['total']:,.2f} | {'🟢' if revenue_data['total'] > 0 else '🟡'} |
| Pending Approvals | {len(pending_approvals)} | {'🟢' if len(pending_approvals) < 5 else '🟡'} |
| Issues | {len(issues)} | {'🟢' if len(issues) == 0 else '🔴'} |

---

## Revenue Summary

### Total Revenue: ${revenue_data['total']:,.2f}

"""
    
    # Revenue by category
    if revenue_data['by_category']:
        content += "### Revenue by Category\n\n"
        content += "| Category | Amount |\n"
        content += "|----------|--------|\n"
        for category, amount in sorted(revenue_data['by_category'].items(), key=lambda x: x[1], reverse=True):
            content += f"| {category} | ${amount:,.2f} |\n"
        content += "\n"
    
    # Recent transactions
    if revenue_data['transactions']:
        content += "### Recent Transactions\n\n"
        content += "| Date | File | Amount | Category |\n"
        content += "|------|------|--------|----------|\n"
        for txn in revenue_data['transactions'][-10:]:  # Last 10
            date_str = txn['date'].strftime('%Y-%m-%d') if isinstance(txn['date'], datetime) else '-'
            category = txn.get('category', '-')
            content += f"| {date_str} | {txn['file']} | ${txn['amount']:,.2f} | {category} |\n"
        content += "\n"
    
    # Pending revenue
    if revenue_data['pending']:
        content += "### Pending Revenue\n\n"
        pending_total = sum(p['amount'] for p in revenue_data['pending'])
        content += f"**Total Pending:** ${pending_total:,.2f}\n\n"
        content += "| File | Amount | Category |\n"
        content += "|------|--------|----------|\n"
        for p in revenue_data['pending']:
            content += f"| {p['file']} | ${p['amount']:,.2f} | {p['category']} |\n"
        content += "\n"
    
    content += "---\n\n"
    
    # Completed Tasks
    content += "## Completed Tasks\n\n"
    
    if completed_tasks:
        # Group by type
        by_type = defaultdict(list)
        for task in completed_tasks:
            by_type[task['type']].append(task)
        
        for task_type, tasks in sorted(by_type.items()):
            content += f"### {task_type.title()} ({len(tasks)})\n\n"
            content += "| File | Source | Completed |\n"
            content += "|------|--------|-----------|\n"
            for task in tasks[:20]:  # Limit to 20 per category
                date_str = task['completed_at'].strftime('%Y-%m-%d') if isinstance(task['completed_at'], datetime) else '-'
                content += f"| {task['filename']} | {task['source']} | {date_str} |\n"
            content += "\n"
    else:
        content += "*No tasks completed this week.*\n\n"
    
    content += "---\n\n"
    
    # Pending Approvals
    content += "## Pending Approvals\n\n"
    
    if pending_approvals:
        content += f"**{len(pending_approvals)} items awaiting approval**\n\n"
        content += "| File | Channel | Category | Created |\n"
        content += "|------|---------|----------|--------|\n"
        for approval in pending_approvals[:20]:  # Limit to 20
            content += f"| {approval['filename']} | {approval['channel']} | {approval['category']} | {approval['created_at']} |\n"
        content += "\n"
        
        # Action required
        content += "### ⚠️ Action Required\n\n"
        content += "Please review and approve/reject the items above.\n\n"
    else:
        content += "✅ **No pending approvals.**\n\n"
    
    content += "---\n\n"
    
    # Pending Tasks
    content += "## Pending Tasks\n\n"
    
    if pending_tasks:
        # Group by priority
        by_priority = defaultdict(list)
        for task in pending_tasks:
            by_priority[task['priority']].append(task)
        
        for priority in ['high', 'medium', 'low']:
            tasks = by_priority.get(priority, [])
            if tasks:
                content += f"### {priority.title()} Priority ({len(tasks)})\n\n"
                content += "| File | Channel | Type |\n"
                content += "|------|---------|------|\n"
                for task in tasks[:10]:
                    content += f"| {task['filename']} | {task['channel']} | {task['type']} |\n"
                content += "\n"
    else:
        content += "✅ **No pending tasks.**\n\n"
    
    content += "---\n\n"
    
    # Issues and Errors
    content += "## Issues & Errors\n\n"
    
    if issues:
        content += f"**{len(issues)} issue(s) detected**\n\n"
        
        # Group by type
        by_type = defaultdict(list)
        for issue in issues:
            by_type[issue['type']].append(issue)
        
        for issue_type, issue_list in by_type.items():
            content += f"### {issue_type.replace('_', ' ').title()} ({len(issue_list)})\n\n"
            
            for issue in issue_list[:10]:
                if issue_type == 'stuck_task':
                    content += f"- `{issue['filename']}` stuck in {issue['zone']} zone for {issue['age_hours']}h\n"
                elif issue_type == 'watcher_error':
                    content += f"- {issue['message'][:100]}...\n"
                else:
                    content += f"- `{issue['filename']}`\n"
            content += "\n"
        
        content += "### 🔧 Recommended Actions\n\n"
        content += "1. Review error logs in `Logs/` folder\n"
        content += "2. Check stuck tasks in `In_Progress/` folder\n"
        content += "3. Run health check: `python watchdog.py --status`\n\n"
    else:
        content += "✅ **No issues detected.**\n\n"
    
    content += "---\n\n"
    
    # Inbox Status
    content += "## Inbox Status\n\n"
    
    if inbox_status['count'] > 0:
        content += f"**{inbox_status['count']} file(s) in Inbox**\n\n"
        if inbox_status['files']:
            content += "Recent files:\n\n"
            for f in inbox_status['files'][:10]:
                content += f"- `{f}`\n"
            content += "\n"
    else:
        content += "✅ **Inbox is empty.**\n\n"
    
    content += "---\n\n"
    
    # Key Metrics Summary
    content += "## Key Metrics Summary\n\n"
    content += "```\n"
    content += f"Week:           {week_label}\n"
    content += f"Tasks Done:     {len(completed_tasks)}\n"
    content += f"Revenue:        ${revenue_data['total']:,.2f}\n"
    content += f"Pending:        {len(pending_approvals)} approvals, {len(pending_tasks)} tasks\n"
    content += f"Issues:         {len(issues)}\n"
    content += f"Inbox:          {inbox_status['count']} files\n"
    content += "```\n\n"
    
    content += "---\n\n"
    content += "*Generated automatically by ceo_briefing.py*\n"
    
    return content


def check_already_generated(week_start: datetime) -> bool:
    """Check if briefing for this week already exists"""
    expected_date = week_start.strftime('%Y-%m-%d')
    pattern = f"{expected_date}*_CEO_Briefing.md"
    
    existing = list(BRIEFINGS_DIR.glob(pattern))
    return len(existing) > 0


def save_briefing(content: str, week_start: datetime) -> Path:
    """Save briefing to file"""
    date_str = week_start.strftime('%Y-%m-%d')
    filename = f"{date_str}_CEO_Briefing.md"
    filepath = BRIEFINGS_DIR / filename
    
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(content)
    
    return filepath


# ============================================================================
# Commands
# ============================================================================

def run_generate(force: bool = False) -> Optional[Path]:
    """Generate this week's briefing"""
    week_start, week_end = get_week_range()
    
    # Check if already generated
    if not force and check_already_generated(week_start):
        log("Briefing for this week already exists. Use --force to regenerate.", "WARN")
        return None
    
    log(f"Generating briefing for week: {week_start.strftime('%Y-%m-%d')} to {week_end.strftime('%Y-%m-%d')}")
    
    content = generate_briefing(week_start, week_end)
    filepath = save_briefing(content, week_start)
    
    log(f"Briefing saved to: {filepath}")
    return filepath


def run_preview():
    """Preview briefing without saving"""
    week_start, week_end = get_week_range()
    
    log("Generating preview...")
    content = generate_briefing(week_start, week_end)
    
    print()
    print("=" * 60)
    print("  BRIEFING PREVIEW")
    print("=" * 60)
    print()
    print(content[:3000])  # First 3000 chars
    if len(content) > 3000:
        print("\n... (truncated)")
    print()
    print("=" * 60)


def run_check():
    """Check if briefing already generated"""
    week_start, week_end = get_week_range()
    
    if check_already_generated(week_start):
        print(f"✅ Briefing for this week already exists.")
        
        # Find existing briefing
        pattern = f"{week_start.strftime('%Y-%m-%d')}*_CEO_Briefing.md"
        existing = list(BRIEFINGS_DIR.glob(pattern))
        if existing:
            print(f"   File: {existing[0]}")
    else:
        print(f"📝 No briefing for this week yet.")
        print(f"   Run: python ceo_briefing.py --generate")


def run_history():
    """Show briefing history"""
    print()
    print("=" * 60)
    print("  BRIEFING HISTORY")
    print("=" * 60)
    print()
    
    if not BRIEFINGS_DIR.exists():
        print("No briefings found.")
        return
    
    briefings = sorted(BRIEFINGS_DIR.glob("*_CEO_Briefing.md"), reverse=True)
    
    if not briefings:
        print("No briefings found.")
        return
    
    print(f"{'Date':<15} {'File':<40} {'Size':<10}")
    print("-" * 65)
    
    for b in briefings[:20]:  # Last 20 briefings
        stat = b.stat()
        size_kb = stat.st_size / 1024
        print(f"{b.stem:<15} {b.name:<40} {size_kb:.1f} KB")
    
    print()
    print(f"Total: {len(briefings)} briefing(s)")
    print("=" * 60)


# ============================================================================
# Entry Point
# ============================================================================

def main():
    parser = argparse.ArgumentParser(description="CEO Weekly Briefing Generator")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--generate", action="store_true", help="Generate this week's briefing")
    group.add_argument("--force", action="store_true", help="Force regenerate (even if exists)")
    group.add_argument("--preview", action="store_true", help="Preview without saving")
    group.add_argument("--check", action="store_true", help="Check if already generated")
    group.add_argument("--history", action="store_true", help="Show briefing history")
    
    args = parser.parse_args()
    
    if args.generate or args.force:
        run_generate(force=args.force)
    elif args.preview:
        run_preview()
    elif args.check:
        run_check()
    elif args.history:
        run_history()


if __name__ == "__main__":
    main()
