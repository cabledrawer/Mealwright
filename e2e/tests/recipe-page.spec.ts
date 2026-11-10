import { test, expect, type BrowserContext, type Page } from './clock.ts';
import { checkPage, expectNoSidewaysScroll, isPhone, setAccountTheme } from './a11y.ts';

// The recipe page (0.4, PR 3b), against the real server: what it shows, where each ingredient
// is, servings, "N missing · Add to the list", Cook now, and every state of the screen
// (spec "Keeping the UI good", item 2): loading, failed, offline, not found, one line, many
// lines, long names, text at 200%, no nutrition, no servings. Runs in the "phone 0.4 recipe
// page" and "desktop 0.4 recipe page" projects, signed in as the test admin.

const key = () => ({ 'idempotency-key': crypto.randomUUID() });

async function call(page: Page, method: 'POST' | 'PUT', path: string, data: object, status = 201) {
  const response = await page.request.fetch(`/api/v1${path}`, { method, data, headers: key() });
  expect(response.status(), `${method} ${path}: ${await response.text()}`).toBe(status);
  return (await response.json()) as Record<string, any>;
}

const unique = (word: string) =>
  `${word} ${test.info().project.name.startsWith('phone') ? 'p' : 'd'}${Date.now().toString(36)}${Math.floor(Math.random() * 1296).toString(36)}`;

async function makeFood(page: Page, name: string, extra: object = {}) {
  const made = await call(page, 'POST', '/foods', { name, counted_as: 'weight', ...extra });
  return made.food.id as number;
}

const putInPantry = (page: Page, foodId: number, grams: number) =>
  call(page, 'POST', '/stock', { food_id: foodId, amount: { amount: grams, unit: 'g' } });

/** The recipe itself: the reading pane on a computer (beside the list), the whole page on a phone. */
const reader = (page: Page) => (isPhone(page) ? page.locator('main') : page.getByRole('region', { name: 'Recipe', exact: true }));

const makeRecipe = (page: Page, body: object) => call(page, 'POST', '/recipes', body);

const line = (foodId: number, amount: number, unit = 'g', words = 'x') => ({ words, food_id: foodId, amount, unit });

/** A recipe with one ingredient in each state: in stock, a staple, not enough, missing. */
async function sambar(page: Page, extra: object = {}) {
  const name = unique('Sambar');
  const dal = await makeFood(page, unique('Toor dal'));
  const salt = await makeFood(page, unique('Salt'), { staple: true });
  const paneer = await makeFood(page, unique('Paneer'));
  const ghee = await makeFood(page, unique('Ghee'));
  await putInPantry(page, dal, 500);
  await putInPantry(page, paneer, 50);
  const recipe = await makeRecipe(page, {
    name,
    description: 'Lentil & vegetable stew',
    time_minutes: 50,
    serves: 4,
    nutrition: { kcal: 320, protein: 16 },
    tags: ['Batch-friendly'],
    source_note: 'Amma’s',
    lines: [
      { kind: 'heading', words: 'For the dal' },
      line(dal, 200, 'g', 'thuvaram paruppu'),
      line(salt, 1, 'tsp', 'salt'),
      line(paneer, 250, 'g', 'paneer'),
      { words: 'ghee', food_id: ghee, amount: 1, unit: 'tbsp' },
      { words: 'a handful of coriander' },
    ],
    steps: [{ text: 'Rinse the dal.' }, { kind: 'heading', text: 'The tempering' }, { text: 'Pop the seeds.' }],
    ...extra,
  });
  return { recipe, name, dal, salt, paneer, ghee };
}

test.beforeEach(async ({ page }) => {
  await setAccountTheme(page, 'auto');
});

test('opens from All recipes, says where each ingredient is, and passes the accessibility checks', async ({ page }) => {
  const { name, recipe } = await sambar(page);
  await page.goto('/recipes');
  await page.getByRole('searchbox', { name: 'Search recipes' }).fill(name);
  await page.getByRole('link', { name: new RegExp(name) }).click();
  await expect(page).toHaveURL(`/recipes/${recipe.id}`);
  await expect(page.getByRole('heading', { name, level: 1 })).toBeVisible();
  await expect(reader(page).getByText('Lentil & vegetable stew · 50 min')).toBeVisible();
  const lines = page.getByRole('region', { name: 'Ingredients' });
  await expect(lines.getByRole('button', { name: /thuvaram paruppu/ })).toContainText('Cupboard');
  await expect(lines.getByRole('button', { name: /salt/i })).toContainText('Staple');
  await expect(lines.getByRole('button', { name: /paneer/i })).toContainText('Not enough');
  await expect(lines.getByRole('button', { name: /ghee/i })).toContainText('Missing');
  await expect(lines.getByText('a handful of coriander')).toBeVisible();
  await expect(reader(page).getByText('2 missing', { exact: true })).toBeVisible();
  await expect(reader(page).getByText('Rinse the dal.')).toBeVisible();
  await expect(reader(page).getByText('Batch-friendly')).toBeVisible();
  await expect(reader(page).getByText('Source: Amma’s')).toBeVisible();
  await expect(reader(page).getByText('unknown', { exact: true }).first()).toBeVisible(); // carbs were never typed
  // Edit opens the editor (Delete is inside it). Hidden in 0.4: not drawn, not stubbed.
  await expect(page.getByRole('link', { name: 'Edit', exact: true })).toHaveAttribute('href', `/recipes/${recipe.id}/edit`);
  await expect(page.getByRole('main').getByText(/Start cooking|Cook once|Delete/)).toHaveCount(0);
  await expect(page.getByRole('button', { name: 'Plan it', exact: true })).toBeVisible();
  await checkPage(page);
});

test('servings scale the amounts on screen only, and the saved recipe stays as it was', async ({ page }) => {
  const { recipe } = await sambar(page);
  await page.goto(`/recipes/${recipe.id}`);
  await expect(reader(page).getByText('Serves 4')).toBeVisible();
  await page.getByRole('button', { name: 'More servings' }).click();
  await page.getByRole('button', { name: 'More servings' }).click();
  await expect(reader(page).getByText('Serves 6')).toBeVisible();
  await expect(reader(page).getByText(/^300\sg/)).toBeVisible();
  await expect(reader(page).getByText(/^1½\stsp/)).toBeVisible();
  const saved = await (await page.request.get(`/api/v1/recipes/${recipe.id}`)).json();
  expect(saved.serves).toBe(4);
  expect(saved.version).toBe(1);
  // Leaving and coming back starts at the recipe's own number again.
  await page.goBack();
  await page.goForward();
  await expect(reader(page).getByText('Serves 4')).toBeVisible();
});

test('a tap on an ingredient opens the ingredient editor, and a recipe line opens that recipe', async ({ page }) => {
  const { recipe, dal } = await sambar(page);
  const inner = await makeRecipe(page, { name: unique('Podi') });
  const outer = await makeRecipe(page, {
    name: unique('Rasam'),
    lines: [{ words: 'the podi', amount: 2, unit: 'tbsp', recipe_id: inner.id }, line(dal, 10)],
  });
  await page.goto(`/recipes/${recipe.id}`);
  await page.getByRole('button', { name: /thuvaram paruppu/ }).click();
  await expect(page.getByRole('dialog')).toBeVisible();
  // The editor inside the sheet is loaded when first opened, then reads the ingredient: wait for it
  // before leaving the page, or the next page cuts that load short (a page error in WebKit).
  await expect(page.getByRole('dialog').getByRole('heading', { name: /^Toor dal/ })).toBeVisible();
  await page.keyboard.press('Escape');
  await page.goto(`/recipes/${outer.id}`);
  await page.getByRole('link', { name: /the podi/ }).click();
  await expect(page).toHaveURL(`/recipes/${inner.id}`);
  await expect(page.getByRole('heading', { name: inner.name, level: 1 })).toBeVisible();
});

test('"2 missing · Add to the list" adds both with one Undo, and the lines say On list', async ({ page }) => {
  const { recipe } = await sambar(page);
  await page.goto(`/recipes/${recipe.id}`);
  await expect(reader(page).getByText('2 missing', { exact: true })).toBeVisible();
  await page.getByRole('button', { name: 'Add to the list' }).click();
  await expect(page.getByText('2 ingredients added to the shopping list')).toBeVisible();
  await expect(page.getByRole('button', { name: /paneer/i })).toContainText('On list');
  await expect(page.getByRole('button', { name: /ghee/i })).toContainText('On list');
  // Nothing left to add: the line is gone, and nothing says "all in stock".
  await expect(reader(page).getByText(/missing/)).toHaveCount(0);
  await expect(page.getByRole('button', { name: 'Add to the list' })).toHaveCount(0);
  await expect(reader(page).getByText(/all in stock/i)).toHaveCount(0);
  await page.getByRole('button', { name: 'Undo', exact: true }).click();
  await expect(page.getByText('Undone: 2 ingredients added to the shopping list')).toBeVisible();
  await expect(reader(page).getByText('2 missing', { exact: true })).toBeVisible();
});

test('a recipe that uses an unchecked recipe never says all in stock', async ({ page }) => {
  const dal = await makeFood(page, unique('Toor dal'));
  await putInPantry(page, dal, 500);
  const base = await makeRecipe(page, { name: unique('Base') });
  const recipe = await makeRecipe(page, {
    name: unique('Uses base'),
    lines: [line(dal, 100), { words: 'base', amount: 1, unit: 'cup', recipe_id: base.id }],
  });
  await page.goto(`/recipes/${recipe.id}`);
  await expect(page.getByRole('button', { name: /^100 g/ })).toContainText('Cupboard');
  await expect(reader(page).getByText(/missing|all in stock/i)).toHaveCount(0);
});

// --- Cook now ------------------------------------------------------------------------------

test('Cook now is the main button above the ingredients and opens Cook mode; the recipe page has no Keep screen awake', async ({ page }) => {
  const { recipe, name } = await sambar(page);
  await page.goto(`/recipes/${recipe.id}`);
  await expect(page.getByRole('heading', { name, level: 1 })).toBeVisible();
  await expect(page.getByText('Keep screen awake')).toHaveCount(0);
  const above = await page.evaluate(() => {
    const cook = [...document.querySelectorAll('a')].find((a) => a.textContent?.trim() === 'Cook now');
    const heading = [...document.querySelectorAll('h2')].find((h) => h.textContent?.trim() === 'Ingredients');
    return !!cook && !!heading && !!(cook.compareDocumentPosition(heading) & Node.DOCUMENT_POSITION_FOLLOWING);
  });
  expect(above).toBe(true);
  await page.getByRole('link', { name: 'Cook now' }).click();
  // It plans the recipe into today's next meal first, so the address names that meal.
  await expect(page).toHaveURL(new RegExp(`/recipes/${recipe.id}/cook\\?meal=\\d+$`));
  await expect(page.getByRole('region', { name: 'Cook mode' })).toBeVisible();
  await page.getByTestId('cook-notice').getByRole('button', { name: 'Undo' }).click(); // leave the plan as it was
  await expect(page.getByTestId('cook-notice')).toHaveText('Taken out of today’s plan.');
});

// --- The states of the screen ----------------------------------------------------------------

test('loading: says Loading… until the server answers', async ({ page }) => {
  const { recipe, name } = await sambar(page);
  let release!: () => void;
  const held = new Promise<void>((resolve) => (release = resolve));
  await page.route(new RegExp(`/api/v1/recipes/${recipe.id}$`), async (route) => {
    await held;
    await route.continue();
  });
  await page.goto(`/recipes/${recipe.id}`);
  await expect(reader(page).getByText('Loading…')).toBeVisible();
  release();
  await expect(page.getByRole('heading', { name, level: 1 })).toBeVisible();
  await expect(reader(page).getByText('Loading…')).toHaveCount(0);
});

test('failed: says what happened and Try again loads it', async ({ page }) => {
  const { recipe, name } = await sambar(page);
  const url = new RegExp(`/api/v1/recipes/${recipe.id}$`);
  await page.route(url, (route) => route.fulfill({ status: 500, json: { detail: 'Something broke.' } }));
  await page.goto(`/recipes/${recipe.id}`);
  await expect(page.getByText('Couldn’t load this recipe. Try again.')).toBeVisible();
  await checkPage(page);
  await page.unroute(url);
  await page.getByRole('button', { name: 'Try again' }).click();
  await expect(page.getByRole('heading', { name, level: 1 })).toBeVisible();
});

test('not found: a deleted recipe says it isn’t here, with a way back', async ({ page }) => {
  const { recipe } = await sambar(page);
  const removed = await page.request.delete(`/api/v1/recipes/${recipe.id}`, { headers: key() });
  expect(removed.ok()).toBe(true);
  await page.goto(`/recipes/${recipe.id}`);
  await expect(page.getByRole('heading', { name: 'Recipe not found' })).toBeVisible();
  await expect(page.getByText('This recipe isn’t here any more. It may have been deleted.')).toBeVisible();
  await checkPage(page);
  await page.getByRole('link', { name: 'Recipes' }).first().click();
  await expect(page).toHaveURL('/recipes');
});

async function goOffline(page: Page, context: BrowserContext, id: number, name: string) {
  const hello = page.waitForResponse((r) => r.url().endsWith('/api/v1/events'));
  await page.goto(`/recipes/${id}`);
  await expect(page.getByRole('heading', { name, level: 1 })).toBeVisible();
  await hello;
  // Kept: the app's start-up after the stream opens has no signal to wait for; the next step cuts the network.
  await page.waitForTimeout(500);
  await context.route('**/api/**', (route) => route.abort());
  await page.evaluate(() => document.dispatchEvent(new Event('visibilitychange')));
}

test('server down after the recipe loaded: it stays, Edit and Delete go, and Shopping is reachable', async ({
  page,
  context,
}) => {
  const { recipe, name } = await sambar(page);
  await goOffline(page, context, recipe.id, name);
  await expect(page.getByTestId(isPhone(page) ? 'connection-phone' : 'connection-desktop')).toBeVisible({
    timeout: 15_000,
  });
  await expect(page.getByRole('heading', { name, level: 1 })).toBeVisible();
  await expect(page.getByRole('link', { name: 'Edit', exact: true })).toHaveCount(0);
  await expect(page.getByRole('heading', { name: 'Can’t reach your Mealwright server.' })).toHaveCount(0);
  await expect(
    isPhone(page)
      ? page.getByRole('link', { name: 'Shop', exact: true }).first()
      : page.getByRole('link', { name: 'Shopping', exact: true }).first(),
  ).toBeVisible();
  await checkPage(page);
  await context.unroute('**/api/**');
});

test('a recipe with only a name, no nutrition and no servings reads calmly', async ({ page }) => {
  const name = unique('Plain');
  const recipe = await makeRecipe(page, { name, serves: null });
  await page.goto(`/recipes/${recipe.id}`);
  await expect(page.getByRole('heading', { name, level: 1 })).toBeVisible();
  await expect(reader(page).getByText('Nutrition unknown')).toBeVisible();
  await expect(reader(page).getByText('Nothing written down yet.')).toBeVisible();
  await expect(page.getByRole('group', { name: 'Servings' })).toHaveCount(0);
  await checkPage(page);
});

test('a recipe that makes something but has no servings and no lines shows Makes as plain text', async ({ page }) => {
  const recipe = await makeRecipe(page, { name: unique('Batter'), serves: null, makes: { amount: 1.5, unit: 'l' } });
  await page.goto(`/recipes/${recipe.id}`);
  await expect(reader(page).getByText('Makes 1½ litres')).toBeVisible();
  await expect(page.getByRole('group', { name: 'Servings' })).toHaveCount(0);
});

test('Makes without Serves: − / + in whole multiples from 1×, the lines scaling with it', async ({ page }) => {
  const dal = await makeFood(page, unique('Toor dal'));
  const recipe = await makeRecipe(page, {
    name: unique('Batter'),
    serves: null,
    makes: { amount: 200, unit: 'g' },
    lines: [line(dal, 150, 'g', 'urad dal')],
  });
  await page.goto(`/recipes/${recipe.id}`);
  const stepper = page.getByRole('group', { name: 'How much it makes' });
  await expect(stepper.getByText('Makes 200 g')).toBeVisible();
  await expect(reader(page).getByText(/Makes/)).toHaveCount(1);
  await expect(stepper.getByRole('button', { name: 'Make less' })).toBeDisabled();
  await stepper.getByRole('button', { name: 'Make more' }).click();
  await expect(stepper.getByText('Makes 400 g')).toBeVisible();
  await expect(reader(page).getByText(/^300\sg/)).toBeVisible();
  await stepper.getByRole('button', { name: 'Make more' }).click();
  await expect(stepper.getByText('Makes 600 g')).toBeVisible();
  await expect(reader(page).getByText(/^450\sg/)).toBeVisible();
  await expect(page.getByRole('group', { name: 'Servings' })).toHaveCount(0);
  await checkPage(page);
  const saved = await (await page.request.get(`/api/v1/recipes/${recipe.id}`)).json();
  expect(saved.serves).toBeNull();
  expect(saved.makes.amount).toBe(200);
  expect(saved.version).toBe(1);
  // At 200% text it still fits beside "Ingredients", or under it.
  await page.evaluate(() => (document.documentElement.style.fontSize = '200%'));
  await expectNoSidewaysScroll(page);
  const box = await stepper.boundingBox();
  expect(box!.x + box!.width).toBeLessThanOrEqual(page.viewportSize()!.width);
  // Leaving and coming back starts at 1× again.
  await page.evaluate(() => (document.documentElement.style.fontSize = ''));
  await page.goBack();
  await page.goForward();
  await expect(stepper.getByText('Makes 200 g')).toBeVisible();
});

test('one line is enough', async ({ page }) => {
  const dal = await makeFood(page, unique('Toor dal'));
  const recipe = await makeRecipe(page, { name: unique('Single'), lines: [line(dal, 100)] });
  await page.goto(`/recipes/${recipe.id}`);
  await expect(page.getByRole('region', { name: 'Ingredients' }).getByRole('listitem')).toHaveCount(1);
  await checkPage(page);
});

const LONG = [
  'பச்சைப் பயறு (பாசிப்பயறு) முழுதாக, கரிம விவசாயிகளின் சந்தையில் வாங்கியது',
  'Organic stone-ground whole wheat flour flatbreads from the Saturday market, coarse, 5 kg bag',
];

test('many lines and steps with very long names, and the text at 200%, never scroll sideways', async ({ page }) => {
  const foods: number[] = [];
  for (let i = 0; i < 12; i++) foods.push(await makeFood(page, unique(`Ingredient ${i}`)));
  const lines = Array.from({ length: 80 }, (_, i) => ({
    ...line(foods[i % foods.length]!, 10 + i, 'g', i < 2 ? LONG[i]! : `ingredient line number ${i}`),
    note: i < 3 ? `${LONG[1]!} ${LONG[0]!}` : null,
  }));
  const steps = Array.from({ length: 60 }, (_, i) => ({ text: i < 2 ? LONG[i]! : `Step number ${i}: stir it well.` }));
  const name = `${LONG[0]!} ${LONG[1]!}`.slice(0, 180);
  const recipe = await makeRecipe(page, {
    name,
    description: LONG[1],
    tags: ['Quick', 'Kids', 'Festival and special-occasion cooking', 'பச்சைப் பயறு (பாசிப்பயறு) முழுதாக'],
    nutrition: { kcal: 12345, protein: 1234.5, carbs: 1, fat: 1, fibre: 1 },
    lines,
    steps,
  });
  await page.goto(`/recipes/${recipe.id}`);
  await expect(page.getByRole('heading', { level: 1 })).toBeVisible();
  await expect(page.getByRole('region', { name: 'Ingredients' }).getByRole('listitem')).toHaveCount(80);
  await checkPage(page);
  await page.evaluate(() => (document.documentElement.style.fontSize = '200%'));
  await expect(page.getByRole('heading', { level: 1 })).toBeVisible();
  await expectNoSidewaysScroll(page);
  if (isPhone(page)) {
    // The servings and the missing line still fit at 200%.
    const box = await page.getByRole('group', { name: 'Servings' }).boundingBox();
    expect(box!.x + box!.width).toBeLessThanOrEqual(page.viewportSize()!.width);
  }
});

test('reduced motion: nothing on the page animates', async ({ page }) => {
  const { recipe, name } = await sambar(page);
  await page.emulateMedia({ reducedMotion: 'reduce' });
  await page.goto(`/recipes/${recipe.id}`);
  await expect(page.getByRole('heading', { name, level: 1 })).toBeVisible();
  const running = await page.evaluate(
    () => document.getAnimations().filter((a) => a.playState === 'running' && (a.effect?.getTiming().duration as number) > 0.1).length,
  );
  expect(running).toBe(0);
});

// --- Optional ingredients and steps, and the nutrition note (0.8 R3, F151) ----------------------

test('an optional line and step are marked, and the nutrition note leads to the figures and goes when they are saved', async ({ page }) => {
  const name = unique('Biryani');
  const created = await makeRecipe(page, {
    name,
    nutrition: { kcal: 610 },
    lines: [
      { words: 'mutton', amount: 1, unit: 'kg' },
      { words: 'raw papaya paste', amount: 2, unit: 'tbsp', optional: true },
    ],
    steps: [{ text: 'Rub the mutton.' }, { text: 'Fry onions for the top.', optional: true }],
  });
  // An ingredient line changes after the figures were set: the recipe says so.
  const lines = created.lines.map((l: any) => ({ id: l.id, words: l.words, amount: l.id === created.lines[0].id ? 2 : l.amount, unit: l.unit, optional: l.optional }));
  await call(page, 'PUT', `/recipes/${created.id}`, { name, version: created.version, nutrition: created.nutrition, lines, steps: created.steps.map((s: any) => ({ text: s.text, optional: s.optional })) }, 200);
  await page.goto(`/recipes/${created.id}`);
  const recipe = reader(page);
  await expect(recipe.getByRole('heading', { name, level: 1 })).toBeVisible();
  await expect(recipe.getByText('Optional', { exact: true })).toHaveCount(1);
  await expect(recipe.getByText('Optional step', { exact: true })).toHaveCount(1);
  await expect(recipe.getByRole('note')).toContainText('Nutrition possibly out of date: the ingredients changed since it was worked out.');
  await checkPage(page);
  await recipe.getByRole('link', { name: 'Work it out again' }).click();
  await expect(page).toHaveURL(/\/recipes\/\d+\/edit\?nutrition=1$/);
  await expect(page.getByRole('textbox', { name: 'kcal' })).toBeFocused();
  await page.getByRole('button', { name: /^Save/ }).click();
  await expect(page).toHaveURL(new RegExp(`/recipes/${created.id}$`));
  await expect(page.getByRole('note')).toHaveCount(0);
  await expect(page.getByText('Nutrition possibly out of date')).toHaveCount(0);
});
