# 🚨 QUICK FIX GUIDE - 1ai-reach Critical Issues

**Generated:** 2026-04-20T22:04:06Z
**Status:** API SERVICE DOWN - IMMEDIATE ACTION REQUIRED

---

## ⚡ 5-MINUTE EMERGENCY FIX

Your API service is currently down. Run these commands to restore service:

```bash
cd /home/openclaw/projects/1ai-reach

# Backup the broken file
cp src/oneai_reach/api/v1/legacy.py src/oneai_reach/api/v1/legacy.py.backup

# Fix the import error
cat > /tmp/fix_import.py << 'PYTHON'
import sys
filepath = "src/oneai_reach/api/v1/legacy.py"
with open(filepath, 'r') as f:
    lines = f.readlines()

# Replace line 14
lines[13] = "from voice_config import get_voice_config\nfrom state_manager import update_voice_config\n"

with open(filepath, 'w') as f:
    f.writelines(lines)
print("✓ Fixed import in legacy.py")
PYTHON

python3 /tmp/fix_import.py

# Restart API service
sudo systemctl restart 1ai-reach-api.service

# Wait and check status
sleep 3
sudo systemctl status 1ai-reach-api.service --no-pager

# Test API
curl -s http://localhost:8000/health && echo "✓ API is UP" || echo "✗ API still down"
```

---

## 📋 VERIFICATION CHECKLIST

After running the fix above, verify:

```bash
# 1. Check service status
sudo systemctl status 1ai-reach-api.service
# Should show: Active: active (running)

# 2. Check logs for errors
journalctl -u 1ai-reach-api.service -n 20 --no-pager
# Should NOT show ImportError

# 3. Test API endpoint
curl http://localhost:8000/health
# Should return 200 OK

# 4. Check dashboard can connect
curl http://localhost:8502
# Should return HTML
```

---

## 🔧 DASHBOARD FIX (If needed)

If dashboard has issues after API fix:

```bash
cd /home/openclaw/projects/1ai-reach/dashboard

# Install missing dependencies
npm install

# Restart dashboard service
sudo systemctl restart 1ai-reach-dashboard.service

# Verify
sleep 3
sudo systemctl status 1ai-reach-dashboard.service
```

---

## 📊 WHAT WAS WRONG?

**Problem:** Import error in `src/oneai_reach/api/v1/legacy.py`

**Before (BROKEN):**
```python
from voice_config import get_voice_config, update_voice_config
```

**After (FIXED):**
```python
from voice_config import get_voice_config
from state_manager import update_voice_config
```

**Why:** The function `update_voice_config` exists in `state_manager.py`, not `voice_config.py`.

---

## 🚀 NEXT STEPS (After Emergency Fix)

1. **Read full audit report:**
   ```bash
   cat ~/projects/1ai-reach/AUDIT_REPORT.md
   ```

2. **Review fix proposals:**
   ```bash
   cat ~/projects/1ai-reach/FIX_PROPOSALS.md
   ```

3. **Plan remaining fixes:**
   - 4 bare except clauses (30 min)
   - 76 sys.path manipulations (2 hours)
   - 158 print statements (1 hour)
   - Build artifacts cleanup (15 min)

---

## 📞 TROUBLESHOOTING

### If API still won't start:

```bash
# Check detailed error
journalctl -u 1ai-reach-api.service -n 50 --no-pager | grep -i error

# Check Python can import
cd /home/openclaw/projects/1ai-reach
python3 -c "import sys; sys.path.insert(0, 'src'); from oneai_reach.api.main import app; print('OK')"

# Check file was actually modified
grep -n "from state_manager import update_voice_config" src/oneai_reach/api/v1/legacy.py
```

### If dashboard won't start:

```bash
# Check for missing dependencies
cd dashboard
npm list 2>&1 | grep UNMET

# Check Next.js binary
ls -la node_modules/.bin/next

# Manual start for debugging
npm run dev
```

---

## ✅ SUCCESS CRITERIA

You'll know everything is working when:

- ✅ `systemctl status 1ai-reach-api.service` shows "active (running)"
- ✅ `curl http://localhost:8000/health` returns 200 OK
- ✅ `systemctl status 1ai-reach-dashboard.service` shows "active (running)"
- ✅ Dashboard loads at http://localhost:8502
- ✅ No ImportError in `journalctl -u 1ai-reach-api.service`

---

**Need help?** Check the full reports:
- `AUDIT_REPORT.md` - Complete findings
- `FIX_PROPOSALS.md` - Detailed fix instructions

