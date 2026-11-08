import { test, expect, type Page } from './clock.ts';

// SvelteKit 3 checks for a new version of the app by itself when a tab comes back into view
// (the window "focus" event), after some page loads, and every hour unless version.pollInterval
// is 0 (it is: cabledrawer, 25 Oct 2026). The docs give no way to switch the focus check off.
// Updates here come only through our service worker, which keeps the old version until every
// window of it is closed. So SvelteKit's check must never be seen: no offline bar, no toast, no
// console error, no page error; it must never reload the page or touch the worker. The worker
// answers the check itself with its own version (rules.ts, VERSION_FILE), so the server is not
// asked and, with no connection, nothing fails.

async function underWorker(page: Page) {
  await page.goto('/shopping');
  await page.evaluate(() => navigator.serviceWorker.ready.then(() => true));
  await page.reload();
  await expect(page.getByRole('heading', { level: 1 })).toBeVisible();
  // Kept: the app's own start-up has no signal to wait for, and the tests then prove nothing happens.
  await page.waitForTimeout(1500); // the app's own start-up has settled
}

/** What the person can see of the connection: the offline bar and any toast. */
const statusLines = (page: Page) => page.getByRole('status').allInnerTexts();

/** The window getting focus back: where SvelteKit's own check listens. */
const focusBack = async (page: Page) => {
  await page.evaluate(() => window.dispatchEvent(new Event('focus')));
  // Kept: proves no update check is made after the focus event, so it can only be waited out.
  await page.waitForTimeout(1500);
};

/** The tab hidden and shown again, then focused, the way a browser does it. */
const backIntoView = async (page: Page) => {
  await page.evaluate(() => {
    const set = (state: 'hidden' | 'visible') => {
      Object.defineProperty(document, 'visibilityState', { configurable: true, get: () => state });
      Object.defineProperty(document, 'hidden', { configurable: true, get: () => state === 'hidden' });
      document.dispatchEvent(new Event('visibilitychange'));
    };
    set('hidden');
    set('visible');
    window.dispatchEvent(new Event('focus'));
  });
  // Kept: proves no update check is made, so it can only be waited out.
  await page.waitForTimeout(1500);
};

const isWebKit = () => test.info().project.use.browserName === 'webkit';

/**
 * Ask for the version file from the page. The server answers it with "no-cache"; only our worker
 * answers with "no-store", so that header proves the worker (and not the server) answered. On
 * WebKit this is the proof, as request.serviceWorker() only exists on Chromium.
 */
const askVersion = (page: Page) =>
  page.evaluate(async () => {
    const r = await fetch('/_app/version.json');
    return { status: r.status, body: await r.json(), cache: r.headers.get('cache-control') };
  });

/** Anything the person, or the console, would see. */
function watch(page: Page) {
  const problems: string[] = [];
  page.on('console', (m) => {
    if (m.type() === 'error' || m.type() === 'warning') problems.push(`console ${m.type()}: ${m.text()}`);
  });
  page.on('pageerror', (e) => problems.push(`page error: ${e.message}`));
  page.on('requestfailed', (r) => problems.push(`request failed: ${r.url()}`));
  return problems;
}

const mark = (page: Page) =>
  page.evaluate(() => {
    (window as unknown as { __kept: number }).__kept = 1;
  });
const kept = (page: Page) =>
  page.evaluate(() => (window as unknown as { __kept?: number }).__kept);

const workerState = (page: Page) =>
  page.evaluate(async () => {
    const r = await navigator.serviceWorker.getRegistration();
    return {
      installing: Boolean(r?.installing),
      waiting: Boolean(r?.waiting),
      active: r?.active?.scriptURL ?? null,
    };
  });

test('the tab coming back into view, online: nothing shows, nothing reloads, the worker is left alone', async ({
  page,
  context,
}) => {
  await underWorker(page);
  const before = await statusLines(page);
  const worker = await workerState(page);
  await mark(page);
  const problems = watch(page);
  const serverAsked: string[] = [];
  // Chromium can say which requests came from the worker; WebKit can't (see askVersion).
  if (!isWebKit()) {
    context.on('request', (r) => {
      if (r.url().includes('/_app/version.json') && r.serviceWorker()) serverAsked.push(r.url());
    });
  }

  await backIntoView(page);

  expect(await kept(page), 'the page was reloaded').toBe(1);
  expect(await statusLines(page)).toEqual(before);
  expect(await workerState(page)).toEqual(worker);
  expect(problems).toEqual([]);
  expect(serverAsked, 'the worker should answer the version check itself').toEqual([]);
  expect((await askVersion(page)).cache, 'the worker answers it, with its own no-store').toBe('no-store');
  await expect(page.getByRole('heading', { level: 1 })).toBeVisible();
});

test('the window getting focus with no connection: the same bar as before, no toast, no error, no reload', async ({
  page,
  context,
}) => {
  test.skip(test.info().project.use.browserName === 'webkit', "Playwright's WebKit offline switch blocks requests before the service worker sees them (proved 25 Oct); the iPhone hand test covers offline Safari");
  await underWorker(page);
  await context.setOffline(true);
  // The app finds out it is offline by itself (after about three seconds); let that settle,
  // so the bar is the one it would show anyway, then look.
  // Kept: the app notices it is offline by itself after about 3 seconds; waiting it out is the test.
  await page.waitForTimeout(5000);
  const before = await statusLines(page);
  const worker = await workerState(page);
  await mark(page);
  const problems = watch(page);

  await focusBack(page);

  expect(await kept(page), 'the page was reloaded').toBe(1);
  expect(await statusLines(page)).toEqual(before);
  expect(await workerState(page)).toEqual(worker);
  expect(problems, 'SvelteKit’s check must fail nothing, even with no connection').toEqual([]);
  await context.setOffline(false);
});

test('the version check is answered by the worker with the same answer online, offline and before the server could say otherwise', async ({
  page,
  context,
}) => {
  await underWorker(page);
  const online = await askVersion(page);
  expect(online.status).toBe(200);
  expect(typeof online.body.version).toBe('string');
  expect(online.cache).toBe('no-store');
  // The offline half: Playwright's WebKit offline switch blocks requests before the service
  // worker sees them (proved 25 Oct), so only Chromium does it; the iPhone hand test covers
  // offline Safari.
  if (isWebKit()) return;
  await context.setOffline(true);
  expect(await askVersion(page)).toEqual(online);
  await context.setOffline(false);
});

test('the server still serves /_app/version.json, and the worker never keeps it', async ({ page }) => {
  await underWorker(page);
  const cached = await page.evaluate(async () => {
    const out: string[] = [];
    for (const name of await caches.keys()) {
      out.push(...(await (await caches.open(name)).keys()).map((r) => new URL(r.url).pathname));
    }
    return out;
  });
  expect(cached.filter((p) => p.includes('version.json'))).toEqual([]);
  // page.request goes to the server directly, not through the worker.
  const response = await page.request.get('/_app/version.json');
  expect(response.status()).toBe(200);
  expect(response.headers()['cache-control']).toBe('no-cache');
});

test('a new worker waits: the open page keeps working and keeps its worker', async ({ page }) => {
  await underWorker(page);
  await mark(page);
  const before = await workerState(page);
  expect(before.waiting).toBe(false);
  expect(before.active).not.toBeNull();

  // A "new version": the same worker under another address, which the browser treats as a new
  // worker for the same scope. It installs, then waits for every window of the old one to close.
  await page.evaluate(async () => {
    const registration = await navigator.serviceWorker.register('/service-worker.js?next', {
      type: 'module',
    });
    await registration.update();
  });
  await expect.poll(async () => (await workerState(page)).waiting, { timeout: 15_000 }).toBe(true);
  // Kept: proves the waiting worker does NOT take over, so it can only be waited out.
  await page.waitForTimeout(1500); // long enough for it to take over, if anything let it

  const after = await workerState(page);
  expect(after.waiting).toBe(true);
  expect(after.active, 'the old worker is still the one running').toBe(before.active);
  expect(await kept(page), 'the page was reloaded').toBe(1);
  // Still working, with the old worker: a client-side move to another page.
  await page.getByRole('link', { name: 'Pantry' }).first().click();
  await expect(page.getByRole('heading', { level: 1 })).toHaveText('Pantry');
  expect(await kept(page), 'the page was reloaded').toBe(1);
  expect((await workerState(page)).active).toBe(before.active);
});
