import { test, expect, type Page } from './clock.ts';
import {
  checkPage,
  expectNoAxeViolations,
  inTheme,
  isPhone,
  setAccountTheme,
  THEMES,
} from './a11y.ts';

// Live updates and the connection bar (0.3, PR 5), against the real server, on phone and
// desktop (sync protocol 10 and 11.4; UX principle 16).

const key = () => ({ 'idempotency-key': crypto.randomUUID() });
const tag = () => `${test.info().project.name.replace(/\W/g, '')}${Date.now()}`;

async function call(page: Page, method: 'POST', path: string, data?: object) {
  const response = await page.request.fetch(`/api/v1${path}`, { method, data, headers: key() });
  expect(response.ok(), `${method} ${path}: ${await response.text()}`).toBe(true);
  return response.json();
}

async function mainList(page: Page): Promise<string> {
  const { lists } = await (await page.request.get('/api/v1/shopping/lists')).json();
  return lists.find((l: { main: boolean }) => l.main).id;
}

async function onList(page: Page, name: string) {
  const { food } = await call(page, 'POST', '/foods', { name, counted_as: 'weight' });
  await call(page, 'POST', `/shopping/lists/${await mainList(page)}/items`, {
    food_id: food.id,
    amount: { amount: 500, unit: 'g' },
  });
}

/** The offline bar for this layout (phone: above the tabs; desktop: foot of the sidebar). */
const bar = (page: Page) => page.getByTestId(isPhone(page) ? 'connection-phone' : 'connection-desktop');

/** The page is open, signed in, and its live stream has said hello (so nothing is still on its way). */
async function open(page: Page, path: string) {
  const hello = page.waitForResponse((r) => r.url().endsWith('/api/v1/events'));
  await page.goto(path);
  await expect(page.getByRole('heading', { level: 1 })).toBeVisible();
  await hello;
  // Nothing may still be on its way: an answer that reaches the app after the connection is cut
  // counts as "connected" and cancels the offline bar before it shows. (A fixed half-second was
  // not always long enough on a busy machine.)
  await page.waitForLoadState('networkidle');
}

test.beforeEach(async ({ page }) => {
  await setAccountTheme(page, 'auto');
});

test('a second window sees a tick live', async ({ page, context }) => {
  const name = `Live ${tag()}`;
  await onList(page, name);
  const other = await context.newPage();
  await open(page, '/shopping');
  await open(other, '/shopping');
  await expect(other.getByRole('checkbox', { name: `Tick ${name}` })).toBeVisible();

  // Ticking in one window takes the item off the "to buy" part of the other, with no reload
  // (it moves into the folded "In the trolley").
  await page.getByRole('checkbox', { name: `Tick ${name}` }).click();
  await expect(other.getByRole('checkbox', { name: `Tick ${name}` })).toHaveCount(0, {
    timeout: 10_000,
  });
  await other.close();
});

test('a second window adding an item shows up live, without a reload', async ({ page, context }) => {
  const other = await context.newPage();
  await open(page, '/shopping');
  await open(other, '/shopping');
  const name = `Added ${tag()}`;
  await onList(other, name); // through the API, from the other window
  await expect(page.getByRole('button', { name, exact: true })).toBeVisible({ timeout: 10_000 });
  await other.close();
});

test('the Pantry refreshes live and keeps what is typed in an open form', async ({ page, context }) => {
  const other = await context.newPage();
  await open(page, '/pantry');
  await page
    .getByRole('button', { name: /Add to pantry/ })
    .first()
    .click();
  const sheet = page.getByRole('dialog', { name: 'Add to pantry' });
  await sheet.getByRole('searchbox', { name: 'Find an ingredient' }).fill('half typed');

  // The other window puts something in the pantry.
  const name = `Stocked ${tag()}`;
  const { food } = await call(other, 'POST', '/foods', { name, counted_as: 'weight' });
  await call(other, 'POST', '/stock', { food_id: food.id, amount: { amount: 300, unit: 'g' } });

  // The open form is left alone...
  await page.waitForTimeout(1500);
  await expect(sheet.getByRole('searchbox', { name: 'Find an ingredient' })).toHaveValue('half typed');
  // ...and the list behind it is up to date once it is closed.
  await page.keyboard.press('Escape');
  await expect(page.getByText(name).first()).toBeVisible({ timeout: 10_000 });
  await other.close();
});

test('the stream is open and answers hello, and the app uses only that', async ({ page }) => {
  const response = page.waitForResponse((r) => r.url().endsWith('/api/v1/events'));
  await open(page, '/shopping');
  const events = await response;
  expect(events.status()).toBe(200);
  expect(events.headers()['content-type']).toContain('text/event-stream');
  expect(events.headers()['cache-control']).toBe('no-store');
});

test.describe('the connection bar', () => {
  test('appears after 3 seconds offline, with Try now, and "Back online — all saved" when it returns', async ({
    page,
    context,
  }) => {
    await open(page, '/shopping');
    await expect(bar(page)).toBeHidden();
    await context.setOffline(true);
    await expect(bar(page)).toBeVisible({ timeout: 10_000 });
    await expect(bar(page)).toContainText('Offline');
    await expect(bar(page)).not.toContainText('waiting'); // no changes made
    await expect(bar(page).getByRole('button', { name: 'Try now' })).toBeVisible();

    await context.setOffline(false);
    await expect(bar(page)).toBeHidden({ timeout: 10_000 });
    const toast = page.getByRole('status').filter({ hasText: 'Back online — all saved' });
    await expect(toast).toBeVisible();
  });

  test('a blip shows nothing at all', async ({ page, context }) => {
    await open(page, '/shopping');
    await context.setOffline(true);
    await page.waitForTimeout(1000);
    await context.setOffline(false);
    // Past the 3 seconds it would have taken, still nothing, and no toast.
    await page.waitForTimeout(4000);
    await expect(bar(page)).toBeHidden();
    await expect(page.getByText('Back online')).toHaveCount(0);
  });

  test('the Shopping subtitle says offline while offline', async ({ page, context }) => {
    // Other projects' planned meals may have put plan lines on the shared list (0.6): the
    // subtitle then says so too.
    await open(page, '/shopping');
    await expect(page.getByText(/^\d+ to buy(?: · built from .+)? · (synced with .+|saved)$/)).toBeVisible();
    await context.setOffline(true);
    const device = isPhone(page) ? 'phone' : 'computer';
    await expect(
      page.getByText(new RegExp(`^\\d+ to buy(?: · built from .+)? · offline, saving on this ${device}$`)),
    ).toBeVisible({ timeout: 10_000 });
    await context.setOffline(false);
    await expect(page.getByText(/^\d+ to buy(?: · built from .+)? · (synced with .+|saved)$/)).toBeVisible({
      timeout: 10_000,
    });
  });

  test('Try now stays offline while the server can’t be reached, and reconnects when it can', async ({
    page,
    context,
  }) => {
    await open(page, '/pantry');
    // Only our server is unreachable (the browser itself still says it is online, so
    // nothing but Try now will bring the app back quickly).
    const blocked = (route: { abort: () => Promise<void> }) => route.abort();
    await context.route('**/api/**', blocked);
    // The app comes back to the foreground, fetches, and finds it can't reach the server.
    await page.evaluate(() => document.dispatchEvent(new Event('visibilitychange')));
    await expect(bar(page)).toBeVisible({ timeout: 15_000 });
    // Pantry needs the server: it says so, and points to Shopping.
    await expect(
      page.getByText('Pantry comes back by itself when the server answers. Your shopping list works offline.'),
    ).toBeVisible();
    const tryNow = bar(page).getByRole('button', { name: 'Try now' });
    await tryNow.click();
    await expect(bar(page)).toBeVisible(); // still can't reach it

    await context.unroute('**/api/**', blocked);
    await tryNow.click();
    await expect(bar(page)).toBeHidden({ timeout: 10_000 });
    await expect(page.getByRole('status').filter({ hasText: 'Back online — all saved' })).toBeVisible();
  });

  test('desktop: a small dot when the sidebar is collapsed', async ({ page, context }) => {
    test.skip(isPhone(page), 'the sidebar is desktop only');
    await open(page, '/shopping');
    await page.getByRole('button', { name: 'Collapse sidebar' }).click();
    await context.setOffline(true);
    const dot = page.getByTestId('connection-dot');
    await expect(dot.getByRole('button', { name: 'Offline. Try now' })).toBeVisible({
      timeout: 10_000,
    });
    await context.setOffline(false);
    await expect(dot.getByRole('button')).toBeHidden({ timeout: 10_000 });
    await page.getByRole('button', { name: 'Expand sidebar' }).click();
  });

  test('the bar and the toast pass the accessibility checks in both themes', async ({
    page,
    context,
  }) => {
    await open(page, '/shopping');
    await context.setOffline(true);
    await expect(bar(page)).toBeVisible({ timeout: 10_000 });
    await checkPage(page); // both themes
    // 44 px targets are checked by checkPage on the phone; on desktop check Try now itself.
    const box = await bar(page).getByRole('button', { name: 'Try now' }).boundingBox();
    expect(box?.height ?? 0).toBeGreaterThanOrEqual(44 - 0.5);

    await context.setOffline(false);
    const toast = page.getByRole('status').filter({ hasText: 'Back online — all saved' });
    await expect(toast).toBeVisible({ timeout: 10_000 });
    await toast.hover(); // a toast waits while the pointer is on it
    // Check the toast as it stays, not halfway through its 180 ms fade-in.
    await toast.evaluate((el) =>
      Promise.all(
        (el.closest('.toast') ?? el).getAnimations({ subtree: true }).map((a) => a.finished),
      ),
    );
    for (const theme of THEMES) {
      await inTheme(page, theme);
      await expectNoAxeViolations(page, `Back online toast, ${theme}`);
    }
  });
});

test.describe('the app talks only to itself', () => {
  test('every request the app makes goes to the app’s own address only', async ({ page, context }) => {
    const base = new URL(test.info().project.use.baseURL ?? 'http://127.0.0.1').origin;
    const strangers: string[] = [];
    let fromWorker = 0;
    context.on('request', (request) => {
      if (request.serviceWorker()) fromWorker += 1;
      const url = request.url();
      if (url.startsWith('data:') || url.startsWith('blob:')) return;
      if (new URL(url).origin !== base) strangers.push(`${request.method()} ${url}`);
    });
    for (const path of ['/', '/shopping', '/pantry', '/recipes', '/settings', '/plan']) {
      await open(page, path);
    }
    // The service worker's own requests too: wait for it, then load once more under it.
    await page.evaluate(() => navigator.serviceWorker.ready.then(() => true));
    await page.reload();
    await expect(page.getByRole('heading', { level: 1 })).toBeVisible();
    expect(context.serviceWorkers().length).toBeGreaterThan(0);
    await page.waitForTimeout(1000);
    // Proof that the worker's own requests (its precaching) were seen, not just the page's.
    expect(fromWorker, 'no request from the service worker was seen').toBeGreaterThan(0);
    expect(strangers, `requests that left the app’s address:\n${strangers.join('\n')}`).toEqual([]);
  });
});
