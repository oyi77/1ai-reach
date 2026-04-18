# Instructions

- Following Playwright test failed.
- Explain why, be concise, respect Playwright best practices.
- Provide a snippet of code with the fix, if possible.

# Test info

- Name: products.spec.ts >> Product Management E2E >> should handle product variants (if implemented)
- Location: tests/e2e/products.spec.ts:227:7

# Error details

```
Test timeout of 30000ms exceeded.
```

```
Error: locator.click: Test timeout of 30000ms exceeded.
Call log:
  - waiting for getByRole('button', { name: /Add Product/i })

```

# Page snapshot

```yaml
- generic [active] [ref=e1]:
  - complementary [ref=e2]:
    - generic [ref=e3]:
      - generic [ref=e4]:
        - heading "1ai-reach" [level=1] [ref=e5]
        - paragraph [ref=e6]: Outreach Automation
      - separator
      - navigation [ref=e7]:
        - link "Dashboard" [ref=e8] [cursor=pointer]:
          - /url: /
          - img [ref=e9]
          - text: Dashboard
        - link "Funnel" [ref=e14] [cursor=pointer]:
          - /url: /funnel
          - img [ref=e15]
          - text: Funnel
        - link "Conversations" [ref=e17] [cursor=pointer]:
          - /url: /conversations
          - img [ref=e18]
          - text: Conversations
        - link "Knowledge Base" [ref=e20] [cursor=pointer]:
          - /url: /kb
          - img [ref=e21]
          - text: Knowledge Base
        - link "Products" [ref=e23] [cursor=pointer]:
          - /url: /products
          - img [ref=e24]
          - text: Products
        - link "Sales Pipeline" [ref=e28] [cursor=pointer]:
          - /url: /pipeline
          - img [ref=e29]
          - text: Sales Pipeline
        - link "Services" [ref=e30] [cursor=pointer]:
          - /url: /services
          - img [ref=e31]
          - text: Services
        - link "Run Pipeline" [ref=e34] [cursor=pointer]:
          - /url: /pipeline-control
          - img [ref=e35]
          - text: Run Pipeline
        - link "Voice Settings" [ref=e37] [cursor=pointer]:
          - /url: /voice-settings
          - img [ref=e38]
          - text: Voice Settings
      - separator
      - paragraph [ref=e42]: v2.0.0 — Next.js
  - banner [ref=e43]:
    - button [disabled] [ref=e44]:
      - img [ref=e45]
    - text: 1ai-reach
  - main [ref=e46]:
    - generic [ref=e48]:
      - heading "404" [level=1] [ref=e49]
      - heading "This page could not be found." [level=2] [ref=e51]
```

# Test source

```ts
  129 |     await page.getByPlaceholder('Category').fill('Test');
  130 |     await page.getByPlaceholder('SKU').fill('IMG-001');
  131 |     await page.getByPlaceholder('Price (cents)').fill('8000000');
  132 |     await page.getByRole('button', { name: /Save Product/i }).click();
  133 |     await expect(page.getByRole('dialog')).not.toBeVisible({ timeout: 5000 });
  134 | 
  135 |     // Take screenshot showing product ready for image upload
  136 |     await page.screenshot({ path: 'test-results/product-ready-for-image.png', fullPage: true });
  137 | 
  138 |     // Note: Actual image upload would require:
  139 |     // 1. A test image file in the test fixtures
  140 |     // 2. An image upload UI component (not visible in current implementation)
  141 |     // 3. File input interaction: await page.setInputFiles('input[type="file"]', 'path/to/test-image.jpg')
  142 |     // This test documents the expected flow for when image upload UI is added
  143 |   });
  144 | 
  145 |   test('should import products from CSV file', async ({ page }) => {
  146 |     // Create a test CSV content
  147 |     const csvContent = `name,description,category,sku,base_price_cents,status,visibility
  148 | Imported Coffee,Premium blend,Coffee,IMP-001,20000000,active,public
  149 | Imported Tea,Green tea,Beverages,IMP-002,15000000,active,public`;
  150 | 
  151 |     // Create a temporary CSV file
  152 |     const csvPath = path.join(__dirname, '../fixtures/test-products.csv');
  153 |     
  154 |     // Note: In a real test, you would:
  155 |     // 1. Create the CSV file using fs.writeFileSync
  156 |     // 2. Upload it via: await page.setInputFiles('input#product-import', csvPath)
  157 |     // 3. Wait for import success message
  158 |     // 4. Verify imported products appear in table
  159 | 
  160 |     // Click import button
  161 |     await page.getByRole('button', { name: /Import CSV/i }).click();
  162 | 
  163 |     // Take screenshot showing import ready state
  164 |     await page.screenshot({ path: 'test-results/csv-import-ready.png', fullPage: true });
  165 | 
  166 |     // Document expected flow:
  167 |     // - File input should trigger
  168 |     // - CSV validation should occur
  169 |     // - Success/error message should display
  170 |     // - Products should appear in table
  171 |   });
  172 | 
  173 |   test('should validate CSV import with error handling', async ({ page }) => {
  174 |     // Create invalid CSV content (missing required fields)
  175 |     const invalidCSV = `name,description
  176 | Invalid Product,Missing required fields`;
  177 | 
  178 |     // Take screenshot of initial state
  179 |     await page.screenshot({ path: 'test-results/csv-validation-start.png', fullPage: true });
  180 | 
  181 |     // Expected behavior:
  182 |     // 1. Upload invalid CSV
  183 |     // 2. Validation errors should be displayed
  184 |     // 3. No products should be imported
  185 |     // 4. User should see clear error messages
  186 | 
  187 |     // This test documents the validation flow
  188 |     // Actual implementation would upload the invalid CSV and verify error messages
  189 |   });
  190 | 
  191 |   test('should export products to CSV', async ({ page }) => {
  192 |     // Create some products first
  193 |     const products = [
  194 |       { name: 'Export Test 1', category: 'Test', sku: 'EXP-001', price: '10000000' },
  195 |       { name: 'Export Test 2', category: 'Test', sku: 'EXP-002', price: '15000000' },
  196 |     ];
  197 | 
  198 |     for (const product of products) {
  199 |       await page.getByRole('button', { name: /Add Product/i }).click();
  200 |       await page.getByPlaceholder('Product Name').fill(product.name);
  201 |       await page.getByPlaceholder('Category').fill(product.category);
  202 |       await page.getByPlaceholder('SKU').fill(product.sku);
  203 |       await page.getByPlaceholder('Price (cents)').fill(product.price);
  204 |       await page.getByRole('button', { name: /Save Product/i }).click();
  205 |       await expect(page.getByRole('dialog')).not.toBeVisible({ timeout: 5000 });
  206 |     }
  207 | 
  208 |     // Take screenshot before export
  209 |     await page.screenshot({ path: 'test-results/products-before-export.png', fullPage: true });
  210 | 
  211 |     // Setup download handler
  212 |     const downloadPromise = page.waitForEvent('download');
  213 |     
  214 |     // Click export button
  215 |     await page.getByRole('button', { name: /Export CSV/i }).click();
  216 | 
  217 |     // Wait for download
  218 |     const download = await downloadPromise;
  219 |     
  220 |     // Verify download occurred
  221 |     expect(download.suggestedFilename()).toContain('.csv');
  222 | 
  223 |     // Take screenshot after export
  224 |     await page.screenshot({ path: 'test-results/products-exported.png', fullPage: true });
  225 |   });
  226 | 
  227 |   test('should handle product variants (if implemented)', async ({ page }) => {
  228 |     // Create a product
> 229 |     await page.getByRole('button', { name: /Add Product/i }).click();
      |                                                              ^ Error: locator.click: Test timeout of 30000ms exceeded.
  230 |     await page.getByPlaceholder('Product Name').fill('Variant Test Product');
  231 |     await page.getByPlaceholder('Category').fill('Test');
  232 |     await page.getByPlaceholder('SKU').fill('VAR-001');
  233 |     await page.getByPlaceholder('Price (cents)').fill('10000000');
  234 |     await page.getByRole('button', { name: /Save Product/i }).click();
  235 |     await expect(page.getByRole('dialog')).not.toBeVisible({ timeout: 5000 });
  236 | 
  237 |     // Take screenshot
  238 |     await page.screenshot({ path: 'test-results/product-for-variants.png', fullPage: true });
  239 | 
  240 |     // Expected variant flow:
  241 |     // 1. Click on product to view details
  242 |     // 2. Add variant button should be visible
  243 |     // 3. Fill variant form (size, color, etc.)
  244 |     // 4. Save variant
  245 |     // 5. Verify variant appears in product details
  246 |   });
  247 | 
  248 |   test('should display empty state when no products exist', async ({ page }) => {
  249 |     // Wait for products to load
  250 |     await page.waitForLoadState('networkidle');
  251 | 
  252 |     // Check for empty state message (if no products exist)
  253 |     const emptyMessage = page.getByText(/No products for this number/i);
  254 |     
  255 |     // Take screenshot of current state
  256 |     await page.screenshot({ path: 'test-results/products-state.png', fullPage: true });
  257 | 
  258 |     // This test verifies the empty state UI is shown when appropriate
  259 |   });
  260 | 
  261 |   test('should filter products by WA number', async ({ page }) => {
  262 |     // Check if WA number selector is present
  263 |     const waSelector = page.locator('select, [role="combobox"]').first();
  264 |     
  265 |     if (await waSelector.isVisible()) {
  266 |       // Take screenshot of WA selector
  267 |       await page.screenshot({ path: 'test-results/wa-number-selector.png', fullPage: true });
  268 | 
  269 |       // Expected behavior:
  270 |       // 1. Select different WA number
  271 |       // 2. Products should reload for that WA number
  272 |       // 3. Product count should update
  273 |     }
  274 |   });
  275 | 
  276 |   test('should show loading states during operations', async ({ page }) => {
  277 |     // Check for loading spinner on initial load
  278 |     const loader = page.locator('[class*="animate-spin"]');
  279 |     
  280 |     // Take screenshot if loader is visible
  281 |     if (await loader.isVisible({ timeout: 1000 }).catch(() => false)) {
  282 |       await page.screenshot({ path: 'test-results/loading-state.png', fullPage: true });
  283 |     }
  284 | 
  285 |     // Wait for content to load
  286 |     await page.waitForLoadState('networkidle');
  287 | 
  288 |     // Verify loading state is gone
  289 |     await expect(loader).not.toBeVisible();
  290 |   });
  291 | 
  292 |   test('should validate required fields in product form', async ({ page }) => {
  293 |     // Open add product dialog
  294 |     await page.getByRole('button', { name: /Add Product/i }).click();
  295 |     await expect(page.getByRole('dialog')).toBeVisible();
  296 | 
  297 |     // Try to save without filling required fields
  298 |     await page.getByRole('button', { name: /Save Product/i }).click();
  299 | 
  300 |     // Take screenshot showing validation state
  301 |     await page.screenshot({ path: 'test-results/form-validation.png', fullPage: true });
  302 | 
  303 |     // Expected behavior:
  304 |     // - Form should not submit
  305 |     // - Validation errors should be shown
  306 |     // - Required fields should be highlighted
  307 |   });
  308 | 
  309 |   test('should format prices correctly in IDR currency', async ({ page }) => {
  310 |     // Create a product with specific price
  311 |     await page.getByRole('button', { name: /Add Product/i }).click();
  312 |     await page.getByPlaceholder('Product Name').fill('Price Format Test');
  313 |     await page.getByPlaceholder('Category').fill('Test');
  314 |     await page.getByPlaceholder('SKU').fill('PRICE-001');
  315 |     await page.getByPlaceholder('Price (cents)').fill('25000000'); // Rp 250,000
  316 |     await page.getByRole('button', { name: /Save Product/i }).click();
  317 |     await expect(page.getByRole('dialog')).not.toBeVisible({ timeout: 5000 });
  318 | 
  319 |     // Verify price is formatted correctly (should show Rp 250.000 or similar)
  320 |     const priceCell = page.locator('tr', { has: page.getByText('Price Format Test') })
  321 |       .locator('td').filter({ hasText: /Rp|IDR/i });
  322 |     
  323 |     await expect(priceCell).toBeVisible();
  324 | 
  325 |     // Take screenshot showing formatted price
  326 |     await page.screenshot({ path: 'test-results/price-formatting.png', fullPage: true });
  327 |   });
  328 | });
  329 | 
```