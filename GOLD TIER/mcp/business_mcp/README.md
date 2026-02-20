# business-mcp  v2.0.0

Production-ready MCP server for external business actions.

| | |
|---|---|
| **Transport** | JSON-RPC 2.0 over stdio |
| **Protocol** | MCP 2024-11-05 |
| **Dependencies** | Python ≥ 3.11 — stdlib only, no pip installs |
| **Entry point** | `mcp/business_mcp/server.py` |

---

## Tools

### `send_email`

Send a plain-text email via Gmail SMTP.

| Parameter | Type | Required | Limit | Description |
|-----------|------|----------|-------|-------------|
| `to` | string | yes | 254 chars (RFC 5321) | Recipient email address |
| `subject` | string | yes | 998 chars (RFC 2822) | Email subject line |
| `body` | string | yes | 1 MB | Plain-text email body |

**Behaviour:**
- Validates input before connecting to SMTP
- Strips `\r`, `\n`, `\x00` from headers to prevent injection attacks
- Retries up to 3 times with backoff (0 s → 3 s → 8 s) on transient SMTP errors
- Auth failures are not retried (permanent error)
- Enforces a sliding-window rate limit: **20 emails per 60 seconds**
- Appends a record to `Logs/business.log` for every attempt (success **and** failure)

---

### `log_activity`

Append a timestamped entry to `Logs/business.log`.

| Parameter | Type | Required | Limit | Description |
|-----------|------|----------|-------|-------------|
| `message` | string | yes | 10 000 chars | Activity description |

**Behaviour:**
- Thread-safe (internal `threading.Lock`)
- Auto-rotates `business.log` when it reaches **5 MB** (renamed to `business.log.YYYYMMDD_HHMMSS`)
- Creates `Logs/` directory if it does not exist

**Log format:**
```
[YYYY-MM-DD HH:MM:SS UTC] <message>
```

---

### `ping`

Health-check endpoint.

```json
→ {"jsonrpc":"2.0","id":1,"method":"ping","params":{}}
← {"jsonrpc":"2.0","id":1,"result":{"status":"ok","server":"business-mcp","version":"2.0.0"}}
```

---

## Production Features

| Feature | Detail |
|---------|--------|
| **Structured logging** | JSON-formatted lines → stderr; stdout is the MCP channel only |
| **SMTP retry + backoff** | 3 attempts with 0 / 3 / 8 s delays |
| **Header injection prevention** | CR, LF, NUL stripped from `To` and `Subject` |
| **Input validation** | RFC 5321/2822 length limits enforced before SMTP connection |
| **Rate limiting** | Sliding-window: 20 emails / 60 s, thread-safe |
| **Thread-safe log writes** | `threading.Lock` around all `business.log` writes |
| **Log rotation** | Auto-renames at 5 MB, no external cron needed |
| **Graceful shutdown** | `SIGTERM` / `SIGINT` handled; main loop drains then exits cleanly |
| **Exception safety** | Unhandled handler exceptions return JSON-RPC `-32603` instead of crashing |
| **Startup validation** | Warns to stderr if `EMAIL_ADDRESS` / `EMAIL_PASSWORD` are missing |
| **No pip dependencies** | Runs on any Python ≥ 3.11 with no installs |

---

## Environment Variables

Set these in the vault's `.env` file **or** your shell environment.

| Variable | Required by | Description |
|----------|-------------|-------------|
| `EMAIL_ADDRESS` | `send_email` | Gmail sender address |
| `EMAIL_PASSWORD` | `send_email` | Gmail **App Password** (16 chars) — not your account password |

### Generating a Gmail App Password

1. Go to [myaccount.google.com/security](https://myaccount.google.com/security).
2. Enable **2-Step Verification**.
3. Search for **App Passwords** and create one for "Mail / Other".
4. Paste the 16-character token into `.env` as `EMAIL_PASSWORD`.

---

## Registration in Claude Code

`business-mcp` is already registered in `.claude/settings.json`:

```json
"business-mcp": {
  "command": "python",
  "args": ["mcp/business_mcp/server.py"],
  "env": {
    "EMAIL_ADDRESS": "${EMAIL_ADDRESS}",
    "EMAIL_PASSWORD": "${EMAIL_PASSWORD}"
  }
}
```

Claude Code launches it automatically on startup.

---

## Manual Testing

All tests send newline-delimited JSON to stdin.

**Ping (health check):**
```bash
printf '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2024-11-05","capabilities":{},"clientInfo":{"name":"test","version":"1.0"}}}\n{"jsonrpc":"2.0","id":2,"method":"ping","params":{}}\n' \
  | python mcp/business_mcp/server.py
```

**List tools:**
```bash
printf '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2024-11-05","capabilities":{},"clientInfo":{"name":"test","version":"1.0"}}}\n{"jsonrpc":"2.0","id":2,"method":"tools/list","params":{}}\n' \
  | python mcp/business_mcp/server.py
```

**Log an activity:**
```bash
printf '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2024-11-05","capabilities":{},"clientInfo":{"name":"test","version":"1.0"}}}\n{"jsonrpc":"2.0","id":2,"method":"tools/call","params":{"name":"log_activity","arguments":{"message":"Deployment completed"}}}\n' \
  | python mcp/business_mcp/server.py
```

**Send an email** (requires `.env` to be configured):
```bash
printf '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2024-11-05","capabilities":{},"clientInfo":{"name":"test","version":"1.0"}}}\n{"jsonrpc":"2.0","id":2,"method":"tools/call","params":{"name":"send_email","arguments":{"to":"you@example.com","subject":"Test","body":"Hello from business-mcp v2"}}}\n' \
  | python mcp/business_mcp/server.py
```

Expected stderr on startup (credentials present):
```
2026-02-19 12:00:00 [INFO] business-mcp: business-mcp v2.0.0 starting (vault: /path/to/vault)
2026-02-19 12:00:00 [INFO] business-mcp: Environment OK. Sender: aiemployees0@gmail.com
```

---

## File Layout

```
mcp/business_mcp/
├── server.py      ← MCP server (single file, no external deps)
└── README.md      ← This file

Logs/
└── business.log   ← Auto-created; rotated at 5 MB
```

---

## Error Reference

| JSON-RPC code | Meaning |
|---------------|---------|
| `-32700` | Parse error — malformed JSON |
| `-32600` | Invalid Request — not a JSON object |
| `-32601` | Method not found |
| `-32602` | Invalid params — missing or out-of-range argument |
| `-32603` | Internal error — unexpected handler exception |
