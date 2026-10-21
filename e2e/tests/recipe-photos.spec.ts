import { test, expect, type Locator, type Page } from './clock.ts';
import { checkPage, expectNoSidewaysScroll, isPhone, setAccountTheme } from './a11y.ts';
import { photoPng, uploadPhoto, type Shape } from '../review/photos.ts';

// Recipe photos on All recipes (the 52 px square at the start of each row) and on the recipe page
// (a box above the name on a phone, beside the nutrition figures in the computer's reading pane),
// against the real server. Every state (spec "Keeping the UI good", item 2): with and without a
// photo, a very tall and a very wide one (cropped, not stretched), a photo that can't be
// fetched (and tries again when the connection comes back), a name that wraps (the square stays at
// the top), the text at 200%, and Edit → Save with a new photo and with none. Runs in the
// "phone 0.4 photos" and "desktop 0.4 photos" projects, signed in as the test admin.

const key = () => ({ 'idempotency-key': crypto.randomUUID() });

async function call(page: Page, method: 'POST' | 'PUT', path: string, data: object, status = 201) {
  const response = await page.request.fetch(`/api/v1${path}`, { method, data, headers: key() });
  expect(response.status(), `${method} ${path}: ${await response.text()}`).toBe(status);
  return (await response.json()) as Record<string, any>;
}

const unique = (word: string) =>
  `${word} ${test.info().project.name.startsWith('phone') ? 'p' : 'd'}${Date.now().toString(36)}${Math.floor(Math.random() * 1296).toString(36)}`;

/** A recipe, with a test photo of this shape when one is asked for. Gives back the recipe and its photo. */
async function recipeWith(page: Page, name: string, shape?: Shape, extra: object = {}) {
  const photo = shape ? await uploadPhoto(page.request, shape) : undefined;
  const recipe = await call(page, 'POST', '/recipes', {
    name,
    time_minutes: 30,
    nutrition: { kcal: 320, protein: 16, carbs: 48, fat: 7, fibre: 11 },
    steps: [{ text: 'Stir.' }],
    ...(photo ? { photo_id: photo } : {}),
    ...extra,
  });
  return { recipe, photo: recipe.photo as { id: number; url: string; list_url: string; width: number; height: number } | null };
}

const search = (page: Page, words: string) => page.getByRole('searchbox', { name: 'Search recipes' }).fill(words);
const row = (page: Page, name: string) => page.getByRole('link', { name: new RegExp(name) });
/** The row's square: its first child. */
const square = (link: Locator) => link.locator('.square');
const reader = (page: Page) => (isPhone(page) ? page.locator('main') : page.getByRole('region', { name: 'Recipe', exact: true }));

/** The phone loses its connection, the photos come back, and so does the connection. */
async function offlineThenBack(page: Page) {
  await page.context().setOffline(true);
  await expect.poll(() => page.evaluate(() => navigator.onLine)).toBe(false);
  await page.unrouteAll();
  await page.context().setOffline(false);
}

/** Wait until the picture has really loaded: its natural size is known. */
const loaded = (img: Locator) => expect.poll(() => img.evaluate((el: HTMLImageElement) => el.complete && el.naturalWidth > 0)).toBe(true);

test.beforeEach(async ({ page }) => {
  await setAccountTheme(page, 'auto');
});

test('All recipes: the photo fills the row’s square (the small copy), and a recipe with none keeps the plain square', async ({ page }) => {
  const tag = unique('Photo');
  const { recipe: withPhoto, photo } = await recipeWith(page, `${tag} yes`, 'dish');
  await recipeWith(page, `${tag} no`, undefined, { time_minutes: null, nutrition: {} });
  await page.goto('/recipes');
  await search(page, tag);
  await expect(page.locator('li')).toHaveCount(2);

  const img = row(page, `${tag} yes`).locator('img');
  await expect(img).toHaveCount(1);
  expect(photo).toBeTruthy();
  await expect(img).toHaveAttribute('src', `/api/v1/recipes/photos/${photo!.id}/list`);
  expect(photo!.list_url).toBe(`/api/v1/recipes/photos/${photo!.id}/list`);
  await expect(img).toHaveAttribute('alt', '');
  await expect(img).toHaveAttribute('loading', 'lazy');
  await loaded(img);
  const box = await img.boundingBox();
  expect([box!.width, box!.height]).toEqual([52, 52]);
  expect(await img.evaluate((el) => getComputedStyle(el).objectFit)).toBe('cover');
  expect(await square(row(page, `${tag} yes`)).evaluate((el) => getComputedStyle(el).borderRadius)).toBe('12px');

  // None: no picture, the same plain 52 px square as before.
  await expect(row(page, `${tag} no`).locator('img')).toHaveCount(0);
  const plain = await square(row(page, `${tag} no`)).boundingBox();
  expect([plain!.width, plain!.height]).toEqual([52, 52]);
  expect(withPhoto.photo.id).toBe(photo!.id);
  await checkPage(page);
});

test('All recipes: a very tall and a very wide photo are cropped to the square, never stretched', async ({ page }) => {
  const tag = unique('Shape');
  await recipeWith(page, `${tag} tall`, 'tall');
  await recipeWith(page, `${tag} wide`, 'wide');
  await page.goto('/recipes');
  await search(page, tag);
  for (const shape of ['tall', 'wide']) {
    const img = row(page, `${tag} ${shape}`).locator('img');
    await loaded(img);
    const box = await img.boundingBox();
    expect([box!.width, box!.height]).toEqual([52, 52]);
    // The file keeps its own shape (cover crops it); the page doesn't squash it into a square.
    const natural = await img.evaluate((el: HTMLImageElement) => [el.naturalWidth, el.naturalHeight]);
    expect(shape === 'tall' ? natural[1]! > natural[0]! : natural[0]! > natural[1]!).toBe(true);
    expect(await img.evaluate((el) => getComputedStyle(el).objectFit)).toBe('cover');
  }
});

test('All recipes: a photo that can’t be fetched leaves the plain square, with no broken-image icon', async ({ page }) => {
  const tag = unique('Gone');
  await recipeWith(page, tag, 'dish');
  await page.route('**/api/v1/recipes/photos/*/list', (route) => route.abort());
  await page.goto('/recipes');
  await search(page, tag);
  const link = row(page, tag);
  await expect(link).toBeVisible();
  await expect(link.locator('img')).toHaveCount(0);
  const plain = await square(link).boundingBox();
  expect([plain!.width, plain!.height]).toEqual([52, 52]);
  await checkPage(page);
});

test('All recipes: a photo that failed while offline loads once the connection comes back', async ({ page }) => {
  const tag = unique('Back');
  await recipeWith(page, tag, 'dish');
  await page.route('**/api/v1/recipes/photos/*/list', (route) => route.abort());
  await page.goto('/recipes');
  await search(page, tag);
  const link = row(page, tag);
  await expect(link).toBeVisible();
  await expect(link.locator('img')).toHaveCount(0);
  await offlineThenBack(page);
  const img = link.locator('img');
  await expect(img).toHaveCount(1);
  await loaded(img);
  const box = (await img.boundingBox())!;
  expect([box.width, box.height]).toEqual([52, 52]);
});

test('All recipes: when a name wraps onto several lines the square stays at the top of the row', async ({ page }) => {
  // A short tag, so the short recipe's name stays on one line even in the computer's narrow list pane.
  const tag = `W${Date.now().toString(36).slice(-6)}${Math.floor(Math.random() * 36).toString(36)}`;
  const long = `${tag} spiced roasted cauliflower with tahini, pomegranate and a very long name that keeps going and going`;
  await recipeWith(page, long, 'dish');
  await recipeWith(page, `${tag} a`, undefined, { time_minutes: null, nutrition: {} });
  await page.goto('/recipes');
  await search(page, tag);

  const tall = row(page, 'spiced roasted');
  await expect(tall.locator('img')).toHaveCount(1);
  const linkBox = (await tall.boundingBox())!;
  const squareBox = (await square(tall).boundingBox())!;
  expect(linkBox.height).toBeGreaterThan(100);
  // 10 px of room above it, as in a one-line row; not centred in the tall row.
  expect(squareBox.y - linkBox.y).toBeLessThanOrEqual(10.5);
  // A short name keeps the square centred in its 72 px row.
  const shortBox = (await row(page, `${tag} a`).boundingBox())!;
  const shortSquare = (await square(row(page, `${tag} a`)).boundingBox())!;
  expect(shortBox.height).toBeGreaterThanOrEqual(72);
  expect(shortSquare.y - shortBox.y).toBeCloseTo(shortBox.y + shortBox.height - (shortSquare.y + shortSquare.height), 0);

  // The same at 200% text: nothing scrolls sideways, the square is still at the top.
  await page.evaluate(() => (document.documentElement.style.fontSize = '200%'));
  await expect(tall).toBeVisible();
  await expectNoSidewaysScroll(page);
  const big = (await tall.boundingBox())!;
  const bigSquare = (await square(tall).boundingBox())!;
  expect(bigSquare.y - big.y).toBeLessThanOrEqual(10.5);
  await checkPage(page);
});

test('the recipe page: the large copy in a 170 px box above the name (phone) or beside the figures (computer)', async ({ page }) => {
  const name = unique('Sambar');
  const { recipe, photo } = await recipeWith(page, name, 'dish');
  await page.goto(`/recipes/${recipe.id}`);
  await expect(page.getByRole('heading', { name, level: 1 })).toBeVisible();

  const img = reader(page).getByRole('img', { name: `Photo of ${name}` });
  await expect(img).toHaveAttribute('src', `/api/v1/recipes/photos/${photo!.id}/large`);
  await loaded(img);
  expect(await img.evaluate((el) => getComputedStyle(el).objectFit)).toBe('cover');
  const frame = reader(page).locator('.frame');
  expect(await frame.evaluate((el) => getComputedStyle(el).borderRadius)).toBe('20px');
  const box = (await frame.boundingBox())!;
  const imgBox = (await img.boundingBox())!;
  expect([imgBox.width, imgBox.height]).toEqual([box.width, box.height]);
  const heading = (await page.getByRole('heading', { name, level: 1 }).boundingBox())!;
  const figures = (await reader(page).getByRole('region', { name: 'Nutrition per serving' }).boundingBox())!;

  if (isPhone(page)) {
    expect(box.height).toBe(170);
    expect(box.y + box.height).toBeLessThanOrEqual(heading.y);
    expect(box.width).toBeGreaterThan(300);
  } else {
    // Beside the figures, in the same row, at least 150 px tall; the figures are to its right.
    expect(box.height).toBeGreaterThanOrEqual(150);
    expect(box.x + box.width).toBeLessThanOrEqual(figures.x);
    expect(box.y).toBeLessThan(figures.y + figures.height);
    expect(figures.y).toBeLessThan(box.y + box.height);
    expect(box.y).toBeGreaterThanOrEqual(heading.y + heading.height);
  }
  await expectNoSidewaysScroll(page);
  await checkPage(page);
});

test('the recipe page: a very tall and a very wide photo fill the box, cropped, never stretched', async ({ page }) => {
  for (const shape of ['tall', 'wide'] as const) {
    const name = unique(`Shape ${shape}`);
    const { recipe } = await recipeWith(page, name, shape);
    await page.goto(`/recipes/${recipe.id}`);
    const img = reader(page).getByRole('img', { name: `Photo of ${name}` });
    await loaded(img);
    const frame = (await reader(page).locator('.frame').boundingBox())!;
    const box = (await img.boundingBox())!;
    expect([box.width, box.height]).toEqual([frame.width, frame.height]);
    expect(await img.evaluate((el) => getComputedStyle(el).objectFit)).toBe('cover');
    const natural = await img.evaluate((el: HTMLImageElement) => [el.naturalWidth, el.naturalHeight]);
    expect(shape === 'tall' ? natural[1]! > natural[0]! * 2 : natural[0]! > natural[1]! * 2).toBe(true);
  }
});

test('the recipe page: no photo means no box, and the nutrition figures take the width', async ({ page }) => {
  const name = unique('Plain');
  const { recipe } = await recipeWith(page, name);
  await page.goto(`/recipes/${recipe.id}`);
  await expect(page.getByRole('heading', { name, level: 1 })).toBeVisible();
  await expect(reader(page).locator('img')).toHaveCount(0);
  await expect(reader(page).locator('.frame')).toHaveCount(0);
  await expect(reader(page).getByRole('region', { name: 'Nutrition per serving' })).toBeVisible();
  await checkPage(page);
});

test('the recipe page: a photo that can’t be fetched leaves no box and no broken-image icon', async ({ page }) => {
  const name = unique('Gone');
  const { recipe } = await recipeWith(page, name, 'dish');
  await page.route('**/api/v1/recipes/photos/*/large', (route) => route.abort());
  await page.goto(`/recipes/${recipe.id}`);
  await expect(page.getByRole('heading', { name, level: 1 })).toBeVisible();
  await expect(reader(page).getByRole('region', { name: 'Nutrition per serving' })).toBeVisible();
  await expect(reader(page).locator('img')).toHaveCount(0);
  await expect(reader(page).locator('.frame')).toHaveCount(0);
  await checkPage(page);
});

test('the recipe page: a photo that failed while offline loads once the connection comes back', async ({ page }) => {
  const name = unique('Back');
  const { recipe } = await recipeWith(page, name, 'dish');
  await page.route('**/api/v1/recipes/photos/*/large', (route) => route.abort());
  await page.goto(`/recipes/${recipe.id}`);
  await expect(page.getByRole('heading', { name, level: 1 })).toBeVisible();
  await expect(reader(page).locator('.frame')).toHaveCount(0);
  await offlineThenBack(page);
  await loaded(reader(page).getByRole('img', { name: `Photo of ${name}` }));
  await checkPage(page);
});

test('the recipe page: with the text at 200% the photo and figures still fit', async ({ page }) => {
  const name = unique('Large text');
  const { recipe } = await recipeWith(page, name, 'dish');
  await page.goto(`/recipes/${recipe.id}`);
  await loaded(reader(page).getByRole('img', { name: `Photo of ${name}` }));
  await page.evaluate(() => (document.documentElement.style.fontSize = '200%'));
  await expect(page.getByRole('heading', { name, level: 1 })).toBeVisible();
  await expectNoSidewaysScroll(page);
  await checkPage(page);
});

test('Edit → Save with a new photo, then with the photo removed: the recipe page and the list both show it', async ({ page }) => {
  const name = unique('Edited');
  const { recipe } = await recipeWith(page, name);
  const list = () => (isPhone(page) ? page.locator('main') : page.getByRole('region', { name: 'Recipe list' }));
  /** Back to All recipes the way a person would: the phone's "Recipes" link; on a computer the list is beside it. */
  async function theList() {
    if (isPhone(page)) {
      await reader(page).getByRole('link', { name: 'Recipes', exact: true }).click();
      await expect(page).toHaveURL('/recipes');
      await search(page, name);
    }
    return row(page, name);
  }
  async function openAndEdit() {
    await row(page, name).click();
    await expect(page).toHaveURL(`/recipes/${recipe.id}`);
    await reader(page).getByRole('link', { name: 'Edit', exact: true }).click();
    await expect(page).toHaveURL(`/recipes/${recipe.id}/edit`);
  }

  await page.goto('/recipes');
  await search(page, name);
  await expect(list().getByRole('link', { name: new RegExp(name) }).locator('img')).toHaveCount(0);

  // A new photo: the page shows the large copy, and the list's square the small one.
  await openAndEdit();
  await page.locator('input[type=file]').setInputFiles({ name: 'dish.png', mimeType: 'image/png', buffer: photoPng('dish') });
  await expect(page.getByRole('button', { name: 'Change photo' })).toBeVisible();
  await page.getByRole('button', { name: /^Save/ }).click();
  await expect(page).toHaveURL(`/recipes/${recipe.id}`);
  const img = reader(page).getByRole('img', { name: `Photo of ${name}` });
  await expect(img).toHaveAttribute('src', /^\/api\/v1\/recipes\/photos\/\d+\/large$/);
  await loaded(img);
  const id = /photos\/(\d+)\//.exec((await img.getAttribute('src'))!)![1];
  const square = (await theList()).locator('img');
  await expect(square).toHaveAttribute('src', `/api/v1/recipes/photos/${id}/list`);
  await loaded(square);

  // The photo removed: no box on the page, the plain square in the list.
  await openAndEdit();
  await page.getByRole('button', { name: 'Remove photo' }).click();
  await expect(page.getByRole('button', { name: 'Add a photo' })).toBeVisible();
  await page.getByRole('button', { name: /^Save/ }).click();
  await expect(page).toHaveURL(`/recipes/${recipe.id}`);
  await expect(page.getByRole('heading', { name, level: 1 })).toBeVisible();
  await expect(reader(page).locator('.frame')).toHaveCount(0);
  await expect(reader(page).locator('img')).toHaveCount(0);
  await expect((await theList()).locator('img')).toHaveCount(0);
  await checkPage(page);
});
