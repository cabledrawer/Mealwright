import { mkdtempSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { defineConfig } from '@playwright/test';

// Browser tests run against the real app, started fresh on 127.0.0.1 with an empty
// data folder, in headless Chromium.
const port = Number(process.env.E2E_APP_PORT ?? 18080);
const dataDir = mkdtempSync(join(tmpdir(), 'mealwright-e2e-'));

export default defineConfig({
  testDir: './tests',
  workers: 1,
  retries: 0,
  forbidOnly: true,
  projects: [{ name: 'chromium', use: { browserName: 'chromium' } }],
  reporter: 'list',
  use: {
    baseURL: `http://127.0.0.1:${port}`,
  },
  webServer: {
    command: 'uv run --frozen --project ../backend python -m mealwright',
    url: `http://127.0.0.1:${port}/api/v1/version`,
    env: {
      MEALWRIGHT_DATA_DIR: dataDir,
      MEALWRIGHT_HOST: '127.0.0.1',
      MEALWRIGHT_PORT: String(port),
    },
    reuseExistingServer: false,
    timeout: 60_000,
  },
});
