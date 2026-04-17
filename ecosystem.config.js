module.exports = {
  apps: [
    {
      name: '1ai-reach-api',
      script: 'python',
      args: '-m uvicorn oneai_reach.api.main:app --host 0.0.0.0 --port 8000',
      cwd: '/home/openclaw/.openclaw/workspace/1ai-reach',
      interpreter: 'none',
      env: {
        PYTHONPATH: '/home/openclaw/.openclaw/workspace/1ai-reach/src',
        NODE_ENV: 'production'
      },
      instances: 1,
      exec_mode: 'fork',
      autorestart: true,
      watch: false,
      max_memory_restart: '1G',
      error_file: '/home/openclaw/.openclaw/workspace/1ai-reach/logs/pm2-error.log',
      out_file: '/home/openclaw/.openclaw/workspace/1ai-reach/logs/pm2-out.log',
      log_date_format: 'YYYY-MM-DD HH:mm:ss Z',
      merge_logs: true,
      min_uptime: '10s',
      max_restarts: 10
    }
  ]
};
