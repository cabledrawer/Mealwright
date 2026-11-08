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
    // Kept: the real-time run waits real seconds on purpose (the other run moves the page's clock).
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

// B3 L4 (cabledrawer 30 Oct: "The Try now timing case: fix in PC2"): the server comes back while a
// check that began during the outage is still waiting for an answer. Try now must ask afresh;
// before, it joined the old check and its failure said the server was still down.
test('Try now while an older check is still waiting does not say the server is down when it is back', async ({ page }) => {
  await page.goto('/recipes/ingredients');
  await expect(page.getByRole('heading', { level: 1 })).toBeVisible();
  await page.waitForLoadState('networkidle');

  await page.route('**/api/**', proxyGap);
  // Checks of the server's version never get an answer: the one under way stays waiting.
  const held: Route[] = [];
  await page.route('**/api/v1/version', (route) => {
    held.push(route);
  });
  await page.reload();
  // The page's time moves on until the bar is up and a check is waiting.
  await expect(async () => {
    await page.clock.runFor(1000);
    expect(held.length).toBeGreaterThan(0);
    await expect(bar(page)).toBeVisible({ timeout: 500 });
  }).toPass({ timeout: 20_000 });
  const waiting = held.length;

  // The server is back (checks of its version now reach it); Try now is pressed while the old
  // check is still waiting. Everything else stays down until the end, so nothing else clears the bar.
  await page.unroute('**/api/v1/version');
  await page.route('**/api/v1/version', (route) => route.continue());
  await bar(page).getByRole('button', { name: /Try now/ }).click();
  await expect(bar(page)).toBeHidden();
  await expect(backOnline(page)).toBeVisible();
  await page.unroute('**/api/v1/version');
  await page.unroute('**/api/**', proxyGap);

  // The old check, when its time is up, changes nothing; no new "down" either.
  for (let n = 0; n < 10; n++) await page.clock.runFor(1000);
  expect(held.length).toBe(waiting);
  await expect(bar(page)).toBeHidden();
});

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

  // The one steady message is the bar; the open recipe stays where it was (cabledrawer 31 Oct: the list beside it may show the note).
  await expect(bar(page)).toBeVisible();
  await expect(reading.getByRole('heading', { level: 1, name })).toBeVisible();
  await expect(page.getByRole('heading', { name: 'Can’t reach your Mealwright server.' })).toHaveCount(0);
}

test('a recipe already open stays when the server stops', async ({ page }) => {
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

// F86 (0.7 alpha 1 hand test, cabledrawer 30 Oct): when a page's code can't be fetched (the server
// down, the page not saved on this device), the app showed a bare "500 Internal Error": no menu
// and no "Can't reach" note. It now shows the note inside the normal frame, with the menu.
test("a page whose code can't be fetched shows the Can't reach note with the menu, never a 500", async ({
  page,
}) => {
  await page.goto('/shopping');
  await expect(page.getByRole('heading', { level: 1 })).toBeVisible();
  await page.waitForLoadState('networkidle');

  // Nothing of any page that hasn't been opened yet can be fetched; the API answers 502.
  await page.route('**/_app/immutable/nodes/*', (route) => route.abort('failed'));
  await page.route('**/api/**', proxyGap);
  await page.getByRole('link', { name: 'Settings' }).first().click();

  await expect(page.getByRole('heading', { name: 'Can’t reach your Mealwright server.' })).toBeVisible();
  await expect(page.getByText(/500|Internal Error/)).toHaveCount(0);
  // The normal frame: the menu is still there (the sidebar on a computer, the tabs on a phone).
  await expect(page.getByRole('navigation').first()).toBeVisible();
  await expect(page.getByRole('link', { name: 'Shopping' }).first()).toBeVisible();
  // The first words are the right ones (no "Something went wrong." that changes later).
  await expect(page.getByText('Something went wrong.')).toHaveCount(0);

  // Try again while the server is still down keeps the note and the menu: it never reloads
  // onto the proxy's bare page.
  await page.getByRole('button', { name: 'Try again' }).click();
  await expect(page.getByRole('button', { name: 'Try again' })).toBeEnabled();
  await expect(page.getByRole('heading', { name: 'Can’t reach your Mealwright server.' })).toBeVisible();
  await expect(page.getByRole('link', { name: 'Shopping' }).first()).toBeVisible();
});

// F80 on Settings (cabledrawer 31 Oct: Recipes, Ingredients and Pantry may show the note instead): once
// loaded, the screen stays when the server stops, and what needs the server is greyed out.
for (const screen of [
  { name: 'Settings', path: '/settings', shows: /Appearance/ },
] as const) {
  test(`${screen.name} already showing stays when the server stops`, async ({ page }) => {
    await page.goto(screen.path);
    await expect(page.getByRole('heading', { level: 1 })).toBeVisible();
    await page.waitForLoadState('networkidle');
    await page.route('**/api/**', proxyGap);
    await page.evaluate(() => window.dispatchEvent(new Event('online')));
    for (let n = 0; n < 12; n++) await page.clock.runFor(1000);
    await expect(bar(page)).toBeVisible();
    await expect(page.getByRole('heading', { name: 'Can’t reach your Mealwright server.' })).toHaveCount(0);
    await expect(page.getByRole('heading', { level: 1 })).toBeVisible();
    if (screen.name === 'Settings') {
      await expect(page.getByRole('heading', { name: 'Appearance' })).toBeVisible();
      await expect(page.getByRole('switch', { name: /pints/i })).toBeDisabled();
    }
  });
}

// F80 (review): the list is loaded, the server goes down, and a recipe that never loaded is
// clicked: the reading pane says why instead of staying blank.
test('three panes: a recipe that never loaded says why the server is down, not a blank pane', async ({ page }) => {
  test.skip(isPhone(page), 'The list and the recipe are beside each other on a computer only.');
  const name = `Idli ${Date.now().toString(36)}`;
  const made = await page.request.fetch('/api/v1/recipes', {
    method: 'POST',
    data: { name, serves: 2, lines: [{ words: 'rice', amount: 200, unit: 'g' }] },
    headers: { 'idempotency-key': crypto.randomUUID() },
  });
  expect(made.status()).toBe(201);
  const id = ((await made.json()) as { id: number }).id;
  await page.goto('/recipes');
  const list = page.getByRole('region', { name: 'Recipe list' });
  // Search for it, so other tests' recipes can't push it off the list's first page.
  await page.getByRole('searchbox', { name: 'Search recipes' }).fill(name);
  await expect(list.getByRole('link', { name })).toBeVisible();
  await page.waitForLoadState('networkidle');
  await page.route(new RegExp(`/api/v1/recipes/${id}(/|\\?|$)`), proxyGap);
  await list.getByRole('link', { name }).click();
  const reading = page.getByRole('region', { name: 'Recipe', exact: true });
  await expect(reading.getByRole('heading', { name: 'Can’t reach your Mealwright server.' })).toBeVisible();
  // The list beside it stays.
  await expect(list.getByRole('link', { name })).toBeVisible();
});

const apiKey = () => ({ 'idempotency-key': crypto.randomUUID() });
async function post(page: Page, path: string, data: object) {
  const response = await page.request.fetch(`/api/v1${path}`, { method: 'POST', data, headers: apiKey() });
  expect(response.ok(), `${path}: ${await response.text()}`).toBe(true);
  return response.json();
}

// F80 review round 2: nothing that writes to the server is live while it is down.
// cabledrawer 31 Oct: the Pantry may show the "Can't reach" note instead of its list; whatever stays is greyed out.
test('Pantry: when the server stops, the packet menu, Edit link and Undo of an opened row are greyed out or gone', async ({ page }) => {
  const places = (await (await page.request.get('/api/v1/places')).json()) as { id: number; name: string }[];
  const name = `Dal ${test.info().project.name.replace(/\W/g, '')} ${Date.now()}`;
  const { food } = await post(page, '/foods', { name, place_id: places[0]!.id });
  await post(page, `/foods/${food.id}/sizes`, { name: 'pack', amount: 200 });
  await post(page, '/stock', { food_id: food.id, amount: { amount: 1, unit: 'pack' }, place_id: places[0]!.id });
  await page.goto('/pantry');
  await page.getByRole('searchbox', { name: isPhone(page) ? 'Search pantry' : 'Find in pantry' }).fill(name);
  await expect(page.getByRole('list', { name: 'Found in the pantry' })).toBeVisible();
  await page.getByRole('button', { name: new RegExp(`^${name}`) }).first().click();
  const lot = page.getByRole('list', { name: `Packets of ${name}` }).getByRole('button');
  await expect(lot.first()).toBeEnabled();
  await page.waitForLoadState('networkidle');

  await page.route('**/api/**', proxyGap);
  await page.evaluate(() => window.dispatchEvent(new Event('online')));
  for (let n = 0; n < 12; n++) await page.clock.runFor(1000);
  await expect(bar(page)).toBeVisible();
  for (const button of await lot.all()) await expect(button).toBeDisabled();
  for (const edit of await page.getByRole('button', { name: `Edit ${name}` }).all()) await expect(edit).toBeDisabled();
  for (const undo of await page.getByRole('button', { name: /^Undo: / }).all()) await expect(undo).toBeDisabled();
});

test('Ingredients: while the server is down the open editor is greyed out or gone, a row click says so, and Undo sends nothing', async ({
  page,
}) => {
  test.skip(isPhone(page), 'Computer layout');
  const name = `Rice ${Date.now()}`;
  await post(page, '/foods', { name, counted_as: 'weight' });
  await page.goto('/recipes/ingredients');
  await expect(page.getByRole('heading', { level: 1 })).toBeVisible();
  await page.getByRole('searchbox', { name: 'Search ingredients' }).fill(name);
  await page.locator('button.row', { hasText: name }).click();
  // Rename while the server is up: a toast with Undo.
  await page.getByRole('button', { name: 'Rename' }).click();
  await page.getByRole('textbox', { name: 'Name' }).fill(`${name} basmati`);
  await page.getByRole('textbox', { name: 'Name' }).press('Enter');
  const undo = page.getByRole('status').getByRole('button', { name: 'Undo' });
  await expect(undo).toBeVisible();
  await page.waitForLoadState('networkidle');

  const sent: string[] = [];
  page.on('request', (r) => {
    if (r.method() !== 'GET' && r.url().includes('/api/')) sent.push(`${r.method()} ${r.url()}`);
  });
  await page.route('**/api/**', proxyGap);
  await page.evaluate(() => window.dispatchEvent(new Event('online')));
  for (let n = 0; n < 12; n++) await page.clock.runFor(1000);
  await expect(bar(page)).toBeVisible();
  // The editor's changes are greyed out or gone (cabledrawer 31 Oct: the list may give way to the note).
  for (const rename of await page.getByRole('button', { name: 'Rename' }).all()) await expect(rename).toBeDisabled();
  for (const merge of await page.getByRole('button', { name: 'Merge with another…' }).all()) await expect(merge).toBeDisabled();
  // The toast's Undo needs the server: it says so and sends nothing.
  const before = sent.length;
  if (await undo.isVisible()) await undo.click();
  else await page.keyboard.press('Control+z');
  await expect(page.getByText('Can’t reach your Mealwright server. Check your connection.').last()).toBeVisible();
  expect(sent.slice(before)).toEqual([]);
  // A row click, if the list is still there, says so too.
  const row = page.locator('button.row').first();
  if (await row.isVisible()) {
    await row.click();
    await expect(page.getByText('Can’t reach your Mealwright server. Check your connection.').last()).toBeVisible();
  }
});

test('Pantry: "+ Add to pantry" says why while the server is down', async ({ page }) => {
  await page.goto('/pantry');
  await expect(page.getByRole('heading', { name: 'Pantry', level: 1 })).toBeVisible();
  await page.waitForLoadState('networkidle');
  await page.route('**/api/**', proxyGap);
  await page.evaluate(() => window.dispatchEvent(new Event('online')));
  for (let n = 0; n < 12; n++) await page.clock.runFor(1000);
  await expect(bar(page)).toBeVisible();
  await page.getByRole('button', { name: /Add to pantry/ }).first().click();
  await expect(page.getByText('Can’t reach your Mealwright server. Try again when it’s back.').last()).toBeVisible();
  await expect(page.getByRole('dialog', { name: 'Add to pantry' })).toHaveCount(0);
});

test('Import: while the server is down the box says it can’t reach the server, in the server-down words', async ({ page }) => {
  await page.goto('/recipes/import');
  await expect(page.getByRole('heading', { level: 1 })).toBeVisible();
  await page.getByRole('textbox').first().fill('https://bananaleaf.example/sambar/');
  await page.waitForLoadState('networkidle');
  await page.route('**/api/**', proxyGap);
  await page.evaluate(() => window.dispatchEvent(new Event('online')));
  for (let n = 0; n < 12; n++) await page.clock.runFor(1000);
  await expect(bar(page)).toBeVisible();
  await expect(page.getByRole('status').filter({ hasText: 'Can’t reach your Mealwright server. Try again when it’s back.' })).toBeVisible();
  await expect(page.getByText(/back online/)).toHaveCount(0);
  await expect(page.getByRole('button', { name: 'Read the recipe' })).toBeDisabled();
});

test('Shopping: a tick’s Undo still works while the server is down (it is queued)', async ({ page }) => {
  const name = `Lentils ${Date.now()}`;
  const { food } = await post(page, '/foods', { name, counted_as: 'weight' });
  const { lists } = await (await page.request.get('/api/v1/shopping/lists')).json();
  const main = lists.find((l: { main: boolean }) => l.main).id;
  await post(page, `/shopping/lists/${main}/items`, { food_id: food.id, amount: { amount: 300, unit: 'g' } });
  await page.goto('/shopping');
  await expect(page.getByRole('checkbox', { name: `Tick ${name}` })).toBeVisible();
  await page.waitForLoadState('networkidle');
  await page.route('**/api/**', proxyGap);
  await page.evaluate(() => window.dispatchEvent(new Event('online')));
  for (let n = 0; n < 12; n++) await page.clock.runFor(1000);
  await expect(bar(page)).toBeVisible();
  await page.getByRole('checkbox', { name: `Tick ${name}` }).click();
  await expect(page.getByRole('checkbox', { name: `Tick ${name}` })).toHaveCount(0);
  await page.getByRole('status').getByRole('button', { name: 'Undo' }).click();
  await expect(page.getByRole('checkbox', { name: `Tick ${name}` })).toBeVisible();
});

/** The server stops (every call answers 502) and the bar shows. */
async function serverStops(page: Page) {
  await page.waitForLoadState('networkidle');
  await page.route('**/api/**', proxyGap);
  await page.evaluate(() => window.dispatchEvent(new Event('online')));
  for (let n = 0; n < 12; n++) await page.clock.runFor(1000);
  await expect(bar(page)).toBeVisible();
}

const CANT_REACH = 'Can’t reach your Mealwright server. Check your connection.';

// Things already open when the server drops (A2 last round): the guard under the greyed buttons.
test('Pantry: a packet menu already open when the server stops sends nothing when Used is tapped', async ({ page }) => {
  const places = (await (await page.request.get('/api/v1/places')).json()) as { id: number; name: string }[];
  const name = `Moong ${test.info().project.name.replace(/\W/g, '')} ${Date.now()}`;
  const { food } = await post(page, '/foods', { name, place_id: places[0]!.id });
  await post(page, `/foods/${food.id}/sizes`, { name: 'pack', amount: 200 });
  await post(page, '/stock', { food_id: food.id, amount: { amount: 1, unit: 'pack' }, place_id: places[0]!.id });
  await page.goto('/pantry');
  await page.getByRole('searchbox', { name: isPhone(page) ? 'Search pantry' : 'Find in pantry' }).fill(name);
  await expect(page.getByRole('list', { name: 'Found in the pantry' })).toBeVisible();
  await page.getByRole('button', { name: new RegExp(`^${name}`) }).first().click();
  await page.getByRole('list', { name: `Packets of ${name}` }).getByRole('button').first().click();
  const menu = page.getByRole('dialog');
  await expect(menu.getByRole('button', { name: 'Used', exact: true })).toBeVisible();

  const sent: string[] = [];
  page.on('request', (r) => {
    if (r.method() !== 'GET' && r.url().includes('/api/')) sent.push(`${r.method()} ${r.url()}`);
  });
  await serverStops(page);
  await menu.getByRole('button', { name: 'Used', exact: true }).click();
  await expect(page.getByText(CANT_REACH).last()).toBeVisible();
  expect(sent).toEqual([]);
  await expect(page.getByText('Couldn’t save. Try again.')).toHaveCount(0);
});

test('Ingredients: the rename box already open when the server stops sends nothing', async ({ page }) => {
  test.skip(isPhone(page), 'Computer layout');
  const name = `Barley ${Date.now()}`;
  await post(page, '/foods', { name, counted_as: 'weight' });
  await page.goto('/recipes/ingredients');
  await page.getByRole('searchbox', { name: 'Search ingredients' }).fill(name);
  await page.locator('button.row', { hasText: name }).click();
  await page.getByRole('button', { name: 'Rename' }).click();
  const box = page.getByRole('textbox', { name: 'Name' });
  await box.fill(`${name} pearl`);
  const sent: string[] = [];
  page.on('request', (r) => {
    if (r.method() !== 'GET' && r.url().includes('/api/')) sent.push(`${r.method()} ${r.url()}`);
  });
  await serverStops(page);
  await box.press('Enter');
  await expect(page.getByText(CANT_REACH).last()).toBeVisible();
  expect(sent).toEqual([]);
  await expect(page.getByText('Couldn’t save. Try again.')).toHaveCount(0);
});
