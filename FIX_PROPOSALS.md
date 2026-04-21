# 1ai-reach Fix Proposals

## CRITICAL FIX #1: Import Error (API Service Down)

### Problem
`src/oneai_reach/api/v1/legacy.py` imports `update_voice_config` from wrong module.

### Solution (Recommended: Option 1)
**File:** `src/oneai_reach/api/v1/legacy.py`

**Current (line 14):**
```python
from voice_config import get_voice_config, update_voice_config
```

**Fixed:**
```python
from voice_config import get_voice_config
from state_manager import update_voice_config
```

### Apply Fix:
```bash
cd /home/openclaw/projects/1ai-reach

# Backup first
cp src/oneai_reach/api/v1/legacy.py src/oneai_reach/api/v1/legacy.py.backup

# Apply fix
sed -i '14s/.*/from voice_config import get_voice_config\nfrom state_manager import update_voice_config/' src/oneai_reach/api/v1/legacy.py

# Restart service
sudo systemctl restart 1ai-reach-api.service

# Verify
sleep 3
sudo systemctl status 1ai-reach-api.service
```

---

## CRITICAL FIX #2: Dashboard Dependencies

### Problem
Dashboard has unmet dependencies, `next` binary missing.

### Solution
```bash
cd /home/openclaw/projects/1ai-reach/dashboard

# Install all dependencies
npm install

# Verify build works
npm run build

# Restart dashboard service
sudo systemctl restart 1ai-reach-dashboard.service
```

---

## HIGH PRIORITY FIX #1: Bare Except Clauses

### Problem
4 bare `except:` clauses swallow all errors.

### Solution

**File 1:** `src/oneai_reach/application/voice/voice_pipeline_service.py:215`
```python
# Before:
            except:
                pass

# After:
            except Exception as e:
                logger.warning(f"Failed to stop typing indicator: {e}")
```

**File 2:** `src/oneai_reach/application/voice/tts_service.py:170`
```python
# Before:
        except:
            sentences = [s.strip() for s in text.split(".") if s.strip()]

# After:
        except ImportError:
            # Fallback if nltk not available
            sentences = [s.strip() for s in text.split(".") if s.strip()]
```

**File 3:** `src/oneai_reach/application/voice/audio_service.py:176`
```python
# Before:
            except:
                sample_rate = 16000

# After:
            except (ValueError, UnicodeDecodeError):
                sample_rate = 16000  # Default fallback
```

**File 4:** `src/oneai_reach/application/voice/audio_service.py:301`
```python
# Before:
            except:
                # fallback

# After:
            except Exception as e:
                logger.warning(f"Audio conversion fallback: {e}")
                # fallback
```

---

## HIGH PRIORITY FIX #2: Remove sys.path Manipulation

### Problem
76 instances of `sys.path.insert()` make imports fragile.

### Solution
Install package in editable mode and remove all sys.path hacks.

```bash
cd /home/openclaw/projects/1ai-reach

# Install package in editable mode
pip install -e .

# Now all scripts can import without sys.path manipulation
# Example: scripts/orchestrator.py can remove lines 21-22
```

**Then update each script to remove:**
```python
# DELETE THESE LINES:
_src = Path(__file__).parent.parent / "src"
sys.path.insert(0, str(_src))
```

---

## HIGH PRIORITY FIX #3: Replace print() with logging

### Problem
158 print() statements in production code.

### Solution Template
```python
# At top of file:
import logging
logger = logging.getLogger(__name__)

# Replace:
print(f"[WEBHOOK] Event: {event}")

# With:
logger.info("Webhook event received", extra={"event": event, "session": session})

# Replace:
print(f"Error: {e}")

# With:
logger.error(f"Operation failed: {e}", exc_info=True)
```

**Priority files to fix:**
1. `webhook_server.py` (4 prints)
2. `mcp_server.py` (5 prints)
3. `scripts/leads.py` (funnel summary)
4. `scripts/brain_client.py` (debug output)

---

## MEDIUM PRIORITY FIX #1: Package Name

### Problem
`pyproject.toml` has wrong package name.

### Solution
```bash
cd /home/openclaw/projects/1ai-reach

# Fix package name
sed -i 's/name = "oneai-engage"/name = "oneai-reach"/' pyproject.toml

# Reinstall
pip install -e .
```

---

## MEDIUM PRIORITY FIX #2: Clean Build Artifacts

### Problem
898 build artifacts tracked/present.

### Solution
```bash
cd /home/openclaw/projects/1ai-reach

# Clean Python artifacts
find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null
find . -type f -name "*.pyc" -delete
find . -type d -name "*.egg-info" -exec rm -rf {} + 2>/dev/null

# Clean dashboard artifacts
cd dashboard
rm -rf .next
npm run build

# Update .gitignore
cat >> .gitignore << 'GITIGNORE'
# Python
__pycache__/
*.py[cod]
*$py.class
.pytest_cache/
*.egg-info/
dist/
build/
.venv/
venv/

# Node
node_modules/
.next/
.turbo/
npm-debug.log*

# IDE
.vscode/
.idea/
*.swp
*.swo

# OS
.DS_Store
Thumbs.db
GITIGNORE
```

---

## MEDIUM PRIORITY FIX #3: Stale Path References

### Problem
Generated files reference old workspace paths.

### Solution
```bash
cd /home/openclaw/projects/1ai-reach

# Remove stale generated files
rm -rf docs/e2e-reports/dashboard/.next

# Rebuild dashboard (will regenerate with correct paths)
cd dashboard
npm run build
```

---

## EXECUTION ORDER (Recommended)

### Phase 1: Critical (NOW - 15 minutes)
```bash
# 1. Fix import error
cd /home/openclaw/projects/1ai-reach
cp src/oneai_reach/api/v1/legacy.py src/oneai_reach/api/v1/legacy.py.backup
sed -i '14s/from voice_config import get_voice_config, update_voice_config/from voice_config import get_voice_config\nfrom state_manager import update_voice_config/' src/oneai_reach/api/v1/legacy.py
sudo systemctl restart 1ai-reach-api.service

# 2. Fix dashboard dependencies
cd dashboard
npm install
sudo systemctl restart 1ai-reach-dashboard.service

# 3. Verify services
sudo systemctl status 1ai-reach-api.service
sudo systemctl status 1ai-reach-dashboard.service
```

### Phase 2: High Priority (This Week - 2 hours)
1. Fix bare except clauses (4 files)
2. Install package in editable mode
3. Remove sys.path manipulation from key scripts
4. Replace print() with logging in webhook/mcp servers

### Phase 3: Medium Priority (This Month - 1 hour)
1. Fix package name in pyproject.toml
2. Clean build artifacts
3. Update .gitignore
4. Rebuild dashboard to fix stale paths

---

## VERIFICATION CHECKLIST

After Phase 1:
- [ ] `sudo systemctl status 1ai-reach-api.service` shows "active (running)"
- [ ] `curl http://localhost:8000/health` returns 200 OK
- [ ] Dashboard loads at http://localhost:8502
- [ ] No import errors in journalctl logs

After Phase 2:
- [ ] No bare `except:` clauses in voice modules
- [ ] `pip show oneai-reach` shows package installed
- [ ] Scripts run without sys.path manipulation
- [ ] Logs use proper logging instead of print()

After Phase 3:
- [ ] Package name is "oneai-reach" in pyproject.toml
- [ ] No __pycache__ or .pyc files in git status
- [ ] Dashboard .next/ has correct paths
- [ ] .gitignore comprehensive

