const { defineConfig, devices } = require('@playwright/test');

module.exports = defineConfig({
  testDir: '.',
  testMatch: '*.spec.js',
  fullyParallel: true,
  reporter: 'list',
  use: { ...devices['Desktop Chrome'], viewport: { width: 1000, height: 760 } },
  projects: [{ name: 'chromium', use: { browserName: 'chromium' } }]
});
