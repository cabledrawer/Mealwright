import { test, expect, type Page, type Route } from './clock.ts';
import { checkPage, expectNoSidewaysScroll, inTheme, setAccountTheme } from './a11y.ts';

// Pints (0.6, PR 7): the household's pint in Settings, and the review's card "This looks like a
// US recipe" with its switch (mockups ImportPints-*). Runs on Chromium (phone and computer) and
// WebKit (computer), see playwright.config.ts. The review is the server's answer to
// POST /recipes/import made up in the browser (no test goes online); Save, Settings and the
// household setting are the real server's. The tests run one at a time on one server, and each
// puts the pint back to UK.

type Json = Record<string, any>; // eslint-disable-line @typescript-eslint/no-explicit-any

const SWITCH = 'Read its pints as US pints (473 ml)';
const unique = (name: string) => `${name} ${test.info().project.name.replace(/\D/g, '')}${Date.now() % 100000}`;

async function setPints(page: Page, pints: 'uk' | 'us') {
  const response = await page.request.patch('/api/v1/household', { data: { pints } });
  expect(response.ok(), `couldn’t set the pint: ${response.status()}`).toBe(true);
}

const pintsNow = async (page: Page) => ((await (await page.request.get('/api/v1/household')).json()) as Json).pints as string;

test.beforeEach(async ({ page }) => {
  await setAccountTheme(page, 'auto');
  await setPints(page, 'uk');
});

test.afterEach(async ({ page }) => {
  await setPints(page, 'uk');
});

/** A US recipe site read for a UK household, as the server answers it. */
function pudding(name = 'Creamy rice pudding'): Json {
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
    pint_ml: null,
    ...more,
  });
  return {
    source: { kind: 'link', url: 'https://www.allrecipes.com/recipe/1/x/', site: 'allrecipes.com' },
    name,
    description: null,
    author: null,
    time_minutes: null,
    serves: null,
    makes: null,
    tags: [],
    nutrition: { kcal: null, protein: null, carbs: null, fat: null, fibre: null },
    photo: { state: 'off', photo: null, message: 'Photo not downloaded' },
    lines: [
      line({
        written: '2 pints whole milk',
        words: 'whole milk',
        amount: 946,
        amount_text: '946',
        unit: 'ml',
        note: 'as written: 2 pints whole milk',
        new_ingredient: { name: 'Whole milk', counted_as: 'volume', place: null },
        learn_name: 'whole milk',
        pint_ml: { uk_ml: 1136, us_ml: 946 },
      }),
      line({
        written: '1 tsp vanilla extract',
        words: 'vanilla extract',
        amount: 1,
        amount_text: '1',
        unit: 'tsp',
        new_ingredient: { name: 'Vanilla extract', counted_as: 'volume', place: null },
        learn_name: 'vanilla extract',
      }),
    ],
    steps: [{ kind: 'step', text: 'Simmer the rice in the milk.' }],
    counts: { matched: 0, to_confirm: 0, needs_you: 2, staple: 0 },
    lines_cut: false,
    steps_cut: false,
    steps_shortened: 0,
    left_out: [],
    pints: { household: 'uk', us_site: true, reading: 'us' },
  };
}

const answer = (page: Page, body: Json) =>
  page.route('**/api/v1/recipes/import', (route: Route) =>
    route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(body) }),
  );

async function openReview(page: Page, body: Json) {
  await answer(page, body);
  await page.goto('/recipes/import');
  await page.getByLabel('Paste a link or the recipe’s text').fill('https://www.allrecipes.com/recipe/1/x/');
  await page.getByRole('button', { name: 'Read the recipe' }).click();
  await expect(page.getByRole('heading', { level: 1 })).toHaveText('Check before saving');
}

test('a US recipe: the card, the switch on by default, the milk in US pints', async ({ page }) => {
  await openReview(page, pudding());
  await expect(page.getByText('This looks like a US recipe')).toBeVisible();
  await expect(page.getByRole('switch', { name: SWITCH })).toBeChecked();
  await expect(page.getByText('For this recipe only. Your setting stays UK pints.')).toBeVisible();
  await expect(page.getByText('946 ml', { exact: true })).toBeVisible();
  await expect(page.getByText(/2 pints whole milk\s+· US pints/)).toBeVisible();
  await expect(page.getByText('Switch it off and the whole milk reads 1.14 L (UK pints).')).toBeVisible();
  await expectNoSidewaysScroll(page);
  await checkPage(page);
});

test('the switch re-reads the pint line, for this recipe only', async ({ page }) => {
  await openReview(page, pudding());
  await page.getByRole('switch', { name: SWITCH }).click();
  await expect(page.getByRole('switch', { name: SWITCH })).not.toBeChecked();
  await expect(page.getByText('1136 ml', { exact: true })).toBeVisible();
  await expect(page.getByText(/2 pints whole milk\s+· UK pints/)).toBeVisible();
  await expect(page.getByText('Switch it on and the whole milk reads 946 ml (US pints).')).toBeVisible();
  expect(await pintsNow(page)).toBe('uk'); // the household's own setting is untouched either way
  await page.getByRole('switch', { name: SWITCH }).click();
  await expect(page.getByText('946 ml', { exact: true })).toBeVisible();
  expect(await pintsNow(page)).toBe('uk');
});

test('Save keeps the pint the switch was left on', async ({ page }) => {
  const title = unique('Rice pudding');
  await openReview(page, pudding(title));
  await page.getByRole('switch', { name: SWITCH }).click(); // UK pints: 1136 ml
  await page.getByRole('button', { name: 'Save recipe' }).click();
  await expect(page).toHaveURL(/\/recipes\/\d+$/);
  const id = Number(page.url().split('/').pop());
  const recipe = (await (await page.request.get(`/api/v1/recipes/${id}`)).json()) as Json;
  const milk = recipe.lines.find((l: Json) => l.words === 'whole milk');
  expect([milk.amount, milk.unit]).toEqual([1136, 'ml']);
  await page.getByRole('button', { name: 'Undo' }).click(); // leaves no recipe behind
  await expect(page.getByText(/^Undone/)).toBeVisible();
});

test('a US household sees no card, and a page that is not American neither', async ({ page }) => {
  await openReview(page, { ...pudding(), pints: { household: 'us', us_site: true, reading: 'us' } });
  await expect(page.getByText('946 ml', { exact: true })).toBeVisible();
  await expect(page.getByText('This looks like a US recipe')).toHaveCount(0);
  await openReview(page, { ...pudding(), pints: { household: 'uk', us_site: false, reading: 'uk' } });
  await expect(page.getByText('This looks like a US recipe')).toHaveCount(0);
});

test('the card in the dark theme passes the accessibility scan', async ({ page }) => {
  await openReview(page, pudding());
  await inTheme(page, 'dark');
  await checkPage(page, { themes: ['dark'] });
});

test('Settings has the pint switch: off for UK pints, saved on the server', async ({ page }) => {
  await page.goto('/settings');
  const pint = page.getByRole('switch', { name: 'Read pints as US pints' });
  await expect(page.getByRole('heading', { name: 'Amounts' })).toBeVisible();
  await expect(pint).not.toBeChecked();
  await expect(page.getByText('A pint is 568 ml (UK). Switch on for 473 ml (US).')).toBeVisible();
  await checkPage(page);
  await pint.click();
  await expect(pint).toBeChecked();
  await expect(page.getByText('A pint is 473 ml (US).')).toBeVisible();
  await expect.poll(() => pintsNow(page)).toBe('us');
  await page.reload();
  await expect(page.getByRole('switch', { name: 'Read pints as US pints' })).toBeChecked();
  await page.getByRole('switch', { name: 'Read pints as US pints' }).click();
  await expect.poll(() => pintsNow(page)).toBe('uk');
});

test('Settings puts the switch back when the server can’t save it', async ({ page }) => {
  await page.route('**/api/v1/household', (route: Route) =>
    route.request().method() === 'PATCH'
      ? route.fulfill({ status: 403, contentType: 'application/json', body: JSON.stringify({ detail: 'Only the household’s admin can change this.', code: 'admins_only' }) })
      : route.continue(),
  );
  await page.goto('/settings');
  const pint = page.getByRole('switch', { name: 'Read pints as US pints' });
  await pint.click();
  await expect(page.getByRole('alert')).toHaveText('Only the household’s admin can change this.');
  await expect(pint).not.toBeChecked();
  expect(await pintsNow(page)).toBe('uk');
});
