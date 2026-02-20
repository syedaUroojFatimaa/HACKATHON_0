# 🤖 AI-Powered Personal Operating System
### Autonomous Business Assistant — Bronze → Gold Tier Implementation

---

## Table of Contents
1. [Project Overview](#project-overview)
2. [Architecture Overview](#architecture-overview)
3. [Folder Structure](#folder-structure)
4. [Setup Instructions](#setup-instructions)
5. [Tier Feature Map](#tier-feature-map)
6. [Agent Skills Reference](#agent-skills-reference)
7. [MCP Servers](#mcp-servers)
8. [Watcher Scripts](#watcher-scripts)
9. [Human-in-the-Loop Workflow](#human-in-the-loop-workflow)
10. [Ralph Wiggum Loop](#ralph-wiggum-loop)
11. [Lessons Learned](#lessons-learned)

---

## Project Overview

This system turns an Obsidian vault into the **brain** of an autonomous AI employee. Claude Code acts as the reasoning engine, reading from and writing to the vault, triggering external actions via MCP servers, and monitoring incoming signals via Watcher scripts.

**Three delivery tiers:**

| Tier | Nickname | Est. Hours | Key Unlock |
|------|----------|-----------|------------|
| 🥉 Bronze | MVP | 8–12h | Vault + one Watcher + Claude R/W |
| 🥈 Silver | Functional Assistant | 20–30h | Multi-Watcher + LinkedIn posting + approval flow |
| 🥇 Gold | Autonomous Employee | 40h+ | Odoo ERP + social media + weekly CEO briefing |

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                        SIGNAL LAYER                             │
│  Gmail Watcher │ WhatsApp Watcher │ LinkedIn │ File Watcher     │
└───────────────────────────┬─────────────────────────────────────┘
                            │ raw signals → /Inbox
                            ▼
┌─────────────────────────────────────────────────────────────────┐
│                     OBSIDIAN VAULT (Brain)                      │
│                                                                 │
│  /Inbox          Raw, unprocessed notes & signals               │
│  /Needs_Action   Claude-generated Plan.md files                 │
│  /Done           Completed & archived items                     │
│  /Dashboard.md   Live status overview (auto-updated)            │
│  /Company_Handbook.md  Policies, personas, constraints          │
│  /Audit_Logs     Timestamped action history (Gold)              │
└───────────────────────────┬─────────────────────────────────────┘
                            │ read / write
                            ▼
┌─────────────────────────────────────────────────────────────────┐
│                    CLAUDE CODE (Reasoning Engine)               │
│                                                                 │
│  Agent Skills:                                                  │
│   • classify_and_triage   • draft_response                      │
│   • create_plan           • social_post_generator               │
│   • accounting_sync       • ceo_briefing                        │
│   • audit_logger          • ralph_wiggum_loop                   │
└───────────────────────────┬─────────────────────────────────────┘
                            │ tool calls
                            ▼
┌─────────────────────────────────────────────────────────────────┐
│                       MCP SERVER LAYER                          │
│                                                                 │
│  mcp-gmail      Send/read emails                                │
│  mcp-linkedin   Post content, read notifications                │
│  mcp-social     Facebook, Instagram, Twitter/X (Gold)           │
│  mcp-odoo       JSON-RPC → Odoo Community ERP (Gold)            │
└─────────────────────────────────────────────────────────────────┘
```

**Data flow in one sentence:** Watchers push signals into `/Inbox` → Claude reasons over them using Agent Skills → Claude writes Plans to `/Needs_Action` → Human approves (or auto-approves) → MCP servers execute → items move to `/Done` → Audit Log updated.

---

## Folder Structure

```
project-root/
│
├── vault/                          # Obsidian vault (the "brain")
│   ├── Dashboard.md                # Live status dashboard
│   ├── Company_Handbook.md         # Rules, tone, personas, constraints
│   ├── Inbox/                      # Raw incoming signals
│   ├── Needs_Action/               # Claude-generated Plan.md files
│   ├── Done/                       # Archived completed items
│   └── Audit_Logs/                 # Timestamped action history (Gold)
│
├── watchers/
│   ├── gmail_watcher.py            # Polls Gmail, writes to /Inbox
│   ├── whatsapp_watcher.py         # WhatsApp Web monitoring (Silver)
│   ├── linkedin_watcher.py         # LinkedIn notifications (Silver)
│   └── file_watcher.py             # Local filesystem changes
│
├── skills/                         # Claude Code Agent Skills
│   ├── classify_and_triage.md
│   ├── create_plan.md
│   ├── draft_response.md
│   ├── social_post_generator.md
│   ├── accounting_sync.md          # Gold
│   ├── ceo_briefing.md             # Gold
│   ├── audit_logger.md             # Gold
│   └── ralph_wiggum_loop.md        # Gold
│
├── mcp-servers/
│   ├── mcp-gmail/
│   ├── mcp-linkedin/
│   ├── mcp-social/                 # Gold: FB + IG + Twitter
│   └── mcp-odoo/                   # Gold: Odoo JSON-RPC
│
├── approval/
│   └── approval_queue.md           # Human-in-the-loop staging area
│
├── cron/
│   └── schedule.sh                 # Cron / Task Scheduler entries
│
├── .env.example                    # API keys template (never commit .env)
└── README.md                       # This file
```

---

## Setup Instructions

### Prerequisites

| Requirement | Version | Notes |
|-------------|---------|-------|
| Python | 3.10+ | For Watcher scripts |
| Node.js | 18+ | For MCP servers |
| Claude Code | latest | `npm install -g @anthropic/claude-code` |
| Obsidian | latest | Free desktop app |
| Odoo Community | 19+ | Gold tier only — self-hosted |

---

### Step 1 — Clone & Configure

```bash
git clone https://github.com/your-org/ai-personal-os.git
cd ai-personal-os
cp .env.example .env
```

Edit `.env` with your credentials:

```env
# Anthropic
ANTHROPIC_API_KEY=sk-ant-...

# Gmail (OAuth2)
GMAIL_CLIENT_ID=...
GMAIL_CLIENT_SECRET=...
GMAIL_REFRESH_TOKEN=...

# LinkedIn
LINKEDIN_ACCESS_TOKEN=...

# Social (Gold)
FACEBOOK_PAGE_ACCESS_TOKEN=...
INSTAGRAM_ACCOUNT_ID=...
TWITTER_BEARER_TOKEN=...
TWITTER_API_KEY=...

# Odoo (Gold)
ODOO_URL=http://localhost:8069
ODOO_DB=your_db
ODOO_USERNAME=admin
ODOO_PASSWORD=...
```

---

### Step 2 — Install Dependencies

```bash
# Python watchers
pip install -r requirements.txt

# MCP servers
cd mcp-servers/mcp-gmail && npm install
cd ../mcp-linkedin && npm install
# (Gold) cd ../mcp-social && npm install
# (Gold) cd ../mcp-odoo && npm install
```

---

### Step 3 — Configure Claude Code

Create or edit `~/.claude/claude.json` (or project-level `.claude/claude.json`):

```json
{
  "mcpServers": {
    "gmail": {
      "command": "node",
      "args": ["./mcp-servers/mcp-gmail/index.js"],
      "env": { "GMAIL_CLIENT_ID": "${GMAIL_CLIENT_ID}" }
    },
    "linkedin": {
      "command": "node",
      "args": ["./mcp-servers/mcp-linkedin/index.js"]
    },
    "odoo": {
      "command": "node",
      "args": ["./mcp-servers/mcp-odoo/index.js"]
    }
  }
}
```

---

### Step 4 — Point Obsidian at the Vault

1. Open Obsidian → "Open folder as vault"
2. Select `./vault/`
3. Recommended plugins: **Dataview**, **Tasks**, **Templater**

---

### Step 5 — Start Watchers

```bash
# Run individually
python watchers/gmail_watcher.py

# Or use the provided cron schedule
bash cron/schedule.sh install
```

Cron entries (Linux/macOS):

```cron
*/5 * * * *  python /path/to/watchers/gmail_watcher.py
*/10 * * * * python /path/to/watchers/linkedin_watcher.py
0 8 * * 1   claude --skill ceo_briefing   # Weekly Monday 8am briefing
0 2 * * 0   claude --skill accounting_sync # Weekly Sunday 2am audit
```

---

### Step 6 — Run Claude Code

```bash
# Interactive session with vault access
claude

# Or trigger a specific skill directly
claude --skill classify_and_triage --input vault/Inbox/
```

---

### Step 7 — Verify Setup (Bronze Smoke Test)

```bash
# Drop a test file into Inbox
echo "Test signal: new client inquiry from test@example.com" > vault/Inbox/test_signal.md

# Run Claude against it
claude "Read vault/Inbox/test_signal.md, classify it, and create a Plan.md in vault/Needs_Action/"

# Confirm output
ls vault/Needs_Action/
```

---

## Tier Feature Map

### 🥉 Bronze — Foundation

- [ ] `vault/Dashboard.md` and `vault/Company_Handbook.md` created
- [ ] One Watcher running (Gmail or file system)
- [ ] Claude Code reading from and writing to vault
- [ ] `/Inbox`, `/Needs_Action`, `/Done` folders active
- [ ] All AI logic implemented as Agent Skills

### 🥈 Silver — Functional Assistant

- [ ] All Bronze requirements
- [ ] 2+ Watchers (Gmail + WhatsApp + LinkedIn)
- [ ] Automated LinkedIn posting via `social_post_generator` skill
- [ ] Claude reasoning loop producing `Plan.md` files
- [ ] One MCP server live (email sending)
- [ ] Human-in-the-loop approval queue
- [ ] Cron / Task Scheduler running
- [ ] All AI logic implemented as Agent Skills

### 🥇 Gold — Autonomous Employee

- [ ] All Silver requirements
- [ ] Cross-domain integration (Personal + Business vaults merged)
- [ ] Odoo Community (self-hosted) integrated via `mcp-odoo` JSON-RPC
- [ ] Facebook + Instagram posting + summary generation
- [ ] Twitter/X posting + summary generation
- [ ] Multiple MCP servers orchestrated together
- [ ] Weekly Business + Accounting Audit with CEO Briefing
- [ ] Error recovery and graceful degradation in all skills
- [ ] Comprehensive audit logging in `/Audit_Logs`
- [ ] Ralph Wiggum Loop for autonomous multi-step tasks
- [ ] Architecture documentation + lessons learned

---

## Agent Skills Reference

All AI functionality lives in `skills/`. Each skill is a markdown file that Claude Code reads as a system prompt / instruction set before acting.

| Skill File | Tier | Purpose |
|------------|------|---------|
| `classify_and_triage.md` | Bronze | Read Inbox items, assign urgency, route to Needs_Action or Done |
| `create_plan.md` | Bronze | Generate structured Plan.md with steps, owners, deadlines |
| `draft_response.md` | Silver | Draft email/message replies for human review |
| `social_post_generator.md` | Silver | Generate and schedule LinkedIn/social posts |
| `accounting_sync.md` | Gold | Pull Odoo data, reconcile, flag anomalies |
| `ceo_briefing.md` | Gold | Compile weekly cross-domain summary report |
| `audit_logger.md` | Gold | Append timestamped entries to Audit_Logs/ |
| `ralph_wiggum_loop.md` | Gold | Autonomous multi-step task executor with self-correction |

**How to invoke a skill in Claude Code:**
```
Read skills/create_plan.md, then apply it to vault/Inbox/client_inquiry.md
```

---

## MCP Servers

### `mcp-gmail`
- **Actions:** `send_email`, `list_unread`, `get_thread`
- **Auth:** OAuth2 with refresh token
- **Used by:** `draft_response` skill, approval workflow

### `mcp-linkedin`
- **Actions:** `create_post`, `get_notifications`, `get_analytics`
- **Auth:** LinkedIn OAuth2 access token
- **Used by:** `social_post_generator` skill

### `mcp-social` *(Gold)*
- **Actions:** `facebook_post`, `instagram_post`, `twitter_post`, `get_engagement_summary`
- **Auth:** Per-platform tokens in `.env`
- **Used by:** `social_post_generator`, `ceo_briefing` skills

### `mcp-odoo` *(Gold)*
- **Protocol:** JSON-RPC over HTTP to Odoo 19+ instance
- **Actions:** `get_invoices`, `get_payments`, `create_journal_entry`, `get_account_summary`
- **Auth:** Odoo username/password session token
- **Used by:** `accounting_sync`, `ceo_briefing` skills

**Odoo JSON-RPC example call:**
```javascript
const result = await fetch(`${ODOO_URL}/web/dataset/call_kw`, {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({
    jsonrpc: '2.0', method: 'call', id: 1,
    params: {
      model: 'account.move',
      method: 'search_read',
      args: [[['state', '=', 'posted']]],
      kwargs: { fields: ['name', 'amount_total', 'invoice_date'], limit: 50 }
    }
  })
});
```

---

## Human-in-the-Loop Workflow

Sensitive actions (sending emails, posting publicly, financial entries) are **staged for approval** before execution.

**Flow:**

```
Claude proposes action
        ↓
Writes to vault/approval/approval_queue.md
        ↓
Operator reviews (Obsidian or CLI)
        ↓
   APPROVE → Claude executes via MCP
   REJECT  → Item archived with rejection note
   EDIT    → Claude revises and re-queues
```

**approval_queue.md format:**

```markdown
## [PENDING] Send email to client@example.com
- **Skill:** draft_response
- **Proposed at:** 2025-03-15 09:32
- **Action:** Send reply to thread ID abc123
- **Preview:** "Thank you for your inquiry..."
- **Decision:** [ ] APPROVE  [ ] REJECT  [ ] EDIT
```

Claude Code polls this file on each run and executes or discards based on the checkbox state.

---

## Ralph Wiggum Loop

*(Gold Tier — Section 2D)*

The Ralph Wiggum Loop enables **autonomous multi-step task completion** with self-correction. Named after the character who persists cheerfully regardless of outcomes.

**Loop structure:**

```
1. PLAN     — Claude reads goal, decomposes into ordered steps
2. EXECUTE  — Execute step N via appropriate skill / MCP call
3. OBSERVE  — Read result back from vault or MCP response
4. EVALUATE — Did step succeed? Does plan need revision?
5. CORRECT  — If failed: retry, reroute, or escalate to human
6. ADVANCE  — Move to step N+1 or mark goal complete
7. LOG      — Append to Audit_Logs/ at each step
```

**Termination conditions:**
- All steps complete → write summary to `/Done`
- 3 consecutive failures on same step → escalate to human via approval queue
- Max iterations (configurable, default 20) reached → pause and notify

**Invoke:**
```
Read skills/ralph_wiggum_loop.md, then autonomously complete the goal described in vault/Needs_Action/onboard_new_client.md
```

---

## Lessons Learned

*(To be populated as implementation progresses — document surprises, workarounds, and architecture decisions here)*

**Template entries:**

```markdown
### 2025-MM-DD — [Title]
**What happened:** ...
**Why it matters:** ...
**How we fixed it / decision made:** ...
```

---

## Contributing

1. All new AI functionality must be an Agent Skill in `skills/`
2. Never commit `.env` — use `.env.example` as the template
3. All MCP servers must handle errors gracefully and return structured JSON errors
4. Audit log every action that touches external systems

---

## License

MIT — see `LICENSE` for details.
