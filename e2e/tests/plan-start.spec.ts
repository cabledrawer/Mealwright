import { test, expect, type Page } from './clock.ts';
import { checkPage, setAccountTheme } from './a11y.ts';

// The plan works backwards (0.8 M3, F124; cabledrawer 31 Oct and 9 Nov): adding a recipe with a long
// wait asks when it will be started (Plan it on the recipe page), the meal's menu changes the
// time, Today says "Start tonight at 21:00" with Start it in Cook mode and Done already, and
// Cook mode on day two opens after the step that waited, with the steps up to it folded. Runs on
// Chromium (phone and computer) and on WebKit (computer), see playwright.config.ts.
//
// The server's clock is the tests' fixed day (clock.ts): Saturday 17 October 2026, 10:00 in
// London. Each project plans on days of its own (tomorrow plus its own number), in the Breakfast
// meal, and every test takes what it planned off the plan again.

const key = () => ({ 'idempotency-key': crypto.randomUUID() });

async function call(page: Page, method: 'POST' | 'PUT' | 'DELETE' | 'PATCH', path: string, data?: object) {
  const response = await page.request.fetch(`/api/v1${path}`, { method, data, headers: key() });
  expect(response.ok(), `${method} ${path}: ${await response.text()}`).toBe(true);
  return (await response.json()) as Record<string, any>;
}

const INDEX: Record<string, number> = { 'desktop 0.8 plan start': 0, 'phone 0.8 plan start': 1, 'webkit 0.8 plan start': 2 };
const projectIndex = () => INDEX[test.info().project.name] ?? 0;
const stamp = () => `${test.info().project.name.replace(/\W/g, '')}${Date.now().toString(36)}${Math.floor(Math.random() * 1296).toString(36)}`;

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
const dayShort = (iso: string) => weekdayShort.format(new Date(`${iso}T12:00:00Z`));

async function setup(page: Page) {
  // The household's time zone is the admin's browser's, kept the first time it is sent: say it
  // here so the times read the same whichever test comes first (the server's clock is London's).
  await call(page, 'POST', '/household/from-browser', { time_zone: 'Europe/London' });
  const household = (await (await page.request.get('/api/v1/household')).json()) as { today: string };
  const list = (await (await page.request.get('/api/v1/meal-slots')).json()) as { id: number; name: string }[];
  const slot = Object.fromEntries(list.map((s) => [s.name, s.id])) as Record<string, number>;
  return { today: household.today, breakfast: slot['Breakfast']! };
}

/** Masala dosa: six steps, the third waits 8 to 12 hours; 30 minutes of work. */
async function dosa(page: Page, name = `Dosa ${stamp()}`) {
  const made = await call(page, 'POST', '/recipes', {
    name,
    serves: 4,
    time_minutes: 30,
    steps: [
      { text: 'Wash the rice and the dal.' },
      { text: 'Soak them for four hours.' },
      { text: 'Grind to a batter and leave it to ferment.', wait: { kind: 'ferment', min_minutes: 480, max_minutes: 720 } },
      { text: 'Stir the batter and add salt.' },
      { text: 'Heat the pan.' },
      { text: 'Make the dosas.' },
    ],
  });
  return { id: made.id as number, name };
}

type Ahead = { start_day: string | null; start_time: string | null; started_day: string | null; started_time: string | null; waited_minutes: number | null };
async function itemOn(page: Page, day: string, recipeId: number) {
  const plan = (await (await page.request.get(`/api/v1/plan?from=${day}&to=${day}`)).json()) as { meals: any[] };
  const item = plan.meals.flatMap((m) => m.items).find((i: any) => i.recipe?.id === recipeId);
  return item ? { id: item.id as number, ahead: item.ahead as Ahead | null } : null;
}

// A script error anywhere on the page fails the test that caused it. The phone opens the Plan on
// Eat; the meal's card is on Both.
const scriptErrors: string[] = [];
test.beforeEach(async ({ page }) => {
  scriptErrors.length = 0;
  page.on('pageerror', (error) => scriptErrors.push(error.message));
  await page.addInitScript(() => localStorage.setItem('mealwright.plan-show', 'both'));
  await setAccountTheme(page, 'auto');
});
test.afterEach(() => {
  expect(scriptErrors, 'the page raised no script errors').toEqual([]);
});

/** Open the Plan on the week that holds `day`, scrolled to it on the phone (Today's "+ Plan" link). */
async function openWeekOf(page: Page, day: string) {
  await page.goto(`/plan?day=${day}`);
}

test('Plan it on a recipe with a long wait asks when it will be started, and the meal can change the time, with Undo', async ({ page }) => {
  test.setTimeout(90_000); // two accessibility scans (both themes) and three screens to open
  const { today } = await setup(page);
  const recipe = await dosa(page);
  const day = addDays(today, 1 + projectIndex()); // a Breakfast at 08:00, so Sat 21:00 and 19:00 are still to come
  const eve = addDays(day, -1);
  try {
    await page.goto(`/recipes/${recipe.id}`);
    await page.getByRole('button', { name: 'Plan it', exact: true }).click();
    const sheet = page.getByRole('dialog', { name: recipe.name });
    await sheet.getByRole('button', { name: dayName(day) }).click();
    await sheet.getByRole('button', { name: 'Breakfast', exact: true }).click();
    await sheet.getByRole('button', { name: 'Plan it here' }).click();

    // The question: the wait, the times worked back from the meal, Another time…
    const ask = page.getByTestId('plan-start');
    await expect(ask).toBeVisible();
    await expect(ask.getByRole('heading', { name: `${recipe.name} · ${dayShort(day)} breakfast` })).toBeVisible();
    await expect(ask).toContainText('Breakfast at 08:00');
    await expect(ask).toContainText('It has to ferment first.');
    await expect(ask).toContainText('8–12 h');
    await expect(ask.getByRole('radio', { name: new RegExp(`${dayShort(eve)} 21:00.*ready by 08:00`) })).toBeChecked();
    await expect(ask.getByRole('radio', { name: new RegExp(`${dayShort(eve)} 19:00.*ready by 07:30`) })).not.toBeChecked();
    await expect(ask.getByRole('button', { name: 'Another time…' })).toBeVisible();
    await expect(ask).toContainText('Start tonight at 21:00');
    await checkPage(page);
    await ask.getByText(`${dayShort(eve)} 19:00`).click();
    await ask.getByRole('button', { name: 'Add to plan' }).click();
    await expect.poll(async () => (await itemOn(page, day, recipe.id))?.ahead?.start_time).toBe('19:00');
    expect((await itemOn(page, day, recipe.id))?.ahead?.start_day).toBe(eve);

    // Changing it from the meal: the menu says when it starts, and asks again with Save.
    await openWeekOf(page, day);
    // The computer's card is named by the recipe, the phone's "Breakfast: Recipe. Open menu"; the
    // tray's button of the same recipe ("Recipe. Choose a day to plan it") is not the meal.
    const card = page.getByRole('button', { name: new RegExp(`^(?:Breakfast: )?${recipe.name}(?!\\. Choose)`) }).first();
    await expect(card).toBeVisible({ timeout: 15_000 });
    await card.focus();
    await page.keyboard.press('Enter');
    await page.getByRole('dialog', { name: recipe.name }).getByRole('button', { name: `Starts ${dayShort(eve)} 19:00…` }).click({ timeout: 15_000 });
    await expect(ask.getByRole('radio', { name: new RegExp(`${dayShort(eve)} 19:00`) })).toBeChecked();
    await ask.getByRole('button', { name: 'Another time…' }).click();
    await ask.getByLabel('Time').fill('17:30');
    await ask.getByRole('button', { name: 'Save' }).click();
    await expect.poll(async () => (await itemOn(page, day, recipe.id))?.ahead?.start_time).toBe('17:30');
    await expect(page.getByRole('status').filter({ hasText: 'Changed when to start' })).toBeVisible();
    await page.getByRole('button', { name: 'Undo', exact: true }).click();
    await expect.poll(async () => (await itemOn(page, day, recipe.id))?.ahead?.start_time).toBe('19:00');
  } finally {
    const item = await itemOn(page, day, recipe.id);
    if (item) await page.request.fetch(`/api/v1/plan/items/${item.id}`, { method: 'DELETE', headers: key(), maxRetries: 3 });
  }
});

// cabledrawer 10 Nov: moving a meal that has a start time asks "When will you start it?" again for
// its new day (it used to drop the time). Cancel moves nothing; Undo puts the old time back.
// Dinner, not Breakfast, so the other tests' meals are never in the same card.
test('moving a meal that has a start time asks when to start it on its new day, with Undo', async ({ page }) => {
  test.setTimeout(90_000);
  const { today } = await setup(page);
  const list = (await (await page.request.get('/api/v1/meal-slots')).json()) as { id: number; name: string }[];
  const dinner = list.find((s) => s.name === 'Dinner')!.id;
  const recipe = await dosa(page);
  // Mon to Wed, moved two days on (Wed to Fri): the same week however the week starts.
  const day = addDays(today, 2 + projectIndex());
  const to = addDays(day, 2);
  await call(page, 'POST', '/plan/items', { date: day, slot_id: dinner, recipe_id: recipe.id, start: { day, time: '08:00' } });
  try {
    await openWeekOf(page, day);
    const card = page.getByRole('button', { name: new RegExp(`^(?:Dinner: )?${recipe.name}(?!\\. Choose)`) }).first();
    await expect(card).toBeVisible({ timeout: 15_000 });
    const moveTo = async () => {
      await card.focus();
      await page.keyboard.press('Enter');
      const sheet = page.getByRole('dialog', { name: recipe.name });
      await sheet.getByRole('button', { name: 'Move to…' }).click();
      await sheet.getByRole('button', { name: dayName(to) }).click();
      await sheet.getByRole('button', { name: 'Dinner', exact: true }).click();
      await sheet.getByRole('button', { name: 'Move here' }).click();
    };

    // Cancel: nothing moves, and the time stays.
    await moveTo();
    const ask = page.getByTestId('plan-start');
    await expect(ask.getByRole('heading', { name: `${recipe.name} · ${dayShort(to)} dinner` })).toBeVisible();
    await ask.getByRole('button', { name: 'Cancel' }).click();
    await expect(ask).toBeHidden();
    expect((await itemOn(page, day, recipe.id))?.ahead?.start_time).toBe('08:00');

    // Asked again for the new day: the time picked goes with the move.
    await moveTo();
    await ask.getByRole('button', { name: 'Another time…' }).click();
    await ask.getByLabel('Day').fill(to);
    await ask.getByLabel('Time').fill('07:30');
    await ask.getByRole('button', { name: 'Move', exact: true }).click();
    await expect.poll(async () => (await itemOn(page, to, recipe.id))?.ahead?.start_time).toBe('07:30');
    expect((await itemOn(page, to, recipe.id))?.ahead?.start_day).toBe(to);
    expect(await itemOn(page, day, recipe.id)).toBeNull();

    // Undo: back on its old day, with its old time.
    await page.getByRole('button', { name: 'Undo', exact: true }).click();
    await expect.poll(async () => (await itemOn(page, day, recipe.id))?.ahead?.start_time).toBe('08:00');
  } finally {
    for (const d of [day, to]) {
      const item = await itemOn(page, d, recipe.id);
      if (item) await page.request.fetch(`/api/v1/plan/items/${item.id}`, { method: 'DELETE', headers: key(), maxRetries: 3 });
    }
  }
});

test('a time that is not before the meal is refused in the question, and Cancel plans nothing', async ({ page }) => {
  const { today } = await setup(page);
  const recipe = await dosa(page);
  const day = addDays(today, 1 + projectIndex());
  await page.goto(`/recipes/${recipe.id}`);
  await page.getByRole('button', { name: 'Plan it', exact: true }).click();
  const sheet = page.getByRole('dialog', { name: recipe.name });
  await sheet.getByRole('button', { name: dayName(day) }).click();
  await sheet.getByRole('button', { name: 'Breakfast', exact: true }).click();
  await sheet.getByRole('button', { name: 'Plan it here' }).click();
  const ask = page.getByTestId('plan-start');
  await ask.getByRole('button', { name: 'Another time…' }).click();
  await ask.getByLabel('Day').fill(day);
  await ask.getByLabel('Time').fill('09:00');
  await ask.getByRole('button', { name: 'Add to plan' }).click();
  await expect(ask.getByRole('alert')).toHaveText('Pick a time before the meal.');
  await ask.getByRole('button', { name: 'Cancel' }).click();
  await expect(ask).toBeHidden();
  expect(await itemOn(page, day, recipe.id)).toBeNull();
});

test('Today says Start tonight, Done already marks it begun with Undo, and Start it in Cook mode opens Cook mode', async ({ page }) => {
  const { today, breakfast } = await setup(page);
  const recipe = await dosa(page);
  const day = addDays(today, 3 + projectIndex()); // a meal still to come, started today at 21:00
  const planned = await call(page, 'POST', '/plan/items', { date: day, slot_id: breakfast, recipe_id: recipe.id, start: { day: today, time: '21:00' } });
  try {
    await page.goto('/');
    const card = page.getByTestId('start-tonight').filter({ hasText: recipe.name });
    await expect(card).toBeVisible();
    await expect(card.getByRole('heading', { name: 'Start tonight at 21:00' })).toBeVisible();
    await expect(card).toContainText('Ferment · 8–12 h');
    await expect(card).toContainText('Grind to a batter and leave it to ferment');
    await expect(card).toContainText(`For ${dayShort(day)} breakfast · ${recipe.name} · 30 min of work`);
    await expect(card).toContainText('Start by 21:00 so it’s ready by 08:00.');
    await checkPage(page);

    // Done already: the card goes, the wait is begun, and Undo brings it back.
    await card.getByRole('button', { name: 'Done already' }).click();
    await expect(page.getByRole('status').filter({ hasText: `Marked ${recipe.name} as started` })).toBeVisible();
    await expect(card).toHaveCount(0);
    await expect.poll(async () => (await itemOn(page, day, recipe.id))?.ahead?.started_time).not.toBeNull();
    await page.getByRole('button', { name: 'Undo', exact: true }).click();
    await expect(card).toBeVisible();
    await expect.poll(async () => (await itemOn(page, day, recipe.id))?.ahead?.started_time ?? null).toBeNull();

    // Start it in Cook mode: Cook mode for this recipe and meal, on its first step.
    await card.getByRole('button', { name: 'Start it in Cook mode' }).click();
    await expect(page).toHaveURL(new RegExp(`/recipes/${recipe.id}/cook\\?meal=${planned.meal_id}`));
    await expect(page.getByTestId('step-count')).toContainText('Step 1 of 6');
  } finally {
    await page.request.fetch(`/api/v1/plan/items/${planned.item_id}`, { method: 'DELETE', headers: key(), maxRetries: 3 });
  }
});

test('the Plan\'s Cook view says Start tonight on the day to start, with Done already', async ({ page }) => {
  const { today, breakfast } = await setup(page);
  const recipe = await dosa(page);
  const day = addDays(today, 3 + projectIndex());
  const eve = addDays(day, -1);
  const planned = await call(page, 'POST', '/plan/items', { date: day, slot_id: breakfast, recipe_id: recipe.id, start: { day: eve, time: '21:00' } });
  try {
    await openWeekOf(page, eve); // the start is on a day of next week
    await page.getByRole('group', { name: 'Show', exact: true }).getByRole('button', { name: 'Cook', exact: true }).click();
    const line = page.getByTestId('cook-start').filter({ hasText: `(for ${dayShort(day)} breakfast)` });
    await expect(line.first()).toContainText(`Start tonight at 21:00: grind to a batter and leave it to ferment (for ${dayShort(day)} breakfast)`);
    await line.first().getByRole('button', { name: 'Done already' }).click();
    await expect.poll(async () => (await itemOn(page, day, recipe.id))?.ahead?.started_time).not.toBeNull();
    await expect(page.getByRole('status').filter({ hasText: `Marked ${recipe.name} as started` })).toBeVisible();
  } finally {
    await page.request.fetch(`/api/v1/plan/items/${planned.item_id}`, { method: 'DELETE', headers: key(), maxRetries: 3 });
  }
});

test('Cook mode marks the wait begun past its step, and opens after it with the steps folded and how long it waited', async ({ page }) => {
  const { today, breakfast } = await setup(page);
  const recipe = await dosa(page);
  const day = addDays(today, 5 + projectIndex());
  const planned = await call(page, 'POST', '/plan/items', { date: day, slot_id: breakfast, recipe_id: recipe.id, start: { day: today, time: '21:00' } });
  const url = `/recipes/${recipe.id}/cook?meal=${planned.meal_id}&day=${day}`;
  const count = (p: Page) => p.getByTestId('step-count');
  const next = (p: Page) => p.getByRole('button', { name: 'Next →' });
  try {
    await page.goto(url);
    await expect(count(page)).toHaveText('Step 1 of 6');
    await next(page).click();
    await next(page).click();
    // The step that waits says what happens next; nothing is begun yet.
    await expect(count(page)).toHaveText('Step 3 of 6');
    await expect(page.getByTestId('ahead-note')).toContainText('Then it waits (8–12 h)');
    expect((await itemOn(page, day, recipe.id))?.ahead?.started_time).toBeNull();
    await next(page).click();
    await expect(count(page)).toHaveText('Step 4 of 6');
    await expect.poll(async () => (await itemOn(page, day, recipe.id))?.ahead?.started_time ?? null).not.toBeNull();

    // Coming back: it opens at step 4, the steps up to the wait folded, with how long it has waited.
    await page.goto(url);
    await expect(count(page)).toHaveText('Step 4 of 6');
    await expect(page.getByTestId('step-text')).toHaveText('Stir the batter and add salt.');
    const folded = page.getByTestId('folded-steps');
    await expect(folded).toContainText('1–3 · Grind to a batter and leave it to ferment');
    await expect(folded).toContainText(/Done today \d\d:\d\d/);
    await expect(page.getByTestId('waited')).toContainText(/Fermented \d+\s?min/);
    await expect(page.getByTestId('waited')).toContainText('needed 8–12 h');
    await checkPage(page);
    // Back goes into the folded steps as usual.
    await page.getByRole('button', { name: '← Back' }).click();
    await expect(count(page)).toHaveText('Step 3 of 6');
  } finally {
    await page.request.fetch(`/api/v1/plan/items/${planned.item_id}`, { method: 'DELETE', headers: key(), maxRetries: 3 });
  }
});
