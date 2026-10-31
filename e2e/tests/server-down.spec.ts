import { test, expect, type Page, type Route } from './clock.ts';
import { isPhone } from './a11y.ts';

// The server stopped behind the reverse proxy (0.7, F67; spec section 6, "Server down (F67's
// cause)", cabledrawer 28 Oct). With Mealwright stopped, Caddy answers every request with an empty
// 502. The app must show one steady offline state until the server is really back, never
// "Back online — all saved" while it's down, and the page again once it is.
//
// No service worker here: on WebKit, once it controls the page, page.route stops seeing its
// requests (see import-pints.spec.ts). Only /api is answered by the "proxy", so the page
// itself still loads, as it does from the service worker's copy on a phone.
test.use({ serviceWorkers: 'block' });

/** The offline bar for this layout (phone: above the tabs; desktop: foot of the sidebar). */
const bar = (page: Page) => page.getByTestId(isPhone(page) ? 'connection-phone' : 'connection-desktop');

const backOnline = (page: Page) => page.getByText('Back online — all saved');

/** Caddy with the backend stopped: a 502 with nothing in it. */
const proxyGap = (route: Route) => route.fulfill({ status: 502, body: '' });

const PAGES = [
  // `notes`: how many "Can't reach your Mealwright server." notes: Today and Shopping show
  // their saved copy instead.
  // `realTime`: this one waits the full time on the real clock, on the desktop project only;
  // the others, and this one on phone and WebKit, move the page's clock on instead, which fires
  // the same timers in the same order (cabledrawer 30 Oct: a faster check, with one real-time test
  // kept, on one browser).
  { name: 'Ingredients', path: '/recipes/ingredients', notes: 1, realTime: false },
  { name: 'Today', path: '/', notes: 0, realTime: false },
  { name: 'Plan', path: '/plan', notes: 1, realTime: true },
  { name: 'Shopping', path: '/shopping', notes: 0, realTime: false },
  // cabledrawer 30 Oct: Settings and the recipe panes in line with the other pages.
  { name: 'Recipes', path: '/recipes', notes: 1, realTime: false },
  { name: 'Settings', path: '/settings', notes: 1, realTime: false },
] as const;

for (const { name, path, notes, realTime: realTimePage } of PAGES) {
  test(`${name}: the server answering 502 is one steady offline state, and the page comes back with it`, async ({
    page,
  }, testInfo) => {
    const realTime = realTimePage && testInfo.project.name === 'desktop 0.7 server down';
    if (realTime) test.slow();
    // A second of the page's time: really waited, or the page's clock moved on at once.
    const second = () => (realTime ? page.waitForTimeout(1000) : page.clock.runFor(1000));
    /** Wait for the bar to come or go, letting the page's time pass a second at a time. */
    const barTurns = (shown: boolean) =>
      expect(async () => {
        if (!realTime) await page.clock.runFor(1000);
        await expect(bar(page))[shown ? 'toBeVisible' : 'toBeHidden']({ timeout: realTime ? 15_000 : 500 });
      }).toPass({ timeout: 20_000 });
    // Open it once with the server up, as Tess had (Today and Shopping keep a copy).
    await page.goto(path);
    await expect(page.getByRole('heading', { level: 1 })).toBeVisible();
    await page.waitForLoadState('networkidle');

    // The server stops, and the page is reloaded.
    await page.route('**/api/**', proxyGap);
    await page.reload();
    await barTurns(true);
    // The bar's word follows the cause too (cabledrawer 30 Oct): the device has a network.
    await expect(bar(page)).toContainText('Can’t reach server');

    // Steady for over two rounds of the online check (every 5 seconds): the bar never goes,
    // the page never flits between "You're offline" and itself, and no "Back online" toast.
    // The device's network is fine; only the server doesn't answer (cabledrawer 30 Oct): "Can't
    // reach your Mealwright server…", never "You're offline…".
    const note = page.getByRole('heading', { name: 'Can’t reach your Mealwright server.' });
    for (let n = 0; n < 12; n++) {
      await expect(bar(page)).toBeVisible();
      await expect(note).toHaveCount(notes);
      await expect(backOnline(page)).toHaveCount(0);
      await expect(page.getByText(/You’re offline/)).toHaveCount(0);
      await second();
    }

    // The server is back: the next check finds it, the bar goes, and the page is there.
    await page.unroute('**/api/**', proxyGap);
    await barTurns(false);
    await expect(backOnline(page)).toBeVisible();
    await expect(page.getByRole('heading', { level: 1 })).toBeVisible();
    await expect(note).toHaveCount(0);
  });
}

// F80 (0.7 alpha 1 hand test, cabledrawer 30 Oct): with a recipe open on the PC, about 20 seconds
// after the server stopped, the open recipe was replaced by the "Can't reach" note, with no
// typing and no reload. What is already on screen stays; the bar says the server is down.
async function recipeStaysWhenServerStops(page: Page, withServiceWorker: boolean) {
  const name = `Dosa ${Date.now().toString(36)}`;
  const made = await page.request.fetch('/api/v1/recipes', {
    method: 'POST',
    data: { name, serves: 2, lines: [{ words: 'rice', amount: 200, unit: 'g' }] },
    headers: { 'idempotency-key': crypto.randomUUID() },
  });
  expect(made.status()).toBe(201);
  const id = ((await made.json()) as { id: number }).id;
  await page.goto(`/recipes/${id}`);
  if (withServiceWorker) {
    // The service worker controls the page (after a reload) before the server stops.
    await page.evaluate(() => navigator.serviceWorker.ready.then(() => undefined));
    await page.reload();
    await expect.poll(() => page.evaluate(() => navigator.serviceWorker.controller !== null)).toBe(true);
  }
  const reading = page.getByRole('region', { name: 'Recipe', exact: true });
  await expect(reading.getByRole('heading', { level: 1, name })).toBeVisible();
  await expect(page.getByRole('region', { name: 'Recipe list' })).toBeVisible();
  await page.waitForLoadState('networkidle');

  // The server stops: every call gets the proxy's empty 502. The page's time moves on past
  // the bar's wait, several rounds of the online check and the live stream's retries.
  await page.route('**/api/**', proxyGap);
  // The live stream dropping makes the page ask its server whether it is there; the browser's
  // own "online" word makes it ask the same way (a stream already open can't be dropped from
  // here).
  await page.evaluate(() => window.dispatchEvent(new Event('online')));
  for (let n = 0; n < 30; n++) await page.clock.runFor(1000);

  // The one steady message is the bar; the recipe and the list stay where they were.
  await expect(bar(page)).toBeVisible();
  await expect(reading.getByRole('heading', { level: 1, name })).toBeVisible();
  await expect(page.getByRole('region', { name: 'Recipe list' })).toBeVisible();
  await expect(page.getByRole('heading', { name: 'Can’t reach your Mealwright server.' })).toHaveCount(0);
}

test('a recipe already open stays when the server stops, and the list beside it too', async ({ page }) => {
  test.skip(isPhone(page), 'The list and the recipe are beside each other on a computer only.');
  await recipeStaysWhenServerStops(page, false);
});

// The same with the service worker controlling the page, as on an installed app (Chromium only:
// WebKit's page.route doesn't see requests once a service worker controls the page).
test.describe('with the service worker', () => {
  test.use({ serviceWorkers: 'allow' });
  test('a recipe already open stays when the server stops (service worker on)', async ({ page, browserName }) => {
    test.skip(isPhone(page) || browserName !== 'chromium', 'Computer layout, Chromium only.');
    await recipeStaysWhenServerStops(page, true);
  });
});
