import { test, expect, type Page } from '@playwright/test';
import { isPhone } from './a11y.ts';
import { ADMIN } from './servers.ts';

// The offline queue end to end (0.3, PR 6): sync protocol section 14, E2 and E3, against the
// real server and service worker, on phone and desktop. Each test signs in a session of its
// own (no saved session), because E3 signs out and that must not end anyone else's.
//
// E1 (two logins, Tess and Wren) needs a second login, which 0.3 has no way to make
// yet; it's left for when there is one.

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

/** A new ingredient, by weight; on the main list too unless `listed` is false. */
async function ingredient(page: Page, name: string, listed = true) {
  const { food } = await call(page, 'POST', '/foods', { name, counted_as: 'weight' });
  if (listed) {
    await call(page, 'POST', `/shopping/lists/${await mainList(page)}/items`, {
      food_id: food.id,
      amount: { amount: 500, unit: 'g' },
    });
  }
}

interface ServerItem {
  food: { name: string };
  ticked_at: string | null;
}

/** The main list's lines, as the server has them. */
async function serverItems(page: Page): Promise<ServerItem[]> {
  const view = await (await page.request.get(`/api/v1/shopping/lists/${await mainList(page)}`)).json();
  return view.shops.flatMap((shop: { aisles: { items: ServerItem[] }[]; in_trolley: ServerItem[] }) => [
    ...shop.aisles.flatMap((a) => a.items),
    ...shop.in_trolley,
  ]);
}

/** The offline bar for this layout (phone: above the tabs; desktop: foot of the sidebar). */
const bar = (page: Page) => page.getByTestId(isPhone(page) ? 'connection-phone' : 'connection-desktop');

/** "Offline — 3 changes waiting" on a phone; on a desktop, the line under "Offline". */
const waitingText = (page: Page, n: number) => {
  const changes = `${n} ${n === 1 ? 'change' : 'changes'}`;
  return isPhone(page) ? `Offline — ${changes} waiting` : `${changes} waiting. They'll save when you're back.`;
};

/** The phone database is there. */
const phoneDatabase = (page: Page) =>
  page.evaluate(async () => (await indexedDB.databases()).some((db) => db.name === 'mealwright'));

/** Sign in with a session of this test's own. */
async function signIn(page: Page) {
  const signedIn = await page.request.post('/api/v1/session', {
    data: { username: ADMIN.username, password: ADMIN.password },
  });
  expect(signedIn.ok()).toBe(true);
}

/** On Shopping, with the app under its worker and the live stream open. */
async function start(page: Page) {
  await page.goto('/shopping');
  await page.evaluate(() => navigator.serviceWorker.ready.then(() => true));
  const hello = page.waitForResponse((r) => r.url().endsWith('/api/v1/events'));
  await page.reload(); // the first page load is not under the worker; this one is
  await expect(page.getByRole('heading', { name: 'Shopping', level: 1 })).toBeVisible();
  await hello;
  await page.waitForTimeout(500);
}

test('E2: changes made offline survive a reload, then reach the server', async ({ page, context }) => {
  const t = tag();
  const [first, second, added] = [`Ghee ${t}`, `Jaggery ${t}`, `Tamarind ${t}`];
  await signIn(page);
  await ingredient(page, first);
  await ingredient(page, second);
  await ingredient(page, added, false);
  await start(page);

  await context.setOffline(true);
  await page.getByRole('checkbox', { name: `Tick ${first}` }).click();
  await page.getByRole('checkbox', { name: `Tick ${second}` }).click();
  await page.getByRole('textbox', { name: 'Add an item' }).fill(added);
  await page.getByRole('list', { name: 'Matching ingredients' }).getByRole('button', { name: added }).click();
  await expect(page.getByRole('button', { name: added, exact: true })).toBeVisible();
  await expect(bar(page)).toContainText(waitingText(page, 3), { timeout: 10_000 });

  // Reloaded while offline: the app comes from the worker, the list and the 3 changes from
  // the phone.
  await page.reload();
  await expect(page.getByRole('heading', { name: 'Shopping', level: 1 })).toBeVisible();
  await expect(page.getByRole('button', { name: added, exact: true })).toBeVisible();
  await expect(page.getByRole('checkbox', { name: `Tick ${first}` })).toHaveCount(0);
  await expect(page.getByRole('checkbox', { name: `Tick ${second}` })).toHaveCount(0);
  await expect(bar(page)).toContainText(waitingText(page, 3), { timeout: 10_000 });

  await context.setOffline(false);
  await expect(page.getByRole('status').filter({ hasText: 'Back online — all saved' })).toBeVisible({
    timeout: 15_000,
  });
  await expect(bar(page)).toBeHidden();
  const items = await serverItems(page);
  const line = (name: string) => items.find((i) => i.food.name === name);
  expect(line(first)?.ticked_at).not.toBeNull();
  expect(line(second)?.ticked_at).not.toBeNull();
  expect(line(added)).toBeDefined();
  expect(line(added)?.ticked_at).toBeNull();
});

test('E3: signing out offline warns first, then wipes, and the session ends once back', async ({
  page,
  context,
}) => {
  const name = `Cardamom ${tag()}`;
  await signIn(page);
  await ingredient(page, name);
  await start(page);

  await context.setOffline(true);
  await page.getByRole('checkbox', { name: `Tick ${name}` }).click();
  await expect(bar(page)).toContainText(waitingText(page, 1), { timeout: 10_000 });
  await page.getByRole('link', { name: 'Settings' }).first().click();
  await expect(page.getByRole('heading', { name: 'Settings', level: 1 })).toBeVisible();

  // The warning, with its three choices. Stay signed in keeps the change.
  const warning = "1 change hasn't been sent yet. If you sign out now, it's lost.";
  await page.getByRole('button', { name: 'Sign out', exact: true }).click();
  await expect(page.getByRole('alert')).toHaveText(warning);
  await expect(page.getByRole('button', { name: 'Try sending now' })).toBeVisible();
  await expect(page.getByRole('button', { name: 'Sign out and lose it' })).toBeVisible();
  await page.getByRole('button', { name: 'Stay signed in' }).click();
  await expect(page.getByRole('alert')).toHaveCount(0);
  await expect(bar(page)).toContainText(waitingText(page, 1));
  expect(await phoneDatabase(page)).toBe(true);

  // Sign out and lose it: the phone database is gone, and the sign-in page shows.
  await page.getByRole('button', { name: 'Sign out', exact: true }).click();
  await page.getByRole('button', { name: 'Sign out and lose it' }).click();
  await expect(page).toHaveURL(/\/sign-in$/);
  await expect(page.getByRole('button', { name: 'Sign in' })).toBeVisible();
  expect(await phoneDatabase(page)).toBe(false);
  expect(await page.evaluate(() => localStorage.getItem('mealwright.sign-out-pending'))).toBe('1');

  // Back online: the first thing sent ends the old session on the server.
  const sent: string[] = [];
  page.on('request', (request) => {
    const url = new URL(request.url());
    if (url.pathname.startsWith('/api/')) sent.push(`${request.method()} ${url.pathname}`);
  });
  const ended = page.waitForResponse(
    (r) => r.url().endsWith('/api/v1/session') && r.request().method() === 'DELETE',
  );
  await context.setOffline(false);
  expect((await ended).status()).toBe(204);
  expect(sent[0]).toBe('DELETE /api/v1/session');
  await expect.poll(() => page.evaluate(() => localStorage.getItem('mealwright.sign-out-pending'))).toBeNull();
  expect((await page.request.get('/api/v1/me')).status()).toBe(401);
  // The tick that was lost never reached the server.
  await signIn(page);
  const items = await serverItems(page);
  expect(items.find((i) => i.food.name === name)?.ticked_at).toBeNull();
  expect(await phoneDatabase(page)).toBe(false);
});
