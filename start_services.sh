#!/bin/bash

LOG_DIR="/home/openclaw/.openclaw/workspace/1ai-reach/logs"
mkdir -p "$LOG_DIR"

echo "🚀 Starting 1ai-reach Services..."

# Kill existing
pkill -f "webhook_server.py" 2>/dev/null
sleep 2

# Start webhook server with auto-restart wrapper
nohup bash -c '
    while true; do
        python3 /home/openclaw/.openclaw/workspace/1ai-reach/webhook_server.py >> /home/openclaw/.openclaw/workspace/1ai-reach/logs/webhook_server.log 2>&1
        echo "[$(date)] Webhook crashed, restarting in 5s..." >> /home/openclaw/.openclaw/workspace/1ai-reach/logs/crashes.log
        sleep 5
    done
' > /dev/null 2>&1 &

echo "✅ Webhook server started (auto-restart enabled)"

cd /home/openclaw/.openclaw/workspace/1ai-reach

sleep 3
echo ""
echo "Services status:"
echo "  - Webhook: http://localhost:8766"
echo "  - Public: https://engage.aitradepulse.com"
