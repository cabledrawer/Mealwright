import { test, expect, type BrowserContext, type Locator, type Page } from '@playwright/test';
import { checkPage, expectNoSidewaysScroll, setAccountTheme } from './a11y.ts';

// Recipes on a computer (0.4, PR 4): the three panes (sidebar · All recipes · the recipe being
// read), against the real server. Runs in the "desktop 0.4 panes" project (1280 × 900); the
// tests that are about width set their own. The phone's pages are covered by recipes.spec.ts,
// recipe-page.spec.ts and the saved phone screenshots.

const key = () => ({ 'idempotency-key': crypto.randomUUID() });

async function call(page: Page, method: 'POST' | 'PUT', path: string, data: object, status = 201) {
  const response = await page.request.fetch(`/api/v1${path}`, {
    method,
    data,
    headers: key(),
  });
  expect(response.status(), `${method} ${path}: ${await response.text()}`).toBe(status);
  return (await response.json()) as Record<string, any>;
}

const stamp = () => `${Date.now().toString(36)}${Math.floor(Math.random() * 1296).toString(36)}`;

async function makeFood(page: Page, name: string) {
  const made = await call(page, 'POST', '/foods', {
    name,
    counted_as: 'weight',
  });
  return made.food.id as number;
}

const makeRecipe = (page: Page, body: object) => call(page, 'POST', '/recipes', body);

const list = (page: Page) => page.getByRole('region', { name: 'Recipe list' });
const reading = (page: Page) => page.getByRole('region', { name: 'Recipe', exact: true });
const rows = (page: Page) => list(page).getByRole('listitem');
const search = (page: Page, words: string) => page.getByRole('searchbox', { name: 'Search recipes' }).fill(words);

/** Make `count` recipes whose names start with `tag`, A to Z in the order made. */
async function manyNamed(page: Page, tag: string, count: number, extra: object = {}) {
  const made: { id: number; name: string }[] = [];
  for (let i = 1; i <= count; i++) {
    const name = `${tag} ${String(i).padStart(2, '0')}`;
    const recipe = await makeRecipe(page, {
      name,
      steps: [{ text: `Step for ${name}.` }],
      ...extra,
    });
    made.push({ id: recipe.id, name });
  }
  return made;
}

test.beforeEach(async ({ page }) => {
  await setAccountTheme(page, 'auto');
});

test('/recipes shows the list beside a calm empty reading pane, and passes the accessibility checks', async ({ page }) => {
  await page.goto('/recipes');
  await expect(list(page).getByRole('heading', { name: 'Recipes', level: 1 })).toBeVisible();
  await expect(reading(page).getByRole('heading', { name: 'Choose a recipe' })).toBeVisible();
  await expect(reading(page).getByText('Pick one from the list to read it here.')).toBeVisible();
  await expect(reading(page).getByRole('article')).toHaveCount(0);
  // The sidebar's tree marks All recipes as the page you are on.
  await expect(page.getByRole('group', { name: 'Recipes' }).getByRole('link', { name: 'All recipes' })).toHaveAttribute(
    'aria-current',
    'page',
  );
  // Hidden in 0.4: not drawn, not stubbed.
  await expect(
    page.getByRole('main').getByText(/New recipe|Import a recipe|Plan it|Start cooking|Cook once|Planned|Edit|Delete|Drafts/),
  ).toHaveCount(0);
  await checkPage(page);
});

test('a recipe opens beside the list: its row is marked, its heading has focus, and the sidebar and breadcrumb agree', async ({ page }) => {
  const tag = `Aardvark ${stamp()}`;
  const [first, second] = await manyNamed(page, tag, 2, {
    description: 'One line about it',
  });
  await page.goto('/recipes');
  await search(page, tag);
  await expect(rows(page)).toHaveCount(2);

  await list(page)
    .getByRole('link', { name: new RegExp(first!.name) })
    .click();
  await expect(page).toHaveURL(`/recipes/${first!.id}`);
  const heading = reading(page).getByRole('heading', {
    name: first!.name,
    level: 1,
  });
  await expect(heading).toBeVisible();
  await expect(heading).toBeFocused(); // the screen reader says its name
  await expect(list(page).getByRole('link', { name: new RegExp(first!.name) })).toHaveAttribute('aria-current', 'page');
  await expect(list(page).getByRole('link', { name: new RegExp(second!.name) })).not.toHaveAttribute('aria-current', 'page');
  const crumbs = reading(page).getByRole('navigation', { name: 'Breadcrumb' });
  await expect(crumbs.getByRole('link', { name: 'Recipes' })).toBeVisible();
  await expect(crumbs.locator('[aria-current="page"]')).toHaveText(first!.name);
  await expect(page.getByRole('group', { name: 'Recipes' }).getByRole('link', { name: 'All recipes' })).toHaveAttribute(
    'aria-current',
    'page',
  );
  // The list is still searched.
  await expect(page.getByRole('searchbox', { name: 'Search recipes' })).toHaveValue(tag);
  await expect(rows(page)).toHaveCount(2);
  await expect(page).toHaveTitle(`${first!.name} · Mealwright`);
  await checkPage(page);

  // Another recipe: the pane changes, the list stays, and there is a heading to hear again.
  await list(page)
    .getByRole('link', { name: new RegExp(second!.name) })
    .click();
  await expect(page).toHaveURL(`/recipes/${second!.id}`);
  await expect(reading(page).getByRole('heading', { name: second!.name, level: 1 })).toBeFocused();
  await expect(list(page).getByRole('link', { name: new RegExp(second!.name) })).toHaveAttribute('aria-current', 'page');
  await expect(list(page).getByRole('link', { name: new RegExp(first!.name) })).not.toHaveAttribute('aria-current', 'page');
});

test('Back and Forward move between recipes, and a reload keeps the open recipe', async ({ page }) => {
  // A to Z with a name no other test uses, so both rows are in the first page of the list.
  const tag = `Aaardvark ${stamp()}`;
  const [first, second] = await manyNamed(page, tag, 2);
  await page.goto('/recipes');
  await search(page, tag);
  await list(page)
    .getByRole('link', { name: new RegExp(first!.name) })
    .click();
  await expect(reading(page).getByRole('heading', { name: first!.name, level: 1 })).toBeVisible();
  await list(page)
    .getByRole('link', { name: new RegExp(second!.name) })
    .click();
  await expect(reading(page).getByRole('heading', { name: second!.name, level: 1 })).toBeVisible();

  await page.goBack();
  await expect(page).toHaveURL(`/recipes/${first!.id}`);
  await expect(reading(page).getByRole('heading', { name: first!.name, level: 1 })).toBeVisible();
  await expect(list(page).getByRole('link', { name: new RegExp(first!.name) })).toHaveAttribute('aria-current', 'page');
  await page.goBack();
  await expect(page).toHaveURL('/recipes');
  await expect(reading(page).getByRole('heading', { name: 'Choose a recipe' })).toBeVisible();
  await expect(page.getByRole('searchbox', { name: 'Search recipes' })).toHaveValue(tag); // the list stayed as it was
  await page.goForward();
  await page.goForward();
  await expect(page).toHaveURL(`/recipes/${second!.id}`);

  await page.reload();
  await expect(page).toHaveURL(`/recipes/${second!.id}`);
  await expect(reading(page).getByRole('heading', { name: second!.name, level: 1 })).toBeVisible();
  await expect(list(page).getByRole('link', { name: new RegExp(second!.name) })).toHaveAttribute('aria-current', 'page');
});

test('the list keeps its search, its filter and its scroll while recipes open', async ({ page }) => {
  const tag = `Tagged${stamp()}`;
  const word = `Scroller ${stamp()}`;
  const made = await manyNamed(page, word, 24, { tags: [tag] });
  await page.goto('/recipes');
  await search(page, word);
  await expect(rows(page)).toHaveCount(24);
  const filters = list(page).getByRole('group', { name: 'Show' });
  await filters.getByRole('button', { name: tag }).click();
  await expect(filters.getByRole('button', { name: tag })).toHaveAttribute('aria-pressed', 'true');
  await expect(rows(page)).toHaveCount(24);

  // Scroll the list to its end, open the last recipe, and look again.
  const far = await list(page).evaluate((el) => {
    el.scrollTop = el.scrollHeight;
    return el.scrollTop;
  });
  expect(far).toBeGreaterThan(300);
  await list(page)
    .getByRole('link', { name: new RegExp(made.at(-1)!.name) })
    .click();
  await expect(reading(page).getByRole('heading', { name: made.at(-1)!.name, level: 1 })).toBeVisible();
  expect(await list(page).evaluate((el) => el.scrollTop)).toBeGreaterThanOrEqual(far - 2);
  await expect(page.getByRole('searchbox', { name: 'Search recipes' })).toHaveValue(word);
  await expect(filters.getByRole('button', { name: tag })).toHaveAttribute('aria-pressed', 'true');
  // And the same after going on to another one and Back.
  await list(page)
    .getByRole('link', { name: new RegExp(made.at(-2)!.name) })
    .click();
  await expect(reading(page).getByRole('heading', { name: made.at(-2)!.name, level: 1 })).toBeVisible();
  await page.goBack();
  await expect(reading(page).getByRole('heading', { name: made.at(-1)!.name, level: 1 })).toBeVisible();
  expect(await list(page).evaluate((el) => el.scrollTop)).toBeGreaterThanOrEqual(far - 2);
});

test('a long recipe scrolls in its own pane, and the next recipe opens at its top', async ({ page }) => {
  const tag = `Longread ${stamp()}`;
  const long = await makeRecipe(page, {
    name: `${tag} one`,
    steps: Array.from({ length: 40 }, (_, i) => ({
      text: `Step number ${i + 1}: stir it well and keep going for a while.`,
    })),
  });
  const short = await makeRecipe(page, {
    name: `${tag} two`,
    steps: [{ text: 'Stir.' }],
  });
  await page.goto(`/recipes/${long.id}`);
  await expect(reading(page).getByRole('heading', { name: `${tag} one`, level: 1 })).toBeVisible();
  const scrolled = await reading(page).evaluate((el) => {
    el.scrollTop = 400;
    return {
      top: el.scrollTop,
      whole: document.scrollingElement!.scrollHeight <= innerHeight,
    };
  });
  expect(scrolled.top).toBeGreaterThan(300);
  expect(scrolled.whole, 'the page itself does not scroll').toBe(true);
  await page.goto('/recipes');
  await search(page, tag);
  await page.getByRole('link', { name: new RegExp(`${tag} one`) }).click();
  await reading(page).evaluate((el) => (el.scrollTop = 400));
  await list(page)
    .getByRole('link', { name: new RegExp(`${tag} two`) })
    .click();
  await expect(reading(page).getByRole('heading', { name: `${tag} two`, level: 1 })).toBeVisible();
  expect(await reading(page).evaluate((el) => el.scrollTop)).toBe(0);
  expect(short.id).toBeGreaterThan(0);
});

// --- Keyboard -----------------------------------------------------------------------------------

/** Which pane the focused element is in: 0 the sidebar, 1 the list, 2 the reading pane. */
const paneOfFocus = (page: Page) =>
  page.evaluate(() => {
    const el = document.activeElement;
    if (!el || el === document.body) return null;
    if (el.closest('aside')) return 0;
    if (el.closest('[aria-label="Recipe list"]')) return 1;
    if (el.closest('[aria-label="Recipe"]')) return 2;
    return -1;
  });

test('keyboard: Tab goes nav, then list, then reading pane; rows are links; Enter opens one and focus follows to its heading', async ({
  page,
}) => {
  const tag = `Keys ${stamp()}`;
  const dal = await makeFood(page, `Keys dal ${stamp()}`);
  const [one, two] = await manyNamed(page, tag, 2, {
    lines: [{ words: 'dal', food_id: dal, amount: 100, unit: 'g' }],
  });
  await page.goto(`/recipes/${one!.id}`);
  await expect(reading(page).getByRole('heading', { name: one!.name, level: 1 })).toBeVisible();
  await search(page, tag);
  await expect(rows(page)).toHaveCount(2);
  await expect(list(page).getByRole('listitem').getByRole('button')).toHaveCount(0);
  await expect(list(page).getByRole('link', { name: new RegExp(one!.name) })).toBeVisible();

  // Tab from the top of the page: every stop is in the same pane as the one before, or later.
  await page.getByRole('link', { name: 'Skip to content' }).focus();
  const seen: number[] = [];
  for (let i = 0; i < 80; i++) {
    await page.keyboard.press('Tab');
    const pane = await paneOfFocus(page);
    if (pane === null) break;
    seen.push(pane);
    if (pane === 2 && seen.filter((p) => p === 2).length > 3) break;
  }
  expect(seen, 'Tab visits the sidebar, then the list, then the reading pane').toEqual([...seen].sort((a, b) => a - b));
  expect(new Set(seen)).toEqual(new Set([0, 1, 2]));

  // Enter on a row (a link) opens that recipe, and focus lands on its heading.
  const row = list(page).getByRole('link', { name: new RegExp(two!.name) });
  await row.focus();
  await page.keyboard.press('Enter');
  await expect(page).toHaveURL(`/recipes/${two!.id}`);
  const heading = reading(page).getByRole('heading', {
    name: two!.name,
    level: 1,
  });
  await expect(heading).toBeFocused();
  // Tab goes on into the reading pane (the Keep screen awake switch or the servings), not back.
  await page.keyboard.press('Tab');
  expect(await paneOfFocus(page)).toBe(2);
  // Shift+Tab twice goes back to the list.
  await page.keyboard.press('Shift+Tab');
  await page.keyboard.press('Shift+Tab');
  expect(await paneOfFocus(page)).toBe(1);
});

// --- Widths -------------------------------------------------------------------------------------

test('widths: three panes from 1024 px (sidebar open) or 848 px (sidebar collapsed); one page at a time below; the phone layout under 768 px', async ({
  page,
}) => {
  const tag = `Widths ${stamp()}`;
  const [one] = await manyNamed(page, tag, 1);
  const panes = async () => (await reading(page).count()) > 0 && (await list(page).count()) > 0;

  // Wide: three panes. Very wide: the same, with the recipe kept to a readable width.
  for (const width of [2560, 1440, 1280, 1024]) {
    await page.setViewportSize({ width, height: 900 });
    await page.goto(`/recipes/${one!.id}`);
    await expect(reading(page).getByRole('heading', { name: one!.name, level: 1 })).toBeVisible();
    await expect(list(page).getByRole('heading', { name: 'Recipes' })).toBeVisible();
    expect(await panes(), `${width} px`).toBe(true);
    await expectNoSidewaysScroll(page);
    const article = await reading(page).getByRole('article').boundingBox();
    expect(article!.width).toBeLessThanOrEqual(1100);
    expect(article!.width).toBeGreaterThanOrEqual(width === 1024 ? 400 : 600);
  }

  // The in-between: a tablet held upright, or a narrow window. The sidebar stays; Recipes shows
  // one page at a time, the list and then the recipe (as on a phone).
  for (const width of [1023, 900, 768]) {
    await page.setViewportSize({ width, height: 900 });
    await page.goto('/recipes');
    await expect(page.getByRole('heading', { name: 'Recipes', level: 1 })).toBeVisible();
    await expect(page.getByRole('navigation', { name: 'Main' })).toBeVisible(); // the sidebar
    expect(await panes(), `${width} px, list`).toBe(false);
    await expectNoSidewaysScroll(page);
    await page.goto(`/recipes/${one!.id}`);
    await expect(page.getByRole('heading', { name: one!.name, level: 1 })).toBeVisible();
    expect(await panes(), `${width} px, recipe`).toBe(false);
    await expect(page.getByRole('searchbox', { name: 'Search recipes' })).toHaveCount(0);
    await expect(page.getByRole('navigation', { name: 'Breadcrumb' })).toBeVisible();
  }

  // The sidebar collapsed to icons leaves room for the panes sooner.
  await page.addInitScript(() => localStorage.setItem('mealwright.sidebar', 'collapsed'));
  for (const [width, wantPanes] of [
    [848, true],
    [847, false],
  ] as const) {
    await page.setViewportSize({ width, height: 900 });
    await page.goto(`/recipes/${one!.id}`);
    await expect(page.getByRole('heading', { name: one!.name, level: 1 })).toBeVisible();
    expect(await panes(), `${width} px, collapsed`).toBe(wantPanes);
    await expectNoSidewaysScroll(page);
  }

  // Under 768 px: the phone's layout, with its tab bar and no sidebar.
  await page.setViewportSize({ width: 767, height: 900 });
  await page.goto('/recipes');
  await expect(page.getByRole('heading', { name: 'Recipes', level: 1 })).toBeVisible();
  await expect(page.getByRole('link', { name: 'Ingredients', exact: true })).toBeVisible();
  expect(await panes()).toBe(false);
});

test('resizing across the width where the panes fit changes the layout without losing the open recipe', async ({ page }) => {
  const tag = `Resize ${stamp()}`;
  const [one] = await manyNamed(page, tag, 1);
  await page.goto(`/recipes/${one!.id}`);
  await expect(reading(page).getByRole('heading', { name: one!.name, level: 1 })).toBeVisible();
  await page.setViewportSize({ width: 900, height: 900 });
  await expect(list(page)).toHaveCount(0);
  await expect(page.getByRole('heading', { name: one!.name, level: 1 })).toBeVisible();
  await page.setViewportSize({ width: 1300, height: 900 });
  await expect(list(page)).toBeVisible();
  await expect(reading(page).getByRole('heading', { name: one!.name, level: 1 })).toBeVisible();
  await expect(page).toHaveURL(`/recipes/${one!.id}`);
});

// --- States -------------------------------------------------------------------------------------

test('not found: a deleted recipe says so beside a working list', async ({ page }) => {
  const recipe = await makeRecipe(page, { name: `Gone ${stamp()}` });
  const removed = await page.request.delete(`/api/v1/recipes/${recipe.id}`, {
    headers: key(),
  });
  expect(removed.ok()).toBe(true);
  await page.goto(`/recipes/${recipe.id}`);
  await expect(reading(page).getByRole('heading', { name: 'Recipe not found' })).toBeVisible();
  await expect(reading(page).getByText('This recipe isn’t here any more. It may have been deleted.')).toBeVisible();
  await expect(reading(page).getByRole('heading', { name: 'Recipe not found' })).toBeFocused();
  await expect(page.getByRole('searchbox', { name: 'Search recipes' })).toBeVisible();
  await checkPage(page);
  // The breadcrumb leads back to the list's own page.
  await reading(page).getByRole('link', { name: 'Recipes' }).click();
  await expect(page).toHaveURL('/recipes');
});

test('loading and failed: each pane says its own, and the list still works', async ({ page }) => {
  const recipe = await makeRecipe(page, { name: `Slow ${stamp()}` });
  let release!: () => void;
  const held = new Promise<void>((resolve) => (release = resolve));
  const url = new RegExp(`/api/v1/recipes/${recipe.id}$`);
  await page.route(url, async (route) => {
    await held;
    await route.fulfill({ status: 500, json: { detail: 'Something broke.' } });
  });
  await page.goto(`/recipes/${recipe.id}`);
  await expect(reading(page).getByText('Loading…')).toBeVisible();
  await expect(page.getByRole('searchbox', { name: 'Search recipes' })).toBeVisible();
  release();
  await expect(reading(page).getByText('Couldn’t load this recipe. Try again.')).toBeVisible();
  await checkPage(page);
  await page.unroute(url);
  await reading(page).getByRole('button', { name: 'Try again' }).click();
  await expect(reading(page).getByRole('heading', { name: recipe.name, level: 1 })).toBeVisible();
});

test('empty household: the list says No recipes yet and the reading pane stays quiet', async ({ page }) => {
  await page.route('**/api/v1/recipes?**', (route) =>
    route.fulfill({
      json: { total: 0, all_recipes: 0, recipes: [], next: null },
    }),
  );
  await page.route('**/api/v1/recipes/tags', (route) => route.fulfill({ json: { tags: [] } }));
  await page.goto('/recipes');
  await expect(list(page).getByRole('heading', { name: 'No recipes yet' })).toBeVisible();
  await expect(reading(page).getByText('Choose a recipe')).toHaveCount(0);
  await expect(page.getByRole('main').getByText(/New recipe|Add a recipe|Import/)).toHaveCount(0);
  await checkPage(page);
});

async function goOffline(page: Page, context: BrowserContext, path: string, searched: string) {
  const hello = page.waitForResponse((r) => r.url().endsWith('/api/v1/events'));
  await page.goto(path);
  await search(page, searched);
  await expect(page.getByRole('searchbox', { name: 'Search recipes' })).toHaveValue(searched);
  await hello;
  await page.waitForTimeout(500);
  await context.route('**/api/**', (route) => route.abort());
  await page.evaluate(() => document.dispatchEvent(new Event('visibilitychange')));
}

test('offline: one note for both panes, and the list is back as it was when the connection returns', async ({ page, context }) => {
  const tag = `Offline ${stamp()}`;
  const [one] = await manyNamed(page, tag, 1);
  await goOffline(page, context, `/recipes/${one!.id}`, tag);
  const note = page.getByText('Recipes needs your Mealwright server — your shopping list works offline.');
  await expect(note).toBeVisible({ timeout: 15_000 });
  await expect(note).toHaveCount(1);
  await expect(page.getByRole('link', { name: 'Shopping', exact: true }).first()).toBeVisible();
  await expect(page.getByRole('searchbox')).toHaveCount(0);
  await expect(page.getByRole('heading', { name: 'Recipes', level: 1 })).toBeVisible();
  await checkPage(page);
  // Back online: the panes return as they were left, the search still in the box.
  await context.unroute('**/api/**');
  await page.getByRole('button', { name: 'Try now' }).first().click();
  await expect(page.getByRole('searchbox', { name: 'Search recipes' })).toHaveValue(tag);
  await expect(reading(page).getByRole('heading', { name: one!.name, level: 1 })).toBeVisible();
  await expect(note).toHaveCount(0);
});

// --- Many, long names, 200% text -------------------------------------------------------------------

const LONG = [
  'பச்சைப் பயறு (பாசிப்பயறு) முழுதாக, கரிம விவசாயிகளின் சந்தையில் வாங்கியது',
  'Organic stone-ground whole wheat flour flatbreads from the Saturday market, coarse, 5 kg bag',
];

test('very long names and the text at 200% never scroll the page sideways, and each pane scrolls on its own', async ({ page }) => {
  const tag = `Stress${stamp()}`;
  const foods: number[] = [];
  for (let i = 0; i < 6; i++) foods.push(await makeFood(page, `${tag} ${i} ${LONG[0]}`.slice(0, 100)));
  const name = `${tag} ${LONG[0]} ${LONG[1]}`.slice(0, 190);
  const recipe = await makeRecipe(page, {
    name,
    description: LONG[1],
    tags: [`${tag} ${LONG[0]}`.slice(0, 40)],
    lines: Array.from({ length: 40 }, (_, i) => ({
      words: i < 2 ? LONG[i]! : `ingredient ${i}`,
      food_id: foods[i % 6],
      amount: 10 + i,
      unit: 'g',
    })),
    steps: Array.from({ length: 30 }, (_, i) => ({
      text: i < 2 ? LONG[i]! : `Step ${i}: stir.`,
    })),
    serves: 4,
  });
  await manyNamed(page, tag, 3);
  await page.goto(`/recipes/${recipe.id}`);
  await expect(reading(page).getByRole('heading', { level: 1 })).toBeVisible();
  await search(page, tag);
  await expect(rows(page).first()).toBeVisible();
  await expectNoSidewaysScroll(page);
  await page.evaluate(() => (document.documentElement.style.fontSize = '200%'));
  await expect(reading(page).getByRole('heading', { level: 1 })).toBeVisible();
  await expectNoSidewaysScroll(page);
  const sizes = await page.evaluate(() => {
    const reader = document.querySelector('[aria-label="Recipe"]') as HTMLElement;
    const pane = document.querySelector('[aria-label="Recipe list"]') as HTMLElement;
    return {
      reader: reader.scrollHeight > reader.clientHeight,
      readerWidth: reader.clientWidth,
      listWidth: pane.clientWidth,
      page: document.scrollingElement!.scrollHeight <= innerHeight + 1,
    };
  });
  expect(sizes.reader, 'a long recipe scrolls inside the reading pane').toBe(true);
  expect(sizes.page, 'and the page itself stays still').toBe(true);
  expect(sizes.readerWidth).toBeGreaterThan(300);
});

test('reduced motion: nothing in the panes animates', async ({ page }) => {
  const [one] = await manyNamed(page, `Calm ${stamp()}`, 1);
  await page.emulateMedia({ reducedMotion: 'reduce' });
  await page.goto(`/recipes/${one!.id}`);
  await expect(reading(page).getByRole('heading', { name: one!.name, level: 1 })).toBeVisible();
  const running = await page.evaluate(
    () => document.getAnimations().filter((a) => a.playState === 'running' && (a.effect?.getTiming().duration as number) > 0.1).length,
  );
  expect(running).toBe(0);
});

test('the panes at the mockup size: two columns for the recipe when the pane is wide enough', async ({ page }) => {
  const dal = await makeFood(page, `Cols dal ${stamp()}`);
  const recipe = await makeRecipe(page, {
    name: `Cols ${stamp()}`,
    serves: 4,
    lines: [{ words: 'dal', food_id: dal, amount: 100, unit: 'g' }],
    steps: [{ text: 'Cook it.' }],
  });
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto(`/recipes/${recipe.id}`);
  const ingredients: Locator = reading(page).getByRole('region', {
    name: 'Ingredients',
  });
  const method: Locator = reading(page).getByRole('region', { name: 'Method' });
  await expect(ingredients).toBeVisible();
  const a = (await ingredients.boundingBox())!;
  const b = (await method.boundingBox())!;
  expect(b.x, 'the method sits beside the ingredients').toBeGreaterThan(a.x + a.width - 1);
  await page.setViewportSize({ width: 1100, height: 900 });
  await expect(ingredients).toBeVisible();
  const c = (await ingredients.boundingBox())!;
  const d = (await method.boundingBox())!;
  expect(d.y, 'and under them when the pane is narrower').toBeGreaterThan(c.y + c.height - 1);
});
