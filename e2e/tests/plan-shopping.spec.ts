import { test, expect, type Page } from './clock.ts';
import { inTheme, setAccountTheme, THEMES } from './a11y.ts';

// Plan shopping (0.8, S3): from 1100 px the Shopping page is one column grouped by shop and
// aisle, one-line rows (tick · name · amount · why · ⋯), and a column of panels (Shops, Check
// you have these, In the trolley). Against the real server; the projects share one server and
// one main list, so each test uses ingredients of its own and takes its plan and lines away.

const key = () => ({ 'idempotency-key': crypto.randomUUID() });
const stamp = () => `${test.info().project.name.replace(/\W/g, '')}${Date.now().toString(36)}`;
const DAYS = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'];

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

const weekday = (iso: string) => DAYS[new Date(`${iso}T12:00:00Z`).getUTCDay()]!;

async function kitchen(page: Page) {
  const household = (await (await page.request.get('/api/v1/household')).json()) as { today: string };
  const slots = (await (await page.request.get('/api/v1/meal-slots')).json()) as { id: number; name: string }[];
  const dinner = slots.find((s) => s.name === 'Dinner')!.id;
  const items: number[] = [];
  const lines: string[] = [];
  return {
    today: household.today,
    food: async (name: string, extra: object = {}) =>
      (await call(page, 'POST', '/foods', { name, counted_as: 'weight', ...extra })).food.id as number,
    shop: async (name: string) => (await call(page, 'POST', '/shops', { name })).id as number,
    recipe: async (name: string, foods: [number, number][]) =>
      (
        await call(page, 'POST', '/recipes', {
          name,
          serves: 4,
          lines: foods.map(([food_id, amount]) => ({ words: 'x', food_id, amount, unit: 'g' })),
        })
      ).id as number,
    plan: async (recipeId: number, daysAhead: number) => {
      const made = await call(page, 'POST', '/plan/items', {
        date: addDays(household.today, daysAhead),
        slot_id: dinner,
        recipe_id: recipeId,
      });
      items.push(made.item_id as number);
      return addDays(household.today, daysAhead);
    },
    typed: async (foodId: number, grams: number) => {
      const { lists } = (await (await page.request.get('/api/v1/shopping/lists')).json()) as { lists: { id: string; main: boolean }[] };
      const made = await call(page, 'POST', `/shopping/lists/${lists.find((l) => l.main)!.id}/items`, {
        food_id: foodId,
        amount: { amount: grams, unit: 'g' },
      });
      lines.push(made.item.id as string);
    },
    async cleanUp() {
      for (const id of items) await page.request.fetch(`/api/v1/plan/items/${id}`, { method: 'DELETE', headers: key() });
      for (const id of lines) await page.request.fetch(`/api/v1/shopping/items/${id}`, { method: 'DELETE', headers: key() });
      await page.request.fetch('/api/v1/shopping/from-plan', { method: 'POST' });
    },
  };
}

const row = (page: Page, name: string) => page.getByRole('listitem').filter({ has: page.getByRole('button', { name, exact: true }) });

test.beforeEach(async ({ page }) => {
  await setAccountTheme(page, 'auto');
});

for (const width of [1280, 1100]) {
  for (const theme of THEMES) {
    test(`two shops show both sections in Settings order, with why-text (${width} px, ${theme})`, async ({ page }) => {
      await page.setViewportSize({ width, height: 900 });
      const k = await kitchen(page);
      const tag = stamp();
      try {
        const first = await k.shop(`Aaa shop ${tag}`);
        const second = await k.shop(`Zzz shop ${tag}`);
        const onion = `Onion ${tag}`;
        const milk = `Milk ${tag}`;
        const onionId = await k.food(onion, { shop_id: second });
        const milkId = await k.food(milk, { shop_id: first });
        const sambar = `Sambar ${tag}`;
        const day = await k.plan(await k.recipe(sambar, [[onionId, 200]]), 2);
        await k.typed(milkId, 500);

        await page.goto('/shopping');
        await inTheme(page, theme);
        await expect(page.getByRole('heading', { name: 'Plan shopping', level: 1 })).toBeVisible();
        const head1 = page.getByRole('heading', { name: new RegExp(`^Aaa shop ${tag}`) });
        const head2 = page.getByRole('heading', { name: new RegExp(`^Zzz shop ${tag}`) });
        await expect(head1).toBeVisible();
        await expect(head2).toBeVisible();
        // Settings order: the shop made first comes first.
        const [b1, b2] = [await head1.boundingBox(), await head2.boundingBox()];
        expect(b1!.y).toBeLessThan(b2!.y);

        // One line each, with why: the recipe and its day; "Added by you".
        await expect(row(page, onion).getByText(`${sambar} (${weekday(day)})`)).toBeVisible();
        await expect(row(page, milk).getByText('Added by you')).toBeVisible();
        const box = await row(page, onion).boundingBox();
        expect(box!.height).toBeLessThanOrEqual(64);

        // The right-hand column.
        await expect(page.getByRole('region', { name: 'Shops' })).toBeVisible();
        await expect(page.getByRole('button', { name: /^All · \d+$/ })).toBeVisible();
        await expect(page.getByRole('button', { name: new RegExp(`^Zzz shop ${tag} · 1$`) })).toBeVisible();
        await expect(page.getByRole('link', { name: 'Manage' })).toBeVisible();
        const scrollWidth = await page.evaluate(() => document.documentElement.scrollWidth);
        expect(scrollWidth).toBeLessThanOrEqual(width);

        // A shop chip shows just that shop.
        await page.getByRole('button', { name: new RegExp(`^Zzz shop ${tag} · 1$`) }).click();
        await expect(row(page, onion)).toBeVisible();
        await expect(row(page, milk)).toHaveCount(0);
      } finally {
        await k.cleanUp();
      }
    });
  }
}

test('under 1100 px it is the phone screen, with no Plan shopping', async ({ page }) => {
  await page.setViewportSize({ width: 1099, height: 900 });
  await page.goto('/shopping');
  await expect(page.getByRole('heading', { name: 'Shopping', level: 1 })).toBeVisible();
  await expect(page.getByRole('heading', { name: 'Plan shopping' })).toHaveCount(0);
  await expect(page.getByRole('region', { name: 'Shops' })).toHaveCount(0);
});

test('a household with one shop shows no shop headers', async ({ page }) => {
  const k = await kitchen(page);
  const tag = stamp();
  try {
    const name = `Single ${tag}`;
    const id = await k.food(name);
    await k.plan(await k.recipe(`Dish ${tag}`, [[id, 100]]), 1);
    // Whatever other tests added, this household has no shop: everything is "Any shop".
    await page.route('**/api/v1/shopping/changes*', async (route) => {
      const response = await route.fetch();
      const body = await response.json();
      body.shops = [];
      for (const item of body.items) item.shop_id = null;
      await route.fulfill({ response, json: body });
    });
    await page.goto('/shopping');
    await expect(row(page, name)).toBeVisible();
    await expect(page.getByRole('heading', { level: 2, name: /· \d+$/ })).toHaveCount(0);
  } finally {
    await k.cleanUp();
  }
});

test('"Usual pack?" quick picks sit under a row with no size, and a tap sets the Usual size', async ({ page }) => {
  const k = await kitchen(page);
  const tag = stamp();
  try {
    const name = `Tamarind ${tag}`;
    const id = await k.food(name);
    await k.plan(await k.recipe(`Rasam ${tag}`, [[id, 60]]), 1);
    await page.goto('/shopping');
    await expect(row(page, name).getByText(/no pack size/)).toBeVisible();
    const picks = page.getByRole('group', { name: `Usual pack for ${name}?` });
    await expect(picks).toBeVisible();
    const first = picks.getByRole('button').first();
    const text = (await first.textContent())!.trim();
    await first.click();
    // The size is the ingredient's Usual size now, and the line says it in packs.
    await expect(picks).toHaveCount(0);
    await expect(row(page, name).getByText(/^1 \S+ \(/)).toBeVisible();
    const food = (await (await page.request.get(`/api/v1/foods/${id}`)).json()) as {
      sizes: { usual: boolean; display: string }[];
    };
    expect(food.sizes.some((s) => s.usual && s.display.includes(text.replace(/\s/g, ' ')))).toBe(true);
  } finally {
    await k.cleanUp();
  }
});

test('"Make it a staple?" shows for a tiny need of a best-before ingredient; one tap, with Undo', async ({ page }) => {
  const k = await kitchen(page);
  const tag = stamp();
  // Cornmeal is a best-before ingredient in Mealwright's pack-size table (smallest pack 500 g).
  const found = (await (await page.request.get('/api/v1/foods?q=Cornmeal')).json()) as { foods: { id: number; name: string }[] };
  const existing = found.foods.find((f) => f.name === 'Cornmeal');
  const id = existing ? existing.id : await k.food('Cornmeal');
  try {
    await k.plan(await k.recipe(`Polenta ${tag}`, [[id, 5]]), 1);
    await page.goto('/shopping');
    const link = row(page, 'Cornmeal').getByRole('button', { name: 'Make it a staple?' });
    await expect(link).toBeVisible();
    await link.click();
    await expect(page.getByText('Cornmeal is now a staple')).toBeVisible();
    await expect(link).toHaveCount(0);
    await page.getByRole('button', { name: 'Undo' }).first().click();
    await expect(row(page, 'Cornmeal').getByRole('button', { name: 'Make it a staple?' })).toBeVisible();
  } finally {
    await call(page, 'PATCH', `/foods/${id}`, { staple: false }).catch(() => undefined);
    await k.cleanUp();
  }
});

test('+ New shop adds a shop chip', async ({ page }) => {
  const tag = stamp();
  await page.goto('/shopping');
  await page.getByRole('button', { name: '+ New shop' }).click();
  await page.getByRole('textbox', { name: 'Shop name' }).fill(`Corner ${tag}`);
  await page.getByRole('button', { name: 'Add shop' }).click();
  await expect(page.getByRole('button', { name: new RegExp(`^Corner ${tag} · 0$`) })).toBeVisible();
});
