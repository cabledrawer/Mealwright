import { test, expect, type Locator, type Page } from './clock.ts';
import { checkPage, expectNoSidewaysScroll, isPhone } from './a11y.ts';

// The phone opens the Plan on Eat; these tests are about the cards, which are Both (0.7, P2).
test.beforeEach(async ({ page }) => {
  await page.addInitScript(() => localStorage.setItem('mealwright.plan-show', 'both'));
});

// "Cooked it", the review (0.7, K3), against the real server: what comes out of the pantry, a Use
// switch and an amount you can change on every row, one Confirm and one Undo, a tab for each
// recipe of a meal, "Bought some — used them", the question in the pantry's unit (F106), a Cook
// once batch, and the screen at 200% text in both themes. Runs on Chromium (phone and computer)
// and WebKit (computer), see playwright.config.ts.
//
// The three projects share one server, so every test makes ingredients and recipes with names of
// its own and plans in days of its own (the Plan tests in the weeks before the one Today asks about).

const key = () => ({ 'idempotency-key': crypto.randomUUID() });
const stamp = () => `${test.info().project.name.replace(/\W/g, '')}${Date.now().toString(36)}`;

async function call(page: Page, method: 'POST' | 'PUT' | 'DELETE' | 'PATCH', path: string, data?: object) {
  const response = await page.request.fetch(`/api/v1${path}`, { method, data, headers: key() });
  expect(response.ok(), `${method} ${path}: ${await response.text()}`).toBe(true);
  return (await response.json()) as Record<string, any>;
}

function addDays(iso: string, days: number): string {
  const d = new Date(`${iso}T12:00:00Z`);
  d.setUTCDate(d.getUTCDate() + days);
  return d.toISOString().slice(0, 10);
}

const INDEX: Record<string, number> = { 'desktop 0.7 cooked': 0, 'phone 0.7 cooked': 1, 'webkit 0.7 cooked': 2 };
const projectIndex = () => INDEX[test.info().project.name] ?? 0;

async function setup(page: Page) {
  const today = ((await (await page.request.get('/api/v1/household')).json()) as { today: string }).today;
  const slots = (await (await page.request.get('/api/v1/meal-slots')).json()) as { id: number; name: string }[];
  const slot = Object.fromEntries(slots.map((s) => [s.name, s.id])) as Record<string, number>;
  return {
    today,
    slot,
    food: async (name: string, extra: object = {}) =>
      (await call(page, 'POST', '/foods', { name, counted_as: 'weight', ...extra })).food.id as number,
    stock: (foodId: number, amount: number, unit = 'g') =>
      call(page, 'POST', '/stock', { food_id: foodId, amount: { amount, unit } }),
    recipe: async (name: string, lines: object[]) => (await call(page, 'POST', '/recipes', { name, serves: 4, lines })).id as number,
    plan: async (recipeId: number, day: string, slotId: number) =>
      (await call(page, 'POST', '/plan/items', { date: day, slot_id: slotId, recipe_id: recipeId })) as { item_id: number; meal_id: number },
  };
}

const line = (foodId: number, words: string, amount?: number, unit?: string) => ({ words, food_id: foodId, amount, unit });

/** How much of an ingredient is in the pantry, in every place. */
async function have(page: Page, name: string): Promise<number> {
  const data = (await (await page.request.get(`/api/v1/pantry?q=${encodeURIComponent(name)}`)).json()) as {
    places: { groups: { food: { name: string }; stock: { amount: number } }[] }[];
  };
  return data.places.flatMap((p) => p.groups).filter((g) => g.food.name === name).reduce((n, g) => n + g.stock.amount, 0);
}

/** Anything left waiting by another test is answered first, so a test's meal is the card. */
async function clearWaiting(page: Page) {
  const read = (await (await page.request.get('/api/v1/today')).json()) as { waiting: { meal_id: number }[] };
  for (const w of read.waiting) await call(page, 'POST', `/plan/meals/${w.meal_id}/didnt`);
}

/** A day that Today asks about (4 to 6 days back: today.spec uses 1 to 3), of this project's own. */
const waitingDay = (today: string) => addDays(today, -(4 + projectIndex()));
/** A day in the weeks before, of this project's own: `week` 0 is 15 days back, 1 is 22, 2 is 29. */
const pastDay = (today: string, week: number) => addDays(today, -(15 + 7 * week + projectIndex()));

const card = (page: Page) => page.getByTestId('did-you-cook');
const review = (page: Page, name: string) => page.getByRole('dialog', { name: `Cooked ${name}` });
const confirm = (dialog: Locator) => dialog.getByRole('button', { name: 'Confirm · update pantry' });
const rowOf = (dialog: Locator, name: string) => dialog.getByTestId('cook-row').filter({ hasText: name });

async function openToday(page: Page, name: string) {
  await page.goto('/');
  await expect(card(page).getByText(`Did you cook ${name}?`)).toBeVisible();
  await card(page).getByRole('button', { name: 'Cooked it' }).click();
}

test('Today: the review shows what comes out, Confirm takes it, one Undo gives it back', async ({ page }) => {
  const k = await setup(page);
  await clearWaiting(page);
  const s = stamp();
  const dal = await k.food(`Toor dal ${s}`);
  const salt = await k.food(`Salt ${s}`, { staple: true });
  await k.stock(dal, 800);
  const name = `Sambar ${s}`;
  await k.plan(await k.recipe(name, [line(dal, 'toor dal', 200, 'g'), line(salt, 'salt', 1, 'g')]), waitingDay(k.today), k.slot.Dinner);

  await openToday(page, name);
  const dialog = review(page, name);
  await expect(dialog.getByRole('group', { name: 'Portions cooked' })).toBeVisible();
  await expect(rowOf(dialog, `Toor dal ${s}`)).toContainText('800 → 600 g');
  await expect(rowOf(dialog, `Toor dal ${s}`)).toContainText('−200 g');
  await expect(dialog.getByText('Staples · not counted')).toBeVisible();
  await expect(dialog.getByText(`Salt ${s}`)).toBeVisible();
  await expect(dialog.getByText('1 ingredient will change')).toBeVisible();
  await checkPage(page); // axe in both themes; on the phone also the 44 px targets and no sideways scroll

  // The Use switch leaves it out; the pantry would not change.
  const use = dialog.getByRole('switch', { name: `Take Toor dal ${s} from the pantry` });
  await use.click();
  await expect(dialog.getByText('Nothing will be taken from the pantry')).toBeVisible();
  await use.click();
  await expect(dialog.getByText('1 ingredient will change')).toBeVisible();

  expect(await have(page, `Toor dal ${s}`)).toBe(800); // nothing changes until Confirm
  await confirm(dialog).click();
  await expect(card(page)).toHaveCount(0);
  await expect.poll(() => have(page, `Toor dal ${s}`)).toBe(600);

  // One Undo for the pantry and the meal: the card is back and the packet is whole again.
  await page.getByRole('button', { name: 'Undo', exact: true }).click();
  await expect(card(page).getByText(`Did you cook ${name}?`)).toBeVisible();
  await expect.poll(() => have(page, `Toor dal ${s}`)).toBe(800);
});

test('F125: Undo of Cooked it in Settings → Recent changes also undoes the meal’s Cooked', async ({ page }) => {
  test.skip(projectIndex() !== 0, 'Chromium on the computer; the others share the waiting card');
  const k = await setup(page);
  await clearWaiting(page);
  const s = stamp();
  const dal = await k.food(`Moong dal ${s}`);
  await k.stock(dal, 800);
  const name = `Khichdi ${s}`;
  await k.plan(await k.recipe(name, [line(dal, 'moong dal', 200, 'g')]), waitingDay(k.today), k.slot.Lunch);

  await openToday(page, name);
  await confirm(review(page, name)).click();
  await expect(card(page)).toHaveCount(0);
  await expect.poll(() => have(page, `Moong dal ${s}`)).toBe(600);

  // One "Cooked it", one line in Recent changes, one Undo.
  await page.goto('/settings?section=recent-changes');
  const recent = page.getByRole('region', { name: 'Recent changes' });
  const undo = recent.getByRole('button', { name: `Undo: Cooked ${name} (4 portions)` });
  await expect(undo).toHaveCount(1);
  await undo.click();
  await expect(page.getByRole('status').filter({ hasText: `Undone: Cooked ${name}` })).toContainText(`Undone: Cooked ${name}`);
  await expect.poll(() => have(page, `Moong dal ${s}`)).toBe(800);

  // The meal is asked about again, as after the toast's Undo.
  await page.goto('/');
  await expect(card(page).getByText(`Did you cook ${name}?`)).toBeVisible();
});

test('a counted ingredient can be set by Used or Left, and Portions cooked updates every row', async ({ page }) => {
  const k = await setup(page);
  const s = stamp();
  const onion = await k.food(`Onion ${s}`, { counted_as: 'count' });
  const dal = await k.food(`Dal ${s}`);
  await k.stock(onion, 5, 'count');
  await k.stock(dal, 800);
  const name = `Rasam ${s}`;
  const day = pastDay(k.today, 0);
  await k.plan(await k.recipe(name, [line(onion, 'onions', 2), line(dal, 'dal', 200, 'g')]), day, k.slot.Lunch);

  await openMealOnPlan(page, k.today, day, k.slot.Lunch, 'Lunch', name);
  await page.getByRole('dialog').getByRole('button', { name: 'Cooked it' }).click();
  const dialog = review(page, name);
  await expect(rowOf(dialog, `Onion ${s}`)).toContainText('5 → 3');
  await dialog.getByRole('button', { name: `More Onion ${s}` }).click();
  await expect(rowOf(dialog, `Onion ${s}`)).toContainText('5 → 2½');
  await rowOf(dialog, `Onion ${s}`).getByRole('button', { name: 'Left' }).click();
  // Portions: every row follows.
  await dialog.getByRole('button', { name: 'More portions' }).click();
  await expect(rowOf(dialog, `Dal ${s}`)).toContainText('−250 g');
  await confirm(dialog).click();
  await expect(dialog).toBeHidden();
  // "Left" was chosen with 2.5: the pantry is left with 2½ onions, and 250 g of dal came out.
  await expect.poll(() => have(page, `Onion ${s}`)).toBe(2.5);
  await expect.poll(() => have(page, `Dal ${s}`)).toBe(550);
});

test('"Bought some — used them" changes nothing in the pantry and the cooked record keeps it', async ({ page }) => {
  const k = await setup(page);
  const s = stamp();
  const shallot = await k.food(`Shallot ${s}`, { counted_as: 'count' });
  const name = `Kootu ${s}`;
  const day = pastDay(k.today, 0);
  const made = await k.plan(await k.recipe(name, [line(shallot, 'shallots', 8)]), day, k.slot.Breakfast);

  await openMealOnPlan(page, k.today, day, k.slot.Breakfast, 'Breakfast', name);
  await page.getByRole('dialog').getByRole('button', { name: 'Cooked it' }).click();
  const dialog = review(page, name);
  const row = rowOf(dialog, `Shallot ${s}`);
  await expect(row.getByText('Not in pantry')).toBeVisible();
  await expect(row.getByRole('switch', { name: `Take Shallot ${s} from the pantry` })).toBeDisabled();
  await row.getByRole('button', { name: 'Bought some — used them' }).click();
  await expect(row.getByRole('button', { name: 'Bought some — used them' })).toHaveAttribute('aria-pressed', 'true');
  await confirm(dialog).click();
  await expect(dialog).toBeHidden();
  await expect.poll(() => have(page, `Shallot ${s}`)).toBe(0);
  // Bought some: nothing was put on the shopping list for it.
  const lists = (await (await page.request.get('/api/v1/shopping/lists')).json()) as { lists: { id: string }[] };
  const main = await (await page.request.get(`/api/v1/shopping/lists/${lists.lists[0]!.id}`)).text();
  expect(main).not.toContain(`Shallot ${s}`);
  const record = (await (await page.request.get(`/api/v1/plan/items/${made.item_id}/cooked`)).json()) as {
    snapshot: { choices: { key: string; bought: boolean; used_milli: number }[] };
  };
  expect(record.snapshot.choices.map((c) => [c.bought, c.used_milli])).toEqual([[true, 0]]);
});

test('F106: the question is in the pantry unit, the answer is learned, and next time it is an estimate', async ({ page }) => {
  const k = await setup(page);
  const s = stamp();
  const toor = await k.food(`Jaggery ${s}`); // not in the bundled table: a cup of it is a question
  await k.stock(toor, 2000);
  const first = `Payasam ${s}`;
  const second = `Pongal ${s}`;
  const recipe = (name: string) => k.recipe(name, [line(toor, 'jaggery', 1, 'cup')]);
  const day = pastDay(k.today, 1);
  await k.plan(await recipe(first), day, k.slot.Dinner);
  await k.plan(await recipe(second), day, k.slot.Lunch);

  await openMealOnPlan(page, k.today, day, k.slot.Dinner, 'Dinner', first);
  await page.getByRole('dialog').getByRole('button', { name: 'Cooked it' }).click();
  const dialog = review(page, first);
  const row = rowOf(dialog, `Jaggery ${s}`);
  await expect(row.getByText(`How much Jaggery ${s} did you use?`)).toBeVisible();
  await expect(row.getByText('Recipe says 1 cup jaggery')).toBeVisible();
  // Not answering never blocks: Confirm is there. Answer in grams, the pantry's unit.
  await expect(confirm(dialog)).toBeEnabled();
  await row.getByRole('textbox', { name: /^Your answer/ }).fill('200');
  await row.getByRole('button', { name: 'Use this' }).click();
  await expect(row.getByText('estimate')).toBeVisible();
  await expect(row).toContainText('−200 g');
  await confirm(dialog).click();
  await expect(dialog).toBeHidden();
  await expect.poll(() => have(page, `Jaggery ${s}`)).toBe(1800);

  // The answer was remembered: the next recipe proposes it, marked as an estimate, no question.
  await openMealOnPlan(page, k.today, day, k.slot.Lunch, 'Lunch', second);
  await page.getByRole('dialog').getByRole('button', { name: 'Cooked it' }).click();
  const again = review(page, second);
  await expect(rowOf(again, `Jaggery ${s}`).getByText('estimate')).toBeVisible();
  await expect(rowOf(again, `Jaggery ${s}`)).toContainText('−200 g');
  await expect(again.getByText(`How much Jaggery ${s} did you use?`)).toHaveCount(0);
  // It can be changed.
  await rowOf(again, `Jaggery ${s}`).getByRole('button', { name: /Change how much/ }).click();
  await again.getByRole('textbox', { name: /How much was used/ }).fill('150');
  await expect(rowOf(again, `Jaggery ${s}`)).toContainText('1800 → 1650 g');
  await confirm(again).click();
  await expect(again).toBeHidden();
  await expect.poll(() => have(page, `Jaggery ${s}`)).toBe(1650);
});

/** The week a past day is in is this many "Previous week" taps back from this week (weeks start on Monday). */
function weeksBack(today: string, day: string): number {
  const dow = (new Date(`${today}T12:00:00Z`).getUTCDay() + 6) % 7;
  const start = addDays(today, -dow);
  return Math.max(0, Math.ceil((Date.parse(start) - Date.parse(day)) / 86_400_000 / 7));
}

const weekday = new Intl.DateTimeFormat('en-GB', { weekday: 'long', timeZone: 'UTC' });
const month = new Intl.DateTimeFormat('en-GB', { month: 'long', timeZone: 'UTC' });
const dayName = (iso: string) => {
  const d = new Date(`${iso}T12:00:00Z`);
  return `${weekday.format(d)} ${d.getUTCDate()} ${month.format(d)}`;
};

async function openMealOnPlan(page: Page, today: string, day: string, slotId: number, slotName: string, text: string) {
  await page.goto('/plan');
  for (let i = 0; i < weeksBack(today, day); i++) await page.getByRole('button', { name: 'Previous week' }).click();
  const button = isPhone(page)
    ? page.getByRole('region', { name: dayName(day) }).getByRole('button', { name: new RegExp(`^${slotName}: .*${text}`) })
    : page.getByTestId(`cell-${day}-${slotId}`).getByRole('button', { name: new RegExp(`^${text}`) }).first();
  await button.click();
}

test('Plan: a meal with two recipes has a tab for each, one Confirm and one Undo', async ({ page }) => {
  const k = await setup(page);
  const s = stamp();
  const rice = await k.food(`Rice ${s}`);
  const coconut = await k.food(`Coconut ${s}`);
  await k.stock(rice, 1000);
  await k.stock(coconut, 300);
  const dosa = `Dosa ${s}`;
  const chutney = `Chutney ${s}`;
  const day = addDays(k.today, -(8 + projectIndex() * 2));
  await k.plan(await k.recipe(dosa, [line(rice, 'rice', 300, 'g')]), day, k.slot.Dinner);
  await k.plan(await k.recipe(chutney, [line(rice, 'rice', 200, 'g'), line(coconut, 'coconut', 100, 'g')]), day, k.slot.Dinner);

  await openMealOnPlan(page, k.today, day, k.slot.Dinner, 'Dinner', dosa);
  await page.getByRole('dialog').getByRole('button', { name: 'Cooked it' }).click();
  const dialog = review(page, `${dosa} and ${chutney}`);
  await expect(dialog.getByRole('tab')).toHaveText([dosa, chutney]);
  await expect(rowOf(dialog, `Rice ${s}`)).toContainText('1000 → 700 g');
  await dialog.getByRole('tab', { name: chutney }).click();
  // The second recipe sees what the first leaves: the same grams are never taken twice.
  await expect(rowOf(dialog, `Rice ${s}`)).toContainText('700 → 500 g');
  await expect(rowOf(dialog, `Coconut ${s}`)).toContainText('300 → 200 g');
  await expect(dialog.getByText('3 ingredients will change')).toBeVisible();
  await checkPage(page);
  await confirm(dialog).click();
  await expect(dialog).toBeHidden();
  await expect.poll(() => have(page, `Rice ${s}`)).toBe(500);
  await expect.poll(() => have(page, `Coconut ${s}`)).toBe(200);

  // One Undo for both recipes (and the meal's answer).
  await page.getByRole('button', { name: 'Undo', exact: true }).click();
  await expect.poll(() => have(page, `Rice ${s}`)).toBe(1000);
  await expect.poll(() => have(page, `Coconut ${s}`)).toBe(300);
});

test('Plan: a Cook once batch is cooked once for the cook day and its tubs, and cannot be taken off until Undone', async ({ page }) => {
  const k = await setup(page);
  const s = stamp();
  const dal = await k.food(`Dal ${s}`);
  await k.stock(dal, 2000);
  const name = `Biryani ${s}`;
  const slotName = ['Breakfast', 'Lunch', 'Snack'][projectIndex()]!;
  if (slotName === 'Snack') await call(page, 'PATCH', `/meal-slots/${k.slot.Snack}`, { enabled: true });
  const made = await k.plan(await k.recipe(name, [line(dal, 'dal', 200, 'g')]), k.today, k.slot[slotName]!);
  const batch = (await call(page, 'POST', `/plan/items/${made.item_id}/batch`, { tub_count: 3, pattern: 'pick' })).batch_id as number;
  // A second recipe in the same meal: the meal's recipes go in one call, the batch in another.
  const rice = await k.food(`Rice ${s}`);
  await k.stock(rice, 1000);
  const raita = `Raita ${s}`;
  const raitaItem = await k.plan(await k.recipe(raita, [line(rice, 'rice', 100, 'g')]), k.today, k.slot[slotName]!);

  await openMealOnPlan(page, k.today, k.today, k.slot[slotName]!, slotName, name);
  await page.getByRole('dialog').getByRole('button', { name: 'Cooked it' }).click();
  const dialog = review(page, `${name} and ${raita}`);
  await expect(dialog.getByRole('tab')).toHaveText([name, raita]);
  // One portion for the cook day and one for each tub.
  await expect(dialog.getByRole('group', { name: 'Portions cooked' })).toContainText('4');
  await expect(rowOf(dialog, `Dal ${s}`)).toContainText('2000 → 1800 g');

  // The batch call fails after the meal's worked: the pantry is put back, the screen stays,
  // and a second Confirm works.
  await page.route('**/api/v1/plan/batches/*/cook', (route) =>
    route.fulfill({ status: 409, json: { detail: 'Nope.', code: 'already_cooked' } }),
  );
  await confirm(dialog).click();
  await expect(page.getByText('Couldn’t save “Cooked it”. Nothing was changed. Try again.')).toBeVisible();
  await expect(dialog).toBeVisible();
  expect(await have(page, `Dal ${s}`)).toBe(2000);
  await expect.poll(() => have(page, `Rice ${s}`)).toBe(1000);
  await page.unroute('**/api/v1/plan/batches/*/cook');

  await confirm(dialog).click();
  await expect(dialog).toBeHidden();
  await expect.poll(() => have(page, `Dal ${s}`)).toBe(1800);
  await expect.poll(() => have(page, `Rice ${s}`)).toBe(900);

  // The cooked record is never lost: the batch can't be taken off until "Cooked it" is undone.
  const refused = await page.request.delete(`/api/v1/plan/batches/${batch}`, { headers: key() });
  expect(refused.status()).toBe(409);
  expect(((await refused.json()) as { detail: string }).detail).toMatch(/^This was cooked on .* Undo “Cooked it” first\.$/);
  await page.getByRole('button', { name: 'Undo', exact: true }).click();
  await expect.poll(() => have(page, `Dal ${s}`)).toBe(2000);
  await expect.poll(() => have(page, `Rice ${s}`)).toBe(1000);
  await call(page, 'DELETE', `/plan/batches/${batch}`);
  // Today's meal is left empty again: the F128 test plans a meal of today in the computer's run.
  for (const item of [made.item_id, raitaItem.item_id]) await call(page, 'DELETE', `/plan/items/${item}`);
});

test('the review at 200% text in both themes: nothing scrolls sideways and Confirm stays in reach', async ({ page }) => {
  const k = await setup(page);
  const s = stamp();
  const toor = await k.food(`Jaggery with a very long name that goes on and on ${s}`);
  const dal = await k.food(`Toor dal ${s}`);
  await k.stock(toor, 500);
  await k.stock(dal, 800);
  const name = `Sambar with a long name ${s}`;
  const day = pastDay(k.today, 2);
  await k.plan(await k.recipe(name, [line(toor, 'jaggery', 2, 'cup'), line(dal, 'dal', 200, 'g')]), day, k.slot.Dinner);

  await openMealOnPlan(page, k.today, day, k.slot.Dinner, 'Dinner', name);
  await page.getByRole('dialog').getByRole('button', { name: 'Cooked it' }).click();
  const dialog = review(page, name);
  await expect(dialog.getByText(/did you use\?/)).toBeVisible();
  await checkPage(page); // both themes, with the question open
  await page.evaluate(() => (document.documentElement.style.fontSize = '200%'));
  await expect(dialog.getByRole('button', { name: 'Cancel' }).first()).toBeVisible();
  await expectNoSidewaysScroll(page);
  expect(
    await dialog.evaluate((el) => el.scrollWidth <= el.clientWidth + 1),
    'the review is wider than itself',
  ).toBe(true);
  // The footer's Confirm is in the window, whatever the text size.
  const box = (await confirm(dialog).boundingBox())!;
  const window = page.viewportSize()!;
  expect(box.y + box.height).toBeLessThanOrEqual(window.height + 1);
});

test('Today: a meal eaten today has its own Cooked it, which opens the same review', async ({ page }) => {
  test.skip(projectIndex() !== 0, 'one project plans the dinner of today; the others share the server');
  const k = await setup(page);
  const s = stamp();
  const rice = await k.food(`Rice ${s}`);
  await k.stock(rice, 1000);
  const name = `Pulao ${s}`;
  await k.plan(await k.recipe(name, [line(rice, 'rice', 200, 'g')]), k.today, k.slot.Dinner);
  await page.goto('/');
  const meal = page.getByTestId('today-eating').locator('.card', { hasText: name });
  await meal.getByRole('button', { name: 'Cooked it' }).click();
  const dialog = review(page, name);
  await expect(rowOf(dialog, `Rice ${s}`)).toContainText('1000 → 800 g');
  await confirm(dialog).click();
  await expect(dialog).toBeHidden();
  await expect.poll(() => have(page, `Rice ${s}`)).toBe(800);
  await expect(meal.getByText('Cooked', { exact: true })).toBeVisible();
});

test('F128: on Today, "Eat it on…" for a meal eaten today offers no meal past the tub’s use-by', async ({ page }) => {
  test.skip(projectIndex() !== 0, 'one project plans the days ahead; the others share the server');
  test.setTimeout(90_000); // a plan call for every free meal up to the use-by, and one to take each off
  const k = await setup(page);
  const household = (await (await page.request.get('/api/v1/household')).json()) as { tub_fridge_days: number };
  const useBy = addDays(k.today, household.tub_fridge_days); // the fridge tub's last day
  const s = stamp();
  const rice = await k.food(`Rice ${s}`);
  await k.stock(rice, 1000);
  const name = `Lemon rice ${s}`;
  const mine = [await k.plan(await k.recipe(name, [line(rice, 'rice', 200, 'g')]), k.today, k.slot.Lunch)];
  // Every meal from today's lunch to the use-by is taken, so the next free ones are after it.
  const filler = await k.recipe(`Filler ${s}`, []);
  const plan = (await (await page.request.get(`/api/v1/plan?from=${k.today}&to=${useBy}`)).json()) as {
    meals: { date: string; slot_id: number }[];
  };
  // Other tests on this server switch Snack on (none switches a meal off), so switch it on here too
  // and fill every meal that is on, whatever ran first; today, only the meals after lunch.
  await call(page, 'PATCH', `/meal-slots/${k.slot.Snack}`, { enabled: true });
  const slots = (await (await page.request.get('/api/v1/meal-slots')).json()) as {
    id: number;
    position: number;
    enabled: boolean;
  }[];
  const lunch = slots.find((x) => x.id === k.slot.Lunch)!.position;
  const on = slots.filter((x) => x.enabled);
  try {
    for (let day = k.today; day <= useBy; day = addDays(day, 1))
      for (const { id: slotId, position } of on)
        if (!plan.meals.some((m) => m.date === day && m.slot_id === slotId) && !(day === k.today && position <= lunch))
          mine.push(await k.plan(filler, day, slotId));

    await page.goto('/');
    const meal = page.getByTestId('today-eating').locator('.card', { hasText: name });
    await meal.getByRole('button', { name: 'Cooked it' }).click();
    const dialog = review(page, name);
    await dialog.getByRole('button', { name: 'More tubs' }).click();
    await expect(dialog.getByText(/^Use by /)).toBeVisible();
    // In the fridge: no free meal is on or before the use-by, so there is nothing to offer.
    await expect(dialog.getByText('Eat it on…')).toHaveCount(0);
    // In the freezer the tub keeps for months: the meals after the fridge's use-by are offered.
    await dialog.getByRole('button', { name: 'Freezer' }).click();
    const days = await dialog
      .getByRole('combobox')
      .locator('option')
      .evaluateAll((options) => options.map((o) => (o as HTMLOptionElement).value.split('|')[0]).filter(Boolean));
    expect(days.length).toBeGreaterThan(0);
    for (const day of days) expect(day! > useBy).toBe(true);
    await dialog.getByRole('button', { name: 'Cancel' }).first().click();
    await expect(dialog).toBeHidden();
  } finally {
    for (const made of mine) await call(page, 'DELETE', `/plan/items/${made.item_id}`);
  }
});

test('F160: Today shows a meal cooked in parts one line per recipe, with its own Cooked it, in both themes', async ({ page }) => {
  const k = await setup(page);
  const s = stamp();
  const first = `Banana bread ${s}`;
  const second = `Lentil soup ${s}`;
  const a = await k.plan(await k.recipe(first, []), k.today, k.slot.Breakfast!);
  const b = await k.plan(await k.recipe(second, []), k.today, k.slot.Breakfast!);
  try {
    await page.goto('/');
    const meal = page.getByTestId('today-eating').locator('.card', { hasText: first });
    const lines = meal.getByTestId('today-cooked-parts');
    await expect(lines.locator('li')).toHaveCount(2);
    await expect(meal.getByRole('button', { name: /^Cooked it/ })).toHaveCount(2);
    for (const button of await meal.getByRole('button', { name: /^Cooked it/ }).all())
      expect((await button.boundingBox())!.height).toBeGreaterThanOrEqual(44);
    // The first one: its review is for it alone, and afterwards it has a tick and a Cooked chip.
    await meal.getByRole('button', { name: `Cooked it: ${first}` }).click();
    const dialog = review(page, first);
    await expect(dialog).toBeVisible();
    await expect(dialog.getByText(second)).toHaveCount(0);
    await confirm(dialog).click();
    await expect(dialog).toBeHidden();
    await expect(meal.getByText('1 of 2 cooked')).toBeVisible();
    await expect(lines.locator('li', { hasText: first }).getByText('Cooked', { exact: true })).toBeVisible();
    await expect(meal.getByRole('button', { name: `Cooked it: ${first}` })).toHaveCount(0);
    await expect(meal.getByRole('button', { name: `Cooked it: ${second}` })).toBeVisible();
    await expectNoSidewaysScroll(page);
    await checkPage(page); // both themes
    await meal.getByRole('button', { name: `Cooked it: ${second}` }).click();
    await confirm(review(page, second)).click();
    await expect(meal.getByText('All cooked')).toBeVisible();
    await expect(meal.getByRole('button', { name: /^Cooked it/ })).toHaveCount(0);
  } finally {
    const pantry = (await (await page.request.get('/api/v1/changes?area=pantry')).json()) as {
      changes: { id: number; kind: string; summary: string; can_undo: boolean }[];
    };
    for (const change of pantry.changes.filter((c) => c.kind === 'cooked' && c.can_undo && c.summary.includes(s)))
      await page.request.fetch(`/api/v1/changes/${change.id}/undo`, { method: 'POST', headers: key() });
    for (const made of [a, b]) await call(page, 'DELETE', `/plan/items/${made.item_id}`);
  }
});


test('F163: the Plan menu of a meal cooked in parts lists its recipes with Cooked on the cooked one, says which, and lets the other be removed alone', async ({ page }) => {
  const k = await setup(page);
  const s = stamp();
  const bread = `Banana bread ${s}`;
  const soup = `Lentil soup ${s}`;
  const day = addDays(k.today, -(15 + projectIndex() * 2));
  const a = await k.plan(await k.recipe(bread, []), day, k.slot.Dinner!);
  const b = await k.plan(await k.recipe(soup, []), day, k.slot.Dinner!);
  try {
    // The bread is cooked (the pantry's part and the meal's answer); the soup is not.
    await call(page, 'POST', `/plan/items/${a.item_id}/cook`, { choices: [] });
    await call(page, 'POST', `/plan/meals/${a.meal_id}/cooked`, {});
    await openMealOnPlan(page, k.today, day, k.slot.Dinner!, 'Dinner', bread);
    const sheet = page.getByRole('dialog');
    if (isPhone(page)) {
      // The phone's card is the meal: its recipes are listed, the cooked one tagged.
      const list = sheet.getByTestId('plan-sheet-parts');
      await expect(list.locator('li')).toHaveCount(2);
      await expect(list.locator('li', { hasText: bread }).getByText('Cooked', { exact: true })).toBeVisible();
      await expect(list.locator('li', { hasText: soup }).getByText('Cooked', { exact: true })).toHaveCount(0);
      await expect(sheet.getByTestId('cooked-stays')).toHaveText(`${bread} was cooked. Undo its Cooked it to move or remove it.`);
      await expect(sheet.getByRole('button', { name: 'Move to…' })).toHaveCount(0);
      await expect(sheet.getByRole('button', { name: `Remove ${bread}` })).toHaveCount(0);
      await checkPage(page); // both themes
      await sheet.getByRole('button', { name: `Remove ${soup}` }).click();
    } else {
      // The computer's card is one recipe: the cooked one says so and is locked; the other can go.
      await expect(sheet.getByTestId('cooked-stays')).toHaveText(`${bread} was cooked. Undo its Cooked it to move or remove it.`);
      await expect(sheet.getByRole('button', { name: 'Move to…' })).toHaveCount(0);
      await expect(sheet.getByRole('button', { name: 'Remove', exact: true })).toHaveCount(0);
      await checkPage(page); // both themes
      await page.keyboard.press('Escape');
      await openMealOnPlan(page, k.today, day, k.slot.Dinner!, 'Dinner', soup);
      await expect(page.getByRole('dialog').getByTestId('cooked-stays')).toHaveCount(0);
      await page.getByRole('dialog').getByRole('button', { name: 'Remove', exact: true }).click();
    }
    await expect(page.getByRole('status')).toContainText(`Removed ${soup}`);
    await expect
      .poll(async () => {
        const plan = (await (await page.request.get(`/api/v1/plan?from=${day}&to=${day}`)).json()) as {
          meals: { id: number; items: { id: number }[] }[];
        };
        return plan.meals.filter((m) => m.id === a.meal_id).flatMap((m) => m.items.map((i) => i.id));
      })
      .toEqual([a.item_id]);
  } finally {
    const pantry = (await (await page.request.get('/api/v1/changes?area=pantry')).json()) as {
      changes: { id: number; kind: string; summary: string; can_undo: boolean }[];
    };
    for (const change of pantry.changes.filter((c) => c.kind === 'cooked' && c.can_undo && c.summary.includes(s)))
      await page.request.fetch(`/api/v1/changes/${change.id}/undo`, { method: 'POST', headers: key() });
    for (const made of [a, b]) await page.request.fetch(`/api/v1/plan/items/${made.item_id}`, { method: 'DELETE', headers: key(), maxRetries: 3 });
  }
});

test('F166: Serves in the Plan menu of a meal cooked in parts names the recipe it changes', async ({ page }) => {
  const k = await setup(page);
  const s = stamp();
  const bread = `Banana bread ${s}`;
  const soup = `Lentil soup ${s}`;
  const day = addDays(k.today, -(17 + projectIndex() * 2));
  const a = await k.plan(await k.recipe(bread, []), day, k.slot.Dinner!);
  const b = await k.plan(await k.recipe(soup, []), day, k.slot.Dinner!);
  try {
    await call(page, 'POST', `/plan/items/${a.item_id}/cook`, { choices: [] });
    await call(page, 'POST', `/plan/meals/${a.meal_id}/cooked`, {});
    await openMealOnPlan(page, k.today, day, k.slot.Dinner!, 'Dinner', soup);
    const sheet = page.getByRole('dialog');
    // The one still to cook is the one Serves changes, and the label says so.
    await expect(sheet.getByRole('group', { name: `Serves · ${soup}` })).toBeVisible();
    await expect(sheet.getByRole('group', { name: 'Serves', exact: true })).toHaveCount(0);
    await expect(sheet.getByText(`Serves · ${soup}`, { exact: true })).toBeVisible();
  } finally {
    const pantry = (await (await page.request.get('/api/v1/changes?area=pantry')).json()) as {
      changes: { id: number; kind: string; summary: string; can_undo: boolean }[];
    };
    for (const change of pantry.changes.filter((c) => c.kind === 'cooked' && c.can_undo && c.summary.includes(s)))
      await page.request.fetch(`/api/v1/changes/${change.id}/undo`, { method: 'POST', headers: key() });
    for (const made of [a, b]) await page.request.fetch(`/api/v1/plan/items/${made.item_id}`, { method: 'DELETE', headers: key(), maxRetries: 3 });
  }
});

test('F170: a recipe with no Serves has no Portions cooked and says how to scale it', async ({ page }) => {
  const k = await setup(page);
  await clearWaiting(page);
  const name = `Sandwich ${stamp()}`;
  const recipe = (await call(page, 'POST', '/recipes', { name, serves: null, lines: [] })).id as number; // no Serves
  // Breakfast: the waiting day's Dinner and Lunch are cooked by the tests above (F125 on the computer).
  const planned = await k.plan(recipe, waitingDay(k.today), k.slot.Breakfast!);
  try {
    await openToday(page, name);
    const dialog = review(page, name);
    await expect(dialog.getByText('Add Serves to the recipe to scale it.')).toBeVisible();
    await expect(dialog.getByRole('group', { name: 'Portions cooked' })).toHaveCount(0);
    await expect(dialog.getByText('as planned')).toHaveCount(0);
    await checkPage(page); // both themes
  } finally {
    await page.request.fetch(`/api/v1/plan/meals/${planned.meal_id}/didnt`, { method: 'POST', headers: key() });
  }
});
