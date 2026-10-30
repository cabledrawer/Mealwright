import { defineConfig, devices, type Project } from '@playwright/test';
import { FIXED_MOMENT } from './tests/clock.ts';
import { AUTH_FILE, PORTS, local } from './tests/servers.ts';

// Every test runs on one fixed date and time (tests/clock.ts). Worked out once, here in the
// main process, so the servers (serve.mjs) and every worker get the same shift.
process.env.E2E_CLOCK_SHIFT_MS ??= String(FIXED_MOMENT - Date.now());

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

// Safari's engine, on a desktop-sized window (the phone layout is covered on Chromium).
const webkit = {
  browserName: 'webkit' as const,
  viewport: { width: 1280, height: 900 },
  launchOptions: { args: [] as string[] },
};

// E2E_PROJECTS picks one half of the projects (./check runs the two halves side by side, each
// with its own servers): "phone" is every phone and WebKit project, "desktop" is all the rest.
// Unset or empty, every project runs.
const half = process.env.E2E_PROJECTS || undefined;
if (half !== undefined && half !== 'phone' && half !== 'desktop') {
  throw new Error(`E2E_PROJECTS must be "phone" or "desktop", not "${half}".`);
}
const inPhoneHalf = (name: string) =>
  name.startsWith('phone') || name.startsWith('webkit') || name === 'screens phone-light' || name === 'slow phone';
const pick = (projects: Project[]) =>
  half === undefined ? projects : projects.filter((p) => inPhoneHalf(p.name ?? '') === (half === 'phone'));

export default defineConfig({
  testDir: './tests',
  // Saved screenshots: animations off, no blinking caret, and no pixels allowed to differ.
  expect: { toHaveScreenshot: { animations: 'disabled', caret: 'hide', maxDiffPixels: 0, threshold: 0 } },
  workers: 1,
  // One more try for a test that fails (cabledrawer 30 Oct): one that then passes doesn't fail the
  // check, but ./check lists it as flaky in its summary and the PR, to fix in the next tidy-up.
  retries: 1,
  forbidOnly: true,
  globalSetup: './global-setup.ts',
  projects: pick([
    { name: 'chromium', testMatch: 'csp.spec.ts', use: { browserName: 'chromium' } },
    { name: 'sign-in', testMatch: 'sign-in.spec.ts', use: desktop },
    // The component gallery is development-only: the built app has none of it (0.4).
    { name: 'gallery', testMatch: 'gallery.spec.ts', use: desktop },
    // Reduced motion and keyboard-only use (0.4).
    { name: 'calm', testMatch: 'calm.spec.ts', use: desktop },
    { name: 'phone', testMatch: 'shell.spec.ts', use: { ...phone, storageState: AUTH_FILE } },
    { name: 'desktop', testMatch: 'shell.spec.ts', use: { ...desktop, storageState: AUTH_FILE } },
    // Ingredients, Pantry and Undo (0.2).
    { name: 'phone 0.2', testMatch: /(pantry|ingredients|undo).*\.spec\.ts/, use: { ...phone, storageState: AUTH_FILE } },
    { name: 'desktop 0.2', testMatch: /(pantry|ingredients|undo).*\.spec\.ts/, use: { ...desktop, storageState: AUTH_FILE } },
    // Shopping and the "How do you count it?" question (0.3).
    { name: 'phone 0.3', testMatch: /shopping.*\.spec\.ts/, use: { ...phone, storageState: AUTH_FILE } },
    { name: 'desktop 0.3', testMatch: /shopping.*\.spec\.ts/, use: { ...desktop, storageState: AUTH_FILE } },
    // The All recipes page and its states (0.4).
    { name: 'phone 0.4 recipes', testMatch: 'recipes.spec.ts', use: { ...phone, storageState: AUTH_FILE } },
    { name: 'desktop 0.4 recipes', testMatch: 'recipes.spec.ts', use: { ...desktop, storageState: AUTH_FILE } },
    // The recipe page and its states (0.4).
    { name: 'phone 0.4 recipe page', testMatch: 'recipe-page.spec.ts', use: { ...phone, storageState: AUTH_FILE } },
    { name: 'desktop 0.4 recipe page', testMatch: 'recipe-page.spec.ts', use: { ...desktop, storageState: AUTH_FILE } },
    // Recipe photos on All recipes and the recipe page (0.4).
    { name: 'phone 0.4 photos', testMatch: 'recipe-photos.spec.ts', use: { ...phone, storageState: AUTH_FILE } },
    { name: 'desktop 0.4 photos', testMatch: 'recipe-photos.spec.ts', use: { ...desktop, storageState: AUTH_FILE } },
    // Recipes on a computer: the three panes (0.4).
    { name: 'desktop 0.4 panes', testMatch: 'recipes-panes.spec.ts', use: { ...desktop, storageState: AUTH_FILE } },
    // Import a recipe: the box, the review, Save and Undo (0.5).
    { name: 'phone 0.5 import', testMatch: 'import.spec.ts', use: { ...phone, storageState: AUTH_FILE } },
    { name: 'desktop 0.5 import', testMatch: 'import.spec.ts', use: { ...desktop, storageState: AUTH_FILE } },
    // Drafts: "Save as draft?", the Drafts screen, carrying on, Delete and Undo (0.5).
    { name: 'phone 0.5 drafts', testMatch: 'drafts.spec.ts', use: { ...phone, storageState: AUTH_FILE } },
    { name: 'desktop 0.5 drafts', testMatch: 'drafts.spec.ts', use: { ...desktop, storageState: AUTH_FILE } },
    // The Plan: week, month, drag, the menu, Undo (0.6).
    { name: 'phone 0.6 plan', testMatch: 'plan.spec.ts', use: { ...phone, storageState: AUTH_FILE } },
    { name: 'desktop 0.6 plan', testMatch: 'plan.spec.ts', use: { ...desktop, storageState: AUTH_FILE } },
    { name: 'webkit 0.6 plan', testMatch: 'plan.spec.ts', use: { ...webkit, storageState: AUTH_FILE } },
    // Cook once, eat for…, tubs and Leftovers here (0.6, PR 4).
    { name: 'phone 0.6 cook once', testMatch: 'plan-cook-once.spec.ts', use: { ...phone, storageState: AUTH_FILE } },
    { name: 'desktop 0.6 cook once', testMatch: 'plan-cook-once.spec.ts', use: { ...desktop, storageState: AUTH_FILE } },
    { name: 'webkit 0.6 cook once', testMatch: 'plan-cook-once.spec.ts', use: { ...webkit, storageState: AUTH_FILE } },
    // The shopping list built from the plan, and the staples card (0.6, PR 5).
    { name: 'phone 0.6 plan list', testMatch: 'plan-list.spec.ts', use: { ...phone, storageState: AUTH_FILE } },
    { name: 'desktop 0.6 plan list', testMatch: 'plan-list.spec.ts', use: { ...desktop, storageState: AUTH_FILE } },
    { name: 'webkit 0.6 plan list', testMatch: 'plan-list.spec.ts', use: { ...webkit, storageState: AUTH_FILE } },
    // Today: Did you cook…?, Cooked it, Didn't, Move it, the first-day state (0.6, PR 6).
    { name: 'phone 0.6 today', testMatch: 'today.spec.ts', use: { ...phone, storageState: AUTH_FILE } },
    { name: 'desktop 0.6 today', testMatch: 'today.spec.ts', use: { ...desktop, storageState: AUTH_FILE } },
    { name: 'webkit 0.6 today', testMatch: 'today.spec.ts', use: { ...webkit, storageState: AUTH_FILE } },
    // Pints: the household's pint in Settings, and the review's US-recipe card (0.6, PR 7).
    { name: 'phone 0.6 pints', testMatch: 'import-pints.spec.ts', use: { ...phone, storageState: AUTH_FILE } },
    { name: 'desktop 0.6 pints', testMatch: 'import-pints.spec.ts', use: { ...desktop, storageState: AUTH_FILE } },
    { name: 'webkit 0.6 pints', testMatch: 'import-pints.spec.ts', use: { ...webkit, storageState: AUTH_FILE } },
    // Live updates, the connection bar and the installable app (0.3, PR 5).
    { name: 'phone 0.3 live', testMatch: /(live|installable)\.spec\.ts/, use: { ...phone, storageState: AUTH_FILE } },
    { name: 'desktop 0.3 live', testMatch: /(live|installable)\.spec\.ts/, use: { ...desktop, storageState: AUTH_FILE } },
    // The server stopped behind the reverse proxy (502): one steady offline state (0.7, F67).
    { name: 'phone 0.7 server down', testMatch: 'server-down.spec.ts', use: { ...phone, storageState: AUTH_FILE } },
    { name: 'desktop 0.7 server down', testMatch: 'server-down.spec.ts', use: { ...desktop, storageState: AUTH_FILE } },
    { name: 'webkit 0.7 server down', testMatch: 'server-down.spec.ts', use: { ...webkit, storageState: AUTH_FILE } },
    // SvelteKit 3's own version check stays out of sight; updates wait for the worker (0.6).
    { name: 'desktop 0.6 version check', testMatch: 'version-check.spec.ts', use: { ...desktop, storageState: AUTH_FILE } },
    // Safari's engine (WebKit), only where it matters most: the offline queue and the service
    // worker (offline.spec, installable.spec, version-check.spec) and the page shell with its
    // strict CSP (shell.spec). Everything else runs on Chromium only, to keep ./check quick (0.6).
    { name: 'webkit offline', testMatch: 'offline.spec.ts', use: webkit },
    { name: 'webkit worker', testMatch: /(installable|version-check|shell)\.spec\.ts/, use: { ...webkit, storageState: AUTH_FILE } },
    // The offline queue end to end (0.3, PR 6). No saved session: each test signs in its own,
    // because signing out must not end the one the other tests share.
    { name: 'phone 0.3 offline', testMatch: 'offline.spec.ts', use: phone },
    { name: 'desktop 0.3 offline', testMatch: 'offline.spec.ts', use: desktop },
    // The recipe editor (0.4).
    { name: 'phone 0.4 editor', testMatch: /recipe-editor.*\.spec\.ts/, use: { ...phone, storageState: AUTH_FILE } },
    { name: 'desktop 0.4 editor', testMatch: /recipe-editor.*\.spec\.ts/, use: { ...desktop, storageState: AUTH_FILE } },
    // Saved screenshots of Pantry and Shopping, phone-light and desktop-dark (0.4), at two device
    // pixels per screen pixel, so thin spaces and small text show as they do on a sharp screen.
    { name: 'screens phone-light', testMatch: 'screens.spec.ts', use: { ...phone, deviceScaleFactor: 2, colorScheme: 'light' as const } },
    { name: 'screens desktop-dark', testMatch: 'screens.spec.ts', use: { ...desktop, viewport: { width: 1440, height: 900 }, deviceScaleFactor: 2, colorScheme: 'dark' as const } },
    { name: 'desktop keyboard', testMatch: 'keyboard.spec.ts', use: { ...desktop, storageState: AUTH_FILE } },
    // Speed on a simulated slow phone (0.4).
    { name: 'slow phone', testMatch: 'slow-phone.spec.ts', use: { ...phone, storageState: AUTH_FILE } },
    // Settings → Privacy (0.5).
    { name: 'phone 0.5 privacy', testMatch: 'privacy.spec.ts', use: { ...phone, storageState: AUTH_FILE } },
    { name: 'desktop 0.5 privacy', testMatch: 'privacy.spec.ts', use: { ...desktop, storageState: AUTH_FILE } },
    // Accessibility (tests/a11y.ts): axe in light and dark; 44 px targets on phone.
    { name: 'phone a11y', testMatch: 'a11y.spec.ts', use: { ...phone, storageState: AUTH_FILE } },
    { name: 'desktop a11y', testMatch: 'a11y.spec.ts', use: { ...desktop, storageState: AUTH_FILE } },
  ]),
  // ./check also asks for a JSON report (PLAYWRIGHT_JSON_OUTPUT_FILE), to find the flaky tests.
  reporter: process.env.PLAYWRIGHT_JSON_OUTPUT_FILE ? [['list'], ['json']] : 'list',
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
    // Generous: in ./check two sets of servers, the backend tests and the image build all start
    // at about the same time.
    timeout: 300_000,
    // Stop serve.mjs politely at the end of the run, so it can stop the servers and remove its
    // throwaway data folder. Playwright's default is to kill it outright, which skips that.
    gracefulShutdown: { signal: 'SIGTERM', timeout: 15_000 },
  },
});
