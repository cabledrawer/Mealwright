import { test, expect, type BrowserContext, type Page } from './clock.ts';
import {
  THEMES,
  checkPage,
  expectNoAxeViolations,
  expectNoSidewaysScroll,
  expectTouchTargets,
  isPhone,
  setAccountTheme,
} from './a11y.ts';

// The All recipes page (0.4, PR 3a), against the real server: the rows and their stock lines,
// search, the filter row, and every state of the screen (spec "Keeping the UI good", item 2):
// empty, loading, failed, offline, one, many, long names and text at 200%. Runs in the
// "phone 0.4 recipes" and "desktop 0.4 recipes" projects, signed in as the test admin.
//
// Recipes and ingredients are made through the API with names that are unique to the test, and
// each test searches for its own, so tests don't trip over each other or over other files.

const key = () => ({ 'idempotency-key': crypto.randomUUID() });

async function call(page: Page, method: 'POST' | 'PUT', path: string, data: object, status = 201) {
  const response = await page.request.fetch(`/api/v1${path}`, { method, data, headers: key() });
  expect(response.status(), `${method} ${path}: ${await response.text()}`).toBe(status);
  return (await response.json()) as Record<string, any>;
}

const unique = (page: Page, word: string) =>
  `${word} ${test.info().project.name.startsWith('phone') ? 'p' : 'd'}${Date.now().toString(36)}${Math.floor(Math.random() * 1296).toString(36)}`;

async function makeFood(page: Page, name: string, extra: object = {}) {
  const made = await call(page, 'POST', '/foods', { name, counted_as: 'weight', ...extra });
  return made.food.id as number;
}

async function putInPantry(page: Page, foodId: number, grams: number, extra: object = {}) {
  // Use soon nudges only for Use by dates (0.8, cabledrawer 7 Nov): a food made here sits in the
  // cupboard, which is Best before, so say Use by.
  if ('use_by' in extra) {
    const patched = await page.request.fetch(`/api/v1/foods/${foodId}`, {
      method: 'PATCH',
      data: { date_kind: 'use_by' },
      headers: key(),
    });
    expect(patched.ok(), await patched.text()).toBe(true);
  }
  await call(page, 'POST', '/stock', { food_id: foodId, amount: { amount: grams, unit: 'g' }, ...extra });
}

async function makeRecipe(page: Page, body: object) {
  return call(page, 'POST', '/recipes', body);
}

const line = (foodId: number, grams: number) => ({ words: 'x', food_id: foodId, amount: grams, unit: 'g' });

const search = (page: Page, words: string) =>
  page.getByRole('searchbox', { name: 'Search recipes' }).fill(words);

test.beforeEach(async ({ page }) => {
  await setAccountTheme(page, 'auto');
});

test('shows the count, the rows and what is in stock, and passes the accessibility checks', async ({ page }) => {
  const tag = unique(page, 'Rice');
  const rice = await makeFood(page, tag);
  const nothing = await makeFood(page, unique(page, 'Nothing'));
  await putInPantry(page, rice, 500);
  await makeRecipe(page, { name: `${tag} one`, time_minutes: 50, nutrition: { kcal: 320 }, lines: [line(rice, 200), line(nothing, 10)] });
  await makeRecipe(page, { name: `${tag} two`, lines: [line(rice, 100)] });
  await makeRecipe(page, { name: `${tag} three`, time_minutes: 60 });

  await page.goto('/recipes');
  await expect(page.getByRole('heading', { name: 'Recipes', level: 1 })).toBeVisible();
  await expect(page.getByText(/^\d+ recipes?$/)).toBeVisible();
  await search(page, tag);
  // Wait for the search to narrow the list to the three, so nothing else is on screen.
  await expect(page.locator('li')).toHaveCount(3);
  await expect(page.getByText('50 min · 320 kcal · all in stock but 1', { exact: true })).toBeVisible();
  await expect(page.getByText('nutrition unknown · all in stock', { exact: true })).toBeVisible();
  await expect(page.getByText('1\u00a0h · nutrition unknown', { exact: true })).toBeVisible();
  // Rows are in A to Z order, and each one opens its recipe.
  const names = await page.locator('li').allInnerTexts();
  expect(names.map((n) => n.split('\n')[0])).toEqual([`${tag} one`, `${tag} three`, `${tag} two`]);
  await expect(page.locator('li a')).toHaveCount(3);
  await expect(page.locator('li button')).toHaveCount(0);
  // "+ New recipe" is the one button on the list, and opens a small choice (N1).
  await expect(page.getByRole('button', { name: 'New recipe', exact: true })).toHaveAttribute('aria-haspopup', 'menu');
  // Not built yet, so not there: Planned. Import and Drafts are (0.5; Import its own item, F113): the
  // phone has their buttons at the top of this page, a computer has them in the sidebar.
  await expect(page.getByRole('main').getByText(/Planned/)).toHaveCount(0);
  await expect(page.getByRole('main').getByRole('link', { name: /^Drafts/ })).toHaveCount(isPhone(page) ? 1 : 0);
  await expect(page.getByRole('main').getByRole('link', { name: 'Import', exact: true })).toHaveCount(isPhone(page) ? 1 : 0);
  await expect(page.getByRole('link', { name: 'Import', exact: true })).toBeVisible();
  await expect(page.getByRole('link', { name: 'Import a recipe', exact: true })).toHaveCount(0);
  await checkPage(page);
});

test('the Ingredients button opens Ingredients (phone)', async ({ page }) => {
  test.skip(!isPhone(page), 'the sidebar has it on a computer');
  await page.goto('/recipes');
  await page.getByRole('link', { name: 'Ingredients' }).click();
  await expect(page).toHaveURL('/recipes/ingredients');
});

test('search finds other names, tags and recipe names, never the method', async ({ page }) => {
  const word = unique(page, 'Paruppu').replace(/\s+/g, '');
  const dal = await makeFood(page, unique(page, 'Toor dal'));
  await call(page, 'POST', `/foods/${dal}/other-names`, { name: word });
  const tagged = unique(page, 'Sambar');
  await makeRecipe(page, { name: tagged, tags: [`Quick${word}`], lines: [line(dal, 100)] });
  const stirred = unique(page, 'Kheer');
  await makeRecipe(page, { name: stirred, steps: [{ text: `Stir in the ${word} slowly.` }] });

  await page.goto('/recipes');
  await search(page, word);
  await expect(page.getByText(tagged, { exact: true })).toBeVisible();
  await expect(page.getByText(stirred, { exact: true })).toHaveCount(0);
  await search(page, `quick${word}`); // the tag
  await expect(page.getByText(tagged, { exact: true })).toBeVisible();
  await search(page, stirred.toLowerCase()); // the recipe's own name, any case
  await expect(page.getByText(stirred, { exact: true })).toBeVisible();
  await search(page, `${word} nonsense`);
  await expect(page.getByText(`No recipe matches “${word} nonsense”.`)).toBeVisible();
});

/** Today, the household's: a use-by date of today is "use soon". */
const householdToday = async (page: Page) => ((await (await page.request.get('/api/v1/household')).json()) as { today: string }).today;

test('the Use soon filter keeps the recipes that use something about to go off, and search narrows it', async ({ page }) => {
  const word = unique(page, 'Palak').replace(/\s+/g, '');
  const soon = await makeFood(page, unique(page, 'Greens'));
  const later = await makeFood(page, unique(page, 'Rice'));
  await putInPantry(page, soon, 500, { use_by: await householdToday(page) });
  await putInPantry(page, later, 500);
  await makeRecipe(page, { name: `${word} greens`, lines: [line(soon, 100)] });
  await makeRecipe(page, { name: `${word} greens curry`, lines: [line(soon, 100)] });
  await makeRecipe(page, { name: `${word} rice`, lines: [line(later, 100)] });

  await page.goto('/recipes');
  await search(page, word);
  const rows = page.locator('li');
  await expect(rows).toHaveCount(3);
  const filters = page.getByRole('group', { name: 'Show' });
  const chip = filters.getByRole('button', { name: 'Use soon', exact: true });
  await chip.click();
  await expect(chip).toHaveAttribute('aria-pressed', 'true');
  await expect(rows).toHaveCount(2);
  await expect(page.getByText(`${word} rice`, { exact: true })).toHaveCount(0);
  await checkPage(page);
  await search(page, `${word} curry`);
  await expect(rows).toHaveCount(1);
  await search(page, `${word} nonsense`);
  await expect(page.getByText(`No recipe matches “${word} nonsense”.`)).toBeVisible();
  await checkPage(page);
});

test('Pantry’s link to the recipes for what is going off opens All recipes on Use soon', async ({ page }) => {
  const word = unique(page, 'Spinach').replace(/\s+/g, '');
  const soon = await makeFood(page, unique(page, 'Greens'));
  await putInPantry(page, soon, 500, { use_by: await householdToday(page) });
  await makeRecipe(page, { name: `${word} soup`, lines: [line(soon, 100)] });
  await makeRecipe(page, { name: `${word} plain` });

  await page.goto('/pantry');
  await expect(page.getByRole('heading', { name: 'Pantry', level: 1 })).toBeVisible();
  await page.getByRole('link', { name: isPhone(page) ? 'Recipes that use them →' : 'Recipes that use them' }).click();
  await expect(page).toHaveURL('/recipes?filter=use-soon');
  const chip = page.getByRole('group', { name: 'Show' }).getByRole('button', { name: 'Use soon', exact: true });
  await expect(chip).toHaveAttribute('aria-pressed', 'true');
  await search(page, word);
  await expect(page.getByText(`${word} soup`, { exact: true })).toBeVisible();
  await expect(page.getByText(`${word} plain`, { exact: true })).toHaveCount(0);
  await checkPage(page);
});

/** Two recipes that use something going off today and one that doesn't, all found by `word`. */
async function soonRecipes(page: Page, word: string) {
  const soon = await makeFood(page, unique(page, 'Greens'));
  const later = await makeFood(page, unique(page, 'Rice'));
  await putInPantry(page, soon, 500, { use_by: await householdToday(page) });
  await putInPantry(page, later, 500);
  const first = await makeRecipe(page, { name: `${word} greens`, lines: [line(soon, 100)] });
  await makeRecipe(page, { name: `${word} greens curry`, lines: [line(soon, 100)] });
  await makeRecipe(page, { name: `${word} rice`, lines: [line(later, 100)] });
  return first.id as number;
}

const useSoonChip = (page: Page) =>
  page.getByRole('group', { name: 'Show' }).getByRole('button', { name: 'Use soon', exact: true });
const allChip = (page: Page) => page.getByRole('group', { name: 'Show' }).getByRole('button', { name: 'All', exact: true });

test('the Use soon chip and the address stay in step, without adding history steps', async ({ page }) => {
  const word = unique(page, 'Step').replace(/\s+/g, '');
  await soonRecipes(page, word);
  await page.goto('/recipes?filter=use-soon');
  await expect(useSoonChip(page)).toHaveAttribute('aria-pressed', 'true');
  const steps = await page.evaluate(() => history.length);
  // A chip tap changes the address quietly (replaced, not added).
  await page.getByRole('group', { name: 'Show' }).getByRole('button', { name: 'Can cook now' }).click();
  await expect(page).toHaveURL('/recipes');
  await useSoonChip(page).click();
  await expect(page).toHaveURL('/recipes?filter=use-soon');
  await allChip(page).click();
  await expect(page).toHaveURL('/recipes');
  await useSoonChip(page).click();
  await expect(page).toHaveURL('/recipes?filter=use-soon');
  expect(await page.evaluate(() => history.length)).toBe(steps);
  // A reload keeps it.
  await page.reload();
  await expect(useSoonChip(page)).toHaveAttribute('aria-pressed', 'true');
  await search(page, word);
  await expect(page.locator('li')).toHaveCount(2);
});

test('on a phone, Back from a recipe finds the list on the chip it was on', async ({ page }) => {
  test.skip(!isPhone(page), 'phone layout');
  const word = unique(page, 'Back').replace(/\s+/g, '');
  await soonRecipes(page, word);
  await page.goto('/recipes');
  await useSoonChip(page).click();
  await search(page, word);
  await page.getByRole('link', { name: new RegExp(`^${word} greens curry`) }).click();
  await expect(page).toHaveURL(/\/recipes\/\d+$/);
  await page.goBack();
  await expect(page).toHaveURL('/recipes?filter=use-soon');
  await expect(useSoonChip(page)).toHaveAttribute('aria-pressed', 'true');
  // And the other way: All, a recipe, Back.
  await allChip(page).click();
  await expect(page).toHaveURL('/recipes');
  await search(page, word);
  await page.getByRole('link', { name: new RegExp(`^${word} rice`) }).click();
  await expect(page).toHaveURL(/\/recipes\/\d+$/);
  await page.goBack();
  await expect(page).toHaveURL('/recipes');
  await expect(allChip(page)).toHaveAttribute('aria-pressed', 'true');
});

test('on a computer, opening a recipe keeps the Use soon filter, a reload too, and Back and Forward move it with the address', async ({ page }) => {
  test.skip(isPhone(page), 'the three panes');
  const word = unique(page, 'Panes').replace(/\s+/g, '');
  await soonRecipes(page, word);
  await page.goto('/recipes?filter=use-soon');
  await expect(useSoonChip(page)).toHaveAttribute('aria-pressed', 'true');
  await search(page, word);
  await expect(page.locator('li')).toHaveCount(2);
  // Open a recipe: the address keeps the filter, and so does the list beside it.
  await page.getByRole('link', { name: new RegExp(`^${word} greens curry`) }).click();
  await expect(page).toHaveURL(/\/recipes\/\d+\?filter=use-soon$/);
  await expect(page.getByRole('heading', { name: `${word} greens curry`, level: 1 })).toBeVisible();
  await expect(useSoonChip(page)).toHaveAttribute('aria-pressed', 'true');
  await expect(page.getByRole('region', { name: 'Recipe list' }).locator('li')).toHaveCount(2); // the search was kept too, as before
  // Reload: the recipe is open and the chip is still on.
  await page.reload();
  await expect(page.getByRole('heading', { name: `${word} greens curry`, level: 1 })).toBeVisible();
  await expect(useSoonChip(page)).toHaveAttribute('aria-pressed', 'true');
  // Back to the list, Forward to the recipe: the address and the chip agree each time.
  await page.goBack();
  await expect(page).toHaveURL('/recipes?filter=use-soon');
  await expect(useSoonChip(page)).toHaveAttribute('aria-pressed', 'true');
  await page.goForward();
  await expect(page).toHaveURL(/\/recipes\/\d+\?filter=use-soon$/);
  await expect(useSoonChip(page)).toHaveAttribute('aria-pressed', 'true');

  // From All: open a recipe, then switch to Use soon. Back (to the address without the filter)
  // puts the chip back on All; Forward puts it on Use soon again.
  await page.goto('/recipes');
  await expect(allChip(page)).toHaveAttribute('aria-pressed', 'true');
  await search(page, word);
  await page.getByRole('link', { name: new RegExp(`^${word} rice`) }).click();
  await expect(page).toHaveURL(/\/recipes\/\d+$/);
  const open = page.url();
  await useSoonChip(page).click();
  await expect(page).toHaveURL(`${open}?filter=use-soon`);
  await page.goBack();
  await expect(page).toHaveURL('/recipes');
  await expect(allChip(page)).toHaveAttribute('aria-pressed', 'true');
  await page.goForward();
  await expect(page).toHaveURL(`${open}?filter=use-soon`);
  await expect(useSoonChip(page)).toHaveAttribute('aria-pressed', 'true');
  await checkPage(page);
});

test('the filter row: Can cook now, a tag, and search together', async ({ page }) => {
  const word = unique(page, 'Chana').replace(/\s+/g, '');
  const have = await makeFood(page, unique(page, 'Have'));
  const lack = await makeFood(page, unique(page, 'Lack'));
  await putInPantry(page, have, 500);
  await makeRecipe(page, { name: `${word} yes`, tags: [`Fast${word}`], lines: [line(have, 100)] });
  await makeRecipe(page, { name: `${word} no`, tags: [`Fast${word}`], lines: [line(have, 100), line(lack, 10)] });
  await makeRecipe(page, { name: `${word} slow`, lines: [line(have, 100)] });

  await page.goto('/recipes');
  await search(page, word);
  const rows = page.locator('li');
  await expect(rows).toHaveCount(3);
  const filters = page.getByRole('group', { name: 'Show' });
  await filters.getByRole('button', { name: 'Can cook now' }).click();
  await expect(filters.getByRole('button', { name: 'Can cook now' })).toHaveAttribute('aria-pressed', 'true');
  await expect(rows).toHaveCount(2); // "no" is missing one
  await expect(page.getByText(`${word} no`, { exact: true })).toHaveCount(0);
  // One filter at a time: a tag replaces Can cook now.
  await filters.getByRole('button', { name: `Fast${word}` }).click();
  await expect(filters.getByRole('button', { name: 'Can cook now' })).toHaveAttribute('aria-pressed', 'false');
  await expect(rows).toHaveCount(2);
  await expect(page.getByText(`${word} slow`, { exact: true })).toHaveCount(0);
  // And the search narrows whatever is chosen.
  await search(page, `${word} yes`);
  await expect(rows).toHaveCount(1);
  await search(page, word);
  await filters.getByRole('button', { name: 'All', exact: true }).click();
  await expect(rows).toHaveCount(3);
  // The title still counts every recipe, not just the matches.
  await expect(page.getByText(/^\d+ recipes$/)).toBeVisible();
});

test('a stock line follows the pantry: use soon, and a made-up total', async ({ page }) => {
  const spinach = await makeFood(page, unique(page, 'Spinach'));
  const today = (await (await page.request.get('/api/v1/household')).json()).today as string;
  await putInPantry(page, spinach, 200, { use_by: today });
  const name = unique(page, 'Palak');
  await makeRecipe(page, { name, lines: [line(spinach, 100)] });
  await page.goto('/recipes');
  await search(page, name);
  const lowerFirst = (s: string) => s[0]!.toLowerCase() + s.slice(1);
  const foodName = (await (await page.request.get(`/api/v1/foods/${spinach}`)).json()).name as string;
  await expect(page.getByText(`Uses ${lowerFirst(foodName)} (today)`)).toBeVisible();
});

// --- The states of the screen ------------------------------------------------------------

const EMPTY = { total: 0, all_recipes: 0, recipes: [], next: null };

test('empty: says No recipes yet, with New recipe to add one', async ({ page }) => {
  await page.route('**/api/v1/recipes?**', (route) => route.fulfill({ json: EMPTY }));
  await page.route('**/api/v1/recipes/tags', (route) => route.fulfill({ json: { tags: [] } }));
  await page.goto('/recipes');
  await expect(page.getByRole('heading', { name: 'No recipes yet' })).toBeVisible();
  await expect(page.getByText('Recipes you add will show here.')).toBeVisible();
  await expect(page.getByRole('button', { name: 'New recipe', exact: true })).toBeVisible();
  await expect(page.getByText(/Add a recipe/)).toHaveCount(0);
  await expect(page.getByRole('link', { name: 'Import', exact: true })).toBeVisible();
  await expect(page.getByRole('searchbox')).toHaveCount(0);
  await checkPage(page);
});

test('loading: says Loading… until the server answers', async ({ page }) => {
  let release!: () => void;
  const held = new Promise<void>((resolve) => (release = resolve));
  await page.route('**/api/v1/recipes?**', async (route) => {
    await held;
    await route.continue();
  });
  await page.goto('/recipes');
  await expect(page.getByText('Loading…')).toBeVisible();
  await expect(page.getByText(/No recipes yet/)).toHaveCount(0);
  release();
  await expect(page.getByText('Loading…')).toHaveCount(0);
});

test('failed: says what happened and Try again loads it', async ({ page }) => {
  await page.route('**/api/v1/recipes?**', (route) =>
    route.fulfill({ status: 500, json: { detail: 'Something broke.' } }),
  );
  await page.goto('/recipes');
  await expect(page.getByText('Couldn’t load your recipes. Try again.')).toBeVisible();
  await expect(page.getByText(/No recipes yet/)).toHaveCount(0);
  await checkPage(page);
  await page.unroute('**/api/v1/recipes?**');
  await page.getByRole('button', { name: 'Try again' }).click();
  await expect(page.getByText('Couldn’t load your recipes. Try again.')).toHaveCount(0);
  await expect(page.getByRole('searchbox', { name: 'Search recipes' })).toBeVisible();
});

async function goOffline(page: Page, context: BrowserContext) {
  // Wait for the live stream's hello first: one arriving after the failed fetch would rightly
  // say the server is there after all.
  const hello = page.waitForResponse((r) => r.url().endsWith('/api/v1/events'));
  await page.goto('/recipes');
  await expect(page.getByRole('searchbox', { name: 'Search recipes' })).toBeVisible();
  await hello;
  // Kept: the app's start-up after the stream opens has no signal to wait for; the next step cuts the network.
  await page.waitForTimeout(500);
  // Only our server is unreachable: the app comes to the foreground, fetches and finds out.
  await context.route('**/api/**', (route) => route.abort());
  await page.evaluate(() => document.dispatchEvent(new Event('visibilitychange')));
}

test('server down after the list loaded: the bar shows, and Shopping is reachable', async ({ page, context }) => {
  await goOffline(page, context);
  await expect(page.getByTestId(isPhone(page) ? 'connection-phone' : 'connection-desktop')).toBeVisible({
    timeout: 15_000,
  });
  // Shopping works offline: the sidebar on a computer, the "Shop" tab on a phone.
  await expect(
    isPhone(page)
      ? page.getByRole('link', { name: 'Shop', exact: true }).first()
      : page.getByRole('link', { name: 'Shopping', exact: true }).first(),
  ).toBeVisible();
  await checkPage(page);
  await context.unroute('**/api/**');
});

test('server down before anything loaded: the note says it needs the server, and points to Shopping', async ({
  page,
  context,
}) => {
  await context.route('**/api/v1/recipes**', (route) => route.abort());
  await page.goto('/recipes');
  await expect(
    page.getByText('Recipes comes back by itself when the server answers. Your shopping list works offline.'),
  ).toBeVisible({ timeout: 15_000 });
  await expect(page.getByRole('link', { name: 'Shopping', exact: true }).first()).toBeVisible();
  await expect(page.getByRole('searchbox')).toHaveCount(0);
  await context.unroute('**/api/v1/recipes**');
});

// --- Many, long names, 200% text ------------------------------------------------------------

const LONG = [
  'பச்சைப் பயறு (பாசிப்பயறு) முழுதாக, கரிம விவசாயிகளின் சந்தையில் வாங்கியது',
  'Organic stone-ground whole wheat flour flatbreads from the Saturday market, coarse, 5 kg bag',
];

function manyRecipes(count: number) {
  return Array.from({ length: count }, (_, i) => ({
    id: i + 1,
    name: i < LONG.length ? LONG[i]! : `Recipe ${String(i + 1).padStart(3, '0')}`,
    description: null,
    time_minutes: 45,
    serves: 4,
    makes: null,
    made_ahead: false,
    tags: [],
    ingredient_count: 6,
    photo: null,
    version: 1,
    updated_at: '2026-10-20T10:00:00Z',
    kcal: i % 3 === 0 ? null : 300 + i,
    stock: { counted: 6, missing: i % 4, can_cook_now: i % 4 === 0 },
    use_soon:
      i % 5 === 0
        ? { foods: [{ id: 1, name: LONG[1]! }, { id: 2, name: 'Spinach' }, { id: 3, name: 'Milk' }], use_by: '2026-10-20', days_left: 0 }
        : null,
  }));
}

test('many recipes with long names, and the text at 200%, never scroll sideways', async ({ page }) => {
  await page.route('**/api/v1/recipes?**', (route) =>
    route.fulfill({ json: { total: 220, all_recipes: 220, recipes: manyRecipes(50), next: '50' } }),
  );
  await page.route('**/api/v1/recipes/tags', (route) =>
    route.fulfill({
      json: { tags: [...LONG, 'Quick', 'Kids', 'Sunday', 'Freezer-friendly'].map((name) => ({ name, recipes: 3 })) },
    }),
  );
  await page.goto('/recipes');
  await expect(page.getByText('220 recipes')).toBeVisible();
  await expect(page.locator('li')).toHaveCount(50);
  await expect(page.getByRole('button', { name: 'Show more' })).toBeVisible();
  await checkPage(page);
  await page.evaluate(() => (document.documentElement.style.fontSize = '200%'));
  await expect(page.getByText('220 recipes')).toBeVisible();
  await expectNoSidewaysScroll(page);
  // The tab labels hold at 200% text (a known paper cut): none overlaps the next.
  if (isPhone(page)) {
    const boxes = await page.locator('nav[aria-label="Main"] a span').evaluateAll((spans) =>
      spans.map((s) => {
        const range = document.createRange();
        range.selectNodeContents(s);
        const { left, right } = range.getBoundingClientRect();
        return { left, right };
      }),
    );
    for (let i = 1; i < boxes.length; i++) expect(boxes[i]!.left).toBeGreaterThanOrEqual(boxes[i - 1]!.right);
  }
});

// The theme is set before the page opens: switching it on the open page reloads the list,
// which would clear the failed state before its accessibility checks.
for (const theme of THEMES) {
  test(`a failed Show more keeps the list, the count and the filters, and Try again loads the next page (${theme})`, async ({ page }) => {
    let fail = true;
    await page.route('**/api/v1/recipes?**', (route) => {
      if (route.request().url().includes('after=')) {
        return fail
          ? route.fulfill({ status: 500, json: { detail: 'Something broke.' } })
          : route.fulfill({ json: { total: 60, all_recipes: 60, recipes: manyRecipes(60).slice(50), next: null } });
      }
      return route.fulfill({ json: { total: 60, all_recipes: 60, recipes: manyRecipes(50), next: '50' } });
    });
    await page.route('**/api/v1/recipes/tags', (route) => route.fulfill({ json: { tags: [{ name: 'Quick', recipes: 3 }] } }));
    await page.emulateMedia({ colorScheme: theme });
    await page.goto('/recipes');
    await expect(page.locator('html')).toHaveAttribute('data-theme', theme);
    await expect(page.locator('li')).toHaveCount(50);
    await page.getByRole('button', { name: 'Show more' }).click();
    await expect(page.getByText('Couldn’t load more recipes. Try again.')).toBeVisible();
    await expect(page.locator('li')).toHaveCount(50);
    await expect(page.getByText('60 recipes')).toBeVisible();
    await expect(page.getByRole('button', { name: 'Can cook now' })).toBeVisible();
    await expect(page.getByText(/Couldn’t load your recipes/)).toHaveCount(0);
    await expectNoAxeViolations(page, `/recipes, failed Show more, ${isPhone(page) ? 'phone' : 'desktop'}, ${theme}`);
    if (isPhone(page)) {
      await expectTouchTargets(page);
      await expectNoSidewaysScroll(page);
    }
    fail = false;
    await page.getByRole('button', { name: 'Try again' }).click();
    await expect(page.locator('li')).toHaveCount(60);
    await expect(page.getByText(/Couldn’t load more/)).toHaveCount(0);
  });
}

test('opening the page asks for the list once', async ({ page }) => {
  const asked: string[] = [];
  await page.route('**/api/v1/recipes?**', (route) => {
    asked.push(route.request().url());
    return route.fulfill({ json: { total: 3, all_recipes: 3, recipes: manyRecipes(3), next: null } });
  });
  await page.route('**/api/v1/recipes/tags', (route) => route.fulfill({ json: { tags: [] } }));
  await page.goto('/recipes');
  await expect(page.locator('li')).toHaveCount(3);
  // Kept: proves no second search request is made, so it can only be waited out.
  await page.waitForTimeout(600); // longer than the 200 ms pause before a search
  expect(asked).toHaveLength(1);
});

test('reduced motion: nothing on the page animates', async ({ page }) => {
  await page.emulateMedia({ reducedMotion: 'reduce' });
  await page.goto('/recipes');
  await expect(page.getByRole('searchbox', { name: 'Search recipes' })).toBeVisible();
  const running = await page.evaluate(() =>
    document.getAnimations().filter((a) => a.playState === 'running' && (a.effect?.getTiming().duration as number) > 0.1).length,
  );
  expect(running).toBe(0);
});

test('the tag chips are one row that scrolls sideways, never wraps, and the page never scrolls sideways (cabledrawer 9 Nov)', async ({ page }) => {
  const word = unique(page, 'Row').replace(/\s+/g, '');
  const tags = Array.from({ length: 16 }, (_, i) => `${word} a rather long tag ${i}`.slice(0, 40));
  await makeRecipe(page, { name: `${word} soup`, tags: tags.slice(0, 10) });
  await makeRecipe(page, { name: `${word} stew`, tags: tags.slice(10) });
  await page.goto('/recipes');
  const group = page.getByRole('group', { name: 'Show' });
  const chips = group.getByRole('button');
  await expect(chips.first()).toBeVisible();
  expect(await chips.count()).toBeGreaterThan(16);
  const height = page.viewportSize()!.height;
  // At every width the page can have (a phone, a tablet, the two-pane and three-pane computer),
  // and at 200% text: one row, scrolling inside itself, and the page never scrolls sideways.
  for (const [width, big] of [[428, false], [768, false], [1100, false], [1300, false], [428, true]] as const) {
    await page.setViewportSize({ width, height });
    await page.evaluate((zoom) => (document.documentElement.style.fontSize = zoom ? '200%' : ''), big);
    const where = `${width} px${big ? ' at 200% text' : ''}`;
    // The row that is on screen: in the three panes the list is the middle pane.
    const shown = group.first();
    // The page has taken its new width first. From 1024 px the list moves into the middle pane: a new
    // list that loads again, so for a moment the old chips are still there, and then none are (this
    // test once measured in that moment and found no chips at all).
    await expect(page.getByRole('region', { name: 'Recipe', exact: true }), where).toHaveCount(width >= 1024 ? 1 : 0);
    await expect(shown, where).toBeVisible();
    await expect(shown.getByRole('button').nth(16), where).toBeVisible(); // the list has come back
    // Every chip there is, measured together: more than 16 of them, all on one row.
    await expect
      .poll(
        async () => {
          const tops = await shown.getByRole('button').evaluateAll((els) => els.map((el) => Math.round(el.getBoundingClientRect().top)));
          return tops.length > 16 ? new Set(tops).size : `only ${tops.length} chips`;
        },
        { message: `one row at ${where}` },
      )
      .toBe(1);
    // It scrolls inside itself (the layout has settled once it has a width).
    await expect
      .poll(() => shown.evaluate((el) => el.clientWidth > 0 && el.scrollWidth > el.clientWidth), { message: `it scrolls inside itself at ${where}` })
      .toBe(true);
    await expectNoSidewaysScroll(page);
    // The keyboard reaches the last chip and the row scrolls it into view.
    const last = shown.getByRole('button').last();
    await last.focus();
    await expect(last, where).toBeInViewport();
    await expectNoSidewaysScroll(page);
  }
  await page.evaluate(() => (document.documentElement.style.fontSize = ''));
  await checkPage(page);
});

test('Manage tags: a look-alike tag merges with a toast Undo that puts it back, and a rename to an existing name is refused (cabledrawer 9 Nov)', async ({ page }) => {
  const word = unique(page, 'Mt').replace(/\s+/g, '');
  const proper = `${word} South Indian`;
  const dashed = `${word}-south-indian`.toLowerCase();
  const plain = `${word} Quick`;
  const a = await makeRecipe(page, { name: `${word} sambar`, tags: [proper, plain] });
  const b = await makeRecipe(page, { name: `${word} rasam`, tags: [dashed] });
  // A long list of tags, so the merge picker would be far below the tapped row (F221).
  const many = Array.from({ length: 26 }, (_, i) => `${word} tag ${String(i).padStart(2, '0')}`);
  await makeRecipe(page, { name: `${word} many`, tags: many.slice(0, 13) });
  await makeRecipe(page, { name: `${word} lots`, tags: many.slice(13) });
  const tagsOf = async (id: number) => ((await (await page.request.get(`/api/v1/recipes/${id}`)).json()) as { tags: string[] }).tags;

  await page.goto('/recipes');
  await page.getByRole('button', { name: 'Manage tags' }).click();
  const sheet = page.getByRole('dialog', { name: 'Manage tags' });
  await expect(sheet).toBeVisible();
  const row = (name: string) => sheet.getByRole('listitem').filter({ has: page.getByText(name, { exact: true }) });
  await expect(row(dashed)).toContainText('1 recipe · looks like');
  await checkPage(page);

  // A rename to a name another tag has is refused, and says so.
  await sheet.getByRole('button', { name: `Rename ${plain}` }).click();
  await sheet.getByRole('textbox', { name: `New name for ${plain}` }).fill(proper.toLowerCase());
  await sheet.getByRole('button', { name: 'Save' }).click();
  await expect(sheet.getByRole('alert')).toContainText('There’s already a tag called');
  await sheet.getByRole('button', { name: 'Cancel' }).click();
  // A rename to a free name changes the tag on its recipes.
  await sheet.getByRole('button', { name: `Rename ${plain}` }).click();
  await sheet.getByRole('textbox', { name: `New name for ${plain}` }).fill(`${plain} dinner`);
  await sheet.getByRole('button', { name: 'Save' }).click();
  await expect(row(`${plain} dinner`)).toBeVisible();
  expect(await tagsOf(a.id)).toContain(`${plain} dinner`);

  // Merge: asked once in words, then a toast with Undo.
  await sheet.getByRole('button', { name: `Merge ${dashed} into…` }).click();
  // The picker and its Merge button open in view, not at the foot of the long list (F221).
  await expect(sheet.getByLabel(`Merge “${dashed}” into`)).toBeInViewport();
  await expect(sheet.getByRole('button', { name: 'Merge', exact: true })).toBeInViewport();
  // The keyboard follows: onto the picker, and back to Merge into… on Cancel (FX4 review r1).
  await expect(sheet.getByLabel(`Merge “${dashed}” into`)).toBeFocused();
  await sheet.getByRole('button', { name: 'Cancel' }).click();
  await expect(sheet.getByRole('button', { name: `Merge ${dashed} into…` })).toBeFocused();
  await sheet.getByRole('button', { name: `Merge ${dashed} into…` }).click();
  await sheet.getByLabel(`Merge “${dashed}” into`).selectOption({ label: proper });
  await expect(sheet.getByText(`Merge “${dashed}” into “${proper}”? Its 1 recipe gets “${proper}”, and “${dashed}” goes. You can Undo.`)).toBeVisible();
  await checkPage(page);
  await sheet.getByRole('button', { name: 'Merge', exact: true }).click();
  await expect(page.getByText(`Merged tag ${dashed} into ${proper}`)).toBeVisible();
  await expect(row(dashed)).toHaveCount(0);
  expect(await tagsOf(b.id)).toEqual([proper]);
  await page.getByRole('button', { name: 'Undo', exact: true }).click();
  await expect(row(dashed)).toBeVisible();
  expect(await tagsOf(b.id)).toEqual([dashed]);
  expect(await tagsOf(a.id)).toContain(proper);
  await sheet.getByRole('button', { name: 'Close' }).click();
  await expect(sheet).toBeHidden();
});
