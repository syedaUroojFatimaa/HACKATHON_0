# Gold Tier AI Employee — Architecture & Lessons Learned

## 1. System Overview

The Gold Tier AI Employee is an autonomous, event-driven agent system built entirely inside an **Obsidian vault**. Claude Code (the AI agent) reads from and writes to the vault using native file tools, while external actions (email, social media, accounting) are handled by specialised Agent Skills and MCP servers.

The system is designed around five principles:
- **File-as-message-queue** — every task, approval, and log entry is a plain Markdown file
- **Exactly-once processing** — state ledger JSON files prevent duplicate processing
- **Graceful degradation** — every skill reports clearly when unconfigured; nothing crashes the scheduler
- **Human-in-the-loop** — sensitive actions require explicit APPROVED/REJECTED before execution
- **Stdlib-first** — external pip dependencies are minimised; most skills use only Python standard library

---

## 2. High-Level Architecture

```
+---------------------------------------------------------------+
|                      OBSIDIAN VAULT                           |
|                                                               |
|  Inbox/          Needs_Action/     Needs_Approval/   Done/   |
|  [drop zone] --> [task queue]  --> [approval gate] -> [archive]|
|                      |                    |                   |
|                      v                    v                   |
|              ralph-wiggum-loop      human-approval            |
|              (step executor)        (blocking gate)           |
|                      |                                        |
|              error-recovery                                   |
|              (stuck task quarantine -> Errors/)               |
|                                                               |
|  Logs/System_Log.md    Logs/actions.log    Logs/ai_employee.log|
|  Reports/CEO_Weekly.md   Reports/Social_Log.md               |
|  Accounting/Current_Month.md                                  |
+---------------------------------------------------------------+
         |                    |                    |
         v                    v                    v
   [MCP Servers]       [Agent Skills]       [External APIs]
   business-mcp        gmail-send           Gmail SMTP
   odoo-mcp            gmail-watcher        Gmail IMAP
   email-server        accounting-manager   Odoo JSON-RPC
                       ceo-briefing         Twitter API v2 (*)
                       social-summary       Facebook Graph (*)
                       twitter-post (*)
                       facebook-post (*)

(*) = ready to activate, requires credentials
```

---

## 3. Directory Structure

```
GOLD TIER/
|-- .claude/
|   |-- commands/          Slash command definitions (/process-tasks etc.)
|   |-- settings.json      MCP server registry (3 servers)
|   `-- skills/            16 Agent Skill modules
|-- mcp/
|   |-- business_mcp/      Email + activity log MCP (v2.0.0 production)
|   `-- odoo_mcp/          Odoo accounting MCP (v1.0.0)
|-- mcp_servers/           Legacy email MCP (kept for backwards compat)
|-- scripts/               Core orchestration scripts
|-- Inbox/                 New file drop zone (watched every cycle)
|-- Needs_Action/          Active task queue
|-- Needs_Approval/        Human-in-the-loop gate
|-- Done/                  Completed task archive
|-- Errors/                Quarantined stuck tasks
|-- Logs/                  All log files and state ledgers
|-- Plans/                 Generated execution plans
|-- Reports/               CEO briefings, social post log
|-- Accounting/            Markdown accounting ledger
|-- .env                   Credentials (not committed to git)
|-- CLAUDE.md              Master reference for Claude Code
|-- Company_Handbook.md    Operating rules
|-- Dashboard.md           Central status overview
`-- Architecture.md        This document
```

---

## 4. Agent Skills Catalogue (16 skills)

### Core Vault Skills
| Skill | Script | Purpose |
|-------|--------|---------|
| vault-watcher | scripts/watch_inbox.py | Poll Inbox/ every 15s, create tasks |
| task-planner | scripts/task_planner.py | Analyse inbox files, generate Plans/ |
| silver-scheduler | scripts/run_ai_employee.py | Central orchestrator (daemon loop) |
| vault-file-manager | move_task.py | Move files between vault folders |

### Task Execution
| Skill | Script | Purpose |
|-------|--------|---------|
| ralph-wiggum-loop | ralph_loop.py | Step-by-step task executor with safety gates |
| human-approval | request_approval.py | Human-in-the-loop gate |
| error-recovery | error_recovery.py | Stuck task detection, quarantine, retry |

### Communication
| Skill | Script | Purpose |
|-------|--------|---------|
| gmail-send | send_email.py | Send email via Gmail SMTP |
| gmail-watcher | watch_gmail.py | Monitor Gmail IMAP, create tasks |

### Social Media
| Skill | Script | Status | Purpose |
|-------|--------|--------|---------|
| social-summary | social_summary.py | Active | Log all social posts, Reports/Social_Log.md |
| twitter-post | post_twitter.py | Ready* | Post to Twitter/X via API v2 |
| facebook-post | post_facebook.py | Ready* | Post to Facebook Page via Graph API |
| linkedin-post | post_linkedin.py | Dormant | LinkedIn browser automation (not in use) |
| linkedin-auto-post | auto_post.py | Dormant | LinkedIn auto-generate + post (not in use) |

(*) = skill is complete; add credentials to .env to activate

### Business Intelligence
| Skill | Script | Purpose |
|-------|--------|---------|
| accounting-manager | accounting_manager.py | Markdown ledger for income/expense |
| ceo-briefing | ceo_briefing.py | Weekly executive briefing (Reports/CEO_Weekly.md) |

---

## 5. MCP Servers

### business-mcp (v2.0.0) — Primary
**File:** `mcp/business_mcp/server.py`
**Protocol:** JSON-RPC 2.0 over stdio, MCP 2024-11-05
**Tools:** `send_email`, `log_activity`
**Features:** SMTP retry+backoff, rate limiting (20/60s), header injection prevention, thread-safe log rotation at 5 MB, graceful SIGTERM/SIGINT shutdown.

### odoo-mcp (v1.0.0)
**File:** `mcp/odoo_mcp/server.py`
**Protocol:** JSON-RPC 2.0 over stdio, MCP 2024-11-05
**Backend:** Odoo Community self-hosted via `/jsonrpc` endpoint (stateless, no cookies)
**Tools:**
- `odoo_health_check` — ping + authenticate
- `odoo_get_invoices` — list customer invoices (filter by state)
- `odoo_create_invoice` — create draft customer invoice
- `odoo_get_vendor_bills` — list vendor bills
- `odoo_accounting_summary` — asset/liability/income/expense/equity balances + net profit
- `odoo_create_journal_entry` — post manual journal entry (validated to balance)

### email-server (legacy)
**File:** `mcp_servers/email_server.py`
**Kept for backwards compatibility.** New integrations should use business-mcp.

---

## 6. Data Flow — Full Scheduler Cycle

```
Every 300 seconds (--daemon) or on demand (--once):

[1] vault-watcher
    Inbox/*.md  -->  Needs_Action/task_*.md
    (State: Logs/.watcher_state.json — prevents duplicates)

[2] task-planner
    Needs_Action/task_*.md  -->  Plans/Plan_*.md
    (State: Logs/.planner_state.json)

[3] ralph-wiggum-loop
    Plans/Plan_*.md  -->  steps executed
    Risky keywords detected  -->  Needs_Approval/ (blocks until human acts)
    Max 5 steps/task, 10 tasks/cycle

[4] process-tasks
    Needs_Action/*.md  -->  Done/*.md
    Updates: Dashboard.md, Logs/System_Log.md

[5] human-approval check
    Needs_Approval/*.md  -->  resolve APPROVED/REJECTED
    (Non-blocking: scheduler continues if nothing pending)

[6] error-recovery
    Needs_Action/ stuck tasks (>15 min)  -->  Errors/
    Retry up to 3x with 5 min delay between attempts
    (State: Logs/.error_recovery_state.json)

[7] ceo-briefing (once per 7-day rolling window)
    All logs + Dashboard + Accounting  -->  Reports/CEO_Weekly.md
    (State: Logs/.ceo_briefing_state.json)

[8] log-rotation
    ai_employee.log > 5 MB  -->  rotate to dated archive
```

---

## 7. External Integration Points

### Gmail
- **Outbound:** `gmail-send` skill and `business-mcp` `send_email` tool
- **Inbound:** `gmail-watcher` polls IMAP every cycle, marks emails SEEN
- **Auth:** Gmail App Password (not account password) — set in .env

### Odoo Community
- **Protocol:** Odoo JSON-RPC at `/jsonrpc` endpoint
- **Auth:** Stateless — DB name + username + password sent per-request
- **No pip deps** — uses stdlib `urllib.request`
- **Setup:** See `mcp/odoo_mcp/README.md`

### Twitter/X (future)
- **Skill:** `.claude/skills/twitter-post/`
- **API:** Twitter API v2 via `tweepy`
- **Auth:** OAuth 1.0a (API Key + API Secret + Access Token + Access Secret)
- **Status check:** `python post_twitter.py --status`

### Facebook (future)
- **Skill:** `.claude/skills/facebook-post/`
- **API:** Meta Graph API v19.0 via stdlib `http.client`
- **Auth:** Page Access Token
- **Status check:** `python post_facebook.py --status`

---

## 8. Security Model

| Layer | Approach |
|-------|---------|
| Credentials | Stored in `.env` at vault root; never committed to git |
| SMTP | Header injection prevention on To/Subject fields; rate-limited to 20/min |
| Task execution | ralph loop detects risky keywords (delete, drop, format, rm -rf, etc.) |
| Sensitive actions | Routed to Needs_Approval/ — scheduler does NOT auto-approve |
| Odoo | Password sent over localhost only (ODOO_URL defaults to http://localhost:8069) |
| Twitter/Facebook | Credentials checked before any API call; clear "not configured" message if missing |

---

## 9. Design Decisions

### Decision 1: File-as-queue over a real message broker
**Choice:** Markdown files in Inbox/ and Needs_Action/ act as the task queue.
**Why:** Zero infrastructure — no Redis, RabbitMQ, or database required. Obsidian provides a human-readable UI over the same files the agent reads. State ledger JSON files provide exactly-once delivery guarantees.
**Trade-off:** No concurrent consumers. Single-process scheduler is fine for Gold Tier workloads.

### Decision 2: Stdlib-first design
**Choice:** Every skill tries to use only Python standard library. `tweepy` and `playwright` are the only pip dependencies.
**Why:** Reduces setup friction. The vault works immediately after `pip install playwright tweepy` — no Django, SQLAlchemy, or other heavy frameworks.
**Trade-off:** Some tasks (OAuth, HTML parsing) require more code than with third-party libs.

### Decision 3: Atomic file writes everywhere
**Choice:** All files that are read-modify-written use `.tmp` → `os.replace()` pattern.
**Why:** Prevents corrupt state if the scheduler is interrupted mid-write (power loss, SIGKILL).
**Trade-off:** Slightly more complex than direct file.write() but negligible overhead.

### Decision 4: Stateless Odoo authentication
**Choice:** Odoo JSON-RPC with credentials on every request (no session cookies).
**Why:** MCP servers are stateless by design (spawned per-Claude-Code session). Session cookies would expire between sessions. Per-request auth is simpler and more reliable.
**Trade-off:** Slightly more network overhead. Acceptable because Odoo is on localhost.

### Decision 5: Social skills as stubs
**Choice:** Twitter and Facebook skills are complete code with graceful "not configured" behaviour.
**Why:** The infrastructure is ready; only credentials are needed to activate. This avoids `ImportError` crashes while keeping the codebase complete.
**Trade-off:** Tests can't run end-to-end without real API credentials.

### Decision 6: LinkedIn dormant, email primary
**Choice:** LinkedIn skills exist but are not integrated into the scheduler workflow. Email is the primary outbound channel.
**Why:** Email is more reliable and doesn't require browser automation or rate-limit management. LinkedIn automation via Playwright is fragile against UI changes.
**Trade-off:** No automated social posting unless Twitter or Facebook are activated.

---

## 10. Lessons Learned

### L1: Obsidian + Claude Code is a powerful pairing
The vault structure maps naturally to an agent's task management needs. Obsidian provides instant human oversight — you can open any file and see exactly what the agent is doing. Claude Code's file tools (Read, Write, Edit, Glob, Grep) are sufficient for all vault operations without any custom tooling.

### L2: Human-in-the-loop is non-negotiable for Gold Tier
The human-approval skill was the most important addition over Silver Tier. Without it, the ralph loop would execute destructive or public-facing actions without review. The Needs_Approval/ directory as a gate is simple but robust.

### L3: State ledgers are worth the complexity
The `.json` state files in Logs/ (watcher, planner, gmail, ceo, error-recovery) eliminated an entire class of bugs: duplicate task creation from the same inbox file, duplicate CEO briefings per week, duplicate email task creation. Every exactly-once guarantee is backed by a state file.

### L4: Graceful degradation is a feature, not an afterthought
Skills that print "STATUS: NOT CONFIGURED" and exit 0 (instead of crashing with a KeyError or ImportError) make the system usable before all credentials are in place. The scheduler can run a full cycle even if Twitter, Facebook, and Odoo are not configured.

### L5: MCP servers need zero pip dependencies
The business-mcp and odoo-mcp servers use only stdlib. If they depended on `requests` or `aiohttp`, any `pip install` failure would silently break Claude Code's MCP integration. Stdlib-only servers are guaranteed to work on any Python 3.11+ install.

### L6: Log rotation must be built-in
Without rotation, `ai_employee.log` grows unboundedly. The 5 MB auto-rotation in the scheduler (and in business-mcp) prevents disk exhaustion on long-running daemon deployments.

### L7: Browser automation for social media is fragile
The linkedin-post skill uses Playwright to drive a real browser. LinkedIn's DOM changes frequently, and the skill has broken multiple times during development. API-based skills (twitter-post, facebook-post) are far more reliable. Future LinkedIn work should target LinkedIn's official API, not browser automation.

### L8: The CEO briefing's rolling 7-day gate is the right pattern
Generating the briefing on every scheduler cycle would produce hundreds of files per week. The rolling 7-day window (tracked in `.ceo_briefing_state.json`) ensures exactly one briefing per week while still running on every cycle without an external cron.

---

## 11. Gold Tier Requirements Coverage

| Requirement | Status | Implementation |
|-------------|--------|---------------|
| All Silver requirements | Done | vault-watcher, task-planner, scheduler, file-manager, gmail, human-approval |
| Cross-domain integration (Personal + Business) | Done | Gmail personal + accounting/CEO/Odoo business |
| Odoo accounting via JSON-RPC MCP | Done | mcp/odoo_mcp/server.py — 6 tools |
| Facebook integration | Ready* | .claude/skills/facebook-post/ — add credentials to activate |
| Instagram integration | Note** | Use Facebook skill with Instagram Business API when needed |
| Twitter/X integration | Ready* | .claude/skills/twitter-post/ — add credentials to activate |
| Multiple MCP servers | Done | business-mcp, odoo-mcp, email-server (legacy) |
| Weekly Business & Accounting Audit + CEO Briefing | Done | ceo-briefing skill, Reports/CEO_Weekly.md |
| Error recovery + graceful degradation | Done | error-recovery skill, stuck task quarantine |
| Comprehensive audit logging | Done | actions.log, System_Log.md, ai_employee.log, errors.log |
| Ralph Wiggum loop | Done | ralph-wiggum-loop skill with safety gates |
| Architecture + lessons learned documentation | Done | This document |
| All AI as Agent Skills | Done | 16 skills in .claude/skills/ |

(*) = Ready to activate by adding credentials to .env
(**) = Instagram Business posting uses same Meta Graph API as Facebook; extend facebook-post skill

---

## 12. Future Roadmap

- **Instagram posting** — Extend `facebook-post` skill with `/{page_id}/media` + `/{page_id}/media_publish` endpoints from Meta Graph API
- **Odoo inventory** — Add `odoo_get_products` and `odoo_update_stock` tools to odoo-mcp
- **Sentiment analysis** — Analyse incoming Gmail subjects to auto-prioritise tasks
- **Multi-vault support** — Parameterise VAULT_ROOT so one Claude Code instance can manage multiple client vaults
- **Slack integration** — Add `slack-notify` skill using Slack Incoming Webhooks (no pip deps)
- **Dashboard auto-refresh** — Update Dashboard.md counts in real time from scheduler cycle results
