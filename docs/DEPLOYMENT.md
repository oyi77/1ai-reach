# Deployment Guide

## Production Deployment Status

**Last Updated**: 2026-04-19

### Current Production Issue

The production API at `https://reach.aitradepulse.com` is returning 500 errors for `/api/v1/admin/status` and `/api/v1/agents/funnel` endpoints.

**Root Cause**: Production server is running old code and needs to be updated with latest changes.

**Resolution Required**: Manual deployment to production server.

### Local Environment Status ✅

- **API Service**: Running on `localhost:8000` (systemd service: `1ai-reach-api`)
- **Dashboard**: Running on `localhost:8502`
- **Database**: SQLite at `data/1ai_reach.db` with all migrations applied
- **Product Tables**: Created and functional
- **Tests**: All 23 integration tests passing (13 product API + 10 CS product lookup)

### Latest Changes Pushed to GitHub

**Commit**: `0da978e` - "chore: remove large node_modules from e2e reports"

**Previous Commit**: `5ae045c` - "feat: complete product management feature implementation"

**Total Commits Ahead**: 67 commits pushed to `origin/master`

### Production Deployment Steps

To deploy the latest code to production:

1. **SSH to Production Server**:
   ```bash
   ssh <production-server>
   ```

2. **Navigate to Project Directory**:
   ```bash
   cd /path/to/1ai-reach
   ```

3. **Pull Latest Code**:
   ```bash
   git pull origin master
   ```

4. **Run Database Migrations**:
   ```bash
   sqlite3 data/1ai_reach.db < src/oneai_reach/infrastructure/database/migrations/001_create_products_tables.sql
   ```

5. **Restart API Service**:
   ```bash
   sudo systemctl restart 1ai-reach-api
   ```

6. **Verify Deployment**:
   ```bash
   curl https://reach.aitradepulse.com/api/v1/admin/status
   curl https://reach.aitradepulse.com/api/v1/agents/funnel
   ```

### Production Environment Details

- **Domain**: `reach.aitradepulse.com`
- **DNS**: Cloudflare proxy (104.21.19.125, 172.67.186.43)
- **API Port**: 8000 (behind Cloudflare)
- **Dashboard Port**: 8502
- **WAHA Service**: `waha.aitradepulse.com` (requires API key)

### Database Schema Status

**Local Database** (`data/1ai_reach.db`):
- ✅ Products tables created
- ✅ Product variants table
- ✅ Inventory table
- ✅ Product overrides table
- ✅ Product images table
- ✅ Variant options table
- ✅ All indexes created

**Production Database**: Needs migration (see step 4 above)

### Test Data Created

3 sample products created for testing:
1. **Kopi Arabica Premium** - IDR 85,000 (Beverages)
2. **Teh Hijau Organik** - IDR 55,000 (Beverages)
3. **Cokelat Batangan Premium** - IDR 120,000 (Snacks)

### WAHA Configuration

**Local**: `http://127.0.0.1:3010` (API Key: `199c96bcb87e45a39f6cde9e5677ed09`)
**Production**: `https://waha.aitradepulse.com` (API Key: `0673158ede14970b922f7e62075bd0f211490ca335111a9e`)

**Current Sessions**: 0 (no WhatsApp sessions active)

### Known Issues

1. **Production API 500 Errors**: Requires manual deployment (see steps above)
2. **Funnel Stats All Zero**: Expected - no leads in database yet
3. **WAHA Sessions**: No active WhatsApp sessions (user mentioned "there should be 4 connected whatsapp")

### Next Steps

1. Deploy latest code to production server
2. Restart production API service
3. Verify production endpoints return 200
4. Set up WhatsApp sessions in WAHA (4 sessions as per user requirement)
5. Run outreach pipeline to generate leads for funnel stats

### Verification Checklist

After deployment, verify:
- [ ] `https://reach.aitradepulse.com/api/v1/admin/status` returns 200
- [ ] `https://reach.aitradepulse.com/api/v1/agents/funnel` returns 200
- [ ] `https://reach.aitradepulse.com/api/v1/products?wa_number_id=default` returns products
- [ ] Dashboard loads at `https://reach.aitradepulse.com`
- [ ] Product management UI works correctly
- [ ] WAHA has 4 active WhatsApp sessions
