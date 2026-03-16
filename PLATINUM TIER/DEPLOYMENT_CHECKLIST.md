# Platinum Tier Deployment Checklist

## Pre-Deployment Verification

### 1. Core Architecture ✅
- [ ] Work-zone folders created (`scripts/setup_workzones.bat`)
- [ ] Cloud worker configured (`scripts/cloud_worker.py`)
- [ ] Local worker configured (`scripts/local_worker.py`)
- [ ] Claim-by-move rule implemented
- [ ] Single-writer Dashboard rule implemented

### 2. Git Sync ✅
- [ ] `.gitignore` configured (secrets excluded)
- [ ] `sync.bat` tested
- [ ] Cloud auto-pull configured (`scripts/setup_cloud_pull.bat`)
- [ ] Git repository initialized

### 3. Health Monitoring ✅
- [ ] Watchdog configured (`watchdog.py`)
- [ ] Task Scheduler setup (`scripts/setup_watchdog.bat`)
- [ ] `Logs/system_health.md` updating every 5 min

### 4. CEO Briefing ✅
- [ ] Briefing generator working (`ceo_briefing.py`)
- [ ] Sunday 8AM schedule configured
- [ ] `Briefings/` folder created

---

## Required Integrations

### 5. Email Integration ⚠️

**Files:** `scripts/email_sender.py`, `.env`

- [ ] Add to `.env` (Local machine ONLY):
```
EMAIL_ADDRESS=your-email@gmail.com
EMAIL_PASSWORD=your-app-password
SMTP_SERVER=smtp.gmail.com
SMTP_PORT=587
```

- [ ] Test email sending:
```cmd
python scripts/email_sender.py --test
```

- [ ] Integrate with `local_worker.py`:
  - Update `execute_email_send()` to call `email_sender.py`

- [ ] Test full flow:
```cmd
REM Create test approval in Pending_Approval/email/
python scripts/email_sender.py --send approval_test.md
```

### 6. Social Media Integration ⚠️

**Files:** `scripts/social_poster.py`, `.env`

- [ ] Add to `.env` (Local machine ONLY):
```
# Twitter API v2
TWITTER_API_KEY=your-api-key
TWITTER_API_SECRET=your-api-secret
TWITTER_ACCESS_TOKEN=your-token
TWITTER_ACCESS_TOKEN_SECRET=your-token-secret

# LinkedIn
LINKEDIN_ACCESS_TOKEN=your-token
LINKEDIN_ORG_ID=your-org-id (optional)
```

- [ ] Install dependencies:
```cmd
pip install tweepy requests
```

- [ ] Test configuration:
```cmd
python scripts/social_poster.py --check
```

- [ ] Integrate with `local_worker.py`:
  - Update `execute_social_post()` to call `social_poster.py`

### 7. WhatsApp Integration ⚠️

**Status:** Not yet implemented

**Files to create:** `scripts/whatsapp_sender.py`

- [ ] Create WhatsApp sender script
- [ ] Store session in `sessions/whatsapp/` (never sync)
- [ ] Local-only execution
- [ ] Integrate with approval flow

---

## Cloud VM Deployment

### 8. Oracle Cloud Free VM Setup ⚠️

**Estimated time:** 30 minutes

#### Step 1: Create VM
- [ ] Sign up at https://cloud.oracle.com
- [ ] Create Always Free ARM VM (Ampere A1 Compute)
- [ ] Choose Ubuntu 22.04
- [ ] Note public IP address

#### Step 2: SSH Setup
```bash
# Generate SSH key (Windows: use PuTTYgen or WSL)
ssh-keygen -t rsa -b 4096

# Copy public key to VM
ssh-copy-id ubuntu@<vm-ip>

# Test connection
ssh ubuntu@<vm-ip>
```

#### Step 3: Install Dependencies
```bash
# Update system
sudo apt update && sudo apt upgrade -y

# Install Python
sudo apt install python3 python3-pip python3-venv -y

# Install Node.js
curl -fsSL https://deb.nodesource.com/setup_18.x | sudo -E bash -
sudo apt install nodejs -y

# Install Git
sudo apt install git -y

# Install PM2
sudo npm install -g pm2
```

#### Step 4: Clone Repository
```bash
cd ~
git clone <your-repo-url> PLATINUM-TIER
cd PLATINUM-TIER

# Setup Python environment
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

#### Step 5: Configure Environment
```bash
# Create .env (Cloud version - NO secrets)
cp .env.example .env

# Edit .env - Cloud only needs:
# - Email for receiving (IMAP)
# - API keys for DRAFTING only
# NO sending credentials!
nano .env
```

#### Step 6: Setup HTTPS (Optional but Recommended)
```bash
# Install nginx
sudo apt install nginx -y

# Configure reverse proxy
sudo nano /etc/nginx/sites-available/platinum-tier

# Get SSL certificate
sudo apt install certbot python3-certbot-nginx -y
sudo certbot --nginx -d your-domain.com
```

#### Step 7: Start Services
```bash
# Start with PM2
cd ~/PLATINUM-TIER
pm2 start ecosystem.config.js
pm2 save

# Setup PM2 startup
pm2 startup
# Run the generated command
```

#### Step 8: Configure Firewall
```bash
# Allow SSH
sudo ufw allow 22

# Allow HTTP/HTTPS (if using web server)
sudo ufw allow 80
sudo ufw allow 443

# Enable firewall
sudo ufw enable
```

### 9. Cloud VM Verification

- [ ] PM2 processes running:
```bash
pm2 status
```

- [ ] Health check passing:
```bash
python3 watchdog.py --status
```

- [ ] Cloud worker drafting:
```bash
# Drop test file in Inbox
echo "Test email" > Inbox/test_email.txt

# Wait 2 minutes, check Pending_Approval
ls Pending_Approval/email/
```

- [ ] Logs updating:
```bash
tail -f Logs/cloud_worker.log
```

---

## Local Machine Setup

### 10. Local Machine Configuration

- [ ] Clone repository
- [ ] Setup Python venv
- [ ] Install dependencies
- [ ] Configure `.env` with ALL credentials:
  - Email sending (Gmail)
  - Social media (Twitter, LinkedIn)
  - WhatsApp session
  - Banking/payment APIs
  - Odoo credentials

- [ ] Run setup scripts:
```cmd
scripts\setup_workzones.bat
scripts\setup_watchdog.bat
scripts\setup_ceo_briefing.bat
```

- [ ] Start local worker:
```cmd
python scripts\local_worker.py --daemon
```

---

## Odoo Integration

### 11. Odoo Community Setup ⚠️

**Status:** Not yet implemented

#### On Cloud VM:
```bash
# Install Docker (recommended)
sudo apt install docker.io docker-compose -y

# Pull Odoo image
docker run -d -p 8069:8069 --name odoo -v odoo-data:/var/lib/odoo odoo:16.0

# Or install directly
sudo apt install odoo -y
```

#### Configuration:
- [ ] Odoo accessible at `http://vm-ip:8069`
- [ ] Create database
- [ ] Install Accounting module
- [ ] Create API user for AI Employee

#### MCP Integration:
- [ ] Create `scripts/odoo_mcp.py`
- [ ] Cloud can draft invoices
- [ ] Local must approve before posting
- [ ] Sync accounting data to `Accounting/` folder

---

## End-to-End Demo Test

### 12. Platinum Demo Validation ⚠️

**Test Scenario:** Email arrives → Cloud drafts → Local approves → Email sent

#### Step 1: Prepare
- [ ] Cloud VM running
- [ ] Local machine running
- [ ] Git sync working
- [ ] Email credentials configured on Local

#### Step 2: Simulate Email Arrival
```cmd
# On Cloud VM
cat > Inbox/demo_inquiry.md << 'EOF'
---
type: email
from: demo@example.com
subject: Demo Inquiry
received: 2026-03-16 09:00:00 UTC
---

This is a test email for the Platinum demo.
EOF
```

#### Step 3: Cloud Processing (wait 2 min)
- [ ] Cloud detects email
- [ ] Cloud creates draft reply
- [ ] Cloud writes `Pending_Approval/email/approval_demo_inquiry.md`
- [ ] Cloud moves original to `Approved/email/`

#### Step 4: Git Sync
- [ ] Approval file synced to Local
- [ ] Verify on Local: `dir Pending_Approval\email\`

#### Step 5: Local Approval
```cmd
# On Local machine
python scripts\local_worker.py --approve
```

- [ ] Local claims approval
- [ ] Local executes email send
- [ ] Email sent via Gmail

#### Step 6: Verification
- [ ] Check email received at `demo@example.com`
- [ ] Check `Logs/local_worker.log` shows send
- [ ] Check `Dashboard.md` updated
- [ ] Check approval moved to `Approved/email/`

#### Step 7: Document Results
- [ ] Screenshot of sent email
- [ ] Screenshot of Dashboard.md
- [ ] Screenshot of PM2 status
- [ ] Record screen capture for demo

---

## Security Verification

### 13. Security Audit

- [ ] `.gitignore` excludes:
  - `.env`
  - `sessions/`
  - `tokens/`
  - `Logs/*.log`

- [ ] Cloud `.env` has NO:
  - Email sending passwords
  - Social media tokens
  - WhatsApp credentials
  - Banking API keys

- [ ] Local `.env` has ALL credentials (never synced)

- [ ] Git history clean:
```cmd
git log --all --full-history -- .env
# Should show no commits
```

- [ ] Test sync doesn't leak secrets:
```cmd
# Add test secret to Local .env
echo "SECRET_TEST=123" >> .env

# Run sync
sync.bat push

# Check Cloud - secret should NOT appear
```

---

## Final Checks

### 14. Production Readiness

- [ ] All workers running in daemon mode
- [ ] Health monitoring active
- [ ] Auto-restart configured
- [ ] CEO briefing scheduled
- [ ] Logs rotating (log_manager.py)
- [ ] Backup strategy in place
- [ ] Error alerts configured
- [ ] Documentation complete

### 15. Documentation

- [ ] `README.md` updated with setup instructions
- [ ] `DEPLOYMENT.md` complete
- [ ] `WORKZONE_ARCHITECTURE.md` reviewed
- [ ] `HEALTH_MONITORING.md` reviewed
- [ ] `CEO_BRIEFING_GUIDE.md` reviewed
- [ ] `GIT_CONFLICT_GUIDE.md` reviewed
- [ ] `PROJECT_COMPLETENESS_AUDIT.md` updated

---

## Sign-Off

| Component | Status | Notes |
|-----------|--------|-------|
| Work-Zone Architecture | ☐ Complete | |
| Git Sync | ☐ Complete | |
| Health Monitoring | ☐ Complete | |
| CEO Briefing | ☐ Complete | |
| Email Integration | ☐ Complete | |
| Social Integration | ☐ Complete | |
| WhatsApp Integration | ☐ Complete | |
| Cloud VM Deployment | ☐ Complete | |
| Odoo Integration | ☐ Complete | Optional |
| Demo Validation | ☐ Complete | |
| Security Audit | ☐ Complete | |

**Overall Status:** ☐ Ready for Production

**Date:** _______________

**Signed:** _______________

---

## Quick Status Check

Run this command to see current status:

```cmd
echo === Project Completeness ===
echo.
echo Core Architecture:
dir /b scripts\cloud_worker.py scripts\local_worker.py 2>nul && echo   [OK] Workers exist || echo   [ ] Workers missing
dir /b In_Progress\cloud In_Progress\local 2>nul && echo   [OK] Work zones exist || echo   [ ] Work zones missing
echo.
echo Git Sync:
dir /b .gitignore 2>nul && echo   [OK] .gitignore exists || echo   [ ] .gitignore missing
dir /b sync.bat 2>nul && echo   [OK] sync.bat exists || echo   [ ] sync.bat missing
echo.
echo Health Monitoring:
dir /b watchdog.py 2>nul && echo   [OK] watchdog.py exists || echo   [ ] watchdog.py missing
dir /b scripts\setup_watchdog.bat 2>nul && echo   [OK] Watchdog setup exists || echo   [ ] Watchdog setup missing
echo.
echo CEO Briefing:
dir /b ceo_briefing.py 2>nul && echo   [OK] ceo_briefing.py exists || echo   [ ] ceo_briefing.py missing
dir /b scripts\setup_ceo_briefing.bat 2>nul && echo   [OK] Briefing setup exists || echo   [ ] Briefing setup missing
echo.
echo Integrations:
dir /b scripts\email_sender.py 2>nul && echo   [OK] Email sender exists || echo   [ ] Email sender missing
dir /b scripts\social_poster.py 2>nul && echo   [OK] Social poster exists || echo   [ ] Social poster missing
```
