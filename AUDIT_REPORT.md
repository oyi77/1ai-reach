# 1ai-reach Codebase Audit Report
**Date:** 2026-04-21
**Status:** CRITICAL ISSUES FOUND - API SERVICE DOWN

---

## 🔴 CRITICAL ISSUES (Service Breaking)

### 1. **Import Error - API Service Failing** ⚠️ SEVERITY: CRITICAL
**Location:** `src/oneai_reach/api/v1/legacy.py:14`
**Issue:** 
```python
from voice_config import get_voice_config, update_voice_config
```
- `update_voice_config` does NOT exist in `scripts/voice_config.py`
- Function actually exists in `scripts/state_manager.py:581`
- Causes API service to crash on startup (ImportError)

**Impact:** 
- 1ai-reach-api.service is in crash loop (auto-restart)
- API completely unavailable
- Dashboard cannot communicate with backend

**Fix:**
```python
# Option 1: Import from correct module
from state_manager import update_voice_config
from voice_config import get_voice_config

# Option 2: Add wrapper in voice_config.py
def update_voice_config(*args, **kwargs):
    from state_manager import update_voice_config as _update
    return _update(*args, **kwargs)
```

---

### 2. **Dashboard Dependencies Missing** ⚠️ SEVERITY: HIGH
**Location:** `dashboard/`
**Issue:** 10+ UNMET npm dependencies
```
UNMET DEPENDENCY @base-ui/react@^1.4.0
UNMET DEPENDENCY @playwright/test@^1.59.1
UNMET DEPENDENCY @tailwindcss/postcss@^4
UNMET DEPENDENCY @types/node@^20
UNMET DEPENDENCY @types/react-dom@^19
UNMET DEPENDENCY @types/react@^19
UNMET DEPENDENCY class-variance-authority@^0.7.1
UNMET DEPENDENCY clsx@^2.1.1
UNMET DEPENDENCY eslint-config-next@16.2.3
UNMET DEPENDENCY eslint@^9
```

**Impact:**
- `npm run build` fails (next: not found)
- Dashboard may have runtime errors
- TypeScript types missing

**Fix:**
```bash
cd dashboard
npm install
```

---

### 3. **Old Path References in Generated Files** ⚠️ SEVERITY: MEDIUM
**Location:** `docs/e2e-reports/dashboard/.next/types/`
**Issue:** 2 files contain old workspace paths:
```
/home/openclaw/.openclaw/workspace/1ai-engage/dashboard/
```

**Impact:**
- Stale build artifacts
- Potential confusion during debugging
- Type checking may reference wrong paths

**Fix:**
```bash
cd dashboard
rm -rf .next
npm run build
```

---

## 🟡 HIGH PRIORITY ISSUES

### 4. **Bare Except Clauses (Error Swallowing)** ⚠️ SEVERITY: HIGH
**Locations:**
- `src/oneai_reach/application/voice/voice_pipeline_service.py:215`
- `src/oneai_reach/application/voice/tts_service.py:170`
- `src/oneai_reach/application/voice/audio_service.py:176`
- `src/oneai_reach/application/voice/audio_service.py:301`

**Issue:**
```python
except:
    pass  # Silently swallows ALL exceptions
```

**Impact:**
- Hides bugs and errors
- Makes debugging impossible
- Can mask critical failures

**Fix:**
```python
# voice_pipeline_service.py:215
except Exception as e:
    logger.warning(f"Failed to stop typing indicator: {e}")
    pass

# tts_service.py:170
except ImportError:
    # Fallback if nltk not available
    sentences = [s.strip() for s in text.split(".") if s.strip()]

# audio_service.py:176
except (ValueError, UnicodeDecodeError):
    sample_rate = 16000  # Default fallback
```

---

### 5. **Excessive sys.path Manipulation** ⚠️ SEVERITY: MEDIUM
**Issue:** 76 instances of `sys.path.insert()` across 68 files

**Locations:**
- All scripts in `scripts/` directory
- Test files
- `webhook_server.py`
- API legacy router

**Impact:**
- Fragile import system
- Hard to maintain
- Breaks when paths change
- Makes packaging difficult

**Fix:**
- Use proper Python package structure
- Install package in editable mode: `pip install -e .`
- Remove all `sys.path.insert()` calls
- Use relative imports within package

---

### 6. **Debug Print Statements in Production** ⚠️ SEVERITY: MEDIUM
**Issue:** 158 `print()` statements across 28 files

**Key locations:**
- `webhook_server.py` - 4 print statements
- `mcp_server.py` - 5 print statements
- `scripts/leads.py` - funnel summary prints
- `scripts/brain_client.py` - debug prints

**Impact:**
- Clutters logs
- No log levels
- Can't disable debug output
- Performance overhead

**Fix:**
```python
# Replace all print() with proper logging
import logging
logger = logging.getLogger(__name__)

# Instead of:
print(f"[WEBHOOK] Event: {event}")

# Use:
logger.info(f"Event: {event}", extra={"event": event, "session": session})
```

---

## 🟢 MEDIUM PRIORITY ISSUES

### 7. **Package Name Mismatch** ⚠️ SEVERITY: LOW
**Location:** `pyproject.toml:6`
**Issue:**
```toml
name = "oneai-engage"  # Should be "oneai-reach"
```

**Impact:**
- Confusing package name
- Doesn't match project name
- May cause pip install issues

**Fix:**
```toml
name = "oneai-reach"
```

---

### 8. **Large Complex Files** ⚠️ SEVERITY: LOW
**Issue:** Several files exceed recommended complexity:
- `src/oneai_reach/domain/exceptions.py` - 734 lines
- `src/oneai_reach/domain/repositories/product_repository.py` - 389 lines
- `src/oneai_reach/domain/models/product.py` - 330 lines

**Impact:**
- Hard to maintain
- Difficult to test
- Increased cognitive load

**Fix:**
- Split exceptions.py into separate files per exception type
- Extract repository methods into smaller focused classes
- Consider breaking down large models

---

### 9. **Build Artifacts in Repository** ⚠️ SEVERITY: LOW
**Issue:** 898 `__pycache__`, `.pyc`, `node_modules` entries found

**Impact:**
- Bloats repository
- Slows git operations
- Can cause merge conflicts

**Fix:**
```bash
# Clean up
find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null
find . -type f -name "*.pyc" -delete

# Ensure .gitignore is comprehensive
cat >> .gitignore << 'GITIGNORE'
__pycache__/
*.py[cod]
*$py.class
.pytest_cache/
node_modules/
.next/
.venv/
*.egg-info/
dist/
build/
GITIGNORE
```

---

## ✅ SECURITY AUDIT (PASSED)

### No Critical Security Issues Found ✓
- ✅ No hardcoded API keys in code (all use env vars)
- ✅ No `eval()` or `exec()` usage
- ✅ No SQL injection vectors (using ORMs/parameterized queries)
- ✅ No command injection (subprocess calls are safe)
- ✅ API keys properly loaded from environment

**Note:** `.env.example` contains a sample WAHA_API_KEY, but this is acceptable for documentation.

---

## 📋 IMMEDIATE ACTION PLAN

### Priority 1 (DO NOW - Service Down)
1. **Fix import error in legacy.py**
   ```bash
   # Edit src/oneai_reach/api/v1/legacy.py line 14
   sed -i 's/from voice_config import get_voice_config, update_voice_config/from voice_config import get_voice_config\nfrom state_manager import update_voice_config/' src/oneai_reach/api/v1/legacy.py
   
   # Restart service
   sudo systemctl restart 1ai-reach-api.service
   ```

2. **Install dashboard dependencies**
   ```bash
   cd dashboard
   npm install
   npm run build
   ```

### Priority 2 (This Week)
3. Fix all bare `except:` clauses with specific exceptions
4. Replace `print()` with proper logging
5. Remove sys.path manipulation, use proper package install

### Priority 3 (This Month)
6. Clean up build artifacts
7. Fix package name in pyproject.toml
8. Refactor large complex files
9. Rebuild dashboard to fix stale paths

---

## 📊 SUMMARY

| Category | Count | Severity |
|----------|-------|----------|
| Critical (Service Breaking) | 1 | 🔴 |
| High Priority | 5 | 🟡 |
| Medium Priority | 3 | 🟢 |
| Security Issues | 0 | ✅ |

**Overall Status:** NEEDS IMMEDIATE ATTENTION
**Estimated Fix Time:** 2-4 hours for critical issues

