import { test, expect, type Page } from './clock.ts';
import { setAccountTheme } from './a11y.ts';

// The 0.7 paper cuts on the recipe screens (PC1): the editor carries on where you left off, and
// Duplicate. Against the real server, signed in as the test admin.

type Json = Record<string, any>; // eslint-disable-line @typescript-eslint/no-explicit-any

const unique = (name: string) => `${name} ${test.info().project.name.replace(/\D/g, '')}${Date.now() % 100000}`;

async function makeRecipe(page: Page, body: Json): Promise<Json> {
  const response = await page.request.post('/api/v1/recipes', {
    data: body,
    headers: { 'idempotency-key': crypto.randomUUID() },
  });
  expect(response.status(), await response.text()).toBe(201);
  return (await response.json()) as Json;
}

const nameBox = (page: Page) => page.getByLabel('Name', { exact: true });
const carrying = (page: Page) => page.getByText('Carrying on where you left off');

test.beforeEach(async ({ page }) => {
  await setAccountTheme(page, 'auto');
});

test('a reload keeps a new recipe’s edits; Start over drops them', async ({ page }) => {
  const name = unique('Half a dosa');
  await page.goto('/recipes/new');
  await expect(carrying(page)).toHaveCount(0);
  await nameBox(page).fill(name);
  await page.reload();
  await expect(carrying(page)).toBeVisible();
  await expect(nameBox(page)).toHaveValue(name);

  await page.getByRole('button', { name: 'Start over' }).click();
  await expect(nameBox(page)).toHaveValue('');
  await expect(carrying(page)).toHaveCount(0);
  await page.reload();
  await expect(nameBox(page)).toHaveValue('');
  await expect(carrying(page)).toHaveCount(0);
});

test('a reload keeps an existing recipe’s edits; Start over opens the saved recipe again', async ({ page }) => {
  const name = unique('Rasam');
  const recipe = await makeRecipe(page, { name });
  await page.goto(`/recipes/${recipe.id}/edit`);
  await expect(nameBox(page)).toHaveValue(name);
  await nameBox(page).fill(`${name} changed`);
  await page.reload();
  await expect(carrying(page)).toBeVisible();
  await expect(nameBox(page)).toHaveValue(`${name} changed`);
  await page.getByRole('button', { name: 'Start over' }).click();
  await expect(nameBox(page)).toHaveValue(name);
  await expect(carrying(page)).toHaveCount(0);
});

test('another recipe’s editor is not touched', async ({ page }) => {
  const [a, b] = [unique('Alpha'), unique('Beta')];
  const first = await makeRecipe(page, { name: a });
  const second = await makeRecipe(page, { name: b });
  await page.goto(`/recipes/${first.id}/edit`);
  await nameBox(page).fill(`${a} edited`);
  await page.goto(`/recipes/${second.id}/edit`);
  await expect(nameBox(page)).toHaveValue(b);
  await expect(carrying(page)).toHaveCount(0);
});

test('Save clears what the tab kept', async ({ page }) => {
  const name = unique('Saved dosa');
  await page.goto('/recipes/new');
  await nameBox(page).fill(name);
  await page.getByRole('button', { name: /^Save/ }).click();
  await expect(page).toHaveURL(/\/recipes\/\d+$/);
  await page.goto('/recipes/new');
  await expect(nameBox(page)).toHaveValue('');
  await expect(carrying(page)).toHaveCount(0);
});

test('Cancel clears it too, and Undo still brings the editor back as it was', async ({ page }) => {
  const name = unique('Cancelled dosa');
  await page.goto('/recipes/new');
  await nameBox(page).fill(name);
  await page.getByRole('button', { name: 'Cancel' }).click();
  await expect(page).toHaveURL('/recipes');
  await page.goto('/recipes/new');
  await expect(nameBox(page)).toHaveValue('');
  await expect(carrying(page)).toHaveCount(0);

  await nameBox(page).fill(name);
  await page.getByRole('button', { name: 'Cancel' }).click();
  await expect(page.getByText('Changes not saved')).toBeVisible();
  await page.getByRole('button', { name: 'Undo', exact: true }).click();
  await expect(page).toHaveURL('/recipes/new');
  await expect(nameBox(page)).toHaveValue(name);
});

test('Duplicate makes "(copy)", opens it in the editor, and leaves the original alone', async ({ page }) => {
  const name = unique('Sambar');
  const recipe = await makeRecipe(page, {
    name,
    serves: 6,
    tags: ['Batch-friendly'],
    lines: [{ words: 'toor dal', amount: '200', unit: 'g' }, { words: 'salt' }],
    steps: [{ text: 'Boil the dal.' }],
  });
  await page.goto(`/recipes/${recipe.id}`);
  await page.getByRole('button', { name: `More for ${name}` }).click();
  await page.getByRole('menuitem', { name: 'Duplicate' }).click();
  await expect(page).toHaveURL(/\/recipes\/\d+\/edit$/);
  const copyId = Number(new URL(page.url()).pathname.split('/').at(-2));
  expect(copyId).not.toBe(recipe.id);
  await expect(nameBox(page)).toHaveValue(`${name} (copy)`);
  await expect(page.getByLabel('Ingredient 1', { exact: true })).toHaveValue('toor dal');
  await expect(page.getByRole('group', { name: 'Serves' })).toContainText('6');

  const copy = await (await page.request.get(`/api/v1/recipes/${copyId}`)).json();
  expect(copy.lines.map((l: Json) => l.words)).toEqual(['toor dal', 'salt']);
  expect(copy.steps.map((x: Json) => x.text)).toEqual(['Boil the dal.']);
  expect(copy.tags).toEqual(['Batch-friendly']);
  const original = await (await page.request.get(`/api/v1/recipes/${recipe.id}`)).json();
  expect(original.name).toBe(name);
  expect(original.version).toBe(recipe.version);
});
