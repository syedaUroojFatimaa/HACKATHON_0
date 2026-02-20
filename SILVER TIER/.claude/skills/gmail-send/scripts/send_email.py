"""
send_email.py — Send real emails via Gmail SMTP.

Requires environment variables:
  EMAIL_ADDRESS    — Gmail sender address
  EMAIL_PASSWORD   — Gmail App Password

Usage:
    python send_email.py --to user@example.com --subject "Hello" --body "Message"
"""

import argparse
import os
import re
import smtplib
import sys
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime, timezone

SMTP_HOST = "smtp.gmail.com"
SMTP_PORT = 587

# Simple email validation.
_EMAIL_RE = re.compile(r"^[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}$")


def validate_email(addr):
    return bool(_EMAIL_RE.match(addr))


def send(to, subject, body, cc=None):
    """Send an email. Returns (success: bool, message: str)."""
    sender = os.environ.get("EMAIL_ADDRESS", "").strip()
    password = os.environ.get("EMAIL_PASSWORD", "").strip()

    if not sender:
        return False, "EMAIL_ADDRESS environment variable not set."
    if not password:
        return False, "EMAIL_PASSWORD environment variable not set."
    if not validate_email(sender):
        return False, f"Invalid sender address: {sender}"
    if not validate_email(to):
        return False, f"Invalid recipient address: {to}"
    if cc and not validate_email(cc):
        return False, f"Invalid CC address: {cc}"

    msg = MIMEMultipart()
    msg["From"] = sender
    msg["To"] = to
    msg["Subject"] = subject
    if cc:
        msg["Cc"] = cc

    msg.attach(MIMEText(body, "plain", "utf-8"))

    recipients = [to]
    if cc:
        recipients.append(cc)

    try:
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=30) as server:
            server.ehlo()
            server.starttls()
            server.ehlo()
            server.login(sender, password)
            server.sendmail(sender, recipients, msg.as_string())
    except smtplib.SMTPAuthenticationError:
        return False, "SMTP authentication failed. Check EMAIL_PASSWORD (must be an App Password)."
    except smtplib.SMTPRecipientsRefused:
        return False, f"Recipient refused by server: {to}"
    except smtplib.SMTPException as e:
        return False, f"SMTP error: {e}"
    except OSError as e:
        return False, f"Network error: {e}"

    return True, f"Email sent to {to}"


def main():
    parser = argparse.ArgumentParser(description="Send email via Gmail SMTP")
    parser.add_argument("--to", required=True, help="Recipient email address")
    parser.add_argument("--subject", required=True, help="Email subject")
    parser.add_argument("--body", required=True, help="Email body (plain text)")
    parser.add_argument("--cc", default=None, help="CC recipient (optional)")
    args = parser.parse_args()

    success, message = send(args.to, args.subject, args.body, args.cc)

    if success:
        now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
        print(f"SUCCESS: {message}")
        print(f"  To:      {args.to}")
        print(f"  Subject: {args.subject}")
        print(f"  Sent at: {now}")
    else:
        print(f"ERROR: {message}")
        sys.exit(1)


if __name__ == "__main__":
    main()
