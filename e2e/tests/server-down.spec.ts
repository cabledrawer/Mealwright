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
  // `realTime`: this one waits the full time on the real clock; the others move the page's
  // clock on instead, which fires the same timers in the same order (cabledrawer 30 Oct: a faster
  // check, with one real-time test kept).
  { name: 'Ingredients', path: '/recipes/ingredients', notes: 1, realTime: false },
  { name: 'Today', path: '/', notes: 0, realTime: false },
  { name: 'Plan', path: '/plan', notes: 1, realTime: true },
  { name: 'Shopping', path: '/shopping', notes: 0, realTime: false },
  // cabledrawer 30 Oct: Settings and the recipe panes in line with the other pages.
  { name: 'Recipes', path: '/recipes', notes: 1, realTime: false },
  { name: 'Settings', path: '/settings', notes: 1, realTime: false },
] as const;

for (const { name, path, notes, realTime } of PAGES) {
  test(`${name}: the server answering 502 is one steady offline state, and the page comes back with it`, async ({
    page,
  }) => {
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
