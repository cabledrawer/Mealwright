import { test, expect, testNow, type Page } from './clock.ts';
import { workerReady } from './worker.ts';
import { checkPage, inTheme, isPhone, setAccountTheme } from './a11y.ts';

// The recipe editor (0.4): New recipe and Edit recipe, against the real server. Runs in the
// "phone 0.4 editor" and "desktop 0.4 editor" projects, signed in as the test admin.

/** A 2 × 2 pixel PNG, for the photo tests. */
const DISH = Buffer.from(
  'iVBORw0KGgoAAAANSUhEUgAAAAIAAAACCAIAAAD91JpzAAAAEElEQVR4nGN4VqcERAwQCgAtxgYZHCtf2QAAAABJRU5ErkJggg==',
  'base64',
);

type Json = Record<string, any>; // eslint-disable-line @typescript-eslint/no-explicit-any

const unique = (name: string) => `${name} ${test.info().project.name.replace(/\D/g, '')}${Date.now() % 100000}`;

async function post(page: Page, path: string, data: Json | Buffer, headers: Record<string, string> = {}) {
  const response = await page.request.post(`/api/v1${path}`, {
    data,
    headers: { 'idempotency-key': crypto.randomUUID(), ...headers },
  });
  expect(response.status(), await response.text()).toBeLessThan(300);
  return (await response.json()) as Json;
}

async function makeFood(page: Page, name: string, other?: string): Promise<Json> {
  const made = await post(page, '/foods', { name, counted_as: 'weight' });
  if (other) await post(page, `/foods/${made.food.id}/other-names`, { name: other });
  return made.food;
}

async function makeRecipe(page: Page, body: Json): Promise<Json> {
  return post(page, '/recipes', body);
}

async function getRecipe(page: Page, id: number): Promise<Json> {
  const response = await page.request.get(`/api/v1/recipes/${id}`);
  expect(response.status()).toBe(200);
  return (await response.json()) as Json;
}

const save = (page: Page) => page.getByRole('button', { name: /^Save/ });

test.beforeEach(async ({ page }) => {
  await setAccountTheme(page, 'auto');
});

test('a new recipe: New recipe opens it, Save waits for a name, lands on the recipe, and Edit opens it again', async ({ page }) => {
  await page.goto('/recipes');
  // The list's count ("0 recipes") shows when the list has loaded. On an empty kitchen the page
  // then swaps its "New recipe" button for a new one, so a menu opened before that is closed
  // under the click (the app's behaviour; the test waits for the settled page).
  await expect(page.getByText(/^\d+ recipes?$/)).toBeVisible();
  await page.getByRole('button', { name: 'New recipe', exact: true }).click();
  await page.getByRole('menuitem', { name: 'Add by hand' }).click();
  await expect(page).toHaveURL(/\/recipes\/new$/);
  await expect(page.getByRole('heading', { level: 1 })).toHaveText('New recipe');
  await expect(save(page)).toBeDisabled();
  await expect(page.getByText('A name is all you need to save.')).toBeVisible();
  // A new recipe starts at Serves 4.
  await expect(page.getByRole('group', { name: 'Serves' })).toContainText('4');

  const name = unique('Rasam');
  await page.getByLabel('Name', { exact: true }).fill(name);
  await expect(save(page)).toBeEnabled();
  await save(page).click();

  // It lands on the recipe's page, with "Saved".
  await expect(page).toHaveURL(/\/recipes\/\d+$/);
  await expect(page.getByRole('status').filter({ hasText: 'Saved' })).toBeVisible();
  await expect(page.getByRole('heading', { name, level: 1 })).toBeVisible();
  const id = Number(new URL(page.url()).pathname.split('/').at(-1));
  const recipe = await getRecipe(page, id);
  expect(recipe.name).toBe(name);
  expect(recipe.serves).toBe(4);
  expect(recipe.version).toBe(1);

  // Edit, at the top of the recipe page, opens the editor filled in.
  await page.getByRole('link', { name: 'Edit', exact: true }).click();
  await expect(page).toHaveURL(new RegExp(`/recipes/${id}/edit$`));
  await expect(page.getByRole('heading', { level: 1 })).toHaveText('Edit recipe');
  await expect(page.getByLabel('Name', { exact: true })).toHaveValue(name);
});

test('every box is saved, and Edit opens them filled in', async ({ page }) => {
  const toor = await makeFood(page, unique('Toor dal'), 'thuvaram paruppu');
  const name = unique('Sambar');
  await page.goto('/recipes/new');
  await page.getByLabel('Name', { exact: true }).fill(name);
  await page.getByLabel('Short description').fill('Lentil & vegetable stew');
  await page.getByLabel('Time').fill('50');
  await page.getByRole('button', { name: 'More servings' }).click();
  await page.getByLabel('Makes amount').fill('1.5');
  await page.getByLabel('Makes unit').selectOption('l');
  await page.getByLabel('Tags').fill('Batch-friendly');
  await page.keyboard.press('Enter');
  await page.getByLabel('Tags').fill('Quick,');
  await page.getByLabel('kcal').fill('320');
  await page.getByLabel('protein g').fill('14,5');
  await page.getByLabel('Source').fill('Tess’s');

  // A new recipe starts with one empty line and one empty step. "thuvaram" is only the start of
  // another name ("thuvaram paruppu"), so picking fills in the ingredient's name (cabledrawer 25 Oct).
  await pickIngredient(page, 1, 'thuvaram', toor.name);
  await page.getByLabel('Amount for ingredient 1').fill('1½');
  await page.getByLabel('Unit for ingredient 1').selectOption('cup');
  await page.getByLabel('Note for ingredient 1').fill('rinsed');
  // A line with no amount is fine.
  await page.getByRole('button', { name: '+ Add line' }).click();
  await typeWords(page, 2, 'salt to taste');
  // A heading, moved to the top with the keyboard.
  await page.getByRole('button', { name: '+ Add heading' }).first().click();
  await page.getByRole('textbox', { name: 'Heading 3', exact: true }).fill('For the dal');
  await page.getByRole('button', { name: /^Move heading 3\./ }).focus();
  await page.keyboard.press('Alt+ArrowUp');
  await page.keyboard.press('Alt+ArrowUp');
  await page.getByRole('textbox', { name: 'Step 1', exact: true }).fill('Boil the dal.');
  await page.getByRole('button', { name: '+ Add step' }).click();
  await page.getByRole('textbox', { name: 'Step 2', exact: true }).fill('Add the tamarind.');

  await save(page).click();
  await expect(page).toHaveURL(/\/recipes\/\d+$/);
  const id = Number(new URL(page.url()).pathname.split('/').at(-1));
  const recipe = await getRecipe(page, id);
  expect(recipe).toMatchObject({
    name,
    description: 'Lentil & vegetable stew',
    time_minutes: 50,
    serves: 5,
    makes: { amount: 1.5, unit: 'l' },
    tags: ['Batch-friendly', 'Quick'],
    source_note: 'Tess’s',
    nutrition: { kcal: 320, protein: 14.5, carbs: null },
  });
  expect(recipe.lines.map((l: Json) => [l.kind, l.words, l.amount_text, l.unit, l.food?.id ?? null, l.note])).toEqual([
    ['heading', 'For the dal', null, null, null, null],
    ['ingredient', toor.name, '1½', 'cup', toor.id, 'rinsed'],
    ['ingredient', 'salt to taste', null, null, null, null],
  ]);
  expect(recipe.steps.map((s: Json) => s.text)).toEqual(['Boil the dal.', 'Add the tamarind.']);

  await page.goto(`/recipes/${id}/edit`);
  await expect(page.getByRole('heading', { level: 1 })).toHaveText('Edit recipe');
  await expect(page.getByLabel('Name', { exact: true })).toHaveValue(name);
  await expect(page.getByLabel('Time')).toHaveValue('50');
  await expect(page.getByLabel('Amount for ingredient 2')).toHaveValue('1½');
  // The words are the ingredient's own name, so "Linked to" has nothing to add.
  await expect(page.getByText('Linked to')).toHaveCount(0);
  await expect(page.getByText('Not linked')).toBeVisible();
  await expect(page.getByRole('textbox', { name: 'Step 2', exact: true })).toHaveValue('Add the tamarind.');
  await expect(page.getByRole('button', { name: 'Delete recipe' })).toBeVisible();
});

/** Type the line's own words, linking nothing (the pick-list opens; Escape shuts it). */
async function typeWords(page: Page, n: number, text: string) {
  const box = page.getByLabel(`Ingredient ${n}`, { exact: true });
  await box.fill(text);
  await box.press('Escape');
  await expect(page.getByRole('listbox', { name: 'Matching ingredients' })).toBeHidden();
}

/** Type in the ingredient box of line `n` (1 is the first) and pick the option with `name`. */
async function pickIngredient(page: Page, n: number, typed: string, name: string) {
  await page.getByLabel(`Ingredient ${n}`, { exact: true }).fill(typed);
  await page
    .getByRole('listbox', { name: 'Matching ingredients' })
    .getByRole('option', { name: new RegExp(`^${name}`) })
    .click();
}

test('a line linked from the start of a name shows the full name; words typed in full stay (cabledrawer 25 Oct)', async ({ page }) => {
  const toor = await makeFood(page, unique('Toor Dal'), 'thuvaram paruppu');
  const coriander = await makeFood(page, unique('Coriander'));
  // Saved the 0.5.0 way: the words as typed, linked to the ingredient picked.
  const recipe = await makeRecipe(page, {
    name: unique('Rasam'),
    lines: [
      { words: 'thu', amount: 100, unit: 'g', food_id: toor.id },
      { words: 'fresh coriander', food_id: coriander.id },
      { words: 'tamarind' },
    ],
  });

  await page.goto(`/recipes/${recipe.id}`);
  const lines = page.locator('.main');
  await expect(lines.filter({ hasText: 'g ' + toor.name })).toHaveCount(1);
  await expect(lines.filter({ hasText: /\bthu\b/ })).toHaveCount(0);
  await expect(lines.filter({ hasText: 'fresh coriander' })).toHaveCount(1);
  await expect(page.getByText(coriander.name, { exact: true })).toBeVisible();
  await expect(lines.filter({ hasText: 'tamarind' })).toHaveCount(1);

  // The editor opens with the full name, so Cancel with nothing else changed just closes.
  await page.goto(`/recipes/${recipe.id}/edit`);
  await expect(page.getByLabel('Ingredient 1', { exact: true })).toHaveValue(toor.name);
  await expect(page.getByLabel('Ingredient 2', { exact: true })).toHaveValue('fresh coriander');
  await expect(page.getByText('Linked to')).toContainText(coriander.name);
  await page.getByRole('button', { name: 'Cancel' }).click();
  await expect(page).toHaveURL(`/recipes/${recipe.id}`);
  await expect(page.getByText('Changes not saved')).toHaveCount(0);
});

test('Cancel with nothing changed just closes, with no toast', async ({ page }) => {
  await page.goto('/recipes/new');
  await page.getByRole('button', { name: 'Cancel' }).click();
  await expect(page).toHaveURL('/recipes');
  await expect(page.getByText('Changes not saved')).toHaveCount(0);
});

test('a new recipe cancelled with a typed name comes back with Undo', async ({ page }) => {
  await page.goto('/recipes/new');
  await page.getByLabel('Name', { exact: true }).fill('Half a recipe');
  await page.getByRole('button', { name: 'Cancel' }).click();
  await expect(page).toHaveURL('/recipes');
  await expect(page.getByText('Changes not saved')).toBeVisible();
  await page.getByRole('button', { name: 'Undo', exact: true }).click();
  await expect(page).toHaveURL('/recipes/new');
  await expect(page.getByLabel('Name', { exact: true })).toHaveValue('Half a recipe');
});

test('lines can be put in a new order with the keyboard and the mouse', async ({ page }) => {
  const recipe = await makeRecipe(page, {
    name: unique('Order'),
    lines: [{ words: 'alpha' }, { words: 'bravo' }, { words: 'charlie' }],
    steps: [{ text: 'one' }, { text: 'two' }],
  });
  await page.goto(`/recipes/${recipe.id}/edit`);
  await expect(page.locator('[data-line]')).toHaveCount(3);
  const words = async () =>
    page.locator('[data-line] [data-words]').evaluateAll((els) =>
      els.map((el) => (el instanceof HTMLInputElement ? el.value : (el.textContent ?? '').trim())),
    );
  expect(await words()).toEqual(['alpha', 'bravo', 'charlie']);

  const handle = page.getByRole('button', { name: /^Move ingredient 1\./ });
  await handle.focus();
  await page.keyboard.press('Alt+ArrowDown');
  expect(await words()).toEqual(['bravo', 'alpha', 'charlie']);
  await expect(page.getByRole('button', { name: /^Move ingredient 2\./ })).toBeFocused();
  await expect(page.getByText('Moved to 2 of 3')).toBeAttached();

  // Dragging the last handle above the first.
  const last = page.getByRole('button', { name: /^Move ingredient 3\./ });
  const first = page.getByRole('button', { name: /^Move ingredient 1\./ });
  // With the ingredient box on a line of its own on a phone, a line is taller (F36): scroll so
  // that the first line is at the top, and the last is still on the screen.
  await first.evaluate((el) => el.scrollIntoView({ block: 'start' }));
  const from = (await last.boundingBox())!;
  const to = (await first.boundingBox())!;
  await page.mouse.move(from.x + from.width / 2, from.y + from.height / 2);
  await page.mouse.down();
  await page.mouse.move(to.x + to.width / 2, to.y + 4, { steps: 8 });
  await page.mouse.up();
  expect(await words()).toEqual(['charlie', 'bravo', 'alpha']);

  await save(page).click();
  await expect(page).toHaveURL(`/recipes/${recipe.id}`);
  expect((await getRecipe(page, recipe.id)).lines.map((l: Json) => l.words)).toEqual(['charlie', 'bravo', 'alpha']);
});

test('removing a line has Undo', async ({ page }) => {
  const recipe = await makeRecipe(page, { name: unique('Remove line'), lines: [{ words: 'alpha' }, { words: 'bravo' }] });
  await page.goto(`/recipes/${recipe.id}/edit`);
  await page.getByRole('button', { name: 'Remove line' }).first().click();
  await expect(page.getByText('Removed alpha')).toBeVisible();
  await page.getByRole('button', { name: 'Undo', exact: true }).click();
  await expect(page.getByText('Undone: Removed alpha')).toBeVisible();
  await expect(page.locator('[data-line]')).toHaveCount(2);
});

test('a recipe can be an ingredient, and one that would make a loop is greyed out with the reason', async ({ page }) => {
  const powder = await makeRecipe(page, { name: unique('Sambar powder'), serves: null, makes: { amount: 200, unit: 'g' } });
  const sambar = await makeRecipe(page, {
    name: unique('Sambar'),
    lines: [{ words: 'Sambar powder', amount: 2, unit: 'tbsp', recipe_id: powder.id }],
  });
  // Sambar powder can't use Sambar, because Sambar uses Sambar powder.
  await page.goto(`/recipes/${powder.id}/edit`);
  await page.getByRole('button', { name: '+ Add line' }).click();
  const query = sambar.name.split(' ').slice(0, 2).join(' ');
  await page.getByLabel('Ingredient 1', { exact: true }).fill(query);
  const picker = page.getByRole('listbox', { name: 'Matching ingredients' });
  const blocked = picker.getByRole('option', { name: new RegExp(`^${sambar.name}`) });
  await expect(blocked).toHaveAttribute('aria-disabled', 'true');
  await expect(picker.getByText(`can’t use ${sambar.name}, because ${sambar.name} uses ${powder.name}`)).toBeVisible();
  await blocked.click({ force: true }); // it says so (aria-disabled) but can be pressed: nothing happens
  await expect(picker.getByRole('option', { name: new RegExp(`^${sambar.name}`) })).toBeVisible(); // still open: nothing picked
  await checkPage(page);

  // The recipe itself.
  await page.getByLabel('Ingredient 1', { exact: true }).fill(powder.name);
  await expect(picker.getByText('A recipe can’t use itself.')).toBeVisible();
});

test('the pick-list opens while you type: other names, recipe counts, keys, and + New ingredient last (0.6)', async ({ page }) => {
  const drum = await makeFood(page, unique('Drumsticks'), 'murungakkai');
  await makeRecipe(page, { name: unique('Drum curry'), lines: [{ words: 'drumsticks', food_id: drum.id }] });
  const recipe = await makeRecipe(page, { name: unique('Pick list') });
  await page.goto(`/recipes/${recipe.id}/edit`);
  await page.getByRole('button', { name: '+ Add line' }).first().click();
  const box = page.getByLabel('Ingredient 1', { exact: true });
  await expect(box).toHaveAttribute('role', 'combobox');
  await expect(box).toHaveAttribute('aria-expanded', 'false');
  const word = drum.name.split(' ')[0].slice(0, 5);
  await box.fill(word);
  await expect(box).toHaveAttribute('aria-expanded', 'true');
  const list = page.getByRole('listbox', { name: 'Matching ingredients' });
  const option = list.getByRole('option', { name: new RegExp(`^${drum.name}`) });
  await expect(option).toContainText('also called murungakkai');
  await expect(option).toContainText('in 1 recipe');
  // + New ingredient is the last option.
  await expect(list.getByRole('option').last()).toHaveText(`+ New ingredient “${word}”`);
  // Typing alone links nothing; the arrow keys and Enter pick, and the line shows the full name.
  await expect(page.getByText('Not linked')).toBeVisible();
  // Other tests' drumsticks share the household, so walk down to this one.
  const names = await list.getByRole('option').allTextContents();
  const at = names.findIndex((n) => n.startsWith(drum.name));
  for (let i = 0; i <= at; i++) await box.press('ArrowDown');
  await expect(option).toHaveAttribute('aria-selected', 'true');
  await box.press('Enter');
  await expect(box).toHaveValue(drum.name);
  await expect(box).toHaveAttribute('aria-expanded', 'false');
  await expect(page.getByText('Not linked')).toHaveCount(0);
  // Escape shuts the list and keeps the words.
  await box.fill(`${drum.name} leaves`);
  await expect(box).toHaveAttribute('aria-expanded', 'true');
  await box.press('Escape');
  await expect(box).toHaveAttribute('aria-expanded', 'false');
  await expect(box).toHaveValue(`${drum.name} leaves`);
  await checkPage(page);
});

test('Enter in the last box adds a new line, and the order is Ingredient, Amount, Unit, Note (F36)', async ({ page }) => {
  const recipe = await makeRecipe(page, { name: unique('Enter adds') });
  await page.goto(`/recipes/${recipe.id}/edit`);
  await page.getByRole('button', { name: '+ Add line' }).first().click();
  const boxes = page.locator('[data-line]').first().locator('input:visible, select:visible');
  const labels = await boxes.evaluateAll((els) => els.map((e) => e.getAttribute('aria-label') ?? ''));
  expect(labels).toEqual([
    'Ingredient 1',
    'Amount for ingredient 1',
    'Unit for ingredient 1',
    'Note for ingredient 1',
  ]);
  await expect(page.locator('[data-line]')).toHaveCount(1);
  await page.getByLabel('Note for ingredient 1').fill('rinsed');
  await page.getByLabel('Note for ingredient 1').press('Enter');
  await expect(page.locator('[data-line]')).toHaveCount(2);
  await expect(page.getByLabel('Ingredient 2', { exact: true })).toBeFocused();
  // Enter in a box that is not the last one adds nothing.
  await page.getByLabel('Note for ingredient 1').press('Enter');
  await expect(page.locator('[data-line]')).toHaveCount(2);
});

test('a recipe used as an ingredient is saved as a recipe line', async ({ page }) => {
  const powder = await makeRecipe(page, { name: unique('Podi'), serves: null });
  const outer = await makeRecipe(page, { name: unique('Outer') });
  await page.goto(`/recipes/${outer.id}/edit`);
  await page.getByRole('button', { name: '+ Add line' }).first().click();
  await pickIngredient(page, 1, powder.name, powder.name);
  await page.getByLabel('Amount for ingredient 1').fill('2');
  await page.getByLabel('Unit for ingredient 1').selectOption('tbsp');
  await expect(page.getByText('recipe', { exact: true })).toBeVisible();
  await save(page).click();
  await expect(page).toHaveURL(`/recipes/${outer.id}`);
  const saved = await getRecipe(page, outer.id);
  expect(saved.lines[0]).toMatchObject({ link: 'recipe', recipe: { id: powder.id }, unit: 'tbsp', amount_text: '2' });
});

test('+ New ingredient opens "Pantry keeps it by", then the line is linked', async ({ page }) => {
  const recipe = await makeRecipe(page, { name: unique('New ing') });
  await page.goto(`/recipes/${recipe.id}/edit`);
  await page.getByRole('button', { name: '+ Add line' }).first().click();
  const fresh = unique('Kokum');
  await page.getByLabel('Ingredient 1', { exact: true }).fill(fresh);
  await page.getByRole('option', { name: new RegExp(`^\\+ New ingredient “${fresh}”`) }).click();
  await expect(page.getByRole('heading', { name: 'Pantry keeps it by' })).toBeVisible();
  await page.getByRole('radio', { name: /By weight/ }).check();
  await page.getByRole('button', { name: /^(Add|Save|Done|Make)/ }).last().click();
  await expect(page.getByRole('heading', { name: 'Pantry keeps it by' })).toBeHidden();
  await save(page).click();
  await expect(page).toHaveURL(`/recipes/${recipe.id}`);
  const saved = await getRecipe(page, recipe.id);
  expect(saved.lines[0]).toMatchObject({ words: fresh, link: 'ingredient', food: { name: fresh } });
});

test('Made ahead says when an ingredient with that name is already there', async ({ page }) => {
  const batter = unique('Dosa batter');
  await makeFood(page, batter);
  await page.goto('/recipes/new');
  await page.getByLabel('Name', { exact: true }).fill(batter);
  await page.getByRole('switch', { name: 'Made ahead (keeps in the pantry)' }).click();
  await expect(
    page.getByText(`${batter} is already in Ingredients. It will be linked to this recipe, and its pantry stock stays.`),
  ).toBeVisible();
  await expect(page.getByText('Add how much it makes, so the pantry can count it.')).toBeVisible();
  // A name nobody has says what will be added instead.
  await page.getByLabel('Ingredient name').fill(unique('Idli batter'));
  await expect(page.getByText(/to Ingredients as homemade/)).toBeVisible();
  await expect(page.getByText(/is already in Ingredients/)).toHaveCount(0);
});

test('Made ahead makes the ingredient on Save, and turning it off keeps it', async ({ page }) => {
  const name = unique('Podi');
  await page.goto('/recipes/new');
  await page.getByLabel('Name', { exact: true }).fill(name);
  await page.getByRole('button', { name: 'Clear (for a batter or a powder)' }).click();
  await page.getByLabel('Makes amount').fill('200');
  await page.getByLabel('Makes unit').selectOption('g');
  await page.getByRole('switch', { name: 'Made ahead (keeps in the pantry)' }).click();
  await expect(page.getByText(`Adds ${name} to Ingredients as homemade`)).toBeVisible();
  await save(page).click();
  await expect(page).toHaveURL(/\/recipes\/\d+$/);
  const id = Number(new URL(page.url()).pathname.split('/').at(-1));
  let recipe = await getRecipe(page, id);
  expect(recipe).toMatchObject({ made_ahead: true, serves: null, homemade: { name } });

  await page.goto(`/recipes/${id}/edit`);
  await expect(page.getByText(`Kept in Ingredients as ${name}.`)).toBeVisible();
  await page.getByRole('switch', { name: 'Made ahead (keeps in the pantry)' }).click();
  await expect(page.getByText(`${name} stays in Ingredients, no longer linked to this recipe.`)).toBeVisible();
  await save(page).click();
  await expect(page).toHaveURL(`/recipes/${id}`);
  recipe = await getRecipe(page, id);
  expect(recipe.made_ahead).toBe(false);
  expect(recipe.homemade).toBeNull();
});

test('the photo: untouched leaves photo_id out, Remove photo sends null, Cancel frees an unsaved upload once Undo has gone', async ({ page }) => {
  const bodies: Json[] = [];
  const deleted: string[] = [];
  await page.route(/\/api\/v1\/recipes(\/\d+)?$/, async (route) => {
    const request = route.request();
    if (request.method() === 'PUT') bodies.push(request.postDataJSON() as Json);
    await route.continue();
  });
  await page.route(/\/api\/v1\/recipes\/photos\/\d+$/, async (route) => {
    if (route.request().method() === 'DELETE') deleted.push(route.request().url());
    await route.continue();
  });

  const recipe = await makeRecipe(page, { name: unique('Photo') });
  // 1. Pick a photo: it uploads at once; Save sends its id.
  await page.goto(`/recipes/${recipe.id}/edit`);
  await page.locator('input[type=file]').setInputFiles({ name: 'dish.png', mimeType: 'image/png', buffer: DISH });
  await expect(page.getByRole('img', { name: 'Cover for this recipe' })).toBeVisible();
  await expect(page.getByRole('button', { name: 'Change photo' })).toBeVisible();
  await save(page).click();
  await expect(page).toHaveURL(`/recipes/${recipe.id}`);
  expect(typeof bodies[0]!.photo_id).toBe('number');
  const photo = (await getRecipe(page, recipe.id)).photo;
  expect(photo.id).toBe(bodies[0]!.photo_id);

  // 2. Change something else: the photo is left alone, so photo_id is left out.
  await page.goto(`/recipes/${recipe.id}/edit`);
  await expect(page.getByRole('img', { name: 'Cover for this recipe' })).toBeVisible();
  await page.getByLabel('Short description').fill('Still has its photo');
  await save(page).click();
  await expect(page).toHaveURL(`/recipes/${recipe.id}`);
  expect('photo_id' in bodies[1]!).toBe(false);
  expect((await getRecipe(page, recipe.id)).photo.id).toBe(photo.id);

  // 3. Remove photo: photo_id is sent as null.
  await page.goto(`/recipes/${recipe.id}/edit`);
  await page.getByRole('button', { name: 'Remove photo' }).click();
  await expect(page.getByRole('button', { name: 'Add a photo' })).toBeVisible();
  await save(page).click();
  await expect(page).toHaveURL(`/recipes/${recipe.id}`);
  expect(bodies[2]).toHaveProperty('photo_id', null);
  expect((await getRecipe(page, recipe.id)).photo).toBeNull();

  // 4. Cancel: an upload nobody took is deleted so its place is free.
  // (A new recipe: Cancel lands on All recipes, which this branch has.)
  await page.goto('/recipes/new');
  await page.locator('input[type=file]').setInputFiles({ name: 'dish.png', mimeType: 'image/png', buffer: DISH });
  await expect(page.getByRole('button', { name: 'Change photo' })).toBeVisible();
  await page.getByRole('button', { name: 'Cancel' }).click();
  await expect(page).toHaveURL('/recipes');
  // While "Changes not saved · Undo" is up the upload is kept, so Undo can bring it back...
  await expect(page.getByText('Changes not saved')).toBeVisible();
  expect(deleted.length).toBe(0);
  // ...and it goes once that toast has gone (the page's clock jumps the toast's seconds, one at a
  // time, instead of the test waiting for them).
  await expect
    .poll(async () => {
      await page.clock.runFor(1000);
      return deleted.length;
    }, { timeout: 20_000 })
    .toBe(1);
});

test('the server’s words about a photo are shown as they are', async ({ page }) => {
  await page.goto('/recipes/new');
  const upload = page.locator('input[type=file]');
  await upload.setInputFiles({ name: 'notes.txt', mimeType: 'image/jpeg', buffer: Buffer.from('not a picture') });
  await expect(page.getByRole('alert').filter({ hasText: "That isn’t a photo Mealwright can use." })).toBeVisible();
  await expect(page.getByRole('button', { name: 'Add a photo' })).toBeVisible();

  await upload.setInputFiles({ name: 'huge.jpg', mimeType: 'image/jpeg', buffer: Buffer.alloc(16 * 1024 * 1024, 1) });
  await expect(page.getByText('That photo is bigger than 15 MB.')).toBeVisible();

  await page.route('**/api/v1/recipes/photos', (route) =>
    route.fulfill({
      status: 422,
      contentType: 'application/json',
      body: JSON.stringify({
        detail: 'That photo is too big to use (over 50 megapixels). Try a smaller copy.',
        code: 'too_many_pixels',
      }),
    }),
  );
  await upload.setInputFiles({ name: 'dish.png', mimeType: 'image/png', buffer: DISH });
  await expect(page.getByText('That photo is too big to use (over 50 megapixels). Try a smaller copy.')).toBeVisible();

  await page.route('**/api/v1/recipes/photos', (route) =>
    route.fulfill({
      status: 409,
      contentType: 'application/json',
      body: JSON.stringify({
        detail: 'Too many photos waiting to be saved. Save or cancel a recipe first.',
        code: 'too_many_photos_waiting',
      }),
    }),
  );
  await upload.setInputFiles({ name: 'dish.png', mimeType: 'image/png', buffer: DISH });
  await expect(page.getByText('Too many photos waiting to be saved. Save or cancel a recipe first.')).toBeVisible();
});

test('a photo shows "uploading" while it is on its way, and its bar stops moving with reduced motion', async ({ page }) => {
  await page.emulateMedia({ reducedMotion: 'reduce' });
  let release = () => {};
  const held = new Promise<void>((done) => (release = done));
  await page.route('**/api/v1/recipes/photos', async (route) => {
    await held;
    await route.continue();
  });
  await page.goto('/recipes/new');
  await page.getByLabel('Name', { exact: true }).fill(unique('Uploading'));
  await page.locator('input[type=file]').setInputFiles({ name: 'dish.png', mimeType: 'image/png', buffer: DISH });
  await expect(page.getByText('Uploading photo…')).toBeVisible();
  await expect(save(page)).toBeDisabled(); // Save waits for the photo's id
  const duration = await page.getByRole('progressbar').locator('span').evaluate((el) => getComputedStyle(el).animationDuration);
  expect(duration).toBe('1e-05s');
  await checkPage(page);
  release();
  await expect(page.getByRole('button', { name: 'Change photo' })).toBeVisible();
  await expect(save(page)).toBeEnabled();
});

test('two people editing: the second Save is stopped, Wren’s version opens over the editor, Save mine anyway saves', async ({ page }) => {
  const recipe = await makeRecipe(page, {
    name: unique('Conflict'),
    lines: [{ words: 'dal', amount: 200, unit: 'g' }, { words: 'turmeric' }],
    steps: [{ text: 'Boil.' }],
  });
  await page.goto(`/recipes/${recipe.id}/edit`);
  await page.getByLabel('Short description').fill('Mine');
  // Someone else saves first.
  const response = await page.request.put(`/api/v1/recipes/${recipe.id}`, {
    data: {
      name: recipe.name,
      version: recipe.version,
      overwrite: false,
      serves: 6,
      lines: [
        { id: recipe.lines[0].id, words: 'dal', amount: 300, unit: 'g' },
        { id: recipe.lines[1].id, words: 'turmeric' },
        { words: 'aubergine', amount: 1 },
      ],
      steps: [{ text: 'Boil.' }],
    },
  });
  expect(response.status()).toBe(200);

  await save(page).click();
  const banner = page.getByRole('alert').filter({ hasText: 'changed this recipe after you opened it.' });
  await expect(banner).toBeVisible();
  await expect(banner).toContainText('Tess changed this recipe after you opened it.');
  await banner.getByRole('button', { name: /^See .*version$/ }).click();
  const sheet = page.getByRole('dialog', { name: /version$/ });
  await expect(sheet).toBeVisible();
  await expect(sheet).toContainText('was 200 g');
  await expect(sheet).toContainText('added by Tess');
  await expect(sheet).toContainText('Serves 6');
  await checkPage(page);
  await sheet.getByRole('button', { name: 'Back to my edit' }).click();
  await expect(sheet).toBeHidden();
  await expect(page.getByLabel('Short description')).toHaveValue('Mine'); // untouched

  await banner.getByRole('button', { name: 'Save mine anyway' }).click();
  await expect(page).toHaveURL(`/recipes/${recipe.id}`);
  const saved = await getRecipe(page, recipe.id);
  expect(saved.description).toBe('Mine');
  expect(saved.version).toBe(3);
});

test('"Couldn’t save. Try again." keeps what was typed, and Try again saves', async ({ page }) => {
  const recipe = await makeRecipe(page, { name: unique('Retry') });
  let fail = true;
  await page.route(`**/api/v1/recipes/${recipe.id}`, async (route) => {
    if (route.request().method() === 'PUT' && fail) {
      fail = false;
      return route.fulfill({ status: 500, contentType: 'application/json', body: '{"detail":"Something went wrong."}' });
    }
    return route.continue();
  });
  await page.goto(`/recipes/${recipe.id}/edit`);
  await page.getByLabel('Short description').fill('Typed before the failure');
  await save(page).click();
  const banner = page.getByRole('alert').filter({ hasText: 'Couldn’t save. Try again.' });
  await expect(banner).toBeVisible();
  await expect(page.getByLabel('Short description')).toHaveValue('Typed before the failure');
  await checkPage(page);
  await banner.getByRole('button', { name: 'Try again' }).click();
  await expect(page).toHaveURL(`/recipes/${recipe.id}`);
  expect((await getRecipe(page, recipe.id)).description).toBe('Typed before the failure');
});

test('offline: the editor stays open, Save is greyed out and says why', async ({ page, context }) => {
  await page.goto('/recipes/new');
  await page.getByLabel('Name', { exact: true }).fill('Typed offline');
  await page.waitForLoadState('networkidle'); // the app is watching the connection
  await workerReady(page);
  await context.setOffline(true);
  // The browser says so too (Playwright's switch does not send that word by itself).
  await page.evaluate(() => window.dispatchEvent(new Event('offline')));
  // A short blip shows nothing; the note comes after a few seconds (OFFLINE_AFTER_MS).
  await expect(page.getByText('You’re offline. Save when you’re back online.')).toBeVisible({ timeout: 10000 });
  await expect(save(page)).toBeDisabled();
  await expect(page.getByLabel('Name', { exact: true })).toHaveValue('Typed offline');
  await checkPage(page);
  await context.setOffline(false);
  await expect(save(page)).toBeEnabled({ timeout: 15000 });
});

test('a box the server refuses is marked, with its message under it', async ({ page }) => {
  await page.goto('/recipes/new');
  await page.getByLabel('Name', { exact: true }).fill(unique('Marked'));
  await page.getByLabel('Amount for ingredient 1').fill('lots');
  await typeWords(page, 1, 'salt');
  await save(page).click();
  await expect(page.getByText('Type an amount like 200, 1.5, ½ or 1½, or leave it empty.')).toBeVisible();
  await expect(page.getByLabel('Amount for ingredient 1')).toHaveAttribute('aria-invalid', 'true');
});

test('a line with an amount but no words is marked before anything is sent', async ({ page }) => {
  await page.goto('/recipes/new');
  await page.getByLabel('Name', { exact: true }).fill(unique('Empty words'));
  await page.getByLabel('Amount for ingredient 1').fill('2');
  await save(page).click();
  await expect(page.getByText('Type what it is, or pick an ingredient.')).toBeVisible();
  await expect(page).toHaveURL('/recipes/new');
});

test('Delete recipe goes at once, with Undo', async ({ page }) => {
  const name = unique('Doomed');
  const recipe = await makeRecipe(page, { name });
  await page.goto(`/recipes/${recipe.id}/edit`);
  await page.getByRole('button', { name: 'Delete recipe' }).click();
  await expect(page).toHaveURL('/recipes');
  await expect(page.getByText(`Deleted ${name}`)).toBeVisible();
  expect((await page.request.get(`/api/v1/recipes/${recipe.id}`)).status()).toBe(404);
  await page.getByRole('button', { name: 'Undo', exact: true }).click();
  await expect(page.getByText(`Undone: Deleted ${name}`)).toBeVisible();
  expect((await page.request.get(`/api/v1/recipes/${recipe.id}`)).status()).toBe(200);
});

test('Delete from Edit, reached from the recipe page, lands on All recipes, not another recipe (0.5.1)', async ({ page }) => {
  // cabledrawer 22 Oct (0.4.0): after Delete the app showed Egg Bhurji, a recipe he had opened before.
  const before = await makeRecipe(page, { name: unique('Egg Bhurji') });
  const name = unique('Doomed');
  const recipe = await makeRecipe(page, { name });
  // Search for each, so other tests' recipes can't push them off the first page.
  const search = page.getByRole('searchbox', { name: 'Search recipes' });
  await page.goto('/recipes');
  await search.fill(before.name);
  await page.getByRole('link', { name: new RegExp(before.name) }).first().click();
  await expect(page).toHaveURL(`/recipes/${before.id}`);
  if (isPhone(page)) await page.goto('/recipes');
  await search.fill(name);
  await page.getByRole('link', { name: new RegExp(name) }).first().click();
  await expect(page).toHaveURL(`/recipes/${recipe.id}`);
  await page.getByRole('link', { name: 'Edit', exact: true }).click();
  await expect(page).toHaveURL(`/recipes/${recipe.id}/edit`);
  await page.getByRole('button', { name: 'Delete recipe' }).click();
  await expect(page.getByText(`Deleted ${name}`)).toBeVisible();
  await expect(page).toHaveURL('/recipes');
  await expect(page.getByRole('heading', { name: before.name, level: 1 })).toHaveCount(0);
});

test('Delete recipe in the recipe page’s ⋯ menu: at once, "Deleted …" with Undo, on Recipes (0.6)', async ({ page }) => {
  const name = unique('Doomed');
  const recipe = await makeRecipe(page, { name });
  await page.goto(`/recipes/${recipe.id}`);
  await page.getByRole('button', { name: `More for ${name}` }).click();
  await expect(page.getByRole('menuitem')).toHaveText(['Duplicate', 'Delete recipe']);
  await page.getByRole('menuitem', { name: 'Delete recipe' }).click();
  await expect(page).toHaveURL('/recipes');
  await expect(page.getByText(`Deleted ${name}`)).toBeVisible();
  expect((await page.request.get(`/api/v1/recipes/${recipe.id}`)).status()).toBe(404);
  await page.getByRole('button', { name: 'Undo', exact: true }).click();
  await expect(page.getByText(`Undone: Deleted ${name}`)).toBeVisible();
  expect((await page.request.get(`/api/v1/recipes/${recipe.id}`)).status()).toBe(200);
});

test('Ctrl+S saves on a computer', async ({ page }) => {
  test.skip(isPhone(page), 'a keyboard shortcut');
  await page.goto('/recipes/new');
  await page.getByLabel('Name', { exact: true }).fill(unique('Ctrl S'));
  await page.keyboard.press('Control+s');
  await expect(page).toHaveURL(/\/recipes\/\d+$/);
});

test('a recipe that is not there says so', async ({ page }) => {
  await page.goto('/recipes/999999/edit');
  await expect(page.getByText('That recipe isn’t here any more.')).toBeVisible();
});

test('the editor passes the accessibility checks in both themes, new and filled in', async ({ page }) => {
  await page.goto('/recipes/new');
  await expect(page.getByRole('heading', { level: 1 })).toHaveText('New recipe');
  await checkPage(page);
  const food = await makeFood(page, unique('Toor'), 'arhar');
  const recipe = await makeRecipe(page, {
    name: unique('Filled in'),
    description: 'Lentil & vegetable stew',
    time_minutes: 50,
    tags: ['Quick', 'Batch-friendly'],
    lines: [
      { kind: 'heading', words: 'For the dal' },
      { words: 'arhar', amount: 200, unit: 'g', food_id: food.id, note: 'rinsed' },
      { words: 'karuveppilai', amount: 1 },
    ],
    steps: [{ kind: 'heading', text: 'The dal' }, { text: 'Boil.' }],
  });
  await page.goto(`/recipes/${recipe.id}/edit`);
  await expect(page.getByRole('textbox', { name: 'Step 1', exact: true })).toHaveValue('Boil.');
  await checkPage(page);
  await inTheme(page, 'dark');
});

test('Batch cook (B1): each step shows its guessed timing, a change makes it set by you, Save keeps it, Guess again undoes it', async ({ page }) => {
  const recipe = await makeRecipe(page, {
    name: unique('Timed sambar'),
    steps: [
      { text: 'Wash the toor dal and pressure cook it with turmeric for 3 whistles.' },
      { text: 'Chop the onion, tomato and drumsticks.' },
      { text: 'Boil the vegetables in the tamarind water until soft.' },
    ],
  });
  // The server has guessed them already, from the words.
  expect(recipe.steps[0].timing).toMatchObject({ hands: 'waiting', minutes: 15, equipment: 'pressure', hands_guessed: true });
  await page.goto(`/recipes/${recipe.id}/edit`);
  await expect(page.getByText('Waiting · 15 min').first()).toBeVisible(); // steps 1 and 3
  await expect(page.getByText('Pressure cooker', { exact: true })).toBeVisible();
  await expect(page.getByText('guessed', { exact: true })).toHaveCount(3);
  await expect(page.getByText('set by you', { exact: true })).toHaveCount(0);
  // Change step 2: all three become the person's.
  await page.getByRole('button', { name: 'Change the timing of step 2' }).click();
  await page.getByRole('radio', { name: 'Waiting' }).click();
  await page.getByRole('textbox', { name: /^Minutes/ }).fill('12');
  await page.getByRole('radio', { name: 'Hob ring' }).click();
  await expect(page.getByText('Waiting · 12 min')).toBeVisible();
  await expect(page.getByText('set by you', { exact: true })).toHaveCount(1);
  await expect(page.getByText('guessed', { exact: true })).toHaveCount(2);
  await checkPage(page);
  await save(page).click();
  await expect(page).toHaveURL(new RegExp(`/recipes/${recipe.id}$`));
  const saved = await getRecipe(page, recipe.id);
  expect(saved.steps[1].timing).toEqual({
    hands: 'waiting',
    minutes: 12,
    equipment: 'hob',
    hands_guessed: false,
    minutes_guessed: false,
    equipment_guessed: false,
  });
  expect(saved.steps[0].timing.hands_guessed).toBe(true);
  // Opened again it says so, and Guess again gives the guess back.
  await page.goto(`/recipes/${recipe.id}/edit`);
  await expect(page.getByText('set by you', { exact: true })).toHaveCount(1);
  await page.getByRole('button', { name: 'Change the timing of step 2' }).click();
  await page.getByRole('button', { name: 'Guess again' }).click();
  await expect(page.getByText('set by you', { exact: true })).toHaveCount(0);
  await save(page).click();
  await expect(page).toHaveURL(new RegExp(`/recipes/${recipe.id}$`));
  expect((await getRecipe(page, recipe.id)).steps[1].timing).toMatchObject({ hands: 'hands', equipment: 'none', hands_guessed: true });
});

test('Batch cook (B1): a step whose words change says its guess is made when saved, and a minutes box that is not a number stops Save until it is put right', async ({ page }) => {
  const recipe = await makeRecipe(page, { name: unique('Timed words'), steps: [{ text: 'Chop the onion.' }, { kind: 'heading', text: 'Tadka' }] });
  await page.goto(`/recipes/${recipe.id}/edit`);
  await expect(page.getByText('Hands-on · 5 min')).toBeVisible();
  await page.getByRole('textbox', { name: 'Step 1', exact: true }).fill('Pressure cook the dal for 3 whistles.');
  await expect(page.getByText('Guessed when you save')).toBeVisible();
  await page.getByRole('button', { name: 'Change the timing of step 1' }).click();
  await page.getByRole('textbox', { name: /^Minutes/ }).fill('ten');
  await expect(page.getByText('Type the minutes as a whole number, such as 10.').first()).toBeVisible();
  await save(page).click();
  await expect(page).toHaveURL(new RegExp(`/recipes/${recipe.id}/edit$`));
  await page.getByRole('textbox', { name: /^Minutes/ }).fill('10');
  await save(page).click();
  await expect(page).toHaveURL(new RegExp(`/recipes/${recipe.id}$`));
  // Only the minutes are the person's; the other two are guessed from the new words (B1 review r1 M3).
  expect((await getRecipe(page, recipe.id)).steps[0].timing).toMatchObject({
    minutes: 10,
    minutes_guessed: false,
    hands: 'waiting',
    hands_guessed: true,
    equipment: 'pressure',
    equipment_guessed: true,
  });
  // A heading has no timing boxes.
  await expect(page.getByRole('button', { name: /Change the timing of step 2/ })).toHaveCount(0);
});

test('a very long name wraps, and text at 200% still fits', async ({ browser }) => {
  // A new context gets the project's options and this worker's server and sign-in by itself.
  const context = await browser.newContext({ bypassCSP: true });
  await context.clock.install({ time: testNow() });
  const page = await context.newPage();
  try {
    const long = 'Tess’s Sunday drumstick and shallot sambar with freshly roasted sambar powder and a lot more words after that';
    const recipe = await makeRecipe(page, {
      name: long,
      description: 'துவரம் பருப்பு (தூர் தால்) முழுதாக, கரிம விவசாயிகளின் சந்தையில் வாங்கியது',
      lines: [{ words: 'thuvaram paruppu (tuvaram paruppu, arhar dal, துவரம் பருப்பு)', amount: 200, unit: 'g', note: 'soaked in warm water' }],
    });
    await page.goto(`/recipes/${recipe.id}/edit`);
    await page.addStyleTag({ content: 'html { font-size: 200% !important; }' });
    const name = page.getByLabel('Name', { exact: true });
    await expect(name).toHaveValue(long);
    // Not cut off: the box is as tall as its text.
    const fits = await name.evaluate((el) => el.scrollHeight <= el.clientHeight + 1);
    expect(fits).toBe(true);
    const sideways = await page.evaluate(() => document.documentElement.scrollWidth > document.documentElement.clientWidth);
    expect(sideways).toBe(false);
    await expect(page.getByRole('button', { name: /^Cancel/ })).toBeVisible();
    await expect(save(page)).toBeVisible();
  } finally {
    await context.close();
  }
});

test('F185: the pick-list opens from the box and stays clear of the sidebar, at a narrow window', async ({ page }) => {
  test.skip(isPhone(page), 'computer layout');
  const food = await makeFood(page, unique('Test Dosa batter'));
  const recipe = await makeRecipe(page, { name: unique('Narrow list') });
  await page.setViewportSize({ width: 912, height: 800 });
  await page.goto(`/recipes/${recipe.id}/edit`);
  await page.getByRole('button', { name: '+ Add line' }).first().click();
  const box = page.getByLabel('Ingredient 1', { exact: true });
  await box.fill(food.name.split(' ').slice(0, 2).join(' '));
  const list = page.getByRole('listbox', { name: 'Matching ingredients' });
  await expect(list.getByRole('option', { name: new RegExp(`^${food.name}`) })).toBeVisible();
  const popup = (await list.locator('xpath=../..').boundingBox())!;
  const input = (await box.boundingBox())!;
  const sidebar = (await page.getByRole('complementary', { name: 'Sidebar' }).boundingBox())!;
  expect(popup.x).toBeGreaterThanOrEqual(sidebar.x + sidebar.width);
  expect(popup.x).toBeGreaterThanOrEqual(input.x - 1);
  expect(popup.x + popup.width).toBeLessThanOrEqual(page.viewportSize()!.width);
});

test('a Waits box that is not a length stops Save and says so; the old wait is never saved quietly (M1)', async ({ page }) => {
  await page.goto('/recipes');
  const name = unique('Waity');
  const made = await post(page, '/recipes', {
    name,
    steps: [{ text: 'Marinate the paneer.', wait: { kind: 'marinate', min_minutes: 120 } }],
  });
  await page.goto(`/recipes/${made.id}/edit`);
  const length = page.getByLabel('Length', { exact: false }).first();
  await expect(length).toHaveValue('2');
  await length.fill('lots');
  await save(page).click();
  await expect(page.getByText('Type how long it waits, such as 4 hours.')).toBeVisible();
  await expect(page).toHaveURL(/\/edit$/);
  expect((await getRecipe(page, made.id)).version).toBe(1); // nothing was saved
  await length.fill('3');
  await save(page).click();
  await expect(page).toHaveURL(new RegExp(`/recipes/${made.id}$`));
  expect((await getRecipe(page, made.id)).steps[0].wait.min_minutes).toBe(180);
});

test('a recipe and an ingredient with the same name sit together, the recipe first, each labelled (F189)', async ({ page }) => {
  const name = unique('Dosa batter');
  const batter = await makeRecipe(page, { name });
  await makeFood(page, name);
  const recipe = await makeRecipe(page, { name: unique('Masala dosa') });
  await page.goto(`/recipes/${recipe.id}/edit`);
  await page.getByRole('button', { name: '+ Add line' }).first().click();
  const box = page.getByLabel('Ingredient 1', { exact: true });
  await box.fill(name);
  const list = page.getByRole('listbox', { name: 'Matching ingredients' });
  const options = list.getByRole('option');
  await expect(options.nth(0)).toContainText('Recipe');
  await expect(options.nth(0)).toContainText(name);
  await expect(options.nth(1)).toContainText('Ingredient');
  await expect(list.getByText('Recipes', { exact: true })).toHaveCount(0); // no group heading: no other recipe
  await checkPage(page);
  // The recipe is the first pick: Down, Enter.
  await box.press('ArrowDown');
  await box.press('Enter');
  await page.getByRole('button', { name: 'Save' }).first().click();
  await expect.poll(async () => (await getRecipe(page, recipe.id)).lines[0]?.link).toBe('recipe');
  expect((await getRecipe(page, recipe.id)).lines[0].recipe.id).toBe(batter.id);
});
