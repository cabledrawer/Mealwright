import { test, expect, type Page, type Route } from './clock.ts';
import { checkPage, expectNoSidewaysScroll, inTheme, setAccountTheme } from './a11y.ts';
import { uploadPhoto } from '../review/photos.ts';

// Import a recipe (0.5): the one box, "Importing from links is switched off", the review, Save
// and its one Undo, "You already have this recipe", and "From: site · by author" on the recipe
// page. Runs in the "phone 0.5 import" and "desktop 0.5 import" projects, signed in as the test
// admin. Nothing here goes online: the main server's link switch is off (as it starts), the
// pasted-text path never goes online, and the link screens are shown with the server's answers
// to POST /recipes/import made up in the browser (page.route). The Save is always the real one.

type Json = Record<string, any>; // eslint-disable-line @typescript-eslint/no-explicit-any

const unique = (name: string) => `${name} ${test.info().project.name.replace(/\D/g, '')}${Date.now() % 100000}`;

const box = (page: Page) => page.getByLabel('Paste a link or the recipe’s text');
const onPhone = () => test.info().project.name.startsWith('phone');
/** The three steps: "Step N of 3" under the title on a phone, the numbered steps beside it on a computer. */
async function expectStep(page: Page, step: 1 | 2, pasted = 'Link pasted') {
  if (onPhone()) {
    await expect(page.getByText(`Step ${step} of 3`, { exact: true })).toBeVisible();
    await expect(page.getByRole('list', { name: 'Import steps' })).toHaveCount(0);
    return;
  }
  const steps = page.getByRole('list', { name: 'Import steps' });
  await expect(steps.getByRole('listitem')).toHaveText([step === 1 ? '1 · Paste' : `1 · ${pasted} ✓`, '2 · Check', '3 · Save']);
  await expect(steps.locator('[aria-current="step"]')).toHaveText(step === 1 ? '1 · Paste' : '2 · Check');
  await expect(page.getByText(/^Step \d of 3$/)).toHaveCount(0);
}
const read = (page: Page) => page.getByRole('button', { name: 'Read the recipe' });

test.beforeEach(async ({ page }) => {
  await setAccountTheme(page, 'auto');
});

/** A review as the server answers it, with lines that need a choice (no ingredient ids are used). */
function review(over: Json = {}, names: { onion: string; hing: string; curry: string } = { onion: 'a', hing: 'b', curry: 'c' }): Json {
  const line = (more: Json): Json => ({
    kind: 'ingredient',
    written: '',
    words: '',
    amount: null,
    amount_text: null,
    unit: null,
    size: null,
    note: null,
    readable: true,
    label: 'needs_you',
    food: null,
    place: null,
    matched_by: null,
    counts: true,
    new_ingredient: null,
    learn_name: null,
    ...more,
  });
  const guess = (name: string, counted_as: string) => ({ name, counted_as, place: null });
  return {
    source: { kind: 'link', url: 'https://bananaleaf.example/sambar/', site: 'bananaleaf.example' },
    name: 'Sambar',
    description: 'Lentil & vegetable stew',
    author: 'Meena Raman',
    time_minutes: 50,
    serves: 4,
    makes: null,
    tags: ['Dinner'],
    nutrition: { kcal: 320, protein: null, carbs: null, fat: null, fibre: null },
    photo: { state: 'off', photo: null, message: 'Photo not downloaded' },
    lines: [
      line({ kind: 'heading', label: null, written: 'For the sambar:', words: 'For the sambar', readable: true }),
      line({
        written: '1 red onion, sliced',
        words: names.onion,
        amount: 1,
        amount_text: '1',
        note: 'sliced',
        label: 'to_confirm',
        food: null,
        new_ingredient: guess(names.onion, 'count'),
        learn_name: names.onion,
      }),
      line({
        written: '¼ tsp asafoetida',
        words: names.hing,
        amount: 0.25,
        amount_text: '¼',
        unit: 'tsp',
        new_ingredient: guess(names.hing, 'volume'),
        learn_name: names.hing,
      }),
      line({
        written: 'a sprig of curry leaves, and a very long description of how fresh they should be',
        words: names.curry,
        new_ingredient: guess(names.curry, 'weight'),
        learn_name: names.curry,
      }),
    ],
    steps: [
      { kind: 'step', text: 'Boil the dal until soft.' },
      { kind: 'step', text: 'Add the vegetables and simmer.' },
    ],
    counts: { matched: 0, to_confirm: 1, needs_you: 2, staple: 0 },
    lines_cut: false,
    steps_cut: false,
    steps_shortened: 0,
    left_out: [{ heading: 'Tips', lines: 4 }],
    ...over,
  };
}

const answer = (page: Page, status: number, body: Json, delay = 0) =>
  page.route('**/api/v1/recipes/import', async (route: Route) => {
    if (delay) await new Promise((resolve) => setTimeout(resolve, delay));
    await route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(body) });
  });

test('Recipes has an Import a recipe button that opens the box', async ({ page }) => {
  await page.goto('/recipes');
  await page.getByRole('link', { name: 'Import a recipe', exact: true }).click();
  await expect(page).toHaveURL(/\/recipes\/import$/);
  await expect(page.getByRole('heading', { level: 1 })).toHaveText('Import a recipe');
  await expect(read(page)).toBeDisabled();
  await expectStep(page, 1);
  await expect(page.getByText('How it works')).toBeVisible();
  // Photo downloads start off, so the box says so (and checkPage scans it in both themes).
  await expect(page.getByText('Recipe photos: not downloaded.')).toBeVisible();
  await expect(page.getByRole('link', { name: 'Change in Settings → Privacy' })).toHaveAttribute('href', '/settings/privacy#outside-connections');
  await checkPage(page);
});

/** The server's answer to GET /privacy/switches, made up in the browser. */
const photoSwitch = (page: Page, on: boolean) =>
  page.route('**/api/v1/privacy/switches', (route: Route) =>
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        switches: [
          { connection: 'recipe_import', on: false },
          { connection: 'recipe_photos', on },
        ],
        can_change: true,
      }),
    }),
  );

test('the box says nothing about photos while "Download recipe photos" is on', async ({ page }) => {
  await photoSwitch(page, true);
  const answered = page.waitForResponse('**/api/v1/privacy/switches');
  await page.goto('/recipes/import');
  await answered;
  await expect(page.getByText('How it works')).toBeVisible();
  await expect(page.getByText('Recipe photos: not downloaded.')).toHaveCount(0);
  await checkPage(page);
});

test('the box says nothing about photos when the switch can’t be read', async ({ page }) => {
  await page.route('**/api/v1/privacy/switches', (route: Route) => route.fulfill({ status: 500, contentType: 'application/json', body: '{"detail":"Something went wrong."}' }));
  const answered = page.waitForResponse('**/api/v1/privacy/switches');
  await page.goto('/recipes/import');
  await answered;
  await expect(page.getByText('How it works')).toBeVisible();
  await expect(page.getByText('Recipe photos: not downloaded.')).toHaveCount(0);
});

test('the box says whether it thinks it is a link or pasted text', async ({ page }) => {
  await page.goto('/recipes/import');
  await box(page).fill('https://bananaleaf.example/sambar/');
  await expect(page.getByText('A link · your server visits this page once')).toBeVisible();
  await box(page).fill('Sambar\n1 cup toor dal');
  await expect(page.getByText('Pasted text · nothing goes online')).toBeVisible();
  await expect(read(page)).toBeEnabled();
  await checkPage(page);
});

test('importing from links is switched off (as it starts), and pasted text still works', async ({ page }) => {
  await page.goto('/recipes/import');
  await box(page).fill('https://bananaleaf.example/sambar/');
  await read(page).click();
  const alert = page.getByRole('alert');
  await expect(alert.getByText('Importing from links is switched off')).toBeVisible();
  await expect(alert.getByText(/Nothing was fetched/)).toBeVisible();
  await expect(alert.getByRole('link', { name: 'Open Settings', exact: true })).toHaveAttribute('href', '/settings/privacy#outside-connections');
  await checkPage(page);
  // Paste text instead: the box is emptied and focused.
  await alert.getByRole('button', { name: 'Paste text instead' }).click();
  await expect(box(page)).toHaveValue('');
  await expect(box(page)).toBeFocused();
});

test('an unusual refusal shows the server’s sentence, and the box keeps what was typed', async ({ page }) => {
  await answer(page, 422, { detail: 'This link isn’t a web page.', code: 'not_a_page' });
  await page.goto('/recipes/import');
  await box(page).fill('https://bananaleaf.example/menu.pdf');
  await read(page).click();
  await expect(page.getByRole('alert')).toContainText('This link isn’t a web page.');
  await expect(box(page)).toHaveValue('https://bananaleaf.example/menu.pdf');
  await checkPage(page);
});

test('a slow page says Reading… and nothing else can be sent meanwhile', async ({ page }) => {
  await answer(page, 200, review(), 1500);
  await page.goto('/recipes/import');
  await box(page).fill('https://bananaleaf.example/sambar/');
  await read(page).click();
  await expect(page.getByRole('button', { name: 'Reading…' })).toBeDisabled();
  await expect(page.getByRole('heading', { level: 1 })).toHaveText('Check before saving');
});

test('offline, the box says it needs the server and nothing is sent', async ({ page, context }) => {
  await page.goto('/recipes/import');
  await box(page).fill('https://bananaleaf.example/sambar/');
  // Let the page go quiet first: an answer that arrives after the connection is cut would count
  // as connected (docs/dev/browser-tests.md).
  await page.waitForLoadState('networkidle');
  await context.setOffline(true);
  await page.evaluate(() => window.dispatchEvent(new Event('offline')));
  await expect(page.getByText(/Importing needs your Mealwright server/)).toBeVisible({ timeout: 10000 });
  await expect(read(page)).toBeDisabled();
  await context.setOffline(false);
});

test('the review: counts, each line as written → read → in your kitchen, Photo not downloaded, only Save', async ({ page }) => {
  await answer(page, 200, review());
  await page.goto('/recipes/import');
  await box(page).fill('https://bananaleaf.example/sambar/');
  await read(page).click();
  await expect(page.getByRole('heading', { level: 1 })).toHaveText('Check before saving');
  await expectStep(page, 2);
  await expect(page.getByText('0 matched')).toBeVisible();
  await expect(page.getByText('1 to confirm')).toBeVisible();
  await expect(page.getByText('2 need you')).toBeVisible();
  await expect(page.getByText('Photo not downloaded.', { exact: true })).toBeVisible();
  await expect(page.getByRole('link', { name: 'Settings → Privacy' })).toBeVisible();
  await expect(page.getByText('Nothing is saved until you choose.').first()).toBeVisible();
  await expect(page.getByText('4 lines after “Tips” were left out. You can add them by hand.')).toBeVisible();
  await expect(page.getByRole('button', { name: 'Save recipe' })).toBeVisible();
  await expect(page.getByText(/plan it/i)).toHaveCount(0); // Save & plan it waits for 0.6
  await expect(page.getByRole('status').filter({ hasText: '3 lines will be saved without an ingredient' })).toBeVisible();
  await checkPage(page);
});

test('the review: long names and text at 200% never scroll sideways', async ({ page }) => {
  const long = 'வெண்டைக்காய் '.repeat(8) + 'x'.repeat(60);
  await answer(page, 200, review({ name: long }, { onion: long, hing: 'Asafoetida', curry: long }));
  await page.goto('/recipes/import');
  await box(page).fill('https://bananaleaf.example/sambar/');
  await read(page).click();
  await expect(page.getByRole('heading', { level: 1 })).toHaveText('Check before saving');
  await expectNoSidewaysScroll(page);
  await page.evaluate(() => (document.documentElement.style.fontSize = '200%'));
  await expectNoSidewaysScroll(page);
  await page.evaluate(() => (document.documentElement.style.fontSize = ''));
});

test('a review in the dark theme passes the accessibility scan', async ({ page }) => {
  await answer(page, 200, review());
  await page.goto('/recipes/import');
  await box(page).fill('https://bananaleaf.example/sambar/');
  await read(page).click();
  await expect(page.getByRole('heading', { level: 1 })).toHaveText('Check before saving');
  await page.getByRole('button', { name: 'New ingredient' }).first().click();
  await page.getByRole('button', { name: 'Treat as staple' }).first().click();
  await inTheme(page, 'dark');
  await checkPage(page, { themes: ['dark'] });
});

test('You already have this recipe: Open it, or Import again as a copy', async ({ page }) => {
  let asked = 0;
  await page.route('**/api/v1/recipes/import', async (route) => {
    asked += 1;
    const again = (route.request().postDataJSON() as Json).again === true;
    await route.fulfill({
      status: again ? 200 : 409,
      contentType: 'application/json',
      body: JSON.stringify(
        again
          ? review()
          : {
              detail: 'You already have this recipe',
              code: 'already_imported',
              recipe: { id: 9999, name: 'Sambar' },
              site: 'bananaleaf.example',
              imported_at: '2026-10-03T10:00:00Z',
              photo: null,
            },
      ),
    });
  });
  await page.goto('/recipes/import');
  await box(page).fill('https://bananaleaf.example/sambar/');
  await read(page).click();
  const sheet = page.getByRole('dialog', { name: 'You already have this recipe' });
  await expect(sheet).toBeVisible();
  await expect(sheet.getByText('Sambar')).toBeVisible();
  await expect(sheet.getByRole('link', { name: 'Open it' })).toHaveAttribute('href', '/recipes/9999');
  await checkPage(page);
  // Cancel just closes it.
  await sheet.getByRole('button', { name: 'Cancel' }).click();
  await expect(sheet).toBeHidden();
  await read(page).click();
  await sheet.getByRole('button', { name: 'Import again as a copy' }).click();
  await expect(page.getByRole('heading', { level: 1 })).toHaveText('Check before saving');
  expect(asked).toBe(3);
});

test('pasted text, end to end: the review, Save, the recipe, and one Undo that takes it all back', async ({ page }) => {
  const dal = unique('Red lentils');
  const hing = unique('Hing');
  const masala = unique('Garam masala');
  const title = unique('Dal tadka');
  await page.goto('/recipes/import');
  await box(page).fill(
    `${title}\nIngredients\n1 cup ${dal}\n¼ tsp ${hing}\n1 tsp ${masala}\nMethod\n1. Boil the lentils.\n2. Fry the tadka.\nTips\nServe hot.\n`,
  );
  await read(page).click();
  await expect(page.getByRole('heading', { level: 1 })).toHaveText('Check before saving');
  await expectStep(page, 2, 'Text pasted');
  await expect(page.getByLabel('Name', { exact: true }).first()).toHaveValue(title);
  await expect(page.getByText('1 line after “Tips” was left out')).toBeVisible();
  // All three unknown lines need a choice (nothing here is in this kitchen yet).
  await expect(page.getByText('Not in your ingredients')).toHaveCount(3);
  await page.getByRole('button', { name: 'New ingredient' }).first().click();
  await page.getByRole('button', { name: 'Treat as staple' }).first().click();
  await page.getByRole('button', { name: 'New ingredient' }).first().click();
  await checkPage(page);
  await page.getByRole('button', { name: 'Save recipe' }).click();
  await expect(page).toHaveURL(/\/recipes\/\d+$/);
  const id = Number(page.url().split('/').pop());
  await expect(page.getByRole('heading', { level: 1 })).toHaveText(title);
  await expect(page.getByText('Boil the lentils.')).toBeVisible();
  // The toast says what was imported, with the one Undo.
  await expect(page.getByRole('button', { name: 'Undo', exact: true })).toBeVisible();
  const foods = (await (await page.request.get(`/api/v1/foods?q=${encodeURIComponent(hing)}`)).json()) as Json;
  expect(foods.foods.map((f: Json) => f.name.toLowerCase())).toContain(hing.toLowerCase());
  const changes = (await (await page.request.get('/api/v1/changes?area=ingredients&limit=10')).json()) as Json;
  expect(changes.changes.filter((c: Json) => c.kind === 'recipe_imported' && c.summary.includes(title))).toHaveLength(1);
  await page.getByRole('button', { name: 'Undo', exact: true }).click();
  await expect(page.getByText(/^Undone/)).toBeVisible();
  expect((await page.request.get(`/api/v1/recipes/${id}`)).status()).toBe(404);
  const after = (await (await page.request.get(`/api/v1/foods?q=${encodeURIComponent(hing)}`)).json()) as Json;
  expect(after.foods).toHaveLength(0);
});

test('a link import keeps where it came from: From: site · by author on the recipe page', async ({ page }) => {
  const names = { onion: unique('Red onion'), hing: unique('Hing'), curry: unique('Curry leaves') };
  const title = unique('Sambar');
  await answer(page, 200, review({ name: title, makes: { amount: 24, unit: 'cookies' } }, names));
  await page.goto('/recipes/import');
  await box(page).fill('https://bananaleaf.example/sambar/');
  await read(page).click();
  await expect(page.getByRole('heading', { level: 1 })).toHaveText('Check before saving');
  await page.getByRole('button', { name: 'New ingredient' }).first().click();
  await page.getByRole('button', { name: 'Treat as staple' }).first().click();
  await page.getByRole('button', { name: 'Treat as staple' }).first().click();
  await page.getByRole('button', { name: 'Save recipe' }).click();
  await expect(page).toHaveURL(/\/recipes\/\d+$/);
  // Makes is saved as it was shown: 24 cookies, not 24000.
  const saved = (await (await page.request.get(`/api/v1/recipes/${page.url().split('/').pop()}`)).json()) as Json;
  expect([saved.makes.amount, saved.makes.unit]).toEqual([24, 'cookies']);
  await expect(page.getByText('From: bananaleaf.example · by Meena Raman')).toBeVisible();
  await expect(page.getByRole('link', { name: 'bananaleaf.example' })).toHaveAttribute(
    'href',
    'https://bananaleaf.example/sambar/',
  );
  // Imported again from the same address, the real server says the household has it.
  await page.unroute('**/api/v1/recipes/import');
  await page.goto('/recipes/import');
  await box(page).fill('https://bananaleaf.example/sambar/');
  await read(page).click();
  // (the main server has the link switch off, so the switch is what answers first)
  await expect(page.getByRole('alert')).toContainText('Importing from links is switched off');
  await checkPage(page);
});

test('the editor says a web address is a link you can open yourself', async ({ page }) => {
  await page.goto('/recipes/new');
  await expect(page.getByText('A web address shows as a link you can open yourself. Mealwright never visits it.')).toBeVisible();
});

/** A review whose photo was downloaded: a real stored photo, so its two copies can be fetched. */
async function withDownloadedPhoto(page: Page) {
  const id = await uploadPhoto(page.request, 'dish');
  const response = await page.request.get(`/api/v1/recipes/photos/${id}/list`);
  expect(response.ok()).toBe(true);
  const photo = {
    id,
    url: `/api/v1/recipes/photos/${id}/large`,
    width: 1600,
    height: 1200,
    list_url: `/api/v1/recipes/photos/${id}/list`,
    list_width: 208,
    list_height: 156,
  };
  await answer(page, 200, review({ photo: { state: 'downloaded', photo, message: null } }));
  await page.goto('/recipes/import');
  await box(page).fill('https://bananaleaf.example/sambar/');
  await read(page).click();
  await expect(page.getByRole('heading', { level: 1 })).toHaveText('Check before saving');
  return photo;
}

const loadedPicture = (page: Page) =>
  expect.poll(() => page.getByRole('img', { name: 'Downloaded from the page' }).evaluate((el: HTMLImageElement) => el.complete && el.naturalWidth > 0)).toBe(true);

test('the review: the downloaded photo shows its large copy', async ({ page }) => {
  const photo = await withDownloadedPhoto(page);
  const img = page.getByRole('img', { name: 'Downloaded from the page' });
  await expect(img).toHaveAttribute('src', photo.url);
  await loadedPicture(page);
});

test('the review: if only the large copy can’t be fetched, the list copy shows (F22)', async ({ page }) => {
  await page.route('**/api/v1/recipes/photos/*/large', (route) => route.abort());
  const photo = await withDownloadedPhoto(page);
  const img = page.getByRole('img', { name: 'Downloaded from the page' });
  await expect(img).toHaveAttribute('src', photo.list_url);
  await loadedPicture(page);
  await expect(page.getByRole('img', { name: 'No photo' })).toHaveCount(0);
  await checkPage(page);
});

test('the review: if neither copy can be fetched, the "No photo" box shows, never a broken picture (F22)', async ({ page }) => {
  await page.route('**/api/v1/recipes/photos/*/*', (route) => route.abort());
  await withDownloadedPhoto(page);
  await expect(page.getByRole('img', { name: 'No photo' })).toBeVisible();
  await expect(page.getByRole('img', { name: 'Downloaded from the page' })).toHaveCount(0);
  await checkPage(page);
});

test('Save with lines that have no ingredient goes through them one at a time (F4)', async ({ page }) => {
  const names = { onion: unique('Red onion'), hing: unique('Hing'), curry: unique('Curry leaves') };
  await answer(page, 200, review({ name: unique('Sambar') }, names));
  await page.goto('/recipes/import');
  await box(page).fill('https://bananaleaf.example/sambar/');
  await read(page).click();
  await expect(page.getByRole('heading', { level: 1 })).toHaveText('Check before saving');
  await page.getByRole('button', { name: 'Save recipe' }).click();
  const sheet = page.getByRole('dialog', { name: '3 lines aren’t linked yet' });
  await expect(sheet).toBeVisible();
  await expect(sheet.getByText('Line 1 of 3')).toBeVisible();
  await checkPage(page);
  await sheet.getByRole('button', { name: 'Skip this line' }).click();
  await expect(sheet.getByText('Line 2 of 3')).toBeVisible();
  await sheet.getByRole('button', { name: 'Treat as staple' }).click();
  await expect(sheet.getByText('Line 3 of 3')).toBeVisible();
  await inTheme(page, 'dark');
  await checkPage(page, { themes: ['dark'] });
  // Back to Check: nothing was saved, and the line that was settled shows it.
  await sheet.getByRole('button', { name: 'Back to Check' }).click();
  await expect(sheet).toBeHidden();
  await expect(page.getByRole('heading', { level: 1 })).toHaveText('Check before saving');
  await expect(page.getByText('New staple:')).toBeVisible();
  // Save again: only the two left are asked about, and Save anyway saves the recipe.
  await page.getByRole('button', { name: 'Save recipe' }).click();
  await expect(sheet).toBeVisible();
  await expect(sheet.getByText('Line 1 of 2')).toBeVisible();
  await sheet.getByRole('button', { name: 'Save anyway' }).click();
  await expect(page).toHaveURL(/\/recipes\/\d+$/);
  await page.getByRole('button', { name: 'Undo', exact: true }).click();
  await expect(page.getByText(/^Undone/)).toBeVisible();
});

test('the Check lines: status dots, a chip that fixes the amount, and a New ingredient that closes with Done (F30.6, F10, F21)', async ({ page }) => {
  const names = { onion: unique('Red onion'), hing: unique('Hing'), curry: unique('Curry leaves') };
  await answer(page, 200, review({ name: unique('Sambar') }, names));
  await page.goto('/recipes/import');
  await box(page).fill('https://bananaleaf.example/sambar/');
  await read(page).click();
  await expect(page.getByRole('heading', { level: 1 })).toHaveText('Check before saving');
  await expect(page.getByRole('img', { name: 'To confirm' })).toHaveCount(1);
  await expect(page.getByRole('img', { name: 'Needs you' })).toHaveCount(2);
  // The line to confirm has Treat as staple too.
  await expect(page.getByRole('button', { name: 'Treat as staple' })).toHaveCount(3);
  // The curry leaves line has no amount.
  await page.getByRole('button', { name: /^No amount/ }).click();
  await page.getByLabel('Amount', { exact: true }).fill('2');
  await page.getByRole('button', { name: 'Done', exact: true }).click();
  await expect(page.getByRole('button', { name: /^Amount 2/ })).toBeVisible();
  // New ingredient opens its form; Done settles it.
  await page.getByRole('button', { name: `New ingredient “${names.hing}”` }).click();
  await expect(page.getByLabel('Usually kept in')).toBeVisible();
  await checkPage(page);
  await page.getByRole('button', { name: 'Done', exact: true }).click();
  await expect(page.getByLabel('Usually kept in')).toHaveCount(0);
  await expect(page.getByRole('button', { name: 'Edit', exact: true })).toBeVisible();
  await inTheme(page, 'dark');
  await checkPage(page, { themes: ['dark'] });
});

test('a long method step is split only after a preview, and can be put back (F13)', async ({ page }) => {
  const names = { onion: unique('Red onion'), hing: unique('Hing'), curry: unique('Curry leaves') };
  const long =
    'Heat the oil. Add the onion and fry until golden. Stir in the spices. Pour in the stock. Simmer for twenty minutes.';
  await answer(page, 200, review({ name: unique('Sambar'), steps: [{ kind: 'step', text: long }] }, names));
  await page.goto('/recipes/import');
  await box(page).fill('https://bananaleaf.example/sambar/');
  await read(page).click();
  await expect(page.getByText('A long step (5 sentences)')).toBeVisible();
  await page.getByRole('button', { name: 'Split into shorter steps' }).click();
  await expect(page.getByText('Preview: this step as 3 steps')).toBeVisible();
  await page.getByRole('button', { name: 'Keep as one' }).click();
  await expect(page.getByText('Preview: this step as 3 steps')).toHaveCount(0);
  await page.getByRole('button', { name: 'Split into shorter steps' }).click();
  await page.getByRole('button', { name: 'Keep the split' }).click();
  await expect(page.getByText('Method · 3 steps found')).toBeVisible();
  await page.getByRole('button', { name: 'Put the steps back as they were' }).click();
  await expect(page.getByText('Method · 1 step found')).toBeVisible();
});

test('a recipe photo opens full size, and Esc or a tap closes it (F29)', async ({ page }) => {
  const title = unique('Sambar');
  const photoId = await uploadPhoto(page.request, 'dish');
  const created = await page.request.post('/api/v1/recipes', {
    data: { name: title, steps: [{ text: 'Stir.' }], photo_id: photoId },
    headers: { 'idempotency-key': crypto.randomUUID() },
  });
  expect(created.ok()).toBe(true);
  const { id } = (await created.json()) as Json;
  await page.goto(`/recipes/${id}`);
  const photo = page.getByRole('button', { name: 'Show the photo full size' }).first();
  await photo.click();
  const viewer = page.getByRole('dialog', { name: `Photo of ${title}` });
  await expect(viewer).toBeVisible();
  await inTheme(page, 'dark');
  await checkPage(page, { themes: ['dark'] });
  await page.keyboard.press('Escape');
  await expect(viewer).toBeHidden();
  await expect(photo).toBeFocused();
  await photo.click();
  await viewer.getByRole('img').click();
  await expect(viewer).toBeHidden();
  await page.request.delete(`/api/v1/recipes/${id}`, { headers: { 'idempotency-key': crypto.randomUUID() } });
});

test('the photo on Check opens full size too (F29)', async ({ page }) => {
  await withDownloadedPhoto(page);
  await page.goto('/recipes/import');
  await box(page).fill('https://bananaleaf.example/sambar/');
  await read(page).click();
  await expect(page.getByRole('heading', { level: 1 })).toHaveText('Check before saving');
  await page.getByRole('button', { name: 'Show the photo full size' }).click();
  const viewer = page.getByRole('dialog', { name: 'Downloaded from the page' });
  await expect(viewer).toBeVisible();
  await page.keyboard.press('Escape');
  await expect(viewer).toBeHidden();
  await expectNoSidewaysScroll(page);
});
