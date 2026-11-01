import { test, expect, type Page } from './clock.ts';
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

test('the Ingredients title never breaks inside a word, with New ingredient beside it', async ({
  page,
}) => {
  await page.goto('/recipes/ingredients');
  const title = page.getByRole('heading', { level: 1, name: 'Ingredients' });
  await expect(title).toBeVisible();
  // Each word of the title sits on one line (a word broken in two has two boxes).
  const boxesPerWord = await title.evaluate((h1) => {
    const text = h1.firstChild as Text;
    return [...text.data.matchAll(/\S+/g)].map((match) => {
      const range = document.createRange();
      range.setStart(text, match.index);
      range.setEnd(text, match.index + match[0].length);
      return range.getClientRects().length;
    });
  });
  expect(boxesPerWord).toEqual([1]);
  // A phone shows the round +, a computer the words; nothing scrolls sideways.
  const button = isPhone(page)
    ? page.getByRole('button', { name: 'New ingredient', exact: true })
    : page.getByRole('button', { name: '+ New ingredient' });
  await expect(button).toBeVisible();
  const scrollWidth = await page.evaluate(() => document.documentElement.scrollWidth);
  expect(scrollWidth).toBeLessThanOrEqual(page.viewportSize()!.width);
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

test('F97: a name that is not there can be added straight from the search box', async ({
  page,
}) => {
  const food = await makeFood(page, 'Chilli powder');
  await page.goto('/recipes/ingredients');
  const search = page.getByRole('searchbox', { name: 'Search ingredients' });
  const list = page.getByRole('region', { name: 'All ingredients' });
  const start = food.name.split(' ').slice(0, 2).join(' ');
  const wanted = `${start} flakes ${Date.now()}`;
  // Part of a name that exists finds it, and still offers the new name at the end.
  await search.fill(start);
  await expect(list.getByRole('button', { name: new RegExp(`^${food.name}`) })).toBeVisible();
  await expect(list.getByRole('button', { name: /^\+ New ingredient: / })).toBeVisible();
  // The exact name offers nothing.
  await search.fill(food.name.toUpperCase());
  await expect(list.getByRole('button', { name: new RegExp(`^${food.name}`, 'i') })).toBeVisible();
  await expect(list.getByRole('button', { name: /^\+ New ingredient: / })).toHaveCount(0);
  // A new name: the question comes with the name shown, then the new ingredient opens.
  await search.fill(wanted);
  await list.getByRole('button', { name: `+ New ingredient: \u201c${wanted}\u201d` }).click();
  const question = page.getByRole('dialog', { name: 'Pantry keeps it by' });
  await expect(question.getByText(wanted, { exact: true })).toBeVisible();
  await question.getByRole('radio', { name: /By weight/ }).click();
  await question.getByRole('button', { name: 'Add', exact: true }).click();
  await expect(
    isPhone(page)
      ? page.getByRole('dialog', { name: `Edit ${wanted}` })
      : page.getByRole('complementary', { name: `Edit ${wanted}` }),
  ).toBeVisible();
  await expect(search).toHaveValue('');
});

test('changes save as you go, and Undo puts them back', async ({ page }) => {
  const food = await makeFood(page, 'Moong dal');
  const editor = await openEditor(page, food.name);
  const staple = editor.getByRole('switch', { name: 'Staple' });
  await staple.click();
  await expect(staple).toHaveAttribute('aria-checked', 'true');
  const toast = page.getByRole('status').filter({ hasText: /./ }).last();
  await expect(toast.getByRole('button', { name: 'Undo', exact: true })).toBeVisible();

  // Saved on the server… (the toast shows at once, before the server has answered)
  await expect
    .poll(async () => (await (await page.request.get(`/api/v1/foods/${food.id}`)).json()).staple)
    .toBe(true);

  // …and Undo takes it back.
  await toast.getByRole('button', { name: 'Undo', exact: true }).click();
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

test('an ingredient brought back by a Pantry Undo says so in Recent changes, and its removal loses its Undo', async ({
  page,
}) => {
  const food = await makeFood(page, 'Lemon');
  const key = () => ({ 'idempotency-key': crypto.randomUUID() });
  const stocked = await page.request.post('/api/v1/stock', {
    data: { food_id: food.id, amount: { amount: 100, unit: 'g' } },
    headers: key(),
  });
  expect(stocked.status(), await stocked.text()).toBe(201);
  const lot = ((await stocked.json()) as { groups: { lots: { id: number }[] }[] }).groups[0].lots[0];
  const used = await page.request.post(`/api/v1/stock/${lot.id}/used`, { headers: key() });
  expect(used.ok(), await used.text()).toBe(true);
  const usedId = ((await used.json()) as { change: { id: number } }).change.id;
  const removed = await page.request.delete(`/api/v1/foods/${food.id}`, { headers: key() });
  expect(removed.ok(), await removed.text()).toBe(true);
  // Undo "Used 100 g" in Pantry: the stock goes back, so the ingredient comes back.
  const undone = await page.request.post(`/api/v1/changes/${usedId}/undo`, { headers: key() });
  expect(undone.ok(), await undone.text()).toBe(true);

  await page.goto('/recipes/ingredients');
  if (isPhone(page)) await page.getByRole('button', { name: 'Recent changes' }).click();
  else await page.getByRole('button', { name: /^Recent changes( · \d+\+?)?$/ }).click();
  const recent = isPhone(page)
    ? page.getByRole('dialog', { name: 'Recent changes' })
    : page.getByRole('region', { name: 'Recent changes' });
  await expect(recent.getByText(`${food.name} is back in Ingredients`)).toBeVisible();
  await expect(recent.getByText(`Removed ${food.name} from Ingredients`)).toBeVisible();
  // Neither line has an Undo: the "back" line never does, and the removal no longer stands.
  await expect(recent.getByRole('button', { name: `Undo: ${food.name} is back in Ingredients` })).toHaveCount(0);
  await expect(recent.getByRole('button', { name: `Undo: Removed ${food.name} from Ingredients` })).toHaveCount(0);
  await checkPage(page);
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
