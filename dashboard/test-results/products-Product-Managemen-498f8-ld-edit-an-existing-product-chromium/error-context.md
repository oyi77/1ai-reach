# Instructions

- Following Playwright test failed.
- Explain why, be concise, respect Playwright best practices.
- Provide a snippet of code with the fix, if possible.

# Test info

- Name: products.spec.ts >> Product Management E2E >> should edit an existing product
- Location: tests/e2e/products.spec.ts:64:7

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
  1   | import { test, expect } from '@playwright/test';
  2   | import path from 'path';
  3   | 
  4   | test.describe('Product Management E2E', () => {
  5   |   test.beforeEach(async ({ page }) => {
  6   |     // Navigate to products page
  7   |     await page.goto('/products');
  8   |     await page.waitForLoadState('networkidle');
  9   |   });
  10  | 
  11  |   test('should display products page with header and controls', async ({ page }) => {
  12  |     // Verify page title
  13  |     await expect(page.locator('h1')).toContainText('Products');
  14  | 
  15  |     // Verify main controls are present
  16  |     await expect(page.getByRole('button', { name: /Add Product/i })).toBeVisible();
  17  |     await expect(page.getByRole('button', { name: /Import CSV/i })).toBeVisible();
  18  |     await expect(page.getByRole('button', { name: /Export CSV/i })).toBeVisible();
  19  | 
  20  |     // Take screenshot for evidence
  21  |     await page.screenshot({ path: 'test-results/products-page-loaded.png', fullPage: true });
  22  |   });
  23  | 
  24  |   test('should create a new product with full form flow', async ({ page }) => {
  25  |     // Click Add Product button
  26  |     await page.getByRole('button', { name: /Add Product/i }).click();
  27  | 
  28  |     // Wait for dialog to open
  29  |     await expect(page.getByRole('dialog')).toBeVisible();
  30  |     await expect(page.getByText('Add Product')).toBeVisible();
  31  | 
  32  |     // Fill product form
  33  |     await page.getByPlaceholder('Product Name').fill('Test Coffee Beans');
  34  |     await page.getByPlaceholder('Description').fill('Premium Arabica coffee beans from Java');
  35  |     await page.getByPlaceholder('Category').fill('Coffee');
  36  |     await page.getByPlaceholder('SKU').fill('COFFEE-001');
  37  |     await page.getByPlaceholder('Price (cents)').fill('15000000'); // Rp 150,000
  38  | 
  39  |     // Select status
  40  |     await page.locator('select, [role="combobox"]').filter({ hasText: /active/i }).first().click();
  41  |     await page.getByRole('option', { name: 'Active' }).click();
  42  | 
  43  |     // Select visibility
  44  |     await page.locator('select, [role="combobox"]').filter({ hasText: /public/i }).first().click();
  45  |     await page.getByRole('option', { name: 'Public' }).click();
  46  | 
  47  |     // Take screenshot before save
  48  |     await page.screenshot({ path: 'test-results/product-form-filled.png', fullPage: true });
  49  | 
  50  |     // Save product
  51  |     await page.getByRole('button', { name: /Save Product/i }).click();
  52  | 
  53  |     // Wait for dialog to close and product to appear in table
  54  |     await expect(page.getByRole('dialog')).not.toBeVisible({ timeout: 5000 });
  55  |     
  56  |     // Verify product appears in table
  57  |     await expect(page.getByText('Test Coffee Beans')).toBeVisible();
  58  |     await expect(page.getByText('COFFEE-001')).toBeVisible();
  59  | 
  60  |     // Take screenshot of success
  61  |     await page.screenshot({ path: 'test-results/product-created.png', fullPage: true });
  62  |   });
  63  | 
  64  |   test('should edit an existing product', async ({ page }) => {
  65  |     // First create a product to edit
> 66  |     await page.getByRole('button', { name: /Add Product/i }).click();
      |                                                              ^ Error: locator.click: Test timeout of 30000ms exceeded.
  67  |     await page.getByPlaceholder('Product Name').fill('Edit Test Product');
  68  |     await page.getByPlaceholder('Category').fill('Test');
  69  |     await page.getByPlaceholder('SKU').fill('EDIT-001');
  70  |     await page.getByPlaceholder('Price (cents)').fill('10000000');
  71  |     await page.getByRole('button', { name: /Save Product/i }).click();
  72  |     await expect(page.getByRole('dialog')).not.toBeVisible({ timeout: 5000 });
  73  | 
  74  |     // Find and click edit button for the product
  75  |     const productRow = page.locator('tr', { has: page.getByText('Edit Test Product') });
  76  |     await productRow.getByRole('button').first().click(); // Edit button
  77  | 
  78  |     // Wait for dialog
  79  |     await expect(page.getByRole('dialog')).toBeVisible();
  80  |     await expect(page.getByText('Edit Product')).toBeVisible();
  81  | 
  82  |     // Modify product name
  83  |     await page.getByPlaceholder('Product Name').fill('Updated Test Product');
  84  |     await page.getByPlaceholder('Price (cents)').fill('12000000');
  85  | 
  86  |     // Save changes
  87  |     await page.getByRole('button', { name: /Save Product/i }).click();
  88  |     await expect(page.getByRole('dialog')).not.toBeVisible({ timeout: 5000 });
  89  | 
  90  |     // Verify updated product
  91  |     await expect(page.getByText('Updated Test Product')).toBeVisible();
  92  | 
  93  |     // Take screenshot
  94  |     await page.screenshot({ path: 'test-results/product-edited.png', fullPage: true });
  95  |   });
  96  | 
  97  |   test('should delete a product with confirmation', async ({ page }) => {
  98  |     // Create a product to delete
  99  |     await page.getByRole('button', { name: /Add Product/i }).click();
  100 |     await page.getByPlaceholder('Product Name').fill('Delete Test Product');
  101 |     await page.getByPlaceholder('Category').fill('Test');
  102 |     await page.getByPlaceholder('SKU').fill('DELETE-001');
  103 |     await page.getByPlaceholder('Price (cents)').fill('5000000');
  104 |     await page.getByRole('button', { name: /Save Product/i }).click();
  105 |     await expect(page.getByRole('dialog')).not.toBeVisible({ timeout: 5000 });
  106 | 
  107 |     // Verify product exists
  108 |     await expect(page.getByText('Delete Test Product')).toBeVisible();
  109 | 
  110 |     // Setup dialog handler for confirmation
  111 |     page.on('dialog', dialog => dialog.accept());
  112 | 
  113 |     // Find and click delete button
  114 |     const productRow = page.locator('tr', { has: page.getByText('Delete Test Product') });
  115 |     await productRow.getByRole('button').last().click(); // Delete button (last button)
  116 | 
  117 |     // Wait for product to be removed
  118 |     await expect(page.getByText('Delete Test Product')).not.toBeVisible({ timeout: 5000 });
  119 | 
  120 |     // Take screenshot
  121 |     await page.screenshot({ path: 'test-results/product-deleted.png', fullPage: true });
  122 |   });
  123 | 
  124 |   test('should upload and preview product image', async ({ page }) => {
  125 |     // Note: This test requires a mock image file
  126 |     // Create a product first
  127 |     await page.getByRole('button', { name: /Add Product/i }).click();
  128 |     await page.getByPlaceholder('Product Name').fill('Image Test Product');
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
```