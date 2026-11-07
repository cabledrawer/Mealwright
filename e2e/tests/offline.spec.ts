import { test, expect, testNow, type Page } from './clock.ts';
import { isPhone } from './a11y.ts';
import { ADMIN } from './servers.ts';

// The offline queue end to end (0.3, PR 6): sync protocol section 14, E1, E2 and E3, against
// the real server and service worker, on phone and desktop. Each test signs in a session of
// its own (no saved session), because E3 signs out and that must not end anyone else's.
//
// E1 here is the same-login version (cabledrawer 18 Oct): two devices, both signed in as
// Tess. The two-person E1 (Tess and Wren) stays for 0.8, when a second login can be
// made in the app.

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
  return isPhone(page) ? `Offline — ${changes} waiting` : `${changes} waiting. They’ll save when you’re back.`;
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

/** The phone's saved copy of the list names `name` (it's written just after the screen shows it). */
const savedCopyNames = (page: Page, name: string) =>
  page.evaluate(
    (name) =>
      new Promise<boolean>((done) => {
        const open = indexedDB.open('mealwright');
        open.onerror = () => done(false);
        open.onsuccess = () => {
          const db = open.result;
          if (!db.objectStoreNames.contains('copy.foods')) return (db.close(), done(false));
          const all = db.transaction('copy.foods').objectStore('copy.foods').getAll();
          all.onerror = () => (db.close(), done(false));
          all.onsuccess = () => (db.close(), done(JSON.stringify(all.result).includes(name)));
        };
      }),
    name,
  );

/**
 * On Shopping, with the app under its worker and the live stream open. With `row`: also with
 * that row on the screen and in the phone's saved copy. Tests that then cut or slow the network
 * need that, or on a busy machine the saved copy may not hold the row yet (27 Oct: Shopping
 * then waited for the held server, 4.8 s).
 */
async function start(page: Page, row?: string) {
  await page.goto('/shopping');
  await page.evaluate(() => navigator.serviceWorker.ready.then(() => true));
  const hello = page.waitForResponse((r) => r.url().endsWith('/api/v1/events'));
  await page.reload(); // the first page load is not under the worker; this one is
  await expect(page.getByRole('heading', { name: 'Shopping', level: 1 })).toBeVisible();
  await hello;
  if (row) {
    await expect(page.getByRole('checkbox', { name: `Tick ${row}` })).toBeVisible();
    await expect.poll(() => savedCopyNames(page, row)).toBe(true);
  }
  // Kept: the app's start-up after the stream opens has no signal to wait for; the tests then cut the network.
  await page.waitForTimeout(500);
}

test('E2: changes made offline survive a reload, then reach the server', async ({ page, context }) => {
  test.skip(test.info().project.use.browserName === 'webkit', "Playwright's WebKit offline switch blocks requests before the service worker sees them (proved 25 Oct); the iPhone hand test covers offline Safari");
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
  await expect(page.getByRole('checkbox', { name: `Tick ${first}`, exact: true })).toHaveCount(0);
  await expect(page.getByRole('checkbox', { name: `Tick ${second}`, exact: true })).toHaveCount(0);
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

test('offline: a tick offers Undo at once; Undo is queued after it, and the server ends up unticked', async ({
  page,
  context,
}) => {
  const name = `Fenugreek ${tag()}`;
  await signIn(page);
  await ingredient(page, name);
  await start(page);

  await context.setOffline(true);
  await page.getByRole('checkbox', { name: `Tick ${name}` }).click();
  // No usual place yet, so the toast says it's ticked; Change and Undo are there at once.
  const toast = page.getByRole('status').filter({ hasText: `${name} ticked` });
  await expect(toast).toBeVisible();
  await expect(toast.getByRole('button', { name: 'Change' })).toBeVisible();
  await toast.getByRole('button', { name: 'Undo', exact: true }).click();
  await expect(page.getByRole('status').filter({ hasText: `Undone: ${name} ticked` })).toBeVisible();
  await expect(bar(page)).toContainText(waitingText(page, 2), { timeout: 10_000 });
  await expect(page.getByRole('checkbox', { name: `Tick ${name}` })).not.toBeChecked();

  await context.setOffline(false);
  await expect(page.getByRole('status').filter({ hasText: 'Back online — all saved' })).toBeVisible({
    timeout: 15_000,
  });
  const line = (await serverItems(page)).find((i) => i.food.name === name);
  expect(line).toBeDefined();
  expect(line?.ticked_at).toBeNull();
});

test('F63: offline, "2 l milk" in the add box joins the 1 L line, and the server agrees once back', async ({
  page,
  context,
}) => {
  test.skip(test.info().project.use.browserName === 'webkit', "Playwright's WebKit offline switch blocks requests before the service worker sees them (proved 25 Oct); the iPhone hand test covers offline Safari");
  const name = `Kefir ${tag()}`;
  await signIn(page);
  const { food } = await call(page, 'POST', '/foods', { name, counted_as: 'volume' });
  await call(page, 'POST', `/shopping/lists/${await mainList(page)}/items`, {
    food_id: food.id,
    amount: { amount: 1000, unit: 'ml' },
  });
  await start(page, name);

  await context.setOffline(true);
  await page.getByRole('textbox', { name: 'Add an item' }).fill(`2 l ${name}`);
  await page.getByRole('list', { name: 'Matching ingredients' }).getByRole('button', { name }).click();
  // One line, now 3 L: the typed 2 L joined the 1 L line, on the phone alone.
  await expect(page.getByRole('button', { name: new RegExp(`^Change amount: ${name}, 3`) })).toBeVisible();
  await expect(page.getByRole('button', { name, exact: true })).toHaveCount(1);
  await expect(bar(page)).toContainText(waitingText(page, 1), { timeout: 10_000 });

  await context.setOffline(false);
  await expect(page.getByRole('status').filter({ hasText: 'Back online — all saved' })).toBeVisible({
    timeout: 15_000,
  });
  const lines = (await serverItems(page)).filter((i) => i.food.name === name);
  expect(lines).toHaveLength(1);
  expect((lines[0] as unknown as { amount: { amount: number } }).amount.amount).toBe(3000);
});

test('F130: offline, a new item name asks Pantry keeps it by, adds at once, and the ingredient is made once when the server is back', async ({
  page,
  context,
}) => {
  test.skip(test.info().project.use.browserName === 'webkit', "Playwright's WebKit offline switch blocks requests before the service worker sees them (proved 25 Oct); the iPhone hand test covers offline Safari");
  const name = `Curry leaves ${tag()}`;
  await signIn(page);
  await start(page);

  await context.setOffline(true);
  await page.getByRole('textbox', { name: 'Add an item' }).fill(name);
  await page.getByRole('button', { name: `+ New ingredient: “${name}”` }).click();
  const dialog = page.getByRole('dialog', { name: 'Pantry keeps it by' });
  await expect(dialog).toBeVisible();
  await dialog.getByRole('radio', { name: /One by one/ }).click();
  await expect(dialog.getByRole('button', { name: 'Add', exact: true })).toBeEnabled();
  await dialog.getByRole('button', { name: 'Add', exact: true }).click();
  await expect(dialog).toBeHidden();
  await expect(page.getByRole('button', { name, exact: true })).toBeVisible();
  await expect(bar(page)).toContainText(waitingText(page, 1), { timeout: 10_000 });

  await context.setOffline(false);
  await expect(page.getByRole('status').filter({ hasText: 'Back online — all saved' })).toBeVisible({
    timeout: 15_000,
  });
  expect((await serverItems(page)).filter((i) => i.food.name === name)).toHaveLength(1);
  const { foods } = await (await page.request.get(`/api/v1/foods?q=${encodeURIComponent(name)}`)).json();
  expect(foods.filter((f: { name: string; counted_as: string }) => f.name === name)).toHaveLength(1);
  expect(foods.find((f: { name: string }) => f.name === name).counted_as).toBe('count');
});

test('F62: offline, ticking a line with no amount still asks How much?, and the answer is a second queued change', async ({
  page,
  context,
}) => {
  test.skip(test.info().project.use.browserName === 'webkit', "Playwright's WebKit offline switch blocks requests before the service worker sees them (proved 25 Oct); the iPhone hand test covers offline Safari");
  const name = `Nutmeg ${tag()}`;
  await signIn(page);
  const { food } = await call(page, 'POST', '/foods', { name, counted_as: 'weight' });
  await call(page, 'POST', `/shopping/lists/${await mainList(page)}/items`, { food_id: food.id });
  await start(page, name);

  await context.setOffline(true);
  await page.getByRole('checkbox', { name: `Tick ${name}` }).click();
  const row = page.getByRole('listitem').filter({ hasText: name });
  await expect(row.getByText('How much?')).toBeVisible();
  // The phone doesn't know this ingredient's sizes: the ready-made choices and Other… are there.
  await row.getByRole('radio', { name: '500 g' }).click();
  await row.getByRole('button', { name: 'Done' }).click();
  await expect(bar(page)).toContainText(waitingText(page, 2), { timeout: 10_000 });

  await context.setOffline(false);
  await expect(page.getByRole('status').filter({ hasText: 'Back online — all saved' })).toBeVisible({
    timeout: 15_000,
  });
  const line = (await serverItems(page)).find((i) => i.food.name === name);
  expect(line?.ticked_at).not.toBeNull();
  // The answer reached the pantry too: 500 g of it.
  await expect.poll(async () => (await pantryStock(page, food.id)).map(([grams]) => grams)).toEqual([500]);
});

test('E3: signing out offline warns first, then wipes, and the session ends once back', async ({
  page,
  context,
}) => {
  test.skip(test.info().project.use.browserName === 'webkit', "Playwright's WebKit offline switch blocks requests before the service worker sees them (proved 25 Oct); the iPhone hand test covers offline Safari");
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
  const warning = "1 change hasn’t been sent yet. If you sign out now, it’s lost.";
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

test('other tabs: signing out in one tab clears every other tab and takes it to sign in', async ({
  page,
  context,
}) => {
  const name = `Ajwain ${tag()}`;
  await signIn(page);
  await ingredient(page, name);
  await start(page);
  const other = await context.newPage();
  await start(other);
  await expect(other.getByRole('checkbox', { name: `Tick ${name}` })).toBeVisible();

  await page.getByRole('link', { name: 'Settings' }).first().click();
  await expect(page.getByRole('heading', { name: 'Settings', level: 1 })).toBeVisible();
  await page.getByRole('button', { name: 'Sign out', exact: true }).click();
  await expect(page).toHaveURL(/\/sign-in$/);

  // The other tab cleared itself and went to sign in, without being touched.
  await expect(other).toHaveURL(/\/sign-in$/);
  await expect(other.getByRole('button', { name: 'Sign in' })).toBeVisible();
  await expect(other.getByText(name)).toHaveCount(0);
  await expect(other.getByRole('heading', { name: 'Shopping' })).toHaveCount(0);
  // And it didn't make the phone database again.
  // Kept: proves the phone database is NOT made, so there is no state to wait for.
  await other.waitForTimeout(1500);
  expect(await phoneDatabase(other)).toBe(false);
  expect(await phoneDatabase(page)).toBe(false);
  await other.close();
});

/** Toor dal by weight with a 500 g packet, 1 packet on the main list. Its ID. */
async function toorDal(page: Page, name: string): Promise<number> {
  const { food } = await call(page, 'POST', '/foods', { name, counted_as: 'weight' });
  await call(page, 'POST', `/foods/${food.id}/sizes`, { name: 'packet', amount: 500 });
  await call(page, 'POST', `/shopping/lists/${await mainList(page)}/items`, {
    food_id: food.id,
    amount: { amount: 1, unit: 'packet' },
  });
  return food.id;
}

/** The ingredient's stock in the pantry, one entry per place: [grams, as shown]. */
async function pantryStock(page: Page, foodId: number): Promise<[number, string][]> {
  const pantry = await (await page.request.get('/api/v1/pantry')).json();
  const out: [number, string][] = [];
  for (const p of pantry.places)
    for (const g of p.groups)
      if (g.food.id === foodId) out.push([g.stock.amount, g.stock.short.replace(/\s+/g, ' ')]);
  return out;
}

/** Answer "Yes, 2" to any "Did you buy 2?" other tests left open, as another device of this login. */
async function settleCards(page: Page) {
  const me = await (await page.request.get('/api/v1/me')).json();
  const copy = await (await page.request.get('/api/v1/shopping/changes?since=0')).json();
  for (const q of copy.questions.filter((x: { open: boolean }) => x.open)) {
    const answered = await page.request.post('/api/v1/shopping/actions', {
      data: {
        protocol: 1,
        device_id: crypto.randomUUID(),
        login_id: me.id,
        since: 0,
        sent_at: new Date().toISOString(),
        actions: [
          {
            id: crypto.randomUUID(),
            made_at: new Date().toISOString(),
            seen: 0,
            kind: 'answer_double_tick',
            question_id: q.id,
            answer: 'two',
          },
        ],
      },
    });
    expect(answered.ok(), await answered.text()).toBe(true);
  }
}

// E1 for 0.3 (cabledrawer 18 Oct): two devices, both signed in as Tess. Both offline, both
// tick toor dal; back online, both ask "Did you buy 2?"; Just 1 on one clears the other.
// Nothing seeded: the ingredient is made through the API, the ticks through the app. The
// two-person E1 (Tess and Wren) waits for 0.8, when a second login can be made in the app.
test('E1 (same login): toor dal ticked offline on two devices; "Did you buy 2?"; Just 1 clears both', async ({
  page,
  context,
  browser,
}) => {
  const name = `Toor dal ${tag()}`;
  await signIn(page);
  await settleCards(page); // so the only card is this test's
  const foodId = await toorDal(page, name);
  const otherContext = await browser.newContext();
  await otherContext.clock.install({ time: testNow() });
  const other = await otherContext.newPage();
  try {
    await signIn(other);
    await start(page);
    await start(other);

    await context.setOffline(true);
    await otherContext.setOffline(true);
    await page.getByRole('checkbox', { name: `Tick ${name}` }).click();
    await other.getByRole('checkbox', { name: `Tick ${name}` }).click();
    await expect(bar(page)).toContainText(waitingText(page, 1), { timeout: 10_000 });
    await expect(bar(other)).toContainText(waitingText(other, 1), { timeout: 10_000 });

    // Back online one after the other: the second tick finds the line already ticked.
    await context.setOffline(false);
    await expect(bar(page)).toBeHidden({ timeout: 15_000 });
    await otherContext.setOffline(false);
    await expect(bar(other)).toBeHidden({ timeout: 15_000 });

    // Both ticks were Tess's, so the card doesn't name anyone.
    const card = (p: Page) => p.getByRole('region', { name: 'Did you buy 2?' });
    const text = 'This was ticked on two phones, so 2 packets went into the pantry.';
    for (const p of [page, other]) {
      await expect(card(p)).toBeVisible({ timeout: 15_000 });
      await expect(card(p)).toContainText(text);
      await expect(card(p).getByRole('button', { name: 'Yes, 2' })).toBeVisible();
    }
    await expect.poll(() => pantryStock(page, foodId)).toEqual([[1000, '2 packets']]);

    // Just 1 on one device: the other's card goes within 5 seconds, and the pantry has 1.
    await other.getByRole('region', { name: 'Did you buy 2?' }).getByRole('button', { name: 'Just 1' }).click();
    await expect(card(other)).toHaveCount(0);
    await expect(card(page)).toHaveCount(0, { timeout: 5_000 });
    await expect.poll(() => pantryStock(page, foodId)).toEqual([[500, '1 packet']]);
  } finally {
    await otherContext.close();
  }
});

// Opening on no signal, or one so weak requests hang (cabledrawer 20 Oct, hand test: the app was
// blank for 30–40 s, then Shopping said "Loading…" for 42 s; the saved copy shows at once).
// "About a second" is allowed 1.5 s here, for a busy test machine (the builder's choice,
// proposed, for cabledrawer); measured, it is under 0.1 s offline and about 0.8 s with every
// request hanging (the start waits half a second for the server). The offline test also
// passed before the fix, as Playwright's offline fails requests at once: it guards against
// going back. The hanging test is the one that shows the fix.
const ABOUT_A_SECOND = 1500;

/** Open the app at Today, then tap Shopping: how long each took to show. */
async function openToday(page: Page, row: string) {
  const today = page.getByRole('heading', { name: 'Today', level: 1 });
  const opened = Date.now();
  await page.goto('/', { waitUntil: 'commit' });
  await today.waitFor({ timeout: 60_000 });
  const todayMs = Date.now() - opened;
  const tapped = Date.now();
  await page
    .getByRole('navigation')
    .last()
    .getByRole('link', { name: isPhone(page) ? 'Shop' : 'Shopping' })
    .click();
  await page.getByRole('checkbox', { name: `Tick ${row}` }).waitFor({ timeout: 60_000 });
  return { todayMs, listMs: Date.now() - tapped };
}

test('opening offline shows Today, then the saved list, each within about a second', async ({ page, context }) => {
  test.skip(test.info().project.use.browserName === 'webkit', "Playwright's WebKit offline switch blocks requests before the service worker sees them (proved 25 Oct); the iPhone hand test covers offline Safari");
  const first = `Ghee ${tag()}`;
  await signIn(page);
  await ingredient(page, first);
  await start(page, first);
  await context.setOffline(true);
  const { todayMs, listMs } = await openToday(page, first);
  expect(todayMs).toBeLessThan(ABOUT_A_SECOND);
  expect(listMs).toBeLessThan(ABOUT_A_SECOND);
  await expect(page.getByText('Loading…')).toHaveCount(0);
  await context.setOffline(false);
});

test('a slow network doesn’t hold the saved list back, and the list updates when the answers come', async ({ page }) => {
  test.skip(test.info().project.use.browserName === 'webkit', "Playwright's WebKit page.route doesn't see a page's requests once the service worker controls it (measured 25 Oct); the iPhone hand test covers Safari");
  test.setTimeout(90_000);
  const t = tag();
  const [first, second] = [`Ghee ${t}`, `Jaggery ${t}`];
  await signIn(page);
  await ingredient(page, first);
  await start(page, first);
  // Every request to the server is held for 5 s (page.request below isn't): long enough to
  // show the list isn't waiting for it.
  let release!: () => void;
  const released = new Promise<void>((done) => (release = done));
  await page.route(/\/api\//, async (route) => {
    await released;
    await route.continue().catch(() => undefined);
  });
  let releasedAt = 0;
  const holding = setTimeout(() => {
    releasedAt = Date.now();
    release();
  }, 5_000);
  try {
    const { todayMs, listMs } = await openToday(page, first);
    expect(todayMs).toBeLessThan(ABOUT_A_SECOND);
    expect(listMs).toBeLessThan(ABOUT_A_SECOND);
    await expect(page.getByText('Loading…')).toHaveCount(0);
    // Added on another device meanwhile: it shows once the held answers arrive.
    await ingredient(page, second);
    await expect(page.getByRole('checkbox', { name: `Tick ${second}` })).toBeVisible({ timeout: 60_000 });
    expect(releasedAt).toBeGreaterThan(0);
    await expect(page.getByRole('checkbox', { name: `Tick ${first}` })).toBeVisible();
  } finally {
    clearTimeout(holding);
    release();
    await page.unrouteAll({ behavior: 'ignoreErrors' });
  }
});

// --- Shopping on the phone, "in the shop" (0.8, S4): Add as bought and Already have it ---------

/** An ingredient bought in 500 g packets, not on the list. */
async function packetFood(page: Page, name: string): Promise<number> {
  const { food } = await call(page, 'POST', '/foods', { name, counted_as: 'weight' });
  await call(page, 'POST', `/foods/${food.id}/sizes`, { name: 'packet', amount: 500 });
  return food.id;
}

/** The newest pantry change that names this ingredient. */
async function pantryChanges(page: Page, name: string): Promise<{ kind: string; summary: string }[]> {
  const { changes } = await (await page.request.get('/api/v1/changes?area=pantry&limit=100')).json();
  return changes.filter((c: { summary: string }) => c.summary.includes(name));
}

/** Already have it, from the amount box (a swipe does the same on a phone): the half packet. */
async function haveHalf(page: Page, name: string) {
  await page.getByRole('button', { name, exact: true }).click();
  await page.getByRole('button', { name: 'Already have it' }).click();
  const sheet = page.getByRole('dialog', { name: `Already have ${name}` });
  await sheet.getByRole('radio', { name: /^250/ }).click();
  await sheet.getByRole('button', { name: /^Put 250.g in the pantry$/ }).click();
  await expect(sheet).toBeHidden();
}

test('S4: Add as bought offline is an add and a tick in the queue; the pantry has it once back', async ({ page, context }) => {
  const name = `Jaggery ${tag()}`;
  await signIn(page);
  const foodId = await packetFood(page, name);
  await start(page);

  await context.setOffline(true);
  await page.getByRole('textbox', { name: 'Add an item' }).fill(name);
  await page.getByRole('button', { name: 'Add as bought' }).click();
  await expect(bar(page)).toContainText(waitingText(page, 2), { timeout: 10_000 });

  await context.setOffline(false);
  await expect(page.getByRole('status').filter({ hasText: 'Back online — all saved' })).toBeVisible({ timeout: 15_000 });
  const line = (await serverItems(page)).filter((i) => i.food.name === name);
  expect(line).toHaveLength(1);
  expect(line[0]!.ticked_at).not.toBeNull();
  await expect.poll(() => pantryStock(page, foodId)).toEqual([[500, '1 packet']]);
  expect((await pantryChanges(page, name))[0]!.summary).toMatch(/^Bought 1.packet /);
});

test('S4: Already have it offline: the amount at home is queued, and the pantry has it as found, not bought, once back', async ({ page, context }) => {
  const name = `Ghee ${tag()}`;
  await signIn(page);
  await ingredient(page, name);
  const foodId = (await (await page.request.get(`/api/v1/foods?q=${encodeURIComponent(name)}`)).json()).foods[0].id;
  await start(page, name);

  await context.setOffline(true);
  await haveHalf(page, name);
  await expect(bar(page)).toContainText(waitingText(page, 1), { timeout: 10_000 });
  // Shown as found, in the trolley, at once.
  await page.getByRole('button', { name: /^In the trolley/ }).first().click();
  await expect(page.getByText('250 g · found at home')).toBeVisible();

  await context.setOffline(false);
  await expect(page.getByRole('status').filter({ hasText: 'Back online — all saved' })).toBeVisible({ timeout: 15_000 });
  await expect.poll(() => pantryStock(page, foodId)).toEqual([[250, '250 g']]);
  const [newest] = await pantryChanges(page, name);
  expect(newest!.kind).toBe('found');
  expect(newest!.summary).toMatch(new RegExp(`^Found ${name} at home: 250.g → `));
  expect((await pantryChanges(page, name)).filter((c) => c.kind === 'shopped')).toEqual([]);
});

test('S4: Already have it sent twice (the answer was lost) puts the amount in once', async ({ page }) => {
  const name = `Hing ${tag()}`;
  await signIn(page);
  await ingredient(page, name);
  const foodId = (await (await page.request.get(`/api/v1/foods?q=${encodeURIComponent(name)}`)).json()).foods[0].id;
  await start(page, name);

  // The server gets the first send and the phone never hears back, so it sends the same action
  // again: the server answers it from its record, and applies nothing twice.
  let sends = 0;
  await page.route('**/api/v1/shopping/actions', async (route) => {
    sends += 1;
    if (sends === 1) {
      await route.fetch();
      await route.abort('failed');
    } else {
      await route.continue();
    }
  });
  await haveHalf(page, name);
  await expect.poll(() => sends, { timeout: 30_000 }).toBeGreaterThanOrEqual(2);
  await expect(bar(page)).toBeHidden({ timeout: 30_000 });
  await expect.poll(() => pantryStock(page, foodId)).toEqual([[250, '250 g']]);
  expect((await pantryChanges(page, name)).filter((c) => c.kind === 'found')).toHaveLength(1);
});

test('S4: Already have it on two phones: both amounts go in, no "Did you buy 2?", one line in the trolley', async ({ page, context, browser }) => {
  const name = `Jeera ${tag()}`;
  await signIn(page);
  await settleCards(page);
  await ingredient(page, name);
  const foodId = (await (await page.request.get(`/api/v1/foods?q=${encodeURIComponent(name)}`)).json()).foods[0].id;
  const otherContext = await browser.newContext();
  await otherContext.clock.install({ time: testNow() });
  const other = await otherContext.newPage();
  try {
    await signIn(other);
    await start(page, name);
    await start(other, name);
    await context.setOffline(true);
    await otherContext.setOffline(true);
    await haveHalf(page, name);
    await haveHalf(other, name);
    await expect(bar(page)).toContainText(waitingText(page, 1), { timeout: 10_000 });
    await expect(bar(other)).toContainText(waitingText(other, 1), { timeout: 10_000 });

    await context.setOffline(false);
    await expect(bar(page)).toBeHidden({ timeout: 15_000 });
    await otherContext.setOffline(false);
    await expect(bar(other)).toBeHidden({ timeout: 15_000 });

    await expect.poll(() => pantryStock(page, foodId)).toEqual([[500, '500 g']]);
    expect((await pantryChanges(page, name)).filter((c) => c.kind === 'found')).toHaveLength(2);
    for (const p of [page, other]) {
      await expect(p.getByRole('region', { name: 'Did you buy 2?' })).toHaveCount(0);
    }
    const mine = (await serverItems(page)).filter((i) => i.food.name === name);
    expect(mine).toHaveLength(1);
    expect(mine[0]!.ticked_at).not.toBeNull();
  } finally {
    await otherContext.close();
  }
});

// --- F130 (PR 128 review L1, L2): a new name offline, with an amount, and on two phones --------

test('F130: offline, "500 g" and a new name: the add keeps the amount, and the ingredient is made once when the server is back', async ({ page, context }) => {
  const name = `Paneer ${tag()}`;
  await signIn(page);
  await start(page);

  await context.setOffline(true);
  await page.getByRole('textbox', { name: 'Add an item' }).fill(`500 g ${name}`);
  await page.getByRole('button', { name: `+ New ingredient: “${name}”` }).click();
  const dialog = page.getByRole('dialog', { name: 'Pantry keeps it by' });
  await expect(dialog).toBeVisible();
  await dialog.getByRole('button', { name: 'Add', exact: true }).click();
  await expect(dialog).toBeHidden();
  await expect(page.getByRole('button', { name: new RegExp(`^Change amount: ${name}, 500`) })).toBeVisible();
  await expect(bar(page)).toContainText(waitingText(page, 1), { timeout: 10_000 });

  await context.setOffline(false);
  await expect(page.getByRole('status').filter({ hasText: 'Back online — all saved' })).toBeVisible({ timeout: 15_000 });
  const lines = (await serverItems(page)).filter((i) => i.food.name === name);
  expect(lines).toHaveLength(1);
  expect((lines[0] as unknown as { amount: { amount: number } }).amount.amount).toBe(500);
  const { foods } = await (await page.request.get(`/api/v1/foods?q=${encodeURIComponent(name)}`)).json();
  expect(foods.filter((f: { name: string }) => f.name === name)).toHaveLength(1);
});

test('F130: the same new name added offline on two phones ends up as one ingredient', async ({ page, context, browser }) => {
  const name = `Kokum ${tag()}`;
  await signIn(page);
  const otherContext = await browser.newContext();
  await otherContext.clock.install({ time: testNow() });
  const other = await otherContext.newPage();
  try {
    await signIn(other);
    await start(page);
    await start(other);
    await context.setOffline(true);
    await otherContext.setOffline(true);
    for (const p of [page, other]) {
      await p.getByRole('textbox', { name: 'Add an item' }).fill(name);
      await p.getByRole('button', { name: `+ New ingredient: “${name}”` }).click();
      const dialog = p.getByRole('dialog', { name: 'Pantry keeps it by' });
      await dialog.getByRole('radio', { name: /One by one/ }).click();
      await dialog.getByRole('button', { name: 'Add', exact: true }).click();
      await expect(dialog).toBeHidden();
      await expect(bar(p)).toContainText(waitingText(p, 1), { timeout: 10_000 });
    }
    await context.setOffline(false);
    await expect(bar(page)).toBeHidden({ timeout: 15_000 });
    await otherContext.setOffline(false);
    await expect(bar(other)).toBeHidden({ timeout: 15_000 });

    const { foods } = await (await page.request.get(`/api/v1/foods?q=${encodeURIComponent(name)}`)).json();
    expect(foods.filter((f: { name: string }) => f.name === name)).toHaveLength(1);
    // One line on the list: the second add joined the first (they are the same ingredient).
    expect((await serverItems(page)).filter((i) => i.food.name === name)).toHaveLength(1);
  } finally {
    await otherContext.close();
  }
});
