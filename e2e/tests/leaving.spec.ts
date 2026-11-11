import { test, expect, type Page, type Route } from './clock.ts';

// Leaving a page while it still talks to the server (T1, cabledrawer 11 Nov). A request the page
// starts after the browser has begun to leave it is refused by WebKit (Safari's engine), which
// logs "Fetch API cannot load … due to access control checks." as a script error; that failed
// plan-start.spec.ts under load. Requests cut off by the leave are not a failure either: the page
// being left must not say "Can’t reach your Mealwright server" while the next one loads.
// Runs on Chromium (phone and computer) and on WebKit (computer), see playwright.config.ts.

const key = () => ({ 'idempotency-key': crypto.randomUUID() });
const stamp = () => `${Date.now().toString(36)}${Math.floor(Math.random() * 1296).toString(36)}`;

/** Every script error and console error the page raises, as text. */
function scriptErrors(page: Page) {
  const errors: string[] = [];
  page.on('pageerror', (error) => errors.push(`pageerror: ${error.message}`));
  page.on('console', (message) => {
    if (message.type() === 'error') errors.push(`console: ${message.text()}`);
  });
  return errors;
}

/** Hold requests whose address matches `url` until `release()`; `seen(n)` waits for the n-th. */
async function hold(page: Page, url: RegExp, only: (route: Route) => boolean = () => true) {
  const held: Route[] = [];
  const waiters: { n: number; resolve: () => void }[] = [];
  const handler = async (route: Route) => {
    if (!only(route)) return route.continue();
    held.push(route);
    for (const w of waiters.filter((w) => held.length >= w.n)) w.resolve();
  };
  await page.route(url, handler);
  return {
    seen: (n: number) =>
      new Promise<void>((resolve) => {
        if (held.length >= n) resolve();
        else waiters.push({ n, resolve });
      }),
    release: async () => {
      await page.unroute(url, handler);
      for (const route of held.splice(0)) await route.continue().catch(() => undefined);
    },
  };
}

const isPage = (route: Route) => route.request().isNavigationRequest();
const pantryHeading = (page: Page) => page.getByRole('heading', { name: 'Pantry', level: 1 });

test.beforeEach(async ({ page }) => {
  // The list has a row, so a failed reload would say so beside it.
  const made = await page.request.fetch('/api/v1/recipes', {
    method: 'POST',
    headers: key(),
    data: { name: `Leaving ${stamp()}`, steps: [{ text: 'Stir.' }] },
  });
  expect(made.ok(), await made.text()).toBe(true);
});

test('a request started while the page is being left raises no script error', async ({ page }) => {
  const errors = scriptErrors(page);
  // Something on the page asks the server just after the person has started to leave it: here,
  // a timer that fires then says the tab has come back, so All recipes fetches its list again.
  await page.addInitScript(() =>
    addEventListener('beforeunload', () =>
      setTimeout(() => {
        document.dispatchEvent(new Event('visibilitychange'));
        console.info('asked again while leaving');
      }, 0)
    )
  );
  await page.goto('/recipes');
  await expect(page.locator('[aria-busy="false"]').first()).toBeVisible();
  // The next page is slow to come, so the one being left is still there when the timer fires.
  const next = await hold(page, /\/pantry$/, isPage);
  const asked = page.waitForEvent('console', (m) => m.text() === 'asked again while leaving');
  const leaving = page.goto('/pantry');
  try {
    await next.seen(1);
    await asked;
  } finally {
    await next.release();
  }
  await leaving;
  await expect(pantryHeading(page)).toBeVisible();
  expect(errors, 'leaving raised no script error').toEqual([]);
});

test('requests cut off by leaving are not shown as “can’t reach the server”', async ({ page, browserName }) => {
  // Chromium lets the page's requests go on until the next page arrives; WebKit cuts them off as
  // soon as the leave starts, with the page still on screen.
  test.skip(browserName !== 'webkit', 'only WebKit cuts requests off while the page is still showing');
  const errors = scriptErrors(page);
  // The list's recipes and tags are still on their way when the person leaves.
  const list = await hold(page, /\/api\/v1\/recipes(\?|\/tags$)/);
  const next = await hold(page, /\/pantry$/, isPage);
  const cut: string[] = [];
  page.on('requestfailed', (request) => {
    if (/\/api\/v1\/recipes(\?|\/tags$)/.test(request.url())) cut.push(request.url());
  });
  let leaving: Promise<unknown> | null = null;
  try {
    await page.goto('/recipes');
    await list.seen(2);
    leaving = page.goto('/pantry');
    await next.seen(1);
    await expect.poll(() => cut.length, 'the browser cut the list’s requests off').toBe(2);
    // The page being left is still on screen until the next one comes. Once it has dealt with
    // the cut-off requests (one turn of its event loop), it says nothing about the server.
    const words = await page.evaluate(
      () => new Promise<string>((done) => setTimeout(() => done(document.body.innerText), 0))
    );
    expect(words).not.toMatch(/Can’t reach|You’re offline|Couldn’t load/);
  } finally {
    await next.release();
    await list.release();
  }
  await leaving;
  await expect(pantryHeading(page)).toBeVisible();
  expect(errors, 'leaving raised no script error').toEqual([]);
});
