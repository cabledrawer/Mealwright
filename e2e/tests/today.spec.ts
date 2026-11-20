import { test, expect, type Page } from './clock.ts';
import { checkPage } from './a11y.ts';
import { addDays, key, stamp } from './helpers.ts';

// Today (0.6, PR 6), against the real server: "Did you cook Sambar?" with Cooked it (and "Any
// left over?"), Didn't and Move it (to tomorrow, alongside a meal that has food), and the
// first-day state. Runs on Chromium (phone and computer) and WebKit (computer), see
// playwright.config.ts. The projects share one server, and an answered meal keeps its slot, so
// each project and test plans on a day and meal of its own and answers its own meal.

async function call(page: Page, method: 'POST' | 'DELETE', path: string, data?: object) {
  const response = await page.request.fetch(`/api/v1${path}`, { method, data, headers: key() });
  expect(response.ok(), `${method} ${path}: ${await response.text()}`).toBe(true);
  return (await response.json()) as Record<string, any>;
}

/** Today's server data, the slots by name, and a meal planned in the past for this project. */
async function start(page: Page, slotName: string) {
  const today = (await (await page.request.get('/api/v1/household')).json()).today as string;
  const slots = (await (await page.request.get('/api/v1/meal-slots')).json()).meal_slots as { id: number; name: string }[];
  const slot = Object.fromEntries(slots.map((s) => [s.name, s.id])) as Record<string, number>;
  // Anything left waiting by another test is answered first, so this meal is the card.
  const read = (await (await page.request.get('/api/v1/today')).json()) as { waiting: { meal_id: number }[] };
  for (const w of read.waiting) await call(page, 'POST', `/plan/meals/${w.meal_id}/mark-not-cooked`);
  const project = test.info().project.name;
  const back = project.includes('phone') ? 1 : project.includes('desktop') ? 2 : 3;
  const name = `Sambar ${stamp()}`;
  const recipe = (await call(page, 'POST', '/recipes', { name, serves: 4, lines: [] })).id as number;
  const made = await call(page, 'POST', '/plan/items', {
    date: addDays(today, -back),
    slot_id: slot[slotName],
    recipe_id: recipe,
  });
  return { today, slot, name, meal: made.meal_id as number, recipe };
}

const card = (page: Page) => page.getByTestId('did-you-cook');
const stat = (page: Page, label: string) => page.getByTestId('today-stats').locator('.stat', { hasText: label }).locator('b');

test('Cooked it with leftovers makes a tub, Undo asks again, then Cooked it', async ({ page }) => {
  const k = await start(page, 'Breakfast');
  await page.goto('/');
  await expect(page.getByRole('heading', { name: 'Today', level: 1 })).toBeVisible();
  await expect(card(page).getByText(`Did you cook ${k.name}?`)).toBeVisible();
  await expect(card(page).getByText('Nothing changes in the pantry until you say.')).toBeVisible();
  await checkPage(page); // the card passes the accessibility checks, both themes
  const before = Number(await stat(page, 'tubs left').innerText());

  await card(page).getByRole('button', { name: 'Cooked it' }).click();
  const sheet = page.getByRole('dialog', { name: `Cooked ${k.name}` });
  await expect(sheet.getByText('Nothing in this recipe comes from the pantry.')).toBeVisible();
  await expect(sheet.getByText('None', { exact: true })).toBeVisible();
  await sheet.getByRole('button', { name: 'More tubs' }).click();
  await expect(sheet.getByRole('group', { name: 'Leftover tubs' }).getByText('1 tub')).toBeVisible();
  await expect(sheet.getByRole('button', { name: 'Fridge' })).toHaveAttribute('aria-pressed', 'true');
  await expect(sheet.getByText(/Use by .* · \d+ days left|Use by .* · use by/)).toBeVisible();
  await sheet.getByRole('button', { name: 'Confirm · update pantry' }).click();

  await expect(card(page)).toHaveCount(0);
  await expect(page.getByText(new RegExp(`Cooked ${k.name}`)).first()).toBeVisible();
  await expect(stat(page, 'tubs left')).toHaveText(String(before + 1));

  // Undo: the card is back, the tub is gone.
  await page.getByRole('button', { name: 'Undo', exact: true }).click();
  await expect(card(page).getByText(`Did you cook ${k.name}?`)).toBeVisible();
  await expect(stat(page, 'tubs left')).toHaveText(String(before));

  // Cooked it with nothing left over: the card goes for good.
  await card(page).getByRole('button', { name: 'Cooked it' }).click();
  await sheet.getByRole('button', { name: 'Confirm · update pantry' }).click();
  await expect(card(page)).toHaveCount(0);
  await expect(stat(page, 'tubs left')).toHaveText(String(before));
  await page.reload();
  await expect(card(page)).toHaveCount(0);
});

test('Didn’t marks the meal not cooked', async ({ page }) => {
  const k = await start(page, 'Lunch');
  await page.goto('/');
  await expect(card(page).getByText(`Did you cook ${k.name}?`)).toBeVisible();
  await card(page).getByRole('button', { name: 'Didn’t' }).click();
  await expect(card(page)).toHaveCount(0);
  await expect(page.getByText(`Didn’t cook ${k.name}`)).toBeVisible();
  // The card goes at once; the server's answer follows.
  await expect
    .poll(async () => {
      const plan = await (await page.request.get(`/api/v1/plan?from=${addDays(k.today, -5)}&to=${addDays(k.today, -1)}`)).json();
      return plan.meals.find((m: any) => m.id === k.meal).status;
    })
    .toBe('didnt');
});

test('Move it to tomorrow adds alongside a meal that has food', async ({ page }) => {
  const k = await start(page, 'Dinner');
  const tomorrow = addDays(k.today, 1);
  const other = `Dosa ${stamp()}`;
  const dosa = (await call(page, 'POST', '/recipes', { name: other, serves: 4, lines: [] })).id as number;
  await call(page, 'POST', '/plan/items', { date: tomorrow, slot_id: k.slot.Dinner, recipe_id: dosa });

  await page.goto('/');
  await card(page).getByRole('button', { name: 'Move it' }).click();
  const sheet = page.getByRole('dialog', { name: `Move ${k.name} to` });
  await expect(sheet.getByText('Quick picks')).toBeVisible();
  await expect(sheet.getByRole('button', { name: /^Today · Dinner/ })).toContainText('free');
  const tomorrowPick = sheet.getByRole('button', { name: /^Tomorrow · Dinner/ });
  await expect(tomorrowPick).toContainText('adds alongside');
  await tomorrowPick.click();
  await sheet.getByRole('button', { name: 'Move to tomorrow' }).click();

  await expect(card(page)).toHaveCount(0);
  await expect(page.getByText(new RegExp(`Moved ${k.name} from`))).toBeVisible();
  await expect
    .poll(async () => {
      const plan = await (await page.request.get(`/api/v1/plan?from=${tomorrow}&to=${tomorrow}`)).json();
      const dinner = plan.meals.find((m: any) => m.slot_id === k.slot.Dinner);
      const names = dinner.items.map((i: any) => i.recipe?.name);
      return names.includes(k.name) && names.includes(other);
    })
    .toBe(true);
  await expect
    .poll(async () => {
      const old = await (await page.request.get(`/api/v1/plan?from=${addDays(k.today, -5)}&to=${addDays(k.today, -1)}`)).json();
      return old.meals.find((m: any) => m.id === k.meal).status;
    })
    .toBe('moved');
});

// "0 tubs left" is not in the warm tubs colour; with a tub left it is (0.7 paper cuts).
test.describe('the tubs left number', () => {
  test.use({ serviceWorkers: 'block' });

  const colours = (page: Page) =>
    page.evaluate(() => {
      const paint = (value: string) => {
        const probe = document.body.appendChild(document.createElement('span'));
        probe.style.color = value;
        const colour = getComputedStyle(probe).color;
        probe.remove();
        return colour;
      };
      const number = document.querySelector('[data-testid="today-stats"] .stat.tubs b')!;
      return {
        now: getComputedStyle(number).color,
        tubs: paint('var(--color-tubs)'),
        muted: paint('var(--color-text-muted)'),
      };
    });

  const withTubs = async (page: Page, tubs: unknown[]) => {
    await page.route('**/api/v1/today', async (route) => {
      const response = await route.fetch();
      const body = await response.json();
      await route.fulfill({ response, json: { ...body, first_day: false, tubs_left: tubs, tubs_left_next: null } });
    });
    await page.goto('/');
  };

  test('0 is quiet', async ({ page }) => {
    await withTubs(page, []);
    await expect(stat(page, 'tubs left')).toHaveText('0');
    const c = await colours(page);
    expect(c.now).toBe(c.muted);
    expect(c.now).not.toBe(c.tubs);
  });

  test('1 or more keeps the warm colour', async ({ page }) => {
    const real = await page.request.get('/api/v1/today');
    const sample = ((await real.json()) as { tubs_left: unknown[] }).tubs_left[0];
    // The shared household may have no tub left: borrow a plain object, the number only counts them.
    await withTubs(page, [sample ?? { id: 1 }]);
    await expect(stat(page, 'tubs left')).toHaveText('1');
    const c = await colours(page);
    expect(c.now).toBe(c.tubs);
  });
});

// No service worker here: on WebKit, once it controls the page, page.route stops seeing its
// requests (see import-pints.spec.ts).
test.describe('an empty household', () => {
  test.use({ serviceWorkers: 'block' });

  test('a household with nothing yet sees Your kitchen is ready', async ({ page }) => {
    // The shared test household is never empty, so the server's answer is changed to say so (the
    // conditions themselves are tested in the backend: test_today.py).
    await page.route('**/api/v1/today', async (route) => {
      const response = await route.fetch();
      const body = await response.json();
      await route.fulfill({ response, json: { ...body, first_day: true } });
    });
    await page.goto('/');
    await expect(page.getByRole('heading', { name: 'Your kitchen is ready' })).toBeVisible();
    await expect(page.getByRole('link', { name: /Import a recipe/ }).first()).toBeVisible();
    await expect(page.getByRole('link', { name: /Add what’s in your cupboards/ })).toBeVisible();
    await expect(page.getByRole('link', { name: /Plan a meal/ })).toBeVisible();
    await checkPage(page);
  });
});

// F150: "This week" is a list of seven rows, today first, each with the day, the dinner's name (or the
// day's last meal), how many meals, and a blue Cook mark on a day with cooking; an empty day says
// Nothing planned with "+ Plan", which opens the Plan on that day's week. The plan is the test's
// own (the server's answer is changed), so it does not depend on what other tests left.
test.describe('F150: This week', () => {
  test.use({ serviceWorkers: 'block' });

  const recipeItem = (id: number, name: string, extra: Record<string, unknown> = {}) => ({
    id,
    position: 0,
    kind: 'recipe',
    recipe: { id: id + 500, name, removed: false, photo_url: null, time_minutes: null, kcal: null, serves: 2 },
    tub_id: null,
    ingredient: null,
    kept_name: null,
    servings: null,
    note: null,
    eating: 2,
    cooked: false,
    ...extra,
  });
  const meal = (id: number, date: string, slot_id: number, items: object[]) => ({
    id,
    date,
    slot_id,
    status: 'planned',
    items,
    kcal: null,
    eater_member_ids: [] as number[],
  });

  async function openWithPlan(page: Page) {
    const real = (await (await page.request.get('/api/v1/today')).json()) as { today: string; slots: { id: number; name: string }[] };
    const slot = Object.fromEntries(real.slots.map((s) => [s.name, s.id])) as Record<string, number>;
    const today = real.today;
    const long = Array(6).fill('Roasted aubergine and chickpea stew with preserved lemon and tahini').join(' ');
    const plan = {
      start: today,
      end: addDays(today, 6),
      meals: [
        meal(9001, today, slot.Breakfast!, [recipeItem(9101, 'Upma')]),
        meal(9002, today, slot.Lunch!, [recipeItem(9102, 'Lentil soup')]),
        meal(9003, today, slot.Dinner!, [recipeItem(9103, 'Banana bread')]),
        meal(9004, addDays(today, 1), slot.Lunch!, [recipeItem(9104, 'Lemon rice')]),
        meal(9005, addDays(today, 1), slot.Dinner!, [recipeItem(9105, long)]),
        meal(9006, addDays(today, 3), slot.Dinner!, [
          { ...recipeItem(9106, ''), kind: 'tub', recipe: null, tub_id: 9201, eating: null },
        ]),
        meal(9007, addDays(today, 4), slot.Snack!, [recipeItem(9107, 'Fruit')]),
      ],
      batch_cooks: [
        {
          id: 9301, recipe_id: 1, recipe_name: 'Sambar', cook_meal_id: 9005, cooked_on: addDays(today, 1),
          tub_count: 1, pattern: 'pick', prep_note: null, colour: null, portions: 2, portions_left: 0,
        },
      ],
      tubs: [
        { id: 9201, batch_id: 9301, amount_quarters: 4, number: 1, place_id: null, place_kind: 'fridge', member_id: null, use_by: addDays(today, 5) },
      ],
    };
    await page.route('**/api/v1/today', async (route) => {
      const response = await route.fetch();
      const body = await response.json();
      await route.fulfill({ response, json: { ...body, first_day: false, waiting: [], plan } });
    });
    await page.goto('/');
    return { today, long };
  }

  const row = (page: Page, day: string) => page.getByTestId(`week-${day}`);

  test('seven rows from today: the dinner’s name, the meal count, a Cook mark, and Nothing planned', async ({ page }) => {
    const { today, long } = await openWithPlan(page);
    const rows = page.locator('section.week li');
    await expect(rows).toHaveCount(7);
    await expect(rows.first()).toHaveAttribute('data-testid', `week-${today}`);

    await expect(row(page, today)).toContainText('Today');
    await expect(row(page, today)).toContainText('Banana bread');
    await expect(row(page, today)).toContainText('3 meals');
    // The day sits beside its name (one line of the list, like the other rows), not above it.
    const [dow, dinner] = [await row(page, today).locator('.dow').boundingBox(), await row(page, today).locator('.name').boundingBox()];
    expect(dinner!.x).toBeGreaterThan(dow!.x + dow!.width - 1);
    expect(Math.abs(dinner!.y - dow!.y)).toBeLessThan(30);
    await expect(row(page, today).getByText('Cook', { exact: true })).toHaveCount(1); // a fresh recipe is cooking

    const tomorrow = row(page, addDays(today, 1));
    await expect(tomorrow).toContainText('2 meals');
    await expect(tomorrow.getByText('Cook', { exact: true })).toBeVisible();

    // A tub: its recipe's name, and "tub · 1 meal"; nothing to cook.
    const tub = row(page, addDays(today, 3));
    await expect(tub).toContainText('Sambar');
    await expect(tub).toContainText('tub · 1 meal');
    await expect(tub.getByText('Cook', { exact: true })).toHaveCount(0);

    // No dinner: the day's last meal.
    await expect(row(page, addDays(today, 4))).toContainText('Fruit');

    // An empty day.
    const empty = row(page, addDays(today, 2));
    await expect(empty).toContainText('Nothing planned');
    await expect(empty.getByRole('link', { name: '+ Plan' })).toBeVisible();

    // Rows are at least 44 px; a long name ends with an ellipsis; nothing runs sideways.
    for (let i = 0; i < 7; i++) {
      const box = (await rows.nth(i).boundingBox())!;
      expect(box.height, `row ${i}`).toBeGreaterThanOrEqual(44);
    }
    const name = tomorrow.locator('.name');
    await expect(name).toHaveText(long);
    const cut = await name.evaluate((el) => ({ over: el.scrollWidth > el.clientWidth, style: getComputedStyle(el).textOverflow }));
    expect(cut).toEqual({ over: true, style: 'ellipsis' });
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  });

  test('+ Plan opens the Plan on that day’s week', async ({ page }) => {
    const { today } = await openWithPlan(page);
    const day = addDays(today, 2); // the Monday after today (a Saturday)
    await row(page, day).getByRole('link', { name: '+ Plan' }).click();
    await expect(page).toHaveURL(new RegExp(`/plan\\?day=${day}$`));
    await expect(page.getByRole('button', { name: 'Today', exact: true })).toBeEnabled(); // not today's week
    await expect(page.locator('.range')).toContainText(String(Number(day.slice(8))));
  });

  /** Meals at breakfast, lunch and dinner on today+2 … today+6, so the week's list is long. */
  async function longWeek(page: Page, today: string) {
    const slots = (await (await page.request.get('/api/v1/meal-slots')).json()).meal_slots as { id: number; name: string }[];
    const slot = Object.fromEntries(slots.map((x) => [x.name, x.id])) as Record<string, number>;
    const recipe = (await call(page, 'POST', '/recipes', { name: `Pongal ${stamp()}`, serves: 2, lines: [] })).id as number;
    const meals: number[] = [];
    for (let n = 2; n <= 6; n++)
      for (const name of ['Breakfast', 'Lunch', 'Dinner']) {
        const made = await call(page, 'POST', '/plan/items', { date: addDays(today, n), slot_id: slot[name], recipe_id: recipe });
        if (!meals.includes(made.meal_id)) meals.push(made.meal_id);
      }
    return meals;
  }

  test('F169: + Plan opens the Plan scrolled to that day in the list, and picks it in the phone’s Month', async ({ page }) => {
    const { today } = await openWithPlan(page);
    const meals = await longWeek(page, today);
    const day = addDays(today, 6); // the Friday, the last of the five days
    try {
      // The list (Eat) first: on a phone it is the Plan's own choice, on a computer it is kept here.
      await page.evaluate(() => localStorage.setItem('mealwright.plan-show', 'eat'));
      await page.setViewportSize({ width: page.viewportSize()!.width, height: 480 }); // so the week needs scrolling
      await page.goto('/');
      await row(page, day).getByRole('link', { name: '+ Plan' }).click();
      await expect(page).toHaveURL(new RegExp(`/plan\\?day=${day}$`));
      const section = (d: string) => page.locator(`[data-plan-day="${d}"]`);
      await expect(section(day)).toBeInViewport();
      await expect(section(addDays(today, 2))).not.toBeInViewport(); // the Monday was scrolled past
      // The phone's Month picks that day rather than the 1st or today.
      if (test.info().project.name.includes('phone')) {
        await page.getByRole('group', { name: 'View' }).getByRole('button', { name: 'Month' }).click();
        const cell = page.getByRole('group', { name: 'Days' }).getByRole('button', { name: new RegExp(`^\\w+ ${Number(day.slice(8))}\\b`) });
        await expect(cell).toHaveAttribute('aria-pressed', 'true');
      }
    } finally {
      await page.evaluate(() => localStorage.removeItem('mealwright.plan-show'));
      for (const id of meals) await page.request.fetch(`/api/v1/plan/meals/${id}`, { method: 'DELETE', headers: key(), maxRetries: 3 });
    }
  });
});
