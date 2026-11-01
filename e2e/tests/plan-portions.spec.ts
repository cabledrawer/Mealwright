import { test, expect, type Page } from './clock.ts';
import { expectNoAxeViolations, expectNoSidewaysScroll, expectTouchTargets, inTheme, isPhone, setAccountTheme } from './a11y.ts';

// The phone opens the Plan on Eat; these tests are about the cards, which are Both (0.7, P2).
test.beforeEach(async ({ page }) => {
  await page.addInitScript(() => localStorage.setItem('mealwright.plan-show', 'both'));
});

// Portions, Serves - N + and Note (0.7, P1): "Leftovers on…" with several meals ticked and the
// portions left, "No portions left" with Cook more and Add anyway, Serves in the meal's menu
// (also on a meal planned before the update, which has no number set), who's eating, and a
// "+ Note" when adding to a meal. Runs on Chromium, computer and phone, both themes, and the
// sheets at 200% text.
//
// The two projects share one server, and every test plans in a week of its own (far from the
// other plan tests'). The tests' day is a Saturday.

const key = () => ({ 'idempotency-key': crypto.randomUUID() });

async function call(page: Page, method: 'POST' | 'PUT' | 'DELETE' | 'PATCH', path: string, data?: object) {
  const response = await page.request.fetch(`/api/v1${path}`, { method, data, headers: key() });
  expect(response.ok(), `${method} ${path}: ${await response.text()}`).toBe(true);
  return (await response.json()) as Record<string, any>;
}

const INDEX: Record<string, number> = { 'desktop 0.7 portions': 0, 'phone 0.7 portions': 1, 'webkit 0.7 portions': 2 };
const projectIndex = () => INDEX[test.info().project.name] ?? 0;
/** A Saturday far from the other plan tests' weeks: this project's own, and the test's own (k 0 to 6; the last weeks the plan allows). */
const far = (today: string, k: number) => addDays(today, 7 * (84 + projectIndex() * 7 + k));
const stamp = () => `${test.info().project.name.replace(/\W/g, '')}${Date.now().toString(36)}`;

function addDays(iso: string, days: number): string {
  const d = new Date(`${iso}T12:00:00Z`);
  d.setUTCDate(d.getUTCDate() + days);
  return d.toISOString().slice(0, 10);
}
const weekdayLong = new Intl.DateTimeFormat('en-GB', { weekday: 'long', timeZone: 'UTC' });
const weekdayShort = new Intl.DateTimeFormat('en-GB', { weekday: 'short', timeZone: 'UTC' });
const monthLong = new Intl.DateTimeFormat('en-GB', { month: 'long', timeZone: 'UTC' });
const dayName = (iso: string) => {
  const d = new Date(`${iso}T12:00:00Z`);
  return `${weekdayLong.format(d)} ${d.getUTCDate()} ${monthLong.format(d)}`;
};
/** "Sun 18": how the sheet writes a day. */
const dayWords = (iso: string) => {
  const d = new Date(`${iso}T12:00:00Z`);
  return `${weekdayShort.format(d)} ${d.getUTCDate()}`;
};

async function setup(page: Page) {
  const household = (await (await page.request.get('/api/v1/household')).json()) as { today: string };
  const list = (await (await page.request.get('/api/v1/meal-slots')).json()) as { id: number; name: string }[];
  const slot = Object.fromEntries(list.map((s) => [s.name, s.id])) as Record<string, number>;
  const me = (await (await page.request.get('/api/v1/me')).json()) as { id: number; name: string };
  return { today: household.today, slot, me };
}

const makeRecipe = async (page: Page, name: string, serves = 4) =>
  (await call(page, 'POST', '/recipes', { name, serves })).id as number;
const planned = async (page: Page, recipeId: number, day: string, slotId: number) =>
  (await call(page, 'POST', '/plan/items', { date: day, slot_id: slotId, recipe_id: recipeId })) as { item_id: number; meal_id: number };

async function planRange(page: Page, from: string, to: string) {
  return (await (await page.request.get(`/api/v1/plan?from=${from}&to=${to}`)).json()) as Record<string, any>;
}

async function openWeekOf(page: Page, today: string, day: string) {
  await page.goto('/plan');
  const ahead = Math.round((new Date(`${day}T12:00:00Z`).getTime() - new Date(`${today}T12:00:00Z`).getTime()) / 86_400_000 / 7);
  for (let i = 0; i < ahead; i++) await page.getByRole('button', { name: 'Next week' }).click();
}

const cell = (page: Page, day: string, slotId: number) => page.getByTestId(`cell-${day}-${slotId}`);

/** The card or row of a meal: on a computer a card in its cell, on a phone a row in its day. */
function mealButton(page: Page, day: string, slotName: string, slotId: number, text: string) {
  return isPhone(page)
    ? page.getByRole('region', { name: dayName(day) }).getByRole('button', { name: new RegExp(`^${slotName}: .*${text}`) })
    : cell(page, day, slotId).getByRole('button', { name: new RegExp(`^${text}`) }).first();
}

const scriptErrors: string[] = [];
test.beforeEach(async ({ page }) => {
  scriptErrors.length = 0;
  page.on('pageerror', (error) => scriptErrors.push(error.message));
  await setAccountTheme(page, 'auto');
});
test.afterEach(() => {
  expect(scriptErrors, 'the page raised no script errors').toEqual([]);
});

/** A batch made through the API, cooked at dinner on `day`, with `tubs` tubs and `placed` of them in meals. */
async function batchOf(page: Page, name: string, day: string, dinner: number, tubs: number, pattern: 'pick' | 'lunches' = 'pick') {
  const meal = await planned(page, await makeRecipe(page, name), day, dinner);
  const made = await call(page, 'POST', `/plan/items/${meal.item_id}/batch`, { tub_count: tubs, pattern });
  return { meal, batch: made.batch_id as number };
}

async function openLeftovers(page: Page, day: string, dinner: number, name: string) {
  await mealButton(page, day, 'Dinner', dinner, name).click();
  const menu = page.getByRole('dialog', { name });
  await menu.getByRole('button', { name: 'Leftovers on…' }).click();
  await expect(menu.getByText(`Leftovers of ${name}`)).toBeVisible();
  return menu;
}

// --- Leftovers on… --------------------------------------------------------------------------------

test('Leftovers on… ticks several meals at once and shows the portions left', async ({ page }) => {
  const { today, slot } = await setup(page);
  const name = `Biryani ${stamp()}`;
  const day = far(today, 0);
  const sun = addDays(day, 1);
  const mon = addDays(day, 2);
  await batchOf(page, name, day, slot.Dinner, 3); // 3 tubs, none in a meal yet: 1 + 3 portions
  await openWeekOf(page, today, day);
  const menu = await openLeftovers(page, day, slot.Dinner, name);
  await expect(menu.getByText(`Cooked ${dayWords(day)} · dinner · keeps in the fridge until ${dayWords(addDays(day, 3))}`)).toBeVisible();
  await expect(menu.getByText(`Makes 4 · 1 eaten ${weekdayShort.format(new Date(`${day}T12:00:00Z`))} · 0 tubs planned · 3 left`)).toBeVisible();
  // Nothing on the cook day (dinner is the last meal) or the day after the use-by.
  await expect(menu.getByRole('checkbox', { name: new RegExp(`^${dayWords(day)} `) })).toHaveCount(0);
  await expect(menu.getByRole('checkbox', { name: new RegExp(`^${dayWords(addDays(day, 4))} `) })).toHaveCount(0);
  await menu.getByRole('checkbox', { name: `${dayWords(sun)} · Lunch` }).check();
  await menu.getByRole('checkbox', { name: `${dayWords(mon)} · Dinner` }).check();
  await expect(menu.getByText('2 picked, 1 left')).toBeVisible();
  await expect(menu.getByRole('alert')).toHaveCount(0);
  await menu.getByRole('button', { name: 'Plan 2 tubs' }).click();
  await expect(page.getByRole('status').filter({ hasText: 'leftovers of' })).toBeVisible();
  const tubDays = async () =>
    (await planRange(page, day, addDays(day, 5))).meals.flatMap((m: any) => m.items.filter((i: any) => i.kind === 'tub').map(() => m.date)).sort();
  await expect.poll(tubDays).toEqual([sun, mon]);
  const after = await planRange(page, day, addDays(day, 5));
  expect(after.batch_cooks.find((b: any) => b.recipe_name === name)).toMatchObject({ portions: 4, portions_left: 1 });
  await page.getByRole('button', { name: 'Undo', exact: true }).click();
  await expect.poll(async () => (await planRange(page, day, addDays(day, 5))).batch_cooks[0].portions_left).toBe(3);
});

test('with no portions left it says so, and Cook more makes the batch bigger', async ({ page }) => {
  const { today, slot } = await setup(page);
  const name = `Pulao ${stamp()}`;
  const day = far(today, 1);
  const tue = addDays(day, 3);
  await batchOf(page, name, day, slot.Dinner, 1, 'lunches'); // its one tub is in tomorrow's lunch
  await openWeekOf(page, today, day);
  const menu = await openLeftovers(page, day, slot.Dinner, name);
  await expect(menu.getByText(/Makes 2 · 1 eaten \w+ · 1 tub planned · 0 left/)).toBeVisible();
  await menu.getByRole('checkbox', { name: `${dayWords(tue)} · Lunch` }).check();
  await expect(menu.getByRole('alert')).toHaveText(`No portions left for ${dayWords(tue)} lunch.`);
  await expect(menu.getByText('Makes 3 · list updates')).toBeVisible();
  await expect(menu.getByText('Plans it; the batch stays at 2')).toBeVisible();
  await expect(menu.getByRole('button', { name: 'Plan 1 tub' })).toBeDisabled();
  await menu.getByRole('button', { name: /Cook more/ }).click();
  await menu.getByRole('button', { name: 'Plan 1 tub' }).click();
  await expect(page.getByRole('status').filter({ hasText: 'leftovers of' })).toBeVisible();
  await expect.poll(async () => (await planRange(page, day, addDays(day, 5))).batch_cooks[0].tub_count).toBe(2);
});

test('with no portions left, Add anyway plans the meal and the batch stays the same', async ({ page }) => {
  const { today, slot } = await setup(page);
  const name = `Khichdi ${stamp()}`;
  const day = far(today, 2);
  const tue = addDays(day, 3);
  await batchOf(page, name, day, slot.Dinner, 1, 'lunches');
  await openWeekOf(page, today, day);
  const menu = await openLeftovers(page, day, slot.Dinner, name);
  await menu.getByRole('checkbox', { name: `${dayWords(tue)} · Lunch` }).check();
  await menu.getByRole('button', { name: /Add anyway/ }).click();
  await menu.getByRole('button', { name: 'Plan 1 meal' }).click();
  await expect(page.getByRole('status').filter({ hasText: 'leftovers of' })).toBeVisible();
  await expect.poll(async () => (await planRange(page, day, addDays(day, 5))).meals.find((m: any) => m.date === tue)?.items.length).toBe(1);
  const plan = await planRange(page, day, addDays(day, 5));
  expect(plan.batch_cooks[0]).toMatchObject({ tub_count: 1, portions: 2 });
  expect(plan.meals.find((m: any) => m.date === tue).items[0]).toMatchObject({ kind: 'recipe', servings: 1 });
});

test('Leftovers on… passes the accessibility checks in both themes, and holds at 200% text', async ({ page }) => {
  const { today, slot } = await setup(page);
  const name = `Sambar rice ${stamp()} with a long name that has to wrap inside the sheet`;
  const day = far(today, 3);
  const tue = addDays(day, 3);
  await batchOf(page, name, day, slot.Dinner, 1, 'lunches');
  await openWeekOf(page, today, day);
  const menu = await openLeftovers(page, day, slot.Dinner, name);
  await menu.getByRole('checkbox', { name: `${dayWords(tue)} · Lunch` }).check();
  await expect(menu.getByRole('alert')).toBeVisible();
  for (const theme of ['light', 'dark'] as const) {
    await inTheme(page, theme);
    await expectNoAxeViolations(page, `Leftovers on…, ${theme}`);
  }
  await inTheme(page, 'light');
  if (isPhone(page)) await expectTouchTargets(page);
  await page.evaluate(() => (document.documentElement.style.fontSize = '200%'));
  await expectNoSidewaysScroll(page);
  await expect(menu.getByRole('button', { name: /Cook more/ })).toBeVisible();
  await expect(menu.getByRole('button', { name: /Add anyway/ })).toBeVisible();
  for (const theme of ['light', 'dark'] as const) {
    await inTheme(page, theme);
    await expectNoAxeViolations(page, `Leftovers on… at 200% text, ${theme}`);
  }
  await page.evaluate(() => (document.documentElement.style.fontSize = ''));
  await inTheme(page, 'light');
});

// --- Serves - N + ---------------------------------------------------------------------------------

test('Serves - N + in the meal’s menu works on a meal planned before the update', async ({ page }) => {
  const { today, slot } = await setup(page);
  const name = `Sambar ${stamp()}`;
  const day = far(today, 4);
  // Planned with no number, as every meal was before 0.7: the recipe's own Serves (4) is meant.
  const meal = await planned(page, await makeRecipe(page, name, 4), day, slot.Dinner);
  expect(((await planRange(page, day, day)).meals[0].items[0]).servings).toBeNull();
  await openWeekOf(page, today, day);
  await mealButton(page, day, 'Dinner', slot.Dinner, name).click();
  const menu = page.getByRole('dialog', { name });
  const serves = menu.getByRole('group', { name: 'Serves' });
  await expect(serves.getByRole('status')).toHaveText('4');
  await serves.getByRole('button', { name: 'One more' }).click();
  await serves.getByRole('button', { name: 'One more' }).click();
  await expect(serves.getByRole('status')).toHaveText('6');
  // One change a moment after the last press.
  await expect.poll(async () => (await planRange(page, day, day)).meals[0].items[0].servings).toBe(6);
  await expect(page.getByRole('status').filter({ hasText: `Set ${name} for 6` })).toBeVisible();
  for (const theme of ['light', 'dark'] as const) {
    await inTheme(page, theme);
    await expectNoAxeViolations(page, `the meal’s menu with Serves, ${theme}`);
  }
  await inTheme(page, 'light');
  // The same menu holds at 200% text, and on a phone its buttons are 44 px.
  if (isPhone(page)) await expectTouchTargets(page);
  await page.evaluate(() => (document.documentElement.style.fontSize = '200%'));
  await expectNoSidewaysScroll(page);
  await expect(menu.getByRole('button', { name: 'One more' })).toBeVisible();
  await page.evaluate(() => (document.documentElement.style.fontSize = ''));
  await page.getByRole('button', { name: 'Undo', exact: true }).click();
  await expect.poll(async () => (await planRange(page, day, day)).meals[0].items[0].servings).toBeNull();
  expect(meal.item_id).toBeTruthy();
});

test('who’s eating: shown when the household has more than one login, by sign-in, nobody ticked is everyone', async ({ page }) => {
  const { today, slot, me } = await setup(page);
  const name = `Rasam ${stamp()}`;
  const day = far(today, 5);
  const meal = await planned(page, await makeRecipe(page, name), day, slot.Dinner);
  // The test household has one login; show a second person (who isn't really there) to see the
  // chips. Only the real login is ticked, so the server takes it.
  await page.route('**/api/v1/plan/people', (route) =>
    route.fulfill({ json: [{ login_id: me.id, name: me.name }, { login_id: 987654, name: 'Wren' }] }),
  );
  await openWeekOf(page, today, day);
  await mealButton(page, day, 'Dinner', slot.Dinner, name).click();
  const menu = page.getByRole('dialog', { name });
  const who = menu.getByRole('group', { name: 'Who’s eating?' });
  await expect(who.getByRole('button', { name: 'Everyone' })).toHaveAttribute('aria-pressed', 'true');
  await who.getByRole('button', { name: me.name }).click();
  await expect(who.getByRole('button', { name: 'Everyone' })).toHaveAttribute('aria-pressed', 'false');
  await expect.poll(async () => (await planRange(page, day, day)).meals[0].eater_login_ids).toEqual([me.id]);
  await who.getByRole('button', { name: 'Everyone' }).click();
  await expect.poll(async () => (await planRange(page, day, day)).meals[0].eater_login_ids).toEqual([]);
  expect(meal.meal_id).toBeTruthy();
});

// --- Note -----------------------------------------------------------------------------------------

test('+ Note adds "Eating out" to a meal: it counts as filled, with no Serves or Leftovers', async ({ page }) => {
  const { today, slot } = await setup(page);
  const day = far(today, 6);
  await openWeekOf(page, today, day);
  if (isPhone(page)) {
    await page.getByRole('region', { name: dayName(day) }).getByRole('button', { name: /^\+ Add dinner|^Add to Dinner/ }).first().click();
  } else {
    await cell(page, day, slot.Dinner).getByRole('button', { name: /^Add to Dinner|^\+ Add/ }).first().click();
  }
  const add = page.getByRole('dialog', { name: 'Add to the plan' });
  await add.getByRole('button', { name: '+ Note' }).click();
  await add.getByRole('textbox', { name: 'Note' }).fill('At Amma’s');
  for (const theme of ['light', 'dark'] as const) {
    await inTheme(page, theme);
    await expectNoAxeViolations(page, `+ Note, ${theme}`);
  }
  await inTheme(page, 'light');
  await add.getByRole('button', { name: 'Add note' }).click();
  await expect(page.getByRole('status').filter({ hasText: 'Planned At Amma’s for Dinner' })).toBeVisible();
  await expect.poll(async () => (await planRange(page, day, day)).meals[0]?.items).toMatchObject([
    { kind: 'note', note: 'At Amma’s', recipe: null },
  ]);
  await mealButton(page, day, 'Dinner', slot.Dinner, 'At Amma’s').click();
  const menu = page.getByRole('dialog', { name: 'At Amma’s' });
  await expect(menu.getByRole('button', { name: 'Move to…' })).toBeVisible();
  await expect(menu.getByRole('button', { name: 'Copy to…' })).toBeVisible();
  await expect(menu.getByRole('button', { name: 'Leftovers on…' })).toHaveCount(0);
  await expect(menu.getByRole('group', { name: 'Serves' })).toHaveCount(0);
  await menu.getByRole('button', { name: 'Remove' }).click();
  await expect.poll(async () => (await planRange(page, day, day)).meals.length).toBe(0);
});

test('+ Note: a quick note is one tap', async ({ page }) => {
  const { today, slot } = await setup(page);
  const day = addDays(far(today, 6), 1);
  await openWeekOf(page, today, day);
  if (isPhone(page)) {
    await page.getByRole('region', { name: dayName(day) }).getByRole('button', { name: /^\+ Add dinner|^Add to Dinner/ }).first().click();
  } else {
    await cell(page, day, slot.Dinner).getByRole('button', { name: /^Add to Dinner|^\+ Add/ }).first().click();
  }
  const add = page.getByRole('dialog', { name: 'Add to the plan' });
  await add.getByRole('button', { name: '+ Note' }).click();
  await add.getByRole('button', { name: 'Takeaway' }).click();
  await expect.poll(async () => (await planRange(page, day, day)).meals[0]?.items[0]?.note).toBe('Takeaway');
});

// --- The drop zone and the one-day picker also ask ----------------------------------------------

test('a "Leftovers here" drop with no portion left asks Cook more or Add anyway', async ({ page }) => {
  test.skip(isPhone(page) || test.info().project.use.browserName === 'webkit', 'a mouse drag, on Chromium');
  const { today, slot } = await setup(page);
  const name = `Upma ${stamp()}`;
  const day = far(today, 2);
  const sun = addDays(day, 1);
  await batchOf(page, name, day, slot.Dinner, 1, 'lunches'); // its one tub is in Sunday's lunch
  await openWeekOf(page, today, day);
  const from = mealButton(page, day, 'Dinner', slot.Dinner, name);
  const to = cell(page, sun, slot.Dinner);
  await from.scrollIntoViewIfNeeded();
  const a = (await from.boundingBox())!;
  await page.mouse.move(a.x + a.width / 2, a.y + a.height / 2);
  await page.mouse.down();
  await page.mouse.move(a.x + a.width / 2 + 12, a.y + a.height / 2 + 12, { steps: 3 });
  await to.scrollIntoViewIfNeeded();
  const b = (await to.boundingBox())!;
  await page.mouse.move(b.x + b.width / 2, b.y + b.height * 0.2, { steps: 10 });
  const zone = to.locator('[data-drop-zone="leftovers"]');
  await expect(zone).toBeVisible();
  const z = (await zone.boundingBox())!;
  await page.mouse.move(z.x + z.width / 2, z.y + z.height / 2, { steps: 4 });
  await page.mouse.up();
  const ask = page.getByRole('dialog', { name: 'No portions left' });
  await expect(ask.getByRole('alert')).toHaveText(`No portions left for ${dayWords(sun)} dinner.`);
  for (const theme of ['light', 'dark'] as const) {
    await inTheme(page, theme);
    await expectNoAxeViolations(page, `No portions left, ${theme}`);
  }
  await inTheme(page, 'light');
  // Nothing was planned while it asked.
  expect((await planRange(page, day, addDays(day, 5))).batch_cooks.find((b: any) => b.recipe_name === name).tub_count).toBe(1);
  await ask.getByRole('button', { name: /Cook more/ }).click();
  await expect.poll(async () => (await planRange(page, day, addDays(day, 5))).batch_cooks.find((b: any) => b.recipe_name === name).tub_count).toBe(2);
});
