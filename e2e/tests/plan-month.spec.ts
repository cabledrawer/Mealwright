import { test, expect, type Locator, type Page } from './clock.ts';
import { setAccountTheme } from './a11y.ts';

// The Plan's Month and day (0.7, P4): the COOK and Today tags stay inside their day (F84), the
// month fits one screen and a full day shows 3 items then "+N more" (F47), a click anywhere in a
// day opens it (F53) and offers the meal, a recipe, a freezer tub and Cook once here (F52), and
// "Fill from freezer first" says which meals it filled and why, with one Undo.
//
// The days (all far ahead, since a batch's tubs cannot be in the past). Plan weeks 80 to 83 ahead
// are shared with plan-cards.spec.ts (computer only: Sat/Sun, Thu/Fri and, in weeks 80 to 82,
// Mon/Tue), so this spec takes only Wednesdays, and in week 83 the Monday and Tuesday too:
//   computer: A (F84) Wednesday of week 80, B (F47) week 81, D (tub, Cook once here) week 82;
//   WebKit:   A Monday of week 83, B Tuesday of week 83, D Wednesday of week 83;
//   phone:    D Wednesday of week 80 (the phone has no month grid, so no A or B).
// The click-a-day-and-pick-a-recipe test (C) plans on a day in the past (it needs no batch), in a
// week of the project's own: 9, 14 or 19 weeks back. Everything is named with a word no other
// test uses ("Moon…"). The test that mocks "Fill from freezer first" plans nothing.

const key = () => ({ 'idempotency-key': crypto.randomUUID() });

async function call(
  page: Page,
  method: 'POST' | 'PUT' | 'DELETE' | 'PATCH',
  path: string,
  data?: object
) {
  const response = await page.request.fetch(`/api/v1${path}`, {
    method,
    data,
    headers: key()
  });
  expect(response.ok(), `${method} ${path}: ${await response.text()}`).toBe(true);
  return (await response.json()) as Record<string, any>;
}

function addDays(iso: string, days: number): string {
  const d = new Date(`${iso}T12:00:00Z`);
  d.setUTCDate(d.getUTCDate() + days);
  return d.toISOString().slice(0, 10);
}

type Which = 'A' | 'B' | 'C' | 'D' | 'T';
const kind = () => {
  const name = test.info().project.name;
  return name.startsWith('phone') ? 'phone' : name.startsWith('webkit') ? 'webkit' : 'computer';
};
/** The test's own day. Today is a Saturday, so today + 7 × weeks is one too; Wednesday is 3 before. */
function dayFor(today: string, which: Which): string {
  const wed = (week: number) => addDays(today, 7 * week - 3);
  if (which === 'T') return addDays(today, -7 * { computer: 10, webkit: 25, phone: 40 }[kind()]);
  if (which === 'C') return addDays(today, -7 * { computer: 9, webkit: 14, phone: 19 }[kind()] + 1);
  if (kind() === 'computer') return wed({ A: 80, B: 81, D: 82 }[which]);
  if (kind() === 'webkit') return addDays(wed(83), { A: -2, B: -1, D: 0 }[which]);
  return wed(80);
}

const stamp = () => `Moon${kind()}${Date.now().toString(36)}`;

async function setup(page: Page) {
  const household = (await (await page.request.get('/api/v1/household')).json()) as {
    today: string;
  };
  const list = (await (await page.request.get('/api/v1/meal-slots')).json()) as {
    id: number;
    name: string;
  }[];
  const slot = Object.fromEntries(list.map((s) => [s.name, s.id])) as Record<string, number>;
  await call(page, 'PATCH', `/meal-slots/${slot.Snack}`, { enabled: true });
  return { today: household.today, slot };
}

const makeRecipe = async (page: Page, name: string) =>
  (await call(page, 'POST', '/recipes', { name })).id as number;
const planned = async (page: Page, recipeId: number, day: string, slotId: number) =>
  (await call(page, 'POST', '/plan/items', {
    date: day,
    slot_id: slotId,
    recipe_id: recipeId
  })) as {
    item_id: number;
    meal_id: number;
  };

/** A batch cooked on `day` at dinner, its one tub in no meal (so no other day gets anything). */
async function cookedOnce(page: Page, name: string, day: string, slot: Record<string, number>) {
  const cook = await planned(page, await makeRecipe(page, name), day, slot.Dinner);
  await call(page, 'POST', `/plan/items/${cook.item_id}/batch`, {
    tub_count: 1,
    pattern: 'pick',
    placements: [null]
  });
  return cook;
}

/** The first day of the next month that has six weeks on the Month (weeks start on Monday). */
function sixWeekMonth(today: string): string {
  let [year, month] = [Number(today.slice(0, 4)), Number(today.slice(5, 7))];
  for (let i = 0; i < 24; i++) {
    month++;
    if (month > 12) [year, month] = [year + 1, 1];
    const first = new Date(Date.UTC(year, month - 1, 1));
    const lead = (first.getUTCDay() + 6) % 7;
    const length = new Date(Date.UTC(year, month, 0)).getUTCDate();
    if (Math.ceil((lead + length) / 7) === 6) return first.toISOString().slice(0, 10);
  }
  throw new Error('no six-week month in two years');
}

/** Month, on the month that holds `day`. */
async function openMonthOf(page: Page, today: string, day: string) {
  await page.goto('/plan');
  await page.getByRole('group', { name: 'View' }).getByRole('button', { name: 'Month' }).click();
  const months = (iso: string) => Number(iso.slice(0, 4)) * 12 + Number(iso.slice(5, 7));
  const steps = months(day) - months(today);
  for (let i = 0; i < Math.abs(steps); i++) {
    await page
      .getByRole('button', {
        name: steps > 0 ? 'Next month' : 'Previous month'
      })
      .click();
  }
}

const inside = async (inner: Locator, outer: Locator) => {
  const [a, b] = [await inner.boundingBox(), await outer.boundingBox()];
  expect(a, 'inner box').not.toBeNull();
  expect(b, 'outer box').not.toBeNull();
  const slack = 0.5;
  return (
    a!.x >= b!.x - slack &&
    a!.y >= b!.y - slack &&
    a!.x + a!.width <= b!.x + b!.width + slack &&
    a!.y + a!.height <= b!.y + b!.height + slack
  );
};

const weekday = new Intl.DateTimeFormat('en-GB', { weekday: 'long', timeZone: 'UTC' });
const monthName = new Intl.DateTimeFormat('en-GB', { month: 'long', timeZone: 'UTC' });
/** "Wednesday 19 October", the way the app names a day (never the browser's own punctuation). */
const dayName = (iso: string) => {
  const d = new Date(`${iso}T12:00:00Z`);
  return `${weekday.format(d)} ${d.getUTCDate()} ${monthName.format(d)}`;
};

/** A batch cooked on `day` (in the past) whose tubs are in no meal: in the freezer, or left in the fridge. */
async function pastBatch(
  page: Page,
  name: string,
  day: string,
  slot: Record<string, number>,
  where: 'freezer' | 'fridge'
) {
  const cook = await planned(page, await makeRecipe(page, name), day, slot.Dinner);
  await call(page, 'POST', `/plan/items/${cook.item_id}/batch`, {
    tub_count: 2,
    pattern: 'pick',
    placements: [null, null],
    extras_to_freezer: where === 'freezer'
  });
}

/**
 * Open a day and its "Add to the plan" sheet, the way this layout does: on a computer a click
 * anywhere in the day (not on its number or a chip), on a phone a tap on the day in the dot grid
 * and then "+ Add <meal>" under it. `meal` is the one to put things in.
 */
async function openDay(page: Page, today: string, day: string, meal: string) {
  await openMonthOf(page, today, day);
  if (kind() === 'phone') {
    await page
      .getByRole('group', { name: 'Days' })
      .getByRole('button', { name: dayName(day), exact: true })
      .click();
    await page
      .getByRole('region', { name: dayName(day) })
      .getByRole('button', { name: `+ Add ${meal.toLowerCase()}` })
      .click();
    return page.getByRole('dialog', { name: 'Add to the plan' });
  }
  const where = page.getByTestId(`day-${day}`);
  await expect(where).toBeVisible();
  const box = (await where.boundingBox())!;
  await page.mouse.click(box.x + box.width - 5, box.y + box.height - 5); // the corner: no number, no chip
  const add = page.getByRole('dialog', { name: 'Add to the plan' });
  await expect(add.getByRole('heading', { level: 2 })).toHaveText(`a meal · ${dayName(day)}`);
  await add
    .getByRole('group', { name: 'Meal' })
    .getByRole('button', { name: meal, exact: true })
    .click();
  return add;
}

test.beforeEach(async ({ page }) => {
  await page.addInitScript(() => localStorage.setItem('mealwright.plan-show', 'both'));
  await setAccountTheme(page, 'auto');
});

test('F53: a click anywhere in a day opens it, and a meal and a recipe plan it (the phone taps the day, then + Add)', async ({
  page
}) => {
  const { today } = await setup(page);
  const day = dayFor(today, 'C');
  const name = `${stamp()} Pancakes`;
  await makeRecipe(page, name);
  const add = await openDay(page, today, day, 'Lunch');
  await add.getByRole('searchbox', { name: 'Find a recipe or an ingredient' }).fill(name);
  await add.getByRole('button', { name: new RegExp(`^${name}`) }).click();
  if (kind() === 'phone')
    await expect(page.getByRole('region', { name: dayName(day) })).toContainText(name);
  else await expect(page.getByTestId(`day-${day}`)).toContainText(name);
});

test('F52: the day offers the oldest freezer tub first, leaves out a fridge tub past its use-by, and puts a tub in the meal', async ({
  page
}) => {
  const { today, slot } = await setup(page);
  const day = dayFor(today, 'T');
  const word = stamp();
  // The batches were cooked in the weeks before the day (a freezer tub lasts three months, a fridge
  // tub three days), so the first two are in the freezer, the oldest first, and the third is long past.
  await pastBatch(page, `${word} Oldest`, addDays(day, -14), slot, 'freezer');
  await pastBatch(page, `${word} Newer`, addDays(day, -7), slot, 'freezer');
  await pastBatch(page, `${word} Stale`, addDays(day, -21), slot, 'fridge');
  await pastBatch(page, `${word} Fresh`, addDays(day, -1), slot, 'fridge');

  const add = await openDay(page, today, day, 'Lunch');
  const tubs = add.getByRole('list', { name: 'Tubs left' });
  await expect(add.getByRole('heading', { level: 3, name: 'Use a tub' })).toBeVisible();
  // Tubs of other tests may be in the list too; these four are the oldest, so they come first.
  const rows = tubs.getByRole('listitem').filter({ hasText: word });
  await expect(rows.nth(0)).toContainText(`${word} Oldest · tub 1 of 2`);
  await expect(rows.nth(1)).toContainText(`${word} Oldest · tub 2 of 2`);
  await expect(rows.nth(2)).toContainText(`${word} Newer · tub 1 of 2`);
  await expect(rows.nth(0)).toContainText('Freezer');
  await expect(tubs).not.toContainText(`${word} Stale`);
  await expect(
    add.getByText('Fridge tubs that are past their use-by by then aren’t offered.')
  ).toBeVisible();

  await rows.nth(0).getByRole('button').click();
  const planned = page
    .getByRole('status')
    .filter({ hasText: new RegExp(`Put .*${word} Oldest.* in Lunch`) });
  await expect(planned).toBeVisible();
  await expect
    .poll(async () => {
      const plan = (await (
        await page.request.get(`/api/v1/plan?from=${day}&to=${day}`)
      ).json()) as {
        meals: { slot_id: number; items: { kind: string }[] }[];
      };
      return plan.meals.find((m) => m.slot_id === slot.Lunch)?.items.map((i) => i.kind);
    })
    .toEqual(['tub']);
});

test('F52: "Cook once here…" plans the recipe in the meal and opens Cook once, eat for…', async ({
  page
}) => {
  const { today, slot } = await setup(page);
  const day = dayFor(today, 'D');
  const name = `${stamp()} Pongal`;
  await makeRecipe(page, name);
  const add = await openDay(page, today, day, 'Breakfast');
  await add.getByRole('button', { name: 'Cook once here…' }).click();
  await expect(add.getByText('Pick the recipe to cook once here.')).toBeVisible();
  await expect(add.getByRole('list', { name: 'Tubs left' })).toHaveCount(0);
  await add.getByRole('searchbox', { name: 'Find a recipe or an ingredient' }).fill(name);
  await add.getByRole('button', { name: new RegExp(`^${name}`) }).click();
  const cook = page.getByRole('dialog', { name: 'Cook once, eat for…' });
  await expect(cook).toBeVisible();
  await expect(cook).toContainText(name);
  const meals = (await (await page.request.get(`/api/v1/plan?from=${day}&to=${day}`)).json()) as {
    meals: { slot_id: number; items: { recipe: { name: string } | null }[] }[];
  };
  expect(
    meals.meals.find((m) => m.slot_id === slot.Breakfast)?.items.map((i) => i.recipe?.name)
  ).toContain(name);
});

test('F47: at 1024×768 the month and the day beside it fit one screen with six weeks', async ({
  page
}) => {
  test.skip(kind() === 'phone', 'a phone is narrower than a tablet');
  await page.setViewportSize({ width: 1024, height: 768 });
  const { today } = await setup(page);
  const first = sixWeekMonth(today);
  await openMonthOf(page, today, first);
  const grid = page.getByRole('group', { name: 'Days' });
  await expect(grid.getByRole('button')).toHaveCount(42);
  const room = await page.evaluate(() => ({
    pageScroll: document.documentElement.scrollHeight - innerHeight,
    height: innerHeight
  }));
  expect(room.pageScroll).toBeLessThanOrEqual(0);
  const last = (await grid.getByRole('button').last().boundingBox())!;
  expect(last.y + last.height).toBeLessThanOrEqual(room.height);
});

test.describe('on a computer', () => {
  test.skip(() => kind() === 'phone', 'the month grid is the computer’s');

  for (const width of [1280, 1100]) {
    test(`F84: the COOK and Today tags stay inside their own day at ${width} px`, async ({
      page
    }) => {
      await page.setViewportSize({ width, height: 800 });
      const { today, slot } = await setup(page);
      const day = dayFor(today, 'A');
      await cookedOnce(page, `${stamp()} Curry`, day, slot);

      await openMonthOf(page, today, day);
      const cooking = page.getByTestId(`day-${day}`);
      await expect(cooking.getByText('COOK', { exact: true })).toBeVisible();
      expect(await inside(cooking.getByText('COOK', { exact: true }), cooking)).toBe(true);
      expect(await inside(cooking.getByRole('button', { name: /^Add to / }), cooking)).toBe(true);

      await page.getByRole('button', { name: 'Today', exact: true }).click();
      const here = page.getByTestId(`day-${today}`);
      await expect(here.getByText('Today', { exact: true })).toBeVisible();
      expect(await inside(here.getByText('Today', { exact: true }), here)).toBe(true);
    });
  }

  test('F47: the month fits one screen at 1280×800 with six weeks, and a short day never spills', async ({
    page
  }) => {
    await page.setViewportSize({ width: 1280, height: 800 });
    const { today } = await setup(page);
    const first = sixWeekMonth(today);
    await openMonthOf(page, today, first);
    await expect(page.getByTestId(`day-${first}`)).toBeVisible();
    expect(await page.getByTestId(/^day-/).count()).toBe(42);
    const room = await page.evaluate(() => {
      const cells = [...document.querySelectorAll<HTMLElement>('[data-testid^="day-"]')];
      return {
        pageScroll: document.documentElement.scrollHeight - innerHeight,
        lastBottom: cells.at(-1)!.getBoundingClientRect().bottom,
        height: innerHeight,
        clipped: cells.filter((c) => c.scrollHeight > c.clientHeight + 1).length
      };
    });
    expect(room.pageScroll).toBeLessThanOrEqual(0);
    expect(room.lastBottom).toBeLessThanOrEqual(room.height);
    expect(room.clipped).toBe(0);
  });

  test('F47: a day of five things shows three and "+2 more", the cooking first', async ({
    page
  }) => {
    await page.setViewportSize({ width: 1280, height: 1000 });
    const { today, slot } = await setup(page);
    const day = dayFor(today, 'B');
    const word = stamp();
    await cookedOnce(page, `${word} Curry`, day, slot);
    await planned(page, await makeRecipe(page, `${word} Porridge`), day, slot.Breakfast);
    await planned(page, await makeRecipe(page, `${word} Salad`), day, slot.Lunch);
    await planned(page, await makeRecipe(page, `${word} Soup`), day, slot.Lunch);
    await planned(page, await makeRecipe(page, `${word} Fruit`), day, slot.Snack);

    await openMonthOf(page, today, day);
    const where = page.getByTestId(`day-${day}`);
    const chips = where.getByRole('button', { name: /Open menu$/ });
    await expect(chips).toHaveCount(3);
    // The cooking is first although dinner comes after breakfast and lunch.
    await expect(chips.nth(0)).toContainText(`${word} Curry`);
    await expect(chips.nth(1)).toContainText(`${word} Porridge`);
    await expect(chips.nth(2)).toContainText(`${word} Salad`);
    await where.getByRole('button', { name: '+2 more' }).click();
    const sheet = page.getByRole('dialog', { name: /^(Wednesday|Monday|Tuesday)/ });
    await expect(sheet).toContainText(`${word} Fruit`);
    expect(await inside(where.getByRole('button', { name: '+2 more' }), where)).toBe(true);
  });

  test('"Fill from freezer first" says which meals it filled and why, with one Undo', async ({
    page
  }) => {
    const { today, slot } = await setup(page);
    const day = dayFor(today, 'D');
    // A tub in the freezer, so the button is on (the fill itself is answered by the test, below:
    // the real one would put tubs on other tests' empty days).
    await pastBatch(page, `${stamp()} Freezer`, addDays(dayFor(today, 'T'), -28), slot, 'freezer');
    const summary = 'Filled Tue dinner, Thu lunch from freezer tubs (they run out soonest)';
    const change = {
      id: 999_999,
      kind: 'plan_tub',
      at: '2026-10-17T09:00:00Z',
      who: { login_id: 1, name: 'Test' },
      summary,
      can_undo: true,
      undo_until: null,
      undone: null
    };
    await page.route('**/api/v1/plan/fill-from-freezer', (route) =>
      route.fulfill({ json: { change, meal_id: null, item_id: null } })
    );
    let undone = 0;
    await page.route('**/api/v1/changes/999999/undo', (route) => {
      undone++;
      return route.fulfill({
        json: { result: 'done', message: '', change, undone: change, food: null, brought_back: [] }
      });
    });
    await openMonthOf(page, today, day);
    await page.getByRole('button', { name: 'Fill from freezer first' }).click();
    const toast = page.getByRole('status').filter({ hasText: summary });
    await expect(toast).toBeVisible();
    await expect(toast.getByRole('button', { name: 'Undo', exact: true })).toHaveCount(1);
    await toast.getByRole('button', { name: 'Undo', exact: true }).click();
    await expect.poll(() => undone).toBe(1);
  });
});
