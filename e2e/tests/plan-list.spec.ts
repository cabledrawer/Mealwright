import { test, expect, type Page } from './clock.ts';
import { checkPage, setAccountTheme } from './a11y.ts';

// The shopping list built from the plan (0.6, PR 5), against the real server: a planned recipe's
// ingredients appear on Shopping and follow the plan; a hand edit survives a plan change; the
// "Check you have these" card with Got it and + Add. Runs on Chromium (phone and computer) and
// WebKit (computer), see playwright.config.ts.
//
// The projects share one server and one main list, so each test uses ingredients of its own, plans
// only its own recipe, and takes its meals and lines away again at the end.

const key = () => ({ 'idempotency-key': crypto.randomUUID() });
const stamp = () => `${test.info().project.name.replace(/\W/g, '')}${Date.now().toString(36)}`;

async function call(page: Page, method: 'POST' | 'PUT' | 'DELETE' | 'PATCH', path: string, data?: object) {
  const response = await page.request.fetch(`/api/v1${path}`, { method, data, headers: key() });
  expect(response.ok(), `${method} ${path}: ${await response.text()}`).toBe(true);
  return (await response.json()) as Record<string, any>;
}

function addDays(iso: string, days: number): string {
  const d = new Date(`${iso}T12:00:00Z`);
  d.setUTCDate(d.getUTCDate() + days);
  return d.toISOString().slice(0, 10);
}

/** What a test needs, and the clean-up that puts the shared list and plan back. */
async function kitchen(page: Page) {
  const household = (await (await page.request.get('/api/v1/household')).json()) as { today: string };
  const slots = (await (await page.request.get('/api/v1/meal-slots')).json()) as { id: number; name: string }[];
  const slot = Object.fromEntries(slots.map((s) => [s.name, s.id])) as Record<string, number>;
  const items: number[] = [];
  const lines: string[] = [];
  return {
    today: household.today,
    food: async (name: string, extra: object = {}) =>
      (await call(page, 'POST', '/foods', { name, counted_as: 'weight', ...extra })).food.id as number,
    recipe: async (name: string, lines: object[]) => (await call(page, 'POST', '/recipes', { name, serves: 4, lines })).id as number,
    plan: async (recipeId: number, daysAhead: number, slotName = 'Dinner', extra: object = {}) => {
      const made = await call(page, 'POST', '/plan/items', {
        date: addDays(household.today, daysAhead),
        slot_id: slot[slotName],
        recipe_id: recipeId,
        ...extra,
      });
      items.push(made.item_id as number);
      return made.item_id as number;
    },
    mine: (id: string) => lines.push(id),
    async cleanUp() {
      for (const id of items) await page.request.fetch(`/api/v1/plan/items/${id}`, { method: 'DELETE', headers: key() });
      for (const id of lines) await page.request.fetch(`/api/v1/shopping/items/${id}`, { method: 'DELETE', headers: key() });
      await page.request.fetch('/api/v1/shopping/from-plan', { method: 'POST' });
    },
  };
}

const line = (foodId: number, amount: number, unit = 'g') => ({ words: 'x', food_id: foodId, amount, unit });

/** The main list's lines, from the sync copy, with the ingredient's name. */
async function listLines(page: Page) {
  const copy = (await (await page.request.get('/api/v1/shopping/changes?since=0')).json()) as {
    items: { id: string; food_id: number; amount: number | null; source: string; hand_edited: boolean }[];
    foods: { id: number; name: string }[];
  };
  const names = new Map(copy.foods.map((f) => [f.id, f.name]));
  return copy.items.map((i) => ({ ...i, name: names.get(i.food_id) ?? '' }));
}

const amountButton = (page: Page, name: string, amount: string) =>
  page.getByRole('button', { name: new RegExp(`^Change amount: ${name}, ${amount}`) });

test('a planned recipe puts its ingredients on Shopping, and the lines follow the plan', async ({ page }) => {
  const k = await kitchen(page);
  const tag = stamp();
  const rice = `Rice ${tag}`;
  const dal = `Dal ${tag}`;
  try {
    const riceId = await k.food(rice);
    const dalId = await k.food(dal);
    const sambar = await k.recipe(`Sambar ${tag}`, [line(riceId, 200), line(dalId, 100)]);
    await page.goto('/shopping');
    await expect(page.getByRole('heading', { name: 'Shopping', level: 1 })).toBeVisible();
    await expect(amountButton(page, rice, '200')).toHaveCount(0);

    const first = await k.plan(sambar, 2);
    // Live: the lines arrive on the open screen, and the line above says where they came from.
    await expect(amountButton(page, rice, '200 g')).toBeVisible();
    await expect(amountButton(page, dal, '100 g')).toBeVisible();
    await expect(page.getByText(/to buy · built from this week’s plan/)).toBeVisible();

    // Another meal of the same recipe: the line is updated, not doubled.
    await k.plan(sambar, 3);
    await expect(amountButton(page, rice, '400 g')).toBeVisible();
    await expect(page.getByRole('button', { name: new RegExp(`^Change amount: ${rice}, `) })).toHaveCount(1);

    // Taking the first meal off the plan takes its share off the list.
    await call(page, 'DELETE', `/plan/items/${first}`);
    await expect(amountButton(page, rice, '200 g')).toBeVisible();
  } finally {
    await k.cleanUp();
  }
  await page.goto('/shopping');
  await expect(page.getByText(rice)).toHaveCount(0);
});

test('a hand edit survives a change to the plan', async ({ page }) => {
  const k = await kitchen(page);
  const tag = stamp();
  const rice = `Rice ${tag}`;
  try {
    const riceId = await k.food(rice);
    const pilau = await k.recipe(`Pilau ${tag}`, [line(riceId, 200)]);
    await k.plan(pilau, 2);
    await page.goto('/shopping');
    await amountButton(page, rice, '200 g').click();
    const box = page.getByRole('form', { name: `Change ${rice}` });
    await box.getByRole('textbox', { name: 'Amount' }).fill('750');
    await box.getByRole('button', { name: 'Done' }).click();
    await expect(amountButton(page, rice, '750')).toBeVisible();

    await k.plan(pilau, 3); // the plan now needs 400 g
    await expect.poll(async () => (await listLines(page)).filter((l) => l.name === rice).map((l) => [l.amount, l.hand_edited])).toEqual([[750, true]]);
    await page.reload();
    await expect(amountButton(page, rice, '750')).toBeVisible();
    await expect(page.getByRole('button', { name: new RegExp(`^Change amount: ${rice}, `) })).toHaveCount(1);
  } finally {
    await k.cleanUp();
  }
});

test('Check you have these: Got it stays hidden until the plan changes; + Add puts the staple on the list', async ({ page }) => {
  const k = await kitchen(page);
  const tag = stamp();
  const oil = `Oil ${tag}`;
  const turmeric = `Turmeric ${tag}`;
  try {
    const oilId = await k.food(oil, { staple: true });
    const turmericId = await k.food(turmeric, { staple: true });
    const rice = await k.food(`Rice ${tag}`);
    const stew = await k.recipe(`Stew ${tag}`, [line(oilId, 1, 'tbsp'), line(turmericId, 1, 'tsp'), line(rice, 100)]);
    await k.plan(stew, 2);
    await page.goto('/shopping');
    const card = page.getByRole('region', { name: 'Check you have these' });
    await expect(card).toBeVisible();
    await expect(card.getByText('Staples this week’s recipes use')).toBeVisible();
    await expect(card.getByText(`Stew ${tag}`)).toHaveCount(2);
    // The plan never puts a staple on the list itself.
    await expect(page.getByRole('button', { name: oil, exact: true })).toHaveCount(0);

    // Got it: gone, and still gone after a reload (the server remembers it).
    await card.getByRole('button', { name: `Got it, ${oil}` }).click();
    await expect(card.getByRole('button', { name: `Got it, ${oil}` })).toHaveCount(0);
    await page.reload();
    await expect(card.getByRole('button', { name: `Got it, ${turmeric}` })).toBeVisible();
    await expect(card.getByRole('button', { name: `Got it, ${oil}` })).toHaveCount(0);

    // Another meal that uses it: it asks again.
    await k.plan(stew, 3);
    await page.reload();
    await expect(card.getByRole('button', { name: `Got it, ${oil}` })).toBeVisible();

    // + Add: an ordinary line, and it leaves the card.
    await card.getByRole('button', { name: `+ Add ${turmeric}` }).click();
    await expect(card.getByRole('button', { name: `Got it, ${turmeric}` })).toHaveCount(0);
    await expect(page.getByRole('checkbox', { name: `Tick ${turmeric}` })).toBeVisible();
    const added = (await listLines(page)).find((l) => l.name === turmeric);
    expect(added?.source).toBe('typed');
    if (added) k.mine(added.id);

    await checkPage(page); // the card passes the accessibility checks, both themes
  } finally {
    await k.cleanUp();
  }
});

test('the card is readable in the dark theme and stays on screen at the phone’s width', async ({ page }) => {
  const k = await kitchen(page);
  const tag = stamp();
  const oil = `A very long oil name for a narrow screen ${tag}`;
  try {
    const oilId = await k.food(oil, { staple: true });
    const stew = await k.recipe(`Stew ${tag}`, [line(oilId, 1, 'tbsp')]);
    await k.plan(stew, 2);
    await setAccountTheme(page, 'dark');
    await page.goto('/shopping');
    const card = page.getByRole('region', { name: 'Check you have these' });
    await expect(card).toBeVisible();
    const box = (await card.boundingBox())!;
    const width = page.viewportSize()!.width;
    expect(box.x).toBeGreaterThanOrEqual(0);
    expect(box.x + box.width).toBeLessThanOrEqual(width);
    for (const name of [`Got it, ${oil}`, `+ Add ${oil}`]) {
      const target = (await card.getByRole('button', { name }).boundingBox())!;
      expect(target.height).toBeGreaterThanOrEqual(44);
      expect(target.x + target.width).toBeLessThanOrEqual(width);
    }
  } finally {
    await setAccountTheme(page, 'auto');
    await k.cleanUp();
  }
});
