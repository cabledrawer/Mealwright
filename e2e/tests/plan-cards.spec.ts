import { test, expect, type Locator, type Page } from './clock.ts';
import { expectNoAxeViolations, inTheme, setAccountTheme } from './a11y.ts';
import { uploadPhoto } from '../review/photos.ts';

// The Plan's cards in Both (0.7, P3): COOK and EAT are separate cards, cells are only as tall as
// their content (F42), a COOK card is dragged with its EAT card and Undo puts it back, tubs that
// land before the cook day are flagged, the keyboard moves a card, the tray wraps and drags by the
// photo (F39, F40), and the words of F49 and F65. Computer only. Every test plans in weeks of its
// own (30 to 35 weeks ahead), named with a word no other test uses. The tests' day is a Saturday;
// the day after (Sunday) is in the same week.

const key = () => ({ 'idempotency-key': crypto.randomUUID() });

async function call(page: Page, method: 'POST' | 'PUT' | 'DELETE' | 'PATCH', path: string, data?: object) {
  const response = await page.request.fetch(`/api/v1${path}`, { method, data, headers: key() });
  expect(response.ok(), `${method} ${path}: ${await response.text()}`).toBe(true);
  return (await response.json()) as Record<string, any>;
}

const far = (today: string, k: number) => addDays(today, 7 * (30 + k));
const stamp = () => `Cards${Date.now().toString(36)}`;

function addDays(iso: string, days: number): string {
  const d = new Date(`${iso}T12:00:00Z`);
  d.setUTCDate(d.getUTCDate() + days);
  return d.toISOString().slice(0, 10);
}

async function setup(page: Page) {
  const household = (await (await page.request.get('/api/v1/household')).json()) as { today: string };
  const list = (await (await page.request.get('/api/v1/meal-slots')).json()) as { id: number; name: string }[];
  const slot = Object.fromEntries(list.map((s) => [s.name, s.id])) as Record<string, number>;
  await call(page, 'PATCH', `/meal-slots/${slot.Snack}`, { enabled: true });
  return { today: household.today, slot };
}

const makeRecipe = async (page: Page, name: string) => (await call(page, 'POST', '/recipes', { name })).id as number;
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

async function centre(locator: Locator, down = 0.5) {
  await locator.scrollIntoViewIfNeeded();
  const box = (await locator.boundingBox())!;
  return { x: box.x + box.width / 2, y: box.y + box.height * down };
}

async function mouseDrag(page: Page, from: Locator, to: Locator) {
  const a = await centre(from);
  await page.mouse.move(a.x, a.y);
  await page.mouse.down();
  await page.mouse.move(a.x + 12, a.y + 12, { steps: 3 });
  const b = await centre(to, 0.2);
  await page.mouse.move(b.x, b.y, { steps: 10 });
  await page.mouse.up();
}

test.beforeEach(async ({ page }) => {
  await page.addInitScript(() => localStorage.setItem('mealwright.plan-show', 'both'));
  await setAccountTheme(page, 'auto');
});

/** A batch cooked on `day` at dinner, with its two tubs on the Sunday after: lunch and dinner. */
async function batchWithTubs(page: Page, name: string, day: string, slot: Record<string, number>) {
  const cook = await planned(page, await makeRecipe(page, name), day, slot.Dinner);
  const sun = addDays(day, 1);
  const made = await call(page, 'POST', `/plan/items/${cook.item_id}/batch`, {
    tub_count: 2,
    pattern: 'pick',
    placements: [
      { date: sun, slot_id: slot.Lunch },
      { date: sun, slot_id: slot.Dinner }
    ]
  });
  return { cook, sun, batch: made.batch_id as number };
}

const cookCard = (where: Locator) => where.getByRole('button', { name: /\(cooking\)/ });

test('a batch meal is a COOK card plus an EAT card, tubs are EAT cards, a fresh meal has a pan (cards in Both)', async ({ page }) => {
  const { today, slot } = await setup(page);
  const name = `${stamp()} Curry`;
  const fresh = `${stamp()} Toast`;
  const day = far(today, 0);
  const { sun } = await batchWithTubs(page, name, day, slot);
  await planned(page, await makeRecipe(page, fresh), day, slot.Breakfast);
  await openWeekOf(page, today, day);

  const dinner = cell(page, day, slot.Dinner);
  await expect(cookCard(dinner)).toHaveCount(1);
  await expect(cookCard(dinner)).toContainText('Makes 3 · 2 tubs');
  await expect(cookCard(dinner).locator('svg')).toHaveCount(1); // the pan
  const eating = dinner.getByRole('button', { name: /\(eating\)/ });
  await expect(eating).toHaveCount(1);
  await expect(eating).toContainText('Eat');
  await expect(eating.locator('svg')).toHaveCount(1); // the plate

  const lunch = cell(page, sun, slot.Lunch);
  await expect(lunch).toContainText('Eat · tub 1 of 2');
  await expect(cell(page, sun, slot.Dinner)).toContainText('Eat · last tub');

  const toast = cell(page, day, slot.Breakfast).getByRole('button', { name: new RegExp(`^${fresh}`) });
  await expect(toast).toContainText('Fresh');
  await expect(toast.locator('svg')).toHaveCount(1);
});

test('F42: a cell is only as tall as what is in it', async ({ page }) => {
  const { today, slot } = await setup(page);
  const day = far(today, 1);
  await planned(page, await makeRecipe(page, `${stamp()} Oats`), day, slot.Breakfast);
  await openWeekOf(page, today, day);
  const one = cell(page, day, slot.Breakfast);
  await expect(one.getByRole('button', { name: /Oats/ })).toBeVisible();
  const outer = (await one.boundingBox())!;
  const inner = (await one.locator('.meal').boundingBox())!;
  expect(Math.abs(outer.height - inner.height), 'the cell hugs its meal').toBeLessThanOrEqual(2);
  // The "n recipes" line and the + sit straight under the card, not at the foot of a tall cell.
  const card = (await one.locator('.card').first().boundingBox())!;
  const foot = (await one.locator('.foot').boundingBox())!;
  expect(foot.y - (card.y + card.height)).toBeLessThan(40);
  expect(outer.height).toBeLessThan(260);
});

test('dragging a COOK card moves the cooking and its EAT card, flags tubs now before it, and one Undo puts it back', async ({ page }) => {
  const { today, slot } = await setup(page);
  const name = `${stamp()} Dal`;
  const day = far(today, 2);
  const { sun, cook } = await batchWithTubs(page, name, day, slot);
  await openWeekOf(page, today, day);

  // Sunday's snack comes after lunch and before dinner: the lunch tub is now before the cooking.
  await mouseDrag(page, cookCard(cell(page, day, slot.Dinner)), cell(page, sun, slot.Snack));
  await expect(page.getByRole('status').filter({ hasText: 'Moved' })).toBeVisible();
  await expect.poll(async () => {
    const meals = (await planRange(page, sun, sun)).meals as { id: number; date: string; slot_id: number }[];
    return meals.find((m) => m.id === cook.meal_id)?.slot_id;
  }).toBe(slot.Snack);
  const moved = cell(page, sun, slot.Snack);
  await expect(cookCard(moved)).toHaveCount(1);
  await expect(moved.getByRole('button', { name: /\(eating\)/ })).toHaveCount(1);
  await expect(cell(page, day, slot.Dinner).getByRole('button')).toHaveCount(1); // only "+" is left
  const early = cell(page, sun, slot.Lunch);
  await expect(early).toContainText('Before the cook day');
  await expect(early.locator('.card.before')).toHaveCount(1);
  await expect(cell(page, sun, slot.Dinner)).not.toContainText('Before the cook day');

  await page.getByRole('button', { name: 'Undo', exact: true }).click();
  await expect.poll(async () => {
    const meals = (await planRange(page, day, day)).meals as { id: number; slot_id: number }[];
    return meals.find((m) => m.id === cook.meal_id)?.slot_id;
  }).toBe(slot.Dinner);
  await expect(cookCard(cell(page, day, slot.Dinner))).toHaveCount(1);
  await expect(cell(page, sun, slot.Lunch)).not.toContainText('Before the cook day');
});

test('a COOK card is not dropped on a meal that is already planned', async ({ page }) => {
  const { today, slot } = await setup(page);
  const name = `${stamp()} Rajma`;
  const day = far(today, 3);
  const { sun, cook } = await batchWithTubs(page, name, day, slot);
  await openWeekOf(page, today, day);
  await mouseDrag(page, cookCard(cell(page, day, slot.Dinner)), cell(page, sun, slot.Dinner));
  await expect(page.getByRole('status').filter({ hasText: 'Cooking can only move to an empty meal.' })).toBeVisible();
  const meals = (await planRange(page, day, day)).meals as { id: number; slot_id: number }[];
  expect(meals.find((m) => m.id === cook.meal_id)?.slot_id).toBe(slot.Dinner);
  await expect(cookCard(cell(page, day, slot.Dinner))).toHaveCount(1);
});

test('the cards pass the accessibility check in both themes', async ({ page }) => {
  const { today, slot } = await setup(page);
  const day = far(today, 4);
  await batchWithTubs(page, `${stamp()} Sambar`, day, slot);
  await openWeekOf(page, today, day);
  await expect(cookCard(cell(page, day, slot.Dinner))).toBeVisible();
  for (const theme of ['light', 'dark'] as const) {
    await inTheme(page, theme);
    await expectNoAxeViolations(page, `Plan cards, ${theme}`);
  }
});

test('moving a card with the keyboard only: Enter, arrows for the day, Shift and arrows for the meal, Enter, Escape, Undo', async ({ page }) => {
  const { today, slot } = await setup(page);
  const name = `${stamp()} Pasta`;
  const day = far(today, 5);
  const sun = addDays(day, 1);
  const item = await planned(page, await makeRecipe(page, name), day, slot.Lunch);
  await openWeekOf(page, today, day);
  const here = cell(page, day, slot.Lunch).getByRole('button', { name: new RegExp(`^${name}`) });

  // Escape cancels: nothing moves, and the focus is back on the card.
  await here.focus();
  await page.keyboard.press('Enter');
  const menu = page.getByRole('dialog', { name });
  await expect(menu).toBeVisible();
  await menu.getByRole('button', { name: 'Move to…' }).focus();
  await page.keyboard.press('Enter');
  await page.keyboard.press('ArrowRight');
  await expect(menu.getByRole('status').filter({ hasText: 'Move to' })).toContainText('· Lunch');
  await page.keyboard.press('Escape');
  await expect(menu).toBeHidden();
  await expect(here).toBeFocused();
  expect(((await planRange(page, day, day)).meals as { date: string }[]).filter((m) => m.date === day).length).toBeGreaterThan(0);

  // Arrow keys pick the day (one day on, the same meal), Shift and arrows the meal; Enter confirms.
  await page.keyboard.press('Enter');
  await menu.getByRole('button', { name: 'Move to…' }).focus();
  await page.keyboard.press('Enter');
  await page.keyboard.press('ArrowRight');
  await page.keyboard.press('Shift+ArrowRight');
  await page.keyboard.press('Shift+ArrowRight');
  await page.keyboard.press('Shift+ArrowLeft');
  await page.keyboard.press('Shift+ArrowRight');
  await expect(menu.getByRole('status').filter({ hasText: 'Move to' })).toContainText(/Sunday.* · Dinner/);
  await page.keyboard.press('Enter');
  await expect(menu).toBeHidden();
  const there = cell(page, sun, slot.Dinner).getByRole('button', { name: new RegExp(`^${name}`) });
  await expect(there).toBeVisible();
  await expect(there).toBeFocused(); // focus returns to the moved card
  await expect(page.getByRole('status').filter({ hasText: 'Moved' })).toBeVisible();
  await expect.poll(async () => {
    const meals = (await planRange(page, sun, sun)).meals as { id: number; slot_id: number }[];
    return meals.find((m) => m.id === item.meal_id)?.slot_id;
  }).toBe(slot.Dinner);

  await page.getByRole('button', { name: 'Undo', exact: true }).click();
  await expect(cell(page, day, slot.Lunch).getByRole('button', { name: new RegExp(`^${name}`) })).toBeVisible();
});

test('F39: the tray wraps onto two lines, and the mouse wheel scrolls the rest', async ({ page }) => {
  const { today } = await setup(page);
  const tag = stamp();
  for (let i = 0; i < 16; i++) await makeRecipe(page, `${tag} Tray ${String(i).padStart(2, '0')}`);
  await openWeekOf(page, today, far(today, 6));
  const strip = page.getByRole('list', { name: 'Recipes to plan' });
  await expect(strip.getByRole('button').first()).toBeVisible();
  const lines = await strip.evaluate((el) => {
    const tops = new Set([...el.querySelectorAll('li')].map((li) => (li as HTMLElement).offsetTop));
    return { rows: tops.size, shown: el.clientHeight, whole: el.scrollHeight };
  });
  expect(lines.rows, 'more than one line of recipes').toBeGreaterThan(1);
  expect(lines.whole, 'more recipes than two lines hold').toBeGreaterThan(lines.shown);
  expect(lines.shown, 'two lines high').toBeLessThan(130);
  const box = (await strip.boundingBox())!;
  await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2);
  await page.mouse.wheel(0, 120);
  await expect.poll(() => strip.evaluate((el) => el.scrollTop)).toBeGreaterThan(0);
});

test('F40: a recipe is dragged from its photo as well as from its name', async ({ page }) => {
  const { today, slot } = await setup(page);
  const name = `${stamp()} Photo`;
  const day = far(today, 7);
  const photo = await uploadPhoto(page.request, 'dish');
  await call(page, 'POST', '/recipes', { name, photo_id: photo, steps: [{ text: 'Stir.' }] });
  await openWeekOf(page, today, day);
  await page.getByRole('searchbox', { name: 'Find a recipe to plan' }).fill(name);
  const item = page.getByRole('list', { name: 'Recipes to plan' }).getByRole('button', { name: new RegExp(`^${name}`) });
  await expect(item).toBeVisible();
  const picture = item.locator('img');
  await expect.poll(() => picture.evaluate((img: HTMLImageElement) => img.complete && img.naturalWidth > 0)).toBe(true);
  await mouseDrag(page, picture, cell(page, day, slot.Lunch));
  await expect(page.getByRole('status').filter({ hasText: `Planned ${name}` })).toBeVisible();
  await expect(cell(page, day, slot.Lunch).getByRole('button', { name: new RegExp(`^${name}`) })).toBeVisible();
  await expect(picture).toHaveAttribute('draggable', 'false');
});
