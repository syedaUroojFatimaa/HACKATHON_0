"""
email_sender.py — Local-Only Email Sender

Sends email drafts created by Cloud worker.
ONLY runs on Local machine (has access to email credentials).

Security:
- Uses .env for credentials (never synced to Cloud)
- Only Local can access Gmail API / SMTP
- Logs all sent emails for audit

Usage:
    python scripts/email_sender.py --send approval_file.md
    python scripts/email_sender.py --test
"""

import os
import re
import sys
import argparse
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime, timezone
from pathlib import Path


# ============================================================================
# Configuration
# ============================================================================

SCRIPT_DIR = Path(__file__).parent
VAULT_ROOT = SCRIPT_DIR.parent

# Local-only folders (never synced)
SESSIONS_DIR = VAULT_ROOT / "sessions"
LOGS_DIR = VAULT_ROOT / "Logs"
APPROVED_DIR = VAULT_ROOT / "Approved"

# Ensure directories exist
SESSIONS_DIR.mkdir(parents=True, exist_ok=True)
LOGS_DIR.mkdir(parents=True, exist_ok=True)

# Log file
EMAIL_LOG = LOGS_DIR / "email_sender.log"


# ============================================================================
# Logging
# ============================================================================

def log(message: str, level: str = "INFO"):
    """Log to console and email_sender.log"""
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    entry = f"[{timestamp}] [{level}] {message}"
    print(entry)
    
    try:
        with open(EMAIL_LOG, "a", encoding="utf-8") as f:
            f.write(entry + "\n")
    except OSError as e:
        print(f"[ERROR] Could not write to log: {e}")


# ============================================================================
# Email Configuration
# ============================================================================

def get_email_config() -> dict:
    """Get email configuration from .env (Local only)"""
    config = {
        "email_address": os.environ.get("EMAIL_ADDRESS", ""),
        "email_password": os.environ.get("EMAIL_PASSWORD", ""),
        "smtp_server": os.environ.get("SMTP_SERVER", "smtp.gmail.com"),
        "smtp_port": int(os.environ.get("SMTP_PORT", "587")),
    }
    
    # Also check for Gmail-specific vars
    if not config["email_address"]:
        config["email_address"] = os.environ.get("GMAIL_ADDRESS", "")
    if not config["email_password"]:
        config["email_password"] = os.environ.get("GMAIL_PASSWORD", "")
    
    return config


def check_email_config() -> bool:
    """Check if email is configured"""
    config = get_email_config()
    
    if not config["email_address"] or not config["email_password"]:
        log("Email credentials not configured in .env", "ERROR")
        log("Add EMAIL_ADDRESS and EMAIL_PASSWORD to .env file", "ERROR")
        return False
    
    return True


# ============================================================================
# Email Sending
# ============================================================================

def parse_approval_file(filepath: Path) -> dict:
    """Parse approval file to extract email draft"""
    with open(filepath, "r", encoding="utf-8") as f:
        content = f.read()
    
    email_data = {
        "to": "",
        "subject": "",
        "body": "",
        "metadata": {}
    }
    
    # Parse front matter
    if "---" in content:
        parts = content.split("---")
        if len(parts) >= 3:
            front_matter = parts[1]
            for line in front_matter.split("\n"):
                if ":" in line:
                    key, value = line.split(":", 1)
                    key = key.strip().lower()
                    value = value.strip().strip('"').strip("'")
                    email_data["metadata"][key] = value
    
    # Extract email content from draft section
    draft_match = re.search(r'Subject:\s*(.+?)(?:\n|$)', content, re.IGNORECASE)
    if draft_match:
        email_data["subject"] = draft_match.group(1).strip()
    
    # Extract body (everything after "Subject:" line until next section)
    body_match = re.search(r'Subject:.*?\n\n(.*?)(?:---|\Z)', content, re.DOTALL | re.IGNORECASE)
    if body_match:
        email_data["body"] = body_match.group(1).strip()
    
    # Try to get recipient from metadata or content
    email_data["to"] = email_data["metadata"].get("to", "")
    if not email_data["to"]:
        # Try to extract from original email data in approval
        from_match = re.search(r'from:\s*(.+?)(?:\n|$)', content, re.IGNORECASE)
        if from_match:
            email_data["to"] = from_match.group(1).strip()  # Reply to sender
    
    return email_data


def send_email(to: str, subject: str, body: str, html: bool = False) -> bool:
    """Send email via SMTP"""
    config = get_email_config()
    
    try:
        # Create message
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = config["email_address"]
        msg["To"] = to
        
        # Attach body
        mime_type = "html" if html else "plain"
        msg.attach(MIMEText(body, mime_type))
        
        # Connect and send
        log(f"Connecting to SMTP server {config['smtp_server']}:{config['smtp_port']}")
        server = smtplib.SMTP(config["smtp_server"], config["smtp_port"])
        server.starttls()
        server.login(config["email_address"], config["email_password"])
        
        log(f"Sending email to {to}")
        server.send_message(msg)
        server.quit()
        
        log(f"Email sent successfully to {to}")
        return True
        
    except smtplib.SMTPAuthenticationError:
        log("SMTP Authentication failed. Check credentials.", "ERROR")
        return False
    except smtplib.SMTPException as e:
        log(f"SMTP error: {e}", "ERROR")
        return False
    except Exception as e:
        log(f"Failed to send email: {e}", "ERROR")
        return False


def send_email_via_gmail(to: str, subject: str, body: str) -> bool:
    """Send email via Gmail API (alternative to SMTP)"""
    try:
        # This would use the Gmail API with OAuth2
        # For now, fall back to SMTP
        log("Gmail API not configured, using SMTP instead", "WARN")
        return send_email(to, subject, body)
    except Exception as e:
        log(f"Gmail API error: {e}", "ERROR")
        return False


# ============================================================================
# Approval Processing
# ============================================================================

def process_email_approval(filepath: Path, auto_send: bool = False) -> bool:
    """Process an email approval file and send the email"""
    log(f"Processing email approval: {filepath.name}")
    
    # Parse the approval file
    email_data = parse_approval_file(filepath)
    
    if not email_data["to"]:
        log("No recipient found in approval file", "ERROR")
        return False
    
    if not email_data["subject"]:
        log("No subject found in approval file", "ERROR")
        return False
    
    if not email_data["body"]:
        log("No body found in approval file", "ERROR")
        return False
    
    log(f"Email draft parsed:")
    log(f"  To: {email_data['to']}")
    log(f"  Subject: {email_data['subject']}")
    log(f"  Body length: {len(email_data['body'])} chars")
    
    # Send or preview
    if auto_send:
        success = send_email(
            to=email_data["to"],
            subject=email_data["subject"],
            body=email_data["body"]
        )
        
        if success:
            log("Email sent successfully!")
            # Update approval file status
            update_approval_status(filepath, "sent")
        else:
            log("Failed to send email", "ERROR")
        
        return success
    else:
        log("Preview mode - email not sent")
        print("\n--- EMAIL PREVIEW ---")
        print(f"To: {email_data['to']}")
        print(f"Subject: {email_data['subject']}")
        print(f"\n{email_data['body'][:500]}...")
        print("--- END PREVIEW ---\n")
        return True


def update_approval_status(filepath: Path, status: str):
    """Update approval file with sent status"""
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            content = f.read()
        
        # Update status in front matter
        content = re.sub(
            r'^(status:\s*).*$',
            f'\\g<1>{status}',
            content,
            flags=re.MULTILINE
        )
        
        # Add sent timestamp
        timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
        if "sent_at:" not in content:
            content = content.replace(
                f"status: {status}",
                f"status: {status}\nsent_at: {timestamp}"
            )
        
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(content)
        
        log(f"Updated approval status to: {status}")
        
    except Exception as e:
        log(f"Failed to update approval status: {e}", "ERROR")


# ============================================================================
# Commands
# ============================================================================

def run_send(approval_file: str):
    """Send email from approval file"""
    if not check_email_config():
        return False
    
    filepath = Path(approval_file)
    if not filepath.exists():
        log(f"Approval file not found: {filepath}", "ERROR")
        return False
    
    return process_email_approval(filepath, auto_send=True)


def run_preview(approval_file: str):
    """Preview email without sending"""
    filepath = Path(approval_file)
    if not filepath.exists():
        log(f"Approval file not found: {filepath}", "ERROR")
        return False
    
    return process_email_approval(filepath, auto_send=False)


def run_test():
    """Send test email"""
    if not check_email_config():
        return False
    
    config = get_email_config()
    
    log("Sending test email...")
    success = send_email(
        to=config["email_address"],
        subject="Test Email from AI Employee",
        body="This is a test email from the Platinum Tier AI Employee system.\n\nIf you received this, email sending is working correctly."
    )
    
    if success:
        log(f"Test email sent to {config['email_address']}")
    else:
        log("Test email failed", "ERROR")
    
    return success


def run_pending():
    """Process all pending email approvals"""
    if not check_email_config():
        return False
    
    pending_dir = VAULT_ROOT / "Pending_Approval" / "email"
    if not pending_dir.exists():
        log("No pending email approvals found")
        return True
    
    processed = 0
    for f in pending_dir.glob("approval_*.md"):
        if process_email_approval(f, auto_send=True):
            processed += 1
    
    log(f"Processed {processed} pending email(s)")
    return True


# ============================================================================
# Entry Point
# ============================================================================

def main():
    parser = argparse.ArgumentParser(description="Local Email Sender")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--send", metavar="FILE", help="Send email from approval file")
    group.add_argument("--preview", metavar="FILE", help="Preview email without sending")
    group.add_argument("--pending", action="store_true", help="Process all pending emails")
    group.add_argument("--test", action="store_true", help="Send test email")
    group.add_argument("--check", action="store_true", help="Check email configuration")
    
    args = parser.parse_args()
    
    if args.check:
        config = get_email_config()
        print(f"Email Address: {config['email_address'] or 'NOT SET'}")
        print(f"Email Password: {'***' if config['email_password'] else 'NOT SET'}")
        print(f"SMTP Server: {config['smtp_server']}:{config['smtp_port']}")
        return 0 if check_email_config() else 1
    
    elif args.send:
        return 0 if run_send(args.send) else 1
    
    elif args.preview:
        return 0 if run_preview(args.preview) else 1
    
    elif args.pending:
        return 0 if run_pending() else 1
    
    elif args.test:
        return 0 if run_test() else 1


if __name__ == "__main__":
    sys.exit(main())
