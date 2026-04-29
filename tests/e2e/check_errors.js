const { chromium } = require('playwright');

const PAGES = [
  '/', '/funnel', '/pipeline', '/contacts', '/conversations',
  '/proposals', '/services', '/analytics', '/channels', '/settings',
  '/auto-learn', '/broadcasts', '/outreach-tracker', '/personas'
];

(async () => {
  const browser = await chromium.launch({ headless: true });
  let totalErrors = 0;

  for (const path of PAGES) {
    const page = await browser.newPage();
    const errors = [];
    page.on('console', msg => { if (msg.type() === 'error') errors.push(msg.text()); });
    page.on('pageerror', err => errors.push(err.message));
    
    await page.goto(`https://reach.aitradepulse.com${path}`, { waitUntil: 'networkidle', timeout: 15000 }).catch(() => {});
    await page.waitForTimeout(2000);

    if (errors.length > 0) {
      console.log(`❌ ${path}: ${errors.length} error(s)`);
      errors.forEach(e => console.log(`   ${e.substring(0, 120)}`));
    } else {
      console.log(`✅ ${path}: 0 errors`);
    }
    totalErrors += errors.length;
    await page.close();
  }

  console.log(`\nTotal errors: ${totalErrors}`);
  await browser.close();
  process.exit(totalErrors > 0 ? 1 : 0);
})();
