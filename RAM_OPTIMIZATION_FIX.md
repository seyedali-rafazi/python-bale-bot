# RAM Memory Optimization Fix Report

## Problem Summary
- **Issue**: RAM exhaustion with 20,000 users
- **Root Cause**: Multiple Chromium processes (280MB each) spawned for each Pinterest search
- **Architecture Problem**: Each search created a NEW browser instance instead of reusing existing ones

## Root Cause Analysis

### Before Fix
```
Pinterest Search Request Flow:
1. User requests search
2. pinterest_queue adds to queue
3. Worker calls search_pinterest_images()
4. Creates new PinterestService()
5. _load_search_page() spawns NEW browser with sync_playwright()
6. Browser processes accumulated faster than cleanup
7. With 4 concurrent workers + queue backlog = memory explosion
```

**Memory Usage Pattern:**
- Each Chromium process: ~280 MB
- 4 concurrent workers = 1.1 GB minimum
- Queue backlog creates additional processes
- No reuse between searches

## Implemented Solutions

### 1. Browser Manager (Singleton Pattern)
**File**: `services/playwright_browser_manager.py` (NEW)
- One browser instance per process (shared across searches)
- Reuses browser contexts/pages instead of creating new browsers
- Automatic cleanup on process exit
- Memory-optimized launch arguments

**Key Optimizations:**
```python
args=[
    "--disable-gpu",  # Save memory
    "--single-process",  # Reduce overhead
    "--disable-web-resources",
    "--disable-extensions",
    "--disable-sync",
    "--disable-translate",
]
```

### 2. Pinterest Service Refactor
**File**: `services/pinterest.py` (MODIFIED)
- Changed `_load_search_page()` to use browser manager
- Removed `with sync_playwright() as p:` pattern
- Reuses existing browser instance per process
- Only creates new contexts, not new browsers

**Before:**
```python
with sync_playwright() as p:
    browser = p.chromium.launch(...)  # NEW browser each time!
    context = browser.new_context(...)
    page = context.new_page()
    # ... search ...
    browser.close()  # Too late, already created!
```

**After:**
```python
browser_manager = get_browser_manager()  # Singleton
context = browser_manager.new_context(user_agent)  # Reuse browser
page = context.new_page()
# ... search ...
context.close()  # Just close context, not browser
```

### 3. Worker Concurrency Reduction
**File**: `services/pinterest_queue.py` (MODIFIED)

**Changes:**
| Setting | Before | After | Reason |
|---------|--------|-------|--------|
| PINTEREST_SEARCH_WORKERS | 4 | 2 | Fewer concurrent processes |
| Queue Max Size | 5000 | 100 | Prevent queue overflow |
| Worker Delay | None | 0.5s | Smoother resource usage |

**Expected Impact:**
- Process overhead: 4 processes → 2 processes
- Browser instances: 4 instances → 2 instances (one per process)
- RAM savings: ~560 MB baseline savings

### 4. New Module: Browser Pool (Future Use)
**File**: `services/browser_pool.py` (NEW)
- Async-compatible browser pool (for future migration)
- Currently not used but available for async refactoring

## Expected Results

### Memory Reduction Estimate
```
Before:
- 4 browser processes × 280 MB = 1,120 MB baseline
- Queue backlog creates spikes
- Total: 1.5-2.5 GB for Pinterest searches

After:
- 2 browser processes × 280 MB = 560 MB baseline
- Reduced queue backlog
- Total: 600-800 MB for Pinterest searches
- Improvement: ~60% reduction
```

### Performance Impact
- **Search Speed**: Minimal impact (context creation is fast)
- **Throughput**: Slightly reduced (2 workers vs 4), but more stable
- **RAM Stability**: MAJOR improvement - predictable memory usage

## Additional Recommendations

### 1. Monitor Memory Usage
```bash
# Add monitoring script
watch -n 5 'ps aux | grep chromium | head -5'
# or
ps aux --sort=-%mem | grep chromium
```

### 2. Further Optimization (If Still Issues)

#### Option A: API-Based Alternative
Use Pinterest API instead of browser automation:
- Would eliminate Chromium entirely
- Requires API key/authentication
- Much faster and lighter

#### Option B: Image URL Extraction
Cache extracted URLs to avoid re-scraping:
- Implement caching layer
- Reduce redundant searches
- Return cached results for duplicate queries

#### Option C: Additional Worker Reduction
If memory still high, reduce to 1 worker:
```python
PINTEREST_SEARCH_WORKERS = 1  # Single worker, still responsive
```

#### Option D: Memory Limits
Use cgroups or Docker to cap process memory:
```bash
# Linux cgroups example
ulimit -v 524288  # Limit process to 512MB
```

### 3. Remove Unused Import
The old `sync_playwright` context manager is still imported but no longer needed:
```python
# In pinterest.py - can be removed if not used elsewhere
from playwright.sync_api import sync_playwright  # OPTIONAL: Remove if only using browser_manager
```

## Testing Checklist

- [ ] Run bot with 50-100 concurrent users
- [ ] Monitor RAM usage for 1 hour
- [ ] Check `ps aux` for number of Chromium processes (should be ≤ 2 per worker)
- [ ] Verify Pinterest searches still work correctly
- [ ] Test with multiple rapid searches from different users
- [ ] Monitor process cleanup on app shutdown

## Files Modified/Created

| File | Change | Impact |
|------|--------|--------|
| `services/playwright_browser_manager.py` | NEW | Core optimization |
| `services/pinterest.py` | MODIFIED | Uses browser manager |
| `services/pinterest_queue.py` | MODIFIED | Reduced workers |
| `services/browser_pool.py` | NEW | Future async support |

## Rollback Plan

If issues occur:
1. Revert `pinterest.py` to use `with sync_playwright() as p:`
2. Increase `PINTEREST_SEARCH_WORKERS` back to 4
3. Increase queue maxsize back to 5000

## Next Steps

1. **Deploy and Monitor**: Watch memory usage for 24 hours
2. **Adjust Workers**: If still memory issues, reduce to 1 worker
3. **Consider Caching**: Implement search result caching for frequent queries
4. **Long-term**: Evaluate Pinterest API as alternative to scraping
