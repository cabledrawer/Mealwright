import { test as base } from '@playwright/test';

// One fixed date and time for every browser test and saved screenshot, the same for the browser
// and the servers, so a run that crosses midnight or a clock change (UK clocks go back on 25
// October) reads the same as any other. Every spec imports `test` and `expect` from here.
//
// The run starts at FIXED_MOMENT and time then passes normally. playwright.config.ts works out
// once per run how far that is from the real time (E2E_CLOCK_SHIFT_MS). The servers move their
// clock by that much (serve.mjs starts them with backend/scripts/e2e_server.py, test-only), and
// each test's browser starts at the real time moved by the same amount (Playwright's clock).
// Sign-in cookies last a number of seconds, so they work whatever the date.

export * from '@playwright/test';

/** The day every test runs on: a Saturday. */
export const FIXED_DAY = '2026-10-17';
/** 10:00 in London (British Summer Time): far from midnight and from the clock change. */
export const FIXED_MOMENT = Date.parse(`${FIXED_DAY}T09:00:00Z`);

/** How far the tests' clock is from the real one, in milliseconds (set in playwright.config.ts). */
export function clockShift(): number {
  const shift = Number(process.env.E2E_CLOCK_SHIFT_MS);
  if (process.env.E2E_CLOCK_SHIFT_MS === undefined || !Number.isFinite(shift)) {
    throw new Error('E2E_CLOCK_SHIFT_MS is not set (playwright.config.ts sets it)');
  }
  return shift;
}

/** Now, on the tests' clock. */
export const testNow = () => Date.now() + clockShift();

/** Every page in the test's own browser starts on the tests' clock. A browser a test opens
 *  itself (browser.newContext) installs it with `context.clock.install({ time: testNow() })`. */
export const test = base.extend({
  context: async ({ context }, use) => {
    await context.clock.install({ time: testNow() });
    await use(context);
  },
});
