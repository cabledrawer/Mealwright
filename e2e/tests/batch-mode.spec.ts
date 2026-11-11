import { test, expect, type Page } from './clock.ts';
import { checkPage, expectNoSidewaysScroll, inTheme, isPhone } from './a11y.ts';

// Batch cook mode (0.8 wave 6, B3), against the real server: one session of two recipes cooked
// together from its own address, Now and Next, a timer for each recipe that the server keeps (so
// a reload carries on where it was and another phone agrees), Done, next to the end, and the one
// Cooked it for the whole session with one Undo. Runs on Chromium (phone and computer) and WebKit
// (computer), see playwright.config.ts. The Plan card that opens it comes with B2's screens.

const key = () => ({ 'idempotency-key': crypto.randomUUID() });

async function call(page: Page, method: 'POST' | 'PUT' | 'DELETE' | 'PATCH', path: string, data?: object) {
  const response = await page.request.fetch(`/api/v1${path}`, { method, data, headers: key() });
  expect(response.ok(), `${method} ${path}: ${await response.text()}`).toBe(true);
  return (await response.json()) as Record<string, any>;
}

const stamp = () => `${test.info().project.name.replace(/\W/g, '')}${Date.now().toString(36)}${Math.floor(Math.random() * 1296).toString(36)}`;
const INDEX: Record<string, number> = { 'desktop 0.8 batch mode': 0, 'phone 0.8 batch mode': 1, 'webkit 0.8 batch mode': 2 };

function addDays(iso: string, days: number): string {
  const d = new Date(`${iso}T12:00:00Z`);
  d.setUTCDate(d.getUTCDate() + days);
  return d.toISOString().slice(0, 10);
}

/** Two recipes that both chop onions (so the chopping is one shared task), planned as a session. */
async function session(page: Page) {
  const household = (await (await page.request.get('/api/v1/household')).json()) as { today: string };
  const slots = (await (await page.request.get('/api/v1/meal-slots')).json()) as { id: number; name: string }[];
  const dinner = slots.find((s) => s.name === 'Dinner')!.id;
  const onion = (await call(page, 'POST', '/foods', { name: `Onion ${stamp()}`, counted_as: 'count' })).food.id as number;
  const sambar = `Sambar ${stamp()}`;
  const chettinad = `Chettinad ${stamp()}`;
  const a = await call(page, 'POST', '/recipes', {
    name: sambar,
    serves: 4,
    lines: [{ words: 'onion', food_id: onion, amount: 1 }],
    steps: [
      { text: 'Chop the onion.', lines: [0] },
      { text: 'Pressure cook the dal for 3 whistles.' },
      { text: 'Temper the mustard seeds in ghee for 5 minutes.' },
    ],
  });
  const b = await call(page, 'POST', '/recipes', {
    name: chettinad,
    serves: 4,
    lines: [{ words: 'onions', food_id: onion, amount: 2 }],
    steps: [
      { text: 'Chop the onions finely.', lines: [0] },
      { text: 'Fry the onions and chicken for 8 minutes.' },
      { text: 'Simmer for 25 minutes.' },
    ],
  });
  const day = addDays(household.today, 2 + (INDEX[test.info().project.name] ?? 0));
  const made = await call(page, 'POST', '/batch-cook/sessions', {
    date: day,
    slot_id: dinner,
    recipes: [
      { recipe_id: a.id, tub_count: 2 },
      { recipe_id: b.id, tub_count: 3 },
    ],
  });
  return { id: made.session_id as number, sambar, chettinad, day, change: made.change.id as number };
}

type Schedule = { done_count: number; tasks: { id: string; hands: string; state: string }[] };
const schedule = async (page: Page, id: number) =>
  (await (await page.request.get(`/api/v1/batch-cook/sessions/${id}/schedule`)).json()) as Schedule;

const region = (page: Page) => page.getByRole('region', { name: 'Batch cook mode', exact: true });
const now = (page: Page) => page.getByTestId('batch-now');
const done = (page: Page) => page.getByRole('button', { name: 'Done, next →' });

test('cooks a session: shared prep, a timer that survives a reload, Done, next, and the one Cooked it with one Undo', async ({ page }) => {
  const s = await session(page);
  await page.goto(`/batch-cook/session/${s.id}/cook`);
  await expect(region(page)).toBeVisible();
  await expect(page.getByRole('heading', { name: 'Batch cook · 2 recipes' })).toBeVisible();
  await expect(now(page)).toContainText('Chop 3 ');
  await expect(now(page)).toContainText(`1 for ${s.sambar}`);
  await expect(page.getByTestId('batch-in-use')).toContainText('Nothing in use right now'); // chopping needs no equipment
  await expect(page.getByTestId('batch-next')).toBeVisible();
  await expect(page.getByTestId('batch-timer')).toHaveCount(2);

  // Show ingredients lists both recipes' ingredients.
  await page.getByRole('button', { name: 'Show ingredients' }).click();
  await expect(page.getByRole('dialog', { name: 'All ingredients' })).toContainText(s.chettinad);
  await page.getByRole('button', { name: 'Done', exact: true }).click();

  // Done, next frees the dal's pressure cooker: its timer starts on a tap, and is kept.
  await done(page).click();
  await expect(now(page)).not.toContainText('Chop 3 ');
  await page.getByRole('button', { name: `Start timer for ${s.sambar}` }).click();
  await expect(page.getByRole('timer')).toBeVisible();
  await expect(page.getByTestId('batch-in-use')).toContainText('pressure cooker 1 of 1');
  await expect.poll(async () => (await schedule(page, s.id)).done_count).toBe(1);

  // A reload carries on where it was.
  await page.reload();
  await expect(region(page)).toBeVisible();
  await expect(now(page)).not.toContainText('Chop 3 ');
  await expect(page.getByRole('timer')).toBeVisible();
  await expect(page.getByTestId('batch-progress')).toContainText('Task 2 of');

  // The rest: waiting tasks are marked done through the API (their time is not waited for), the
  // hands-on ones with the button.
  for (let guard = 0; guard < 12; guard++) {
    const found = await schedule(page, s.id);
    const waiting = found.tasks.filter((t) => t.hands === 'waiting' && t.state !== 'done');
    for (const t of waiting) await call(page, 'PUT', `/batch-cook/sessions/${s.id}/schedule/tasks/${t.id}/done`);
    await page.reload();
    const cooked = page.getByRole('button', { name: 'Cooked it', exact: true });
    await expect(done(page).or(cooked)).toBeVisible();
    if (await cooked.isVisible()) break;
    await done(page).click();
    await expect.poll(async () => (await schedule(page, s.id)).done_count).toBeGreaterThan(found.done_count);
  }
  await expect(page.getByTestId('batch-now')).toContainText('Everything is cooked');

  // One Cooked it for both recipes.
  await page.getByRole('button', { name: 'Cooked it' }).click();
  const review = page.getByTestId('session-cooked');
  await expect(review).toContainText(s.sambar);
  await expect(review).toContainText(s.chettinad);
  await expect(review).toContainText('tubs');
  await review.getByRole('button', { name: 'Cooked it' }).click();
  await expect(page).toHaveURL(/\/plan/);
  const changes = (await (await page.request.get('/api/v1/changes?area=pantry')).json()) as { changes: { id: number; kind: string; summary: string }[] };
  const cooked = changes.changes.filter((c) => c.kind === 'cooked' && c.summary.includes(s.sambar));
  expect(cooked).toHaveLength(1);
  expect(cooked[0]!.summary).toContain(s.chettinad);

  // One Undo, then the session comes off the plan again.
  await call(page, 'POST', `/changes/${cooked[0]!.id}/undo`);
  await call(page, 'DELETE', `/batch-cook/sessions/${s.id}`);
});

test('a running timer is ended early and a wait that has not started is skipped (RF3, C7)', async ({ page }) => {
  const s = await session(page);
  await page.goto(`/batch-cook/session/${s.id}/cook`);
  await expect(now(page)).toContainText('Chop 3 ');
  const waitingDone = async () => (await schedule(page, s.id)).tasks.filter((t) => t.hands === 'waiting' && t.state === 'done').length;
  // The dal's timer is started, then ended early: its row has no clock any more.
  await done(page).click();
  await page.getByRole('button', { name: `Start timer for ${s.sambar}` }).click();
  await expect(page.getByRole('timer')).toBeVisible();
  await page.getByRole('button', { name: `End timer early for ${s.sambar}` }).click();
  await expect(page.getByRole('timer')).toHaveCount(0);
  await expect.poll(waitingDone).toBe(1);
  // The other recipe's wait is skipped without a timer once it is ready.
  const skip = page.getByRole('button', { name: `Skip wait for ${s.chettinad}` });
  for (let guard = 0; guard < 6 && !(await skip.isVisible()); guard++) {
    await done(page).click();
    await page.waitForTimeout(300);
  }
  await skip.click();
  await expect.poll(waitingDone).toBe(2);
  await call(page, 'DELETE', `/batch-cook/sessions/${s.id}`);
});

test('another phone agrees without reloading', async ({ page }) => {
  const s = await session(page);
  await page.goto(`/batch-cook/session/${s.id}/cook`);
  await expect(now(page)).toContainText('Chop 3 ');
  const other = await page.context().newPage();
  await other.goto(`/batch-cook/session/${s.id}/cook`);
  await expect(now(other)).toContainText('Chop 3 ');
  await done(other).click();
  await expect(now(page)).not.toContainText('Chop 3 ');
  await call(page, 'DELETE', `/batch-cook/sessions/${s.id}`);
});

test('offline, Done, next keeps working and is sent when the connection is back', async ({ page, context }) => {
  const s = await session(page);
  await page.goto(`/batch-cook/session/${s.id}/cook`);
  await expect(now(page)).toContainText('Chop 3 ');
  await context.setOffline(true);
  await done(page).click();
  await expect(now(page)).not.toContainText('Chop 3 ');
  await expect(page.getByTestId('batch-offline')).toBeVisible();
  await context.setOffline(false);
  await expect.poll(async () => (await schedule(page, s.id)).done_count, { timeout: 30_000 }).toBe(1);
  await call(page, 'DELETE', `/batch-cook/sessions/${s.id}`);
});

test('passes the accessibility checks in both themes, and at 200% text nothing scrolls sideways', async ({ page }) => {
  const s = await session(page);
  await page.goto(`/batch-cook/session/${s.id}/cook`);
  await expect(now(page)).toContainText('Chop 3 ');
  await checkPage(page);
  await page.evaluate(() => (document.documentElement.style.fontSize = '200%'));
  for (const theme of ['light', 'dark'] as const) {
    await inTheme(page, theme);
    await expectNoSidewaysScroll(page);
    const box = (await done(page).boundingBox())!;
    expect(box.y + box.height).toBeLessThanOrEqual(page.viewportSize()!.height + 1);
    await expect(page.getByRole('button', { name: 'Leave Batch cook' })).toBeVisible();
  }
  await inTheme(page, 'light');
  if (isPhone(page)) await expectNoSidewaysScroll(page);
  await call(page, 'DELETE', `/batch-cook/sessions/${s.id}`);
});

test('Start batch cook on the Plan card opens batch cook mode for that session', async ({ page }) => {
  const s = await session(page);
  await page.goto(`/plan?day=${s.day}`);
  const card = page.getByTestId('batch-card').filter({ hasText: s.sambar });
  await card.getByRole('button', { name: 'Start batch cook' }).click();
  await expect(page).toHaveURL(new RegExp(`/batch-cook/session/${s.id}/cook$`));
  await expect(region(page)).toBeVisible();
});

test('one pressure cooker is never offered twice, and the screen says what is in use', async ({ page }) => {
  await call(page, 'PATCH', '/household/kitchen', { pressure_cookers: 1 });
  const household = (await (await page.request.get('/api/v1/household')).json()) as { today: string };
  const slots = (await (await page.request.get('/api/v1/meal-slots')).json()) as { id: number; name: string }[];
  const dals = [];
  for (const n of [1, 2]) {
    dals.push(await call(page, 'POST', '/recipes', { name: `Dal ${n} ${stamp()}`, serves: 4, steps: [{ text: 'Pressure cook the dal for 3 whistles.' }, { text: 'Fry the onions.' }] }));
  }
  const day = addDays(household.today, 6 + (INDEX[test.info().project.name] ?? 0));
  const made = await call(page, 'POST', '/batch-cook/sessions', {
    date: day,
    slot_id: slots.find((x) => x.name === 'Dinner')!.id,
    recipes: dals.map((d) => ({ recipe_id: d.id, tub_count: 2 })),
  });
  await page.goto(`/batch-cook/session/${made.session_id}/cook`);
  const start = page.getByRole('button', { name: /^Start timer for / });
  await expect(start).toHaveCount(1); // the second dal waits for the cooker
  await start.click();
  await expect(page.getByRole('timer')).toBeVisible();
  await expect(start).toHaveCount(0);
  await expect(page.getByTestId('batch-in-use')).toContainText('pressure cooker 1 of 1');
  await call(page, 'DELETE', `/batch-cook/sessions/${made.session_id}`);
});

test('a recipe cooked on its own is left out of the one Cooked it, and said so', async ({ page }) => {
  const s = await session(page);
  const found = (await (await page.request.get(`/api/v1/batch-cook/sessions/${s.id}`)).json()) as { recipes: { batch_id: number; recipe_name: string }[] };
  const alone = found.recipes.find((r) => r.recipe_name === s.sambar)!;
  await call(page, 'POST', `/plan/batches/${alone.batch_id}/cook`, {});
  await call(page, 'POST', `/batch-cook/sessions/${s.id}/schedule`, {});
  const tasks = (await schedule(page, s.id)).tasks;
  for (const t of tasks) await call(page, 'PUT', `/batch-cook/sessions/${s.id}/schedule/tasks/${t.id}/done`);
  await page.goto(`/batch-cook/session/${s.id}/cook`);
  await page.getByRole('button', { name: 'Cooked it', exact: true }).click();
  const review = page.getByTestId('session-cooked');
  await expect(review).toContainText(s.chettinad);
  await expect(page.getByTestId('session-recipe')).toHaveCount(1);
  await expect(page.getByTestId('session-already')).toContainText(`${s.sambar} · already cooked`);
  await review.getByRole('button', { name: 'Cooked it' }).click();
  await expect(page).toHaveURL(/\/plan/);
  const changes = (await (await page.request.get('/api/v1/changes?area=pantry')).json()) as { changes: { id: number; kind: string; summary: string }[] };
  for (const c of changes.changes.filter((c) => c.kind === 'cooked' && (c.summary.includes(s.chettinad) || c.summary.includes(s.sambar)))) {
    await call(page, 'POST', `/changes/${c.id}/undo`);
  }
  await call(page, 'DELETE', `/batch-cook/sessions/${s.id}`);
});
