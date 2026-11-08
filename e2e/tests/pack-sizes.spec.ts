import { test, expect, type Page } from './clock.ts';
import { checkPage, isPhone, setAccountTheme } from './a11y.ts';

// Pack sizes on Ingredients (F121) and the suggested Usual shop of a new ingredient (cabledrawer
// 7 Nov), against the real server. Phone: the pack is a line under the name; computer: a column.

const api = (page: Page) => page.request;

async function makeFood(page: Page, name: string, extra: Record<string, unknown> = {}) {
  const response = await api(page).post('/api/v1/foods', {
    data: { name, counted_as: 'weight', ...extra },
    headers: { 'idempotency-key': crypto.randomUUID() },
  });
  expect(response.status(), await response.text()).toBe(201);
  return ((await response.json()) as { food: { id: number } }).food.id;
}

async function addSize(page: Page, id: number, name: string, amount: number) {
  const response = await api(page).post(`/api/v1/foods/${id}/sizes`, {
    data: { name, amount },
    headers: { 'idempotency-key': crypto.randomUUID() },
  });
  expect(response.status(), await response.text()).toBe(201);
}

async function find(page: Page, name: string) {
  await page.goto('/recipes/ingredients');
  await page.getByRole('searchbox', { name: 'Search ingredients' }).fill(name);
  const list = page.getByRole('region', { name: 'All ingredients' });
  await expect(list.getByRole('button', { name: new RegExp(`^${name}`) })).toBeVisible();
  return list;
}

test.beforeEach(async ({ page }) => {
  await setAccountTheme(page, 'auto');
});

test('the Pack column shows the Usual size and +1 for another', async ({ page }) => {
  const name = `Packed ghee ${test.info().project.name} ${Date.now()}`;
  const id = await makeFood(page, name);
  await addSize(page, id, 'jar', 500);
  await addSize(page, id, 'tin', 1000);
  const list = await find(page, name);
  const row = list.getByRole('listitem').filter({ hasText: name });
  await expect(row.getByText('jar · 500 g')).toBeVisible();
  const plus = row.getByRole('button', { name: 'Also: tin · 1 kg' });
  await expect(plus).toHaveText('+1');
  await expect(plus).toHaveAttribute('title', 'Also: tin · 1\u00a0kg');
  await plus.click();
  await expect(row.getByText('Also: tin · 1 kg', { exact: true })).toBeVisible();
  if (isPhone(page)) {
    // A line under the name.
    const nameBox = await row.getByText(name, { exact: true }).boundingBox();
    const packBox = await row.getByText('jar · 500 g').boundingBox();
    expect(packBox!.y).toBeGreaterThan(nameBox!.y);
  } else {
    await expect(page.getByRole('columnheader')).toHaveCount(0); // a list, not a table
    await expect(page.getByText('Pack', { exact: true })).toBeVisible();
  }
  const scrollWidth = await page.evaluate(() => document.documentElement.scrollWidth);
  expect(scrollWidth).toBeLessThanOrEqual(page.viewportSize()!.width);
});

test('a staple shows its pack in the Pack column, like any other ingredient', async ({ page }) => {
  const name = `Packed rice ${test.info().project.name} ${Date.now()}`;
  const id = await makeFood(page, name, { staple: true });
  await addSize(page, id, 'bag', 5000);
  const list = await find(page, name);
  const row = list.getByRole('listitem').filter({ hasText: name });
  await expect(row.getByText('bag · 5 kg')).toBeVisible();
  await expect(row.getByRole('button', { name: /^Add a pack/ })).toHaveCount(0);
});

test('Add a pack offers common sizes, and a tap makes one the Usual size', async ({ page }) => {
  const name = `Packed tamarind ${test.info().project.name} ${Date.now()}`;
  await makeFood(page, name);
  const list = await find(page, name);
  const row = list.getByRole('listitem').filter({ hasText: name });
  await row.getByRole('button', { name: `Add a pack for ${name}` }).click();
  await expect(row.getByText('Common sizes:')).toBeVisible();
  await expect(row.getByRole('button', { name: 'Other…' })).toBeVisible();
  await row.getByRole('button', { name: '500 g', exact: true }).click();
  await expect(row.getByText('pack · 500 g')).toBeVisible();
  await expect(row.getByRole('button', { name: /^Add a pack/ })).toHaveCount(0);
});

test('on the computer, the open ingredient’s Add a pack is readable on its green row', async ({
  page,
}) => {
  test.skip(isPhone(page), 'the open row is green only on the computer');
  const name = `Packed sumac ${test.info().project.name} ${Date.now()}`;
  await makeFood(page, name);
  const list = await find(page, name);
  await list.getByRole('button', { name: new RegExp(`^${name}`) }).click();
  const row = list.getByRole('listitem').filter({ hasText: name });
  await expect(row).toHaveClass(/\bopen\b/);
  await expect(row.getByRole('button', { name: `Add a pack for ${name}` })).toBeVisible();
  await checkPage(page); // axe in light and dark: the button's words on the green row
});

test('a new ingredient gets the suggested shop, and one tap changes it', async ({ page }) => {
  const project = test.info().project.name;
  const stamp = Date.now();
  const shop = `Indian grocer ${project} ${stamp}`;
  const created = await api(page).post('/api/v1/shops', {
    data: { name: shop },
  });
  expect(created.status(), await created.text()).toBe(201);
  // A specialist ingredient from the table; it has to be the bare name, so one is free only on a fresh run.
  const bare = isPhone(page) ? 'Poha' : 'Jaggery';
  const exists = await api(page).get(`/api/v1/foods?q=${bare}`);
  const taken = ((await exists.json()) as { foods: { name: string }[] }).foods.some(
    (f) => f.name.toLowerCase() === bare.toLowerCase(),
  );
  test.skip(taken, 'the ingredient is there from an earlier run');
  await page.goto('/recipes/ingredients');
  const button = isPhone(page)
    ? page.getByRole('button', { name: 'New ingredient', exact: true })
    : page.getByRole('button', { name: '+ New ingredient' });
  await button.click();
  const question = page.getByRole('dialog', { name: 'Pantry keeps it by' });
  await question.getByRole('textbox', { name: 'Name' }).fill(bare);
  await question.getByRole('button', { name: 'Add', exact: true }).click();
  const editor = isPhone(page)
    ? page.getByRole('dialog', { name: `Edit ${bare}` })
    : page.getByRole('complementary', { name: `Edit ${bare}` });
  const usual = editor.getByLabel('Usual shop');
  // The first shop that names a kind of grocer wins; an earlier run's may come first.
  await expect(usual.locator('option:checked')).toHaveText(/^Indian grocer/);
  await usual.selectOption({ label: 'Any shop' });
  await expect(usual.locator('option:checked')).toHaveText('Any shop');
});
