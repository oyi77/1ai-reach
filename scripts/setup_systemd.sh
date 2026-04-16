#!/bin/bash
# Setup systemd services for 1ai-reach auto-start on boot

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

echo "🔧 Setting up systemd services for 1ai-reach..."
echo ""

# Create log directory
mkdir -p "$PROJECT_DIR/logs"

# Copy service files
echo "📋 Installing service files..."
sudo cp "$PROJECT_DIR/systemd/"*.service /etc/systemd/system/

# Reload systemd
sudo systemctl daemon-reload

# Enable services
sudo systemctl enable 1ai-reach-mcp.service
sudo systemctl enable 1ai-reach-ui.service
sudo systemctl enable 1ai-reach-watchdog.service

echo ""
echo "✅ Systemd services installed!"
echo ""
echo "Commands:"
echo "  sudo systemctl start 1ai-reach-mcp    # Start MCP Server"
echo "  sudo systemctl start 1ai-reach-ui       # Start Streamlit UI"
echo "  sudo systemctl start 1ai-reach-watchdog # Start Watchdog"
echo "  sudo systemctl status 1ai-reach-*       # Check status"
echo ""
echo "Or use: ./scripts/start_all.sh"
echo ""
read -p "Start services now? (y/n) " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    sudo systemctl start 1ai-reach-mcp
    sudo systemctl start 1ai-reach-ui
    sudo systemctl start 1ai-reach-watchdog
    echo ""
    echo "✅ Services started!"
    sleep 2
    sudo systemctl status 1ai-reach-mcp --no-pager
fi
