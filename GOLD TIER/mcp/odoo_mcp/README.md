# odoo-mcp v1.0.0

MCP server for Odoo Community accounting integration.
Exposes Odoo accounting operations as Claude Code tools via JSON-RPC 2.0 over stdio.

---

## Prerequisites

1. **Odoo Community 17+ installed and running locally**
   - Download: https://www.odoo.com/page/community
   - Default URL: http://localhost:8069
   - Windows installer: https://nightly.odoo.com/

2. **An Odoo database created** with the Accounting module installed

3. **An Odoo user account** with accounting access rights

---

## Quick Odoo Setup (Windows)

```bash
# Option A: Docker (recommended for development)
docker run -d -p 8069:8069 --name odoo \
  -e POSTGRES_USER=odoo -e POSTGRES_PASSWORD=odoo \
  odoo:17.0

# Option B: Native installer
# Download from https://nightly.odoo.com/17.0/nightly/exe/
# Run the installer, it sets up PostgreSQL and Odoo automatically
```

After installation:
1. Open http://localhost:8069 in your browser
2. Create a database (e.g. `mycompany`)
3. Install the **Accounting** module from Apps
4. Note your admin username and password

---

## Configuration

Add to your `.env` file:

```
ODOO_URL=http://localhost:8069
ODOO_DB=mycompany
ODOO_USERNAME=admin
ODOO_PASSWORD=your_odoo_admin_password
```

The `ODOO_URL` and `ODOO_USERNAME` have defaults (`http://localhost:8069` and `admin`)
so only `ODOO_DB` and `ODOO_PASSWORD` are strictly required.

---

## Registration in Claude Code

The server is already registered in `.claude/settings.json`:

```json
"odoo-mcp": {
  "command": "python",
  "args": ["mcp/odoo_mcp/server.py"],
  "env": {
    "ODOO_URL":      "${ODOO_URL}",
    "ODOO_DB":       "${ODOO_DB}",
    "ODOO_USERNAME": "${ODOO_USERNAME}",
    "ODOO_PASSWORD": "${ODOO_PASSWORD}"
  }
}
```

---

## Available Tools

| Tool | Description |
|------|-------------|
| `odoo_health_check` | Ping Odoo server and verify credentials |
| `odoo_get_invoices` | List customer invoices (filter by state/limit) |
| `odoo_create_invoice` | Create a new draft customer invoice |
| `odoo_get_vendor_bills` | List vendor bills / expenses |
| `odoo_accounting_summary` | Asset/liability/income/expense balances + net profit |
| `odoo_create_journal_entry` | Post a manual journal entry (must balance) |

---

## Tool Examples (from Claude Code)

### Health check
```
Use odoo_health_check to verify the Odoo connection.
```
Returns: server version, database name, authenticated user ID.

### List invoices
```
Use odoo_get_invoices with state="posted" and limit=10 to show the 10 most recent paid invoices.
```

### Create an invoice
```
Use odoo_create_invoice with:
  partner_name = "Acme Corp"
  amount = 1500.00
  description = "Consulting services - February 2026"
  currency_code = "USD"
```

### Accounting summary (for CEO briefing)
```
Use odoo_accounting_summary to get current account balances.
```
Returns: totals per category (asset, liability, income, expense, equity) + net_profit.

### Journal entry
```
Use odoo_create_journal_entry with:
  ref = "Accrual - Feb 2026"
  journal_code = "MISC"
  lines = [
    {"account_code": "5000", "label": "Office supplies", "debit": 200.00, "credit": 0},
    {"account_code": "1010", "label": "Cash", "debit": 0, "credit": 200.00}
  ]
```
Lines must balance (total debit == total credit).

---

## Smoke Test

With Odoo running and `.env` configured:

```bash
cd "C:\Users\Dell\Desktop\Hackathon_0\GOLD TIER"

printf '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2024-11-05","capabilities":{},"clientInfo":{"name":"test","version":"1.0"}}}\n{"jsonrpc":"2.0","id":2,"method":"tools/call","params":{"name":"odoo_health_check","arguments":{}}}\n' | python mcp/odoo_mcp/server.py
```

Expected output (to stdout):
```json
{"jsonrpc":"2.0","id":1,"result":{"protocolVersion":"2024-11-05",...}}
{"jsonrpc":"2.0","id":2,"result":{"content":[{"type":"text","text":"{\"status\": \"ok\",...}"}]}}
```

---

## Odoo Account Codes Reference

Common account codes in a standard Odoo chart of accounts:

| Code | Account Name |
|------|-------------|
| 1010 | Cash |
| 1100 | Accounts Receivable |
| 1200 | Bank |
| 2000 | Accounts Payable |
| 3000 | Owner's Equity |
| 4000 | Sales Revenue |
| 5000 | Cost of Goods Sold |
| 6000 | Operating Expenses |

Run `odoo_accounting_summary` to see your actual chart of accounts balances.

---

## Troubleshooting

| Error | Cause | Fix |
|-------|-------|-----|
| `Cannot reach Odoo at http://localhost:8069` | Odoo not running | Start Odoo service |
| `Authentication failed` | Wrong DB/username/password | Check .env values |
| `Partner not found: 'Acme Corp'` | Partner not in Odoo | Create partner in Odoo Contacts |
| `Account not found with code '1010'` | Different chart of accounts | Check your Odoo account codes |
| `Journal entry does not balance` | Debits != Credits | Fix line amounts |

---

## Architecture Notes

- **No pip dependencies** — uses stdlib `urllib.request` for all HTTP
- **Stateless authentication** — credentials sent per-request (no session cookies)
- **Thread-safe** — single-threaded MCP server (one request at a time)
- **Graceful degradation** — returns descriptive error text (not exceptions) when Odoo is unreachable
- **MCP protocol** — 2024-11-05 spec, compatible with Claude Code's built-in MCP client
