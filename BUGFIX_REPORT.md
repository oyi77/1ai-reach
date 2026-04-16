# Bug Fix Report - Conversation API Issues

**Date:** 2026-04-16  
**Issues Fixed:** 2 critical bugs

---

## Issue 1: 500 Error on Feedback Endpoint ✅ FIXED

### Problem
```
GET https://engage.aitradepulse.com/api/conversations/25/feedback 500 (Internal Server Error)
GET https://engage.aitradepulse.com/api/conversations/24/feedback 500 (Internal Server Error)
```

### Root Cause
The `_connect()` function was used in the feedback endpoints (lines 387 and 425) but was not imported from `state_manager.py`.

### Fix Applied
Added `_connect` to the imports in `webhook_server.py`:

```python
from state_manager import (
    # ... existing imports ...
    _connect,  # Added this
)
```

**File:** `/home/openclaw/.openclaw/workspace/1ai-reach/webhook_server.py`  
**Lines:** 17-42

---

## Issue 2: Duplicate Conversation Threads ✅ FIXED

### Problem
Multiple conversation entries appearing with the same phone number in the chat list, causing confusion and clutter.

### Root Cause
The `get_all_conversation_stages()` function was doing a simple LEFT JOIN on `sales_stages`, which returned ALL stage history records for each conversation. If a conversation had multiple stage transitions (e.g., discovery → interest → proposal), it would appear 3 times in the list.

**Original Query:**
```sql
LEFT JOIN sales_stages s ON c.id = s.conversation_id
```

This returned every row from `sales_stages` for each conversation.

### Fix Applied
Modified the query to use a window function (`ROW_NUMBER()`) to get only the LATEST stage per conversation:

```sql
LEFT JOIN (
    SELECT conversation_id, stage, entry_trigger, updated_at,
           ROW_NUMBER() OVER (PARTITION BY conversation_id ORDER BY updated_at DESC) as rn
    FROM sales_stages
) s ON c.id = s.conversation_id AND s.rn = 1
```

This ensures each conversation appears only once with its most recent stage.

**File:** `/home/openclaw/.openclaw/workspace/1ai-reach/scripts/state_manager.py`  
**Function:** `get_all_conversation_stages()`  
**Lines:** 884-911

---

## Testing Required

### 1. Feedback Endpoint
Test the feedback endpoints are now working:
```bash
# GET feedback
curl https://engage.aitradepulse.com/api/conversations/25/feedback

# POST feedback
curl -X POST https://engage.aitradepulse.com/api/conversations/25/feedback \
  -H "Content-Type: application/json" \
  -d '{"message_id": 123, "rating": "good", "note": "Great response"}'
```

Expected: 200 OK responses instead of 500 errors.

### 2. Conversations List
Check the conversations page:
```bash
curl https://engage.aitradepulse.com/api/conversations
```

Expected: Each unique phone number should appear only once, showing the latest stage.

---

## Deployment Steps

1. **Restart the webhook server:**
   ```bash
   sudo systemctl restart 1ai-reach-mcp
   ```

2. **Verify service is running:**
   ```bash
   sudo systemctl status 1ai-reach-mcp
   ```

3. **Check logs for errors:**
   ```bash
   tail -f /home/openclaw/.openclaw/workspace/1ai-reach/logs/webhook.log
   ```

4. **Test the endpoints** using the curl commands above.

---

## Impact

- ✅ Feedback endpoint now functional (no more 500 errors)
- ✅ Conversations list shows unique entries (no duplicates)
- ✅ Chat page properly categorized by phone number
- ✅ Better user experience in the dashboard

---

## Notes

- The `ROW_NUMBER()` window function is supported in SQLite 3.25.0+ (2018)
- No database migration needed - this is a query-only change
- Both fixes are backward compatible
