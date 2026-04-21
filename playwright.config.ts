import { defineConfig, devices } from '@playwright/test';

export default defineConfig({
  testDir: '.sisyphus/evidence',
  fullyParallel: false,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 2 : 0,
  workers: 1,
  reporter: 'html',
  use: {
    baseURL: 'http://localhost:3456',
    trace: 'on-first-retry',
    screenshot: 'only-on-failure',
  },
  projects: [
    {
      name: 'chromium',
      use: { ...devices['Desktop Chrome'] },
    },
  ],
  webServer: {
    command: 'cd dashboard && npm run dev',
    url: 'http://localhost:3456',
    reuseExistingServer: true,
    timeout: 120000,
  },
});
