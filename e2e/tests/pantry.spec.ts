import { test, expect, type Page } from '@playwright/test';
import { checkPage, isPhone, setAccountTheme } from './a11y.ts';

// The Pantry (0.2), against the real server, on phone and desktop. Each test makes its
// own foods with unique names, so tests don't trip over each other.

const key = () => ({ 'idempotency-key': crypto.randomUUID() });

async function api(page: Page, method: 'POST' | 'PATCH', path: string, data: object) {
  const response = await page.request.fetch(`/api/v1${path}`, { method, data, headers: key() });
  expect(response.ok(), `${method} ${path}: ${await response.text()}`).toBe(true);
  return response.json();
}

/** A food sold in packets, with stock in the fridge. */
async function stocked(page: Page, name: string, useByDays: number | null = 1) {
  const unique = `${name} ${test.info().project.name.replace(/\W/g, '')} ${Date.now()}`;
  const places = (await (await page.request.get('/api/v1/places')).json()) as {
    id: number;
    name: string;
  }[];
  const fridge = places.find((p) => p.name === 'Fridge')!.id;
  const { food } = await api(page, 'POST', '/foods', { name: unique, place_id: fridge });
  await api(page, 'POST', `/foods/${food.id}/sizes`, { name: 'pack', amount: 200 });
  const { today } = await (await page.request.get('/api/v1/household')).json();
  const useBy = new Date(`${today}T12:00:00Z`);
  useBy.setUTCDate(useBy.getUTCDate() + (useByDays ?? 0));
  const added = await api(page, 'POST', '/stock', {
    food_id: food.id,
    amount: { amount: 1, unit: 'pack' },
    ...(useByDays === null ? {} : { use_by: useBy.toISOString().slice(0, 10) }),
  });
  return { id: food.id as number, name: unique, lot: added.groups[0].lots[0].id as number };
}

const lotsOf = async (page: Page, foodId: number) => {
  const pantry = await (await page.request.get('/api/v1/pantry')).json();
  return pantry.places
    .flatMap((p: { groups: { food: { id: number }; lots: unknown[] }[] }) => p.groups)
    .filter((g: { food: { id: number } }) => g.food.id === foodId)
    .flatMap((g: { lots: unknown[] }) => g.lots).length as number;
};

test.beforeEach(async ({ page }) => {
  await setAccountTheme(page, 'auto');
});

test('the Pantry shows what is where, and passes the accessibility checks', async ({ page }) => {
  const food = await stocked(page, 'Paneer');
  await page.goto('/pantry');
  await expect(page.getByRole('heading', { level: 1 })).toHaveText('Pantry');
  if (isPhone(page)) {
    await expect(page.getByRole('tab', { name: 'All' })).toHaveAttribute('aria-selected', 'true');
    // cabledrawer (17 Oct): All · Fridge · Freezer · Cupboard · More (Use soon is under More).
    await expect(page.getByRole('tab', { name: 'Cupboard' })).toBeVisible();
    await expect(page.getByRole('tab', { name: /More/ })).toBeVisible();
  } else {
    for (const place of ['Fridge', 'Freezer', 'Cupboard', 'Spice rack']) {
      await expect(page.getByRole('heading', { name: place, level: 2 })).toBeVisible();
    }
  }
  await expect(
    page.getByRole('button', { name: new RegExp(`^${food.name}`) }).first(),
  ).toBeVisible();
  await checkPage(page);
});

test('Used from Use soon takes it out, and Undo puts it back', async ({ page }) => {
  const food = await stocked(page, 'Spinach', 0);
  await page.goto('/pantry');
  if (isPhone(page)) {
    await page.getByRole('tab', { name: /More/ }).click();
    await page
      .getByRole('list', { name: 'More' })
      .getByRole('button', { name: 'Use soon' })
      .click();
  }
  const row = page
    .getByRole('listitem')
    .filter({ hasText: food.name })
    .filter({
      has: page.getByRole('button', { name: 'Binned' }),
    });
  await row.first().getByRole('button', { name: 'Used' }).click();
  await expect.poll(() => lotsOf(page, food.id)).toBe(0);
  await page.getByRole('button', { name: 'Undo', exact: true }).click();
  await expect.poll(() => lotsOf(page, food.id)).toBe(1);
});

test('Add to pantry adds what was chosen, where it lives', async ({ page }) => {
  const food = await stocked(page, 'Yoghurt', null);
  await page.goto('/pantry');
  await page
    .getByRole('button', { name: /Add to pantry/ })
    .first()
    .click();
  const sheet = page.getByRole('dialog', { name: 'Add to pantry' });
  await sheet.getByRole('searchbox', { name: 'Find an ingredient' }).fill(food.name);
  await sheet.getByRole('button', { name: new RegExp(`^${food.name}`) }).click();
  await sheet.getByRole('radio', { name: '2 packs' }).click();
  await sheet.getByRole('radio', { name: '+1 week' }).click();
  await expect(sheet.getByLabel(/^Where/)).toHaveValue(/\d+/);
  await sheet.getByRole('button', { name: 'Add to pantry' }).click();
  await expect.poll(() => lotsOf(page, food.id)).toBe(3);
  await expect(page.getByRole('status').getByText(/Added 2\s+packs/)).toBeVisible();
});

test('Ctrl+Z undoes a pantry change on desktop', async ({ page }) => {
  test.skip(isPhone(page), 'Ctrl+Z is a desktop keyboard shortcut');
  const food = await stocked(page, 'Coriander', 0);
  await page.goto('/pantry');
  const side = page.getByRole('complementary', { name: /Use soon/ });
  await side
    .getByRole('listitem')
    .filter({ hasText: food.name })
    .getByRole('button', { name: 'Binned' })
    .click();
  await expect.poll(() => lotsOf(page, food.id)).toBe(0);
  await page.locator('h1').click();
  await page.keyboard.press('ControlOrMeta+z');
  await expect.poll(() => lotsOf(page, food.id)).toBe(1);
});

test('Find in pantry finds an ingredient by its other name', async ({ page }) => {
  test.skip(isPhone(page), 'the search box is on desktop');
  const food = await stocked(page, 'Toordal', null);
  await api(page, 'POST', `/foods/${food.id}/other-names`, {
    name: 'thuvaram paruppu',
  });
  await page.goto('/pantry');
  await page.getByRole('searchbox', { name: 'Find in pantry' }).fill('thuvaram');
  await expect(page.getByRole('button', { name: new RegExp(`^${food.name}`) })).toBeVisible();
  await page.getByRole('searchbox', { name: 'Find in pantry' }).fill('zzzz');
  await expect(page.getByText('Nothing called “zzzz” here.').first()).toBeVisible();
  // The header counts match: "0 items" everywhere while nothing is found.
  await expect(page.getByText(/^[1-9]\d* items?$/)).toHaveCount(0);
});

test('+ Staple makes a new ingredient, with no stock', async ({ page }) => {
  test.skip(isPhone(page), 'the Staples panel is on desktop');
  const name = `Pepper ${Date.now()}`;
  await page.goto('/pantry');
  await page.getByRole('button', { name: '+ Staple' }).click();
  await page.getByRole('searchbox', { name: 'Make an ingredient a staple' }).fill(name);
  await page.getByRole('button', { name: `+ New ingredient: “${name}”` }).click();
  await expect(page.getByRole('button', { name })).toBeVisible();
  const foods = await (
    await page.request.get(`/api/v1/foods?q=${encodeURIComponent(name)}`)
  ).json();
  expect(foods.foods[0].staple).toBe(true);
  const pantry = await (await page.request.get('/api/v1/pantry')).json();
  expect(JSON.stringify(pantry.places)).not.toContain(name);
});

test('the pack lines open the pack menu, with the choices for a full pack', async ({ page }) => {
  const food = await stocked(page, 'Cheese', 3);
  await page.goto('/pantry');
  await page
    .getByRole('button', { name: new RegExp(`^${food.name}`) })
    .first()
    .click();
  const pack = page.getByRole('list', { name: `Packets of ${food.name}` }).getByRole('button');
  await expect(pack).toHaveCount(1);
  const box = (await pack.boundingBox())!;
  expect(box.height).toBeGreaterThanOrEqual(44);
  await pack.click();
  const menu = page.getByRole('dialog', { name: new RegExp(food.name) });
  await expect(menu.getByRole('radio', { name: 'Full' })).toHaveAttribute('aria-checked', 'true');
  await expect(menu.getByRole('radio', { name: '½ left' })).toBeVisible();
  await checkPage(page);
});

test('Add to pantry has a Today use-by', async ({ page }) => {
  const food = await stocked(page, 'Milk', null);
  await page.goto('/pantry');
  await page
    .getByRole('button', { name: /Add to pantry/ })
    .first()
    .click();
  const sheet = page.getByRole('dialog', { name: 'Add to pantry' });
  await sheet.getByRole('searchbox', { name: 'Find an ingredient' }).fill(food.name);
  await sheet.getByRole('button', { name: new RegExp(`^${food.name}`) }).click();
  await sheet.getByRole('radio', { name: '1 pack' }).click();
  await sheet.getByRole('radio', { name: 'Today' }).click();
  await sheet.getByRole('button', { name: 'Add to pantry' }).click();
  const { today } = await (await page.request.get('/api/v1/household')).json();
  await expect
    .poll(async () => {
      const pantry = await (await page.request.get('/api/v1/pantry')).json();
      const lots = pantry.places
        .flatMap(
          (p: { groups: { food: { id: number }; lots: { use_by: string }[] }[] }) => p.groups,
        )
        .filter((g: { food: { id: number } }) => g.food.id === food.id)
        .flatMap((g: { lots: { use_by: string }[] }) => g.lots);
      return lots.map((l: { use_by: string | null }) => l.use_by).filter(Boolean);
    })
    .toEqual([today]);
});

const SIZES = [320, 390] as const;
for (const width of SIZES) {
  for (const theme of ['light', 'dark'] as const) {
    test(`the Add to pantry date field fits a ${width} px phone, ${theme} theme`, async ({
      page,
    }) => {
      test.skip(!isPhone(page), 'the bottom sheet is the phone layout');
      await page.emulateMedia({ colorScheme: theme }); // the account is on Auto
      await page.setViewportSize({ width, height: 800 });
      const food = await stocked(page, 'Lentils', null);
      await page.goto('/pantry');
      await page
        .getByRole('button', { name: /Add to pantry/ })
        .first()
        .click();
      const sheet = page.getByRole('dialog', { name: 'Add to pantry' });
      await sheet.getByRole('searchbox', { name: 'Find an ingredient' }).fill(food.name);
      await sheet.getByRole('button', { name: new RegExp(`^${food.name}`) }).click();
      await sheet.getByRole('radio', { name: 'Pick a date' }).click();
      const date = sheet.getByLabel('Date', { exact: true });
      await expect(date).toBeVisible();
      const fits = await sheet.evaluate((dialog) => {
        const field = dialog.querySelector('input[type="date"]')!.getBoundingClientRect();
        const box = dialog.getBoundingClientRect();
        return {
          scrollWidth: dialog.scrollWidth,
          clientWidth: dialog.clientWidth,
          fieldRight: field.right,
          boxRight: box.right,
          fieldLeft: field.left,
          boxLeft: box.left,
        };
      });
      expect(fits.scrollWidth).toBeLessThanOrEqual(fits.clientWidth);
      expect(fits.fieldRight).toBeLessThanOrEqual(fits.boxRight);
      expect(fits.fieldLeft).toBeGreaterThanOrEqual(fits.boxLeft);
      await page.screenshot({
        path: `review-shots/fix-0.2.1/add-sheet-${width}-${theme}.png`,
      });
    });
  }
}
