import { test, expect, type Locator, type Page } from './clock.ts';
import { expectNoAxeViolations, expectNoSidewaysScroll, inTheme, setAccountTheme } from './a11y.ts';
import { uploadPhoto } from '../review/photos.ts';

// The Plan's cards in Both (0.7, P3): COOK and EAT are separate cards, cells are only as tall as
// their content (F42), a COOK card is dragged with its EAT card and Undo puts it back, tubs that
// land before the cook day are flagged, the keyboard moves a card, the tray wraps and drags by the
// photo (F39, F40), and the words of F49 and F65. Computer only. Every test plans in weeks of its
// own (weeks 80 to 83 ahead), named with a word no other test uses. The tests' day is a Saturday;
// the day after (Sunday) is in the same week.

const key = () => ({ 'idempotency-key': crypto.randomUUID() });

async function call(page: Page, method: 'POST' | 'PUT' | 'DELETE' | 'PATCH', path: string, data?: object) {
  const response = await page.request.fetch(`/api/v1${path}`, { method, data, headers: key() });
  expect(response.ok(), `${method} ${path}: ${await response.text()}`).toBe(true);
  return (await response.json()) as Record<string, any>;
}

// Weeks 80 to 83 ahead, no other plan test's (past weeks cannot hold a batch: its tubs would be in the
// past). Test k (0 to 10) takes week 80 + k % 4, and in it a day and the day after: the Saturday, the
// Thursday or the Monday (k / 4 picks), so no two tests share a day.
const far = (today: string, k: number) => addDays(today, 7 * (80 + (k % 4)) - [0, 2, 5][Math.floor(k / 4)]!);
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
  // Whole weeks from this week's Monday to the day's week.
  const here = new Date(`${today}T12:00:00Z`);
  const days = Math.round((new Date(`${day}T12:00:00Z`).getTime() - here.getTime()) / 86_400_000);
  const ahead = Math.floor((days + ((here.getUTCDay() + 6) % 7)) / 7);
  for (let i = 0; i < Math.abs(ahead); i++) await page.getByRole('button', { name: ahead > 0 ? 'Next week' : 'Previous week' }).click();
}

const weekdayLong = new Intl.DateTimeFormat('en-GB', { weekday: 'long', timeZone: 'UTC' });
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
  // The batch is cooked on the new day, as the server keeps it.
  expect(((await planRange(page, sun, sun)).batch_cooks as { cooked_on: string }[]).map((b) => b.cooked_on)).toContain(sun);
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
  await expect.poll(async () => ((await planRange(page, day, day)).batch_cooks as { cooked_on: string }[]).map((b) => b.cooked_on)).toContain(day);
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
  await expect(menu.getByRole('status').filter({ hasText: 'Move to' })).toContainText(new RegExp(`${weekdayLong.format(new Date(`${sun}T12:00:00Z`))}.* · Dinner`));
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
  await strip.scrollIntoViewIfNeeded();
  const box = (await strip.boundingBox())!;
  await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2);
  await page.mouse.wheel(0, 120);
  await expect.poll(() => strip.evaluate((el) => el.scrollTop)).toBeGreaterThan(0);
});

test('F40: a recipe is dragged from its photo as well as from its name', async ({ page }) => {
  const { today, slot } = await setup(page);
  const name = `${stamp()} Photo`;
  const day = far(today, 7);
  // Tall enough that the tray and the target are both on screen, whatever else is in this week.
  await page.setViewportSize({ width: 1440, height: 1500 });
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

test('F49: a tub is taken off a meal with plain words and a note, not a red "Back to tubs left"', async ({ page }) => {
  const { today, slot } = await setup(page);
  const name = `${stamp()} Kofta`;
  const day = far(today, 8);
  const { sun } = await batchWithTubs(page, name, day, slot);
  await openWeekOf(page, today, day);
  const tub = cell(page, sun, slot.Lunch).getByRole('button', { name: new RegExp(`^${name} tub`) });
  await tub.click();
  const menu = page.getByRole('dialog', { name: `${name} tub` });
  await expect(menu.getByRole('button', { name: 'Back to tubs left' })).toHaveCount(0);
  const off = menu.getByRole('button', { name: 'Take off this meal (keep the tub)' });
  await expect(off).toBeVisible();
  await expect(off).not.toHaveClass(/remove/); // not the red button
  await expect(menu.getByText('The tub stays in the fridge, in Tubs left.')).toBeVisible();
  await off.click();
  await expect(page.getByRole('status').filter({ hasText: /back in tubs left/ })).toBeVisible();
  await expect(cell(page, sun, slot.Lunch).getByRole('button', { name: new RegExp(`^${name} tub`) })).toHaveCount(0);
  await page.getByRole('button', { name: 'Undo', exact: true }).click();
  await expect(cell(page, sun, slot.Lunch).getByRole('button', { name: new RegExp(`^${name} tub`) })).toBeVisible();
});

test('F65: "Any left over?" offers "Eat it on…" the next free meal, and the tub goes there', async ({ page }) => {
  const { today, slot } = await setup(page);
  const name = `${stamp()} Chilli`;
  // Three days back (this week, a day no other test cooks on): "Cooked it" needs a day that has come.
  const cooked = addDays(today, -3);
  await planned(page, await makeRecipe(page, name), cooked, slot.Dinner);
  await page.goto('/plan');
  await cell(page, cooked, slot.Dinner).getByRole('button', { name: new RegExp(`^${name}`) }).first().click();
  await page.getByRole('dialog', { name }).getByRole('button', { name: 'Cooked it' }).click();
  const review = page.getByTestId('cooked-review');
  await review.getByRole('button', { name: 'More tubs' }).click();
  const eat = review.getByLabel('Eat it on…');
  await expect(eat).toBeVisible();
  await expect(eat.locator('option').first()).toHaveText('Not planned yet');
  await eat.selectOption({ index: 1 });
  const [eatDay, eatSlot] = (await eat.inputValue()).split('|') as [string, string];
  expect(eatDay >= today).toBe(true); // never a day that has gone
  await review.getByRole('button', { name: 'Confirm · update pantry' }).click();
  await expect(review).toBeHidden();
  await expect(cell(page, eatDay, Number(eatSlot)).getByRole('button', { name: new RegExp(`^${name} tub`) })).toBeVisible();
  // One Undo takes back the placement and the cooking: no tub, no batch.
  await page.getByRole('button', { name: 'Undo', exact: true }).click();
  await expect(cell(page, eatDay, Number(eatSlot)).getByRole('button', { name: new RegExp(`^${name} tub`) })).toHaveCount(0);
  await expect.poll(async () => {
    const plan = await planRange(page, cooked, addDays(eatDay, 1));
    return (plan.batch_cooks as { recipe_name: string }[]).filter((b) => b.recipe_name === name).length;
  }).toBe(0);
  const left = (await (await page.request.get('/api/v1/plan/tubs-left')).json()) as { tubs: { recipe_name: string }[] };
  expect(left.tubs.filter((t) => t.recipe_name === name)).toHaveLength(0);
});

test('F65 on Today: the same "Eat it on…", and Undo takes the placement back with the cook', async ({ page }) => {
  const { today, slot } = await setup(page);
  const waiting = (await (await page.request.get('/api/v1/today')).json()) as { waiting: { meal_id: number }[] };
  for (const w of waiting.waiting) await call(page, 'POST', `/plan/meals/${w.meal_id}/didnt`);
  const name = `${stamp()} Soup`;
  const cooked = addDays(today, -5);
  await planned(page, await makeRecipe(page, name), cooked, slot.Dinner);
  await page.goto('/');
  await expect(page.getByTestId('did-you-cook').getByText(`Did you cook ${name}?`)).toBeVisible();
  await page.getByTestId('did-you-cook').getByRole('button', { name: 'Cooked it' }).click();
  const review = page.getByTestId('cooked-review');
  await review.getByRole('button', { name: 'More tubs' }).click();
  const eat = review.getByLabel('Eat it on…');
  await expect(eat.locator('option').first()).toHaveText('Not planned yet');
  await eat.selectOption({ index: 1 });
  const [eatDay, eatSlot] = (await eat.inputValue()).split('|') as [string, string];
  expect(eatDay >= today).toBe(true);
  await review.getByRole('button', { name: 'Confirm · update pantry' }).click();
  await expect(review).toBeHidden();
  const tubsAt = async () => {
    const plan = await planRange(page, eatDay, eatDay);
    const meal = (plan.meals as { date: string; slot_id: number; items: { tub_id: number | null }[] }[]).find((m) => m.date === eatDay && m.slot_id === Number(eatSlot));
    return meal?.items.filter((i) => i.tub_id !== null).length ?? 0;
  };
  await expect.poll(tubsAt).toBe(1);
  await page.getByRole('button', { name: 'Undo', exact: true }).click();
  await expect.poll(tubsAt).toBe(0);
  await expect.poll(async () => {
    const plan = await planRange(page, cooked, addDays(eatDay, 1));
    return (plan.batch_cooks as { recipe_name: string }[]).filter((b) => b.recipe_name === name).length;
  }).toBe(0);
});

test('at 1100 px wide and 200% text the cards and the keyboard picker keep their words whole, in both themes', async ({ page }) => {
  test.setTimeout(180_000);
  const { today, slot } = await setup(page);
  const day = far(today, 9);
  const name = 'Dal';
  const { sun } = await batchWithTubs(page, name, day, slot);
  await page.setViewportSize({ width: 1100, height: 900 });
  await openWeekOf(page, today, day);
  await expect(cookCard(cell(page, day, slot.Dinner))).toBeVisible();
  for (const theme of ['light', 'dark'] as const) {
    await inTheme(page, theme);
    for (const text of ['100%', '200%']) {
      await page.evaluate((size) => (document.documentElement.style.fontSize = size), text);
      const broken = () =>
        page.evaluate(([d1, d2]) => {
          const out: string[] = [];
          const own = [`[data-testid^="cell-${d1}"]`, `[data-testid^="cell-${d2}"]`, 'dialog[open]'].join(',');
          for (const area of document.querySelectorAll(own)) {
            const walker = document.createTreeWalker(area, NodeFilter.SHOW_TEXT);
            for (let node = walker.nextNode(); node; node = walker.nextNode()) {
              const el = node.parentElement;
              if (!el || !el.checkVisibility()) continue;
              for (const m of (node.textContent ?? '').matchAll(/[^\s\-–—/·→]+/g)) {
                const range = document.createRange();
                range.setStart(node, m.index!);
                range.setEnd(node, m.index! + m[0].length);
                const lines = new Set([...range.getClientRects()].filter((r) => r.width > 0).map((r) => Math.round(r.top / 4)));
                if (lines.size > 1) out.push(m[0]);
              }
            }
          }
          return out;
        }, [day, sun]);
      await expect.poll(broken, { message: `words broken in the week, ${theme}, ${text}` }).toEqual([]);
      await expectNoSidewaysScroll(page);
      // The keyboard picker.
      await cell(page, sun, slot.Lunch).getByRole('button', { name: /tub/ }).first().click();
      const menu = page.getByRole('dialog');
      await menu.getByRole('button', { name: 'Move to…' }).click();
      await page.keyboard.press('ArrowRight');
      await expect.poll(broken, { message: `words broken in the picker, ${theme}, ${text}` }).toEqual([]);
      await expectNoSidewaysScroll(page);
      await page.keyboard.press('Escape');
      await expect(menu).toBeHidden();
    }
  }
  await page.evaluate(() => (document.documentElement.style.fontSize = ''));
});

test('a COOK card in a meal with several things moves the whole meal (proposed, for cabledrawer)', async ({ page }) => {
  const { today, slot } = await setup(page);
  const name = `${stamp()} Biryani`;
  const side = `${stamp()} Raita`;
  const day = far(today, 10);
  const sun = addDays(day, 1);
  const cook = await planned(page, await makeRecipe(page, name), day, slot.Dinner);
  await planned(page, await makeRecipe(page, side), day, slot.Dinner);
  await call(page, 'POST', `/plan/items/${cook.item_id}/batch`, { tub_count: 1, pattern: 'pick' });
  await openWeekOf(page, today, day);
  await mouseDrag(page, cookCard(cell(page, day, slot.Dinner)), cell(page, sun, slot.Snack));
  await expect.poll(async () => {
    const meals = (await planRange(page, sun, sun)).meals as { id: number; slot_id: number; items: unknown[] }[];
    const moved = meals.find((m) => m.id === cook.meal_id);
    return [moved?.slot_id, moved?.items.length];
  }).toEqual([slot.Snack, 2]);
  await expect(cell(page, sun, slot.Snack).getByRole('button', { name: new RegExp(`^${side}`) })).toBeVisible();
});
