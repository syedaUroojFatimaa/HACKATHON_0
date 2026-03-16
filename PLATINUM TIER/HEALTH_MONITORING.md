# System Health Monitoring Guide

## Overview

The Platinum Tier AI Employee includes a comprehensive health monitoring system that:

- ✅ Checks if orchestrator and watchers are running
- ✅ Auto-restarts stopped processes
- ✅ Logs status every 5 minutes
- ✅ Writes status to `Logs/system_health.md`

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                     System Watchdog                              │
│                     (watchdog.py)                                │
│                                                                  │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │  Process Monitoring                                       │   │
│  │  ├── PM2 monitoring (if available)                        │   │
│  │  ├── Direct process detection (tasklist)                  │   │
│  │  └── PID file checking                                    │   │
│  └──────────────────────────────────────────────────────────┘   │
│                                                                  │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │  Auto-Restart Logic                                       │   │
│  │  ├── Max 3 restart attempts                               │   │
│  │  ├── 60-second cooldown between restarts                  │   │
│  │  └── Priority-based restart order                         │   │
│  └──────────────────────────────────────────────────────────┘   │
│                                                                  │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │  Health Reporting                                         │   │
│  │  ├── Logs/system_health.md (human-readable)               │   │
│  │  ├── Logs/watchdog.log (detailed log)                     │   │
│  │  └── System metrics (CPU, memory, disk)                   │   │
│  └──────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
```

---

## Monitored Processes

| Process | Priority | Script | Auto-Restart |
|---------|----------|--------|--------------|
| orchestrator | 1 | `scripts/run_ai_employee.py` | ✅ |
| file-watcher | 2 | `file_watcher.py` | ✅ |
| log-manager | 3 | `log_manager.py` | ✅ |
| cloud-worker | 4 | `scripts/cloud_worker.py` | ✅ |
| local-worker | 5 | `scripts/local_worker.py` | ✅ |
| watchdog | N/A | `watchdog.py` | ✅ (via PM2) |

---

## Setup Options

### Option 1: Windows Task Scheduler (Recommended)

**Step 1: Run Setup (as Administrator)**

```cmd
cd "C:\Users\Dell\Desktop\Hackathon_0\PLATINUM TIER"
scripts\setup_watchdog.bat
```

**Step 2: Verify Installation**

```cmd
schtasks /Query /TN "PlatinumTierWatchdog"
```

**Step 3: Check First Run**

Wait 5 minutes, then check:
```cmd
type Logs\system_health.md
```

### Option 2: PM2 Monitoring

**Step 1: Add Watchdog to PM2**

```cmd
pm2 start watchdog.py --name watchdog --interpreter python -- --daemon
```

**Or use ecosystem.config.js:**

```cmd
pm2 start ecosystem.config.js
pm2 save
```

**Step 2: Verify**

```cmd
pm2 status
pm2 logs watchdog
```

---

## Commands

### Watchdog Commands

```cmd
REM Run continuous monitoring (daemon mode)
python watchdog.py --daemon

REM Run single health check
python watchdog.py --check

REM Show current status
python watchdog.py --status

REM Restart all services
python watchdog.py --restart

REM Run without PM2 (direct monitoring)
python watchdog.py --daemon --no-pm2
```

### Batch Scripts

```cmd
REM Quick health check
scripts\health_monitor.bat

REM Disable auto-start
scripts\disable_watchdog.bat

REM Re-enable auto-start (as Admin)
scripts\enable_watchdog.bat
```

### Task Scheduler Commands

```cmd
REM View task status
schtasks /Query /TN "PlatinumTierWatchdog"

REM Run task manually
schtasks /Run /TN "PlatinumTierWatchdog"

REM Delete task
schtasks /Delete /TN "PlatinumTierWatchdog" /F

REM View task history
Get-ScheduledTaskInfo "PlatinumTierWatchdog" | Format-List
```

### PM2 Commands

```cmd
REM View watchdog status
pm2 show watchdog

REM View watchdog logs
pm2 logs watchdog --lines 50

REM Restart watchdog
pm2 restart watchdog

REM Stop watchdog
pm2 stop watchdog

REM Delete watchdog
pm2 delete watchdog
```

---

## Health Report Format

The `Logs/system_health.md` file contains:

```markdown
# System Health Report

> **Status:** 🟢 HEALTHY
> **Last Check:** 2026-03-16 10:30:00 UTC
> **Watchdog:** Running

---

## Process Status

| Process | Status | PID | Uptime | Restarts |
|---------|--------|-----|--------|----------|
| 🟢 orchestrator | running | 12345 | 2h | 0 |
| 🟢 file-watcher | running | 12346 | 2h | 0 |
| ... |

---

## System Metrics

| Metric | Value |
|--------|-------|
| CPU Usage | 15% |
| Memory Usage | 512 MB |
| Disk Free | 250.5 GB |
| Python Version | 3.11.0 |

---

## Recent Events

| Time | Event | Details |
|------|-------|---------|
| 10:25:00 | PROCESS_STOPPED | file-watcher |
| 10:25:05 | RESTART_SUCCESS | file-watcher |

---

## Auto-Restart History

| Time | Process | Attempt | Result |
|------|---------|---------|--------|
| 10:25:05 | file-watcher | 1 | SUCCESS |
```

---

## Status Indicators

| Icon | Status | Meaning |
|------|--------|---------|
| 🟢 | HEALTHY | All processes running |
| 🟡 | DEGRADED | Some processes stopped (≤50%) |
| 🔴 | CRITICAL | Most processes stopped (>50%) |

---

## Auto-Restart Logic

### Restart Conditions

1. Process detected as stopped
2. Last restart was >60 seconds ago
3. Restart attempts <3 (max attempts)

### Restart Order

Processes are restarted in priority order:
1. orchestrator (priority 1)
2. file-watcher (priority 2)
3. log-manager (priority 3)
4. cloud-worker (priority 4)
5. local-worker (priority 5)

### Restart Limits

- **Max attempts per process:** 3
- **Cooldown between attempts:** 60 seconds
- **Lock detection:** Prevents restart loops

---

## Troubleshooting

### Watchdog Not Running

```cmd
REM Check if task exists
schtasks /Query /TN "PlatinumTierWatchdog"

REM Check if Python is available
where python

REM Run manually to test
python watchdog.py --check
```

### Processes Keep Stopping

```cmd
REM Check watchdog logs
type Logs\watchdog.log

REM Check PM2 logs
pm2 logs

REM Check process-specific logs
type Logs\ai_employee.log
type Logs\cloud_worker.log
type Logs\local_worker.log
```

### Auto-Restart Not Working

```cmd
REM Check restart history in health report
type Logs\system_health.md

REM Check if max restarts reached
REM (Reset state if needed)
del Logs\.watchdog_state.json
```

### Health Report Not Updating

```cmd
REM Check if Logs directory exists
dir Logs

REM Check file permissions
icacls Logs\system_health.md

REM Run watchdog manually
python watchdog.py --check
```

---

## Configuration

### Edit Check Interval

In `watchdog.py`, modify:
```python
CHECK_INTERVAL = 300  # seconds (5 minutes)
```

### Edit Restart Settings

In `watchdog.py`, modify:
```python
MAX_RESTART_ATTEMPTS = 3   # Max restarts per process
RESTART_COOLDOWN = 60      # Seconds between attempts
```

### Add/Remove Monitored Processes

In `watchdog.py`, modify the `PROCESSES` dictionary:
```python
PROCESSES = {
    "my-new-process": {
        "script": "path/to/script.py",
        "args": "--daemon",
        "check_pattern": "script.py",
        "pid_file": None,
        "priority": 6,
    },
}
```

---

## Integration with Other Systems

### PM2 + Task Scheduler (Hybrid)

Use PM2 for process management and Task Scheduler for watchdog:

```cmd
REM Start all processes with PM2
pm2 start ecosystem.config.js
pm2 save

REM Run watchdog via Task Scheduler
scripts\setup_watchdog.bat
```

Watchdog will detect PM2 processes and report their status.

### External Monitoring

For external monitoring (e.g., Uptime Kuma, Nagios):

```cmd
REM Parse health report for status
powershell -Command "(Get-Content Logs\system_health.md) -match '🟢|🟡|🔴'"
```

### Email Alerts

Create a script to send alerts on critical status:

```python
# Check health status
with open("Logs/system_health.md") as f:
    content = f.read()

if "🔴 CRITICAL" in content:
    # Send alert email
    send_alert("System Critical!")
```

---

## Best Practices

1. **Run watchdog via Task Scheduler** for reliability
2. **Monitor the watchdog** (PM2 auto-restarts it)
3. **Review health reports daily** for trends
4. **Set up external alerts** for critical status
5. **Keep logs rotated** (log_manager.py handles this)
6. **Test restarts periodically** to ensure they work

---

## Quick Reference

| Task | Command |
|------|---------|
| Setup auto-start | `scripts\setup_watchdog.bat` (Admin) |
| Check status | `python watchdog.py --status` |
| View health report | `type Logs\system_health.md` |
| Disable auto-start | `scripts\disable_watchdog.bat` |
| Restart all services | `python watchdog.py --restart` |
| PM2 status | `pm2 status` |
| PM2 logs | `pm2 logs` |

---

## File Locations

| File | Purpose |
|------|---------|
| `watchdog.py` | Main health monitoring script |
| `Logs/system_health.md` | Health status report |
| `Logs/watchdog.log` | Watchdog activity log |
| `Logs\.watchdog_state.json` | Restart state tracking |
| `scripts\setup_watchdog.bat` | Task Scheduler setup |
| `scripts\health_monitor.bat` | Quick health check |
