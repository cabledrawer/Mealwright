import { test, expect, type Page, type Route } from './clock.ts';
import { workerReady } from './worker.ts';
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
    // On the Check screen the phone's own header says it, with "nothing saved yet" (F141).
    await expect(page.getByText(step === 2 ? 'Step 2 of 3 · nothing saved yet' : `Step ${step} of 3`, { exact: true })).toBeVisible();
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

test('Recipes has an Import item (the sidebar, or a button on a phone) that opens the box', async ({ page }) => {
  await page.goto('/recipes');
  await page.getByRole('link', { name: 'Import', exact: true }).click();
  await expect(page).toHaveURL(/\/recipes\/import$/);
  await expect(page.getByRole('heading', { level: 1 })).toHaveText('Import a recipe');
  await expect(read(page)).toBeDisabled();
  await expectStep(page, 1);
  await expect(page.getByText('How it works')).toBeVisible();
  // Photo downloads start off, so the box says so (and checkPage scans it in both themes).
  await expect(page.getByText('Recipe photos: not downloaded.')).toBeVisible();
  await expect(page.getByRole('link', { name: 'Change in Settings → Outside connections' })).toHaveAttribute('href', '/settings/privacy#outside-connections');
  await checkPage(page);
});

/** The server's answer to GET /privacy/switches, made up in the browser. */
const photoSwitch = (page: Page, on: boolean, links = false) =>
  page.route('**/api/v1/privacy/switches', (route: Route) =>
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        switches: [
          { connection: 'recipe_import', on: links },
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
  await photoSwitch(page, false, true);
  const answered = page.waitForResponse('**/api/v1/privacy/switches');
  await page.goto('/recipes/import');
  await answered;
  await box(page).fill('https://bananaleaf.example/sambar/');
  await expect(page.getByText('A link · your server visits this page once')).toBeVisible();
  await box(page).fill('Sambar\n1 cup toor dal');
  await expect(page.getByText('Pasted text · nothing goes online')).toBeVisible();
  await expect(read(page)).toBeEnabled();
  await checkPage(page);
});

test('F239: with Recipe import from links off, a link is not "your server visits this page once"', async ({ page }) => {
  await photoSwitch(page, false, false);
  const answered = page.waitForResponse('**/api/v1/privacy/switches');
  await page.goto('/recipes/import');
  await answered;
  await box(page).fill('https://bananaleaf.example/sambar/');
  await expect(page.locator('.chip', { hasText: 'Importing from links is switched off' })).toBeVisible();
  await expect(page.getByText('your server visits this page once')).toHaveCount(0);
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
  await workerReady(page);
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
  // The phone's header counts say "ok" (mockup Dark-ImportCheckFocus07-Phone).
  await expect(page.getByText(onPhone() ? '0 ok' : '0 matched')).toBeVisible();
  await expect(page.getByText('1 to confirm')).toBeVisible();
  await expect(page.getByText('2 need you')).toBeVisible();
  await expect(page.getByText('Photo not downloaded.', { exact: true })).toBeVisible();
  await expect(page.getByRole('link', { name: 'Settings → Outside connections' })).toBeVisible();
  // The phone's Check says it in its header ("nothing saved yet"), the computer's has it by Save.
  if (!onPhone()) await expect(page.getByText('Nothing is saved until you choose.').first()).toBeVisible();
  await expect(page.getByText('4 lines after “Tips” were left out. You can add them by hand.')).toBeVisible();
  await expect(page.getByRole('button', { name: 'Save recipe' })).toBeVisible();
  await expect(page.getByText(/plan it/i)).toHaveCount(0); // Save & plan it waits for 0.6
  await expect(page.getByText(/without an ingredient/)).toHaveCount(0); // F152: no note
  await expect(page.getByRole('button', { name: 'Save recipe' })).toBeEnabled();
  // The Save bar floats over the foot of the screen: look at the end of the page, where it sits below
  // the content, so the scan is not about which chip happens to be under it at the top.
  await page.locator('ol li').last().scrollIntoViewIfNeeded();
  await checkPage(page);
});

test('the review: on a phone the menu is hidden, and Close and Save stay at the foot of the screen', async ({ page }) => {
  test.skip(!onPhone(), 'the phone’s own Check page (Focus, F141)');
  await answer(page, 200, review());
  await page.goto('/recipes/import');
  await box(page).fill('https://bananaleaf.example/sambar/');
  await read(page).click();
  await expect(page.getByRole('heading', { level: 1 })).toHaveText('Check before saving');
  // No bottom tabs: Close and Save are at the foot, in view, whatever the list is scrolled to.
  await expect(page.getByRole('navigation', { name: 'Main' })).toBeHidden();
  const save = page.getByRole('button', { name: 'Save recipe' });
  const close = page.getByRole('button', { name: /^Back to drafts/ });
  await expect(save).toBeInViewport({ ratio: 1 });
  await expect(close).toBeInViewport({ ratio: 1 });
  await page.locator('ol li').last().scrollIntoViewIfNeeded();
  await expect(save).toBeInViewport({ ratio: 1 });
  await expect(close).toBeInViewport({ ratio: 1 });
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

test('the Check screen that cannot be fetched says so, keeps its header, and Try again opens it', async ({ page }) => {
  const title = unique('Dal tadka');
  await page.goto('/recipes/import');
  await box(page).fill(`${title}\nIngredients\n1 cup lentils\nMethod\n1. Boil the lentils.\n`);
  let blocking = true;
  await page.route('**/_app/immutable/**', (route: Route) => (blocking ? route.abort() : route.continue()));
  await read(page).click();
  await expect(page.getByRole('alert').getByText('Couldn’t open the Check screen. Try again.')).toBeVisible();
  await expect(page.getByRole('heading', { level: 1 })).toHaveText('Check before saving');
  blocking = false;
  // The browser keeps a script that failed to load, so Try again reloads the page.
  await page.getByRole('button', { name: 'Try again' }).click();
  await expect(box(page)).toHaveValue('');
  await box(page).fill(`${title}\nIngredients\n1 cup lentils\nMethod\n1. Boil the lentils.\n`);
  await read(page).click();
  await expect(page.getByLabel('Name', { exact: true }).first()).toHaveValue(title);
  await expect(page.getByRole('alert').getByText('Couldn’t open the Check screen. Try again.')).toHaveCount(0);
});

test('F144: an import is undone from Settings → Recent changes once its toast has gone, on a phone too', async ({ page }) => {
  const title = unique('Dal tadka');
  const spice = unique('Hing');
  await page.goto('/recipes/import');
  await box(page).fill(`${title}\nIngredients\n1 cup ${spice}\nMethod\n1. Boil it.\n`);
  await read(page).click();
  await expect(page.getByRole('heading', { level: 1 })).toHaveText('Check before saving');
  await page.getByRole('button', { name: 'New ingredient' }).first().click();
  await page.getByRole('button', { name: 'Save recipe' }).click();
  await expect(page).toHaveURL(/\/recipes\/\d+$/);
  const id = Number(page.url().split('/').pop());
  const undo = page.getByRole('button', { name: 'Undo', exact: true });
  await expect(undo).toBeVisible();
  await page.mouse.move(0, 0); // a toast under the pointer waits; move it away
  await expect(undo).toBeHidden({ timeout: 15_000 }); // let the toast go
  // The import is in Settings → Recent changes (F172: the only place), on a phone and a computer.
  await page.goto('/settings/recent-changes');
  const recent = page.getByRole('region', { name: 'Recent changes' });
  await expect(recent.getByText(`Imported ${title}`, { exact: false })).toBeVisible();
  await recent.getByRole('button', { name: new RegExp(`^Undo: Imported ${title}`) }).click();
  await expect(page.getByText(/^Undone/)).toBeVisible();
  expect((await page.request.get(`/api/v1/recipes/${id}`)).status()).toBe(404);
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
  // Each line has its own buttons now: look at the end of the page, clear of the floating Save bar.
  await page.locator('ol li').last().scrollIntoViewIfNeeded();
  await checkPage(page);
});

test('the review: if neither copy can be fetched, the "No photo" box shows, never a broken picture (F22)', async ({ page }) => {
  await page.route('**/api/v1/recipes/photos/*/*', (route) => route.abort());
  await withDownloadedPhoto(page);
  await expect(page.getByRole('img', { name: 'No photo' })).toBeVisible();
  await expect(page.getByRole('img', { name: 'Downloaded from the page' })).toHaveCount(0);
  // Each line has its own buttons now: look at the end of the page, clear of the floating Save bar.
  await page.locator('ol li').last().scrollIntoViewIfNeeded();
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
  const again = page.getByRole('dialog', { name: '2 lines aren’t linked yet' });
  await expect(again).toBeVisible();
  await expect(again.getByText('Line 1 of 2')).toBeVisible();
  await again.getByRole('button', { name: 'Save anyway' }).click();
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
  const photo = page.getByRole('button', { name: `Show the photo of ${title} full size` }).first();
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
  await page.getByRole('button', { name: 'Show the photo of Sambar full size' }).click();
  const viewer = page.getByRole('dialog', { name: 'Downloaded from the page' });
  await expect(viewer).toBeVisible();
  await page.keyboard.press('Escape');
  await expect(viewer).toBeHidden();
  await expectNoSidewaysScroll(page);
});

test('Check is three columns on a wide computer and one column on a phone, and larger text stacks them', async ({ page }) => {
  const names = { onion: unique('Red onion'), hing: unique('Hing'), curry: unique('Curry leaves') };
  await answer(page, 200, review({ name: unique('Sambar') }, names));
  await page.setViewportSize(onPhone() ? { width: 390, height: 844 } : { width: 1600, height: 1000 });
  await page.goto('/recipes/import');
  await box(page).fill('https://bananaleaf.example/sambar/');
  await read(page).click();
  await expect(page.getByRole('heading', { level: 1 })).toHaveText('Check before saving');
  const boxes = async () => ({
    details: (await page.getByRole('region', { name: 'Recipe details' }).boundingBox())!,
    lines: (await page.getByRole('region', { name: /^Ingredients/ }).boundingBox())!,
    method: (await page.getByRole('region', { name: /^Method/ }).boundingBox())!,
  });
  const now = await boxes();
  if (onPhone()) {
    // One column: each below the one before. The phone's Check (Focus, F141) puts the ingredients
    // first, then the recipe's details, then the method.
    expect(now.details.y).toBeGreaterThan(now.lines.y + now.lines.height - 1);
    expect(now.method.y).toBeGreaterThan(now.details.y + now.details.height - 1);
  } else {
    // Details, ingredients, method side by side, from the same top.
    expect(now.lines.x).toBeGreaterThan(now.details.x + now.details.width - 1);
    expect(now.method.x).toBeGreaterThan(now.lines.x + now.lines.width - 1);
    expect(Math.abs(now.lines.y - now.details.y)).toBeLessThan(4);
    expect(Math.abs(now.method.y - now.details.y)).toBeLessThan(4);
    await expectNoSidewaysScroll(page);
    await checkPage(page);
    await inTheme(page, 'dark');
    await checkPage(page, { themes: ['dark'] });
    // Text at 200%: no room for three columns, so they stack.
    await page.evaluate(() => (document.documentElement.style.fontSize = '200%'));
    const big = await boxes();
    expect(big.lines.y).toBeGreaterThan(big.details.y + big.details.height - 1);
    await expectNoSidewaysScroll(page);
  }
});

// --- Import Check fixes from real use (0.7, PR A4) ---------------------------------------------

/** Open the Check screen on a review the browser makes up. */
async function checking(page: Page, over: Json = {}, names = { onion: unique('Red onion'), hing: unique('Hing'), curry: unique('Curry leaves') }) {
  await answer(page, 200, review({ name: unique('Sambar'), ...over }, names));
  await page.goto('/recipes/import');
  await box(page).fill('https://bananaleaf.example/sambar/');
  await read(page).click();
  await expect(page.getByRole('heading', { level: 1 })).toHaveText('Check before saving');
}

test('the method numbers its steps through the headings, which take no number (F112)', async ({ page }) => {
  await checking(page, {
    steps: [
      { kind: 'step', text: 'Soak the rice.' },
      { kind: 'heading', text: 'For the batter' },
      { kind: 'step', text: 'Grind it.' },
      { kind: 'step', text: 'Ferment it.' },
      { kind: 'heading', text: 'To serve' },
      { kind: 'step', text: 'Fry it.' },
    ],
  });
  await expect(page.getByText('Method · 4 steps found')).toBeVisible();
  await expect(page.getByRole('heading', { name: 'For the batter' })).toBeVisible();
  // Each run of steps starts at the right number, and no heading is a list item.
  const starts = await page.locator('.method ol').evaluateAll((lists) => lists.map((ol) => [ol.getAttribute('start'), ol.children.length]));
  expect(starts).toEqual([['1', 1], ['2', 2], ['4', 1]]);
  expect(await page.locator('.method li.heading').count()).toBe(0);
});

test('the filled buttons keep their words in the middle (F104)', async ({ page }) => {
  await checking(page);
  const button = page.getByRole('button', { name: /^New ingredient “/ }).first();
  await expect(button).toBeVisible();
  const off = await button.evaluate((el) => {
    const range = document.createRange();
    range.selectNodeContents(el);
    const text = range.getBoundingClientRect();
    const box = el.getBoundingClientRect();
    return {
      sideways: Math.abs(text.left + text.width / 2 - (box.left + box.width / 2)),
      upDown: Math.abs(text.top + text.height / 2 - (box.top + box.height / 2)),
      layout: getComputedStyle(el).flexDirection,
    };
  });
  expect(off.upDown).toBeLessThan(3);
  expect(off.sideways).toBeLessThan(3);
  expect(off.layout).toBe('row');
});

test('a site that refuses says how to paste the recipe, and the box is empty and ready (F115)', async ({ page }) => {
  await answer(page, 422, {
    detail: 'That site wouldn’t let Mealwright read the page. Paste the recipe’s text instead.',
    code: 'site_refused',
  });
  await page.goto('/recipes/import');
  await box(page).fill('https://bananaleaf.example/sambar/');
  await read(page).click();
  const alert = page.getByRole('alert');
  await expect(alert).toContainText('That site wouldn’t let Mealwright read the page.');
  const steps = alert.getByRole('list', { name: 'How to paste the recipe instead' }).getByRole('listitem');
  await expect(steps).toHaveText([
    'Open the recipe in your browser. Tip: the page’s “Print recipe” button gives a cleaner copy.',
    'Select from the title to the end of the method, and copy it.',
    'Paste it here, in place of the link. Pasted text never goes online.',
  ]);
  await expect(box(page)).toHaveValue('');
  await expect(box(page)).toBeFocused();
  await checkPage(page);
  await inTheme(page, 'dark');
  await checkPage(page, { themes: ['dark'] });
});

test('Remove line takes a line out of the counts, and Undo brings it back (F105)', async ({ page }) => {
  await checking(page);
  await expect(page.getByText('1 to confirm')).toBeVisible();
  await expect(page.getByText('2 need you')).toBeVisible();
  await expect(page.getByText(/without an ingredient/)).toHaveCount(0); // F152: no note
  await expect(page.getByRole('heading', { name: /^Ingredients/ })).toContainText('3');
  await page.getByRole('button', { name: /^Remove line: 1 red onion, sliced/ }).click();
  await expect(page.getByText('Removed “1 red onion, sliced”')).toBeVisible();
  await expect(page.getByText('0 to confirm')).toBeVisible();
  await expect(page.getByText(/without an ingredient/)).toHaveCount(0); // F152: no note
  await expect(page.getByRole('heading', { name: /^Ingredients/ })).toContainText('2');
  await expect(page.locator('.written').filter({ hasText: '1 red onion, sliced' })).toHaveCount(0);
  await checkPage(page);
  await page.getByRole('button', { name: 'Undo', exact: true }).click();
  await expect(page.getByText('Undone: Removed “1 red onion, sliced”')).toBeVisible();
  await expect(page.getByText('1 to confirm')).toBeVisible();
  await expect(page.getByText(/without an ingredient/)).toHaveCount(0); // F152: no note
});

test('Split into two turns one line into two, and Undo puts it back (F109)', async ({ page }) => {
  const water = unique('Waterx');
  const broth = unique('Brothx');
  await checking(page, {
    lines: [
      {
        kind: 'ingredient',
        written: '4 1/2 cups water and broth',
        words: `${water} and ${broth}`,
        amount: 4.5,
        amount_text: '4½',
        unit: 'cup',
        size: null,
        note: null,
        readable: true,
        label: 'needs_you',
        food: null,
        place: null,
        matched_by: null,
        counts: true,
        new_ingredient: { name: `${water} and ${broth}`, counted_as: 'volume', place: null },
        learn_name: null,
      },
    ],
    counts: { matched: 0, to_confirm: 0, needs_you: 1, staple: 0 },
  });
  await expect(page.getByText('1 needs you')).toBeVisible();
  await page.getByRole('button', { name: /^Split into two: 4 1\/2 cups water and broth/ }).click();
  await expect(page.getByLabel('First ingredient')).toHaveValue(water);
  await expect(page.getByLabel('Second ingredient')).toHaveValue(broth);
  await checkPage(page);
  await page.getByRole('button', { name: 'Split', exact: true }).click();
  await expect(page.getByText(/^Split “4 1\/2 cups water and broth” into two/)).toBeVisible();
  await expect(page.getByText('2 need you')).toBeVisible();
  await expect(page.getByRole('heading', { name: /^Ingredients/ })).toContainText('2');
  await expect(page.getByRole('button', { name: /^Amount|^No amount/ })).toHaveCount(2);
  await expect(page.getByRole('button', { name: /^Note 4½.cups together/ })).toHaveCount(2);
  await checkPage(page);
  await page.getByRole('button', { name: 'Undo', exact: true }).click();
  await expect(page.getByText('1 needs you')).toBeVisible();
  await expect(page.getByRole('button', { name: /^Split into two: 4 1\/2 cups water and broth/ })).toBeVisible();
});

test('several links are read one after another, each into its own draft, and a failing one in the middle stops nothing (F110)', async ({ page }) => {
  const asked: string[] = [];
  let open = 0;
  let most = 0;
  const kept: string[] = [];
  await page.route('**/api/v1/recipes/import', async (route: Route) => {
    const text: string = route.request().postDataJSON().text;
    asked.push(text);
    open += 1;
    most = Math.max(most, open);
    await new Promise((resolve) => setTimeout(resolve, 150));
    open -= 1;
    if (text.includes('refuses')) {
      await route.fulfill({
        status: 422,
        contentType: 'application/json',
        body: JSON.stringify({
          detail: 'That site wouldn’t let Mealwright read the page. Paste the recipe’s text instead.',
          code: 'site_refused',
        }),
      });
      return;
    }
    const name = text.includes('dosa') ? 'Masala dosa' : 'Rasam';
    await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(review({ name })) });
  });
  await page.route('**/api/v1/recipes/drafts', async (route: Route) => {
    if (route.request().method() !== 'POST') return route.fallback();
    const body = route.request().postDataJSON();
    kept.push(body.review.name);
    await route.fulfill({
      status: 201,
      contentType: 'application/json',
      body: JSON.stringify({ id: kept.length, ...body }),
    });
  });
  // The list agrees with the made-up drafts, so a row is not taken for a draft that is gone.
  await page.route('**/api/v1/recipes/drafts', async (route: Route) => {
    if (route.request().method() !== 'GET') return route.fallback();
    const drafts = kept.map((name, i) => ({ id: i + 1, name, source: { kind: 'link', site: null }, started_by: 'x', started_at: '2026-11-10T10:00:00Z', updated_at: '2026-11-10T10:00:00Z', expires_at: '2026-11-25T10:00:00Z', days_left: 15, lines_total: 3, lines_checked: 0 }));
    await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ drafts, count: drafts.length }) });
  });
  // Recipe import from links is on (F239: while it is off the chip says so instead).
  await photoSwitch(page, false, true);
  const answered = page.waitForResponse('**/api/v1/privacy/switches');
  await page.goto('/recipes/import');
  await answered;
  await box(page).fill(
    'https://example-recipes.org/masala-dosa\nhttps://refuses.example/chicken-65\nhttps://example-kitchen.net/rasam',
  );
  await expect(page.getByText('3 links · one after another').first()).toBeVisible();
  await page.getByRole('button', { name: 'Read the recipes' }).click();
  const results = page.getByRole('region', { name: 'Links being read' });
  const rows = results.getByRole('listitem');
  await expect(rows).toHaveCount(3);
  await expect(rows.nth(0)).toContainText('Masala dosa');
  await expect(rows.nth(0)).toContainText('example-recipes.org · in Drafts');
  await expect(rows.nth(0)).toContainText('Needs checking');
  await expect(rows.nth(1)).toContainText('That site wouldn’t let Mealwright read the page. Paste the recipe’s text instead.');
  await expect(rows.nth(1).getByRole('button', { name: 'Paste text' })).toBeVisible();
  await expect(rows.nth(2)).toContainText('Rasam');
  await expect(rows.nth(2)).toContainText('Needs checking');
  // In order, never two at once, and one draft for each link that could be read.
  expect(asked).toEqual([
    'https://example-recipes.org/masala-dosa',
    'https://refuses.example/chicken-65',
    'https://example-kitchen.net/rasam',
  ]);
  expect(most).toBe(1);
  expect(kept).toEqual(['Masala dosa', 'Rasam']);
  await expect(results).toContainText('If one link can’t be read, the rest carry on. You can leave this screen.');
  await expectNoSidewaysScroll(page);
  await checkPage(page);
  await rows.nth(1).getByRole('button', { name: 'Paste text' }).click();
  await expect(box(page)).toHaveValue('');
  await expect(box(page)).toBeFocused();
  await results.getByRole('link', { name: 'Go to Drafts' }).click();
  await expect(page).toHaveURL(/\/recipes\/drafts$/);
});

// --- Lines on Check (0.8 W4d: F187, F188, F189, and the header rule) ----------------------------

/** An ingredient line as the server reads it, with no ingredient behind it yet. */
const lineOf = (more: Json): Json => ({
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
const needsLine = (written: string, words: string): Json =>
  lineOf({ written, words, new_ingredient: { name: words, counted_as: 'weight', place: null }, learn_name: words });
const headingLine = (words: string): Json => lineOf({ kind: 'heading', label: null, written: words, words });

async function api(page: Page, method: 'post' | 'delete', path: string, data?: Json): Promise<Json> {
  const response = await page.request[method](`/api/v1${path}`, { data, headers: { 'idempotency-key': crypto.randomUUID() } });
  expect(response.status(), await response.text()).toBeLessThan(300);
  return response.status() === 204 ? {} : ((await response.json()) as Json);
}

test('Add a line at the end of each section: named, given the usual choices, and saved where it was added (F187)', async ({ page }) => {
  const n = { urad: unique('Urad dal'), ghee: unique('Ghee'), extra: unique('Fenugreek seeds') };
  if (!onPhone()) await page.setViewportSize({ width: 1280, height: 2600 });
  await checking(page, {
    name: unique('Masala dosa'),
    lines: [headingLine('For the batter'), needsLine(`1 cup ${n.urad}`, n.urad), headingLine('For the dosa'), needsLine(`ghee, for the pan`, n.ghee)],
    steps: [{ kind: 'step', text: 'Fry it.' }],
    counts: { matched: 0, to_confirm: 0, needs_you: 2, staple: 0 },
    left_out: [],
  });
  // One button at the end of each section, named for it.
  const adds = page.getByRole('button', { name: /^Add a line/ });
  await expect(adds).toHaveText(['Add a line to the batter', 'Add a line to the dosa']);
  const count = page.getByRole('heading', { name: /^Ingredients/ });
  await expect(count).toContainText('2');
  await adds.first().click();
  const name = page.getByLabel('What is it?');
  await expect(name).toBeFocused();
  // A line with no name yet is not counted, and asks for a name.
  await expect(count).toContainText('2');
  // The scan starts at the top of the page, so the box is shown whole, not under the page's own bar.
  await checkPage(page);
  await page.getByRole('button', { name: 'Add line', exact: true }).click();
  await expect(page.getByText('Type a name.')).toBeVisible();
  await name.fill(n.extra);
  await name.press('Enter');
  const added = page.locator('li.line[data-added]');
  await expect(added).toContainText('Added by you');
  await expect(count).toContainText('3');
  // The same choices as any line.
  await expect(added.getByRole('button', { name: `New ingredient “${n.extra}”` })).toBeVisible();
  for (const choice of ['Pick an ingredient', 'Made in this recipe', 'Made in another recipe', 'Treat as staple']) {
    await expect(added.getByRole('button', { name: choice, exact: true })).toBeVisible();
  }
  // Cancel on a new box takes the line away again.
  await adds.nth(1).click();
  await expect(name).toBeVisible();
  await page.locator('li.line').getByRole('button', { name: 'Cancel', exact: true }).click();
  await expect(name).toHaveCount(0);
  await expect(count).toContainText('3');
  await inTheme(page, 'dark');
  await checkPage(page, { themes: ['dark'] });
  // Everything is a staple (the simplest choice), and Save puts the new line in the batter, last.
  const staple = page.getByRole('button', { name: 'Treat as staple', exact: true });
  while (await staple.count()) await staple.first().click();
  await page.getByRole('button', { name: 'Save recipe' }).click();
  await expect(page).toHaveURL(/\/recipes\/\d+$/);
  const id = Number(page.url().split('/').pop());
  const saved = (await (await page.request.get(`/api/v1/recipes/${id}`)).json()) as Json;
  expect(saved.lines.map((l: Json) => l.words)).toEqual(['For the batter', n.urad, n.extra, 'For the dosa', n.ghee]);
  await page.getByRole('button', { name: 'Undo', exact: true }).click();
  await expect(page.getByText(/^Undone/)).toBeVisible();
});

test('Add a line is on the recipe with no headings too, and a line left with no name is not saved (F187)', async ({ page }) => {
  const dal = unique('Red lentils');
  await checking(page, {
    name: unique('Plain dal'),
    lines: [needsLine(`1 cup ${dal}`, dal)],
    steps: [{ kind: 'step', text: 'Boil.' }],
    counts: { matched: 0, to_confirm: 0, needs_you: 1, staple: 0 },
    left_out: [],
  });
  await page.getByRole('button', { name: 'Add a line', exact: true }).click();
  await expect(page.getByLabel('What is it?')).toBeFocused();
  await page.getByRole('button', { name: 'Treat as staple', exact: true }).click();
  await page.getByRole('button', { name: 'Save recipe' }).click();
  await expect(page).toHaveURL(/\/recipes\/\d+$/);
  const id = Number(page.url().split('/').pop());
  const saved = (await (await page.request.get(`/api/v1/recipes/${id}`)).json()) as Json;
  expect(saved.lines.map((l: Json) => l.words)).toEqual([dal]);
  await page.getByRole('button', { name: 'Undo', exact: true }).click();
  await expect(page.getByText(/^Undone/)).toBeVisible();
});

test('New ingredient says where it comes from: made in another recipe, kept where you choose (F188)', async ({ page }) => {
  const batter = unique('Dosa batter');
  const made = await api(page, 'post', '/recipes', { name: batter, made_ahead: true, makes: { amount: 1.5, unit: 'l' } });
  await checking(page, {
    name: unique('Masala dosa'),
    lines: [needsLine(`${batter}, as above`, batter)],
    steps: [{ kind: 'step', text: 'Fry it.' }],
    counts: { matched: 0, to_confirm: 0, needs_you: 1, staple: 0 },
    left_out: [],
  });
  await page.getByRole('button', { name: `New ingredient “${batter}”` }).click();
  await expect(page.getByText('Where does it come from?')).toBeVisible();
  await expect(page.getByRole('radio', { name: 'Bought' })).toBeChecked();
  await page.getByRole('radio', { name: 'Made in another recipe' }).click();
  await expect(page.getByText('Which recipe makes it?')).toBeVisible();
  await expect(page.getByText('No recipe for it yet?')).toBeVisible();
  // Done with no recipe picked says so.
  await page.getByRole('button', { name: 'Done', exact: true }).click();
  await expect(page.getByText('Pick the recipe that makes it.')).toBeVisible();
  await page.getByRole('button', { name: new RegExp(`^${batter}`) }).click();
  await expect(page.getByText('Made ahead · that recipe says how long it keeps')).toBeVisible();
  const fridge = page.getByRole('radio', { name: 'Fridge' });
  await expect(fridge).toBeChecked();
  await checkPage(page);
  await page.getByRole('radio', { name: 'Freezer' }).click();
  await page.getByRole('button', { name: 'Done', exact: true }).click();
  await expect(page.getByText('Made in another recipe:', { exact: true })).toBeVisible();
  await expect(page.getByText(`Uses the recipe “${batter}” when you save, kept in Freezer.`)).toBeVisible();
  await page.getByRole('button', { name: 'Save recipe' }).click();
  await expect(page).toHaveURL(/\/recipes\/\d+$/);
  const id = Number(page.url().split('/').pop());
  const saved = (await (await page.request.get(`/api/v1/recipes/${id}`)).json()) as Json;
  expect(saved.lines[0]).toMatchObject({ link: 'recipe', recipe: { id: made.id, name: batter }, food: null });
  const food = (await (await page.request.get(`/api/v1/foods/${made.homemade.id}`)).json()) as Json;
  expect(food.place.name).toBe('Freezer');
  await page.getByRole('button', { name: 'Undo', exact: true }).click();
  await expect(page.getByText(/^Undone/)).toBeVisible();
  const after = (await (await page.request.get(`/api/v1/foods/${made.homemade.id}`)).json()) as Json;
  expect(after.place).toBeNull();
});

test('a line can be made in another recipe from its choices, and Bought goes back to the usual box (F188)', async ({ page }) => {
  const chutney = unique('Coconut chutney');
  const recipe = await api(page, 'post', '/recipes', { name: chutney });
  await checking(page, {
    name: unique('Masala dosa'),
    lines: [needsLine(`${chutney}, to serve`, chutney)],
    steps: [{ kind: 'step', text: 'Fry it.' }],
    counts: { matched: 0, to_confirm: 0, needs_you: 1, staple: 0 },
    left_out: [],
  });
  // The box can go back to Bought.
  await page.getByRole('button', { name: `New ingredient “${chutney}”` }).click();
  await page.getByRole('radio', { name: 'Made in another recipe' }).click();
  await page.getByRole('radio', { name: 'Bought' }).click();
  await expect(page.getByLabel('Usually kept in')).toBeVisible();
  await page.locator('li.line').getByRole('button', { name: 'Cancel', exact: true }).click();
  // The line's own choice: only recipes are listed.
  await page.getByRole('button', { name: 'Made in another recipe', exact: true }).click();
  await expect(page.getByRole('list', { name: 'Matching recipes' })).toBeVisible();
  await page.getByRole('button', { name: new RegExp(`^${chutney}`) }).click();
  await expect(page.getByText('Made in another recipe:', { exact: true })).toBeVisible();
  await page.getByRole('button', { name: 'Save recipe' }).click();
  await expect(page).toHaveURL(/\/recipes\/\d+$/);
  const id = Number(page.url().split('/').pop());
  const saved = (await (await page.request.get(`/api/v1/recipes/${id}`)).json()) as Json;
  expect(saved.lines[0]).toMatchObject({ link: 'recipe', recipe: { id: recipe.id } });
  await page.getByRole('button', { name: 'Undo', exact: true }).click();
});

test('when a recipe and an ingredient share a name, Check offers the recipe first, each labelled (F189)', async ({ page }) => {
  const batter = unique('Dosa batter');
  const recipe = await api(page, 'post', '/recipes', { name: batter });
  await api(page, 'post', '/foods', { name: batter, counted_as: 'volume' });
  await checking(page, {
    name: unique('Masala dosa'),
    lines: [needsLine(`${batter}, as above · 4 cups`, batter)],
    steps: [{ kind: 'step', text: 'Fry it.' }],
    counts: { matched: 0, to_confirm: 0, needs_you: 1, staple: 0 },
    left_out: [],
  });
  await page.getByRole('button', { name: 'Pick an ingredient', exact: true }).click();
  await expect(page.getByRole('heading', { name: `What is “${batter}”?` })).toBeVisible();
  const rows = page.getByRole('list', { name: 'Matching ingredients and recipes' }).getByRole('listitem');
  await expect(rows).toHaveCount(2);
  await expect(rows.nth(0)).toContainText('Recipe');
  await expect(rows.nth(1)).toContainText('Ingredient');
  await expect(page.getByText('When a recipe and an ingredient share a name, the recipe comes first.')).toBeVisible();
  await checkPage(page);
  await rows.nth(0).getByRole('button').click();
  await expect(page.getByText('Made in another recipe:', { exact: true })).toBeVisible();
  await page.getByRole('button', { name: 'Save recipe' }).click();
  await expect(page).toHaveURL(/\/recipes\/\d+$/);
  const id = Number(page.url().split('/').pop());
  const saved = (await (await page.request.get(`/api/v1/recipes/${id}`)).json()) as Json;
  expect(saved.lines[0]).toMatchObject({ link: 'recipe', recipe: { id: recipe.id } });
  await page.getByRole('button', { name: 'Undo', exact: true }).click();
});

test('Save with unlinked lines can pick a recipe too (F189: every picker that links a line)', async ({ page }) => {
  const batter = unique('Idli batter');
  const recipe = await api(page, 'post', '/recipes', { name: batter });
  await checking(page, {
    name: unique('Idli'),
    lines: [needsLine(`${batter}, as above`, batter)],
    steps: [{ kind: 'step', text: 'Steam it.' }],
    counts: { matched: 0, to_confirm: 0, needs_you: 1, staple: 0 },
    left_out: [],
  });
  await page.getByRole('button', { name: 'Save recipe' }).click();
  const sheet = page.getByRole('dialog', { name: '1 line isn’t linked yet' });
  await sheet.getByRole('button', { name: 'Made in another recipe', exact: true }).click();
  await sheet.getByRole('button', { name: new RegExp(`^${batter}`) }).click();
  // The last card is not shown when nothing is left unlinked: the sheet closes, and Save again works.
  await expect(sheet).toBeHidden();
  await page.getByRole('button', { name: 'Save recipe' }).click();
  await expect(page).toHaveURL(/\/recipes\/\d+$/);
  const id = Number(page.url().split('/').pop());
  const saved = (await (await page.request.get(`/api/v1/recipes/${id}`)).json()) as Json;
  expect(saved.lines[0]).toMatchObject({ link: 'recipe', recipe: { id: recipe.id } });
  await page.getByRole('button', { name: 'Undo', exact: true }).click();
});

test('the Check header: the title sits in from the edge, and the step note drops under it when there is no room (cabledrawer 9 Nov)', async ({ page }) => {
  await answer(page, 200, review({ name: unique('Sambar') }));
  await page.setViewportSize(onPhone() ? { width: 320, height: 700 } : { width: 1280, height: 900 });
  await page.goto('/recipes/import');
  await box(page).fill('https://bananaleaf.example/sambar/');
  await read(page).click();
  const title = page.getByRole('heading', { level: 1 });
  await expect(title).toHaveText('Check before saving');
  // The page's own header takes over from the one shown while it loads: measure that one.
  await expect(onPhone() ? page.getByText('Step 2 of 3 · nothing saved yet', { exact: true }) : page.getByRole('list', { name: 'Import steps' })).toBeVisible();
  if (onPhone()) {
    const note = page.getByText('Step 2 of 3 · nothing saved yet', { exact: true });
    const counts = page.getByLabel('What was found');
    // In from the edge: further right than the counts under it, which start at the header's own padding.
    const t = (await title.boundingBox())!;
    expect(t.x - (await counts.boundingBox())!.x).toBeGreaterThanOrEqual(6);
    // 320 px: no room for both on a line, so the note is under the title, at its left.
    const dropped = (await note.boundingBox())!;
    expect(dropped.y).toBeGreaterThanOrEqual(t.y + t.height - 2);
    expect(Math.abs(dropped.x - t.x)).toBeLessThan(4);
    await expectNoSidewaysScroll(page);
    // 600 px: room, so it stays on the title's line, at the right.
    await page.setViewportSize({ width: 600, height: 700 });
    const wide = (await note.boundingBox())!;
    const t2 = (await title.boundingBox())!;
    expect(wide.y).toBeLessThan(t2.y + t2.height);
    expect(wide.x).toBeGreaterThan(t2.x + t2.width);
  } else {
    // The computer's header: the title is in from the edge, and the steps are beside it or under it, never over it.
    const t = (await title.boundingBox())!;
    expect(t.x).toBeGreaterThan(8);
    const steps = (await page.getByRole('list', { name: 'Import steps' }).boundingBox())!;
    const overlaps = steps.x < t.x + t.width && steps.x + steps.width > t.x && steps.y < t.y + t.height && steps.y + steps.height > t.y;
    expect(overlaps).toBe(false);
    await page.setViewportSize({ width: 800, height: 900 });
    const narrow = (await title.boundingBox())!;
    const steps2 = (await page.getByRole('list', { name: 'Import steps' }).boundingBox())!;
    const overlaps2 = steps2.x < narrow.x + narrow.width && steps2.x + steps2.width > narrow.x && steps2.y < narrow.y + narrow.height && steps2.y + steps2.height > narrow.y;
    expect(overlaps2).toBe(false);
    await expectNoSidewaysScroll(page);
  }
});

// A section as its own recipe (0.8 W4e, F190, cabledrawer 8 Nov): "Make this its own recipe" under a
// section heading on Check. The recipe is pasted (the path that never goes online); the Save is the
// real one.

/** A dosa with its batter as a section, in the pasted words a recipe page gives. */
function dosaText(n: { dosa: string; batter: string; dal: string; rice: string; ghee: string }) {
  return [
    n.dosa,
    'Serves 4',
    'Ingredients',
    'For the batter',
    `1 cup ${n.dal}`,
    `3 cups ${n.rice}`,
    'For the dosa',
    `4 cups ${n.batter}, as above`,
    `1 tbsp ${n.ghee}`,
    'Method',
    'For the batter:',
    '1. Soak the dal and rice for 4 hours.',
    '2. Grind and ferment overnight.',
    'For the dosa:', // no blank line before it: it stays a heading (cabledrawer 10 Nov)
    '1. Spread the batter thin and fry.',
  ].join('\n');
}

test('A section as its own recipe: asked on Check, both recipes saved together, one Undo takes both (F190)', async ({ page }) => {
  const n = { dosa: unique('Masala dosa'), batter: `Dosa ${unique('x')} batter`, dal: unique('Urad dal'), rice: unique('Idli rice'), ghee: unique('Ghee') };
  if (!onPhone()) await page.setViewportSize({ width: 1280, height: 2000 });
  await page.goto('/recipes/import');
  await box(page).fill(dosaText(n));
  await read(page).click();
  await expect(page.getByRole('heading', { level: 1 })).toHaveText('Check before saving');
  // One button under each section's heading, never done on its own.
  const make = page.getByRole('button', { name: 'Make this its own recipe' });
  await expect(make).toHaveCount(2);
  await expect(page.locator('.said')).toHaveCount(0);
  await make.first().click();
  const sheet = page.getByRole('dialog', { name: /its own recipe\?$/ });
  await expect(sheet.getByRole('heading', { name: 'Make “For the batter” its own recipe?' })).toBeVisible();
  // Prefilled from the line that names it: "4 cups dosa batter, as above".
  await expect(sheet.getByLabel('Name of the new recipe')).toHaveValue(n.batter);
  await expect(sheet.getByLabel('How much it makes')).toHaveValue('4');
  await expect(sheet).toContainText('with its 2 lines and 2 steps, kept as Made ahead');
  await expect(sheet).toContainText(`${n.dosa} then uses it as one line: “${n.batter} · 4 cups”.`);
  await expect(sheet).toContainText('Both recipes are checked here and saved together.');
  await checkPage(page);
  // Nothing is made until the button.
  await sheet.getByRole('button', { name: 'Cancel' }).click();
  await expect(sheet).toHaveCount(0);
  await expect(page.locator('.said')).toHaveCount(0);
  await make.first().click();
  await sheet.getByRole('button', { name: 'Make it its own recipe' }).click();
  await expect(sheet).toHaveCount(0);
  await expect(page.getByText('Made “For the batter” its own recipe')).toBeVisible();
  await expect(page.locator('.said')).toContainText(`${n.batter} · 4 cups`);
  await expect(page.getByText(`Made in its own recipe: ${n.batter}`)).toBeVisible();
  await expect(make).toHaveCount(1);
  await inTheme(page, 'dark');
  await checkPage(page, { themes: ['dark'] });
  // Both are checked on this screen: the batter's lines still need choices before Save.
  const staple = page.getByRole('button', { name: 'Treat as staple', exact: true });
  while (await staple.count()) await staple.first().click();
  await page.getByRole('button', { name: 'Save recipe' }).click();
  await expect(page).toHaveURL(/\/recipes\/\d+$/);
  const id = Number(page.url().split('/').pop());
  const dosa = (await (await page.request.get(`/api/v1/recipes/${id}`)).json()) as Json;
  expect(dosa.lines.map((l: Json) => l.words)).toEqual(['For the dosa', n.batter, n.ghee]);
  expect(dosa.steps.map((s: Json) => s.text)).toEqual(['For the dosa', 'Spread the batter thin and fry.']);
  const use = dosa.lines[1];
  expect(use.link).toBe('recipe');
  expect(use.amount).toBe(4);
  expect(use.unit).toBe('cup');
  const batter = (await (await page.request.get(`/api/v1/recipes/${use.recipe.id}`)).json()) as Json;
  expect(batter).toMatchObject({ name: n.batter, made_ahead: true });
  expect(batter.lines.map((l: Json) => l.words)).toEqual([n.dal, n.rice]);
  expect(batter.steps.map((s: Json) => s.text)).toEqual(['Soak the dal and rice for 4 hours.', 'Grind and ferment overnight.']);
  // One entry in Recent changes with one Undo; it takes both recipes back.
  await page.getByRole('button', { name: 'Undo', exact: true }).click();
  await expect(page.getByText(/^Undone/)).toBeVisible();
  expect((await page.request.get(`/api/v1/recipes/${id}`)).status()).toBe(404);
  expect((await page.request.get(`/api/v1/recipes/${use.recipe.id}`)).status()).toBe(404);
});

test('A section made its own recipe can be changed and kept in the recipe again, each with Undo (F190)', async ({ page }) => {
  const n = { dosa: unique('Masala dosa'), batter: `Dosa ${unique('x')} batter`, dal: unique('Urad dal'), rice: unique('Idli rice'), ghee: unique('Ghee') };
  if (!onPhone()) await page.setViewportSize({ width: 1280, height: 2000 });
  await page.goto('/recipes/import');
  await box(page).fill(dosaText(n));
  await read(page).click();
  await expect(page.getByRole('heading', { level: 1 })).toHaveText('Check before saving');
  await page.getByRole('button', { name: 'Make this its own recipe' }).first().click();
  const sheet = page.getByRole('dialog', { name: /its own recipe\?$/ });
  // A name and an amount are needed.
  await sheet.getByLabel('Name of the new recipe').fill('');
  await sheet.getByRole('button', { name: 'Make it its own recipe' }).click();
  await expect(sheet.getByText('Type a name.')).toBeVisible();
  await sheet.getByLabel('Name of the new recipe').fill('Batter');
  await sheet.getByLabel('How much it makes').fill('');
  await sheet.getByRole('button', { name: 'Make it its own recipe' }).click();
  await expect(sheet.getByText('Type how much it makes.')).toBeVisible();
  await sheet.getByLabel('How much it makes').fill('1.5');
  await sheet.getByLabel('Unit').selectOption('l');
  await sheet.getByRole('button', { name: 'Make it its own recipe' }).click();
  const said = page.locator('.said');
  await expect(said).toContainText('Batter · 1.5 litres');
  // Change opens the same sheet with what was typed.
  await said.locator('..').getByRole('button', { name: 'Change', exact: true }).click();
  await expect(sheet.getByLabel('Name of the new recipe')).toHaveValue('Batter');
  await sheet.getByLabel('Name of the new recipe').fill(`${n.batter} two`);
  await sheet.getByRole('button', { name: 'Done' }).click();
  await expect(said).toContainText(`${n.batter} two`);
  // Keep in this recipe puts it back, and Undo brings the own recipe back.
  await page.getByRole('button', { name: 'Keep in this recipe' }).click();
  await expect(page.getByText('Kept “For the batter” in this recipe')).toBeVisible();
  await expect(said).toHaveCount(0);
  await expect(page.getByRole('button', { name: 'Make this its own recipe' })).toHaveCount(2);
  await page.getByRole('button', { name: 'Undo', exact: true }).click();
  await expect(said).toContainText(`${n.batter} two`);
});

test('Offline, Save waits as it always does, and the section stays its own recipe until Save (F190)', async ({ page }) => {
  const n = { dosa: unique('Masala dosa'), batter: `Dosa ${unique('x')} batter`, dal: unique('Urad dal'), rice: unique('Idli rice'), ghee: unique('Ghee') };
  await page.goto('/recipes/import');
  await box(page).fill(dosaText(n));
  await read(page).click();
  await expect(page.getByRole('heading', { level: 1 })).toHaveText('Check before saving');
  await page.getByRole('button', { name: 'Make this its own recipe' }).first().click();
  await page.getByRole('dialog', { name: /its own recipe\?$/ }).getByRole('button', { name: 'Make it its own recipe' }).click();
  const staple = page.getByRole('button', { name: 'Treat as staple', exact: true });
  while (await staple.count()) await staple.first().click();
  await page.route('**/api/v1/**', (route) => route.abort('internetdisconnected'));
  await page.evaluate(() => window.dispatchEvent(new Event('offline')));
  await expect(page.getByRole('button', { name: 'Save recipe' })).toBeDisabled();
  await expect(page.locator('.said')).toBeVisible();
  await page.unroute('**/api/v1/**');
  await page.evaluate(() => window.dispatchEvent(new Event('online')));
  await expect(page.getByRole('button', { name: 'Save recipe' })).toBeEnabled();
  await page.getByRole('button', { name: 'Save recipe' }).click();
  await expect(page).toHaveURL(/\/recipes\/\d+$/);
  await page.getByRole('button', { name: 'Undo', exact: true }).click();
  await expect(page.getByText(/^Undone/)).toBeVisible();
});

// --- After several links: open a result, and quick import (0.8 IM2: F209, F216; cabledrawer 10 Nov) --

test('each read link opens its draft, and one button saves the drafts whose ingredients all matched (F209, F216)', async ({ page }) => {
  const ready = unique('Ready dal');
  const other = unique('Needs checking');
  const food = await api(page, 'post', '/foods', { name: unique('Toor dal'), counted_as: 'weight' });
  const foodId: number = food.food.id;
  const foodName: string = food.food.name;
  await page.route('**/api/v1/recipes/import', async (route: Route) => {
    const text: string = route.request().postDataJSON().text;
    const matched = lineOf({ written: '200 g toor dal', words: foodName, amount: 200, amount_text: '200', unit: 'g', label: 'matched', food: { id: foodId, name: foodName }, matched_by: foodName });
    const body = text.includes('ready')
      ? review({ name: ready, lines: [headingLine('For the dal'), matched], counts: { matched: 1, to_confirm: 0, needs_you: 0, staple: 0 } })
      : review({ name: other });
    await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(body) });
  });
  await page.goto('/recipes/import');
  await box(page).fill('https://example-recipes.org/ready-dal\nhttps://example-kitchen.net/other');
  await page.getByRole('button', { name: 'Read the recipes' }).click();
  const results = page.getByRole('region', { name: 'Links being read' });
  await expect(results.getByRole('listitem')).toHaveCount(2);
  await expect(results.getByRole('link', { name: `Check ${other}` })).toBeVisible();
  // cabledrawer 11 Nov: a row whose ingredients all matched says so; the others say they need checking.
  await expect(results.getByRole('listitem').filter({ hasText: ready })).toContainText('✓ All matched');
  await expect(results.getByRole('listitem').filter({ hasText: other })).toContainText('Needs checking');
  await expect(results.getByRole('link', { name: `Check ${ready}` })).toBeVisible();
  // Only the draft whose ingredients all matched is offered for saving.
  await expect(results.getByRole('button', { name: 'Save 1 ready recipe' })).toBeVisible();
  await expect(results).toContainText('Ready means every ingredient matched. The others stay in Drafts for you to check.');
  await checkPage(page);
  await results.getByRole('button', { name: 'Save 1 ready recipe' }).click();
  await expect(page.getByText('Saved 1 recipe', { exact: true })).toBeVisible();
  await expect(results.getByRole('link', { name: `Open ${ready}` })).toBeVisible();
  const list = (await (await page.request.get('/api/v1/recipes/drafts')).json()) as Json;
  expect(list.drafts.filter((d: Json) => d.name === ready)).toHaveLength(0);
  const waiting = list.drafts.filter((d: Json) => d.name === other);
  expect(waiting).toHaveLength(1);
  // One Undo takes the quick save back: its draft is there again, and can be saved again.
  await page.getByRole('button', { name: 'Undo', exact: true }).click();
  await expect(page.getByText(/^Undone/)).toBeVisible();
  await expect(results.getByRole('button', { name: 'Save 1 ready recipe' })).toBeVisible();
  await expect.poll(async () => ((await (await page.request.get('/api/v1/recipes/drafts')).json()) as Json).drafts.filter((d: Json) => d.name === ready).length).toBe(1);
  // The result opens its draft's Check.
  await results.getByRole('link', { name: `Check ${other}` }).click();
  await expect(page).toHaveURL(new RegExp(`/recipes/drafts/${waiting[0].id}$`));
  await expect(page.getByRole('heading', { level: 1 })).toHaveText('Check before saving');
  for (const draft of ((await (await page.request.get('/api/v1/recipes/drafts')).json()) as Json).drafts.filter((d: Json) => d.name === ready || d.name === other)) {
    await page.request.delete(`/api/v1/recipes/drafts/${draft.id}`);
  }
});
