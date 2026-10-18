import { test, expect, type Page } from '@playwright/test';
import { checkPage, isPhone, setAccountTheme } from './a11y.ts';

// The Ingredients page and the ingredient editor (0.2), against the real server.
// Runs in the "phone 0.2" and "desktop 0.2" projects, signed in as the test admin.

/** Make a food through the API, with a unique name so tests don't trip over each other. */
async function makeFood(page: Page, name: string) {
  const unique = `${name} ${test.info().project.name} ${Date.now()}`;
  const response = await page.request.post('/api/v1/foods', {
    data: { name: unique, counted_as: 'weight' },
    headers: { 'idempotency-key': crypto.randomUUID() },
  });
  expect(response.status(), await response.text()).toBe(201);
  return {
    name: unique,
    id: ((await response.json()) as { food: { id: number } }).food.id,
  };
}

async function openEditor(page: Page, name: string) {
  await page.goto('/recipes/ingredients');
  await page.getByRole('searchbox', { name: 'Search ingredients' }).fill(name);
  await page
    .getByRole('region', { name: 'All ingredients' })
    .getByRole('button', { name: new RegExp(`^${name}`) })
    .click();
  return isPhone(page)
    ? page.getByRole('dialog', { name: `Edit ${name}` })
    : page.getByRole('complementary', { name: `Edit ${name}` });
}

test.beforeEach(async ({ page }) => {
  await setAccountTheme(page, 'auto');
});

test('Ingredients opens from Recipes and passes the accessibility checks', async ({ page }) => {
  await makeFood(page, 'Toor dal');
  await page.goto('/recipes');
  if (isPhone(page)) await page.getByRole('link', { name: 'Ingredients' }).click();
  else
    await page
      .getByRole('complementary', { name: 'Sidebar' })
      .getByRole('link', { name: 'Ingredients' })
      .click();
  await expect(page).toHaveURL('/recipes/ingredients');
  await expect(page.getByRole('heading', { level: 1 })).toHaveText('Ingredients');
  await expect(
    page.getByText(/ingredients? · shared by (your )?recipes, pantry and shopping/),
  ).toBeVisible();
  await checkPage(page);
});

test('search finds a food by another name', async ({ page }) => {
  const food = await makeFood(page, 'Toor dal');
  const editor = await openEditor(page, food.name);
  await editor.getByRole('button', { name: '+ Add' }).first().click();
  await page.keyboard.type(`arhar ${food.id}`);
  await page.keyboard.press('Enter');
  await expect(editor.getByRole('button', { name: `Remove arhar ${food.id}` })).toBeVisible();
  if (isPhone(page)) await editor.getByRole('button', { name: 'Done' }).click();
  await page.getByRole('searchbox', { name: 'Search ingredients' }).fill(`arhar ${food.id}`);
  await expect(
    page
      .getByRole('region', { name: 'All ingredients' })
      .getByRole('button', { name: new RegExp(`^${food.name}`) }),
  ).toBeVisible();
});

test('changes save as you go, and Undo puts them back', async ({ page }) => {
  const food = await makeFood(page, 'Moong dal');
  const editor = await openEditor(page, food.name);
  const staple = editor.getByRole('switch', { name: 'Staple' });
  await staple.click();
  await expect(staple).toHaveAttribute('aria-checked', 'true');
  const toast = page.getByRole('status').filter({ hasText: /./ }).last();
  await expect(toast.getByRole('button', { name: 'Undo' })).toBeVisible();

  // Saved on the server…
  const saved = await (await page.request.get(`/api/v1/foods/${food.id}`)).json();
  expect(saved.staple).toBe(true);

  // …and Undo takes it back.
  await toast.getByRole('button', { name: 'Undo' }).click();
  await expect(page.getByText('Undone')).toBeVisible();
  await expect
    .poll(async () => (await (await page.request.get(`/api/v1/foods/${food.id}`)).json()).staple)
    .toBe(false);
});

test('the editor passes the accessibility checks', async ({ page }) => {
  const food = await makeFood(page, 'Chana dal');
  const editor = await openEditor(page, food.name);
  await expect(editor.getByRole('switch', { name: 'Staple' })).toBeVisible();
  await checkPage(page);
});

test('an other name can become its own ingredient, and Undo joins it back', async ({ page }) => {
  const food = await makeFood(page, 'Drumsticks');
  const other = `moringa ${food.id}`;
  const added = await page.request.post(`/api/v1/foods/${food.id}/other-names`, {
    data: { name: other },
    headers: { 'idempotency-key': crypto.randomUUID() },
  });
  expect(added.status()).toBe(201);
  const editor = await openEditor(page, food.name);
  await editor.getByRole('button', { name: other, exact: true }).click();
  await editor.getByRole('button', { name: 'Make its own ingredient' }).click();

  const named = async () =>
    (
      (await (await page.request.get(`/api/v1/foods?q=${encodeURIComponent(other)}`)).json()) as {
        foods: { name: string }[];
      }
    ).foods.map((f) => f.name);
  await expect.poll(named).toContain(other);

  await page.getByRole('button', { name: 'Undo', exact: true }).click();
  await expect.poll(named).not.toContain(other);
});

test('on a long page the sidebar, with its theme switch, and the editor stay in view', async ({
  page,
}) => {
  test.skip(isPhone(page), 'desktop layout');
  for (let i = 0; i < 14; i++) await makeFood(page, `Long list ${i}`);
  await page.setViewportSize({ width: 1280, height: 520 });
  await page.goto('/recipes/ingredients');
  const list = page.getByRole('region', { name: 'All ingredients' });
  await list.getByRole('button').first().waitFor();
  // Scroll to the bottom (again, if the list is still growing).
  await expect
    .poll(() =>
      page.evaluate(() => {
        window.scrollTo(0, document.documentElement.scrollHeight);
        return window.scrollY;
      }),
    )
    .toBeGreaterThan(200);
  const theme = page
    .getByRole('complementary', { name: 'Sidebar' })
    .getByRole('group', { name: 'Theme' });
  await expect(theme).toBeInViewport();
  await expect(page.getByRole('complementary', { name: /^Edit/ })).toBeInViewport();
});

test('Recent changes lists ingredient changes, with Undo', async ({ page }) => {
  const food = await makeFood(page, 'Moringa');
  const edited = await page.request.patch(`/api/v1/foods/${food.id}`, {
    data: { staple: true },
    headers: { 'idempotency-key': crypto.randomUUID() },
  });
  expect(edited.ok()).toBe(true);
  await page.goto('/recipes/ingredients');
  // Desktop: a one-line "Recent changes · N" bar above the editor opens the list in the side
  // column. Phone: a "Recent changes" button opens a sheet.
  if (isPhone(page)) await page.getByRole('button', { name: 'Recent changes' }).click();
  else {
    const bar = page.getByRole('button', { name: /^Recent changes( · \d+\+?)?$/ });
    await checkPage(page); // closed: the editor and the bar
    await bar.click();
  }
  const recent = isPhone(page)
    ? page.getByRole('dialog', { name: 'Recent changes' })
    : page.getByRole('region', { name: 'Recent changes' });
  await expect(recent.getByText(`${food.name} is now a staple`)).toBeVisible();
  await expect(recent.getByText(`Added ${food.name}`, { exact: false })).toBeVisible();
  if (!isPhone(page)) await checkPage(page); // open, before any toast is on screen
  await recent.getByRole('button', { name: `Undo: ${food.name} is now a staple` }).click();
  await expect(page.getByRole('status').filter({ hasText: `Undone: ${food.name} is now a staple` })).toBeVisible();
  const now = await (await page.request.get(`/api/v1/foods/${food.id}`)).json();
  expect(now.staple).toBe(false);
  // The list shows the Undo itself, and the Undone change loses its Undo button.
  await expect(recent.getByText(`Undid: ${food.name} is now a staple`)).toBeVisible();
  await expect(
    recent.getByRole('button', { name: `Undo: ${food.name} is now a staple` }),
  ).toHaveCount(0);
  if (!isPhone(page)) {
    // Close brings the editor back, and focus returns to the bar.
    await recent.getByRole('button', { name: 'Close' }).click();
    await expect(page.getByRole('complementary', { name: /^Edit/ })).toBeVisible();
    await expect(page.getByRole('button', { name: /^Recent changes( · \d+\+?)?$/ })).toBeFocused();
  }
});
