import { test, expect } from '@playwright/test';
import { isPhone } from './a11y.ts';

// Ctrl+Z / Cmd+Z (spec, History and undo): undoes your own last change, except in a
// text box, where the browser undoes the typing. Desktop only: phones have no keyboard
// shortcut.

test.beforeEach(async ({ page }) => {
  test.skip(isPhone(page), 'Ctrl+Z is a desktop keyboard shortcut');
});

async function makeFood(page: import('@playwright/test').Page) {
  const name = `Undo test ${Date.now()}`;
  const response = await page.request.post('/api/v1/foods', {
    data: { name },
    headers: { 'idempotency-key': crypto.randomUUID() },
  });
  expect(response.status()).toBe(201);
  return {
    name,
    id: ((await response.json()) as { food: { id: number } }).food.id,
  };
}

const stapleOf = async (page: import('@playwright/test').Page, id: number) =>
  (await (await page.request.get(`/api/v1/foods/${id}`)).json()).staple as boolean;

test('Ctrl+Z undoes your last change', async ({ page }) => {
  const food = await makeFood(page);
  await page.goto('/recipes/ingredients');
  await page.getByRole('searchbox', { name: 'Search ingredients' }).fill(food.name);
  await page
    .getByRole('region', { name: 'All ingredients' })
    .getByRole('button', { name: new RegExp(`^${food.name}`) })
    .click();
  await page.getByRole('switch', { name: 'Staple' }).click();
  await expect.poll(() => stapleOf(page, food.id)).toBe(true);

  await page.locator('h1').click(); // focus out of any text box
  await page.keyboard.press('ControlOrMeta+z');
  await expect.poll(() => stapleOf(page, food.id)).toBe(false);
});

test('in a text box, Ctrl+Z undoes the typing instead', async ({ page }) => {
  const food = await makeFood(page);
  await page.goto('/recipes/ingredients');
  await page.getByRole('searchbox', { name: 'Search ingredients' }).fill(food.name);
  await page
    .getByRole('region', { name: 'All ingredients' })
    .getByRole('button', { name: new RegExp(`^${food.name}`) })
    .click();
  await page.getByRole('switch', { name: 'Staple' }).click();
  await expect.poll(() => stapleOf(page, food.id)).toBe(true);

  const search = page.getByRole('searchbox', { name: 'Search ingredients' });
  await search.click();
  await page.keyboard.type('xyz');
  await page.keyboard.press('ControlOrMeta+z');
  await expect(search).not.toHaveValue(`${food.name}xyz`);
  expect(await stapleOf(page, food.id)).toBe(true); // the change is still there
});

test('after a reload, Ctrl+Z still undoes your last change', async ({ page }) => {
  const food = await makeFood(page);
  await page.request.patch(`/api/v1/foods/${food.id}`, {
    data: { staple: true },
    headers: { 'idempotency-key': crypto.randomUUID() },
  });
  await page.goto('/recipes/ingredients');
  await page.locator('h1').click();
  await page.keyboard.press('ControlOrMeta+z');
  await expect.poll(() => stapleOf(page, food.id)).toBe(false);
});
