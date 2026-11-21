import { test, expect, type Locator, type Page } from './clock.ts';
import { expectNoSidewaysScroll, inTheme, setAccountTheme } from './a11y.ts';
import { addDays, call, key, type SlotIds } from './helpers.ts';

// The Plan's Month and day (0.7, P4): the COOK and Today tags stay inside their day (F84), the
// month scrolls rather than squeeze a day, which shows 3 items then "+N more" (F47), a click anywhere in a
// day opens it (F53) and offers the meal, a recipe, a freezer tub and Cook once here (F52), and
// "Fill from freezer first" says which meals it filled and why, with one Undo.
//
// The days (all far ahead, since a batch's tubs cannot be in the past). Plan weeks 80 to 83 ahead
// are shared with plan-cards.spec.ts (computer only: Sat/Sun, Thu/Fri and, in weeks 80 to 82,
// Mon/Tue), so this spec takes only Wednesdays, and in week 83 the Monday and Tuesday too:
//   computer: A (F84) and D (Cook once here) Wednesday of week 80, B (F47) week 81,
//             L (leftovers dragged between days) Monday to Tuesday of week 83;
//   WebKit:   A and D Wednesday of week 83, B Wednesday of week 82;
//   phone:    D Wednesday of week 80 (the phone has no month grid, so no A or B).
// A and D only look at their own names and boxes, so they can share a day. The tests of tubs plan
// on past days (a freezer tub lasts three months, a fridge tub three days): T, and U seven weeks
// before it, 10 / 25 / 40 weeks back for the computer / WebKit / phone. The click-a-day-and-pick-
// a-recipe test (C) is on a past day too, 9, 14 or 19 weeks back. Everything is named with a word
// no other test uses ("Moon…"). The test that mocks "Fill from freezer first" plans nothing. A
// test that counts what is on its day clears the day first, so a retry starts from the same day.

type Which = 'A' | 'B' | 'C' | 'D' | 'F' | 'K' | 'L' | 'M' | 'T' | 'U';
const kind = () => {
  const name = test.info().project.name;
  return name.startsWith('phone') ? 'phone' : name.startsWith('webkit') ? 'webkit' : 'computer';
};
/** The test's own day. Today is a Saturday, so today + 7 × weeks is one too; Wednesday is 3 before. */
function dayFor(today: string, which: Which): string {
  const wed = (week: number) => addDays(today, 7 * week - 3);
  if (which === 'U') return addDays(dayFor(today, 'T'), -49);
  if (which === 'T') return addDays(today, -7 * { computer: 10, webkit: 25, phone: 40 }[kind()]);
  if (which === 'C') return addDays(today, -7 * { computer: 9, webkit: 14, phone: 19 }[kind()] + 1);
  if (which === 'L') return addDays(wed(83), -2); // Monday; the day after is the target
  // F (F167): a Wednesday of its own, with one fresh recipe and no batch, cleared before each test.
  if (which === 'F') return wed(84);
  // K (F84): a Wednesday of its own, cleared before each test, so no other test's meals crowd it.
  if (which === 'K') return wed(85);
  // M (F149, F137): a Wednesday no other test here uses, cleared before each test.
  if (which === 'M') return wed(kind() === 'computer' ? 82 : 81);
  if (kind() === 'computer') return wed({ A: 80, B: 81, D: 80 }[which]);
  if (kind() === 'webkit') return wed({ A: 83, B: 82, D: 83 }[which]);
  return wed(80);
}

/** Take everything off a day, so a test that counts what is there starts from nothing on a retry. */
async function clearDay(page: Page, day: string) {
  const plan = (await (await page.request.get(`/api/v1/plan?from=${day}&to=${day}`)).json()) as {
    meals: { id: number; date: string }[];
  };
  for (const meal of plan.meals.filter((m) => m.date === day)) {
    await call(page, 'DELETE', `/plan/meals/${meal.id}`);
  }
}

/** Take off a day only what this test put there: its batches (by recipe name), then its items. */
async function dropMine(page: Page, day: string, names: string[], items: number[]) {
  const plan = (await (await page.request.get(`/api/v1/plan?from=${day}&to=${day}`)).json()) as {
    batch_cooks: { id: number; recipe_name: string }[];
  };
  for (const batch of plan.batch_cooks.filter((b) => names.includes(b.recipe_name))) {
    await call(page, 'DELETE', `/plan/batches/${batch.id}`);
  }
  for (const id of items) {
    await page.request.fetch(`/api/v1/plan/items/${id}`, { method: 'DELETE', headers: key(), maxRetries: 3 });
  }
}

const stamp = () => `Moon${kind()}${Date.now().toString(36)}`;

async function setup(page: Page) {
  const household = (await (await page.request.get('/api/v1/household')).json()) as {
    today: string;
  };
  const list = (await (await page.request.get('/api/v1/meal-slots')).json()).meal_slots as {
    id: number;
    name: string;
  }[];
  const slot = Object.fromEntries(list.map((s) => [s.name, s.id])) as SlotIds;
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
async function cookedOnce(page: Page, name: string, day: string, slot: SlotIds) {
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

/** The middle of a thing, or a point part-way down it. */
async function centre(locator: Locator, down = 0.5) {
  await locator.scrollIntoViewIfNeeded();
  const box = (await locator.boundingBox())!;
  return { x: box.x + box.width / 2, y: box.y + box.height * down };
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
  slot: SlotIds,
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
 * The phone's day under the dot grid. Not the day's cooking below it (PlanCook, `cook-<day>`), which
 * has the same name once the day has any cooking: fresh cooking too since F167.
 */
const dayRegion = (page: Page, day: string) =>
  page.getByRole('region', { name: dayName(day) }).and(page.locator(':not([id^="cook-"])'));

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
    await dayRegion(page, day)
      // "+ Add breakfast" when the meal is empty, the + beside it when it has something
      .getByRole('button', {
        name: new RegExp(`^(\\+ Add ${meal.toLowerCase()}|Add to ${meal} on )`)
      })
      .click();
    return page.getByRole('dialog', { name: 'Add to the plan' });
  }
  const where = page.getByTestId(`day-${day}`);
  await expect(where).toBeVisible();
  // The day's own button (it covers the whole day), clicked in its corner: no number, no chip.
  // Clicked through its locator, so the point is worked out from where the day is at the moment
  // of the click, and the click waits until the day has stopped moving and that point is the
  // day's own (E3): a click at a box read a moment before could land where the day had been
  // while the month was still settling, on a neighbour (F53's rare failure on a computer).
  const hit = where.getByRole('button', { name: /^Add to / });
  const size = (await hit.boundingBox())!;
  await hit.click({ position: { x: size.width - 5, y: size.height - 5 } });
  const add = page.getByRole('dialog', { name: 'Add to the plan' });
  // F127: before a meal is picked, small "Pick a meal, then what to add" over the full day;
  // after, small "Add to" over "Dinner · Wednesday 11".
  await expect(add.getByRole('heading', { level: 2 })).toHaveText(dayName(day));
  await expect(add.getByText('Pick a meal, then what to add')).toBeVisible();
  await add
    .getByRole('group', { name: 'Meal' })
    .getByRole('button', { name: meal, exact: true })
    .click();
  await expect(add.getByRole('heading', { level: 2 })).toHaveText(
    `${meal} · ${dayName(day).split(' ').slice(0, 2).join(' ')}`
  );
  await expect(add.getByText('Add to', { exact: true })).toBeVisible();
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
    await expect(dayRegion(page, day)).toContainText(name);
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
  // Other tests' freezer tubs may use up the twelve places: then the rest are behind "+N more tubs".
  const rest = add.getByRole('button', { name: /^\+\d+ more tubs$/ });
  if (await rest.isVisible()) await rest.click();
  // Tubs of other tests may be in the list too; among this test's own, the oldest come first.
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
  // Found by this test's own batch, so a retry (which has put another tub there) still passes.
  await expect
    .poll(async () => {
      const plan = (await (
        await page.request.get(`/api/v1/plan?from=${day}&to=${day}`)
      ).json()) as {
        meals: { slot_id: number; items: { tub_id: number | null }[] }[];
        tubs: { id: number; batch_id: number }[];
        batch_cooks: { id: number; recipe_name: string }[];
      };
      const batch = plan.batch_cooks.find((b) => b.recipe_name === `${word} Oldest`);
      const mine = new Set(plan.tubs.filter((t) => t.batch_id === batch?.id).map((t) => t.id));
      const lunch = plan.meals.find((m) => m.slot_id === slot.Lunch);
      return lunch?.items.some((i) => i.tub_id !== null && mine.has(i.tub_id));
    })
    .toBe(true);
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
  // A double click plans it once: the recipes wait while it is being planned.
  await add.getByRole('button', { name: new RegExp(`^${name}`) }).dblclick();
  const cook = page.getByRole('dialog', { name: 'Cook once, eat for…' });
  await expect(cook).toBeVisible();
  await expect(cook).toContainText(name);
  const meals = (await (await page.request.get(`/api/v1/plan?from=${day}&to=${day}`)).json()) as {
    meals: { slot_id: number; items: { recipe: { name: string } | null }[] }[];
  };
  expect(
    meals.meals
      .find((m) => m.slot_id === slot.Breakfast)
      ?.items.map((i) => i.recipe?.name)
      .filter((n) => n === name)
  ).toEqual([name]);
});

test('F52: when Cook once here cannot plan the recipe, the sheet stays and says why', async ({
  page
}) => {
  const { today } = await setup(page);
  const day = dayFor(today, 'D');
  const name = `${stamp()} Kesari`;
  await makeRecipe(page, name);
  const add = await openDay(page, today, day, 'Breakfast');
  await add.getByRole('button', { name: 'Cook once here…' }).click();
  await add.getByRole('searchbox', { name: 'Find a recipe or an ingredient' }).fill(name);
  await expect(add.getByRole('button', { name: new RegExp(`^${name}`) })).toBeVisible();
  await page.route('**/api/v1/plan/items', (route) =>
    route.request().method() === 'POST'
      ? route.fulfill({
          status: 422,
          json: { code: 'meal_off', detail: 'That meal is switched off.' }
        })
      : route.fallback()
  );
  await add.getByRole('button', { name: new RegExp(`^${name}`) }).click();
  await expect(
    page.getByRole('status').filter({ hasText: 'That meal is switched off.' })
  ).toBeVisible();
  await expect(add).toBeVisible();
  await expect(page.getByRole('dialog', { name: 'Cook once, eat for…' })).toHaveCount(0);
});

test('F52: a long freezer list never hides a fridge tub; "+N more tubs" lists the rest', async ({
  page
}) => {
  const { today, slot } = await setup(page);
  const day = dayFor(today, 'U');
  const word = stamp();
  // Seven batches of two tubs in the freezer (fourteen, the oldest first), and one in the fridge.
  for (let n = 0; n < 7; n++) {
    await pastBatch(page, `${word} Frozen${n}`, addDays(day, -2 - n), slot, 'freezer');
  }
  await pastBatch(page, `${word} Chilled`, addDays(day, -1), slot, 'fridge');
  const add = await openDay(page, today, day, 'Lunch');
  const tubs = add.getByRole('list', { name: 'Tubs left' });
  await expect(
    tubs
      .getByRole('listitem')
      .filter({ hasText: `${word} Chilled` })
      .first()
  ).toBeVisible();
  const more = add.getByRole('button', { name: /^\+\d+ more tubs$/ });
  await expect(more).toBeVisible();
  const before = await tubs.getByRole('listitem').count();
  await more.click();
  await expect(more).toHaveCount(0);
  expect(await tubs.getByRole('listitem').count()).toBeGreaterThan(before);
  await expect(
    tubs
      .getByRole('listitem')
      .filter({ hasText: `${word} Frozen6` })
      .first()
  ).toBeVisible();
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
      const day = dayFor(today, 'K');
      await clearDay(page, day);
      const curry = `${stamp()} Curry`;
      const cook = await cookedOnce(page, curry, day, slot);
      try {
        await openMonthOf(page, today, day);
        const cooking = page.getByTestId(`day-${day}`);
        await expect(cooking.getByText('COOK', { exact: true })).toBeVisible();
        // Measured until the layout has settled (fonts, chips), not once the moment COOK shows.
        await expect
          .poll(() => inside(cooking.getByText('COOK', { exact: true }), cooking), {
            message: 'COOK stays inside its day'
          })
          .toBe(true);
        await expect
          .poll(() => inside(cooking.getByRole('button', { name: /^Add to / }), cooking), {
            message: 'Add stays inside its day'
          })
          .toBe(true);
      } finally {
        // Its own batch goes too: a day takes only 10, and repeated runs left one each time.
        await dropMine(page, day, [curry], [cook.item_id]);
      }
    });

    test(`F84: on a very full day the Today and COOK tags stay inside it at ${width} px`, async ({
      page
    }) => {
      await page.setViewportSize({ width, height: 800 });
      const { today, slot } = await setup(page);
      // Its own full day: a cooking on today and a meal in every slot, so today shows three
      // chips, "+N more", Today and COOK whatever other tests left there (more can't add to it).
      // Its own meals only: today is everyone's, so nothing else is taken off it.
      // Another test may already have dealt with one of today's meals (Cook now, Cooked it), and
      // a dealt-with meal takes nothing more (409 meal_done), so each one goes in the first
      // still-planned meal of today: the cooking, then four more, so "+N more" is always there.
      const curry = `${stamp()} Full curry`;
      const mine: number[] = [];
      const order = ['Dinner', 'Lunch', 'Breakfast', 'Snack'].map((name) => slot[name]!);
      const intoToday = async (recipeId: number) => {
        for (const slotId of order) {
          const response = await page.request.post('/api/v1/plan/items', {
            data: { date: today, slot_id: slotId, recipe_id: recipeId },
            headers: key()
          });
          if (response.ok()) return (await response.json()) as { item_id: number };
          expect((await response.json()).code, `POST /plan/items into ${slotId}`).toBe('meal_done');
        }
        throw new Error('every meal today has been dealt with');
      };
      try {
        const cook = await intoToday(await makeRecipe(page, curry));
        mine.push(cook.item_id);
        await call(page, 'POST', `/plan/items/${cook.item_id}/batch`, {
          tub_count: 1,
          pattern: 'pick',
          placements: [null]
        });
        for (const name of ['One', 'Two', 'Three', 'Four']) {
          mine.push((await intoToday(await makeRecipe(page, `${stamp()} ${name}`))).item_id);
        }
        await openMonthOf(page, today, today);
        const here = page.getByTestId(`day-${today}`);
        await expect(here.getByText('Today', { exact: true })).toBeVisible();
        await expect(here.getByText('COOK', { exact: true })).toBeVisible();
        await expect(here.getByRole('button', { name: /^\+\d+ more$/ })).toBeVisible();
        // Measured together in one go, once the day has its chips, so nothing moves between them.
        for (const tag of ['Today', 'COOK']) {
          await expect
            .poll(() =>
              here.evaluate((day, text) => {
                const el = [...day.querySelectorAll('.top span')].find((s) => s.textContent?.trim() === text)!;
                const [a, b] = [el.getBoundingClientRect(), day.getBoundingClientRect()];
                const slack = 0.5;
                return (
                  a.left >= b.left - slack &&
                  a.top >= b.top - slack &&
                  a.right <= b.right + slack &&
                  a.bottom <= b.bottom + slack
                );
              }, tag),
              { message: `${tag} stays inside today` }
            )
            .toBe(true);
        }
      } finally {
        await dropMine(page, today, [curry], mine);
      }
    });
  }

  for (const [width, height] of [
    [1280, 800],
    [1366, 768]
  ] as const) {
    test(`F47: a six-week month at ${width}×${height} scrolls, and no day clips what is in it`, async ({
      page
    }) => {
      await page.setViewportSize({ width, height });
      const { today } = await setup(page);
      const first = sixWeekMonth(today);
      await openMonthOf(page, today, first);
      await expect(page.getByTestId(`day-${first}`)).toBeVisible();
      expect(await page.getByTestId(/^day-/).count()).toBe(42);
      // cabledrawer 2 Nov: three things a day matter more than one screen, so the page scrolls.
      const clipped = () =>
        page.evaluate(
          () =>
            [...document.querySelectorAll<HTMLElement>('[data-testid^="day-"]')].filter(
              (c) => c.scrollHeight > c.clientHeight + 1
            ).length
        );
      expect(await clipped()).toBe(0);
      expect(await page.evaluate(() => document.documentElement.scrollHeight > innerHeight)).toBe(
        true
      );
      await page.getByTestId(`day-${addDays(first, 35)}`).scrollIntoViewIfNeeded();
      await expect(page.getByTestId(`day-${addDays(first, 35)}`)).toBeInViewport();
    });
  }

  for (const [width, height] of [
    [1280, 800],
    [1366, 768]
  ] as const) {
    test(`F47: a day of five things shows three and "+2 more" at ${width}×${height}, the cooking first`, async ({
      page
    }) => {
      await page.setViewportSize({ width, height });
      const { today, slot } = await setup(page);
      const day = dayFor(today, 'B');
      await clearDay(page, day);
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
      expect(await inside(where.getByRole('button', { name: '+2 more' }), where)).toBe(true);
      await where.getByRole('button', { name: '+2 more' }).click();
      const sheet = page.getByRole('dialog', { name: /^(Wednesday|Monday|Tuesday)/ });
      await expect(sheet).toContainText(`${word} Soup`);
      await expect(sheet).toContainText(`${word} Fruit`);
    });
  }

  test('F47: at 200% text a busy day still shows "+N more" inside its day, and the side panel scrolls', async ({
    page
  }) => {
    const { today, slot } = await setup(page);
    const day = dayFor(today, 'B');
    const word = stamp();
    await cookedOnce(page, `${word} Curry`, day, slot);
    for (const meal of [slot.Breakfast, slot.Lunch, slot.Lunch, slot.Snack]) {
      await planned(page, await makeRecipe(page, `${word} ${meal}x${Math.random()}`), day, meal);
    }
    await openMonthOf(page, today, day);
    const where = page.getByTestId(`day-${day}`);
    await expect(where).toBeVisible();
    await page.evaluate(() => (document.documentElement.style.fontSize = '200%'));
    const more = where.getByRole('button', { name: /^\+\d+ more$/ });
    await expect(more).toBeVisible();
    await expect
      .poll(async () =>
        page.evaluate(
          () =>
            [...document.querySelectorAll<HTMLElement>('[data-testid^="day-"]')].filter(
              (c) => c.scrollHeight > c.clientHeight + 1
            ).length
        )
      )
      .toBe(0);
    expect(await inside(more, where)).toBe(true);
    expect(await inside(where.locator('.num'), where)).toBe(true);
    // The panel beside the month is cut off at its own edge: it scrolls, so its last button is reachable.
    const panel = page.getByRole('complementary', { name: 'This month' });
    expect(await panel.evaluate((el) => getComputedStyle(el).overflowY)).toBe('auto');
    const fill = page.getByRole('button', { name: 'Fill from freezer first' });
    await fill.scrollIntoViewIfNeeded();
    await expect(fill).toBeInViewport();
  });

  test('the keyboard focus ring of a day is drawn inside it, in both themes', async ({ page }) => {
    const { today } = await setup(page);
    await openMonthOf(page, today, today);
    const hit = page.getByTestId(`day-${today}`).getByRole('button', { name: /^Add to / });
    // Tab to it, as a keyboard user does (focus from a script is not always "focus-visible").
    const label = await hit.getAttribute('aria-label');
    for (let tabs = 0; tabs < 400; tabs++) {
      await page.keyboard.press('Tab');
      if ((await page.evaluate(() => document.activeElement?.getAttribute('aria-label'))) === label)
        break;
    }
    await expect(hit).toBeFocused();
    for (const theme of ['light', 'dark'] as const) {
      await inTheme(page, theme);
      const ring = await hit.evaluate((el) => {
        const style = getComputedStyle(el);
        const offset = parseFloat(style.outlineOffset);
        return {
          visible: el.matches(':focus-visible'),
          style: style.outlineStyle,
          width: parseFloat(style.outlineWidth),
          offset
        };
      });
      expect(ring.visible, theme).toBe(true);
      expect(ring.style, theme).toBe('solid');
      expect(ring.width, theme).toBeGreaterThanOrEqual(2);
      // Negative: inside the button, which fills the day, so the day's clipping cannot cut it.
      expect(ring.offset, theme).toBeLessThanOrEqual(-2);
    }
  });

  test('a chip dragged to a later day with "Leftovers here" plans leftovers there, with Undo', async ({
    page
  }) => {
    test.skip(kind() !== 'computer', 'the computer has the free pair of days');
    const { today, slot } = await setup(page);
    const day = dayFor(today, 'L');
    const next = addDays(day, 1);
    await clearDay(page, day);
    await clearDay(page, next);
    const name = `${stamp()} Dosa`;
    await planned(page, await makeRecipe(page, name), day, slot.Lunch);
    await openMonthOf(page, today, day);
    const chip = page
      .getByTestId(`day-${day}`)
      .getByRole('button', { name: new RegExp(`^${name}`) });
    const target = page.getByTestId(`day-${next}`);
    const a = await centre(chip);
    await page.mouse.move(a.x, a.y);
    await page.mouse.down();
    await page.mouse.move(a.x + 12, a.y + 12, { steps: 3 });
    const b = await centre(target, 0.2);
    await page.mouse.move(b.x, b.y, { steps: 10 });
    const zone = target.locator('[data-drop-zone="leftovers"]');
    await expect(zone).toBeVisible();
    const z = await centre(zone);
    await page.mouse.move(z.x, z.y, { steps: 4 });
    await page.mouse.up();
    await expect(target).toContainText(name);
    await expect(page.getByTestId(`day-${day}`)).toContainText(name);
    await expect(page.getByRole('status').filter({ hasText: 'Leftovers' })).toBeVisible();
    await page.getByRole('button', { name: 'Undo', exact: true }).click();
    await expect(target).not.toContainText(name);
  });

  test('"Fill from freezer first" says which meals it filled and why, with one Undo', async ({
    page
  }) => {
    const { today, slot } = await setup(page);
    const day = dayFor(today, 'D');
    // A tub in the freezer, so the button is on (the fill itself is answered by the test, below:
    // the real one would put tubs on other tests' empty days).
    await pastBatch(page, `${stamp()} Freezer`, addDays(dayFor(today, 'T'), -28), slot, 'freezer');
    const summary = 'Filled Tue 3 dinner, Thu 5 lunch from freezer tubs (they run out soonest)';
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
    // The summary comes with the answer, so wait for the answer first: a slow run then says which
    // stage it stopped at (plan-month.spec.ts:697 in a WebKit full check, 9 Nov). The toast's first
    // words aren't waited for: a quick answer replaces them before they can be seen.
    const answered = page.waitForResponse('**/api/v1/plan/fill-from-freezer');
    await page.getByRole('button', { name: 'Fill from freezer first' }).click();
    await answered;
    const toast = page.getByRole('status').filter({ hasText: summary });
    await expect(toast).toBeVisible();
    await expect(toast.getByRole('button', { name: 'Undo all', exact: true })).toHaveCount(1);
    await expect(toast.getByRole('button', { name: 'Undo', exact: true })).toHaveCount(0);
    await toast.getByRole('button', { name: 'Undo all', exact: true }).click();
    await expect.poll(() => undone).toBe(1);
  });
});

// --- F149: Eat · Cook · Both on the Month (phone and computer) ----------------------------------

/** A batch cooking (dinner) and a fresh meal (lunch) on the same day, with names of their own. */
async function cookAndEat(page: Page, day: string, slot: SlotIds) {
  await clearDay(page, day); // a retry starts from the same day
  const word = stamp();
  const batch = `${word} Batch`;
  const fresh = `${word} Fresh`;
  await cookedOnce(page, batch, day, slot);
  await planned(page, await makeRecipe(page, fresh), day, slot.Lunch);
  // Something that is not cooking, so Cook can be seen leaving it out.
  const note = `${word} Takeaway`;
  await call(page, 'POST', '/plan/items', { date: day, slot_id: slot.Snack, note });
  return { batch, fresh, note };
}

const showSwitch = (page: Page) =>
  page
    .getByRole('group', { name: 'Show', exact: true })
    .filter({ has: page.getByRole('button', { name: 'Both', exact: true }) });

test.describe('F149: the Show switch on the Month', () => {
  test.skip(() => kind() !== 'phone', 'the phone’s month (the computer’s is the next group)');

  test('Eat shows dots and the day’s meals; Cook a blue ring and Start cooking; Both shows both', async ({
    page
  }) => {
    const { today, slot } = await setup(page);
    const day = dayFor(today, 'M');
    const { batch, fresh } = await cookAndEat(page, day, slot);
    await openMonthOf(page, today, day);
    const cell = page.getByRole('group', { name: 'Days' }).getByRole('button', {
      name: dayName(day),
      exact: true
    });
    await cell.click();
    const ring = () => cell.evaluate((el) => getComputedStyle(el).borderTopColor);
    const transparent = 'rgba(0, 0, 0, 0)';
    const legend = page.getByTestId('month-legend');
    const start = page.getByRole('button', { name: `Start cooking ${batch}` });
    const meal = page.getByRole('button', { name: new RegExp(`^Lunch: ${fresh}`) });

    // Both (the switch is kept from the Week: the same choice).
    await expect(showSwitch(page)).toBeVisible();
    await expect(showSwitch(page).getByRole('button', { name: 'Both', exact: true })).toHaveAttribute(
      'aria-pressed',
      'true'
    );
    await expect(legend).toHaveText('Blue ring: a day you cook. Dots: meals planned.');
    await expect.poll(ring).not.toBe(transparent);
    await expect(cell.locator('.dot').first()).toBeVisible();
    await expect(start).toBeVisible();
    await expect(meal).toBeVisible();

    // Cook: no dots, the ring, what is cooked with Start cooking, and no meals.
    await showSwitch(page).getByRole('button', { name: 'Cook', exact: true }).click();
    await expect(legend).toHaveText('Blue ring: a day you cook.');
    await expect(cell.locator('.dot')).toHaveCount(0);
    await expect.poll(ring).not.toBe(transparent);
    await expect(start).toBeVisible();
    await expect(meal).toHaveCount(0);

    // Eat: dots, no ring, the day’s meals, no Start cooking.
    await showSwitch(page).getByRole('button', { name: 'Eat', exact: true }).click();
    await expect(legend).toHaveText('Dots: meals planned, in each batch’s colour.');
    await expect(cell.locator('.dot').first()).toBeVisible();
    await expect.poll(ring).toBe(transparent);
    await expect(meal).toBeVisible();
    await expect(start).toHaveCount(0);

    // The choice is the Week’s too.
    await page.getByRole('button', { name: 'Week', exact: true }).click();
    await expect(showSwitch(page).getByRole('button', { name: 'Eat', exact: true })).toHaveAttribute(
      'aria-pressed',
      'true'
    );
  });

  test('both themes: the ring and the legend read', async ({ page }) => {
    const { today, slot } = await setup(page);
    const day = dayFor(today, 'M');
    await cookAndEat(page, day, slot);
    await openMonthOf(page, today, day);
    for (const theme of ['dark', 'light'] as const) {
      await inTheme(page, theme);
      await expect(page.getByTestId('month-legend')).toBeVisible();
      await expectNoSidewaysScroll(page);
    }
  });
});

test.describe('F149: the Show switch on the computer’s Month', () => {
  test.skip(() => kind() === 'phone', 'the computer’s month');

  test('Cook shows only the cooking chips, batch and fresh, blue with a pan; Eat and Both show every chip', async ({
    page
  }) => {
    const { today, slot } = await setup(page);
    const day = dayFor(today, 'M');
    const { batch, fresh, note } = await cookAndEat(page, day, slot);
    await openMonthOf(page, today, day);
    const where = page.getByTestId(`day-${day}`);
    const chip = (name: string) => where.getByRole('button', { name: new RegExp(name) });
    await expect(showSwitch(page)).toBeVisible();

    await expect(chip(batch)).toBeVisible();
    await expect(chip(fresh)).toBeVisible();
    await expect(chip(note)).toBeVisible();

    await showSwitch(page).getByRole('button', { name: 'Cook', exact: true }).click();
    await expect(chip(batch)).toBeVisible();
    await expect(chip(fresh)).toBeVisible(); // F167: fresh cooking is cooking too
    // Review r1 L5: a screen reader hears it is cooking, as the pan shows.
    await expect(chip(fresh)).toHaveAccessibleName(new RegExp(`^Cooking ${fresh}`));
    await expect(chip(note)).toHaveCount(0);
    await expect(chip(batch).locator('svg')).toHaveCount(1); // the pan
    await expect(chip(fresh).locator('svg')).toHaveCount(1);
    const [chipColour, cookColour] = await page.evaluate((selector) => {
      const probe = document.createElement('i');
      probe.style.background = 'var(--color-cook)';
      document.body.append(probe);
      const cook = getComputedStyle(probe).backgroundColor;
      probe.remove();
      const el = document.querySelector(selector)!;
      return [getComputedStyle(el).backgroundColor, cook];
    }, `[data-testid="day-${day}"] button.chip`);
    expect(chipColour).toBe(cookColour);

    await showSwitch(page).getByRole('button', { name: 'Eat', exact: true }).click();
    await expect(chip(batch)).toBeVisible();
    await expect(chip(fresh)).toBeVisible();
    await expect(chip(batch).locator('svg')).toHaveCount(0);

    await showSwitch(page).getByRole('button', { name: 'Both', exact: true }).click();
    await expect(chip(fresh)).toBeVisible();
  });
});

// --- F167: Month → Cook marks every day with cooking, a fresh recipe as well as a batch ---------

/** A day with one fresh recipe and no batch, with a name of its own. */
async function freshOnly(page: Page, day: string, slot: SlotIds) {
  await clearDay(page, day);
  const fresh = `${stamp()} Fresh`;
  await planned(page, await makeRecipe(page, fresh), day, slot.Dinner);
  return fresh;
}

test.describe('F167 on the phone', () => {
  test.skip(() => kind() !== 'phone', 'the phone’s month');

  test('a day cooked fresh gets the blue ring in Cook and Both, and none in Eat', async ({ page }) => {
    const { today, slot } = await setup(page);
    const day = dayFor(today, 'F');
    const fresh = await freshOnly(page, day, slot);
    await openMonthOf(page, today, day);
    const cell = page.getByRole('group', { name: 'Days' }).getByRole('button', {
      name: dayName(day),
      exact: true
    });
    await cell.click();
    const ring = () => cell.evaluate((el) => getComputedStyle(el).borderTopColor);
    const transparent = 'rgba(0, 0, 0, 0)';
    await showSwitch(page).getByRole('button', { name: 'Cook', exact: true }).click();
    await expect.poll(ring).not.toBe(transparent);
    await expect(page.getByRole('button', { name: `Start cooking ${fresh}` })).toBeVisible();
    await showSwitch(page).getByRole('button', { name: 'Both', exact: true }).click();
    await expect.poll(ring).not.toBe(transparent);
    await showSwitch(page).getByRole('button', { name: 'Eat', exact: true }).click();
    await expect.poll(ring).toBe(transparent);
    await showSwitch(page).getByRole('button', { name: 'Both', exact: true }).click();
  });
});

test.describe('F167 on the computer', () => {
  test.skip(() => kind() === 'phone', 'the computer’s month');

  test('a day cooked fresh has the COOK tag and a blue chip with a pan in Cook', async ({ page }) => {
    const { today, slot } = await setup(page);
    const day = dayFor(today, 'F');
    const fresh = await freshOnly(page, day, slot);
    await openMonthOf(page, today, day);
    const where = page.getByTestId(`day-${day}`);
    await showSwitch(page).getByRole('button', { name: 'Cook', exact: true }).click();
    await expect(where.getByText('COOK', { exact: true })).toBeVisible();
    const chip = where.getByRole('button', { name: new RegExp(fresh) });
    await expect(chip).toBeVisible();
    await expect(chip.locator('svg')).toHaveCount(1);
    // Both matches the phone: every cooking day, fresh as well as batch (cabledrawer 7 Nov, r1 L4).
    await showSwitch(page).getByRole('button', { name: 'Both', exact: true }).click();
    await expect(where.getByText('COOK', { exact: true })).toBeVisible();
  });
});

// --- F137: Week names at the narrowest week grid, 1200 px (H9, cabledrawer 11 Nov) ------------------

test.describe('F137: a Week card’s name breaks between words only', () => {
  test.skip(() => kind() === 'phone', 'the week grid is the computer’s');

  test('at 1200 px (the narrowest week grid) a name never breaks inside a word; a name too long for its cell ends in an ellipsis and is whole on hover', async ({
    page
  }) => {
    await page.setViewportSize({ width: 1200, height: 900 });
    const { today, slot } = await setup(page);
    const day = dayFor(today, 'M');
    await clearDay(page, day);
    const word = stamp();
    const wordy = `${word} Chickpea Authentic Ingredient Curry`;
    const huge = `Supercalifragilisticexpialidocious${word}`;
    await planned(page, await makeRecipe(page, wordy), day, slot.Lunch);
    await planned(page, await makeRecipe(page, huge), day, slot.Dinner);

    await page.goto('/plan');
    const weeks = Math.round(
      (Date.parse(`${day}T12:00:00Z`) - Date.parse(`${today}T12:00:00Z`)) / 86_400_000 / 7
    );
    for (let i = 0; i < weeks; i++) await page.getByRole('button', { name: 'Next week' }).click();

    for (const theme of ['dark', 'light'] as const) {
      await inTheme(page, theme);
      const names = page.getByTestId(new RegExp(`^cell-${day}-`)).locator('.name');
      await expect(names.filter({ hasText: wordy })).toBeVisible();
      const report = await names.evaluateAll((els, mine) => {
        const out: Record<string, unknown> = {};
        for (const el of els) {
          const text = el.textContent ?? '';
          if (!mine.some((m) => text.includes(m))) continue;
          const style = getComputedStyle(el);
          const node = el.firstChild!;
          const broken: string[] = [];
          for (const m of text.matchAll(/\S+/g)) {
            const range = document.createRange();
            range.setStart(node, m.index!);
            range.setEnd(node, m.index! + m[0].length);
            const lines = new Set(
              [...range.getClientRects()].filter((r) => r.width > 0).map((r) => Math.round(r.top / 4))
            );
            if (lines.size > 1) broken.push(m[0]);
          }
          out[text] = {
            wrap: style.overflowWrap,
            breaks: style.wordBreak,
            hyphens: style.hyphens,
            ellipsis: style.textOverflow,
            cut: el.scrollWidth > el.clientWidth,
            broken,
            title: el.closest('button')?.getAttribute('title')
          };
        }
        return out;
      }, [wordy, huge]);
      const wordyReport = report[wordy] as Record<string, unknown>;
      const hugeReport = report[huge] as Record<string, unknown>;
      expect(wordyReport).toMatchObject({
        wrap: 'normal',
        breaks: 'normal',
        hyphens: 'manual',
        broken: [],
        title: wordy
      });
      expect(hugeReport).toMatchObject({ ellipsis: 'ellipsis', cut: true, title: huge });
    }
  });
});

test.describe('the Month’s day panel at 800 and 1024 px (the computer’s compact Month)', () => {
  test.skip(() => kind() === 'phone', 'the computer’s narrow widths');

  for (const width of [800, 1024]) {
    test(`at ${width} px the day sits beside the grid at normal text; at 200% text it goes under the grid, its words whole`, async ({
      page
    }) => {
      await page.setViewportSize({ width, height: 900 });
      const { today, slot } = await setup(page);
      const day = dayFor(today, 'M');
      await clearDay(page, day);
      const name = `Shakshuka ${Date.now().toString(36).slice(-6)}`;
      await planned(page, await makeRecipe(page, name), day, slot.Breakfast);
      await openMonthOf(page, today, day);
      await showSwitch(page).getByRole('button', { name: 'Eat', exact: true }).click();
      const grid = page.getByRole('group', { name: 'Days', exact: true });
      const cell = grid.getByRole('button', { name: dayName(day), exact: true });
      await cell.click();
      await expect(cell).toHaveAttribute('aria-pressed', 'true');
      const meal = page.getByRole('button', { name: new RegExp(`^Breakfast: ${name}`) });
      const words = meal.locator('.name');
      await expect(words).toBeVisible();
      const where = async () => {
        const g = (await grid.boundingBox())!;
        const m = (await meal.boundingBox())!;
        return m.x >= g.x + g.width ? 'beside' : m.y >= g.y + g.height ? 'under' : 'overlapping';
      };
      const broken = () =>
        words.evaluate((el) => {
          const node = el.firstChild!;
          const out: string[] = [];
          for (const m of (el.textContent ?? '').matchAll(/\S+/g)) {
            const range = document.createRange();
            range.setStart(node, m.index!);
            range.setEnd(node, m.index! + m[0].length);
            const lines = new Set(
              [...range.getClientRects()].filter((r) => r.width > 0).map((r) => Math.round(r.top / 4))
            );
            if (lines.size > 1) out.push(m[0]);
          }
          return out;
        });
      // Normal text: as drawn, the day's meals beside the month (F47).
      await expect.poll(where).toBe('beside');
      // At 800 px that panel is about 228 px wide even at normal text: the dishes go under the meal's
      // name when they don't fit beside it, instead of being squeezed until a word breaks (a 9-letter
      // word such as Shakshuka broke there; Opus review 9 Nov).
      await expect.poll(broken).toEqual([]);
      // 200% text: the panel beside the grid was about 240 px wide, and the dishes were squeezed until
      // every word broke (WebKit, full checks 1 and 4). Now the day goes under the grid, as on the phone.
      await page.evaluate(() => (document.documentElement.style.fontSize = '200%'));
      await expect.poll(where).toBe('under');
      await expect.poll(broken).toEqual([]);
      await expectNoSidewaysScroll(page);
    });
  }
});
