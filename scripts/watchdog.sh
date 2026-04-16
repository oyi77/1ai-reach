#!/bin/bash
LOG_FILE="/home/openclaw/.openclaw/workspace/1ai-reach/logs/watchdog.log"
mkdir -p "$(dirname "$LOG_FILE")"

check_and_restart() {
    if ! pgrep -f "$1" > /dev/null 2>&1; then
        echo "[$(date)] $2 is down, restarting..." >> "$LOG_FILE"
        /home/openclaw/.openclaw/workspace/1ai-reach/scripts/start_all.sh
    fi
}

while true; do
    check_and_restart "mcp_server.py --transport http" "MCP Server"
    check_and_restart "streamlit run ui/app.py" "Streamlit UI"
    sleep 60
done
