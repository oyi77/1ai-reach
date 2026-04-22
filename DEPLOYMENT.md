# 1ai-reach Deployment Guide

Complete guide for deploying 1ai-reach infrastructure with Cloudflare Tunnel and cf-router.

---

## Infrastructure Overview

### Architecture

```
Internet → Cloudflare Edge → Cloudflare Tunnel → nginx:6969 (cf-router) → Internal Services
                                                                          ├─ reach.aitradepulse.com → localhost:8502 (Dashboard)
                                                                          └─ (future subdomains) → localhost:XXXX
```

### Key Components

| Component | Purpose | Port | Service |
|---|---|---|---|
| **Cloudflare Tunnel** | Secure tunnel to Cloudflare edge | - | `cloudflared.service` |
| **cf-router (nginx)** | Reverse proxy for subdomain routing | 6969 | Managed by cf-router daemon |
| **1ai-reach Dashboard** | Next.js frontend | 8502 | `1ai-reach-dashboard.service` |
| **1ai-reach API** | FastAPI backend | 8001 | `1ai-reach-api.service` |
| **1ai-reach MCP** | Webhook server | - | `1ai-reach-mcp.service` |

### Cloudflare Tunnel Details

- **Tunnel ID**: `0621c8e9-edab-448f-9434-17807b184c35`
- **Domain**: `aitradepulse.com`
- **Config Location**: `/etc/cloudflared/config.yml` (read by systemd)
- **Generated Config**: `~/.cloudflare-router/tunnel/config.yml` (synced to Cloudflare API)

---

## Port Management

### Reserved Ports (DO NOT USE)

| Port | Service | Status |
|---|---|---|
| 3000 | Other service | ❌ IN USE |
| 8000 | Trading bot | ❌ IN USE |

### Allocated Ports

| Port | Service | Status |
|---|---|---|
| 6969 | cf-router nginx | ✅ RESERVED |
| 8001 | 1ai-reach API | ✅ ALLOCATED |
| 8502 | 1ai-reach Dashboard | ✅ ALLOCATED |

### Port Allocation Rules

1. **Always check before using**: `lsof -i :PORT`
2. **Update systemd service files** when changing ports
3. **Reload systemd** after editing: `systemctl daemon-reload`
4. **Restart service** to apply changes

---

## Subdomain Deployment Workflow

### Step-by-Step Guide

Follow these steps to deploy a new subdomain (e.g., `reach.aitradepulse.com`):

#### 1. Add Mapping to cf-router

Edit the cf-router mappings file:

```bash
vim ~/.cloudflare-router/mappings/cf_1774046746453_e160bb3298781f0de25dddea5fd516a9.yml
```

Add your subdomain entry:

```yaml
- subdomain: reach
  port: 8502
  protocol: http
  description: "1ai-reach Dashboard"
```

**Important**: Ensure your service is already running on the specified port.

#### 2. Regenerate Tunnel Config

Generate the new tunnel configuration:

```bash
cd ~/.cloudflare-router
node src/cli.js generate
```

This creates/updates `~/.cloudflare-router/tunnel/config.yml` with your new subdomain.

**⚠️ Known Issue**: The generator has a YAML indentation bug (lines 59-64 use 3 spaces instead of 2). Check and fix manually if needed.

#### 3. Sync to Cloudflare API

Push the new configuration to Cloudflare:

```bash
cd ~/.cloudflare-router
python3 sync-tunnel-config.py
```

This uploads the config to Cloudflare and increments the version number.

#### 4. Restart Cloudflared

Reload the tunnel daemon to apply changes:

```bash
sudo systemctl restart cloudflared
```

Wait 5-10 seconds for the tunnel to reconnect.

#### 5. Verify Deployment

**Local verification** (via nginx):

```bash
curl -H "Host: reach.aitradepulse.com" http://localhost:6969
```

**External verification**:

```bash
curl https://reach.aitradepulse.com
```

Both should return HTTP 200 with your service's response.

---

## Key Files and Locations

### cf-router Structure

```
~/.cloudflare-router/
├── tunnel/
│   └── config.yml              # Generated tunnel config (synced to Cloudflare)
├── mappings/
│   └── cf_*.yml                # Subdomain mappings (source of truth)
├── apps.yaml                   # App configurations
├── nginx/
│   ├── nginx.conf              # Main nginx config
│   └── sites/
│       └── cf_*_reach.conf     # Generated site configs
├── src/
│   ├── tunnel.js               # Config generator (⚠️ has YAML bug)
│   ├── cli.js                  # CLI commands
│   └── sync-tunnel-config.py  # Cloudflare API sync script
└── README.md                   # cf-router documentation
```

### Cloudflared

```
/etc/cloudflared/
└── config.yml                  # Cloudflared reads this on startup
```

### Systemd Services

```
/etc/systemd/system/
├── cloudflared.service         # Tunnel daemon (root)
└── 1ai-reach-dashboard.service # Dashboard (root)

~/.config/systemd/user/
├── 1ai-reach-api.service       # API (user)
└── 1ai-reach-mcp.service       # MCP webhook (user)
```

### 1ai-reach Project

```
/home/openclaw/projects/1ai-reach/
├── dashboard/                  # Next.js frontend
├── src/oneai_reach/            # Python backend
├── scripts/                    # Pipeline scripts
├── data/                       # Databases and leads
├── proposals/                  # Generated proposals
└── logs/                       # Application logs
```

---

## Service Management

### Check Service Status

```bash
# Cloudflared (tunnel)
sudo systemctl status cloudflared

# Dashboard
sudo systemctl status 1ai-reach-dashboard

# API
systemctl --user status 1ai-reach-api

# MCP webhook
systemctl --user status 1ai-reach-mcp
```

### Restart Services

```bash
# Cloudflared
sudo systemctl restart cloudflared

# Dashboard
sudo systemctl restart 1ai-reach-dashboard

# API
systemctl --user restart 1ai-reach-api

# MCP webhook
systemctl --user restart 1ai-reach-mcp
```

### View Logs

```bash
# Cloudflared
tail -f /tmp/cloudflared-router.log

# Dashboard
journalctl -u 1ai-reach-dashboard -f

# API
journalctl --user -u 1ai-reach-api -f

# MCP webhook
journalctl --user -u 1ai-reach-mcp -f
```

---

## Troubleshooting

### Problem: Subdomain Returns 404

**Symptoms**: External domain returns 404 or "Not Found"

**Diagnosis**:

1. Check cf-router mapping exists:
   ```bash
   cat ~/.cloudflare-router/mappings/cf_*.yml | grep -A3 "subdomain: reach"
   ```

2. Verify tunnel config includes subdomain:
   ```bash
   grep "reach.aitradepulse.com" ~/.cloudflare-router/tunnel/config.yml
   ```

3. Check cloudflared loaded the config:
   ```bash
   tail -f /tmp/cloudflared-router.log | grep "Updated to new configuration"
   ```

4. Verify nginx routing:
   ```bash
   curl -H "Host: reach.aitradepulse.com" http://localhost:6969
   ```

**Solution**:

- If mapping missing: Add to mappings file and regenerate
- If config missing subdomain: Run `node src/cli.js generate` and sync
- If cloudflared not updated: Restart cloudflared
- If nginx fails: Check nginx config and restart cf-router daemon

### Problem: Port Already in Use

**Symptoms**: Service fails to start with "address already in use"

**Diagnosis**:

```bash
lsof -i :PORT
```

**Solution**:

1. **If port is used by another service**: Choose a different port
2. **If port is used by old process**: Kill the process (if safe)
3. **Update service file** with new port
4. **Reload and restart**:
   ```bash
   systemctl --user daemon-reload
   systemctl --user restart SERVICE_NAME
   ```

### Problem: YAML Indentation Error

**Symptoms**: Cloudflared fails to load config, YAML parse errors in logs

**Diagnosis**:

```bash
cat ~/.cloudflare-router/tunnel/config.yml
```

Look for inconsistent indentation (mixing 2-space and 3-space indents).

**Solution**:

1. **Manual fix**: Edit `~/.cloudflare-router/tunnel/config.yml` and fix indentation to 2 spaces
2. **Permanent fix**: Fix the bug in `~/.cloudflare-router/src/tunnel.js` (lines 59-64)
3. **Sync and restart**:
   ```bash
   cd ~/.cloudflare-router
   python3 sync-tunnel-config.py
   sudo systemctl restart cloudflared
   ```

### Problem: Config Not Syncing

**Symptoms**: Changes to mappings don't appear externally

**Root Cause**: cf-router daemon does NOT automatically regenerate/sync when mappings change.

**Solution**: Manual regeneration required:

```bash
cd ~/.cloudflare-router
node src/cli.js generate
python3 sync-tunnel-config.py
sudo systemctl restart cloudflared
```

---

## Known Issues

### 1. YAML Indentation Bug

**Location**: `~/.cloudflare-router/src/tunnel.js` (lines 59-64)

**Issue**: Generator produces inconsistent indentation (3 spaces vs 2 spaces)

**Impact**: Cloudflared may fail to parse config

**Workaround**: Manually fix indentation after generation

**Permanent Fix**: Update tunnel.js to use consistent 2-space indentation

### 2. No Automatic Config Sync

**Issue**: cf-router daemon does NOT automatically regenerate tunnel config when mappings change

**Impact**: Manual regeneration required for every subdomain change

**Workaround**: Run `node src/cli.js generate` and `python3 sync-tunnel-config.py` manually

**Potential Fix**: Add file watcher to cf-router daemon to auto-regenerate on mapping changes

### 3. Cloudflared Restart Required

**Issue**: Cloudflared only loads new config on restart, not automatically

**Impact**: Must restart cloudflared after every config change

**Workaround**: `sudo systemctl restart cloudflared` after syncing

**Note**: This is expected behavior for cloudflared

---

## Security Notes

1. **Never commit tunnel credentials** to git
2. **Tunnel token** is stored in `/etc/cloudflared/config.yml` (root only)
3. **API keys** are in `.env` (gitignored)
4. **Cloudflare API token** is used by `sync-tunnel-config.py` (stored in cf-router config)

---

## Quick Reference

### Deploy New Subdomain (Complete Workflow)

```bash
# 1. Add mapping
vim ~/.cloudflare-router/mappings/cf_*.yml

# 2. Regenerate config
cd ~/.cloudflare-router && node src/cli.js generate

# 3. Sync to Cloudflare
python3 sync-tunnel-config.py

# 4. Restart tunnel
sudo systemctl restart cloudflared

# 5. Verify
curl https://subdomain.aitradepulse.com
```

### Check Deployment Status

```bash
# Services
sudo systemctl status cloudflared
systemctl --user status 1ai-reach-api
sudo systemctl status 1ai-reach-dashboard

# Ports
lsof -i :6969  # cf-router
lsof -i :8001  # API
lsof -i :8502  # Dashboard

# Logs
tail -f /tmp/cloudflared-router.log
journalctl --user -u 1ai-reach-api -f
```

---

## Support

For issues or questions:
- Check logs first: `journalctl -u SERVICE_NAME -f`
- Review this guide's troubleshooting section
- Check cf-router documentation: `~/.cloudflare-router/README.md`
- Verify Cloudflare Tunnel status in Cloudflare dashboard

---

**Last Updated**: 2026-04-22  
**Deployment**: reach.aitradepulse.com (verified working)
