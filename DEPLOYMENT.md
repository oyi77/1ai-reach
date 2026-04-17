# 1ai-reach API Deployment Guide

**Date**: 2026-04-17T23:01:19.583Z  
**Status**: Ready for deployment

---

## Deployment Options

You can deploy the 1ai-reach API using either **systemd** or **PM2**.

---

## Option 1: Deploy with systemd (Recommended)

### 1. Install the systemd service

```bash
cd /home/openclaw/.openclaw/workspace/1ai-reach

# Copy service file to systemd
sudo cp 1ai-reach-api.service /etc/systemd/system/

# Reload systemd
sudo systemctl daemon-reload

# Enable service (start on boot)
sudo systemctl enable 1ai-reach-api

# Start service
sudo systemctl start 1ai-reach-api

# Check status
sudo systemctl status 1ai-reach-api

# View logs
sudo journalctl -u 1ai-reach-api -f
```

### 2. Add to Cloudflare Router

```bash
cd ~/.cloudflare-router

# Add the API to apps.yaml
# Edit apps.yaml and add:
```

```yaml
  1ai-reach-api:
    mode: port
    enabled: true
    hostname: 1ai-reach.aitradepulse.com
    port: 8000
    health_check: /health
```

```bash
# Restart cloudflare router
pm2 restart cf-router

# Or if using systemd
sudo systemctl restart cloudflare-router
```

### 3. Configure WAHA Webhook

```bash
# Get active WAHA sessions
curl http://waha.aitradepulse.com/api/sessions

# Configure webhook for your session (replace {session} with actual session name)
curl -X POST http://waha.aitradepulse.com/api/sessions/{session}/webhook \
  -H "Content-Type: application/json" \
  -d '{
    "url": "https://1ai-reach.aitradepulse.com/api/v1/webhooks/waha/message",
    "events": ["message", "message.any"]
  }'
```

### 4. Verify Deployment

```bash
# Check API health
curl https://1ai-reach.aitradepulse.com/health

# Test webhook (should return session_not_found if session doesn't exist)
curl -X POST https://1ai-reach.aitradepulse.com/api/v1/webhooks/waha/message \
  -H "Content-Type: application/json" \
  -d '{
    "event": "message",
    "session": "test",
    "payload": {
      "from": "+6281234567890",
      "body": "test"
    }
  }'
```

---

## Option 2: Deploy with PM2

### 1. Start with PM2

```bash
cd /home/openclaw/.openclaw/workspace/1ai-reach

# Start the API
pm2 start ecosystem.config.js

# Save PM2 process list
pm2 save

# Setup PM2 startup script
pm2 startup

# Check status
pm2 status

# View logs
pm2 logs 1ai-reach-api
```

### 2. Add to Cloudflare Router

Same as systemd option above (step 2).

### 3. Configure WAHA Webhook

Same as systemd option above (step 3).

---

## Environment Variables

Ensure `.env` file has the correct configuration:

```bash
# WAHA Configuration
WAHA_BASE_URL=https://waha.aitradepulse.com
WAHA_API_KEY=199c96bcb87e45a39f6cde9e5677ed09

# API Configuration
API_PORT=8000
API_HOST=0.0.0.0

# LLM Configuration (for CS responses)
# Add your LLM API keys here
```

---

## Service Management

### systemd Commands

```bash
# Start
sudo systemctl start 1ai-reach-api

# Stop
sudo systemctl stop 1ai-reach-api

# Restart
sudo systemctl restart 1ai-reach-api

# Status
sudo systemctl status 1ai-reach-api

# Logs
sudo journalctl -u 1ai-reach-api -f

# Enable (start on boot)
sudo systemctl enable 1ai-reach-api

# Disable (don't start on boot)
sudo systemctl disable 1ai-reach-api
```

### PM2 Commands

```bash
# Start
pm2 start 1ai-reach-api

# Stop
pm2 stop 1ai-reach-api

# Restart
pm2 restart 1ai-reach-api

# Status
pm2 status

# Logs
pm2 logs 1ai-reach-api

# Monitor
pm2 monit
```

---

## Testing CS & Engagement

Once deployed, test the CS engine with a real WhatsApp message:

1. **Send WhatsApp message** to the connected number
2. **Check logs** for processing:
   ```bash
   # systemd
   sudo journalctl -u 1ai-reach-api -f
   
   # PM2
   pm2 logs 1ai-reach-api
   ```
3. **Verify response** in WhatsApp
4. **Check database** for conversation record:
   ```bash
   sqlite3 data/cs_conversations.db "SELECT * FROM conversations ORDER BY created_at DESC LIMIT 5;"
   ```

---

## Troubleshooting

### API won't start

```bash
# Check if port 8000 is already in use
sudo lsof -i :8000

# Check Python path
which python3

# Test import manually
cd /home/openclaw/.openclaw/workspace/1ai-reach
PYTHONPATH=src python3 -c "from oneai_reach.api.main import app; print('OK')"
```

### Webhook not receiving messages

```bash
# Check WAHA webhook configuration
curl http://waha.aitradepulse.com/api/sessions/{session}/webhook

# Check if API is accessible from WAHA
curl https://1ai-reach.aitradepulse.com/health

# Check cloudflare router
curl http://localhost:7070/api/status
```

### CS engine not responding

```bash
# Check if LLM API keys are configured
grep -E "(OPENAI|ANTHROPIC|GEMINI)" .env

# Check CS engine logs
sudo journalctl -u 1ai-reach-api -f | grep "cs_engine"
```

---

## Monitoring

### Health Check

```bash
# API health
curl https://1ai-reach.aitradepulse.com/health

# Expected response:
# {"status":"healthy","timestamp":"...","version":"1.0.0"}
```

### Metrics

```bash
# Check conversation outcomes
sqlite3 data/cs_outcomes.db "SELECT status, COUNT(*) FROM outcomes GROUP BY status;"

# Check engagement rate
sqlite3 data/cs_outcomes.db "
  SELECT 
    COUNT(*) as total,
    SUM(CASE WHEN status != 'abandoned' THEN 1 ELSE 0 END) as engaged,
    ROUND(100.0 * SUM(CASE WHEN status != 'abandoned' THEN 1 ELSE 0 END) / COUNT(*), 2) as engagement_rate
  FROM outcomes;
"
```

---

## Rollback

If you need to rollback to the old scripts:

```bash
# Stop new API
sudo systemctl stop 1ai-reach-api
# or
pm2 stop 1ai-reach-api

# The old scripts still work via backward compatibility shims
python3 scripts/webhook_server.py
```

---

## Next Steps

1. ✅ Deploy API (systemd or PM2)
2. ✅ Add to cloudflare router
3. ✅ Configure WAHA webhook
4. ✅ Test with real WhatsApp message
5. ✅ Monitor engagement metrics
6. ✅ Enable voice features (optional)

---

**Deployment Status**: Ready  
**API Port**: 8000  
**Public URL**: https://1ai-reach.aitradepulse.com  
**WAHA URL**: https://waha.aitradepulse.com
