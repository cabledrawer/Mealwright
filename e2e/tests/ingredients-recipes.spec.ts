import { test, expect, type Page } from './clock.ts';
import { checkPage, expectNoSidewaysScroll, inTheme, isPhone, setAccountTheme } from './a11y.ts';

// Ingredients and the recipes that use them (0.4, PR 6), against the real server: "Used in N
// recipes" on each row, the "Not in any recipe" filter, the recipes listed in the ingredient
// editor (each a link), removing an ingredient that recipes use ("not linked", and Undo), and a
// recipe's own made-ahead ingredient. Runs in the "phone 0.2" and "desktop 0.2" projects.

const key = () => ({ 'idempotency-key': crypto.randomUUID() });

async function call(page: Page, method: 'POST' | 'PUT' | 'DELETE', path: string, data?: object, status = 201) {
  const response = await page.request.fetch(`/api/v1${path}`, { method, data, headers: key() });
  expect(response.status(), `${method} ${path}: ${await response.text()}`).toBe(status);
  return (await response.json()) as Record<string, any>;
}

/** A word no other test uses, so a search finds only this test's own ingredients and recipes. */
const stamp = () =>
  `${test.info().project.name.startsWith('phone') ? 'p' : 'd'}${Date.now().toString(36)}${Math.floor(Math.random() * 1296).toString(36)}`;

async function makeFood(page: Page, name: string) {
  return (await call(page, 'POST', '/foods', { name, counted_as: 'weight' })).food.id as number;
}

const makeRecipe = (page: Page, name: string, foodIds: number[] = [], extra: object = {}) =>
  call(page, 'POST', '/recipes', {
    name,
    lines: foodIds.map((id) => ({ words: 'some', food_id: id, amount: 100, unit: 'g' })),
    ...extra,
  });

async function openEditor(page: Page, token: string, name: string) {
  await page.goto('/recipes/ingredients');
  await page.getByRole('searchbox', { name: 'Search ingredients' }).fill(token);
  await page
    .getByRole('region', { name: 'All ingredients' })
    .getByRole('button', { name: new RegExp(`^${name}`) })
    .click();
  return isPhone(page) ? page.getByRole('dialog', { name: `Edit ${name}` }) : page.getByRole('complementary', { name: `Edit ${name}` });
}

test.beforeEach(async ({ page }) => {
  await setAccountTheme(page, 'auto');
});

test('each row says how many recipes use the ingredient, and “Not in any recipe” lists the rest', async ({ page }) => {
  const token = stamp();
  const used = await makeFood(page, `Used ${token}`);
  const once = await makeFood(page, `Once ${token}`);
  await makeFood(page, `Alone ${token}`);
  await makeRecipe(page, `First ${token}`, [used, once]);
  await makeRecipe(page, `Second ${token}`, [used]);

  await page.goto('/recipes/ingredients');
  const list = page.getByRole('region', { name: 'All ingredients' });
  await page.getByRole('searchbox', { name: 'Search ingredients' }).fill(token);
  const row = (name: string) => list.getByRole('listitem').filter({ hasText: name });
  await expect(row(`Used ${token}`)).toBeVisible();
  // A screen reader hears it in full; on a phone the row says “2 recipes”, on a computer “2” under “Recipes”.
  await expect(row(`Used ${token}`)).toContainText('Used in 2 recipes');
  await expect(row(`Once ${token}`)).toContainText('Used in 1 recipe');
  await expect(row(`Alone ${token}`)).not.toContainText('Used in');
  await expect(row(`Alone ${token}`).getByText(/recipes?$/)).toHaveCount(0);
  // What shows: the word “recipes” after the number on a phone; only the number, under the
  // “Recipes” heading, on a computer (the word is still there for a screen reader).
  const word = await row(`Used ${token}`).locator('.word').boundingBox();
  if (isPhone(page)) expect(word!.width).toBeGreaterThan(20);
  else {
    expect(word!.width).toBeLessThanOrEqual(1);
    await expect(list.getByText('Recipes', { exact: true })).toBeAttached();
  }

  // The filter, with its count from the server, sits beside Staples.
  const counts = (await (await page.request.get('/api/v1/foods?limit=1')).json()).counts as { unused: number };
  const chip = page.getByRole('button', { name: `Not in any recipe · ${counts.unused}` });
  await expect(chip).toBeVisible();
  await chip.click();
  await expect(chip).toHaveAttribute('aria-pressed', 'true');
  await expect(row(`Alone ${token}`)).toBeVisible();
  await expect(row(`Used ${token}`)).toHaveCount(0);
  await checkPage(page);
});

test('the editor lists the recipes A to Z as links, and a link opens the recipe', async ({ page }) => {
  const token = stamp();
  const dal = await makeFood(page, `Dal ${token}`);
  const sambar = await makeRecipe(page, `Sambar ${token}`, [dal]);
  await makeRecipe(page, `Dosa ${token}`, [dal]);
  const rasam = await makeRecipe(page, `Rasam ${token}`, [dal]);

  const editor = await openEditor(page, token, `Dal ${token}`);
  await expect(editor.getByRole('heading', { name: 'Used in 3 recipes' })).toBeVisible();
  const links = editor.getByRole('link');
  await expect(links).toHaveText([`Dosa ${token}`, `Rasam ${token}`, `Sambar ${token}`]);
  await expect(links.nth(1)).toHaveAttribute('href', `/recipes/${rasam.id}`);
  await checkPage(page);

  await links.nth(2).click();
  await expect(page).toHaveURL(`/recipes/${sambar.id}`);
  await expect(page.getByRole('heading', { name: `Sambar ${token}`, level: 1 })).toBeVisible();
  if (isPhone(page)) {
    // The sheet got out of the way.
    await expect(page.getByRole('dialog')).toHaveCount(0);
  } else {
    // On a computer the recipe opens in the reading pane, beside the list.
    await expect(page.getByRole('region', { name: 'Recipe', exact: true })).toBeVisible();
    await expect(page.getByRole('region', { name: 'Recipe list' })).toBeVisible();
  }
});

test('from a recipe, the ingredient’s editor lists the other recipes; Enter on one opens it and the editor gets out of the way', async ({ page }) => {
  const token = stamp();
  const dal = await makeFood(page, `Dal ${token}`);
  const here = await makeRecipe(page, `Here ${token}`, [dal]);
  const there = await makeRecipe(page, `There ${token}`, [dal]);
  await page.goto(`/recipes/${here.id}`);
  await page.getByRole('region', { name: 'Ingredients' }).getByRole('button', { name: /some/ }).click();
  const editor = page.getByRole('dialog', { name: `Edit Dal ${token}` });
  await expect(editor.getByRole('heading', { name: 'Used in 2 recipes' })).toBeVisible();
  // Keyboard only: Tab to the link, Enter opens it.
  const link = editor.getByRole('link', { name: `There ${token}` });
  await link.focus();
  await expect(link).toBeFocused();
  await page.keyboard.press('Enter');
  await expect(page).toHaveURL(`/recipes/${there.id}`);
  await expect(page.getByRole('heading', { name: `There ${token}`, level: 1 })).toBeVisible();
  await expect(page.getByRole('dialog')).toHaveCount(0);
});

test('an ingredient no recipe uses says so', async ({ page }) => {
  const token = stamp();
  await makeFood(page, `Idle ${token}`);
  const editor = await openEditor(page, token, `Idle ${token}`);
  await expect(editor.getByRole('heading', { name: 'Used in recipes' })).toBeVisible();
  await expect(editor.getByText('Not in any recipe yet.')).toBeVisible();
  await expect(editor.getByText(/^Used in \d/)).toHaveCount(0);
  await expect(editor.getByRole('button', { name: 'Remove from Ingredients' })).toBeVisible();
  await checkPage(page);
});

test('a long list of recipes is folded, shows all and folds again, and never scrolls sideways', async ({ page }) => {
  const token = stamp();
  const dal = await makeFood(page, `Turmeric ${token}`);
  const long = 'Roasted cauliflower with tahini, pomegranate and a very long name that keeps on going and going';
  for (let i = 0; i < 7; i++) {
    await makeRecipe(page, i === 6 ? `${long} ${token}` : `Recipe ${i} ${token}`, [dal]);
  }
  const editor = await openEditor(page, token, `Turmeric ${token}`);
  await expect(editor.getByRole('heading', { name: 'Used in 7 recipes' })).toBeVisible();
  await expect(editor.getByRole('link')).toHaveCount(5);
  const more = editor.getByRole('button', { name: '+ 2 more recipes' });
  await expect(more).toHaveAttribute('aria-expanded', 'false');
  await more.focus();
  await page.keyboard.press('Enter');
  await expect(editor.getByRole('link')).toHaveCount(7);
  const fewer = editor.getByRole('button', { name: 'Show fewer' });
  await expect(fewer).toBeFocused();
  await checkPage(page);
  await page.evaluate(() => (document.documentElement.style.fontSize = '200%'));
  await expectNoSidewaysScroll(page);
  await page.keyboard.press('Space');
  await expect(editor.getByRole('link')).toHaveCount(5);
});

test('removing an ingredient that recipes use says so first; the lines keep their words and say “not linked”; Undo links them again', async ({
  page,
}) => {
  const token = stamp();
  const dal = await makeFood(page, `Remove ${token}`);
  const recipe = await makeRecipe(page, `Stew ${token}`, [dal]);
  await makeRecipe(page, `Soup ${token}`, [dal]);

  const editor = await openEditor(page, token, `Remove ${token}`);
  const hint = 'Used in 2 recipes. Their lines keep their words and show “not linked”.';
  await expect(editor.getByText(hint)).toBeVisible();
  await expect(editor.getByRole('button', { name: 'Remove from Ingredients' })).toHaveAccessibleDescription(hint);
  await checkPage(page);
  await editor.getByRole('button', { name: 'Remove from Ingredients' }).click();

  // At once, with Undo; the editor closes.
  const toast = page.getByRole('status').filter({ hasText: `Removed Remove ${token} from Ingredients` });
  await expect(toast).toBeVisible();
  await expect(page.getByRole('complementary', { name: `Edit Remove ${token}` })).toHaveCount(0);

  // The recipes keep the lines, unlinked.
  const first = async () =>
    (await (await page.request.get(`/api/v1/recipes/${recipe.id}`)).json()).lines[0] as {
      words: string;
      link: string;
      food: { id: number } | null;
    };
  await expect.poll(async () => (await first()).link).toBe('none');
  expect(await first()).toMatchObject({ words: 'some', food: null });

  // Undo links them again.
  await toast.getByRole('button', { name: 'Undo' }).click();
  await expect.poll(async () => (await first()).link).toBe('ingredient');
  expect((await first()).food?.id).toBe(dal);

  // Taken out again (through the API), the recipe page shows the line calmly: its words, “not linked”,
  // and nothing to tap.
  await call(page, 'DELETE', `/foods/${dal}`, undefined, 200);
  await page.goto(`/recipes/${recipe.id}`);
  await expect(page.getByRole('heading', { name: `Stew ${token}`, level: 1 })).toBeVisible();
  const line = page.getByRole('region', { name: 'Ingredients' }).getByRole('listitem').filter({ hasText: 'some' });
  await expect(line).toContainText('not linked');
  await expect(line.getByRole('button')).toHaveCount(0);
  await expect(line.getByRole('link')).toHaveCount(0);
  await checkPage(page);
});

test('a recipe’s own made-ahead ingredient says why it stays, with a link to the recipe', async ({ page }) => {
  const token = stamp();
  const batter = await makeRecipe(page, `Dosa batter ${token}`, [], { made_ahead: true, makes: { amount: 2, unit: 'litres' } });
  const name = batter.homemade.name as string;
  const editor = await openEditor(page, token, name);
  await expect(editor.getByText(/^Made by the recipe/)).toContainText(`Dosa batter ${token}`);
  await expect(editor.getByText(/Turn off Made ahead there to remove it\./)).toBeVisible();
  await expect(editor.getByRole('link', { name: `Dosa batter ${token}` })).toHaveAttribute('href', `/recipes/${batter.id}`);
  await expect(editor.getByRole('button', { name: 'Remove from Ingredients' })).toHaveCount(0);
  await checkPage(page);
});

test('a line whose recipe was deleted says “recipe removed” and opens nothing', async ({ page }) => {
  const token = stamp();
  const inner = await makeRecipe(page, `Podi ${token}`);
  const outer = await makeRecipe(page, `Rasam ${token}`, [], {
    lines: [{ words: 'the podi', amount: 2, unit: 'tbsp', recipe_id: inner.id }],
  });
  await call(page, 'DELETE', `/recipes/${inner.id}`, undefined, 200);
  await page.goto(`/recipes/${outer.id}`);
  await expect(page.getByRole('heading', { name: `Rasam ${token}`, level: 1 })).toBeVisible();
  const line = page.getByRole('region', { name: 'Ingredients' }).getByRole('listitem').filter({ hasText: 'the podi' });
  await expect(line).toContainText('recipe removed');
  await expect(line.getByRole('link')).toHaveCount(0);
  await expect(line.getByRole('button')).toHaveCount(0);
  for (const theme of ['light', 'dark'] as const) {
    await inTheme(page, theme);
    await expect(line).toContainText('recipe removed');
  }
  await checkPage(page);
});

test('Ingredients still works when the list cannot be loaded', async ({ page }) => {
  await page.route('**/api/v1/foods?**', (route) => route.fulfill({ status: 500, contentType: 'application/json', body: '{"detail":"Busy"}' }));
  await page.goto('/recipes/ingredients');
  await expect(page.getByRole('alert').filter({ hasText: 'Couldn’t load your ingredients.' })).toBeVisible();
  // The filter is still there, and no count is made up.
  await expect(page.getByRole('button', { name: 'Not in any recipe' })).toBeVisible();
  // No made-up "0 ingredients" while the list can't be loaded, and Try again is a button (0.5.1).
  await expect(page.getByText(/\d+ ingredients? ·/)).toHaveCount(0);
  await expect(page.getByRole('button', { name: 'Try again' }).first()).toBeVisible();
  await checkPage(page);
  await page.unroute('**/api/v1/foods?**');
  await page.getByRole('button', { name: 'Try again' }).first().click();
  await expect(page.getByText(/\d+ ingredients? ·/)).toBeVisible();
  await expect(page.getByRole('alert').filter({ hasText: 'Couldn’t load your ingredients.' })).toHaveCount(0);
});

test('Ingredients loads again by itself when a short drop is over (0.5.1)', async ({ page }) => {
  let dropped = 0;
  await page.route('**/api/v1/foods?**', (route) => (dropped++ === 0 ? route.abort('internetdisconnected') : route.continue()));
  await page.goto('/recipes/ingredients');
  await expect(page.getByText(/\d+ ingredients? ·/)).toBeVisible({ timeout: 15_000 });
  expect(dropped).toBeGreaterThan(1);
  await expect(page.getByRole('alert').filter({ hasText: 'Couldn’t' })).toHaveCount(0);
});
