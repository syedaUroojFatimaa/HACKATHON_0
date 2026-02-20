"""
email_server.py — MCP Server for sending emails via Gmail SMTP.

Implements the Model Context Protocol (MCP) JSON-RPC interface over stdio.
Claude Code connects to this server and can call the "send_email" tool.

Requires environment variables:
  EMAIL_ADDRESS    — Gmail sender address
  EMAIL_PASSWORD   — Gmail App Password

Usage (via Claude Code):
    Configured in .claude/settings.json, launched automatically.

Manual test:
    echo '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2024-11-05","capabilities":{},"clientInfo":{"name":"test","version":"1.0"}}}' | python mcp_servers/email_server.py
"""

import json
import os
import re
import smtplib
import sys
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

# ---------------------------------------------------------------------------
# SMTP Config
# ---------------------------------------------------------------------------

SMTP_HOST = "smtp.gmail.com"
SMTP_PORT = 587
_EMAIL_RE = re.compile(r"^[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}$")

# ---------------------------------------------------------------------------
# MCP Protocol Constants
# ---------------------------------------------------------------------------

PROTOCOL_VERSION = "2024-11-05"
SERVER_NAME = "email-mcp-server"
SERVER_VERSION = "1.0.0"

# ---------------------------------------------------------------------------
# Email sending logic (reuses gmail-send skill logic)
# ---------------------------------------------------------------------------

def send_email(to, subject, body, cc=None):
    """Send an email via Gmail SMTP. Returns (success, message)."""
    sender = os.environ.get("EMAIL_ADDRESS", "").strip()
    password = os.environ.get("EMAIL_PASSWORD", "").strip()

    if not sender:
        return False, "EMAIL_ADDRESS environment variable not set."
    if not password:
        return False, "EMAIL_PASSWORD environment variable not set."
    if not _EMAIL_RE.match(to):
        return False, f"Invalid recipient address: {to}"

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
        return False, "SMTP auth failed. Check EMAIL_PASSWORD (must be App Password)."
    except smtplib.SMTPRecipientsRefused:
        return False, f"Recipient refused: {to}"
    except smtplib.SMTPException as e:
        return False, f"SMTP error: {e}"
    except OSError as e:
        return False, f"Network error: {e}"

    return True, f"Email sent to {to}"

# ---------------------------------------------------------------------------
# JSON-RPC helpers
# ---------------------------------------------------------------------------

def _write(obj):
    """Write a JSON-RPC message to stdout."""
    data = json.dumps(obj)
    sys.stdout.write(data + "\n")
    sys.stdout.flush()


def _error_response(req_id, code, message):
    return {"jsonrpc": "2.0", "id": req_id, "error": {"code": code, "message": message}}


def _success_response(req_id, result):
    return {"jsonrpc": "2.0", "id": req_id, "result": result}

# ---------------------------------------------------------------------------
# MCP Method handlers
# ---------------------------------------------------------------------------

def handle_initialize(req_id, params):
    return _success_response(req_id, {
        "protocolVersion": PROTOCOL_VERSION,
        "capabilities": {"tools": {}},
        "serverInfo": {"name": SERVER_NAME, "version": SERVER_VERSION},
    })


def handle_tools_list(req_id, params):
    tools = [
        {
            "name": "send_email",
            "description": "Send an email via Gmail SMTP. Requires EMAIL_ADDRESS and EMAIL_PASSWORD environment variables.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "to": {"type": "string", "description": "Recipient email address"},
                    "subject": {"type": "string", "description": "Email subject line"},
                    "body": {"type": "string", "description": "Plain-text email body"},
                    "cc": {"type": "string", "description": "CC recipient (optional)"},
                },
                "required": ["to", "subject", "body"],
            },
        }
    ]
    return _success_response(req_id, {"tools": tools})


def handle_tools_call(req_id, params):
    tool_name = params.get("name", "")
    args = params.get("arguments", {})

    if tool_name != "send_email":
        return _error_response(req_id, -32602, f"Unknown tool: {tool_name}")

    to = args.get("to", "")
    subject = args.get("subject", "")
    body = args.get("body", "")
    cc = args.get("cc")

    if not to or not subject or not body:
        return _error_response(req_id, -32602, "Missing required fields: to, subject, body")

    success, message = send_email(to, subject, body, cc)

    content = [{"type": "text", "text": f"{'SUCCESS' if success else 'ERROR'}: {message}"}]
    return _success_response(req_id, {"content": content, "isError": not success})

# ---------------------------------------------------------------------------
# MCP Main loop (stdio transport)
# ---------------------------------------------------------------------------

HANDLERS = {
    "initialize": handle_initialize,
    "notifications/initialized": None,  # notification, no response
    "tools/list": handle_tools_list,
    "tools/call": handle_tools_call,
}


def main():
    for raw_line in sys.stdin:
        line = raw_line.strip()
        if not line:
            continue

        try:
            msg = json.loads(line)
        except json.JSONDecodeError:
            _write(_error_response(None, -32700, "Parse error"))
            continue

        method = msg.get("method", "")
        req_id = msg.get("id")
        params = msg.get("params", {})

        handler = HANDLERS.get(method)

        if handler is None:
            # It's either a notification (no response needed) or unknown.
            if method.startswith("notifications/"):
                continue
            if req_id is not None:
                _write(_error_response(req_id, -32601, f"Unknown method: {method}"))
            continue

        response = handler(req_id, params)
        if response and req_id is not None:
            _write(response)


if __name__ == "__main__":
    main()
