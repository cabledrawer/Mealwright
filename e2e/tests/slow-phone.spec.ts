import { expect, test, type Page, type Route } from './clock.ts';

// Speed is checked, not assumed (spec "Keeping the UI good", item 5). On a simulated slow
// phone (the CPU four times slower, and a slow mobile network), the common actions show
// their result straight away, before the server has answered: the server's answer is held
// back by the test until after the check. So this fails if an action starts waiting for the
// server before it shows anything.

/** Four times slower CPU; about 400 kbit/s and 300 ms each way, like a poor mobile signal. */
async function slowDown(page: Page) {
  const cdp = await page.context().newCDPSession(page);
  await cdp.send('Emulation.setCPUThrottlingRate', { rate: 4 });
  await cdp.send('Network.enable');
  await cdp.send('Network.emulateNetworkConditions', {
    offline: false,
    latency: 300,
    downloadThroughput: (400 * 1000) / 8,
    uploadThroughput: (400 * 1000) / 8,
  });
}

/** "Straight away": well inside what a person notices, with room for the slow CPU. */
const STRAIGHT_AWAY = 2000;
/** Loading the whole app over the slow network. */
const LOAD = 60_000;

const key = () => ({ 'idempotency-key': crypto.randomUUID() });
const tag = () => `Slow${Date.now()}`;

async function call(page: Page, method: 'GET' | 'POST', path: string, data?: object) {
  const response = await page.request.fetch(`/api/v1${path}`, { method, data, headers: key() });
  expect(response.ok(), `${method} ${path}: ${await response.text()}`).toBe(true);
  return response.json();
}

/** Hold back the server's answer to requests like this until `release()`. */
function hold(page: Page, url: RegExp, methods: string[]) {
  let release!: () => void;
  const released = new Promise<void>((resolve) => (release = resolve));
  let held = 0;
  const done = page.route(url, async (route: Route) => {
    if (!methods.includes(route.request().method())) return route.continue();
    held++;
    await released;
    await route.continue().catch(() => {});
  });
  return { release, held: () => held, done };
}

test('slow phone: ticking an item shows it ticked at once', async ({ page }) => {
  const name = `Tick ${tag()}`;
  const { food } = await call(page, 'POST', '/foods', { name, counted_as: 'weight' });
  const lists = await (await page.request.get('/api/v1/shopping/lists')).json();
  const list = lists.lists.find((l: { main: boolean }) => l.main).id;
  await call(page, 'POST', `/shopping/lists/${list}/items`, {
    food_id: food.id,
    amount: { amount: 300, unit: 'g' },
  });
  await page.goto('/shopping');
  const tick = page.getByRole('checkbox', { name: `Tick ${name}` });
  await expect(tick).toBeVisible({ timeout: LOAD });
  // The page's own start-up requests are answered before the network slows down.
  await page.waitForLoadState('networkidle');

  await slowDown(page);
  const server = hold(page, /\/api\/v1\/shopping\/actions/, ['POST']);
  await tick.click();
  // The list has let go of it and says so with an Undo toast, before the server has said anything.
  await expect(page.getByRole('status').filter({ hasText: `${name} → Cupboard` })).toBeVisible({
    timeout: STRAIGHT_AWAY,
  });
  await expect(tick).toHaveCount(0);
  expect(server.held(), 'the server has not answered yet').toBeLessThanOrEqual(1);
  server.release();
  await server.done;
});

test('slow phone: adding an item shows it on the list at once', async ({ page }) => {
  const name = `Add ${tag()}`;
  await call(page, 'POST', '/foods', { name, counted_as: 'weight' });
  await page.goto('/shopping');
  await expect(page.getByRole('textbox', { name: 'Add an item' })).toBeVisible({ timeout: LOAD });
  // The page's own start-up requests are answered before the network slows down.
  await page.waitForLoadState('networkidle');

  await slowDown(page);
  const server = hold(page, /\/api\/v1\/shopping\/actions/, ['POST']);
  await page.getByRole('textbox', { name: 'Add an item' }).fill(name);
  await page
    .getByRole('list', { name: 'Matching ingredients' })
    .getByRole('button', { name })
    .click();
  await expect(page.getByRole('button', { name, exact: true })).toBeVisible({
    timeout: STRAIGHT_AWAY,
  });
  server.release();
  await server.done;
});

test('slow phone: opening Pantry and Shopping shows the page at once', async ({ page }) => {
  await page.goto('/shopping');
  // Under the app's worker, as on a phone that has been here before: the pages' code comes
  // from the phone, not over the slow network.
  await page.evaluate(() => navigator.serviceWorker.ready.then(() => true));
  await page.reload();
  await expect(page.getByRole('heading', { name: 'Shopping', level: 1 })).toBeVisible({
    timeout: LOAD,
  });
  // Wait for the list itself: the phone keeps this copy, so the next visit can draw it
  // without the server.
  await expect(page.getByText(/\d+ to buy/).first()).toBeVisible({ timeout: LOAD });
  // The page's own start-up requests are answered before the network slows down.
  await page.waitForLoadState('networkidle');

  await slowDown(page);
  const server = hold(page, /\/api\/v1\/(pantry|shopping)/, ['GET']);
  const tabs = page.getByRole('navigation').last();
  await tabs.getByRole('link', { name: 'Pantry' }).click();
  await expect(page.getByRole('heading', { name: 'Pantry', level: 1 })).toBeVisible({
    timeout: STRAIGHT_AWAY,
  });
  await tabs.getByRole('link', { name: 'Shop' }).click();
  await expect(page.getByRole('heading', { name: 'Shopping', level: 1 })).toBeVisible({
    timeout: STRAIGHT_AWAY,
  });
  // The list comes from the copy on the phone, not from the held request.
  await expect(page.getByText(/\d+ to buy/).first()).toBeVisible({ timeout: STRAIGHT_AWAY });
  server.release();
  await server.done;
});
