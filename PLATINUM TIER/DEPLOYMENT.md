# 24/7 Deployment Guide for Windows CMD

This guide sets up the Platinum Tier AI Employee to run continuously on Windows with:
- **PM2** for process management (auto-restart on crash)
- **Windows Task Scheduler** for auto-start on system reboot
- **Health monitoring** for system status checks

---

## Prerequisites

- Python 3.8+ installed
- Node.js 16+ installed (for PM2)
- Administrator access to Windows Task Scheduler

---

## Step-by-Step Deployment Commands

### Step 1: Install Python Environment

```cmd
REM Check if Python is installed
python --version

REM If not installed, download from https://python.org/downloads
REM Or use winget:
winget install Python.Python.3.11
```

### Step 2: Set Up Python Virtual Environment

```cmd
cd /d "C:\Users\Dell\Desktop\Hackathon_0\PLATINUM TIER"

REM Create virtual environment
python -m venv venv

REM Activate virtual environment
venv\Scripts\activate
```

### Step 3: Install Project Dependencies

```cmd
REM Upgrade pip
python -m pip install --upgrade pip

REM Install project dependencies
pip install -r requirements.txt
```

### Step 4: Install Node.js and PM2

```cmd
REM Check if Node.js is installed
node --version
npm --version

REM If not installed, download from https://nodejs.org
REM Or use winget:
winget install OpenJS.NodeJS.LTS

REM Install PM2 globally
npm install -g pm2

REM Verify PM2 installation
pm2 --version
```

### Step 5: Create Required Directories

```cmd
REM Ensure all required directories exist
mkdir Inbox Needs_Action Needs_Approval Done Logs Plans Reports Accounting Errors 2>nul
```

### Step 6: Configure PM2

The `ecosystem.config.js` file has been created with the following processes:
- **orchestrator** - Main scheduler (run_ai_employee.py) in daemon mode
- **file-watcher** - Inbox file watcher (file_watcher.py)
- **log-manager** - Log rotation manager (runs every hour)

### Step 7: Start All Processes with PM2

```cmd
cd /d "C:\Users\Dell\Desktop\Hackathon_0\PLATINUM TIER"

REM Activate virtual environment first
venv\Scripts\activate

REM Start all PM2 processes
pm2 start ecosystem.config.js

REM Save PM2 process list for auto-resume
pm2 save

REM Set PM2 to startup (generates command for Windows)
pm2 startup
```

### Step 8: Configure Windows Task Scheduler for Auto-Start

Run the setup script as Administrator:

```cmd
REM Open Command Prompt as Administrator
cd /d "C:\Users\Dell\Desktop\Hackathon_0\PLATINUM TIER"

REM Run the Task Scheduler setup
scripts\setup_autostart.bat
```

### Step 9: Verify Everything is Running

```cmd
REM Check PM2 process status
pm2 status

REM View live logs
pm2 logs

REM Check specific process logs
pm2 logs orchestrator
pm2 logs file-watcher
pm2 logs log-manager
```

---

## Quick Reference Commands

### Process Management

```cmd
REM Start all processes
pm2 start ecosystem.config.js

REM Stop all processes
pm2 stop ecosystem.config.js

REM Restart all processes
pm2 restart ecosystem.config.js

REM Delete all processes
pm2 delete ecosystem.config.js

REM View process status
pm2 status

REM View process details
pm2 show orchestrator
```

### Log Management

```cmd
REM View all logs
pm2 logs

REM View specific process logs
pm2 logs orchestrator --lines 100

REM Clear all logs
pm2 flush

REM View PM2 daemon logs
type %USERPROFILE%\.pm2\pm2.log
```

### Health Checks

```cmd
REM Run health check script
scripts\health_check.bat

REM Check system status via Python
venv\Scripts\activate && python scripts\run_ai_employee.py --status
```

---

## Troubleshooting

### PM2 Processes Won't Start

```cmd
REM Check PM2 is installed
pm2 --version

REM Reinstall PM2 if needed
npm install -g pm2

REM Check Python path in ecosystem.config.js
REM Make sure PYTHON_PATH points to venv\Scripts\python.exe
```

### Processes Keep Crashing

```cmd
REM View error logs
pm2 logs orchestrator --err

REM Check application logs
type Logs\ai_employee.log
type Logs\watcher_errors.log

REM Check if another instance is running (lock file)
del Logs\.scheduler.lock 2>nul
```

### Manual Start (Without PM2)

```cmd
cd /d "C:\Users\Dell\Desktop\Hackathon_0\PLATINUM TIER"
venv\Scripts\activate

REM Start orchestrator directly
python scripts\run_ai_employee.py --daemon

REM In another terminal, start file watcher
python file_watcher.py
```

### Reset Everything

```cmd
REM Stop and delete all PM2 processes
pm2 stop all
pm2 delete all

REM Clear PM2 data
pm2 flush

REM Remove lock files
del Logs\.scheduler.lock 2>nul
del Logs\.watcher_state.json 2>nul

REM Restart fresh
pm2 start ecosystem.config.js
pm2 save
```

---

## File Locations

| Component | Location |
|-----------|----------|
| Main Script | `scripts\run_ai_employee.py` |
| File Watcher | `file_watcher.py` |
| Log Manager | `log_manager.py` |
| PM2 Config | `ecosystem.config.js` |
| Start Script | `start.bat` |
| Health Check | `scripts\health_check.bat` |
| System Log | `Logs\System_Log.md` |
| Error Log | `Logs\watcher_errors.log` |
| AI Employee Log | `Logs\ai_employee.log` |

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────┐
│                    PM2 Process Manager                   │
├─────────────────┬─────────────────┬─────────────────────┤
│   orchestrator  │  file-watcher   │    log-manager      │
│   (5 min cycle) │  (5 sec poll)   │   (hourly check)    │
└────────┬────────┴────────┬────────┴──────────┬──────────┘
         │                 │                    │
         ▼                 ▼                    ▼
┌─────────────────────────────────────────────────────────┐
│              Platinum Tier AI Employee                   │
│  ┌─────────────┐  ┌──────────────┐  ┌────────────────┐ │
│  │ Inbox/      │  │ Needs_Action/│  │ Needs_Approval/│ │
│  │ (new files) │  │ (pending)    │  │ (waiting)      │ │
│  └─────────────┘  └──────────────┘  └────────────────┘ │
│  ┌─────────────┐  ┌──────────────┐  ┌────────────────┐ │
│  │ Plans/      │  │ Done/        │  │ Reports/       │ │
│  │ (plans)     │  │ (completed)  │  │ (CEO briefing) │ │
│  └─────────────┘  └──────────────┘  └────────────────┘ │
└─────────────────────────────────────────────────────────┘
```
