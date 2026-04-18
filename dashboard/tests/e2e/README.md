# E2E Tests for Product Management

## Prerequisites

1. **Start the API backend** (port 8000):
   ```bash
   cd /path/to/1ai-reach
   python -m uvicorn oneai_reach.api.main:app --host 0.0.0.0 --port 8000
   ```

2. **Start the dashboard** (port 8502):
   ```bash
   cd dashboard
   npm run dev -- -p 8502
   ```

3. **Verify both are running**:
   ```bash
   curl http://localhost:8000/health
   curl http://localhost:8502/products
   ```

## Running Tests

```bash
cd dashboard
npx playwright test tests/e2e/products.spec.ts
```

## Test Coverage

The E2E tests cover:
- ✅ Product page loads with controls
- ✅ Product creation flow (form fill → save → verify)
- ✅ Product editing (open → modify → save)
- ✅ Product deletion with confirmation
- ✅ Image upload flow (documented)
- ✅ CSV import flow (documented)
- ✅ CSV export with download verification
- ✅ Empty state display
- ✅ WA number filtering
- ✅ Loading states
- ✅ Form validation
- ✅ Price formatting (IDR currency)

## Screenshots

Test screenshots are saved to `test-results/` for evidence of test execution.
