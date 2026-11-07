import { test, expect, type Page } from './clock.ts';
import { isPhone } from './a11y.ts';

// Shopping on the phone, "in the shop" (0.8, S4), against the real server at 390 px, on Chromium
// and on WebKit: Already have it, Add as bought, How many?, the trolley most recent first, swipe
// left to clear one, Clear ticked with one Undo, the amount box's quick picks and
// "Different pack?" going back to the planned amount. The offline versions are in offline.spec.ts.
// Every test makes its own ingredients (the list is shared by the tests on the server).

const key = () => ({ 'idempotency-key': crypto.randomUUID() });
const tag = () => `${test.info().project.name.replace(/\W/g, '')}${Date.now()}`;
const chromium = (page: Page) => page.context().browser()?.browserType().name() === 'chromium';

async function call(page: Page, method: 'POST' | 'PATCH', path: string, data?: object) {
  const response = await page.request.fetch(`/api/v1${path}`, { method, data, headers: key() });
  expect(response.ok(), `${method} ${path}: ${await response.text()}`).toBe(true);
  return response.json();
}

async function mainList(page: Page): Promise<string> {
  const { lists } = await (await page.request.get('/api/v1/shopping/lists')).json();
  return lists.find((l: { main: boolean }) => l.main).id;
}

/** Put a counted ingredient on the main list with a base amount, as a phone's `add` does. */
async function addCounted(page: Page, foodId: number, amount: number) {
  const me = await (await page.request.get('/api/v1/me')).json();
  const sent = await page.request.post('/api/v1/shopping/actions', {
    data: {
      protocol: 1,
      device_id: crypto.randomUUID(),
      login_id: me.id,
      since: 0,
      sent_at: new Date().toISOString(),
      actions: [
        {
          id: crypto.randomUUID(),
          kind: 'add',
          made_at: new Date().toISOString(),
          seen: 0,
          list_id: await mainList(page),
          item_id: crypto.randomUUID(),
          food_id: foodId,
          amount,
        },
      ],
    },
  });
  expect(sent.ok(), await sent.text()).toBe(true);
}

/** A new weighed ingredient on the main list (500 g unless said), or counted. */
async function onList(
  page: Page,
  name: string,
  options: { grams?: number; counted?: boolean; listed?: boolean } = {},
) {
  const { food } = await call(page, 'POST', '/foods', {
    name,
    counted_as: options.counted ? 'count' : 'weight',
  });
  if (options.listed !== false && options.counted) await addCounted(page, food.id, 3);
  else if (options.listed !== false) {
    await call(page, 'POST', `/shopping/lists/${await mainList(page)}/items`, {
      food_id: food.id,
      amount: { amount: options.grams ?? 500, unit: 'g' },
    });
  }
  return food.id as number;
}

/** The ingredient's stock in the pantry, one entry per place: [amount, place]. */
async function stock(page: Page, foodId: number): Promise<[number, string][]> {
  const pantry = await (await page.request.get('/api/v1/pantry')).json();
  const out: [number, string][] = [];
  for (const p of pantry.places)
    for (const g of p.groups) if (g.food.id === foodId) out.push([g.stock.amount, p.name]);
  return out;
}

/** The newest pantry change for this ingredient, as Recent changes words it. */
async function lastChange(page: Page, name: string) {
  const { changes } = await (await page.request.get('/api/v1/changes?area=pantry&limit=50')).json();
  return changes.find((c: { summary: string }) => c.summary.includes(name));
}

async function open(page: Page) {
  await page.goto('/shopping');
  await expect(page.getByRole('heading', { name: 'Shopping', level: 1 })).toBeVisible();
}

/** Open every "In the trolley" fold (the phone folds them). */
async function openTrolleyOf(page: Page) {
  const toggles = page.getByRole('button', { name: /^In the trolley/ });
  for (let i = 0; i < (await toggles.count()); i++) {
    const toggle = toggles.nth(i);
    if ((await toggle.getAttribute('aria-expanded')) === 'false') await toggle.click();
  }
}

async function touchSwipe(page: Page, name: string, side: 'left' | 'right', inTrolley = false) {
  // The name is a button on the list; in the trolley the row's tick is the thing to find it by.
  const inside = inTrolley
    ? page.getByRole('checkbox', { name: `Untick ${name}` })
    : page.getByRole('button', { name, exact: true });
  const row = inside.first().locator("xpath=ancestor::div[contains(@class,'slide')]");
  await row.evaluate((el) => el.scrollIntoView({ block: 'center' }));
  const box = (await row.boundingBox())!;
  const y = box.y + box.height / 2;
  const from = side === 'left' ? box.x + box.width - 40 : box.x + 40;
  const cdp = await page.context().newCDPSession(page);
  const send = (type: 'touchStart' | 'touchMove' | 'touchEnd', x?: number) =>
    cdp.send('Input.dispatchTouchEvent', { type, touchPoints: x === undefined ? [] : [{ x, y }] });
  await send('touchStart', from);
  const step = side === 'left' ? -14 : 14;
  for (let i = 1; i <= 16; i++) await send('touchMove', from + i * step);
  await send('touchEnd');
  await cdp.detach();
}

test.beforeEach(({ page }) => {
  test.skip(!isPhone(page), 'the phone screen');
});

test('Already have it (from the amount box): how much is at home, where, and it is found, not bought', async ({ page }) => {
  const name = `Ghee ${tag()}`;
  const id = await onList(page, name);
  await open(page);
  await page.getByRole('button', { name, exact: true }).click();
  await page.getByRole('button', { name: 'Already have it' }).click();
  const sheet = page.getByRole('dialog', { name: `Already have ${name}` });
  await expect(sheet).toBeVisible();
  await expect(sheet.getByText(`How much ${name} is at home?`)).toBeVisible();
  await expect(sheet.getByText('It comes off the list and goes into the pantry as found at home, not bought.')).toBeVisible();
  await sheet.getByRole('radio', { name: /^250/ }).click();
  await sheet.getByRole('combobox', { name: 'Where' }).selectOption({ label: 'Cupboard' });
  await sheet.getByRole('button', { name: /^Put 250.g in the pantry$/ }).click();
  const toast = page.getByRole('status').filter({ hasText: `Found ${name} at home` });
  await expect(toast).toBeVisible();
  await expect(page.getByRole('checkbox', { name: `Tick ${name}` })).toHaveCount(0);
  await expect.poll(async () => await stock(page, id)).toEqual([[250, 'Cupboard']]);
  const change = await lastChange(page, name);
  expect(change.kind).toBe('found');
  expect(change.summary).toMatch(new RegExp(`^Found ${name} at home: 250.g → Cupboard$`));
  // In the trolley, one line: the name, "250 g · found at home", and the place as a button.
  await openTrolleyOf(page);
  await expect(page.getByText('250 g · found at home')).toBeVisible();
  await expect(page.getByRole('button', { name: `Change where ${name} went` })).toHaveText(/→ Cupboard/);
  // Undo puts the line back on the list and takes the stock out.
  await toast.getByRole('button', { name: 'Undo' }).click();
  await expect(page.getByRole('checkbox', { name: `Tick ${name}` })).toBeVisible();
  await expect.poll(async () => await stock(page, id)).toEqual([]);
});

test('swipe right shows Already have it and Move…; a swipe alone changes nothing', async ({ page }) => {
  test.skip(!chromium(page), 'touch events come through the Chromium protocol; WebKit uses the amount box above');
  const name = `Tamarind ${tag()}`;
  const id = await onList(page, name);
  await open(page);
  await touchSwipe(page, name, 'right');
  await expect(page.getByRole('button', { name: new RegExp(`^Already have it ${name}`) })).toBeVisible();
  await expect(page.getByRole('button', { name: new RegExp(`^Move… ${name}`) })).toBeVisible();
  expect(await stock(page, id)).toEqual([]);
  await page.getByRole('button', { name: new RegExp(`^Already have it ${name}`) }).click();
  await expect(page.getByRole('dialog', { name: `Already have ${name}` })).toBeVisible();
});

test('Add as bought: straight into the pantry, with where it goes and one Undo for the add and the tick', async ({ page }) => {
  const name = `Jaggery ${tag()}`;
  const id = await onList(page, name, { listed: false });
  await open(page);
  await page.getByRole('textbox', { name: 'Add an item' }).fill(name);
  const bought = page.getByRole('button', { name: 'Add as bought' });
  await expect(bought).toContainText('Straight into the pantry');
  await bought.click();
  const toast = page.getByRole('status').filter({ hasText: name });
  await expect(toast).toBeVisible();
  await expect(page.getByRole('button', { name, exact: true })).toHaveCount(0); // not left on the list to buy
  // No amount known for it: the sheet "How much?" opens on its row, and an answer puts it in.
  await openTrolleyOf(page);
  await expect(page.getByRole('button', { name: `Change where ${name} went` }).or(page.getByRole('button', { name: `Add amount for ${name}` }))).toBeVisible();
  await toast.getByRole('button', { name: 'Undo' }).click();
  await expect(page.getByRole('checkbox', { name: new RegExp(`${name}$`) })).toHaveCount(0);
  expect(await stock(page, id)).toEqual([]);
});

test('How many? (F134): a new counted ingredient asks 1 · 2 · 6 · 12 and adds what was picked', async ({ page }) => {
  const name = `Mango ${tag()}`;
  await onList(page, name, { counted: true, listed: false });
  await open(page);
  await page.getByRole('textbox', { name: 'Add an item' }).fill(name);
  await page.getByRole('list', { name: 'Matching ingredients' }).getByRole('button', { name, exact: true }).click();
  const ask = page.getByRole('group', { name: `How many ${name}?` });
  for (const n of ['1', '2', '6', '12']) await expect(ask.getByRole('button', { name: n, exact: true })).toBeVisible();
  await ask.getByRole('button', { name: '6', exact: true }).click();
  await expect(page.getByRole('button', { name: new RegExp(`^Change amount: ${name}, 6`) })).toBeVisible();
});

test('In the trolley: most recently ticked first, one line each; Clear ticked is one Undo', async ({ page }) => {
  const t = tag();
  const [first, second, third] = [`Ajwain ${t}`, `Bay ${t}`, `Cumin ${t}`];
  for (const n of [first, second, third]) await onList(page, n);
  await open(page);
  for (const n of [first, third, second]) {
    await page.getByRole('checkbox', { name: `Tick ${n}` }).click();
    await expect(page.getByRole('checkbox', { name: `Tick ${n}` })).toHaveCount(0);
  }
  await openTrolleyOf(page);
  const order = await page
    .getByRole('checkbox', { name: /^Untick / })
    .evaluateAll((boxes) => boxes.map((b) => b.getAttribute('aria-label')));
  const mine = order.filter((label) => [first, second, third].some((n) => label === `Untick ${n}`));
  expect(mine).toEqual([`Untick ${second}`, `Untick ${third}`, `Untick ${first}`]);
  // One line each: the place is a button on it.
  for (const n of [first, second, third]) {
    await expect(page.getByRole('button', { name: `Change where ${n} went` })).toHaveText(/→ /);
  }
});

test('swipe left in the trolley clears just that line, with Undo; Clear ticked is one press and one Undo', async ({ page }) => {
  test.skip(!chromium(page), 'touch events come through the Chromium protocol');
  const t = tag();
  const [a, b] = [`Dill ${t}`, `Fennel ${t}`];
  for (const n of [a, b]) await onList(page, n);
  await open(page);
  for (const n of [a, b]) await page.getByRole('checkbox', { name: `Tick ${n}` }).click();
  await openTrolleyOf(page);
  await touchSwipe(page, b, 'left', true);
  const clear = page.getByRole('button', { name: new RegExp(`^Clear ${b}`) });
  await expect(clear).toBeVisible();
  await clear.click();
  await expect(page.getByRole('checkbox', { name: `Untick ${b}` })).toHaveCount(0);
  await expect(page.getByRole('checkbox', { name: `Untick ${a}` })).toBeVisible();
  const toast = page.getByRole('status').filter({ hasText: 'Cleared 1 ticked item' });
  await toast.getByRole('button', { name: 'Undo' }).click();
  await expect(page.getByRole('checkbox', { name: `Untick ${b}` })).toBeVisible();
});

test('Clear ticked clears them all in one press, and one Undo brings them all back', async ({ page }) => {
  const t = tag();
  const [a, b] = [`Elaichi ${t}`, `Fenugreek ${t}`];
  for (const n of [a, b]) await onList(page, n);
  await open(page);
  for (const n of [a, b]) await page.getByRole('checkbox', { name: `Tick ${n}` }).click();
  await openTrolleyOf(page);
  await page.getByRole('button', { name: 'Clear ticked' }).first().click();
  await expect(page.getByRole('checkbox', { name: `Untick ${a}` })).toHaveCount(0);
  await expect(page.getByRole('checkbox', { name: `Untick ${b}` })).toHaveCount(0);
  const toasts = page.getByRole('status').filter({ hasText: /Cleared \d+ ticked/ });
  await expect(toasts).toHaveCount(1);
  await toasts.getByRole('button', { name: 'Undo' }).click();
  await openTrolleyOf(page);
  await expect(page.getByRole('checkbox', { name: `Untick ${a}` })).toBeVisible();
  await expect(page.getByRole('checkbox', { name: `Untick ${b}` })).toBeVisible();
});

test('the amount box: a line with no amount offers quick amounts and shows its unit (F60)', async ({ page }) => {
  const name = `Nutmeg ${tag()}`;
  await onList(page, name);
  const { food } = await call(page, 'POST', '/foods', { name: `${name} blank`, counted_as: 'weight' });
  await call(page, 'POST', `/shopping/lists/${await mainList(page)}/items`, { food_id: food.id });
  await open(page);
  await page.getByRole('button', { name: `Add amount for ${name} blank` }).click();
  const quick = page.getByRole('group', { name: `Quick amounts for ${name} blank` });
  await expect(quick.getByRole('button')).toHaveText(['250 g', '500 g', '1 kg']);
  await quick.getByRole('button', { name: '500 g' }).click();
  await expect(page.getByRole('textbox', { name: 'Amount' })).toHaveValue('500 g');
  await page.getByRole('button', { name: 'Done' }).click();
  await expect(page.getByRole('button', { name: new RegExp(`^Change amount: ${name} blank, 500`) })).toBeVisible();
});

test('Different pack? can go back to the planned amount after a different one was bought (F153)', async ({ page }) => {
  const name = `Spring onions ${tag()}`;
  const { food } = await call(page, 'POST', '/foods', { name, counted_as: 'count' });
  await addCounted(page, food.id, 6);
  await open(page);
  await page.getByRole('checkbox', { name: `Tick ${name}` }).click();
  await openTrolleyOf(page);
  await page.getByRole('button', { name: `Change where ${name} went` }).click();
  await page.getByRole('button', { name: 'Different pack?' }).click();
  const sheet = page.getByRole('group', { name: 'What did you buy?' });
  await sheet.getByRole('radio', { name: 'Other…' }).click();
  await sheet.getByLabel('How many packs').fill('1');
  await sheet.getByLabel('Size of one').fill('1');
  await sheet.getByRole('button', { name: 'Done' }).click();
  await expect.poll(async () => (await stock(page, food.id)).map(([n]) => n)).toEqual([1]);
  // Reopen: what was bought (1) is the one picked; the planned 6 is another choice, and it works.
  await page.getByRole('button', { name: 'Different pack?' }).click();
  const again = page.getByRole('group', { name: 'What did you buy?' });
  await expect(again.getByRole('radio', { checked: true })).toHaveText(/1.×.1/);
  await again.getByRole('radio', { name: /1.×.6/ }).click();
  await again.getByRole('button', { name: 'Done' }).click();
  await expect.poll(async () => (await stock(page, food.id)).map(([n]) => n)).toEqual([6]);
});
