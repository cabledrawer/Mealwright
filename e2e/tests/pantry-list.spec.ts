import { test, expect, type Page } from '@playwright/test';
import { isPhone } from './a11y.ts';

// Tap a staple, and "+ List" on a running-low row (0.3, PR 6b; cabledrawer 18 Oct): both add to
// the main shopping list through the same action and waiting list as Shopping, so a tap made
// while the connection is failing is kept and sent once, when the server is back. Pantry
// itself still shows its offline note once the bar says Offline (spec section 6), so the taps
// are made at the moment the connection fails.

const key = () => ({ 'idempotency-key': crypto.randomUUID() });
const tag = () => `${test.info().project.name.replace(/\W/g, '')}${Date.now()}`;

async function call(page: Page, method: 'POST' | 'PATCH', path: string, data: object) {
  const response = await page.request.fetch(`/api/v1${path}`, { method, data, headers: key() });
  expect(response.ok(), `${method} ${path}: ${await response.text()}`).toBe(true);
  return response.json();
}

/** The number of times the server recorded this ingredient being added to a list. */
async function timesAdded(page: Page, foodId: number): Promise<number> {
  const { changes } = await (await page.request.get(`/api/v1/changes?food_id=${foodId}&limit=100`)).json();
  return changes.filter((c: { kind: string }) => c.kind === 'item_added').length;
}

/** The offline bar for this layout (phone: above the tabs; desktop: foot of the sidebar). */
const bar = (page: Page) => page.getByTestId(isPhone(page) ? 'connection-phone' : 'connection-desktop');

test('taps on a staple and on + List made while the connection fails are sent once each', async ({
  page,
  context,
}) => {
  const t = tag();
  const [oil, rice] = [`Oil ${t}`, `Basmati ${t}`];
  const staple = (await call(page, 'POST', '/foods', { name: oil, counted_as: 'volume', staple: true })).food;
  const low = (await call(page, 'POST', '/foods', { name: rice, counted_as: 'weight' })).food;
  await call(page, 'PATCH', `/foods/${low.id}`, { running_low_at: { amount: 500, unit: 'g' } });
  await call(page, 'POST', '/stock', { food_id: low.id, amount: { amount: 300, unit: 'g' } });

  // Pantry, under the service worker, with the shopping list already on this phone.
  await page.goto('/pantry');
  await page.evaluate(() => navigator.serviceWorker.ready.then(() => true));
  const hello = page.waitForResponse((r) => r.url().endsWith('/api/v1/events'));
  await page.reload();
  await expect(page.getByRole('heading', { name: 'Pantry', level: 1 })).toBeVisible();
  await hello;
  const addOil = page.getByRole('button', { name: `Add ${oil} to the shopping list`, exact: true });
  const addRice = page.getByRole('button', { name: `Add ${rice} to the shopping list`, exact: true });
  await expect(addOil).toBeVisible();
  await expect(addRice).toBeVisible();
  await page.waitForTimeout(500);

  // The connection fails; both taps are made before the bar turns to Offline.
  await context.setOffline(true);
  await addOil.click();
  await addRice.click();
  await expect(page.getByRole('button', { name: `${oil}, on the shopping list`, exact: true })).toBeVisible();
  await expect(page.getByRole('button', { name: `${rice}, on the shopping list`, exact: true })).toBeVisible();
  // A second tap adds nothing and says so.
  await page.getByRole('button', { name: `${oil}, on the shopping list`, exact: true }).click();
  await expect(page.getByRole('status').filter({ hasText: `${oil} is already on the shopping list.` })).toBeVisible();

  // On Shopping, both are there, waiting.
  await page.getByRole('link', { name: 'Shopping', exact: true }).first().click();
  await expect(page.getByRole('heading', { name: 'Shopping', level: 1 })).toBeVisible();
  await expect(page.getByRole('button', { name: oil, exact: true })).toBeVisible();
  await expect(page.getByRole('button', { name: rice, exact: true })).toBeVisible();
  await expect(bar(page)).toContainText('2 changes waiting', { timeout: 10_000 });
  await context.setOffline(false);
  await expect(page.getByRole('status').filter({ hasText: 'Back online — all saved' })).toBeVisible({
    timeout: 15_000,
  });
  await expect(bar(page)).toBeHidden();

  // Each was sent exactly once.
  expect(await timesAdded(page, staple.id)).toBe(1);
  expect(await timesAdded(page, low.id)).toBe(1);
  await page.waitForTimeout(1500);
  expect(await timesAdded(page, staple.id)).toBe(1);
  expect(await timesAdded(page, low.id)).toBe(1);
});
