/**
 * PM2 Ecosystem Configuration
 * Platinum Tier AI Employee - 24/7 Operation
 * 
 * Usage:
 *   pm2 start ecosystem.config.js
 *   pm2 stop ecosystem.config.js
 *   pm2 restart ecosystem.config.js
 *   pm2 delete ecosystem.config.js
 */

module.exports = {
  apps: [
    {
      /**
       * Main Orchestrator - Silver Scheduler
       * Runs the full AI employee cycle every 5 minutes:
       * - Inbox scanning
       * - Task planning
       * - Ralph loop execution
       * - Task processing
       * - Approval checking
       * - Error recovery
       * - CEO weekly briefing
       */
      name: 'orchestrator',
      script: 'scripts\\run_ai_employee.py',
      args: '--daemon --interval 300',
      interpreter: 'python',
      cwd: __dirname,
      instances: 1,
      autorestart: true,
      watch: false,
      max_memory_restart: '500M',
      env: {
        PYTHONUNBUFFERED: '1',
        PYTHONIOENCODING: 'utf-8',
      },
      error_file: './Logs/pm2_orchestrator_err.log',
      out_file: './Logs/pm2_orchestrator_out.log',
      log_file: './Logs/pm2_orchestrator_combined.log',
      time: true,
      merge_logs: true,
      restart_delay: 5000,
      max_restarts: 10,
      min_uptime: '30s',
    },
    {
      /**
       * File Watcher - Bronze Tier Inbox Monitor
       * Polls Inbox folder every 5 seconds for new files
       * Creates tasks automatically when files appear
       */
      name: 'file-watcher',
      script: 'file_watcher.py',
      interpreter: 'python',
      cwd: __dirname,
      instances: 1,
      autorestart: true,
      watch: false,
      max_memory_restart: '200M',
      env: {
        PYTHONUNBUFFERED: '1',
        PYTHONIOENCODING: 'utf-8',
      },
      error_file: './Logs/pm2_file_watcher_err.log',
      out_file: './Logs/pm2_file_watcher_out.log',
      log_file: './Logs/pm2_file_watcher_combined.log',
      time: true,
      merge_logs: true,
      restart_delay: 3000,
      max_restarts: 10,
      min_uptime: '20s',
    },
    {
      /**
       * Log Manager - Bronze Tier Log Rotation
       * Runs hourly to rotate logs exceeding 1MB
       * Prevents disk space exhaustion
       */
      name: 'log-manager',
      script: 'log_manager.py',
      interpreter: 'python',
      cwd: __dirname,
      instances: 1,
      autorestart: true,
      watch: false,
      max_memory_restart: '100M',
      env: {
        PYTHONUNBUFFERED: '1',
        PYTHONIOENCODING: 'utf-8',
      },
      error_file: './Logs/pm2_log_manager_err.log',
      out_file: './Logs/pm2_log_manager_out.log',
      log_file: './Logs/pm2_log_manager_combined.log',
      time: true,
      merge_logs: true,
      restart_delay: 3000,
      max_restarts: 5,
      min_uptime: '10s',
      cron_restart: '0 * * * *', // Run every hour via cron
    },
    {
      /**
       * Cloud Worker - Work Zone Processor
       * Handles email triage, drafting replies, social posts
       * Creates approval files only (never sends/posts)
       */
      name: 'cloud-worker',
      script: 'scripts\\cloud_worker.py',
      args: '--daemon',
      interpreter: 'python',
      cwd: __dirname,
      instances: 1,
      autorestart: true,
      watch: false,
      max_memory_restart: '300M',
      env: {
        PYTHONUNBUFFERED: '1',
        PYTHONIOENCODING: 'utf-8',
      },
      error_file: './Logs/pm2_cloud_worker_err.log',
      out_file: './Logs/pm2_cloud_worker_out.log',
      log_file: './Logs/pm2_cloud_worker_combined.log',
      time: true,
      merge_logs: true,
      restart_delay: 5000,
      max_restarts: 10,
      min_uptime: '30s',
    },
    {
      /**
       * Local Worker - Work Zone Processor
       * Handles approvals, final send/post actions,
       * WhatsApp session, payments, Dashboard updates
       */
      name: 'local-worker',
      script: 'scripts\\local_worker.py',
      args: '--daemon',
      interpreter: 'python',
      cwd: __dirname,
      instances: 1,
      autorestart: true,
      watch: false,
      max_memory_restart: '300M',
      env: {
        PYTHONUNBUFFERED: '1',
        PYTHONIOENCODING: 'utf-8',
      },
      error_file: './Logs/pm2_local_worker_err.log',
      out_file: './Logs/pm2_local_worker_out.log',
      log_file: './Logs/pm2_local_worker_combined.log',
      time: true,
      merge_logs: true,
      restart_delay: 5000,
      max_restarts: 10,
      min_uptime: '30s',
    },
    {
      /**
       * System Watchdog - Health Monitor
       * Monitors all processes, auto-restarts if stopped,
       * logs status every 5 minutes to system_health.md
       */
      name: 'watchdog',
      script: 'watchdog.py',
      args: '--daemon',
      interpreter: 'python',
      cwd: __dirname,
      instances: 1,
      autorestart: true,
      watch: false,
      max_memory_restart: '200M',
      env: {
        PYTHONUNBUFFERED: '1',
        PYTHONIOENCODING: 'utf-8',
      },
      error_file: './Logs/pm2_watchdog_err.log',
      out_file: './Logs/pm2_watchdog_out.log',
      log_file: './Logs/pm2_watchdog_combined.log',
      time: true,
      merge_logs: true,
      restart_delay: 3000,
      max_restarts: 5,
      min_uptime: '60s',
    },
  ],
};
