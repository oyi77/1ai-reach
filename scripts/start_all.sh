#!/bin/bash
# 1ai-reach Auto-Start Script
# Usage: ./start_all.sh
# This script starts all required services for 1ai-reach

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
LOG_DIR="$PROJECT_DIR/logs"
mkdir -p "$LOG_DIR"

echo "🚀 Starting 1ai-reach Services..."
echo "=================================="
echo ""

# Function to check if process is running
check_process() {
    pgrep -f "$1" > /dev/null 2>&1
}

# Function to kill existing processes
kill_existing() {
    pkill -f "$1" 2>/dev/null || true
}

# 1. Kill existing processes
echo "🧹 Cleaning up existing processes..."
kill_existing "mcp_server.py --transport http"
kill_existing "streamlit run ui/app.py"
sleep 2

# 2. Start MCP Server
echo "🤖 Starting MCP Server (port 8766)..."
if ! check_process "mcp_server.py --transport http"; then
    nohup python3 "$PROJECT_DIR/mcp_server.py" --transport http --host 0.0.0.0 --port 8766 > "$LOG_DIR/mcp_server.log" 2>&1 &
    sleep 3
    if check_process "mcp_server.py --transport http"; then
        echo "   ✅ MCP Server started successfully"
    else
        echo "   ❌ MCP Server failed to start"
        exit 1
    fi
else
    echo "   ⚠️  MCP Server already running"
fi

# 3. Start Streamlit UI
echo "🌐 Starting Streamlit UI (port 8502)..."
if ! check_process "streamlit run ui/app.py"; then
    cd "$PROJECT_DIR"
    nohup streamlit run ui/app.py --server.port 8502 --server.address 0.0.0.0 --server.headless true > "$LOG_DIR/streamlit.log" 2>&1 &
    sleep 5
    if check_process "streamlit run ui/app.py"; then
        echo "   ✅ Streamlit UI started successfully"
    else
        echo "   ❌ Streamlit UI failed to start"
        exit 1
    fi
else
    echo "   ⚠️  Streamlit UI already running"
fi

# 4. Verify WAHA connections
echo ""
echo "📱 Checking WAHA connections..."
WAHA_URL="https://waha.aitradepulse.com"
if curl -s "$WAHA_URL/api/sessions" -H "X-Api-Key: 199c96bcb87e45a39f6cde9e5677ed09" > /dev/null 2>&1; then
    echo "   ✅ WAHA API is reachable"
else
    echo "   ⚠️  WAHA API not reachable (may need manual check)"
fi

# 5. Print status
echo ""
echo "=================================="
echo "✅ All services started!"
echo ""
echo "📊 Service Status:"
echo "   • MCP Server: http://localhost:8766"
echo "   • Streamlit UI: http://localhost:8502"
echo "   • Public URL: https://engage.aitradepulse.com"
echo ""
echo "📋 Active Sessions:"
curl -s "https://waha.aitradepulse.com/api/sessions" -H "X-Api-Key: 199c96bcb87e45a39f6cde9e5677ed09" 2>/dev/null | grep -o '"name":"[^"]*"' | sed 's/"name":"/   • /' | sed 's/"//' || echo "   (Check WAHA manually)"
echo ""
echo "📝 Logs available in: $LOG_DIR"
echo ""
echo "💡 To stop all services: ./scripts/stop_all.sh"
echo "💡 To check status: ./scripts/status.sh"
