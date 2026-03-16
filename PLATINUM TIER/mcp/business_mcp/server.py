"""
server.py — business-mcp v2.0.0
Production-ready MCP server for external business actions.

Transport  : JSON-RPC 2.0 over stdio  (MCP protocol version 2024-11-05)
Tools      : send_email(to, subject, body) · log_activity(message)
Diagnostics: structured logs → stderr   ← never stdout (that is the MCP channel)

Environment variables (loaded from .env at vault root, or set in shell):
  EMAIL_ADDRESS   — Gmail sender address
  EMAIL_PASSWORD  — Gmail App Password (16-char token, NOT account password)

Usage (launched automatically by Claude Code via .claude/settings.json):
  python mcp/business_mcp/server.py

Manual smoke-test:
  printf '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2024-11-05","capabilities":{},"clientInfo":{"name":"test","version":"1.0"}}}\n{"jsonrpc":"2.0","id":2,"method":"ping","params":{}}\n' \\
    | python mcp/business_mcp/server.py
"""

from __future__ import annotations

import collections
import json
import logging
import os
import re
import signal
import smtplib
import sys
import threading
import time
from datetime import datetime, timezone
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

# ──────────────────────────────────────────────────────────────────────────────
# Paths  (resolve relative to this file so the server works from any cwd)
# ──────────────────────────────────────────────────────────────────────────────

_VAULT_ROOT = os.path.abspath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..")
)
_ENV_PATH      = os.path.join(_VAULT_ROOT, ".env")
_BUSINESS_LOG  = os.path.join(_VAULT_ROOT, "Logs", "business.log")

# ──────────────────────────────────────────────────────────────────────────────
# Load .env  (before anything else so logger can use env vars if needed)
# ──────────────────────────────────────────────────────────────────────────────

def _load_dotenv(path: str) -> None:
    if not os.path.isfile(path):
        return
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, val = line.partition("=")
            os.environ.setdefault(key.strip(), val.strip())

_load_dotenv(_ENV_PATH)

# ──────────────────────────────────────────────────────────────────────────────
# Structured stderr logger
# Stdout is exclusively the MCP JSON-RPC channel — diagnostics go to stderr.
# ──────────────────────────────────────────────────────────────────────────────

logging.basicConfig(
    stream=sys.stderr,
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
_log = logging.getLogger("business-mcp")

# ──────────────────────────────────────────────────────────────────────────────
# Constants & limits
# ──────────────────────────────────────────────────────────────────────────────

PROTOCOL_VERSION = "2024-11-05"
SERVER_NAME      = "business-mcp"
SERVER_VERSION   = "2.0.0"

SMTP_HOST        = "smtp.gmail.com"
SMTP_PORT        = 587
SMTP_TIMEOUT_S   = 30

# RFC 5321 / 2822 limits
_MAX_TO_LEN      = 254
_MAX_SUBJECT_LEN = 998
_MAX_BODY_BYTES  = 1 * 1024 * 1024   # 1 MB
_MAX_LOG_MSG_LEN = 10_000            # characters

# Log rotation
_LOG_MAX_BYTES   = 5 * 1024 * 1024  # 5 MB

# SMTP retry backoff (seconds between attempts)
_SMTP_RETRY_DELAYS: tuple[int, ...] = (0, 3, 8)   # 3 total attempts

# Email validation (RFC 5322 simplified)
_EMAIL_RE = re.compile(r"^[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}$")

# ──────────────────────────────────────────────────────────────────────────────
# Thread primitives
# ──────────────────────────────────────────────────────────────────────────────

_log_lock    = threading.Lock()          # serialises writes to business.log
_shutdown    = threading.Event()         # set by signal handler to stop main loop

# ──────────────────────────────────────────────────────────────────────────────
# Graceful shutdown
# ──────────────────────────────────────────────────────────────────────────────

def _on_signal(signum: int, _frame) -> None:
    _log.info("Signal %d received — shutting down gracefully.", signum)
    _shutdown.set()

signal.signal(signal.SIGTERM, _on_signal)
signal.signal(signal.SIGINT,  _on_signal)

# ──────────────────────────────────────────────────────────────────────────────
# Rate limiter — sliding window, thread-safe
# ──────────────────────────────────────────────────────────────────────────────

class _RateLimiter:
    """Allow at most `max_calls` events within a rolling `window_s`-second window."""

    def __init__(self, max_calls: int, window_s: float) -> None:
        self._max    = max_calls
        self._window = window_s
        self._calls: collections.deque[float] = collections.deque()
        self._lock   = threading.Lock()

    def allow(self) -> bool:
        now = time.monotonic()
        with self._lock:
            while self._calls and now - self._calls[0] > self._window:
                self._calls.popleft()
            if len(self._calls) >= self._max:
                return False
            self._calls.append(now)
            return True

    def seconds_until_next(self) -> float:
        with self._lock:
            if not self._calls:
                return 0.0
            return max(0.0, self._window - (time.monotonic() - self._calls[0]))


_email_limiter = _RateLimiter(max_calls=20, window_s=60.0)

# ──────────────────────────────────────────────────────────────────────────────
# Input helpers
# ──────────────────────────────────────────────────────────────────────────────

def _sanitize_header(value: str) -> str:
    """Strip chars that could inject SMTP headers (CR, LF, NUL)."""
    return re.sub(r"[\r\n\x00]", "", value).strip()


def _validate_email_inputs(
    to: str, subject: str, body: str
) -> tuple[bool, str]:
    if not to:
        return False, "to: must not be empty."
    if len(to) > _MAX_TO_LEN:
        return False, f"to: exceeds RFC 5321 limit of {_MAX_TO_LEN} characters."
    if not _EMAIL_RE.match(to):
        return False, f"to: '{to}' is not a valid email address."
    if not subject:
        return False, "subject: must not be empty."
    if len(subject) > _MAX_SUBJECT_LEN:
        return False, f"subject: exceeds RFC 2822 limit of {_MAX_SUBJECT_LEN} characters."
    if not body:
        return False, "body: must not be empty."
    if len(body.encode()) > _MAX_BODY_BYTES:
        return False, f"body: exceeds maximum size of {_MAX_BODY_BYTES // 1024} KB."
    return True, ""

# ──────────────────────────────────────────────────────────────────────────────
# Startup env validation
# ──────────────────────────────────────────────────────────────────────────────

def _check_env() -> None:
    missing = [v for v in ("EMAIL_ADDRESS", "EMAIL_PASSWORD") if not os.environ.get(v)]
    if missing:
        _log.warning(
            "Missing environment variable(s): %s  — send_email will fail until set.",
            ", ".join(missing),
        )
    else:
        _log.info("Environment OK. Sender: %s", os.environ["EMAIL_ADDRESS"])

# ──────────────────────────────────────────────────────────────────────────────
# Business log  (thread-safe, with rotation)
# ──────────────────────────────────────────────────────────────────────────────

def _rotate_log_if_needed() -> None:
    """Rename business.log when it exceeds _LOG_MAX_BYTES."""
    try:
        if os.path.isfile(_BUSINESS_LOG) and os.path.getsize(_BUSINESS_LOG) >= _LOG_MAX_BYTES:
            ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
            rotated = f"{_BUSINESS_LOG}.{ts}"
            os.rename(_BUSINESS_LOG, rotated)
            _log.info("Rotated business.log → %s", os.path.basename(rotated))
    except OSError as exc:
        _log.warning("Log rotation check failed: %s", exc)


def log_activity(message: str) -> tuple[bool, str]:
    """
    Append a timestamped entry to Logs/business.log.
    Thread-safe; auto-rotates the file at 5 MB.
    Returns (success, human-readable result).
    """
    message = message.strip()
    if not message:
        return False, "message: must not be empty."
    if len(message) > _MAX_LOG_MSG_LEN:
        return False, f"message: exceeds {_MAX_LOG_MSG_LEN} character limit."

    os.makedirs(os.path.dirname(_BUSINESS_LOG), exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    entry = f"[{timestamp}] {message}\n"

    with _log_lock:
        _rotate_log_if_needed()
        try:
            with open(_BUSINESS_LOG, "a", encoding="utf-8") as fh:
                fh.write(entry)
        except OSError as exc:
            _log.error("Failed to write business.log: %s", exc)
            return False, f"Failed to write to business.log: {exc}"

    _log.info("Activity logged: %s", message[:120])
    return True, f"Logged: {entry.strip()}"

# ──────────────────────────────────────────────────────────────────────────────
# Email sending  (with retry + backoff)
# ──────────────────────────────────────────────────────────────────────────────

def _smtp_send(sender: str, password: str, to: str, msg_str: str) -> tuple[bool, str]:
    """
    Attempt SMTP delivery with exponential backoff.
    Auth failures are not retried (permanent error).
    """
    last_error: Exception | None = None

    for attempt, delay in enumerate(_SMTP_RETRY_DELAYS, start=1):
        if delay:
            _log.info("SMTP retry %d/%d — waiting %ds …", attempt, len(_SMTP_RETRY_DELAYS), delay)
            time.sleep(delay)

        try:
            with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=SMTP_TIMEOUT_S) as srv:
                srv.ehlo()
                srv.starttls()
                srv.ehlo()
                srv.login(sender, password)
                srv.sendmail(sender, [to], msg_str)
            return True, ""

        except smtplib.SMTPAuthenticationError:
            # Permanent — don't retry
            return False, "SMTP authentication failed. Verify EMAIL_PASSWORD is a valid Gmail App Password."

        except smtplib.SMTPRecipientsRefused:
            # Permanent for this address
            return False, f"Recipient refused by server: {to}"

        except (smtplib.SMTPException, OSError) as exc:
            last_error = exc
            _log.warning("SMTP attempt %d failed: %s", attempt, exc)

    return False, f"SMTP delivery failed after {len(_SMTP_RETRY_DELAYS)} attempt(s): {last_error}"


def send_email(to: str, subject: str, body: str) -> tuple[bool, str]:
    """
    Send a plain-text email via Gmail SMTP.
    Enforces rate limit, validates inputs, prevents header injection.
    Auto-logs every successful send to business.log.
    Returns (success, human-readable result).
    """
    # Rate limit check
    if not _email_limiter.allow():
        wait = _email_limiter.seconds_until_next()
        return False, f"Rate limit exceeded (max 20 emails/min). Retry in {wait:.0f}s."

    # Input validation
    ok, err = _validate_email_inputs(to, subject, body)
    if not ok:
        return False, err

    sender   = os.environ.get("EMAIL_ADDRESS", "").strip()
    password = os.environ.get("EMAIL_PASSWORD", "").strip()
    if not sender:
        return False, "EMAIL_ADDRESS environment variable not set."
    if not password:
        return False, "EMAIL_PASSWORD environment variable not set."

    # Header-injection prevention
    safe_to      = _sanitize_header(to)
    safe_subject = _sanitize_header(subject)

    msg = MIMEMultipart()
    msg["From"]    = sender
    msg["To"]      = safe_to
    msg["Subject"] = safe_subject
    msg["X-Mailer"] = f"{SERVER_NAME}/{SERVER_VERSION}"
    msg.attach(MIMEText(body, "plain", "utf-8"))

    _log.info("Sending email → %s | subject: %s", safe_to, safe_subject[:60])
    success, err_msg = _smtp_send(sender, password, safe_to, msg.as_string())

    if success:
        log_activity(f"send_email | to={safe_to} | subject={safe_subject} | status=sent")
        _log.info("Email delivered to %s", safe_to)
        return True, f"Email sent successfully to {safe_to}."
    else:
        log_activity(f"send_email | to={safe_to} | subject={safe_subject} | status=failed | error={err_msg}")
        _log.error("Email delivery failed: %s", err_msg)
        return False, err_msg

# ──────────────────────────────────────────────────────────────────────────────
# JSON-RPC helpers
# ──────────────────────────────────────────────────────────────────────────────

def _write(obj: dict) -> None:
    """Write one JSON-RPC message to stdout (MCP transport channel)."""
    sys.stdout.write(json.dumps(obj, ensure_ascii=False) + "\n")
    sys.stdout.flush()


def _ok(req_id, result: dict) -> dict:
    return {"jsonrpc": "2.0", "id": req_id, "result": result}


def _err(req_id, code: int, message: str) -> dict:
    return {"jsonrpc": "2.0", "id": req_id, "error": {"code": code, "message": message}}


def _tool_result(text: str, is_error: bool = False) -> dict:
    return {"content": [{"type": "text", "text": text}], "isError": is_error}

# ──────────────────────────────────────────────────────────────────────────────
# MCP method handlers
# ──────────────────────────────────────────────────────────────────────────────

def handle_initialize(req_id, _params: dict) -> dict:
    _log.info("Client initialized.")
    return _ok(req_id, {
        "protocolVersion": PROTOCOL_VERSION,
        "capabilities":    {"tools": {}},
        "serverInfo":      {"name": SERVER_NAME, "version": SERVER_VERSION},
    })


def handle_ping(req_id, _params: dict) -> dict:
    return _ok(req_id, {"status": "ok", "server": SERVER_NAME, "version": SERVER_VERSION})


def handle_tools_list(req_id, _params: dict) -> dict:
    return _ok(req_id, {"tools": [
        {
            "name": "send_email",
            "description": (
                "Send a plain-text email via Gmail SMTP. "
                "Enforces a rate limit of 20 emails per minute. "
                "Every send (success or failure) is recorded in Logs/business.log. "
                "Requires EMAIL_ADDRESS and EMAIL_PASSWORD environment variables."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "to": {
                        "type":        "string",
                        "description": "Recipient email address (RFC 5321, max 254 chars)",
                        "maxLength":   _MAX_TO_LEN,
                    },
                    "subject": {
                        "type":        "string",
                        "description": "Email subject line (max 998 chars)",
                        "maxLength":   _MAX_SUBJECT_LEN,
                    },
                    "body": {
                        "type":        "string",
                        "description": "Plain-text email body (max 1 MB)",
                    },
                },
                "required":             ["to", "subject", "body"],
                "additionalProperties": False,
            },
        },
        {
            "name": "log_activity",
            "description": (
                "Append a timestamped business activity entry to Logs/business.log. "
                "The log is automatically rotated when it reaches 5 MB. "
                "Message limit: 10 000 characters."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "message": {
                        "type":        "string",
                        "description": "Activity description (max 10 000 chars)",
                        "maxLength":   _MAX_LOG_MSG_LEN,
                    },
                },
                "required":             ["message"],
                "additionalProperties": False,
            },
        },
    ]})


def handle_tools_call(req_id, params: dict) -> dict:
    tool = params.get("name", "")
    args = params.get("arguments") or {}

    # ── send_email ──────────────────────────────────────────────────────────
    if tool == "send_email":
        to      = str(args.get("to",      "")).strip()
        subject = str(args.get("subject", "")).strip()
        body    = str(args.get("body",    "")).strip()
        if not to or not subject or not body:
            return _err(req_id, -32602, "send_email: 'to', 'subject', and 'body' are all required.")
        success, msg = send_email(to, subject, body)
        label = "SUCCESS" if success else "ERROR"
        return _ok(req_id, _tool_result(f"{label}: {msg}", is_error=not success))

    # ── log_activity ─────────────────────────────────────────────────────────
    if tool == "log_activity":
        message = str(args.get("message", "")).strip()
        if not message:
            return _err(req_id, -32602, "log_activity: 'message' is required.")
        success, msg = log_activity(message)
        label = "SUCCESS" if success else "ERROR"
        return _ok(req_id, _tool_result(f"{label}: {msg}", is_error=not success))

    return _err(req_id, -32602, f"Unknown tool: '{tool}'")

# ──────────────────────────────────────────────────────────────────────────────
# MCP dispatch table
# ──────────────────────────────────────────────────────────────────────────────

_HANDLERS: dict[str, callable] = {
    "initialize":  handle_initialize,
    "ping":        handle_ping,
    "tools/list":  handle_tools_list,
    "tools/call":  handle_tools_call,
}

# ──────────────────────────────────────────────────────────────────────────────
# Main loop  (stdio transport, newline-delimited JSON-RPC)
# ──────────────────────────────────────────────────────────────────────────────

def main() -> None:
    _log.info("%s v%s starting (vault: %s)", SERVER_NAME, SERVER_VERSION, _VAULT_ROOT)
    _check_env()

    for raw in sys.stdin:
        if _shutdown.is_set():
            break

        line = raw.strip()
        if not line:
            continue

        # Parse
        try:
            msg = json.loads(line)
        except json.JSONDecodeError as exc:
            _log.warning("JSON parse error: %s | raw: %.120s", exc, line)
            _write(_err(None, -32700, f"Parse error: {exc}"))
            continue

        if not isinstance(msg, dict):
            _write(_err(None, -32600, "Invalid Request: expected a JSON object."))
            continue

        method = msg.get("method", "")
        req_id = msg.get("id")
        params = msg.get("params") or {}

        # MCP notifications — fire-and-forget, no response
        if method.startswith("notifications/"):
            _log.debug("Notification received: %s", method)
            continue

        handler = _HANDLERS.get(method)
        if handler is None:
            _log.warning("Unknown method: %s", method)
            if req_id is not None:
                _write(_err(req_id, -32601, f"Method not found: '{method}'"))
            continue

        # Dispatch — guard against unexpected handler exceptions
        try:
            response = handler(req_id, params)
        except Exception as exc:                       # noqa: BLE001
            _log.exception("Unhandled exception in handler for '%s': %s", method, exc)
            if req_id is not None:
                _write(_err(req_id, -32603, f"Internal error: {exc}"))
            continue

        if response is not None and req_id is not None:
            _write(response)

    _log.info("%s shut down.", SERVER_NAME)


if __name__ == "__main__":
    main()
