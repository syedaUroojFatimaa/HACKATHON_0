"""
server.py — odoo-mcp v1.0.0
MCP server for Odoo Community accounting integration.

Transport  : JSON-RPC 2.0 over stdio  (MCP protocol version 2024-11-05)
Backend    : Odoo Community (self-hosted) via Odoo JSON-RPC API (/jsonrpc)
Diagnostics: structured logs -> stderr   <- never stdout (that is the MCP channel)

Tools exposed:
  odoo_health_check       — Ping Odoo server and verify credentials
  odoo_get_invoices       — List customer invoices (filterable by state/limit)
  odoo_create_invoice     — Create a new draft customer invoice
  odoo_get_vendor_bills   — List vendor bills/expenses
  odoo_accounting_summary — Get account balances and P&L overview
  odoo_create_journal_entry — Post a manual journal entry

Environment variables (loaded from .env at vault root, or set in shell):
  ODOO_URL       — Odoo server URL (default: http://localhost:8069)
  ODOO_DB        — Odoo database name (required)
  ODOO_USERNAME  — Odoo login username (default: admin)
  ODOO_PASSWORD  — Odoo login password (required)

Usage (launched automatically by Claude Code via .claude/settings.json):
  python mcp/odoo_mcp/server.py

Smoke test (requires Odoo running locally):
  printf '{\"jsonrpc\":\"2.0\",\"id\":1,\"method\":\"initialize\",\"params\":{\"protocolVersion\":\"2024-11-05\",\"capabilities\":{},\"clientInfo\":{\"name\":\"test\",\"version\":\"1.0\"}}}\\n{\"jsonrpc\":\"2.0\",\"id\":2,\"method\":\"tools/call\",\"params\":{\"name\":\"odoo_health_check\",\"arguments\":{}}}\\n' | python mcp/odoo_mcp/server.py
"""

from __future__ import annotations

import json
import logging
import os
import signal
import sys
import threading
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

_VAULT_ROOT = os.path.abspath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..")
)
_ENV_PATH   = os.path.join(_VAULT_ROOT, ".env")

# ---------------------------------------------------------------------------
# Load .env
# ---------------------------------------------------------------------------

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

# ---------------------------------------------------------------------------
# Structured stderr logger (stdout is the MCP channel — never write there)
# ---------------------------------------------------------------------------

logging.basicConfig(
    stream=sys.stderr,
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
_log = logging.getLogger("odoo-mcp")

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

PROTOCOL_VERSION = "2024-11-05"
SERVER_NAME      = "odoo-mcp"
SERVER_VERSION   = "1.0.0"

_DEFAULT_ODOO_URL      = "http://localhost:8069"
_DEFAULT_ODOO_USERNAME = "admin"
_RPC_TIMEOUT_S         = 30

# ---------------------------------------------------------------------------
# Graceful shutdown
# ---------------------------------------------------------------------------

_shutdown = threading.Event()

def _on_signal(signum: int, _frame) -> None:
    _log.info("Signal %d received — shutting down gracefully.", signum)
    _shutdown.set()

signal.signal(signal.SIGTERM, _on_signal)
signal.signal(signal.SIGINT,  _on_signal)

# ---------------------------------------------------------------------------
# Odoo JSON-RPC client
# ---------------------------------------------------------------------------

class OdooClient:
    """
    Minimal stateless Odoo JSON-RPC client using stdlib urllib.
    Uses the /jsonrpc endpoint (service=common for auth, service=object for model calls).
    No session cookies required — password is sent on every request.
    """

    def __init__(self) -> None:
        self.url      = os.environ.get("ODOO_URL", _DEFAULT_ODOO_URL).rstrip("/")
        self.db       = os.environ.get("ODOO_DB", "")
        self.username = os.environ.get("ODOO_USERNAME", _DEFAULT_ODOO_USERNAME)
        self.password = os.environ.get("ODOO_PASSWORD", "")
        self._uid: int | None = None
        self._uid_lock = threading.Lock()

    # ---- internal RPC -------------------------------------------------------

    def _rpc(self, service: str, method: str, args: list) -> object:
        """
        Call Odoo JSON-RPC endpoint.
        Raises OdooError on Odoo-level faults.
        Raises urllib.error.URLError / OSError on network failures.
        """
        payload = json.dumps({
            "jsonrpc": "2.0",
            "method":  "call",
            "id":      1,
            "params":  {
                "service": service,
                "method":  method,
                "args":    args,
            },
        }).encode("utf-8")

        req = urllib.request.Request(
            f"{self.url}/jsonrpc",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=_RPC_TIMEOUT_S) as resp:
            body = json.loads(resp.read().decode("utf-8"))

        if "error" in body:
            err   = body["error"]
            data  = err.get("data", {})
            msg   = data.get("message") or data.get("name") or err.get("message") or str(err)
            raise OdooError(msg)

        return body.get("result")

    def _authenticate(self) -> int:
        """Authenticate and return uid. Caches for the process lifetime."""
        with self._uid_lock:
            if self._uid is not None:
                return self._uid
            uid = self._rpc("common", "authenticate",
                            [self.db, self.username, self.password, {}])
            if not uid:
                raise OdooError(
                    "Authentication failed — check ODOO_DB, ODOO_USERNAME, ODOO_PASSWORD."
                )
            self._uid = uid
            _log.info("Authenticated as uid=%d on db='%s'", uid, self.db)
            return uid

    def execute_kw(self, model: str, method: str,
                   args: list, kwargs: dict | None = None) -> object:
        """Execute a model method via object.execute_kw."""
        uid = self._authenticate()
        return self._rpc("object", "execute_kw", [
            self.db, uid, self.password,
            model, method, args, kwargs or {},
        ])

    # ---- health -------------------------------------------------------------

    def ping(self) -> dict:
        """Return server version info without authenticating."""
        result = self._rpc("common", "version", [])
        return result if isinstance(result, dict) else {"raw": str(result)}

    def health_check(self) -> dict:
        """Ping + authenticate, return server info and uid."""
        version = self.ping()
        uid     = self._authenticate()
        return {
            "status":         "ok",
            "odoo_url":       self.url,
            "odoo_db":        self.db,
            "odoo_version":   version.get("server_version", "unknown"),
            "uid":            uid,
            "authenticated":  True,
        }

    # ---- invoices -----------------------------------------------------------

    def get_invoices(self, state: str = "all", limit: int = 20) -> list:
        """
        Retrieve customer invoices (account.move, move_type=out_invoice).
        state: 'all' | 'draft' | 'posted' | 'cancel'
        """
        domain: list = [["move_type", "=", "out_invoice"]]
        if state != "all":
            domain.append(["state", "=", state])

        return self.execute_kw(
            "account.move", "search_read",
            [domain],
            {
                "fields": ["name", "partner_id", "invoice_date", "amount_total",
                           "currency_id", "state", "payment_state"],
                "limit":  limit,
                "order":  "invoice_date desc",
            },
        )

    def create_invoice(self, partner_name: str, amount: float,
                       description: str, currency_code: str = "USD") -> dict:
        """
        Create a draft customer invoice.
        Returns the new invoice id and name.
        """
        # Resolve partner
        partners = self.execute_kw(
            "res.partner", "search_read",
            [[["name", "ilike", partner_name]]],
            {"fields": ["id", "name"], "limit": 1},
        )
        if not partners:
            raise OdooError(f"Partner not found: '{partner_name}'")
        partner_id = partners[0]["id"]

        # Resolve currency
        currencies = self.execute_kw(
            "res.currency", "search_read",
            [[["name", "=", currency_code.upper()]]],
            {"fields": ["id", "name"], "limit": 1},
        )
        currency_id = currencies[0]["id"] if currencies else False

        # Create invoice
        vals = {
            "move_type":  "out_invoice",
            "partner_id": partner_id,
            "invoice_line_ids": [(0, 0, {
                "name":      description,
                "quantity":  1,
                "price_unit": amount,
            })],
        }
        if currency_id:
            vals["currency_id"] = currency_id

        inv_id = self.execute_kw("account.move", "create", [[vals]])
        # Fetch the created invoice's name
        inv    = self.execute_kw(
            "account.move", "read", [[inv_id]],
            {"fields": ["name", "state", "amount_total"]},
        )
        record = inv[0] if inv else {}
        return {
            "id":          inv_id,
            "name":        record.get("name", ""),
            "state":       record.get("state", "draft"),
            "amount_total": record.get("amount_total", amount),
            "partner":     partners[0]["name"],
        }

    # ---- vendor bills -------------------------------------------------------

    def get_vendor_bills(self, state: str = "all", limit: int = 20) -> list:
        """
        Retrieve vendor bills (account.move, move_type=in_invoice).
        state: 'all' | 'draft' | 'posted' | 'cancel'
        """
        domain: list = [["move_type", "=", "in_invoice"]]
        if state != "all":
            domain.append(["state", "=", state])

        return self.execute_kw(
            "account.move", "search_read",
            [domain],
            {
                "fields": ["name", "partner_id", "invoice_date", "amount_total",
                           "currency_id", "state", "payment_state"],
                "limit":  limit,
                "order":  "invoice_date desc",
            },
        )

    # ---- accounting summary -------------------------------------------------

    def accounting_summary(self) -> dict:
        """
        Pull account balances for asset, liability, income, and expense account types.
        Returns a summary dict suitable for CEO briefing / audit.
        """
        # Fetch account groups with their balances
        accounts = self.execute_kw(
            "account.account", "search_read",
            [[["deprecated", "=", False]]],
            {
                "fields": ["name", "code", "account_type", "current_balance"],
                "limit":  500,
            },
        )

        summary: dict = {
            "asset":     {"count": 0, "balance": 0.0},
            "liability": {"count": 0, "balance": 0.0},
            "income":    {"count": 0, "balance": 0.0},
            "expense":   {"count": 0, "balance": 0.0},
            "equity":    {"count": 0, "balance": 0.0},
            "other":     {"count": 0, "balance": 0.0},
        }

        _TYPE_MAP = {
            "asset_receivable":     "asset",
            "asset_cash":           "asset",
            "asset_current":        "asset",
            "asset_non_current":    "asset",
            "asset_prepayments":    "asset",
            "asset_fixed":          "asset",
            "liability_payable":    "liability",
            "liability_credit_card":"liability",
            "liability_current":    "liability",
            "liability_non_current":"liability",
            "income":               "income",
            "income_other":         "income",
            "expense":              "expense",
            "expense_depreciation": "expense",
            "expense_direct_cost":  "expense",
            "equity":               "equity",
            "equity_unaffected":    "equity",
            "off_balance":          "other",
        }

        for acc in accounts:
            acc_type = acc.get("account_type", "other")
            bucket   = _TYPE_MAP.get(acc_type, "other")
            summary[bucket]["count"]   += 1
            summary[bucket]["balance"] += float(acc.get("current_balance") or 0)

        # Derived P&L
        summary["net_profit"] = (
            summary["income"]["balance"] - summary["expense"]["balance"]
        )
        return summary

    # ---- journal entry ------------------------------------------------------

    def create_journal_entry(self, ref: str, lines: list,
                              journal_code: str = "MISC") -> dict:
        """
        Post a manual journal entry.

        lines: list of dicts with keys:
          account_code (str), label (str), debit (float), credit (float)

        Returns: {"id": int, "name": str, "state": str}
        """
        # Resolve journal
        journals = self.execute_kw(
            "account.journal", "search_read",
            [[["code", "=", journal_code.upper()]]],
            {"fields": ["id", "name"], "limit": 1},
        )
        if not journals:
            raise OdooError(f"Journal not found with code '{journal_code}'")
        journal_id = journals[0]["id"]

        # Resolve accounts
        line_vals = []
        for line in lines:
            code = str(line.get("account_code", "")).strip()
            accounts = self.execute_kw(
                "account.account", "search_read",
                [[["code", "=", code]]],
                {"fields": ["id", "name"], "limit": 1},
            )
            if not accounts:
                raise OdooError(f"Account not found with code '{code}'")
            line_vals.append((0, 0, {
                "account_id": accounts[0]["id"],
                "name":       str(line.get("label", ref)),
                "debit":      float(line.get("debit", 0)),
                "credit":     float(line.get("credit", 0)),
            }))

        # Create and post the entry
        entry_id = self.execute_kw("account.move", "create", [[{
            "journal_id":     journal_id,
            "ref":            ref,
            "move_type":      "entry",
            "line_ids":       line_vals,
        }]])

        # Post (validate) the entry
        self.execute_kw("account.move", "action_post", [[entry_id]])

        entry = self.execute_kw(
            "account.move", "read", [[entry_id]],
            {"fields": ["name", "state"]},
        )
        record = entry[0] if entry else {}
        return {
            "id":    entry_id,
            "name":  record.get("name", ""),
            "state": record.get("state", "posted"),
        }


class OdooError(Exception):
    """Odoo application-level error."""


# Shared client instance (connection params reloaded from env on each request)
_odoo = OdooClient()

# ---------------------------------------------------------------------------
# JSON-RPC / MCP helpers
# ---------------------------------------------------------------------------

def _write(obj: dict) -> None:
    sys.stdout.write(json.dumps(obj, ensure_ascii=False) + "\n")
    sys.stdout.flush()

def _ok(req_id, result: dict) -> dict:
    return {"jsonrpc": "2.0", "id": req_id, "result": result}

def _err(req_id, code: int, message: str) -> dict:
    return {"jsonrpc": "2.0", "id": req_id, "error": {"code": code, "message": message}}

def _tool_result(text: str, is_error: bool = False) -> dict:
    return {"content": [{"type": "text", "text": text}], "isError": is_error}

def _tool_ok(data) -> dict:
    return _tool_result(json.dumps(data, indent=2, ensure_ascii=False, default=str))

def _tool_err(msg: str) -> dict:
    return _tool_result(f"ERROR: {msg}", is_error=True)

# ---------------------------------------------------------------------------
# MCP method handlers
# ---------------------------------------------------------------------------

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
    tools = [
        {
            "name": "odoo_health_check",
            "description": (
                "Ping the Odoo server and verify authentication credentials. "
                "Returns server version, database name, and authenticated user ID."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {},
                "required": [],
                "additionalProperties": False,
            },
        },
        {
            "name": "odoo_get_invoices",
            "description": (
                "List customer invoices from Odoo. "
                "Optionally filter by state (all/draft/posted/cancel) and limit results."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "state": {
                        "type":        "string",
                        "description": "Invoice state filter: 'all', 'draft', 'posted', 'cancel'",
                        "enum":        ["all", "draft", "posted", "cancel"],
                        "default":     "all",
                    },
                    "limit": {
                        "type":        "integer",
                        "description": "Maximum number of invoices to return (default 20)",
                        "default":     20,
                        "minimum":     1,
                        "maximum":     200,
                    },
                },
                "required":             [],
                "additionalProperties": False,
            },
        },
        {
            "name": "odoo_create_invoice",
            "description": (
                "Create a new draft customer invoice in Odoo. "
                "The partner must already exist in Odoo's contact list."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "partner_name": {
                        "type":        "string",
                        "description": "Name of the customer (must match an existing Odoo partner)",
                    },
                    "amount": {
                        "type":        "number",
                        "description": "Invoice line amount (unit price)",
                    },
                    "description": {
                        "type":        "string",
                        "description": "Invoice line description / product name",
                    },
                    "currency_code": {
                        "type":        "string",
                        "description": "ISO 4217 currency code (e.g. 'USD', 'EUR'). Default: 'USD'",
                        "default":     "USD",
                    },
                },
                "required":             ["partner_name", "amount", "description"],
                "additionalProperties": False,
            },
        },
        {
            "name": "odoo_get_vendor_bills",
            "description": (
                "List vendor bills (expenses/purchases) from Odoo. "
                "Optionally filter by state and limit results."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "state": {
                        "type":        "string",
                        "description": "Bill state filter: 'all', 'draft', 'posted', 'cancel'",
                        "enum":        ["all", "draft", "posted", "cancel"],
                        "default":     "all",
                    },
                    "limit": {
                        "type":        "integer",
                        "description": "Maximum number of bills to return (default 20)",
                        "default":     20,
                        "minimum":     1,
                        "maximum":     200,
                    },
                },
                "required":             [],
                "additionalProperties": False,
            },
        },
        {
            "name": "odoo_accounting_summary",
            "description": (
                "Get a high-level accounting summary from Odoo: "
                "asset, liability, income, expense, and equity balances, "
                "plus derived net profit. Suitable for CEO briefings and audits."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {},
                "required": [],
                "additionalProperties": False,
            },
        },
        {
            "name": "odoo_create_journal_entry",
            "description": (
                "Post a manual journal entry in Odoo. "
                "Lines must balance (total debits == total credits). "
                "Each line references an account by its code (e.g. '1010', '5000')."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "ref": {
                        "type":        "string",
                        "description": "Reference / description for the journal entry",
                    },
                    "journal_code": {
                        "type":        "string",
                        "description": "Journal code in Odoo (e.g. 'MISC', 'BNK1'). Default: 'MISC'",
                        "default":     "MISC",
                    },
                    "lines": {
                        "type":        "array",
                        "description": "Journal lines (must balance)",
                        "items": {
                            "type": "object",
                            "properties": {
                                "account_code": {"type": "string",
                                                 "description": "Account code (e.g. '1010')"},
                                "label":        {"type": "string",
                                                 "description": "Line description"},
                                "debit":        {"type": "number", "minimum": 0},
                                "credit":       {"type": "number", "minimum": 0},
                            },
                            "required": ["account_code", "debit", "credit"],
                        },
                        "minItems": 2,
                    },
                },
                "required":             ["ref", "lines"],
                "additionalProperties": False,
            },
        },
    ]
    return _ok(req_id, {"tools": tools})


def handle_tools_call(req_id, params: dict) -> dict:
    tool = params.get("name", "")
    args = params.get("arguments") or {}

    try:
        # ── odoo_health_check ────────────────────────────────────────────────
        if tool == "odoo_health_check":
            result = _odoo.health_check()
            return _ok(req_id, _tool_ok(result))

        # ── odoo_get_invoices ────────────────────────────────────────────────
        elif tool == "odoo_get_invoices":
            state  = str(args.get("state",  "all"))
            limit  = int(args.get("limit",  20))
            result = _odoo.get_invoices(state=state, limit=limit)
            return _ok(req_id, _tool_ok({"count": len(result), "invoices": result}))

        # ── odoo_create_invoice ──────────────────────────────────────────────
        elif tool == "odoo_create_invoice":
            partner  = str(args.get("partner_name",  "")).strip()
            amount   = float(args.get("amount",       0))
            desc     = str(args.get("description",    "")).strip()
            currency = str(args.get("currency_code",  "USD")).strip()
            if not partner:
                return _ok(req_id, _tool_err("partner_name is required."))
            if amount <= 0:
                return _ok(req_id, _tool_err("amount must be a positive number."))
            if not desc:
                return _ok(req_id, _tool_err("description is required."))
            result = _odoo.create_invoice(partner, amount, desc, currency)
            return _ok(req_id, _tool_ok(result))

        # ── odoo_get_vendor_bills ────────────────────────────────────────────
        elif tool == "odoo_get_vendor_bills":
            state  = str(args.get("state",  "all"))
            limit  = int(args.get("limit",  20))
            result = _odoo.get_vendor_bills(state=state, limit=limit)
            return _ok(req_id, _tool_ok({"count": len(result), "bills": result}))

        # ── odoo_accounting_summary ──────────────────────────────────────────
        elif tool == "odoo_accounting_summary":
            result = _odoo.accounting_summary()
            return _ok(req_id, _tool_ok(result))

        # ── odoo_create_journal_entry ────────────────────────────────────────
        elif tool == "odoo_create_journal_entry":
            ref          = str(args.get("ref",          "")).strip()
            journal_code = str(args.get("journal_code", "MISC")).strip()
            lines        = args.get("lines", [])
            if not ref:
                return _ok(req_id, _tool_err("ref is required."))
            if len(lines) < 2:
                return _ok(req_id, _tool_err("At least 2 journal lines required."))
            # Verify lines balance
            total_debit  = sum(float(l.get("debit",  0)) for l in lines)
            total_credit = sum(float(l.get("credit", 0)) for l in lines)
            if abs(total_debit - total_credit) > 0.01:
                return _ok(req_id, _tool_err(
                    f"Journal entry does not balance: "
                    f"debit={total_debit:.2f} credit={total_credit:.2f}"
                ))
            result = _odoo.create_journal_entry(ref, lines, journal_code)
            return _ok(req_id, _tool_ok(result))

        else:
            return _err(req_id, -32602, f"Unknown tool: '{tool}'")

    except OdooError as exc:
        _log.warning("Odoo error in tool '%s': %s", tool, exc)
        return _ok(req_id, _tool_err(str(exc)))

    except (urllib.error.URLError, OSError, TimeoutError) as exc:
        _log.error("Network error reaching Odoo in tool '%s': %s", tool, exc)
        return _ok(req_id, _tool_err(
            f"Cannot reach Odoo at {_odoo.url}. "
            f"Is Odoo running? Error: {exc}"
        ))


# ---------------------------------------------------------------------------
# Dispatch table
# ---------------------------------------------------------------------------

_HANDLERS: dict = {
    "initialize":  handle_initialize,
    "ping":        handle_ping,
    "tools/list":  handle_tools_list,
    "tools/call":  handle_tools_call,
}

# ---------------------------------------------------------------------------
# Main loop — stdio transport, newline-delimited JSON-RPC
# ---------------------------------------------------------------------------

def _check_env() -> None:
    missing = [v for v in ("ODOO_DB", "ODOO_PASSWORD") if not os.environ.get(v)]
    if missing:
        _log.warning(
            "Missing environment variable(s): %s  — Odoo tools will fail until set.",
            ", ".join(missing),
        )
    else:
        _log.info(
            "Odoo config: url=%s db=%s user=%s",
            os.environ.get("ODOO_URL", _DEFAULT_ODOO_URL),
            os.environ.get("ODOO_DB", ""),
            os.environ.get("ODOO_USERNAME", _DEFAULT_ODOO_USERNAME),
        )


def main() -> None:
    _log.info("%s v%s starting (vault: %s)", SERVER_NAME, SERVER_VERSION, _VAULT_ROOT)
    _check_env()

    for raw in sys.stdin:
        if _shutdown.is_set():
            break

        line = raw.strip()
        if not line:
            continue

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

        if method.startswith("notifications/"):
            _log.debug("Notification received: %s", method)
            continue

        handler = _HANDLERS.get(method)
        if handler is None:
            _log.warning("Unknown method: %s", method)
            if req_id is not None:
                _write(_err(req_id, -32601, f"Method not found: '{method}'"))
            continue

        try:
            response = handler(req_id, params)
        except Exception as exc:
            _log.exception("Unhandled exception in handler for '%s': %s", method, exc)
            if req_id is not None:
                _write(_err(req_id, -32603, f"Internal error: {exc}"))
            continue

        if response is not None and req_id is not None:
            _write(response)

    _log.info("%s shut down.", SERVER_NAME)


if __name__ == "__main__":
    main()
