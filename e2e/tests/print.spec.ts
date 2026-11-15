import { writeFileSync } from 'node:fs';
import { inflateSync } from 'node:zlib';
import { test, expect, type Page } from './clock.ts';
import { isPhone, setAccountTheme } from './a11y.ts';
import { uploadPhoto } from '../review/photos.ts';

// The print layouts (0.9.5 step 12; docs/spec.md "Print", cabledrawer 13 Nov; mockups
// Print-ShoppingList095-A4 and Print-Recipe095-A4, proposed): with the print media on, the page
// is a light A4 sheet whatever the theme, with none of the app around it; the shopping list is
// what is still to buy, a recipe has no photo. Runs on the phone and the computer (and
// WebKit); the PDF checks run on Chromium only. PRINT_SHOTS=<folder> also saves the PDFs.

const key = () => ({ 'idempotency-key': crypto.randomUUID() });
const unique = (word: string) =>
  `${word} ${test.info().project.name.replace(/\W/g, '')}${Date.now().toString(36)}`;

async function call(page: Page, method: 'POST' | 'PUT', path: string, data: object) {
  const response = await page.request.fetch(`/api/v1${path}`, { method, data, headers: key() });
  expect(response.ok(), `${method} ${path}: ${await response.text()}`).toBe(true);
  return (await response.json()) as Record<string, any>;
}

async function mainList(page: Page): Promise<string> {
  const { lists } = await (await page.request.get('/api/v1/shopping/lists')).json();
  return lists.find((l: { main: boolean }) => l.main).id;
}

async function onList(page: Page, name: string, amountG = 500) {
  const { food } = await call(page, 'POST', '/foods', { name, counted_as: 'weight' });
  await call(page, 'POST', `/shopping/lists/${await mainList(page)}/items`, {
    food_id: food.id,
    amount: { amount: amountG, unit: 'g' }
  });
}

const sheet = (page: Page) => page.locator('[data-print-sheet]');

async function toPrint(page: Page) {
  await page.emulateMedia({ media: 'print' });
}

/** Black ink on white: the page and the sheet, whatever the theme. */
async function expectLight(page: Page, selector: string) {
  const colours = await page.evaluate((s) => {
    const el = document.querySelector(s)!;
    return {
      page: getComputedStyle(document.body).backgroundColor,
      ink: getComputedStyle(el).color,
      paper: getComputedStyle(document.documentElement).backgroundColor
    };
  }, selector);
  expect(colours.page).toBe('rgb(255, 255, 255)');
  expect(colours.paper).toBe('rgb(255, 255, 255)');
  expect(colours.ink).toBe('rgb(26, 31, 28)');
}

/** The pages of a PDF (Chromium): each page is one "/Type /Page" object. */
const pagesOf = (pdf: Buffer) => (pdf.toString('latin1').match(/\/Type\s*\/Page[^s]/g) ?? []).length;

/** The pages of a PDF (Chromium) that have any writing on them: Skia draws a page as one compressed stream. */
function pagesWithText(pdf: Buffer): number {
  const raw = pdf.toString('latin1');
  let found = 0;
  for (const m of raw.matchAll(/stream\r?\n/g)) {
    const start = m.index! + m[0].length;
    const end = raw.indexOf('endstream', start);
    try {
      const text = inflateSync(pdf.subarray(start, end)).toString('latin1');
      if (/\bBT\b/.test(text) && /\bT[jJ]\b/.test(text)) found++;
    } catch {
      /* not a compressed content stream (a font, an image) */
    }
  }
  return found;
}

function keep(name: string, pdf: Buffer) {
  if (process.env.PRINT_SHOTS) writeFileSync(`${process.env.PRINT_SHOTS}/${name}.pdf`, pdf);
}

test.afterEach(async ({ page }) => {
  await page.emulateMedia({ media: null });
  await setAccountTheme(page, 'auto');
});

for (const theme of ['light', 'dark'] as const) {
  test(`Shopping list on paper, ${theme} theme: only the sheet, in dark ink on white, no app around it`, async ({ page }) => {
    await setAccountTheme(page, theme);
    const name = unique('Onions');
    await onList(page, name);
    await page.goto('/shopping');
    await expect(page.getByRole('button', { name: new RegExp(`^Change amount: ${name}`) })).toBeVisible();
    await toPrint(page);
    await expect(sheet(page)).toBeVisible();
    await expect(sheet(page).getByRole('heading', { level: 1 })).toContainText('Shopping list');
    await expect(sheet(page).getByRole('cell', { name })).toBeVisible();
    await expect(sheet(page).locator('td.box span').first()).toBeVisible();
    await expect(sheet(page)).toContainText('Printed from Mealwright. Ticks on paper stay on paper');
    // Nothing of the app: no sidebar, tabs, buttons, add box or toast.
    await expect(page.locator('.sidebar-slot')).toBeHidden();
    await expect(page.locator('.tabbar-slot')).toBeHidden();
    await expect(page.getByRole('button', { name: new RegExp(`^Change amount: ${name}`) })).toBeHidden();
    await expect(page.getByRole('searchbox')).toBeHidden();
    await expectLight(page, '[data-print-sheet]');
    // And back on the screen when printing is over.
    await page.emulateMedia({ media: 'screen' });
    await expect(sheet(page)).toHaveCount(0);
  });
}

test('Shopping list on paper leaves out what is in the trolley', async ({ page }) => {
  const kept = unique('Kept');
  const ticked = unique('Ticked');
  await onList(page, kept);
  await onList(page, ticked);
  await page.goto('/shopping');
  await page.getByRole('checkbox', { name: new RegExp(`^Tick ${ticked}`) }).check({ force: true });
  await expect(page.getByRole('button', { name: new RegExp(`^Change amount: ${ticked}`) })).toBeHidden();
  await toPrint(page);
  await expect(sheet(page).getByRole('cell', { name: kept })).toBeVisible();
  await expect(sheet(page)).not.toContainText(ticked);
});

test('A long shopping list flows on to more pages, and a line never splits', async ({ page, browserName }) => {
  test.skip(browserName !== 'chromium', 'page.pdf() is Chromium only');
  const tag = unique('Long');
  for (let i = 0; i < 45; i++) await onList(page, `${tag} ${String(i).padStart(2, '0')}`);
  await page.goto('/shopping');
  await expect(page.getByText(`${tag} 44`).first()).toBeVisible();
  await toPrint(page);
  await expect(sheet(page)).toBeVisible();
  const pdf = await page.pdf({ format: 'A4', preferCSSPageSize: true });
  expect(pagesOf(pdf)).toBeGreaterThan(1);
  keep(`shopping-long-${test.info().project.name.replace(/\W/g, '-')}`, pdf);
  // Every line is one row that may not break across pages.
  const rows = await sheet(page).locator('tr').evaluateAll((trs) => trs.map((t) => getComputedStyle(t).breakInside));
  expect(rows.length).toBeGreaterThan(40);
  expect(new Set(rows)).toEqual(new Set(['avoid']));
  // A heading never sits alone at the foot of a page.
  const heads = await sheet(page).locator('h2, h3').evaluateAll((hs) => hs.map((h) => getComputedStyle(h).breakAfter));
  expect(new Set(heads)).toEqual(new Set(['avoid']));
});

test('Shopping list on paper: no blank page after the list, wherever the list ends on the page', async ({ page, browserName }) => {
  test.skip(browserName !== 'chromium', 'page.pdf() is Chromium only');
  // F235 (hand test, 15 Nov): Chrome showed an empty last page. Three shops, so the sheet has shop
  // and aisle headings, and the list is nudged down a few pixels at a time so its end crosses the
  // foot of the first page.
  const ids: number[] = [];
  for (const word of ['Alpha', 'Beta', 'Gamma']) ids.push((await call(page, 'POST', '/shops', { name: unique(word) })).id);
  const list = await mainList(page);
  for (let i = 0; i < 11; i++) {
    const { food } = await call(page, 'POST', '/foods', { name: unique(`Item${i}`), counted_as: 'weight', shop_id: ids[i % 3] });
    await call(page, 'POST', `/shopping/lists/${list}/items`, { food_id: food.id, amount: { amount: 500, unit: 'g' } });
  }
  await page.setViewportSize({ width: 650, height: 979 });
  await page.goto('/shopping');
  await toPrint(page);
  await expect(sheet(page)).toBeVisible();
  // Nothing but the sheet takes any room on the printed page.
  const rooms = await page.evaluate(() =>
    [...document.body.querySelectorAll('*')]
      .filter((el) => !el.closest('[data-print-sheet]') && !el.contains(document.querySelector('[data-print-sheet]')))
      .filter((el) => {
        const css = getComputedStyle(el);
        if (css.display === 'none' || el.getClientRects().length === 0) return false;
        // Room in the flow, or taken out of it but still on the page (it can still add a page).
        return el.getBoundingClientRect().height > 1 || css.position === 'absolute' || css.position === 'fixed';
      })
      .map((el) => `${el.tagName}.${el.getAttribute('class')} ${getComputedStyle(el).position} ${el.outerHTML.slice(0, 120)}`)
  );
  expect(rooms).toEqual([]);
  const blank: string[] = [];
  for (let nudge = 0; nudge < 120; nudge += 6) {
    await sheet(page).evaluate((e, px) => ((e.querySelector('.meta') as HTMLElement).style.marginTop = `${px}px`), nudge);
    const pdf = await page.pdf({ format: 'A4', preferCSSPageSize: true });
    if (pagesOf(pdf) !== pagesWithText(pdf)) blank.push(`nudge ${nudge}: ${pagesOf(pdf)} pages, ${pagesWithText(pdf)} with writing`);
  }
  expect(blank).toEqual([]);
});

async function recipeWithPhoto(page: Page, name: string) {
  const photo = await uploadPhoto(page.request, 'dish');
  // Lines tied to ingredients that are not in the pantry, so the screen shows "N missing".
  const rice = (await call(page, 'POST', '/foods', { name: unique('Basmati'), counted_as: 'weight' })).food.id;
  const nuts = (await call(page, 'POST', '/foods', { name: unique('Peanuts'), counted_as: 'weight' })).food.id;
  const line = (words: string, food_id: number, amount: number, unit: string) => ({ words, food_id, amount, unit });
  return call(page, 'POST', '/recipes', {
    name,
    description: 'Yellow, sharp and quick.',
    serves: 4,
    time_minutes: 20,
    nutrition: { kcal: 410, protein: 9, carbs: 62, fat: 14 },
    lines: [line('cooked basmati rice', rice, 600, 'g'), line('peanuts', nuts, 40, 'g'), { words: 'salt' }],
    steps: [{ text: 'Spread the cooked rice on a tray to cool.' }, { text: 'Heat the oil in a wide pan.' }],
    photo_id: photo
  });
}

for (const theme of ['light', 'dark'] as const) {
  test(`A recipe on paper, ${theme} theme: no photo, no buttons, servings as chosen, ingredients and method`, async ({ page }) => {
    await setAccountTheme(page, theme);
    const recipe = await recipeWithPhoto(page, unique('Lemon rice'));
    await page.goto(`/recipes/${recipe.id}`);
    const photo = page.getByRole('img', { name: /^Photo of/ });
    await expect(photo.first()).toBeVisible();
    // More servings first: the paper has what the screen shows.
    await page.getByRole('button', { name: 'More servings' }).click();
    await expect(page.getByText('Serves 5')).toBeVisible();
    // On the screen the ingredients are not in the pantry, so "N missing" and its button show.
    await expect(page.locator('article.recipe').getByText(/^\d+ missing$/).first()).toBeVisible();
    await expect(page.getByRole('button', { name: 'Add to the list' })).toBeVisible();
    await toPrint(page);
    await expect(page.getByRole('heading', { level: 1, name: recipe.name })).toBeVisible();
    await expect(page.getByText('Serves 5')).toBeVisible();
    // F236: a screen-only control never prints (the missing bar, the nutrition link, any button).
    await expect(page.locator('article.recipe').getByText(/^\d+ missing$/).first()).toBeHidden();
    await expect(page.getByRole('button', { name: 'Add to the list' })).toBeHidden();
    await expect(page.locator('article.recipe button:visible:not(.line)')).toHaveCount(0);
    await expect(page.getByRole('heading', { name: 'Ingredients' })).toBeVisible();
    await expect(page.getByRole('heading', { name: 'Method' })).toBeVisible();
    await expect(page.getByText('Spread the cooked rice on a tray to cool.')).toBeVisible();
    await expect(page.getByText('Yellow, sharp and quick.')).toBeVisible();
    await expect(photo).toHaveCount(0);
    await expect(page.locator('img:visible')).toHaveCount(0);
    for (const button of ['Cook now', 'Plan it', 'More servings', 'Fewer servings']) {
      await expect(page.getByRole('button', { name: button }).or(page.getByRole('link', { name: button }))).toBeHidden();
    }
    await expect(page.locator('.sidebar-slot')).toBeHidden();
    await expect(page.locator('.tabbar-slot')).toBeHidden();
    await expect(page.getByText('From Mealwright · amounts for 5 · photo left off to save ink')).toBeVisible();
    await expectLight(page, 'h1');
  });
}

test('A recipe in three panes prints without the recipe list and fits more than a window', async ({ page, browserName }) => {
  test.skip(isPhone(page), 'three panes are the computer’s');
  const recipe = await recipeWithPhoto(page, unique('Panes rice'));
  await page.goto(`/recipes/${recipe.id}`);
  await expect(page.getByRole('region', { name: 'Recipe', exact: true })).toBeVisible();
  await toPrint(page);
  await expect(page.getByRole('searchbox', { name: 'Search recipes' })).toBeHidden();
  await expect(page.getByRole('heading', { level: 1, name: recipe.name })).toBeVisible();
  if (browserName === 'chromium') {
    const pdf = await page.pdf({ format: 'A4', preferCSSPageSize: true });
    expect(pagesOf(pdf)).toBe(1);
    keep('recipe-short', pdf);
  }
});

test('A long recipe flows on to a second page; no step is split', async ({ page, browserName }) => {
  test.skip(browserName !== 'chromium', 'page.pdf() is Chromium only');
  const steps = Array.from({ length: 30 }, (_, i) => ({
    text: `Step ${i + 1}: stir the pan slowly and keep going until the mixture is glossy and the grains are separate, then rest it.`
  }));
  const recipe = await call(page, 'POST', '/recipes', { name: unique('Long recipe'), serves: 4, steps });
  await page.goto(`/recipes/${recipe.id}`);
  await toPrint(page);
  await expect(page.getByText('Step 30:')).toBeVisible();
  const pdf = await page.pdf({ format: 'A4', preferCSSPageSize: true });
  expect(pagesOf(pdf)).toBeGreaterThan(1);
  keep(`recipe-long-${test.info().project.name.replace(/\W/g, '-')}`, pdf);
  const breaks = await page.locator('.method li').evaluateAll((li) => li.map((e) => getComputedStyle(e).breakInside));
  expect(new Set(breaks)).toEqual(new Set(['avoid']));
});

for (const path of ['/plan', '/pantry', '/recipes']) {
  test(`${path} printed from the dark theme has dark text on white (every page, not only the two layouts)`, async ({ page }) => {
    await setAccountTheme(page, 'dark');
    await page.goto(path);
    await expect(page.locator('main')).toBeVisible();
    await toPrint(page);
    const seen = await page.evaluate(() => {
      const root = getComputedStyle(document.documentElement);
      const heading = document.querySelector('main h1, main h2') as HTMLElement | null;
      return {
        paper: getComputedStyle(document.body).backgroundColor,
        text: root.getPropertyValue('--color-text').trim(),
        ground: root.getPropertyValue('--color-ground').trim(),
        heading: heading ? getComputedStyle(heading).color : null
      };
    });
    expect(seen.paper).toBe('rgb(255, 255, 255)');
    // The light theme's colours, though the screen is dark.
    expect(seen.text).toBe('#17201c');
    expect(seen.ground).toBe('#f5f6f4');
    if (seen.heading) {
      const [r, g, b] = seen.heading.match(/\d+/g)!.map(Number);
      expect(r! + g! + b!).toBeLessThan(300);
    }
    await expect(page.locator('.sidebar-slot')).toBeHidden();
    await expect(page.locator('.tabbar-slot')).toBeHidden();
  });
}
