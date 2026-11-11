import { test, expect, type Page } from './clock.ts';
import { expectNoAxeViolations, inTheme, isPhone, setAccountTheme } from './a11y.ts';

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

async function dinnerSlot(page: Page) {
  const list = (await (await page.request.get('/api/v1/meal-slots')).json()) as { id: number; name: string }[];
  return list.find((s) => s.name === 'Dinner')!.id;
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
  const slot = await dinnerSlot(page);
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
  await page.goto(`/plan?day=${day}`);
  await page.getByTestId('batch-card').getByRole('button', { name: 'Remove' }).click();
  await expect(page.getByTestId('batch-card')).toHaveCount(0);
  expect((await planRange(page, day)).batch_sessions).toHaveLength(0);
  await page.getByRole('button', { name: 'Undo' }).click();
  await expect(page.getByTestId('batch-card')).toBeVisible();
  expect((await planRange(page, day)).batch_sessions).toHaveLength(1);
  await call(page, 'DELETE', `/batch-cook/sessions/${(await planRange(page, day)).batch_sessions[0].id}`);
});

test('an admin can hide Batch cook in Settings: no sidebar entry, no Plan tab, and the picks are refused', async ({ page }) => {
  await page.goto('/settings');
  if (isPhone(page)) await page.getByRole('link', { name: /^Your kitchen/ }).click();
  const row = page.getByRole('switch', { name: 'Show Batch cook' });
  await expect(row).toBeChecked();
  await row.click();
  await expect(row).not.toBeChecked();
  const refused = await page.request.get('/api/v1/batch-cook/suggestions');
  expect(refused.status()).toBe(409);
  await page.goto('/plan');
  if (isPhone(page)) await expect(page.getByRole('link', { name: /^Batch cook/ })).toHaveCount(0);
  else await expect(page.getByRole('complementary', { name: 'Sidebar' }).getByRole('link', { name: /^Batch cook/ })).toHaveCount(0);
  await page.goto('/settings');
  if (isPhone(page)) await page.getByRole('link', { name: /^Your kitchen/ }).click();
  await page.getByRole('switch', { name: 'Show Batch cook' }).click();
  await expect(page.getByRole('switch', { name: 'Show Batch cook' })).toBeChecked();
  expect((await page.request.get('/api/v1/batch-cook/suggestions')).status()).toBe(200);
});
