"""
watchdog.py — System Health Monitor

Monitors the Platinum Tier AI Employee system health:
  - Checks if orchestrator and watchers are running
  - Auto-restarts stopped processes
  - Logs status every 5 minutes
  - Writes status to Logs/system_health.md

Monitoring Modes:
  - PM2: Monitors PM2-managed processes
  - Direct: Monitors processes directly via PID files
  - Hybrid: Both PM2 and direct monitoring

Usage:
    python watchdog.py --daemon          # Run continuously
    python watchdog.py --check           # Single health check
    python watchdog.py --status          # Show current status
    python watchdog.py --restart         # Restart all services
"""

import os
import sys
import json
import subprocess
import argparse
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Tuple


# ============================================================================
# Configuration
# ============================================================================

SCRIPT_DIR = Path(__file__).parent
VAULT_ROOT = SCRIPT_DIR.parent

# Log and status files
LOGS_DIR = VAULT_ROOT / "Logs"
HEALTH_LOG = LOGS_DIR / "system_health.md"
WATCHDOG_LOG = LOGS_DIR / "watchdog.log"
STATE_FILE = LOGS_DIR / ".watchdog_state.json"

# Process definitions
PROCESSES = {
    "orchestrator": {
        "script": "scripts/run_ai_employee.py",
        "args": "--daemon --interval 300",
        "check_pattern": "run_ai_employee.py",
        "pid_file": "Logs/.scheduler.lock",
        "priority": 1,  # Restart order (lower = first)
    },
    "file-watcher": {
        "script": "file_watcher.py",
        "args": "",
        "check_pattern": "file_watcher.py",
        "pid_file": None,
        "priority": 2,
    },
    "log-manager": {
        "script": "log_manager.py",
        "args": "",
        "check_pattern": "log_manager.py",
        "pid_file": None,
        "priority": 3,
    },
    "cloud-worker": {
        "script": "scripts/cloud_worker.py",
        "args": "--daemon",
        "check_pattern": "cloud_worker.py",
        "pid_file": None,
        "priority": 4,
    },
    "local-worker": {
        "script": "scripts/local_worker.py",
        "args": "--daemon",
        "check_pattern": "local_worker.py",
        "pid_file": None,
        "priority": 5,
    },
}

# Health check interval (5 minutes)
CHECK_INTERVAL = 300  # seconds

# Auto-restart settings
MAX_RESTART_ATTEMPTS = 3
RESTART_COOLDOWN = 60  # seconds between restart attempts

# Ensure directories exist
LOGS_DIR.mkdir(parents=True, exist_ok=True)


# ============================================================================
# Logging
# ============================================================================

def log(message: str, level: str = "INFO"):
    """Log to console and watchdog.log"""
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    entry = f"[{timestamp}] [{level}] {message}"
    print(entry)
    
    try:
        with open(WATCHDOG_LOG, "a", encoding="utf-8") as f:
            f.write(entry + "\n")
    except OSError as e:
        print(f"[ERROR] Could not write to watchdog.log: {e}")


def log_health(status: dict):
    """Write status to system_health.md"""
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    
    # Determine overall health
    total = len(status.get("processes", {}))
    running = sum(1 for p in status.get("processes", {}).values() if p.get("status") == "running")
    stopped = total - running
    
    if stopped == 0:
        health_badge = "🟢 HEALTHY"
        health_status = "healthy"
    elif stopped <= total // 2:
        health_badge = "🟡 DEGRADED"
        health_status = "degraded"
    else:
        health_badge = "🔴 CRITICAL"
        health_status = "critical"
    
    # Build markdown content
    content = f"""# System Health Report

> **Status:** {health_badge}
> **Last Check:** {timestamp}
> **Watchdog:** {'Running' if status.get('watchdog_running', False) else 'Stopped'}

---

## Process Status

| Process | Status | PID | Uptime | Restarts |
|---------|--------|-----|--------|----------|
"""
    
    for proc_name, proc_info in status.get("processes", {}).items():
        proc_status = proc_info.get("status", "unknown")
        status_icon = {"running": "🟢", "stopped": "🔴", "starting": "🟡"}.get(proc_status, "⚪")
        pid = proc_info.get("pid", "-")
        uptime = proc_info.get("uptime", "-")
        restarts = proc_info.get("restart_count", 0)
        
        content += f"| {status_icon} {proc_name} | {proc_status} | {pid} | {uptime} | {restarts} |\n"
    
    # System metrics
    content += f"""
---

## System Metrics

| Metric | Value |
|--------|-------|
| CPU Usage | {status.get('cpu_usage', 'N/A')}% |
| Memory Usage | {status.get('memory_usage', 'N/A')} MB |
| Disk Free | {status.get('disk_free', 'N/A')} GB |
| Python Version | {status.get('python_version', 'N/A')} |

---

## Recent Events

| Time | Event | Details |
|------|-------|---------|
"""
    
    for event in status.get("recent_events", [])[-10:]:
        content += f"| {event.get('time', '-')} | {event.get('event', '-')} | {event.get('details', '-')} |\n"
    
    content += f"""
---

## Auto-Restart History

| Time | Process | Attempt | Result |
|------|---------|---------|--------|
"""
    
    for restart in status.get("restart_history", [])[-10:]:
        content += f"| {restart.get('time', '-')} | {restart.get('process', '-')} | {restart.get('attempt', '-')} | {restart.get('result', '-')} |\n"
    
    content += f"""
---

## Configuration

- **Check Interval:** {CHECK_INTERVAL // 60} minutes
- **Max Restart Attempts:** {MAX_RESTART_ATTEMPTS}
- **Restart Cooldown:** {RESTART_COOLDOWN} seconds
- **Monitoring Mode:** {status.get('mode', 'hybrid')}

---

*Generated by watchdog.py*
"""
    
    try:
        with open(HEALTH_LOG, "w", encoding="utf-8") as f:
            f.write(content)
    except OSError as e:
        log(f"Failed to write health report: {e}", "ERROR")


# ============================================================================
# Process Detection
# ============================================================================

def check_pm2_process(name: str) -> Tuple[bool, Optional[int]]:
    """Check if a PM2 process is running"""
    try:
        result = subprocess.run(
            ["pm2", "list", "--json"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        
        if result.returncode != 0:
            return False, None
        
        pm2_data = json.loads(result.stdout)
        
        for proc in pm2_data:
            if proc.get("name") == name:
                pm2_status = proc.get("pm2_env", {}).get("status", "")
                pid = proc.get("pid")
                return pm2_status == "online", pid
                
        return False, None
        
    except (subprocess.TimeoutExpired, FileNotFoundError, json.JSONDecodeError):
        return False, None


def check_direct_process(pattern: str) -> Tuple[bool, Optional[int]]:
    """Check if a process is running via tasklist"""
    try:
        result = subprocess.run(
            ["tasklist", "/FI", f"IMAGENAME eq python.exe", "/FO", "CSV", "/NH"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        
        for line in result.stdout.split("\n"):
            if pattern in line.lower():
                # Extract PID from CSV output
                parts = line.strip('"').split('","')
                if len(parts) >= 2:
                    try:
                        pid = int(parts[1])
                        return True, pid
                    except ValueError:
                        pass
        
        return False, None
        
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return False, None


def check_pid_file(pid_file: Optional[Path]) -> Tuple[bool, Optional[int]]:
    """Check if a PID file exists and process is alive"""
    if not pid_file or not pid_file.exists():
        return False, None
    
    try:
        with open(pid_file, "r", encoding="utf-8") as f:
            pid = int(f.read().strip())
        
        # Check if process is alive
        result = subprocess.run(
            ["tasklist", "/FI", f"PID eq {pid}"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        
        if str(pid) in result.stdout:
            return True, pid
        
        return False, None
        
    except (ValueError, FileNotFoundError, subprocess.TimeoutExpired):
        return False, None


def get_process_status(proc_name: str, proc_config: dict) -> dict:
    """Get comprehensive status for a process"""
    status = {
        "status": "stopped",
        "pid": None,
        "uptime": "-",
        "restart_count": 0,
    }
    
    # Check PM2 first
    pm2_running, pm2_pid = check_pm2_process(proc_name)
    if pm2_running:
        status["status"] = "running"
        status["pid"] = pm2_pid
        status["uptime"] = get_pm2_uptime(proc_name)
        return status
    
    # Check via pattern
    pattern_running, pattern_pid = check_direct_process(proc_config["check_pattern"])
    if pattern_running:
        status["status"] = "running"
        status["pid"] = pattern_pid
        return status
    
    # Check PID file
    if proc_config.get("pid_file"):
        pid_file = VAULT_ROOT / proc_config["pid_file"]
        pid_running, pid = check_pid_file(pid_file)
        if pid_running:
            status["status"] = "running"
            status["pid"] = pid
            return status
    
    return status


def get_pm2_uptime(proc_name: str) -> str:
    """Get uptime for a PM2 process"""
    try:
        result = subprocess.run(
            ["pm2", "describe", proc_name, "--json"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        
        if result.returncode == 0:
            data = json.loads(result.stdout)
            if data:
                uptime_ms = data[0].get("pm2_env", {}).get("pm_uptime", 0)
                uptime_sec = (datetime.now(timezone.utc).timestamp() * 1000 - uptime_ms) / 1000
                
                if uptime_sec < 60:
                    return f"{int(uptime_sec)}s"
                elif uptime_sec < 3600:
                    return f"{int(uptime_sec // 60)}m"
                elif uptime_sec < 86400:
                    return f"{int(uptime_sec // 3600)}h"
                else:
                    return f"{int(uptime_sec // 86400)}d"
    except:
        pass
    
    return "-"


# ============================================================================
# Process Control
# ============================================================================

def start_process(proc_name: str, proc_config: dict) -> bool:
    """Start a process"""
    log(f"Starting {proc_name}...")
    
    script_path = VAULT_ROOT / proc_config["script"]
    
    if not script_path.exists():
        log(f"Script not found: {script_path}", "ERROR")
        return False
    
    # Build command
    cmd = [sys.executable, str(script_path)]
    if proc_config.get("args"):
        cmd.extend(proc_config["args"].split())
    
    try:
        # Start process (detached)
        subprocess.Popen(
            cmd,
            cwd=str(VAULT_ROOT),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.DETACHED_PROCESS,
        )
        
        log(f"Started {proc_name} (PID will be detected on next check)")
        return True
        
    except Exception as e:
        log(f"Failed to start {proc_name}: {e}", "ERROR")
        return False


def start_pm2_process(proc_name: str, proc_config: dict) -> bool:
    """Start a process via PM2"""
    log(f"Starting {proc_name} via PM2...")
    
    script_path = VAULT_ROOT / proc_config["script"]
    
    if not script_path.exists():
        log(f"Script not found: {script_path}", "ERROR")
        return False
    
    # Build PM2 command
    cmd = ["pm2", "start", str(script_path), "--name", proc_name]
    if proc_config.get("args"):
        cmd.extend(["--", proc_config["args"]])
    cmd.extend(["--interpreter", sys.executable])
    
    try:
        result = subprocess.run(
            cmd,
            cwd=str(VAULT_ROOT),
            capture_output=True,
            text=True,
            timeout=30,
        )
        
        if result.returncode == 0:
            log(f"Started {proc_name} via PM2")
            return True
        else:
            log(f"PM2 start failed: {result.stderr}", "ERROR")
            return False
            
    except subprocess.TimeoutExpired:
        log(f"PM2 start timed out for {proc_name}", "ERROR")
        return False
    except FileNotFoundError:
        log("PM2 not found. Install with: npm install -g pm2", "ERROR")
        return False


def restart_process(proc_name: str, proc_config: dict, use_pm2: bool = True) -> bool:
    """Restart a process"""
    log(f"Restarting {proc_name}...")
    
    # Stop first
    if use_pm2:
        subprocess.run(["pm2", "stop", proc_name], capture_output=True, timeout=10)
    else:
        # Kill by pattern
        pattern = proc_config["check_pattern"]
        subprocess.run(["taskkill", "/FI", f"WINDOWTITLE eq *{pattern}*", "/F"], capture_output=True)
    
    time.sleep(2)
    
    # Start
    if use_pm2:
        return start_pm2_process(proc_name, proc_config)
    else:
        return start_process(proc_name, proc_config)


# ============================================================================
# System Metrics
# ============================================================================

def get_system_metrics() -> dict:
    """Get system resource metrics"""
    metrics = {
        "cpu_usage": "N/A",
        "memory_usage": "N/A",
        "disk_free": "N/A",
        "python_version": sys.version.split()[0],
    }
    
    try:
        # CPU and Memory via WMIC
        cpu_result = subprocess.run(
            ["wmic", "cpu", "get", "LoadPercentage", "/value"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        for line in cpu_result.stdout.split("\n"):
            if "LoadPercentage" in line:
                metrics["cpu_usage"] = line.split("=")[1].strip()
        
        # Memory
        mem_result = subprocess.run(
            ["wmic", "OS", "get", "FreePhysicalMemory,TotalVisibleMemorySize", "/value"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        
        free_mem = 0
        total_mem = 0
        for line in mem_result.stdout.split("\n"):
            if "FreePhysicalMemory" in line:
                free_mem = int(line.split("=")[1].strip())
            elif "TotalVisibleMemorySize" in line:
                total_mem = int(line.split("=")[1].strip())
        
        if total_mem > 0:
            used_mem = (total_mem - free_mem) / 1024  # MB
            metrics["memory_usage"] = f"{int(used_mem)}"
        
        # Disk free
        disk_result = subprocess.run(
            ["wmic", "logicaldisk", "where", "DeviceID='%CD:~0,1%:'", "get", "FreeSpace", "/value"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        for line in disk_result.stdout.split("\n"):
            if "FreeSpace" in line and "=" in line:
                free_bytes = int(line.split("=")[1].strip())
                metrics["disk_free"] = f"{free_bytes / (1024**3):.1f}"
                
    except Exception as e:
        log(f"Failed to get system metrics: {e}", "WARN")
    
    return metrics


# ============================================================================
# Health Check
# ============================================================================

def load_state() -> dict:
    """Load watchdog state"""
    if STATE_FILE.exists():
        try:
            with open(STATE_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except:
            pass
    return {
        "restart_counts": {},
        "last_restart": {},
        "events": [],
        "restart_history": [],
    }


def save_state(state: dict):
    """Save watchdog state"""
    try:
        with open(STATE_FILE, "w", encoding="utf-8") as f:
            json.dump(state, f, indent=2)
    except Exception as e:
        log(f"Failed to save state: {e}", "WARN")


def add_event(state: dict, event: str, details: str):
    """Add an event to the state"""
    timestamp = datetime.now(timezone.utc).strftime("%H:%M:%S")
    state["events"].append({
        "time": timestamp,
        "event": event,
        "details": details,
    })
    # Keep last 100 events
    state["events"] = state["events"][-100:]


def run_health_check(use_pm2: bool = True) -> dict:
    """Run a complete health check"""
    log("--- Health Check Started ---")
    
    state = load_state()
    status = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "watchdog_running": True,
        "mode": "pm2" if use_pm2 else "direct",
        "processes": {},
        "recent_events": state.get("events", [])[-10:],
        "restart_history": state.get("restart_history", [])[-10:],
    }
    
    # Add system metrics
    metrics = get_system_metrics()
    status.update(metrics)
    
    # Check each process
    for proc_name, proc_config in sorted(PROCESSES.items(), key=lambda x: x[1]["priority"]):
        proc_status = get_process_status(proc_name, proc_config)
        
        # Auto-restart if stopped
        if proc_status["status"] == "stopped":
            log(f"Process {proc_name} is STOPPED")
            add_event(state, "PROCESS_STOPPED", proc_name)
            
            # Check restart limits
            now = time.time()
            last_restart = state.get("last_restart", {}).get(proc_name, 0)
            restart_count = state.get("restart_counts", {}).get(proc_name, 0)
            
            if now - last_restart > RESTART_COOLDOWN and restart_count < MAX_RESTART_ATTEMPTS:
                # Attempt restart
                log(f"Attempting restart of {proc_name} (attempt {restart_count + 1})")
                
                if use_pm2:
                    success = start_pm2_process(proc_name, proc_config)
                else:
                    success = start_process(proc_name, proc_config)
                
                # Update state
                state["restart_counts"][proc_name] = restart_count + 1
                state["last_restart"][proc_name] = now
                state["restart_history"].append({
                    "time": datetime.now(timezone.utc).strftime("%H:%M:%S"),
                    "process": proc_name,
                    "attempt": restart_count + 1,
                    "result": "SUCCESS" if success else "FAILED",
                })
                
                if success:
                    proc_status["status"] = "starting"
                    add_event(state, "RESTART_SUCCESS", proc_name)
                else:
                    add_event(state, "RESTART_FAILED", proc_name)
            elif restart_count >= MAX_RESTART_ATTEMPTS:
                log(f"Max restart attempts reached for {proc_name}", "ERROR")
                add_event(state, "MAX_RESTARTS_REACHED", proc_name)
        
        status["processes"][proc_name] = proc_status
    
    # Save state
    save_state(state)
    
    # Write health report
    log_health(status)
    
    # Summary
    running = sum(1 for p in status["processes"].values() if p["status"] == "running")
    total = len(status["processes"])
    log(f"--- Health Check Complete: {running}/{total} processes running ---")
    
    return status


# ============================================================================
# Commands
# ============================================================================

def run_daemon(use_pm2: bool = True):
    """Run watchdog in daemon mode"""
    log("=" * 50)
    print("  System Watchdog - Daemon Mode")
    print("=" * 50)
    print(f"  Check Interval: {CHECK_INTERVAL // 60} minutes")
    print(f"  Monitoring: PM2 = {use_pm2}")
    print(f"  Health Log: {HEALTH_LOG}")
    print("=" * 50)
    
    try:
        while True:
            run_health_check(use_pm2)
            time.sleep(CHECK_INTERVAL)
    except KeyboardInterrupt:
        log("Watchdog stopped by user")


def show_status(use_pm2: bool = True):
    """Show current system status"""
    status = run_health_check(use_pm2)
    
    print()
    print("=" * 60)
    print("  System Health Status")
    print("=" * 60)
    print()
    
    # Overall status
    total = len(status["processes"])
    running = sum(1 for p in status["processes"].values() if p["status"] == "running")
    
    if running == total:
        print("  Overall: 🟢 HEALTHY")
    elif running >= total // 2:
        print("  Overall: 🟡 DEGRADED")
    else:
        print("  Overall: 🔴 CRITICAL")
    
    print()
    print("  Process Status:")
    print("  " + "-" * 50)
    
    for proc_name, proc_info in status["processes"].items():
        icon = {"running": "🟢", "stopped": "🔴", "starting": "🟡"}.get(
            proc_info["status"], "⚪"
        )
        pid = proc_info.get("pid", "-")
        print(f"  {icon} {proc_name:20} PID: {str(pid):8} {proc_info['status']}")
    
    print()
    print("  System Metrics:")
    print("  " + "-" * 50)
    print(f"  CPU Usage:    {status.get('cpu_usage', 'N/A')}%")
    print(f"  Memory Usage: {status.get('memory_usage', 'N/A')} MB")
    print(f"  Disk Free:    {status.get('disk_free', 'N/A')} GB")
    print()
    print("=" * 60)
    print(f"  Full report: {HEALTH_LOG}")
    print("=" * 60)


def restart_all(use_pm2: bool = True):
    """Restart all services"""
    log("Restarting all services...")
    
    # Stop all first
    if use_pm2:
        subprocess.run(["pm2", "stop", "all"], capture_output=True)
    else:
        for proc_name, proc_config in PROCESSES.items():
            pattern = proc_config["check_pattern"]
            subprocess.run(["taskkill", "/FI", f"WINDOWTITLE eq *{pattern}*", "/F"], capture_output=True)
    
    time.sleep(3)
    
    # Start all in priority order
    for proc_name, proc_config in sorted(PROCESSES.items(), key=lambda x: x[1]["priority"]):
        if use_pm2:
            start_pm2_process(proc_name, proc_config)
        else:
            start_process(proc_name, proc_config)
        time.sleep(1)
    
    log("All services restart initiated")
    
    # Verify
    time.sleep(5)
    show_status(use_pm2)


# ============================================================================
# Entry Point
# ============================================================================

def main():
    parser = argparse.ArgumentParser(description="System Health Watchdog")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--daemon", action="store_true", help="Run continuously")
    group.add_argument("--check", action="store_true", help="Single health check")
    group.add_argument("--status", action="store_true", help="Show status")
    group.add_argument("--restart", action="store_true", help="Restart all services")
    
    parser.add_argument(
        "--no-pm2", action="store_true", help="Don't use PM2 (direct monitoring)"
    )
    
    args = parser.parse_args()
    use_pm2 = not args.no_pm2
    
    if args.daemon:
        run_daemon(use_pm2)
    elif args.check:
        run_health_check(use_pm2)
    elif args.status:
        show_status(use_pm2)
    elif args.restart:
        restart_all(use_pm2)


if __name__ == "__main__":
    main()
