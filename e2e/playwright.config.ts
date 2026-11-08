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
// Safari's engine at phone size, only for the screens a phone changes most (Check on the phone, F141).
const webkitPhone = { ...webkit, viewport: { width: 390, height: 844 }, hasTouch: true };

// E2E_PROJECTS picks one or more of the three streams (./check runs them side by side, each
// with its own servers; cabledrawer 8 Nov): "phone" is every Chromium phone project, "webkit" every
// WebKit (Safari engine) project, "desktop" all the rest. Several, comma-separated ("phone,webkit"
// is the old phone half). Unset or empty, every project runs.
const STREAMS = ['phone', 'webkit', 'desktop'];
const wanted = (process.env.E2E_PROJECTS || '').split(',').filter(Boolean);
for (const w of wanted) {
  if (!STREAMS.includes(w)) throw new Error(`E2E_PROJECTS must be phone, webkit or desktop (comma-separated), not "${w}".`);
}
const streamOf = (name: string) =>
  name.startsWith('webkit')
    ? 'webkit'
    : name.startsWith('phone') || name === 'screens phone-light' || name === 'slow phone'
      ? 'phone'
      : 'desktop';
const pick = (projects: Project[]) =>
  wanted.length === 0 ? projects : projects.filter((p) => wanted.includes(streamOf(p.name ?? '')));

export default defineConfig({
  testDir: './tests',
  // Saved screenshots: animations off, no blinking caret, and no pixels allowed to differ.
  expect: { toHaveScreenshot: { animations: 'disabled', caret: 'hide', maxDiffPixels: 0, threshold: 0 } },
  // Each worker runs its own Mealwright server (tests/clock.ts), so files can run side by side:
  // E2E_WORKERS per stream (at most 6: a stream's ports run out after that).
  workers: Number(process.env.E2E_WORKERS ?? 1),
  // One more try for a test that fails (cabledrawer 30 Oct): one that then passes doesn't fail the
  // check, but ./check lists it as flaky in its summary and the PR, to fix in the next tidy-up.
  retries: 1,
  forbidOnly: true,
  // In ./check only (it sets E2E_CHECK_MODE; cabledrawer 8 Nov, T2): stop after 20 failed tests, and
  // when the browser step's time limit is up, so a crashed server or a hang can't run for hours.
  ...(process.env.E2E_CHECK_MODE
    ? {
        maxFailures: Number(process.env.E2E_MAX_FAILURES ?? 20),
        globalTimeout: Number(process.env.E2E_GLOBAL_TIMEOUT_MS ?? 45 * 60_000),
      }
    : {}),
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
    // pantry-list.spec.ts runs on desktop only (cabledrawer 8 Nov, option A in the T2 device list).
    { name: 'phone 0.2', testMatch: /(^|\/)(pantry|ingredients|undo)[^/]*\.spec\.ts$/, testIgnore: /pantry-list\.spec\.ts$/, use: { ...phone, storageState: AUTH_FILE } },
    { name: 'desktop 0.2', testMatch: /(^|\/)(pantry|ingredients|undo)[^/]*\.spec\.ts$/, use: { ...desktop, storageState: AUTH_FILE } },
    // Shopping and the "Pantry keeps it by" question (0.3).
    { name: 'phone 0.8 pack sizes', testMatch: 'pack-sizes.spec.ts', use: { ...phone, storageState: AUTH_FILE } },
    { name: 'desktop 0.8 pack sizes', testMatch: 'pack-sizes.spec.ts', use: { ...desktop, storageState: AUTH_FILE } },
    { name: 'phone 0.8 starter packs', testMatch: 'starter-packs.spec.ts', use: { ...phone, storageState: AUTH_FILE } },
    { name: 'desktop 0.8 starter packs', testMatch: 'starter-packs.spec.ts', use: { ...desktop, storageState: AUTH_FILE } },

    { name: 'phone 0.3', testMatch: /(^|\/)shopping[^/]*\.spec\.ts$/, use: { ...phone, storageState: AUTH_FILE } },
    { name: 'desktop 0.3', testMatch: /(^|\/)shopping[^/]*\.spec\.ts$/, use: { ...desktop, storageState: AUTH_FILE } },
    // Shopping on the phone, "in the shop" (0.8, S4): 390 px on Chromium and on WebKit.
    { name: 'phone 0.8 shop phone', testMatch: 'shop-phone.spec.ts', use: { ...phone, storageState: AUTH_FILE } },
    { name: 'webkit 0.8 shop phone', testMatch: 'shop-phone.spec.ts', use: { ...webkitPhone, storageState: AUTH_FILE } },
    // Plan shopping (0.8, S3): 1280 and 1100 px, set in the tests.
    { name: 'desktop 0.8 plan shopping', testMatch: 'plan-shopping.spec.ts', use: { ...desktop, storageState: AUTH_FILE } },
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
    // "Cooked it", the review: what comes out of the pantry, Use switches, tabs, Undo (0.7, K3).
    { name: 'phone 0.7 cooked', testMatch: 'cooked.spec.ts', use: { ...phone, storageState: AUTH_FILE } },
    { name: 'desktop 0.7 cooked', testMatch: 'cooked.spec.ts', use: { ...desktop, storageState: AUTH_FILE } },
    { name: 'webkit 0.7 cooked', testMatch: 'cooked.spec.ts', use: { ...webkit, storageState: AUTH_FILE } },
    // Cook mode: steps, timers, the chime, leaving, Keep screen awake, Experimental (0.7, K4).
    { name: 'phone 0.7 cook mode', testMatch: 'cook-mode.spec.ts', use: { ...phone, storageState: AUTH_FILE } },
    { name: 'desktop 0.7 cook mode', testMatch: 'cook-mode.spec.ts', use: { ...desktop, storageState: AUTH_FILE } },
    { name: 'webkit 0.7 cook mode', testMatch: 'cook-mode.spec.ts', use: { ...webkit, storageState: AUTH_FILE } },
    // Check screen: change or remove a method step (0.7, F111).
    { name: 'phone 0.7 check steps', testMatch: 'import-steps.spec.ts', use: { ...phone, storageState: AUTH_FILE } },
    { name: 'desktop 0.7 check steps', testMatch: 'import-steps.spec.ts', use: { ...desktop, storageState: AUTH_FILE } },
    { name: 'webkit 0.7 check steps', testMatch: 'import-steps.spec.ts', use: { ...webkit, storageState: AUTH_FILE } },
    // Check on the phone: Focus and One at a time, chosen in Settings (0.7, F141).
    { name: 'phone 0.7 check phone', testMatch: 'import-check-phone.spec.ts', use: { ...phone, storageState: AUTH_FILE } },
    { name: 'desktop 0.7 check phone', testMatch: 'import-check-phone.spec.ts', use: { ...desktop, storageState: AUTH_FILE } },
    { name: 'webkit 0.7 check phone', testMatch: 'import-check-phone.spec.ts', use: { ...webkitPhone, storageState: AUTH_FILE } },
    // Pints: the household's pint in Settings, and the review's US-recipe card (0.6, PR 7).
    { name: 'phone 0.6 pints', testMatch: 'import-pints.spec.ts', use: { ...phone, storageState: AUTH_FILE } },
    { name: 'desktop 0.6 pints', testMatch: 'import-pints.spec.ts', use: { ...desktop, storageState: AUTH_FILE } },
    { name: 'webkit 0.6 pints', testMatch: 'import-pints.spec.ts', use: { ...webkit, storageState: AUTH_FILE } },
    // Portions, Serves - N + and Note (0.7, P1).
    { name: 'phone 0.7 portions', testMatch: 'plan-portions.spec.ts', use: { ...phone, storageState: AUTH_FILE } },
    { name: 'desktop 0.7 portions', testMatch: 'plan-portions.spec.ts', use: { ...desktop, storageState: AUTH_FILE } },
    { name: 'webkit 0.7 portions', testMatch: 'plan-portions.spec.ts', use: { ...webkit, storageState: AUTH_FILE } },
    // The switch Both · Eat · Cook, Plan it, the phone Plan on today, and 768–1100 px (0.7, P2).
    { name: 'phone 0.7 plan views', testMatch: 'plan-views.spec.ts', use: { ...phone, storageState: AUTH_FILE } },
    { name: 'desktop 0.7 plan views', testMatch: 'plan-views.spec.ts', use: { ...desktop, storageState: AUTH_FILE } },
    { name: 'webkit 0.7 plan views', testMatch: 'plan-views.spec.ts', use: { ...webkit, storageState: AUTH_FILE } },
    // Paper cuts on the recipe screens: the editor carries on, Duplicate (0.7, PC1).
    { name: 'phone 0.7 paper cuts', testMatch: 'paper-cuts.spec.ts', use: { ...phone, storageState: AUTH_FILE } },
    { name: 'desktop 0.7 paper cuts', testMatch: 'paper-cuts.spec.ts', use: { ...desktop, storageState: AUTH_FILE } },
    { name: 'webkit 0.7 paper cuts', testMatch: 'paper-cuts.spec.ts', use: { ...webkit, storageState: AUTH_FILE } },
    // Restock dates, "How much?" and navigation (K5, N1, F113).
    { name: 'phone 0.7 staples nav', testMatch: 'staples-nav.spec.ts', use: { ...phone, storageState: AUTH_FILE } },
    { name: 'desktop 0.7 staples nav', testMatch: 'staples-nav.spec.ts', use: { ...desktop, storageState: AUTH_FILE } },
    { name: 'webkit 0.7 staples nav', testMatch: 'staples-nav.spec.ts', use: { ...webkit, storageState: AUTH_FILE } },
    // Live updates, the connection bar and the installable app (0.3, PR 5).
    { name: 'desktop 0.7 plan cards', testMatch: 'plan-cards.spec.ts', use: { ...desktop, storageState: AUTH_FILE } },
    // Month and day: the tags in their day, one screen, a click on any day (0.7, P4).
    { name: 'phone 0.7 plan month', testMatch: 'plan-month.spec.ts', use: { ...phone, storageState: AUTH_FILE } },
    { name: 'desktop 0.7 plan month', testMatch: 'plan-month.spec.ts', use: { ...desktop, storageState: AUTH_FILE } },
    { name: 'webkit 0.7 plan month', testMatch: 'plan-month.spec.ts', use: { ...webkit, storageState: AUTH_FILE } },
    // Stocktake: place by place, picks, counts, staples, the pack size asked once (0.8, S6).
    { name: 'phone 0.8 stocktake', testMatch: 'stocktake.spec.ts', use: { ...phone, storageState: AUTH_FILE } },
    { name: 'desktop 0.8 stocktake', testMatch: 'stocktake.spec.ts', use: { ...desktop, storageState: AUTH_FILE } },
    // Settings: the section list, Meal slots, Shops & places and Recent changes (0.8, S1).
    { name: 'phone 0.8 settings', testMatch: 'settings.spec.ts', use: { ...phone, storageState: AUTH_FILE } },
    { name: 'desktop 0.8 settings', testMatch: 'settings.spec.ts', use: { ...desktop, storageState: AUTH_FILE } },

    { name: 'phone 0.3 live', testMatch: /(^|\/)(live|installable)\.spec\.ts$/, use: { ...phone, storageState: AUTH_FILE } },
    { name: 'desktop 0.3 live', testMatch: /(^|\/)(live|installable)\.spec\.ts$/, use: { ...desktop, storageState: AUTH_FILE } },
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
    // Shopping on the phone offline (0.8, S4): Add as bought, Already have it and the F130 names
    // at 390 px on WebKit, the layout those buttons are made for (the 1280 px run above is Plan shopping).
    { name: 'webkit 0.8 offline phone', testMatch: 'offline.spec.ts', grep: /S4:|F130:/, use: webkitPhone },
    { name: 'webkit worker', testMatch: /(^|\/)(installable|version-check|shell)\.spec\.ts$/, use: { ...webkit, storageState: AUTH_FILE } },
    // The offline queue end to end (0.3, PR 6). No saved session: each test signs in its own,
    // because signing out must not end the one the other tests share.
    { name: 'phone 0.3 offline', testMatch: 'offline.spec.ts', use: phone },
    { name: 'desktop 0.3 offline', testMatch: 'offline.spec.ts', use: desktop },
    // The recipe editor (0.4).
    { name: 'phone 0.4 editor', testMatch: /(^|\/)recipe-editor[^/]*\.spec\.ts$/, use: { ...phone, storageState: AUTH_FILE } },
    { name: 'desktop 0.4 editor', testMatch: /(^|\/)recipe-editor[^/]*\.spec\.ts$/, use: { ...desktop, storageState: AUTH_FILE } },
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
    // serve.mjs says when every server answers. Not `url`: Playwright's port probe before the
    // start could hang ~2 min on this machine (WSL mirrored networking: a closed local port
    // times out instead of refusing), which made a 1-test run take ~2.5 min (T2, 8 Nov).
    wait: { stdout: /E2E: all test servers are ready\./ },
    reuseExistingServer: false,
    // Generous: in ./check three sets of servers, the backend tests and the image build all start
    // at about the same time.
    timeout: 300_000,
    // Stop serve.mjs politely at the end of the run, so it can stop the servers and remove its
    // throwaway data folder. Playwright's default is to kill it outright, which skips that.
    gracefulShutdown: { signal: 'SIGTERM', timeout: 15_000 },
    // serve.mjs stops by itself if this runner dies without stopping it (Ctrl-C, a watchdog).
    env: { E2E_RUNNER_PID: String(process.pid) },
  },
});
