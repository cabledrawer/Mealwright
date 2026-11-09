import { test, expect, type Locator, type Page } from './clock.ts';
import { checkPage, isPhone, setAccountTheme } from './a11y.ts';

// The Plan (0.6, PR 3): the week and the month; drag by mouse and by finger, Alt to copy, the
// Leftovers zone, the recipe tray, the keyboard way (the menu), the phone's long-press sheet,
// Undo, the Month toggle, and the states (empty, offline). Runs on Chromium (computer and
// phone) and on WebKit (computer), see playwright.config.ts.
//
// The server's clock and household "today" are the tests' fixed day (clock.ts). Every test plans
// in a week of its own (today plus 7 × its own number), so the tests never meet each other's
// meals, and names the things it makes with a word no other test uses.
//
// Weeks ahead of today (the plan accepts 0 to 104), one block per plan spec; the next spec takes
// the free weeks 80 to 83:
//   plan-views Plan it tests 0 and 1 (today's 14 days), plan.spec.ts 2 to 34, plan-cook-once.spec.ts 35 to 64,
//   plan-views.spec.ts 65 to 79, plan-portions.spec.ts 84 to 104.

const key = () => ({ 'idempotency-key': crypto.randomUUID() });

type Write = { change: { id: number } | null; meal_id: number | null; item_id: number | null };

async function call(page: Page, method: 'POST' | 'PUT' | 'DELETE' | 'PATCH', path: string, data?: object) {
  const response = await page.request.fetch(`/api/v1${path}`, { method, data, headers: key() });
  expect(response.ok(), `${method} ${path}: ${await response.text()}`).toBe(true);
  return (await response.json()) as Record<string, any>;
}

// The three projects share one server and its data, so each plans in weeks of its own (and, in
// Month, in days of its own), and each test in a week of its own within them.
const INDEX: Record<string, number> = { 'desktop 0.6 plan': 0, 'phone 0.6 plan': 1, 'webkit 0.6 plan': 2 };
const projectIndex = () => INDEX[test.info().project.name] ?? 0;
/** A day in week `k` (1 to 11, never 0) of this project's own weeks: weeks 2 to 34 after today's (a Saturday). */
const inWeek = (today: string, k: number) => addDays(today, 7 * (1 + 11 * projectIndex() + k));

const stamp = () => `${test.info().project.name.replace(/\W/g, '')}${Date.now().toString(36)}`;

function addDays(iso: string, days: number): string {
  const d = new Date(`${iso}T12:00:00Z`);
  d.setUTCDate(d.getUTCDate() + days);
  return d.toISOString().slice(0, 10);
}

const weekday = new Intl.DateTimeFormat('en-GB', { weekday: 'long', timeZone: 'UTC' });
const month = new Intl.DateTimeFormat('en-GB', { month: 'long', timeZone: 'UTC' });
/** "Monday 19 October", the way the app names a day (never the browser's own punctuation). */
const dayName = (iso: string) => {
  const d = new Date(`${iso}T12:00:00Z`);
  return `${weekday.format(d)} ${d.getUTCDate()} ${month.format(d)}`;
};

async function setup(page: Page) {
  const household = (await (await page.request.get('/api/v1/household')).json()) as { today: string; week_starts_on: number };
  const list = (await (await page.request.get('/api/v1/meal-slots')).json()) as { id: number; name: string; enabled: boolean }[];
  const slot = Object.fromEntries(list.map((s) => [s.name, s.id])) as Record<string, number>;
  return { today: household.today, slot };
}

async function makeRecipe(page: Page, name: string) {
  return (await call(page, 'POST', '/recipes', { name })).id as number;
}

async function planned(page: Page, recipeId: number, day: string, slotId: number) {
  return (await call(page, 'POST', '/plan/items', { date: day, slot_id: slotId, recipe_id: recipeId })) as Write;
}

/**
 * The page's own API reads still in flight (fetches under /api/v1; the live stream is an
 * EventSource, not counted). WebKit reports a fetch that a navigation cuts short as a page error
 * ("… due to access control checks"), so the tests let the page finish before they leave it.
 */
const inFlight = new Set<object>();

test.beforeEach(async ({ page }) => {
  inFlight.clear();
  page.on('request', (request) => {
    if (request.resourceType() === 'fetch' && new URL(request.url()).pathname.startsWith('/api/v1/')) inFlight.add(request);
  });
  page.on('requestfinished', (request) => inFlight.delete(request));
  page.on('requestfailed', (request) => inFlight.delete(request));
});

/** Waits until the page has no API read in flight (the reads after a change: the plan, the tubs left). */
async function settled() {
  await expect.poll(() => inFlight.size, { message: 'the page finished its API reads' }).toBe(0);
}

/** Open the Plan on the week that holds `day` (the Next week button, as a person would). */
async function openWeekOf(page: Page, today: string, day: string) {
  // The plan reloads after a move (the plan, then the tubs left): going to /plan in the middle cut
  // that read short, which WebKit reports as a page error (T2a's full check, 8 Nov).
  await settled();
  await page.goto('/plan');
  const back = Math.round((new Date(`${day}T12:00:00Z`).getTime() - new Date(`${today}T12:00:00Z`).getTime()) / 86_400_000 / 7);
  for (let i = 0; i < back; i++) await page.getByRole('button', { name: 'Next week' }).click();
}

const cell = (page: Page, day: string, slotId: number) => page.getByTestId(`cell-${day}-${slotId}`);

/** The middle of a thing, or a point part-way down it (0.25 is the upper part of a place, clear of the drop zones). */
async function centre(locator: Locator, down = 0.5) {
  await locator.scrollIntoViewIfNeeded();
  const box = (await locator.boundingBox())!;
  return { x: box.x + box.width / 2, y: box.y + box.height * down };
}

/** Drag with the mouse. `zone`: hover over one of the cell's drop zones before letting go. */
async function mouseDrag(page: Page, from: Locator, to: Locator, options: { alt?: boolean; zone?: 'copy' | 'leftovers' } = {}) {
  const a = await centre(from);
  await page.mouse.move(a.x, a.y);
  await page.mouse.down();
  await page.mouse.move(a.x + 12, a.y + 12, { steps: 3 });
  if (options.alt) await page.keyboard.down('Alt');
  const b = await centre(to, 0.2);
  await page.mouse.move(b.x, b.y, { steps: 10 });
  if (options.zone) {
    const zone = to.locator(`[data-drop-zone="${options.zone}"]`);
    await expect(zone).toBeVisible();
    const z = await centre(zone);
    await page.mouse.move(z.x, z.y, { steps: 4 });
  }
  await page.mouse.up();
  if (options.alt) await page.keyboard.up('Alt');
}

/** Drag with a finger: touch pointer events. It is held still for the long press first, as a real
 *  finger would be to pick something up, then moved a step at a time. */
async function fingerDrag(from: Locator, to: Locator) {
  const a = await centre(from);
  const b = await centre(to, 0.2);
  await from.evaluate(
    async (el, p) => {
      const fire = (target: EventTarget, type: string, x: number, y: number) =>
        target.dispatchEvent(
          new PointerEvent(type, { pointerId: 7, pointerType: 'touch', isPrimary: true, clientX: x, clientY: y, bubbles: true, cancelable: true, button: 0 }),
        );
      fire(el, 'pointerdown', p.a.x, p.a.y);
      await new Promise((r) => setTimeout(r, 700));
      for (let i = 1; i <= 12; i++) {
        fire(window, 'pointermove', p.a.x + ((p.b.x - p.a.x) * i) / 12, p.a.y + ((p.b.y - p.a.y) * i) / 12);
        await new Promise((r) => setTimeout(r, 16));
      }
      fire(window, 'pointerup', p.b.x, p.b.y);
    },
    { a, b },
  );
}

/** Press and hold with a finger, for longer than a long press. */
async function fingerHold(target: Locator) {
  const a = await centre(target);
  await target.evaluate(
    async (el, p) => {
      const fire = (type: string) =>
        el.dispatchEvent(
          new PointerEvent(type, { pointerId: 8, pointerType: 'touch', isPrimary: true, clientX: p.x, clientY: p.y, bubbles: true, cancelable: true, button: 0 }),
        );
      fire('pointerdown');
      await new Promise((r) => setTimeout(r, 700));
      fire('pointerup');
    },
    a,
  );
}

const toast = (page: Page) => page.getByRole('status').filter({ hasText: /Undo|Planned|Moved|Copied|Removed|Leftovers/ });

// A script error anywhere on the page fails the test that caused it.
// The phone opens the Plan on Eat; these tests are about the cards, which are Both (0.7, P2).
test.beforeEach(async ({ page }) => {
  await page.addInitScript(() => localStorage.setItem('mealwright.plan-show', 'both'));
});

const scriptErrors: string[] = [];

test.beforeEach(async ({ page }) => {
  scriptErrors.length = 0;
  page.on('pageerror', (error) => scriptErrors.push(error.message));
  await setAccountTheme(page, 'auto');
});

test.afterEach(() => {
  expect(scriptErrors, 'the page raised no script errors').toEqual([]);
});

/** A round button is a real icon (an SVG, no letter) whose middle is the circle's middle, within 1 px (F41). */
async function expectCentredIcon(button: Locator) {
  await button.scrollIntoViewIfNeeded();
  await expect(button.locator('svg')).toHaveCount(1);
  expect(((await button.textContent()) ?? '').trim()).toBe('');
  const circle = (await button.boundingBox())!;
  const mark = (await button.locator('svg').boundingBox())!;
  expect(Math.abs(mark.x + mark.width / 2 - (circle.x + circle.width / 2))).toBeLessThanOrEqual(1);
  expect(Math.abs(mark.y + mark.height / 2 - (circle.y + circle.height / 2))).toBeLessThanOrEqual(1);
}

test('the Plan’s round buttons are real icons, centred (F41)', async ({ page }) => {
  const { today, slot } = await setup(page);
  // A meal in the week shown, so that its round + is there (an empty meal has the “+ Add” text button).
  // Taken out again at the end: the household is shared, and Today's tests expect today's
  // Dinner free (the full ./check on a6b191c).
  const item = (await planned(page, await makeRecipe(page, `Plus ${stamp()}`), today, slot.Dinner)).item_id;
  try {
    await page.goto('/plan');
    await expect(page.getByRole('heading', { level: 1, name: 'Plan' })).toBeVisible();
    await expectCentredIcon(page.getByRole('button', { name: 'Previous week' }));
    await expectCentredIcon(page.getByRole('button', { name: 'Next week' }));
    await expectCentredIcon(page.locator('button.plus').first());
    if (!isPhone(page)) {
      await expectCentredIcon(page.getByRole('button', { name: 'Collapse recipe tray' }));
      await page.getByRole('button', { name: 'Collapse recipe tray' }).click();
      await expectCentredIcon(page.getByRole('button', { name: 'Open recipe tray' }));
    }
  } finally {
    await call(page, 'DELETE', `/plan/items/${item}`);
  }
});

test.describe('on a computer', () => {
  test.beforeEach(({ page }) => {
    test.skip(isPhone(page), 'the computer’s week grid, tray and drag');
  });

  test('the week: the header, the meals that are on, the days and the tray', async ({ page }) => {
    const { today } = await setup(page);
    await page.goto('/plan');
    await expect(page.getByRole('heading', { level: 1, name: 'Plan' })).toBeVisible();
    await expect(page.getByRole('group', { name: 'View' }).getByRole('button', { name: 'Week' })).toHaveAttribute('aria-pressed', 'true');
    const meals = page.getByRole('group', { name: 'Meals to show' });
    for (const name of ['Breakfast', 'Lunch', 'Dinner']) await expect(meals.getByRole('button', { name })).toHaveAttribute('aria-pressed', 'true');
    // Snacks are off to begin with; the week starts on Monday.
    await expect(meals.getByRole('button', { name: 'Snack' })).toHaveAttribute('aria-pressed', 'false');
    const days = page.getByRole('group', { name: 'Week plan' }).getByRole('heading', { level: 3 });
    await expect(days).toHaveCount(7);
    await expect(days.first()).toContainText('MON');
    await expect(page.getByRole('region', { name: 'Recipe tray' })).toBeVisible();
    expect(today).toBe('2026-10-17');
  });

  test('drag a recipe from the tray onto a day plans it, and Undo takes it back', async ({ page }) => {
    const { today, slot } = await setup(page);
    const name = `Tray ${stamp()}`;
    await makeRecipe(page, name);
    const day = inWeek(today, 1);
    await openWeekOf(page, today, day);
    await page.getByRole('searchbox', { name: 'Find a recipe to plan' }).fill(name);
    // The search asks again 200 ms after the last key: wait for its answer, or the cards move under
    // the mouse between finding this card and pressing on it (WebKit, full check 5).
    await expect(page.getByRole('list', { name: 'Recipes to plan' }).getByRole('button').filter({ hasNotText: name })).toHaveCount(0);
    const item = page.getByRole('button', { name: `${name}. Choose a day to plan it` });
    await item.scrollIntoViewIfNeeded();
    await mouseDrag(page, item, cell(page, day, slot.Dinner));
    await expect(cell(page, day, slot.Dinner)).toContainText(name);
    await expect(page.getByRole('status').filter({ hasText: `Planned ${name}` })).toBeVisible();
    await page.getByRole('button', { name: 'Undo', exact: true }).click();
    await expect(cell(page, day, slot.Dinner)).not.toContainText(name);
  });

  test('dragging a meal moves it; Alt copies; the Leftovers zone plans leftovers; each has its Undo', async ({ page }) => {
    const { today, slot } = await setup(page);
    const name = `Drag ${stamp()}`;
    const recipe = await makeRecipe(page, name);
    const day = inWeek(today, 2);
    await planned(page, recipe, day, slot.Lunch);
    await openWeekOf(page, today, day);
    const card = () => cell(page, day, slot.Lunch).getByRole('button', { name: new RegExp(`^${name}`) }).first();
    const next = addDays(day, 1);

    // Move: Lunch on `day` → Dinner on `next`.
    await mouseDrag(page, card(), cell(page, next, slot.Dinner));
    await expect(cell(page, next, slot.Dinner)).toContainText(name);
    await expect(cell(page, day, slot.Lunch)).not.toContainText(name);
    await page.getByRole('button', { name: 'Undo', exact: true }).click();
    await expect(cell(page, day, slot.Lunch)).toContainText(name);
    await expect(cell(page, next, slot.Dinner)).not.toContainText(name);

    // Alt-drag: a copy; the first stays.
    await mouseDrag(page, card(), cell(page, next, slot.Dinner), { alt: true });
    await expect(cell(page, next, slot.Dinner)).toContainText(name);
    await expect(cell(page, day, slot.Lunch)).toContainText(name);
    await page.getByRole('button', { name: 'Undo', exact: true }).click();
    await expect(cell(page, next, slot.Dinner)).not.toContainText(name);

    // Leftovers here.
    await mouseDrag(page, card(), cell(page, next, slot.Dinner), { zone: 'leftovers' });
    await expect(cell(page, next, slot.Dinner)).toContainText(name);
    await expect(cell(page, day, slot.Lunch)).toContainText(name);
    await expect(page.getByRole('status').filter({ hasText: 'Leftovers' })).toBeVisible();
    await page.getByRole('button', { name: 'Undo', exact: true }).click();
    await expect(cell(page, next, slot.Dinner)).not.toContainText(name);
  });

  test('a short window: the bottom row\'s drop zones open where the pointer can reach them', async ({ page }) => {
    // The line's full check (8 Nov): with "Tubs left" in the tray the week box was short, and the
    // zones under the Dinner row hung below its visible edge, so dropping on "Leftovers here" did nothing.
    await page.setViewportSize({ width: 1280, height: 640 });
    const { today, slot } = await setup(page);
    const name = `Short ${stamp()}`;
    const recipe = await makeRecipe(page, name);
    const day = inWeek(today, 2);
    await planned(page, recipe, day, slot.Lunch);
    await openWeekOf(page, today, day);
    const next = addDays(day, 1);
    const target = cell(page, next, slot.Dinner);
    const a = await centre(cell(page, day, slot.Lunch).getByRole('button', { name: new RegExp(`^${name}`) }).first());
    const b = await centre(target, 0.2);
    await page.mouse.move(a.x, a.y);
    await page.mouse.down();
    await page.mouse.move(a.x + 12, a.y + 12, { steps: 3 });
    await page.mouse.move(b.x, b.y, { steps: 10 });
    const zone = target.locator('[data-drop-zone="leftovers"]');
    await expect(zone).toBeVisible();
    // No scrolling: what is under the zone's middle, where a person would let go, is the zone.
    const box = (await zone.boundingBox())!;
    const z = { x: box.x + box.width / 2, y: box.y + box.height / 2 };
    expect(await page.evaluate(({ x, y }) => document.elementFromPoint(x, y)?.closest('[data-drop-zone]')?.getAttribute('data-drop-zone') ?? null, z)).toBe('leftovers');
    await page.mouse.move(z.x, z.y, { steps: 4 });
    await expect(zone).toHaveClass(/\bon\b/);
    await page.mouse.up();
    await expect(page.getByRole('status').filter({ hasText: 'Leftovers' })).toBeVisible();
    await expect(target).toContainText(name);
  });

  // No service worker here: on WebKit, once it controls the page, page.route stops seeing its
  // requests (see import-pints.spec.ts).
  test.describe('a slow household answer', () => {
    test.use({ serviceWorkers: 'block' });

    test('the arrows and Today wait until the household’s today has come (a slow connection)', async ({ page }) => {
      // The full ./check on ae14498: “Next week” pressed before the household came threw “Invalid time value”.
      // Since F67 they aren't shown at all until then (no empty week label between ‹ ›).
      let release = () => {};
      const held = new Promise<void>((resolve) => (release = resolve));
      await page.route('**/api/v1/household', async (route) => {
        await held;
        await route.continue();
      });
      await page.goto('/plan');
      await expect(page.getByText('Loading the plan…')).toBeVisible();
      await expect(page.getByRole('button', { name: 'Next week' })).toHaveCount(0);
      await expect(page.getByRole('button', { name: 'Previous week' })).toHaveCount(0);
      await expect(page.getByRole('button', { name: 'Today', exact: true })).toHaveCount(0);
      release();
      await page.getByRole('button', { name: 'Next week' }).click();
      await expect(page.getByRole('button', { name: 'Today', exact: true })).toBeEnabled();
    });
  });

  test('dropping a meal on a filled one puts it in alongside, with “2 recipes”', async ({ page }) => {
    const { today, slot } = await setup(page);
    const one = `Alpha ${stamp()}`;
    const two = `Beta ${stamp()}`;
    const day = inWeek(today, 3);
    await planned(page, await makeRecipe(page, one), day, slot.Dinner);
    await planned(page, await makeRecipe(page, two), addDays(day, 1), slot.Dinner);
    await openWeekOf(page, today, day);
    await mouseDrag(page, cell(page, day, slot.Dinner).getByRole('button', { name: new RegExp(`^${one}`) }).first(), cell(page, addDays(day, 1), slot.Dinner));
    const target = cell(page, addDays(day, 1), slot.Dinner);
    await expect(target).toContainText(one);
    await expect(target).toContainText(two);
    await expect(target).toContainText('2 recipes');
  });

  test('a finger can drag too (touch pointer events)', async ({ page }) => {
    const { today, slot } = await setup(page);
    const name = `Finger ${stamp()}`;
    const recipe = await makeRecipe(page, name);
    const day = inWeek(today, 4);
    await planned(page, recipe, day, slot.Dinner);
    await openWeekOf(page, today, day);
    const from = cell(page, day, slot.Dinner).getByRole('button', { name: new RegExp(`^${name}`) }).first();
    await fingerDrag(from, cell(page, addDays(day, 1), slot.Lunch));
    await expect(cell(page, addDays(day, 1), slot.Lunch)).toContainText(name);
    await expect(cell(page, day, slot.Dinner)).not.toContainText(name);
    await page.getByRole('button', { name: 'Undo', exact: true }).click();
    await expect(cell(page, day, slot.Dinner)).toContainText(name);
  });

  test('the keyboard does everything a drag does: the menu, Move to…, a day, a meal', async ({ page }) => {
    const { today, slot } = await setup(page);
    const name = `Keys ${stamp()}`;
    const recipe = await makeRecipe(page, name);
    const day = inWeek(today, 5);
    await planned(page, recipe, day, slot.Dinner);
    await openWeekOf(page, today, day);
    const card = cell(page, day, slot.Dinner).getByRole('button', { name: new RegExp(`^${name}`) }).first();
    await card.focus();
    await page.keyboard.press('Enter');
    const sheet = page.getByRole('dialog', { name });
    await expect(sheet).toBeVisible();
    for (const word of ['Move to…', 'Copy to…', 'Leftovers on…', 'Remove']) await expect(sheet.getByRole('button', { name: word })).toBeVisible();
    await sheet.getByRole('button', { name: 'Move to…' }).focus();
    await page.keyboard.press('Enter');
    // The tests' day is a Saturday, so the day after (Sunday) is in the same week.
    const to = addDays(day, 1);
    await sheet.getByRole('button', { name: dayName(to) }).focus();
    await page.keyboard.press('Enter');
    await sheet.getByRole('button', { name: 'Lunch' }).focus();
    await page.keyboard.press('Enter');
    await sheet.getByRole('button', { name: 'Move here' }).focus();
    await page.keyboard.press('Enter');
    await expect(sheet).toBeHidden();
    await expect(cell(page, to, slot.Lunch)).toContainText(name);
    await expect(cell(page, day, slot.Dinner)).not.toContainText(name);

    // And a recipe from the tray, by keyboard.
    const other = `Tray keys ${stamp()}`;
    await makeRecipe(page, other);
    await openWeekOf(page, today, inWeek(today, 5));
    await page.getByRole('searchbox', { name: 'Find a recipe to plan' }).fill(other);
    // Wait for the search's answer, or the card can be redrawn between focusing it and pressing Enter.
    await expect(page.getByRole('list', { name: 'Recipes to plan' }).getByRole('button').filter({ hasNotText: other })).toHaveCount(0);
    const tray = page.getByRole('button', { name: `${other}. Choose a day to plan it` });
    await tray.focus();
    await page.keyboard.press('Enter');
    const plan = page.getByRole('dialog', { name: other });
    const on = inWeek(today, 5);
    await plan.getByRole('button', { name: dayName(on) }).click();
    await plan.getByRole('button', { name: 'Breakfast' }).click();
    await plan.getByRole('button', { name: 'Plan it here' }).click();
    await expect(cell(page, on, slot.Breakfast)).toContainText(other);
  });

  test('+ Add finds a recipe or an ingredient and puts it in the meal', async ({ page }) => {
    const { today, slot } = await setup(page);
    const name = `Add ${stamp()}`;
    await makeRecipe(page, name);
    const food = `Fruit ${stamp()}`;
    await call(page, 'POST', '/foods', { name: food, counted_as: 'count' });
    const day = inWeek(today, 6);
    await openWeekOf(page, today, day);
    await cell(page, day, slot.Lunch).getByRole('button', { name: /^Add to Lunch/ }).click();
    const add = page.getByRole('dialog', { name: 'Add to the plan' });
    await add.getByRole('searchbox', { name: 'Find a recipe or an ingredient' }).fill(name);
    await add.getByRole('button', { name: new RegExp(name) }).click();
    await expect(cell(page, day, slot.Lunch)).toContainText(name);
    // The + under a filled meal adds alongside; an ingredient goes in as a plain item.
    await cell(page, day, slot.Lunch).getByRole('button', { name: /^Add to Lunch/ }).click();
    await add.getByRole('searchbox', { name: 'Find a recipe or an ingredient' }).fill(food);
    await add.getByRole('button', { name: new RegExp(food) }).click();
    await expect(cell(page, day, slot.Lunch)).toContainText(food);
    await expect(cell(page, day, slot.Lunch)).toContainText('2 things');
  });

  test('Remove takes a meal off with a toast and Undo; Meals switches hide a row, with Undo', async ({ page }) => {
    const { today, slot } = await setup(page);
    const name = `Gone ${stamp()}`;
    const day = inWeek(today, 7);
    await planned(page, await makeRecipe(page, name), day, slot.Dinner);
    await openWeekOf(page, today, day);
    await cell(page, day, slot.Dinner).getByRole('button', { name: new RegExp(`^${name}`) }).first().click();
    await page.getByRole('dialog', { name }).getByRole('button', { name: 'Remove' }).click();
    await expect(cell(page, day, slot.Dinner)).not.toContainText(name);
    await page.getByRole('button', { name: 'Undo', exact: true }).click();
    await expect(cell(page, day, slot.Dinner)).toContainText(name);

    const dinner = page.getByRole('group', { name: 'Meals to show' }).getByRole('button', { name: 'Dinner' });
    await dinner.click();
    await expect(dinner).toHaveAttribute('aria-pressed', 'false');
    await expect(cell(page, day, slot.Dinner)).toHaveCount(0);
    await page.getByRole('button', { name: 'Undo', exact: true }).click();
    await expect(cell(page, day, slot.Dinner)).toContainText(name);
  });

  test('Month: the toggle, chips, a drag to another day, Alt-drag copy, and Undo', async ({ page }) => {
    const { today, slot } = await setup(page);
    const name = `Month ${stamp()}`;
    // This project's own days of October: the 20th, 22nd and 23rd, the 24th, 26th and 27th…
    const first = 20 + 4 * projectIndex();
    const at = (n: number) => `2026-10-${n}`;
    const day = at(first);
    const to = at(first + 2);
    const copy = at(first + 3);
    await planned(page, await makeRecipe(page, name), day, slot.Dinner);
    await page.goto('/plan');
    await page.getByRole('group', { name: 'View' }).getByRole('button', { name: 'Month' }).click();
    await expect(page.getByRole('heading', { level: 3, name: 'Batches this month' })).toBeVisible();
    await expect(page.getByRole('heading', { level: 3, name: 'Empty days ahead' })).toBeVisible();
    const chip = page.getByTestId(`day-${day}`).getByRole('button', { name: new RegExp(`^${name}`) });
    await expect(chip).toBeVisible();
    await mouseDrag(page, chip, page.getByTestId(`day-${to}`));
    await expect(page.getByTestId(`day-${to}`)).toContainText(name);
    await expect(page.getByTestId(`day-${day}`)).not.toContainText(name);
    await page.getByRole('button', { name: 'Undo', exact: true }).click();
    await expect(page.getByTestId(`day-${day}`)).toContainText(name);
    await mouseDrag(page, chip, page.getByTestId(`day-${copy}`), { alt: true });
    await expect(page.getByTestId(`day-${copy}`)).toContainText(name);
    await expect(page.getByTestId(`day-${day}`)).toContainText(name);
    expect(today).toBeTruthy();
  });

  test('an empty week says so; a long name and 200% text stay inside their cell', async ({ page }) => {
    const { today, slot } = await setup(page);
    await openWeekOf(page, today, inWeek(today, 10));
    await expect(page.getByText('Nothing planned this week.')).toBeVisible();
    const day = inWeek(today, 11);
    const name = `A very long recipe name that keeps going ${'and going '.repeat(8)}${stamp()}`;
    await planned(page, await makeRecipe(page, name.slice(0, 190)), day, slot.Dinner);
    await page.getByRole('button', { name: 'Next week' }).click();
    await page.evaluate(() => (document.documentElement.style.fontSize = '200%'));
    const where = cell(page, day, slot.Dinner);
    await expect(where).toContainText('A very long recipe name');
    const inside = await where.evaluate((el) => el.scrollWidth <= el.clientWidth + 1);
    expect(inside).toBe(true);
  });

  test('pages: no accessibility violations in light and dark; no sideways scrolling', async ({ page }) => {
    const { today, slot } = await setup(page);
    await planned(page, await makeRecipe(page, `A11y ${stamp()}`), inWeek(today, 9), slot.Dinner);
    // A busy day (5 things: three chips, "+2 more" and the number row) must pass axe in Month too (P4).
    for (const meal of [slot.Breakfast, slot.Lunch, slot.Dinner, slot.Dinner]) {
      await planned(page, await makeRecipe(page, `Busy ${stamp()}`), inWeek(today, 9), meal);
    }
    await openWeekOf(page, today, inWeek(today, 9));
    await checkPage(page);
    await page.getByRole('group', { name: 'View' }).getByRole('button', { name: 'Month' }).click();
    await expect(page.getByTestId(`day-${inWeek(today, 9)}`).getByRole('button', { name: /^\+\d+ more$/ })).toBeVisible();
    await checkPage(page);
  });

  test('offline: the plan can be read but not changed, and says why', async ({ page, context }) => {
    test.skip(test.info().project.use.browserName === 'webkit', "Playwright's WebKit offline switch blocks requests before the page sees them; see offline.spec.ts");
    const { today, slot } = await setup(page);
    await page.goto('/plan');
    await expect(cell(page, today, slot.Dinner)).toBeVisible();
    await context.setOffline(true);
    await page.getByRole('button', { name: 'Next week' }).click();
    await expect(page.getByText('You’re offline. Plan changes when you’re back online.').first()).toBeVisible({ timeout: 15_000 });
    await expect(page.getByRole('button', { name: /^Add to / }).first()).toBeDisabled();
    await context.setOffline(false);
  });
});

// Real touch scrolling, which only Chrome can do from a test (CDP's touch scroll gesture). WebKit
// is covered by what lets it scroll: the cards' touch-action (checked in the test after this
// one on every browser) and the synthetic-event test above, where a finger that moves before the
// long press plans and moves nothing.
test.describe('a finger on a computer-sized screen', () => {
  test.use({ hasTouch: true });
  test.beforeEach(({ page }) => {
    test.skip(isPhone(page), 'the computer’s layout');
  });

  test('cards let a finger scroll: touch-action allows panning, and the strip and page do scroll', async ({ page, browserName }) => {
    const { today, slot } = await setup(page);
    const stampNow = stamp();
    // Enough to fill more than the tray's two lines.
    for (let i = 0; i < 16; i++) await makeRecipe(page, `Swipe ${stampNow} ${i}`);
    const day = inWeek(today, 8);
    const name = `Swiped ${stampNow}`;
    await planned(page, await makeRecipe(page, name), day, slot.Dinner);
    await openWeekOf(page, today, day);
    const strip = page.getByRole('list', { name: 'Recipes to plan' });
    await page.getByRole('searchbox', { name: 'Find a recipe to plan' }).fill(`Swipe ${stampNow}`);
    // The search asks again 200 ms after the last key: wait for its answer, or the first card can
    // be one from before the search that is about to go.
    await expect(strip.getByRole('button').filter({ hasNotText: stampNow })).toHaveCount(0);
    const trayCard = strip.getByRole('button').first();
    await expect(trayCard).toBeVisible();
    const card = cell(page, day, slot.Dinner).getByRole('button', { name: new RegExp(`^${name}`) }).first();

    // On every browser: nothing that scrolls is switched off.
    const panning = (l: Locator) => l.evaluate((el) => getComputedStyle(el).touchAction);
    // Polled: a card that redraws can answer "" for a moment.
    await expect.poll(() => panning(trayCard)).toBe('pan-x pan-y');
    await expect.poll(() => panning(card)).toBe('pan-y');
    await expect
      .poll(() => panning(cell(page, day, slot.Dinner).getByRole('button', { name: /^1 recipe/ })))
      .toBe('pan-y');

    // A swipe before the long press (synthetic touch events) plans and moves nothing.
    await trayCard.evaluate(async (el) => {
      const r = el.getBoundingClientRect();
      const fire = (t: EventTarget, type: string, x: number) =>
        t.dispatchEvent(new PointerEvent(type, { pointerId: 9, pointerType: 'touch', isPrimary: true, clientX: x, clientY: r.top + 10, bubbles: true, cancelable: true, button: 0 }));
      fire(el, 'pointerdown', r.left + 20);
      for (let i = 1; i <= 8; i++) fire(window, 'pointermove', r.left + 20 + i * 40);
      fire(window, 'pointerup', r.left + 340);
    });
    await expect(page.getByRole('status').filter({ hasText: /^Planned/ })).toHaveCount(0);

    test.skip(browserName !== 'chromium', 'Real touch scrolling needs Chrome’s DevTools protocol; WebKit has the checks above');
    const client = await page.context().newCDPSession(page);
    // A finger drawn across the screen, as the browser itself sees it (real touch events, so it
    // scrolls or doesn't exactly as it would for a person).
    const swipe = async (from: { x: number; y: number }, dx: number, dy: number) => {
      const at = (i: number) => [{ x: from.x + (dx * i) / 10, y: from.y + (dy * i) / 10 }];
      await client.send('Input.dispatchTouchEvent', { type: 'touchStart', touchPoints: at(0) });
      for (let i = 1; i <= 10; i++) {
        await client.send('Input.dispatchTouchEvent', { type: 'touchMove', touchPoints: at(i) });
        // Kept: 16 ms is the pace of the drag's touch moves (one frame), not a wait for a state.
        await page.waitForTimeout(16);
      }
      await client.send('Input.dispatchTouchEvent', { type: 'touchEnd', touchPoints: [] });
    };

    // Up on a tray card: the strip (two lines high, F39) scrolls, nothing is planned.
    // Where a card is, asked again if the search list redraws it while it is being found (a card
    // that has just gone answers "not attached"; the next one is in the same place).
    const where = async (l: Locator) => {
      let at = { x: 0, y: 0 };
      await expect(async () => {
        at = await centre(l);
      }).toPass({ timeout: 5000 });
      return at;
    };
    const before = await strip.evaluate((el) => el.scrollTop);
    await swipe(await where(trayCard), 0, -60);
    await expect.poll(() => strip.evaluate((el) => el.scrollTop)).toBeGreaterThan(before);
    await expect(page.getByRole('status').filter({ hasText: /^Planned/ })).toHaveCount(0);

    // Up on a meal card, in a short window: the page (or the week grid) scrolls, and the meal stays.
    await page.setViewportSize({ width: 1280, height: 420 });
    const scrolled = () =>
      page.evaluate(() => (document.scrollingElement?.scrollTop ?? 0) + (document.querySelector('.week')?.scrollTop ?? 0));
    const top = await scrolled();
    await swipe(await where(card), 0, -150);
    await expect.poll(scrolled).not.toBe(top);
    await expect(cell(page, day, slot.Dinner)).toContainText(name);
    await expect(page.getByRole('status').filter({ hasText: /Moved|Copied|Leftovers/ })).toHaveCount(0);
  });
});

test.describe('on a phone', () => {
  test.beforeEach(({ page }) => {
    test.skip(!isPhone(page), 'the phone’s day list and long-press sheet');
  });

  test('the week is a list of days; long-press a meal for Move to…, Copy to…, Leftovers on…, Remove', async ({ page }) => {
    const { today, slot } = await setup(page);
    const name = `Press ${stamp()}`;
    const day = inWeek(today, 1);
    await planned(page, await makeRecipe(page, name), day, slot.Dinner);
    await openWeekOf(page, today, day);
    await expect(page.getByRole('region', { name: dayName(day) })).toBeVisible();
    const meal = page.getByRole('region', { name: dayName(day) }).getByRole('button', { name: new RegExp(`^Dinner: ${name}`) });
    await fingerHold(meal);
    const sheet = page.getByRole('dialog', { name });
    await expect(sheet).toBeVisible();
    for (const word of ['Move to…', 'Copy to…', 'Leftovers on…', 'Remove']) await expect(sheet.getByRole('button', { name: word })).toBeVisible();
    await expect(sheet.getByRole('button', { name: 'Cook once, eat for…' })).toBeVisible();
    await expect(sheet.getByRole('button', { name: /tub/i })).toHaveCount(0); // a recipe (not a tub) has no Whose tub? or To freezer
    await sheet.getByRole('button', { name: 'Copy to…' }).click();
    const to = addDays(day, 1);
    await sheet.getByRole('button', { name: dayName(to) }).click();
    await sheet.getByRole('button', { name: 'Lunch' }).click();
    await sheet.getByRole('button', { name: 'Copy here' }).click();
    await expect(page.getByRole('region', { name: dayName(to) })).toContainText(name);
    await expect(page.getByRole('region', { name: dayName(day) })).toContainText(name);
    await page.getByRole('button', { name: 'Undo', exact: true }).click();
    await expect(page.getByRole('region', { name: dayName(to) })).not.toContainText(name);
  });

  test('+ Add dinner plans a recipe; Month is a dot grid and tapping a day shows its meals', async ({ page }) => {
    const { today, slot } = await setup(page);
    const name = `Phone ${stamp()}`;
    await makeRecipe(page, name);
    const day = inWeek(today, 2);
    await openWeekOf(page, today, day);
    await page.getByRole('region', { name: dayName(day) }).getByRole('button', { name: '+ Add dinner' }).click();
    const add = page.getByRole('dialog', { name: 'Add to the plan' });
    await add.getByRole('searchbox', { name: 'Find a recipe or an ingredient' }).fill(name);
    await add.getByRole('button', { name: new RegExp(name) }).click();
    await expect(page.getByRole('region', { name: dayName(day) })).toContainText(name);

    await page.getByRole('group', { name: 'View' }).getByRole('button', { name: 'Month' }).click();
    await page.getByRole('button', { name: dayName(day), exact: true }).click();
    // The day's meals, not its cooking above them (PlanCook, `cook-<day>`): on Both that has the
    // same name once the day has any cooking (fresh too since F167), and it loads a moment later.
    const meals = page.getByRole('region', { name: dayName(day) }).and(page.locator(':not([id^="cook-"])'));
    await expect(meals).toContainText(name);
    expect(slot.Dinner).toBeTruthy();
  });

  test('pages: no accessibility violations, 44 px targets, no sideways scroll', async ({ page }) => {
    const { today, slot } = await setup(page);
    await planned(page, await makeRecipe(page, `A11y ${stamp()}`), inWeek(today, 9), slot.Dinner);
    await openWeekOf(page, today, inWeek(today, 9));
    await checkPage(page);
    await page.getByRole('group', { name: 'View' }).getByRole('button', { name: 'Month' }).click();
    await checkPage(page);
  });
});
