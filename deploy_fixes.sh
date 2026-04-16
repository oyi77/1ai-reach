#!/bin/bash
# Deploy bug fixes for conversation API

echo "=== Deploying Conversation API Fixes ==="
echo ""

# Check if running as root or with sudo
if [ "$EUID" -ne 0 ]; then 
    echo "⚠️  This script needs sudo to restart the service"
    echo "Run: sudo bash deploy_fixes.sh"
    exit 1
fi

echo "1. Restarting webhook server..."
systemctl restart 1ai-reach-mcp

echo ""
echo "2. Checking service status..."
sleep 2
systemctl status 1ai-reach-mcp --no-pager | head -10

echo ""
echo "3. Checking if service is running..."
if systemctl is-active --quiet 1ai-reach-mcp; then
    echo "✅ Service is running"
else
    echo "❌ Service failed to start"
    echo ""
    echo "Check logs with:"
    echo "  sudo journalctl -u 1ai-reach-mcp -n 50"
    exit 1
fi

echo ""
echo "4. Testing feedback endpoint..."
sleep 1
response=$(curl -s -o /dev/null -w "%{http_code}" https://engage.aitradepulse.com/api/conversations/25/feedback)
if [ "$response" = "200" ]; then
    echo "✅ Feedback endpoint working (HTTP $response)"
else
    echo "⚠️  Feedback endpoint returned HTTP $response"
fi

echo ""
echo "5. Testing conversations endpoint..."
response=$(curl -s -o /dev/null -w "%{http_code}" https://engage.aitradepulse.com/api/conversations)
if [ "$response" = "200" ]; then
    echo "✅ Conversations endpoint working (HTTP $response)"
else
    echo "❌ Conversations endpoint returned HTTP $response"
fi

echo ""
echo "=== Deployment Complete ==="
echo ""
echo "Next steps:"
echo "  1. Check the dashboard at https://engage.aitradepulse.com/conversations"
echo "  2. Verify no duplicate conversations appear"
echo "  3. Test feedback functionality"
echo ""
