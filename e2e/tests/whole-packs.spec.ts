import { test, expect, type Page } from './clock.ts';
import { checkPage, isPhone, setAccountTheme } from './a11y.ts';

// Whole packs on the list, and another size suggested when it leaves much less over (0.8 W4c,
// F183 + F204, cabledrawer 8 and 9 Nov), against the real server on a phone (Chromium and WebKit) and
// a computer (Plan shopping). Every test makes its own ingredients and takes its plan and lines
// away: the projects share one server and one main list.

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

/** A recipe needing one ingredient, planned for dinner; the plan is taken away afterwards. */
async function needing(
  page: Page,
  name: string,
  food: { counted_as: 'weight' | 'volume'; sizes: [string, number][] },
  need: { amount: number; unit: string },
) {
  const made = await call(page, 'POST', '/foods', { name, counted_as: food.counted_as });
  const foodId = made.food.id as number;
  for (const [index, [word, amount]] of food.sizes.entries()) {
    await call(page, 'POST', `/foods/${foodId}/sizes`, index === 0 ? { name: word, amount, usual: true } : { name: word, amount });
  }
  const household = (await (await page.request.get('/api/v1/household')).json()) as { today: string };
  const slots = (await (await page.request.get('/api/v1/meal-slots')).json()) as { id: number; name: string }[];
  const recipe = await call(page, 'POST', '/recipes', {
    name: `Dish ${name}`,
    serves: 4,
    lines: [{ words: 'x', food_id: foodId, amount: need.amount, unit: need.unit }],
  });
  const planned = await call(page, 'POST', '/plan/items', {
    date: addDays(household.today, 2),
    slot_id: slots.find((s) => s.name === 'Dinner')!.id,
    recipe_id: recipe.id,
  });
  await call(page, 'POST', '/shopping/from-plan');
  return {
    foodId,
    async cleanUp() {
      await page.request.fetch(`/api/v1/plan/items/${planned.item_id}`, { method: 'DELETE', headers: key() });
      await page.request.fetch('/api/v1/shopping/from-plan', { method: 'POST' });
    },
  };
}

const row = (page: Page, name: string) => page.getByRole('listitem').filter({ has: page.getByRole('button', { name, exact: true }) });

/** Open "which size?" for a row: the phone's amount box, the computer's ⋯ menu. */
async function openSizes(page: Page, name: string) {
  if (isPhone(page)) {
    await row(page, name).getByRole('button', { name: new RegExp(`^Change amount: ${name}`) }).click();
    await page.getByRole('form', { name: `Change ${name}` }).getByRole('button', { name: 'Which size?', exact: true }).click();
  } else {
    await row(page, name).getByRole('button', { name: /^More for / }).click();
    await page.getByRole('menuitem', { name: 'Which size?…' }).click();
  }
  const dialog = page.getByRole('dialog', { name: `${name}: which size?` });
  await expect(dialog).toBeVisible();
  return dialog;
}

test.beforeEach(async ({ page }) => {
  await setAccountTheme(page, 'auto');
});

test('12 g of salt (2 teaspoons) is one whole pack on the list, never "12 ml"', async ({ page }) => {
  const name = `Salt ${stamp()}`;
  const k = await needing(page, name, { counted_as: 'weight', sizes: [['pack', 750]] }, { amount: 12, unit: 'g' });
  try {
    await page.goto('/shopping');
    await expect(row(page, name)).toContainText(/1\spack \(750\sg\)/);
    await expect(row(page, name)).not.toContainText(/\sml/);
  } finally {
    await k.cleanUp();
  }
});

test('an ingredient with no usual size keeps its amount and says there is no pack size yet', async ({ page }) => {
  const name = `Salt ${stamp()}`;
  const k = await needing(page, name, { counted_as: 'weight', sizes: [] }, { amount: 12, unit: 'g' });
  try {
    await page.goto('/shopping');
    if (isPhone(page)) await expect(row(page, name)).toContainText('needed · no pack size yet');
    else await expect(row(page, name)).toContainText('no pack size');
    await expect(row(page, name).getByRole('group', { name: `Usual pack for ${name}?` })).toBeVisible();
    await expect(row(page, name).getByRole('group', { name: `Another size for ${name}` })).toHaveCount(0);
  } finally {
    await k.cleanUp();
  }
});

test('another size is suggested under the row; Use this changes the line, and Undo puts it back', async ({ page }) => {
  const name = `Coconut milk ${stamp()}`;
  const k = await needing(
    page,
    name,
    { counted_as: 'volume', sizes: [['tin', 400], ['small tin', 200]] },
    { amount: 600, unit: 'ml' },
  );
  try {
    await page.goto('/shopping');
    await expect(row(page, name)).toContainText(/2\stins \(400\sml\)/);
    const other = row(page, name).getByRole('group', { name: `Another size for ${name}` });
    await expect(other).toContainText(/Or 3\ssmall tins · 200\sml: nothing left over/);
    await checkPage(page);
    await other.getByRole('button', { name: 'Use this' }).click();
    await expect(row(page, name)).toContainText(/3\ssmall tins \(200\sml\)/);
    await expect(row(page, name).getByRole('group', { name: `Another size for ${name}` })).toHaveCount(0);
    await page.getByRole('button', { name: 'Undo' }).click();
    await expect(row(page, name)).toContainText(/2\stins \(400\sml\)/);
    await expect(row(page, name).getByRole('group', { name: `Another size for ${name}` })).toBeVisible();
  } finally {
    await k.cleanUp();
  }
});

test('tapping the size lists every size with what each leaves over, and a pick can become the usual size', async ({ page }) => {
  const name = `Coconut milk ${stamp()}`;
  const k = await needing(
    page,
    name,
    { counted_as: 'volume', sizes: [['tin', 400], ['small tin', 200]] },
    { amount: 600, unit: 'ml' },
  );
  try {
    await page.goto('/shopping');
    const dialog = await openSizes(page, name);
    await expect(dialog).toContainText(/600\sml needed/);
    const usual = dialog.getByRole('radio', { name: /^2\stins · 400\sml/ });
    await expect(usual).toContainText(/Your usual · 200\sml over/);
    await expect(usual).toContainText('On the list');
    const small = dialog.getByRole('radio', { name: /^3\ssmall tins · 200\sml/ });
    await expect(small).toContainText('Nothing over');
    await expect(small).toContainText('Least left over');
    await checkPage(page);
    await small.click();
    await dialog.getByRole('switch', { name: 'Make the one I pick my usual size' }).click();
    await dialog.getByRole('button', { name: 'Use this' }).click();
    await expect(dialog).toBeHidden();
    await expect(row(page, name)).toContainText(/3\ssmall tins \(200\sml\)/);
    const food = await (await page.request.get(`/api/v1/foods/${k.foodId}`)).json();
    expect(food.sizes.find((s: { usual: boolean }) => s.usual).name).toBe('small tin');
  } finally {
    await k.cleanUp();
  }
});
