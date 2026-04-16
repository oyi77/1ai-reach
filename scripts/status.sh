#!/bin/bash
echo "📊 1ai-reach Service Status"
echo "=============================="

if pgrep -f "mcp_server.py --transport http" > /dev/null; then
    echo "✅ MCP Server: Running (port 8766)"
else
    echo "❌ MCP Server: Stopped"
fi

if pgrep -f "streamlit run ui/app.py" > /dev/null; then
    echo "✅ Streamlit UI: Running (port 8502)"
else
    echo "❌ Streamlit UI: Stopped"
fi

echo ""
echo "💾 Memory Usage:"
free -h | grep "Mem:" | awk '{print "   Used: " $3 " / " $2}'

echo ""
echo "📝 Recent Logs:"
tail -5 /home/openclaw/.openclaw/workspace/1ai-reach/logs/mcp_server.log 2>/dev/null || echo "   No MCP logs"
