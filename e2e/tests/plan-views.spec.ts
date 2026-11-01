import { test, expect, type Page } from './clock.ts';
import { checkPage, expectNoSidewaysScroll, inTheme, isPhone, setAccountTheme, THEMES } from './a11y.ts';

// The Plan's switch Both · Eat · Cook, Plan it on the recipe page, the phone Plan that opens on
// today, and the Plan at 768–1100 px wide (0.7, P2). Runs on Chromium, phone and computer. Every
// test plans in a week of its own, far from the other plan tests' (and scopes what it checks by
// names of its own), because the two projects share one server. The tests' day is a Saturday.
//
// Weeks ahead of today (the plan accepts 0 to 104), one block per plan spec; the next spec takes
// the free weeks 80 to 83:
//   plan-views Plan it tests 0 and 1 (today's 14 days), plan.spec.ts 2 to 34, plan-cook-once.spec.ts 35 to 64,
//   plan-views.spec.ts 65 to 79, plan-portions.spec.ts 84 to 104.

const key = () => ({ 'idempotency-key': crypto.randomUUID() });

async function call(page: Page, method: 'POST' | 'PUT' | 'DELETE' | 'PATCH', path: string, data?: object) {
  const response = await page.request.fetch(`/api/v1${path}`, { method, data, headers: key() });
  expect(response.ok(), `${method} ${path}: ${await response.text()}`).toBe(true);
  return (await response.json()) as Record<string, any>;
}

const INDEX: Record<string, number> = { 'desktop 0.7 plan views': 0, 'phone 0.7 plan views': 1, 'webkit 0.7 plan views': 2 };
const projectIndex = () => INDEX[test.info().project.name] ?? 0;
/** A Saturday far from the other plan tests' weeks: this project's own, and the test's own (k 0 to 4: 0 to 2 here, 3 and 4 the width tests). */
const far = (today: string, k: number) => addDays(today, 7 * (65 + projectIndex() * 5 + k));
/** Short, so a name made with it is no longer than a real one: a word the width tests can't break. */
const short = () => Math.floor(Date.now() * 1000 + Math.random() * 1000).toString(36).slice(-6);
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
/** "Sun 18": how the views write a day. */
const dayWords = (iso: string) => `${dayShort(iso)} ${Number(iso.slice(8, 10))}`;

async function setup(page: Page) {
  const household = (await (await page.request.get('/api/v1/household')).json()) as { today: string };
  const list = (await (await page.request.get('/api/v1/meal-slots')).json()) as { id: number; name: string }[];
  const slot = Object.fromEntries(list.map((s) => [s.name, s.id])) as Record<string, number>;
  const me = (await (await page.request.get('/api/v1/me')).json()) as { id: number; name: string };
  return { today: household.today, slot, me };
}

type Step = { text: string };
const makeRecipe = async (page: Page, name: string, extra: Record<string, unknown> = {}, steps: Step[] = []) =>
  (await call(page, 'POST', '/recipes', { name, serves: 4, time_minutes: 30, steps, ...extra })).id as number;
const planned = async (page: Page, recipeId: number, day: string, slotId: number) =>
  (await call(page, 'POST', '/plan/items', { date: day, slot_id: slotId, recipe_id: recipeId })) as { item_id: number; meal_id: number };

async function planRange(page: Page, from: string, to: string) {
  return (await (await page.request.get(`/api/v1/plan?from=${from}&to=${to}`)).json()) as Record<string, any>;
}

/** Open the Plan on the week that holds `day` (the Next week button, as a person would). */
async function openWeekOf(page: Page, today: string, day: string) {
  await page.goto('/plan');
  await expect(switchOf(page)).toBeVisible();
  const ahead = Math.round((new Date(`${day}T12:00:00Z`).getTime() - new Date(`${today}T12:00:00Z`).getTime()) / 86_400_000 / 7);
  for (let i = 0; i < ahead; i++) await page.getByRole('button', { name: 'Next week' }).click();
}

/** The switch (the recipe tray has a group called Show too, so it is the one with a Both button). */
const switchOf = (page: Page) => page.getByRole('group', { name: 'Show', exact: true }).filter({ has: page.getByRole('button', { name: 'Both', exact: true }) });
const show = (page: Page, which: 'Both' | 'Eat' | 'Cook') => switchOf(page).getByRole('button', { name: which, exact: true });
const dayCard = (page: Page, day: string) => page.getByRole('region', { name: dayName(day) });

const scriptErrors: string[] = [];
test.beforeEach(async ({ page }) => {
  scriptErrors.length = 0;
  page.on('pageerror', (error) => scriptErrors.push(error.message));
  await setAccountTheme(page, 'auto');
});
test.afterEach(() => {
  expect(scriptErrors, 'the page raised no script errors').toEqual([]);
});

/**
 * A week to look at: on `day` (a Saturday) a fresh Pongal for breakfast and a Biryani batch for
 * dinner (3 tubs, so 4 portions: 1 eaten now); two tubs go in Sunday's lunch, the third is spare.
 * The person is ticked as eating the cook-day dinner and owns the two tubs.
 */
async function seedWeek(page: Page, k: { today: string; slot: Record<string, number>; me: { id: number; name: string } }, day: string) {
  const s = short();
  const pongal = `Pongal ${s}`;
  const biryani = `Biryani ${s}`;
  const fresh = await planned(page, await makeRecipe(page, pongal, { serves: 2, time_minutes: 30 }), day, k.slot.Breakfast);
  const cook = await planned(page, await makeRecipe(page, biryani, { serves: 2, time_minutes: 95 }), day, k.slot.Dinner);
  const made = await call(page, 'POST', `/plan/items/${cook.item_id}/batch`, { tub_count: 3, pattern: 'pick', prep_note: 'Soak the rice' });
  await call(page, 'PUT', `/plan/meals/${cook.meal_id}/eaters`, { login_ids: [k.me.id] });
  const sunday = addDays(day, 1);
  const plan = await planRange(page, day, sunday);
  const tubs = plan.tubs.filter((t: any) => t.batch_id === made.batch_id) as { id: number }[];
  for (const tub of tubs.slice(0, 2)) {
    await call(page, 'POST', `/plan/tubs/${tub.id}/place`, { date: sunday, slot_id: k.slot.Lunch });
    await call(page, 'PATCH', `/plan/tubs/${tub.id}`, { member_login_id: k.me.id });
  }
  return { pongal, biryani, freshMeal: fresh, cookMeal: cook, batch: made.batch_id as number, sunday };
}

// --- The switch -----------------------------------------------------------------------------------

test('Both opens first on a computer and Eat first on a phone, and the choice is kept on this device', async ({ page }) => {
  await page.goto('/plan');
  await expect(show(page, isPhone(page) ? 'Eat' : 'Both')).toHaveAttribute('aria-pressed', 'true');
  await expect(show(page, isPhone(page) ? 'Both' : 'Eat')).toHaveAttribute('aria-pressed', 'false');
  await expect(switchOf(page).getByRole('button')).toHaveText(['Both', 'Eat', 'Cook']);
  await show(page, 'Cook').click();
  await expect(show(page, 'Cook')).toHaveAttribute('aria-pressed', 'true');
  await page.reload();
  await expect(show(page, 'Cook')).toHaveAttribute('aria-pressed', 'true');
  expect(await page.evaluate(() => localStorage.getItem('mealwright.plan-show'))).toBe('cook');
  // Blocked storage: the layout decides, and nothing is raised.
  await page.addInitScript(() => {
    Object.defineProperty(window, 'localStorage', {
      get() {
        throw new Error('blocked');
      },
    });
  });
  await page.reload();
  await expect(show(page, isPhone(page) ? 'Eat' : 'Both')).toHaveAttribute('aria-pressed', 'true');
});

// --- Eat ------------------------------------------------------------------------------------------

test('Eat says what is eaten at each meal and where it comes from, with a link to the cooking', async ({ page }) => {
  const k = await setup(page);
  const day = far(k.today, 0);
  const w = await seedWeek(page, k, day);
  await openWeekOf(page, k.today, day);
  await show(page, 'Eat').click();

  const cookDay = dayCard(page, day);
  await expect(cookDay.getByRole('heading', { name: dayWords(day) })).toBeVisible();
  await expect(cookDay.getByRole('button', { name: new RegExp(`Breakfast: .*${w.pongal}`) })).toContainText('fresh');
  await expect(cookDay.getByRole('button', { name: new RegExp(`Dinner: .*${w.biryani}`) })).toContainText(`Freshly made · ${k.me.name}`);
  const sunday = dayCard(page, w.sunday);
  await expect(sunday.getByRole('button', { name: new RegExp(`Lunch: .*${w.biryani}`) })).toContainText(`2 tubs from ${dayShort(day)} · ${k.me.name}`);
  // Empty meals can be added to.
  await expect(sunday.getByRole('button', { name: '+ Add dinner' })).toBeVisible();

  // The meal opens the same menu as everywhere on the Plan.
  await cookDay.getByRole('button', { name: new RegExp(`Breakfast: .*${w.pongal}`) }).click();
  await expect(page.getByRole('dialog', { name: w.pongal }).getByRole('button', { name: 'Move to…' })).toBeVisible();
  await page.keyboard.press('Escape');

  // A cook day has "You cook … →", which shows the Cook view at that day.
  await cookDay.getByRole('button', { name: /You cook this day →/ }).click();
  await expect(show(page, 'Cook')).toHaveAttribute('aria-pressed', 'true');
  await expect(dayCard(page, day).getByText(w.biryani)).toBeVisible();
  await expect(sunday).toHaveCount(0); // a day with nothing to cook is not in the Cook view
  await checkPage(page);
});

// --- Cook -----------------------------------------------------------------------------------------

test('Cook shows the cooking by day: fresh meals and batches, how much, where each tub goes, prep and Start cooking', async ({ page }) => {
  const k = await setup(page);
  const day = far(k.today, 1);
  const w = await seedWeek(page, k, day);
  await openWeekOf(page, k.today, day);
  await show(page, 'Cook').click();

  const card = dayCard(page, day);
  await expect(card.getByText(/\d things to cook · /)).toBeVisible();
  const pongal = card.locator('.entry', { hasText: w.pongal });
  await expect(pongal).toContainText('Fresh · Breakfast');
  await expect(pongal).toContainText('Serves 2 · 30 min');
  await expect(pongal.getByRole('button', { name: `Start cooking ${w.pongal}` })).toBeVisible();
  const biryani = card.locator('.entry', { hasText: w.biryani });
  await expect(biryani).toContainText('Cook · Batch · Dinner');
  await expect(biryani).toContainText('Makes 4 · cook × 2 · 1 h 35 min');
  await expect(biryani).toContainText('Eat 1 now');
  await expect(biryani).toContainText(`Tub → ${dayShort(w.sunday)} lunch`);
  await expect(biryani.getByRole('button', { name: '+ 1 spare tub' })).toBeVisible();
  await expect(biryani).toContainText('Prep ahead: Soak the rice');
  // Sunday has nothing to cook.
  await expect(dayCard(page, w.sunday)).toHaveCount(0);
  // The spare tub opens the meal's menu, which has Leftovers on….
  await biryani.getByRole('button', { name: '+ 1 spare tub' }).click();
  await expect(page.getByRole('dialog', { name: w.biryani }).getByRole('button', { name: 'Leftovers on…' })).toBeVisible();
  await page.keyboard.press('Escape');
  await checkPage(page);
});

test('Start cooking opens Cook mode for that plan item, and Cooked it reaches the review', async ({ page }) => {
  const k = await setup(page);
  const day = far(k.today, 2);
  const name = `Upma ${stamp()}`;
  const other = `Idli ${stamp()}`;
  const recipe = await makeRecipe(page, name, { serves: 2 }, [{ text: 'Roast the rava.' }, { text: 'Serve hot.' }]);
  // Two recipes in one meal: Cooked it reviews only the one that was started.
  await planned(page, await makeRecipe(page, other, { serves: 2 }, [{ text: 'Steam.' }]), day, k.slot.Lunch);
  const item = await planned(page, recipe, day, k.slot.Lunch);
  await openWeekOf(page, k.today, day);
  await show(page, 'Cook').click();
  await dayCard(page, day).getByRole('button', { name: `Start cooking ${name}` }).click();
  await expect(page).toHaveURL(new RegExp(`/recipes/${recipe}/cook\\?meal=${item.meal_id}&day=${day}$`));
  await expect(page.getByRole('region', { name: 'Cook mode', exact: true })).toBeVisible();
  // Nothing was planned: no notice about it.
  await expect(page.getByTestId('cook-notice')).toHaveCount(0);
  while ((await page.getByRole('button', { name: 'Next →' }).count()) > 0) await page.getByRole('button', { name: 'Next →' }).click();
  await page.getByRole('button', { name: 'Cooked it' }).click();
  const review = page.getByRole('dialog', { name: new RegExp(`^Cooked ${name}$`) });
  await expect(review).toBeVisible();
  await review.getByRole('button', { name: 'Cancel' }).first().click();
  await expect(review).toHaveCount(0);
  // The plan was not changed by starting.
  const plan = await planRange(page, day, day);
  expect(plan.meals.find((m: any) => m.id === item.meal_id).items).toHaveLength(2);
});

// --- Plan it --------------------------------------------------------------------------------------

test('Plan it on the recipe page picks the day and the meal, plans the recipe there, and Undo takes it out', async ({ page }) => {
  const k = await setup(page);
  const name = `Kootu ${stamp()}`;
  const recipe = await makeRecipe(page, name);
  const day = addDays(k.today, 1); // the Sunday of this week, which the picker shows at once
  const meal = ['Dinner', 'Lunch', 'Breakfast'][projectIndex()]!; // each project its own meal
  await page.goto(`/recipes/${recipe}`);
  await page.getByRole('button', { name: 'Plan it', exact: true }).click();
  const sheet = page.getByRole('dialog', { name });
  await expect(sheet.getByRole('heading', { name: 'Plan it on…' })).toBeVisible();
  await sheet.getByRole('button', { name: dayName(day) }).click();
  await sheet.getByRole('button', { name: meal, exact: true }).click();
  await sheet.getByRole('button', { name: 'Plan it here' }).click();
  await expect(page.getByText(`Planned ${name} for ${meal}`)).toBeVisible();
  const where = async () => {
    const plan = await planRange(page, day, day);
    return plan.meals.filter((m: any) => m.slot_id === k.slot[meal] && m.items.some((i: any) => i.recipe?.id === recipe)).length;
  };
  await expect.poll(where).toBe(1);
  await page.getByRole('button', { name: 'Undo', exact: true }).click();
  await expect.poll(where).toBe(0);
});

test('Plan it offers the next 14 days from today in one view, with no week arrows', async ({ page }) => {
  const k = await setup(page);
  const name = `Thoran ${stamp()}`;
  const recipe = await makeRecipe(page, name);
  await page.goto(`/recipes/${recipe}`);
  await page.getByRole('button', { name: 'Plan it', exact: true }).click();
  const sheet = page.getByRole('dialog', { name });
  await expect(sheet.getByRole('heading', { name: 'Plan it on…' })).toBeVisible();
  const days = sheet.getByRole('group', { name: 'Day' }).getByRole('button');
  await expect(days).toHaveCount(14);
  await expect(sheet.getByRole('button', { name: dayName(k.today), exact: true })).toBeVisible();
  await expect(sheet.getByRole('button', { name: dayName(addDays(k.today, 13)), exact: true })).toBeVisible();
  await expect(sheet.getByRole('button', { name: dayName(addDays(k.today, 14)), exact: true })).toHaveCount(0);
  await expect(sheet.getByRole('button', { name: dayName(addDays(k.today, -1)), exact: true })).toHaveCount(0);
  await expect(sheet.getByRole('button', { name: 'Earlier week' })).toHaveCount(0);
  await expect(sheet.getByRole('button', { name: 'Later week' })).toHaveCount(0);
  // Day 14 can be planned on, in the second week, with no arrow pressed.
  await sheet.getByRole('button', { name: dayName(addDays(k.today, 13)), exact: true }).click();
  await expect(days.nth(13)).toHaveAttribute('aria-pressed', 'true');
});

test('Plan it shows what is already planned at each meal, and marks a day that has something', async ({ page }) => {
  const k = await setup(page);
  const name = `Avial ${stamp()}`;
  const olan = `Olan ${stamp()}`;
  const other = await makeRecipe(page, olan);
  const recipe = await makeRecipe(page, name);
  const day = addDays(k.today, 9 + projectIndex()); // each project its own day: they share one server
  const empty = addDays(k.today, 12); // nothing of this test's is on it
  const meal = ['Dinner', 'Lunch', 'Breakfast'][projectIndex()]!;
  const spare = ['Lunch', 'Dinner', 'Lunch'][projectIndex()]!;
  await planned(page, other, day, k.slot[meal]!);
  await page.goto(`/recipes/${recipe}`);
  await page.getByRole('button', { name: 'Plan it', exact: true }).click();
  const sheet = page.getByRole('dialog', { name });
  const days = sheet.getByRole('group', { name: 'Day' });
  // The day with something is marked, and the marking has a word for a screen reader.
  const marked = days.getByRole('button', { name: dayName(day), exact: true });
  await expect(marked).toHaveAccessibleDescription('Something planned');
  await marked.click();
  await expect(sheet.getByRole('button', { name: meal, exact: true })).toContainText(olan);
  await expect(sheet.getByRole('button', { name: spare, exact: true }).locator('small')).not.toHaveText(olan);
  await days.getByRole('button', { name: dayName(empty), exact: true }).click();
  await expect(sheet.getByRole('button', { name: meal, exact: true })).not.toContainText(olan);
});

test('Plan it at 200% text shows a long meal name whole, wrapped, with nothing cut off', async ({ page }) => {
  const k = await setup(page);
  const s = short();
  const long = `Roasted aubergine and chickpea stew with preserved lemon ${s}`;
  const name = `Pickle ${stamp()}`;
  const day = addDays(k.today, 13); // nothing but this test's own meal is on it
  const meal = ['Dinner', 'Lunch', 'Breakfast'][projectIndex()]!;
  await planned(page, await makeRecipe(page, long), day, k.slot[meal]!);
  const recipe = await makeRecipe(page, name);
  await page.goto(`/recipes/${recipe}`);
  await page.evaluate(() => (document.documentElement.style.fontSize = '200%'));
  await page.getByRole('button', { name: 'Plan it', exact: true }).click();
  const sheet = page.getByRole('dialog', { name });
  await sheet.getByRole('button', { name: dayName(day), exact: true }).click();
  const small = sheet.getByRole('button', { name: meal, exact: true }).locator('small');
  await expect(small).toContainText(long);
  // Whole: every line of it is shown (nothing hidden past the edge), inside the button and the screen.
  const cut = await small.evaluate((el) => {
    const box = el.getBoundingClientRect();
    const button = el.closest('button')!.getBoundingClientRect();
    return {
      clipped: el.scrollWidth > el.clientWidth || el.scrollHeight > el.clientHeight,
      wraps: parseFloat(getComputedStyle(el).fontSize) * 2 < box.height,
      outside: box.left < button.left - 1 || box.right > button.right + 1 || box.right > window.innerWidth
    };
  });
  expect(cut).toEqual({ clipped: false, wraps: true, outside: false });
  await expectNoSidewaysScroll(page);
});

// --- The phone Plan opens on today -----------------------------------------------------------------

test('the phone Plan opens on today, with earlier days folded away and the date said once', async ({ page }) => {
  test.skip(!isPhone(page), 'the phone');
  const k = await setup(page);
  await page.goto('/plan');
  await expect(show(page, 'Eat')).toHaveAttribute('aria-pressed', 'true');
  await expect(dayCard(page, k.today)).toBeVisible();
  const monday = addDays(k.today, -5); // the tests' day is a Saturday
  await expect(dayCard(page, monday)).toHaveCount(0);
  // Today is the first card, right under the switch.
  const top = await dayCard(page, k.today).boundingBox();
  const switchBox = await switchOf(page).boundingBox();
  expect(top!.y).toBeGreaterThan(switchBox!.y + switchBox!.height);
  expect(top!.y + 100).toBeLessThan(page.viewportSize()!.height); // in view without scrolling
  // The week's dates are said once: not in the header and again in the arrows.
  await expect(page.getByText(/^\d+ – \d+ October$/)).toHaveCount(1);
  // Saturday: Monday to Friday are folded, and the button says how many.
  const earlier = page.getByRole('button', { name: 'Earlier this week (5 days)' });
  await expect(earlier).toHaveAttribute('aria-expanded', 'false');
  await earlier.click();
  await expect(dayCard(page, monday)).toBeVisible();
  await expect(page.getByRole('button', { name: 'Hide earlier days' })).toHaveAttribute('aria-expanded', 'true');
  // Both is the cards, folded the same way.
  await page.getByRole('button', { name: 'Hide earlier days' }).click();
  await show(page, 'Both').click();
  await expect(dayCard(page, k.today)).toBeVisible();
  await expect(dayCard(page, monday)).toHaveCount(0);
  // Another week has no fold.
  await page.getByRole('button', { name: 'Next week' }).click();
  await expect(page.getByRole('button', { name: /^Earlier this week/ })).toHaveCount(0);
});

// --- 768–1100 px wide ------------------------------------------------------------------------------

/** Words that are cut across two lines (a word is one run of letters; a hyphen may wrap). */
async function brokenWords(page: Page): Promise<string[]> {
  return page.evaluate(() => {
    const broken: string[] = [];
    const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
    for (let node = walker.nextNode(); node; node = walker.nextNode()) {
      const el = node.parentElement;
      if (!el || !el.checkVisibility() || el.closest('script,style,[hidden]')) continue;
      const text = node.textContent ?? '';
      for (const m of text.matchAll(/[^\s\-–—/·→]+/g)) {
        const range = document.createRange();
        range.setStart(node, m.index!);
        range.setEnd(node, m.index! + m[0].length);
        const lines = new Set([...range.getClientRects()].filter((r) => r.width > 0).map((r) => Math.round(r.top / 4)));
        if (lines.size > 1) broken.push(`${m[0]} (in <${el.tagName.toLowerCase()} class="${el.className}">)`);
      }
    }
    return broken;
  });
}

async function expectWhole(page: Page, where: string) {
  await expect.poll(() => brokenWords(page), { message: `words broken in the middle: ${where}` }).toEqual([]);
  await expectNoSidewaysScroll(page);
}

for (const width of [800, 1024]) {
  test(`every Plan screen at ${width} px wide, in both themes and at 200% text: no word is broken in the middle`, async ({ page }) => {
    test.skip(isPhone(page), 'the computer layout');
    test.setTimeout(240_000);
    const k = await setup(page);
    // Weeks no other test plans in (one per project, since they share a server, and nothing but this test's own meals in them), so every word on
    // screen is one this test made.
    const day = addDays(k.today, 7 * (65 + 5 * projectIndex() + (width === 800 ? 3 : 4)));
    const w = await seedWeek(page, k, day);
    await page.setViewportSize({ width, height: 900 });
    await openWeekOf(page, k.today, day);

    for (const theme of THEMES) {
      await inTheme(page, theme);
      for (const text of ['100%', '200%']) {
        await page.evaluate((size) => (document.documentElement.style.fontSize = size), text);
        const at = `${width} px, ${theme}, ${text}`;
        for (const which of ['Both', 'Eat', 'Cook'] as const) {
          await show(page, which).click();
          await expect(show(page, which)).toHaveAttribute('aria-pressed', 'true');
          await expect(page.getByText(w.biryani).first()).toBeVisible();
          await expectWhole(page, `${which}, ${at}`);
        }
        // The meal's menu and what it leads to.
        await show(page, 'Eat').click();
        await dayCard(page, day).getByRole('button', { name: new RegExp(`Breakfast: .*${w.pongal}`) }).click();
        const menu = page.getByRole('dialog', { name: w.pongal });
        await expect(menu).toBeVisible();
        await expectWhole(page, `the meal's menu, ${at}`);
        await menu.getByRole('button', { name: 'Cook once, eat for…' }).click();
        // The sheet's code is fetched when first asked for: wait for it before measuring.
        await expect(page.getByRole('dialog', { name: 'Cook once, eat for…' })).toBeVisible();
        await expectWhole(page, `Cook once, ${at}`);
        await page.keyboard.press('Escape');
        await dayCard(page, day).getByRole('button', { name: new RegExp(`Breakfast: .*${w.pongal}`) }).click();
        await menu.getByRole('button', { name: 'Leftovers on…' }).click();
        await expectWhole(page, `Leftovers on…, ${at}`);
        await page.keyboard.press('Escape');
        await dayCard(page, w.sunday).getByRole('button', { name: '+ Add dinner' }).click();
        await expect(page.getByRole('dialog', { name: 'Add to the plan' })).toBeVisible();
        await expectWhole(page, `Add to the plan, ${at}`);
        await page.keyboard.press('Escape');
        await expect(page.getByRole('dialog', { name: 'Add to the plan' })).toHaveCount(0);
        // The month, with its day.
        await page.getByRole('button', { name: 'Month', exact: true }).click();
        await expectWhole(page, `Month, ${at}`);
        await page.getByRole('button', { name: 'Week', exact: true }).click();
        await expect(show(page, 'Eat')).toBeVisible();
      }
    }
    await page.evaluate(() => (document.documentElement.style.fontSize = ''));
  });
}
