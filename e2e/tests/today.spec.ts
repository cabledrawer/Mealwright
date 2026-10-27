import { test, expect, type Page } from './clock.ts';
import { checkPage } from './a11y.ts';

// Today (0.6, PR 6), against the real server: "Did you cook Sambar?" with Cooked it (and "Any
// left over?"), Didn't and Move it (to tomorrow, alongside a meal that has food), and the
// first-day state. Runs on Chromium (phone and computer) and WebKit (computer), see
// playwright.config.ts. The projects share one server, and an answered meal keeps its slot, so
// each project and test plans on a day and meal of its own and answers its own meal.

const key = () => ({ 'idempotency-key': crypto.randomUUID() });
const stamp = () => `${test.info().project.name.replace(/\W/g, '')}${Date.now().toString(36)}`;

async function call(page: Page, method: 'POST' | 'DELETE', path: string, data?: object) {
  const response = await page.request.fetch(`/api/v1${path}`, { method, data, headers: key() });
  expect(response.ok(), `${method} ${path}: ${await response.text()}`).toBe(true);
  return (await response.json()) as Record<string, any>;
}

function addDays(iso: string, days: number): string {
  const d = new Date(`${iso}T12:00:00Z`);
  d.setUTCDate(d.getUTCDate() + days);
  return d.toISOString().slice(0, 10);
}

/** Today's server data, the slots by name, and a meal planned in the past for this project. */
async function start(page: Page, slotName: string) {
  const today = (await (await page.request.get('/api/v1/household')).json()).today as string;
  const slots = (await (await page.request.get('/api/v1/meal-slots')).json()) as { id: number; name: string }[];
  const slot = Object.fromEntries(slots.map((s) => [s.name, s.id])) as Record<string, number>;
  // Anything left waiting by another test is answered first, so this meal is the card.
  const read = (await (await page.request.get('/api/v1/today')).json()) as { waiting: { meal_id: number }[] };
  for (const w of read.waiting) await call(page, 'POST', `/plan/meals/${w.meal_id}/didnt`);
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
  await expect(sheet.getByText('Your pantry isn’t changed by this yet.')).toBeVisible();
  await expect(sheet.getByText('None')).toBeVisible();
  await sheet.getByRole('button', { name: 'More tubs' }).click();
  await expect(sheet.getByText('1 tub')).toBeVisible();
  await expect(sheet.getByRole('button', { name: 'Fridge' })).toHaveAttribute('aria-pressed', 'true');
  await expect(sheet.getByText(/Use by .* · \d+ days left|Use by .* · use by/)).toBeVisible();
  await sheet.getByRole('button', { name: 'Cooked it' }).click();

  await expect(card(page)).toHaveCount(0);
  await expect(page.getByText(new RegExp(`Cooked ${k.name}`)).first()).toBeVisible();
  await expect(stat(page, 'tubs left')).toHaveText(String(before + 1));

  // Undo: the card is back, the tub is gone.
  await page.getByRole('button', { name: 'Undo' }).click();
  await expect(card(page).getByText(`Did you cook ${k.name}?`)).toBeVisible();
  await expect(stat(page, 'tubs left')).toHaveText(String(before));

  // Cooked it with nothing left over: the card goes for good.
  await card(page).getByRole('button', { name: 'Cooked it' }).click();
  await sheet.getByRole('button', { name: 'Cooked it' }).click();
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
