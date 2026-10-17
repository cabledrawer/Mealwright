import { mkdtempSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { defineConfig, devices } from '@playwright/test';

// Browser tests run against the real app, started fresh on 127.0.0.1 with an empty
// data folder, in headless Chromium. The web app is built first and served by the
// backend, so the tests see the real files with the real security headers.
const port = Number(process.env.E2E_APP_PORT ?? 18080);
const dataDir = mkdtempSync(join(tmpdir(), 'mealwright-e2e-'));

// The app shell on a phone and on a desktop, the two layouts the spec designs for.
const phone = {
  ...devices['Pixel 7'],
  browserName: 'chromium' as const,
  viewport: { width: 390, height: 844 },
};
const desktop = { browserName: 'chromium' as const, viewport: { width: 1280, height: 900 } };

export default defineConfig({
  testDir: './tests',
  workers: 1,
  retries: 0,
  forbidOnly: true,
  projects: [
    { name: 'chromium', testMatch: 'csp.spec.ts', use: { browserName: 'chromium' } },
    { name: 'phone', testIgnore: 'csp.spec.ts', use: phone },
    { name: 'desktop', testIgnore: 'csp.spec.ts', use: desktop },
  ],
  reporter: 'list',
  use: {
    baseURL: `http://127.0.0.1:${port}`,
  },
  webServer: {
    // Build first: the backend works out the CSP hashes of the built page at start-up.
    command:
      'npm --prefix ../frontend run -s build && uv run --frozen --project ../backend python -m mealwright',
    url: `http://127.0.0.1:${port}/api/v1/version`,
    env: {
      MEALWRIGHT_DATA_DIR: dataDir,
      MEALWRIGHT_HOST: '127.0.0.1',
      MEALWRIGHT_PORT: String(port),
      MEALWRIGHT_FRONTEND_DIR: '../frontend/build',
      // The tests use plain http://127.0.0.1.
      MEALWRIGHT_ALLOW_PLAIN_HTTP: 'true',
    },
    reuseExistingServer: false,
    timeout: 120_000,
  },
});
