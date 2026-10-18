import { defineConfig, devices } from '@playwright/test';
import { AUTH_FILE, PORTS, local } from './tests/servers.ts';

// Lets the tests see the service worker's own requests (test-only; Playwright hides them
// by default).
process.env.PW_EXPERIMENTAL_SERVICE_WORKER_NETWORK_EVENTS = '1';

// Browser tests run against the real app, in headless Chromium. serve.mjs builds the
// web app and starts three servers on 127.0.0.1 with empty data folders (see
// tests/servers.ts); global-setup.ts creates the admin on the main one.

// mealwright.test → 127.0.0.1, so a test can use a plain http:// address that isn't
// localhost. Nothing is looked up on the network.
const launchOptions = { args: ['--host-resolver-rules=MAP mealwright.test 127.0.0.1'] };

// The app on a phone and on a desktop, the two layouts the spec designs for.
const phone = {
  ...devices['Pixel 7'],
  browserName: 'chromium' as const,
  viewport: { width: 390, height: 844 },
  launchOptions,
};
const desktop = {
  browserName: 'chromium' as const,
  viewport: { width: 1280, height: 900 },
  launchOptions,
};

export default defineConfig({
  testDir: './tests',
  workers: 1,
  retries: 0,
  forbidOnly: true,
  globalSetup: './global-setup.ts',
  projects: [
    { name: 'chromium', testMatch: 'csp.spec.ts', use: { browserName: 'chromium' } },
    { name: 'sign-in', testMatch: 'sign-in.spec.ts', use: desktop },
    // The component gallery is development-only: the built app has none of it (0.4).
    { name: 'gallery', testMatch: 'gallery.spec.ts', use: desktop },
    { name: 'phone', testMatch: 'shell.spec.ts', use: { ...phone, storageState: AUTH_FILE } },
    { name: 'desktop', testMatch: 'shell.spec.ts', use: { ...desktop, storageState: AUTH_FILE } },
    // Ingredients, Pantry and Undo (0.2).
    { name: 'phone 0.2', testMatch: /(pantry|ingredients|undo).*\.spec\.ts/, use: { ...phone, storageState: AUTH_FILE } },
    { name: 'desktop 0.2', testMatch: /(pantry|ingredients|undo).*\.spec\.ts/, use: { ...desktop, storageState: AUTH_FILE } },
    // Shopping and the "How do you count it?" question (0.3).
    { name: 'phone 0.3', testMatch: /shopping.*\.spec\.ts/, use: { ...phone, storageState: AUTH_FILE } },
    { name: 'desktop 0.3', testMatch: /shopping.*\.spec\.ts/, use: { ...desktop, storageState: AUTH_FILE } },
    // Live updates, the connection bar and the installable app (0.3, PR 5).
    { name: 'phone 0.3 live', testMatch: /(live|installable)\.spec\.ts/, use: { ...phone, storageState: AUTH_FILE } },
    { name: 'desktop 0.3 live', testMatch: /(live|installable)\.spec\.ts/, use: { ...desktop, storageState: AUTH_FILE } },
    // The offline queue end to end (0.3, PR 6). No saved session: each test signs in its own,
    // because signing out must not end the one the other tests share.
    { name: 'phone 0.3 offline', testMatch: 'offline.spec.ts', use: phone },
    { name: 'desktop 0.3 offline', testMatch: 'offline.spec.ts', use: desktop },
    // Accessibility (tests/a11y.ts): axe in light and dark; 44 px targets on phone.
    { name: 'phone a11y', testMatch: 'a11y.spec.ts', use: { ...phone, storageState: AUTH_FILE } },
    { name: 'desktop a11y', testMatch: 'a11y.spec.ts', use: { ...desktop, storageState: AUTH_FILE } },
  ],
  reporter: 'list',
  use: {
    baseURL: local(PORTS.main),
    // Dates look as they do on cabledrawer's phone (dd/mm/yyyy), not mm/dd/yyyy.
    locale: 'en-GB',
    timezoneId: 'Europe/London',
  },
  webServer: {
    command: 'node serve.mjs',
    url: `${local(PORTS.main)}/api/v1/version`,
    reuseExistingServer: false,
    timeout: 180_000,
  },
});
