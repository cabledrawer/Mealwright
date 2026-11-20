import { test, expect, type Page } from './clock.ts';
import { workerReady } from './worker.ts';
import { expectNoAxeViolations, expectNoSidewaysScroll, inTheme, isPhone, setAccountTheme } from './a11y.ts';

// Batch cook (Experimental; 0.8 wave 6, B2): the sidebar entry on a computer and the Plan's third
// tab on a phone, the first-time note, Your kitchen on first use, the picks (swap, show me others),
// Plan this batch (one Cook once sheet after another, one Undo for the whole session), the Plan's
// card and "Batch · Sun" tags, Change and Remove, and the admin's switch. Runs on Chromium (computer
// and phone) and WebKit.
//
// The three projects share one server. Each plans on days of its own, far ahead (the plan accepts
// 731 days), with recipes named for the project so another project's picks never mix with its own.

const key = () => ({ 'idempotency-key': crypto.randomUUID() });

async function call(page: Page, method: 'POST' | 'PUT' | 'DELETE' | 'PATCH', path: string, data?: object) {
  const response = await page.request.fetch(`/api/v1${path}`, { method, data, headers: key() });
  expect(response.ok(), `${method} ${path}: ${await response.text()}`).toBe(true);
  return (await response.json()) as Record<string, any>;
}

const INDEX: Record<string, number> = { 'desktop 0.8 batch cook': 0, 'phone 0.8 batch cook': 1, 'webkit 0.8 batch cook': 2 };
const addDays = (iso: string, days: number) => {
  const d = new Date(`${iso}T12:00:00Z`);
  d.setUTCDate(d.getUTCDate() + days);
  return d.toISOString().slice(0, 10);
};
/** This project's own cook day, and the test's own (k 0 to 3), far ahead of every other plan test. */
const cookDay = (today: string, k: number) => addDays(today, 600 + 12 * (INDEX[test.info().project.name] ?? 0) + 3 * k);
const word = (iso: string) => {
  const d = new Date(`${iso}T12:00:00Z`);
  return new Intl.DateTimeFormat('en-GB', { weekday: 'short', timeZone: 'UTC' }).format(d);
};

/** "Saturday 5 December", the grid's day heading. */
const fullDay = (iso: string) => {
  const d = new Date(`${iso}T12:00:00Z`);
  const part = (o: Intl.DateTimeFormatOptions) => new Intl.DateTimeFormat('en-GB', { ...o, timeZone: 'UTC' }).format(d);
  return `${part({ weekday: 'long' })} ${d.getUTCDate()} ${part({ month: 'long' })}`;
};

async function today(page: Page) {
  return ((await (await page.request.get('/api/v1/household')).json()) as { today: string }).today;
}

/** Three recipes with steps (two share an onion to chop), named for this project. */
async function seed(page: Page, tag: string) {
  const onion = (await call(page, 'POST', '/foods', { name: `Onion ${tag}` })).food.id as number;
  const make = async (name: string, steps: string[], withOnion: boolean) =>
    (await call(page, 'POST', '/recipes', {
      name: `${name} ${tag}`,
      steps: steps.map((text) => ({ text })),
      lines: withOnion ? [{ words: `1 onion ${tag}, finely chopped`, food_id: onion, amount: 1 }] : [],
    })).id as number;
  const a = await make('Chettinad', ['Chop the onion.', 'Marinate for 30 minutes.', 'Fry the masala.'], true);
  const b = await make('Sambar', ['Chop the onion.', 'Pressure cook for 3 whistles.'], true);
  const c = await make('Keerai', ['Fry the spinach for 5 minutes.'], false);
  return { a, b, c };
}

async function mealSlot(page: Page, name: string) {
  const list = (await (await page.request.get('/api/v1/meal-slots')).json()).meal_slots as { id: number; name: string }[];
  return list.find((s) => s.name === name)!.id;
}

/** Open Batch cook (the sidebar's entry, or the Plan's tab on a phone), past the first-time note and Your kitchen. */
async function open(page: Page) {
  await page.goto('/plan');
  if (isPhone(page)) await page.getByRole('link', { name: /^Batch cook/ }).click();
  else await page.getByRole('complementary', { name: 'Sidebar' }).getByRole('link', { name: /^Batch cook/ }).click();
  await expect(page).toHaveURL(/\/batch-cook/);
  // The picks are in; Your kitchen opens with them the first time it is used (once per server).
  await expect(page.getByText(/together/).first()).toBeVisible();
  await page.evaluate(() => new Promise((done) => requestAnimationFrame(() => requestAnimationFrame(done))));
  const kitchen = page.getByRole('dialog', { name: 'Your kitchen' });
  if (await kitchen.isVisible()) await kitchen.getByRole('button', { name: 'Save' }).click();
  await expect(kitchen).toHaveCount(0);
}

async function chooseDay(page: Page, day: string) {
  await page.getByRole('button', { name: 'Other…' }).click();
  await page.getByLabel('Cook day', { exact: true }).last().fill(day);
}

async function planRange(page: Page, day: string) {
  return (await (await page.request.get(`/api/v1/plan?from=${day}&to=${addDays(day, 4)}`)).json()) as Record<string, any>;
}

test('the entry is where the design puts it: the sidebar on a computer, the Plan’s third tab on a phone', async ({ page }) => {
  await page.goto('/plan');
  if (isPhone(page)) {
    const tabs = page.getByRole('group', { name: 'View' });
    await expect(tabs.getByRole('button', { name: 'Week' })).toBeVisible();
    await expect(tabs.getByRole('button', { name: 'Month' })).toBeVisible();
    await expect(tabs.getByRole('link', { name: /^Batch cook/ })).toBeVisible();
    await expect(page.getByRole('navigation', { name: 'Main' }).getByRole('link')).toHaveCount(5);
  } else {
    const links = page.getByRole('complementary', { name: 'Sidebar' }).getByRole('navigation', { name: 'Main' }).getByRole('link');
    await expect(links.nth(1)).toHaveText('Plan');
    await expect(links.nth(2)).toHaveText(/^\s*Batch cook/);
    await expect(links.nth(2)).toContainText('Experimental');
    await expect(links.nth(3)).toHaveText('Shopping');
  }
});

test('phone: the Plan header is the title row, then the Week · Month · Batch cook switch the full width, with Eat · Cook · Both fully visible (RF5)', async ({ page }) => {
  test.skip(!isPhone(page), 'the phone header');
  await page.goto('/plan');
  const title = page.getByRole('heading', { level: 1, name: 'Plan' });
  const switchBox = page.getByRole('group', { name: 'View' });
  await expect(switchBox.getByRole('link', { name: /^Batch cook/ })).toBeVisible();
  const [t, sw, settings, width] = await Promise.all([
    title.boundingBox(),
    switchBox.boundingBox(),
    page.getByRole('link', { name: /· Settings$/ }).boundingBox(),
    page.evaluate(() => document.documentElement.clientWidth),
  ]);
  // The avatar and cog stay on the title's row; the switch is under it and spans the page.
  expect(Math.abs(settings!.y + settings!.height / 2 - (t!.y + t!.height / 2))).toBeLessThan(30);
  expect(sw!.y).toBeGreaterThanOrEqual(t!.y + t!.height - 1);
  expect(sw!.width).toBeGreaterThan(width - 60);
  // Eat · Cook · Both is under the header, not half hidden by it: its middle is what a tap would hit.
  for (const name of ['Eat', 'Cook', 'Both']) {
    const button = page.getByRole('group', { name: 'Show' }).getByRole('button', { name, exact: true });
    await expect(button).toBeVisible();
    const hit = await button.evaluate((el) => {
      const r = el.getBoundingClientRect();
      const top = document.elementFromPoint(r.x + r.width / 2, r.y + r.height / 2);
      return top === el || el.contains(top);
    });
    expect(hit, name).toBe(true);
  }
});

test('the first-time note says Got it once, per person, and the picks come from your recipes with their why', async ({ page }) => {
  const tag = `n${Date.now().toString(36)}`;
  await seed(page, tag);
  await open(page);
  const note = page.getByText('The picks and timings are guesses.');
  await expect(note).toBeVisible();
  await page.getByRole('button', { name: 'Got it' }).click();
  await expect(note).toHaveCount(0);
  await page.reload();
  await expect(page.getByRole('heading', { name: /Batch cook|Plan/ }).first()).toBeVisible();
  await expect(page.getByText('About ', { exact: false }).first()).toBeVisible();
  await expect(note).toHaveCount(0);
  await expect(page.getByText(/together/).first()).toBeVisible();
  await expect(page.getByText(/one by one/).first()).toBeVisible();
  // Two joined strings always have their space (RF5): "one by one · hob 4 · pressure cooker 1 · oven yes".
  if (!isPhone(page)) {
    await expect(page.locator('.times .muted')).toHaveText(/one by one · hob \d+ · pressure cooker \d+ · oven (yes|no) Change$/);
  }
  const picks = page.getByRole('list').filter({ has: page.getByRole('button', { name: /^Swap/ }) }).getByRole('listitem');
  await expect(picks).toHaveCount(3);
  await expect(page.getByText(/^Shares onion .* prep with/).first()).toBeVisible();
  await expect(page.getByRole('link', { name: /^Open recipe/ }).first()).toBeVisible();
  for (const theme of ['light', 'dark'] as const) {
    await setAccountTheme(page, theme);
    await inTheme(page, theme);
    await expectNoAxeViolations(page, `Batch cook, ${isPhone(page) ? 'phone' : 'desktop'}, ${theme}`);
  }
  await setAccountTheme(page, 'auto');
});

test('swap changes one pick, and Show me others gives a fresh set when there are others', async ({ page }) => {
  const tag = `s${Date.now().toString(36)}`;
  await seed(page, tag);
  // More recipes than a set, so there are others.
  for (const name of ['Rasam', 'Poriyal', 'Kootu']) {
    await call(page, 'POST', '/recipes', { name: `${name} ${tag}`, steps: [{ text: 'Cook it for 10 minutes.' }] });
  }
  await open(page);
  const names = async () => (await page.locator('.nm').allTextContents()).map((n) => n.trim());
  const first = await names();
  expect(first).toHaveLength(3);
  await page.getByRole('button', { name: `Swap ${first[2]}` }).click();
  await expect.poll(names).not.toEqual(first);
  const swapped = await names();
  expect(swapped.slice(0, 2)).toEqual(first.slice(0, 2));
  expect(swapped).not.toContain(first[2]);
  await page.getByRole('button', { name: 'Show me others' }).click();
  await expect.poll(names).not.toEqual(swapped);
  await page.getByRole('radio', { name: '2' }).click();
  await expect(page.locator('.nm')).toHaveCount(2);
});

test('Plan this batch goes through Cook once for each recipe, plans one session, and one Undo takes it all away', async ({ page }) => {
  const tag = `p${Date.now().toString(36)}`;
  await seed(page, tag);
  const day = cookDay(await today(page), 0);
  await open(page);
  await page.getByRole('radio', { name: '2' }).click();
  await expect(page.locator('.nm')).toHaveCount(2);
  await chooseDay(page, day);
  await page.getByRole('button', { name: 'Plan this batch' }).click();
  const sheet = page.getByRole('dialog', { name: /Cook once, eat for… 1 of 2/ });
  await expect(sheet).toBeVisible();
  await expect(sheet.getByRole('heading', { name: /1 of 2/ })).toBeVisible();
  await sheet.getByRole('button', { name: 'Next recipe' }).click();
  const second = page.getByRole('dialog', { name: /Cook once, eat for… 2 of 2/ });
  await expect(second).toBeVisible();
  // The first recipe's tubs are in the second one's grid as taken (F229).
  await expect(second.getByText('already placed').first()).toBeVisible();
  await second.getByRole('button', { name: 'Plan this batch' }).click();
  // It lands on the Plan, on the cook day: one Batch cook card, and the meals say where they came from.
  await expect(page).toHaveURL(/\/plan/);
  const card = page.getByTestId('batch-card');
  await expect(card).toContainText('Batch cook · 2 recipes');
  await expect(card).toContainText('Experimental');
  await expect(card.getByRole('button', { name: 'Start batch cook' })).toBeVisible();
  await expect(card.getByRole('button', { name: 'Change' })).toBeVisible();
  const tag_ = `Batch · ${word(day)}`;
  await expect(page.getByText(tag_).first()).toBeVisible();
  const plan = await planRange(page, day);
  expect(plan.batch_sessions).toHaveLength(1);
  expect(plan.batch_cooks.filter((b: any) => b.session_id === plan.batch_sessions[0].id)).toHaveLength(2);
  // One Undo for the whole session.
  await page.getByRole('button', { name: 'Undo' }).click();
  await expect(page.getByTestId('batch-card')).toHaveCount(0);
  expect((await planRange(page, day)).batch_sessions).toHaveLength(0);
});

test('Plan this batch asks which optional ingredients each recipe will use, and batch cook mode follows the answer (RF3, C6)', async ({ page }) => {
  const tag = `o${Date.now().toString(36)}`;
  const onion = (await call(page, 'POST', '/foods', { name: `Onion ${tag}` })).food.id as number;
  const cashew = (await call(page, 'POST', '/foods', { name: `Cashew ${tag}` })).food.id as number;
  const a = (await call(page, 'POST', '/recipes', {
    name: `Biryani ${tag}`,
    lines: [
      { words: `1 onion ${tag}`, food_id: onion, amount: 1 },
      { words: `50 g cashew ${tag}`, food_id: cashew, amount: 50, unit: 'g', optional: true },
    ],
    steps: [{ text: 'Chop the onion.', lines: [0] }, { text: 'Fry the cashews for the top.', lines: [1], optional: true }, { text: 'Simmer for 20 minutes.' }],
  })).id as number;
  const b = (await call(page, 'POST', '/recipes', { name: `Dal ${tag}`, steps: [{ text: 'Simmer for 15 minutes.' }] })).id as number;
  const day = addDays(await today(page), 700 + 12 * (INDEX[test.info().project.name] ?? 0));
  const made = await call(page, 'POST', '/batch-cook/sessions', {
    date: day,
    slot_id: await mealSlot(page, 'Dinner'),
    recipes: [{ recipe_id: a, tub_count: 2 }, { recipe_id: b, tub_count: 2 }],
  });
  // Change opens the picks with the session's own two recipes.
  await page.goto(`/batch-cook?change=${made.session_id}`);
  await expect(page.getByText(/together/).first()).toBeVisible();
  await page.evaluate(() => new Promise((done) => requestAnimationFrame(() => requestAnimationFrame(done))));
  const kitchen = page.getByRole('dialog', { name: 'Your kitchen' });
  if (await kitchen.isVisible()) await kitchen.getByRole('button', { name: 'Save' }).click();
  await page.getByRole('button', { name: 'Plan this batch' }).click();
  // The optional question comes first, then the Cook once sheet; Cancel on it plans nothing.
  const asked = page.getByTestId('plan-optional');
  await expect(asked).toBeVisible();
  await expect(asked).toContainText(`Biryani ${tag}`);
  await asked.getByRole('checkbox').uncheck(); // no cashews
  await asked.getByRole('button', { name: 'Next' }).click();
  await page.getByRole('dialog', { name: /1 of 2/ }).getByRole('button', { name: 'Next recipe' }).click();
  await page.getByRole('dialog', { name: /2 of 2/ }).getByRole('button', { name: 'Plan this batch' }).click();
  await expect(page).toHaveURL(/\/plan/);
  const plan = await planRange(page, day);
  const items = plan.meals.flatMap((m: any) => m.items).filter((i: any) => i.recipe?.name === `Biryani ${tag}`);
  expect(items).toHaveLength(1);
  expect(items[0].optional_skipped).toHaveLength(1);
  // Batch cook mode has no step for the cashews that were left out.
  const sid = plan.batch_sessions[0].id as number;
  const schedule = await call(page, 'POST', `/batch-cook/sessions/${sid}/schedule`, {});
  expect((schedule.tasks as { title: string }[]).some((t) => /cashew/i.test(t.title))).toBe(false);
  await call(page, 'DELETE', `/batch-cook/sessions/${sid}`);
});

test('Cancel on the second sheet plans nothing', async ({ page }) => {
  const tag = `c${Date.now().toString(36)}`;
  await seed(page, tag);
  const day = cookDay(await today(page), 1);
  await open(page);
  await page.getByRole('radio', { name: '2' }).click();
  await chooseDay(page, day);
  await page.getByRole('button', { name: 'Plan this batch' }).click();
  await page.getByRole('dialog', { name: /1 of 2/ }).getByRole('button', { name: 'Next recipe' }).click();
  const second = page.getByRole('dialog', { name: /2 of 2/ });
  await expect(second.getByTestId('cook-summary')).toBeVisible();
  await second.getByRole('button', { name: 'Cancel' }).click();
  await expect(page.getByRole('dialog')).toHaveCount(0);
  const plan = await planRange(page, day);
  expect(plan.batch_sessions).toHaveLength(0);
  expect(plan.meals).toHaveLength(0);
});

test('Change reopens the picks with the session’s recipes, and Remove takes the session off with one Undo', async ({ page }) => {
  const tag = `r${Date.now().toString(36)}`;
  const ids = await seed(page, tag);
  const day = cookDay(await today(page), 2);
  const slot = await mealSlot(page, 'Lunch'); // not the server's own pick (Dinner), so a move would show
  const body = (recipes: number[]) => ({
    date: day,
    slot_id: slot,
    recipes: recipes.map((recipe_id) => ({ recipe_id, tub_count: 2, pattern: 'dinners' })),
  });
  const made = await call(page, 'POST', '/batch-cook/sessions', body([ids.a, ids.b]));
  await page.goto(`/plan?day=${day}`);
  const card = page.getByTestId('batch-card');
  await expect(card).toContainText('Batch cook · 2 recipes');
  await card.getByRole('button', { name: 'Change' }).click();
  await expect(page).toHaveURL(new RegExp(`/batch-cook\\?change=${made.session_id}`));
  await expect(page.locator('.nm').filter({ hasText: 'Chettinad' })).toBeVisible();
  await expect(page.locator('.nm').filter({ hasText: 'Sambar' })).toBeVisible();
  // Plan this batch, unchanged: the session stays in the meal it was in.
  await page.getByRole('button', { name: 'Plan this batch' }).click();
  await page.getByRole('dialog', { name: /1 of 2/ }).getByRole('button', { name: 'Next recipe' }).click();
  await page.getByRole('dialog', { name: /2 of 2/ }).getByRole('button', { name: 'Plan this batch' }).click();
  await expect(page).toHaveURL(/\/plan/);
  await expect(page.getByTestId('batch-card')).toContainText('Batch cook · 2 recipes');
  const after = (await planRange(page, day)).batch_sessions as { id: number }[];
  expect(after).toHaveLength(1);
  expect(after[0].id).not.toBe(made.session_id);
  const changed = (await (await page.request.get(`/api/v1/batch-cook/sessions/${after[0].id}`)).json()) as { slot_id: number };
  expect(changed.slot_id).toBe(slot);
  await page.goto(`/plan?day=${day}`);
  await page.getByTestId('batch-card').getByRole('button', { name: 'Remove' }).click();
  await expect(page.getByTestId('batch-card')).toHaveCount(0);
  expect((await planRange(page, day)).batch_sessions).toHaveLength(0);
  await page.getByRole('button', { name: 'Undo' }).click();
  await expect(page.getByTestId('batch-card')).toBeVisible();
  expect((await planRange(page, day)).batch_sessions).toHaveLength(1);
  await call(page, 'DELETE', `/batch-cook/sessions/${(await planRange(page, day)).batch_sessions[0].id}`);
});

test('Start batch cook opens the current session after another person pressed Change (never "not found")', async ({ page }) => {
  const tag = `s${Date.now().toString(36)}`;
  const ids = await seed(page, tag);
  const day = cookDay(await today(page), 2);
  const body = (recipes: number[]) => ({
    date: day,
    recipes: recipes.map((recipe_id) => ({ recipe_id, tub_count: 1, pattern: 'dinners' })),
  });
  const made = await call(page, 'POST', '/batch-cook/sessions', body([ids.a, ids.b]));
  await page.goto(`/plan?day=${day}`);
  await expect(page.getByTestId('batch-card')).toContainText('Batch cook · 2 recipes');
  // Someone else presses Change: the session gets a new id while this Plan is still open.
  const changed = await call(page, 'PUT', `/batch-cook/sessions/${made.session_id}`, body([ids.a, ids.c]));
  expect(changed.session_id).not.toBe(made.session_id);
  await page.getByTestId('batch-card').getByRole('button', { name: 'Start batch cook' }).click();
  await expect(page).toHaveURL(new RegExp(`/batch-cook/session/${changed.session_id}/cook`));
  await expect(page.getByText(/not found/i)).toHaveCount(0);
  await call(page, 'DELETE', `/batch-cook/sessions/${changed.session_id}`);
});

test('the Batch cook card sits inside its cook day, above that day’s meals, on a phone and a computer (RF5)', async ({ page }) => {
  const tag = `d${Date.now().toString(36)}`;
  const ids = await seed(page, tag);
  const day = cookDay(await today(page), 1);
  const dinner = await mealSlot(page, 'Dinner');
  const made = await call(page, 'POST', '/batch-cook/sessions', {
    date: day,
    slot_id: dinner,
    recipes: [ids.a, ids.b].map((recipe_id) => ({ recipe_id, tub_count: 1, pattern: 'dinners' })),
  });
  try {
    await page.goto(`/plan?day=${day}`);
    const card = page.getByTestId('batch-card');
    await expect(card).toHaveCount(1);
    if (isPhone(page)) {
      // Inside the day's own section, before its first meal. Both places are read in one go: the
      // page scrolls to the day as it opens, so two separate readings could differ by a scroll.
      const section = page.locator(`[data-plan-day="${day}"]`);
      await expect(section.getByTestId('batch-card')).toHaveCount(1);
      await expect(section.locator('.meal').first()).toBeVisible();
      const at = await section.evaluate((el) => ({
        card: el.querySelector('[data-testid="batch-card"]')!.getBoundingClientRect().y,
        meal: el.querySelector('.meal')!.getBoundingClientRect().y,
      }));
      expect(at.card).toBeLessThan(at.meal);
    } else {
      // In the day's column of the week grid, between the day's name and its meals.
      const box = (await card.boundingBox())!;
      const head = (await page.getByRole('heading', { level: 3, name: fullDay(day) }).boundingBox())!;
      const cell = (await page.getByTestId(`cell-${day}-${dinner}`).boundingBox())!;
      expect(box.x).toBeGreaterThanOrEqual(head.x - 2);
      expect(box.x + box.width).toBeLessThanOrEqual(head.x + head.width + 2);
      expect(box.y).toBeGreaterThan(head.y);
      expect(box.y + box.height).toBeLessThanOrEqual(cell.y + 1);
    }
    await expectNoSidewaysScroll(page);
  } finally {
    await call(page, 'DELETE', `/batch-cook/sessions/${made.session_id}`);
  }
});

test('an admin can hide Batch cook in Settings: no sidebar entry, no Plan tab, and the picks are refused', async ({ page }) => {
  await page.goto('/settings/kitchen');
  const row = page.getByRole('switch', { name: 'Show Batch cook' });
  await expect(row).toBeChecked();
  const saved = (checked: boolean) =>
    page.waitForResponse((r) => r.url().endsWith('/api/v1/household') && r.request().method() === 'PATCH' && r.ok() && r.request().postData()?.includes(String(checked)) === true);
  const hiding = saved(false);
  await row.click();
  await hiding;
  await expect(row).not.toBeChecked();
  const refused = await page.request.get('/api/v1/batch-cook/suggestions');
  expect(refused.status()).toBe(409);
  await page.goto('/plan');
  if (isPhone(page)) await expect(page.getByRole('link', { name: /^Batch cook/ })).toHaveCount(0);
  else await expect(page.getByRole('complementary', { name: 'Sidebar' }).getByRole('link', { name: /^Batch cook/ })).toHaveCount(0);
  await page.goto('/settings/kitchen');
  const showing = saved(true);
  await page.getByRole('switch', { name: 'Show Batch cook' }).click();
  await showing;
  await expect(page.getByRole('switch', { name: 'Show Batch cook' })).toBeChecked();
  expect((await page.request.get('/api/v1/batch-cook/suggestions')).status()).toBe(200);
});

test('while Batch cook is hidden the Plan card has no buttons, and taking the session off is refused (cabledrawer 11 Nov)', async ({ page }) => {
  const tag = `h${Date.now().toString(36)}`;
  const ids = await seed(page, tag);
  const day = cookDay(await today(page), 3);
  const made = await call(page, 'POST', '/batch-cook/sessions', {
    date: day,
    recipes: [ids.a, ids.b].map((recipe_id) => ({ recipe_id, tub_count: 1, pattern: 'dinners' })),
  });
  await call(page, 'PATCH', '/household', { batch_cook: false });
  try {
    await page.goto(`/plan?day=${day}`);
    const card = page.getByTestId('batch-card');
    await expect(card).toContainText('Batch cook · 2 recipes');
    await expect(card.getByRole('button', { name: 'Remove' })).toHaveCount(0);
    await expect(card.getByRole('button', { name: 'Change' })).toHaveCount(0);
    expect((await page.request.delete(`/api/v1/batch-cook/sessions/${made.session_id}`, { headers: key() })).status()).toBe(409);
    await expect(card.getByRole('button', { name: 'Start batch cook' })).toHaveCount(0);
  } finally {
    await call(page, 'PATCH', '/household', { batch_cook: true });
  }
  await page.goto(`/plan?day=${day}`);
  await expect(page.getByTestId('batch-card').getByRole('button', { name: 'Change' })).toBeVisible();
  await call(page, 'DELETE', `/batch-cook/sessions/${made.session_id}`);
});

test('offline the picks can be read but not changed: no Plan this batch, no Swap, no Show me others', async ({ page, context }) => {
  const tag = `o${Date.now().toString(36)}`;
  await seed(page, tag);
  await call(page, 'POST', '/recipes', { name: `Extra ${tag}`, steps: [{ text: 'Cook it for 10 minutes.' }] });
  await open(page);
  await expect(page.getByRole('button', { name: 'Plan this batch' })).toBeEnabled();
  await workerReady(page);
  await context.setOffline(true);
  try {
    await expect(page.getByRole('button', { name: 'Plan this batch' })).toBeDisabled();
    await expect(page.getByRole('button', { name: 'Show me others' })).toBeDisabled();
    await expect(page.getByRole('button', { name: /^Swap/ }).first()).toBeDisabled();
    await expect(page.getByText(/Batch cook changes/)).toBeVisible();
    await expect(page.locator('.nm').first()).toBeVisible(); // what was read stays on screen
  } finally {
    await context.setOffline(false);
  }
});

test('fewer recipes than asked: the set says so, and with one recipe there is nothing to plan', async ({ page }) => {
  // The server's pool grows with every test, so the answer is made here: 2 recipes can be
  // picked, then only 1.
  let picks = 2;
  await page.route('**/api/v1/batch-cook/suggestions*', async (route) => {
    const day = '2026-11-15';
    await route.fulfill({
      json: {
        date: day,
        count: 3,
        picks: Array.from({ length: picks }, (_, i) => ({ recipe_id: i + 1, name: `Fake ${i + 1}`, minutes: 20, why: 'Fits your kitchen.', use_soon: null })),
        together_minutes: 30,
        one_by_one_minutes: 40,
        pool: picks,
        free_days: [day],
        kitchen: { hob_rings: 4, pressure_cookers: 1, oven: true, asked: true },
      },
    });
  });
  await page.goto('/batch-cook');
  await expect(page.getByText('Only 2 of your recipes have steps, so this batch has 2.')).toBeVisible();
  await expect(page.locator('.nm')).toHaveCount(2);
  await expect(page.getByRole('button', { name: 'Plan this batch' })).toBeEnabled();
  picks = 1;
  await page.getByRole('radio', { name: '4' }).click();
  await expect(page.getByText('Only 1 recipe has steps, so there is nothing to batch with. Add steps to another recipe.')).toBeVisible();
  await expect(page.getByRole('button', { name: 'Plan this batch' })).toBeDisabled();
});
