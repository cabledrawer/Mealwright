import { test, expect, type Page } from './clock.ts';
import { checkPage, expectNoSidewaysScroll, inTheme, isPhone, setAccountTheme } from './a11y.ts';

// Cook mode (0.7, K4), against the real server: Cook now from the recipe page, big text one step
// at a time with Back and Next (buttons, keys, swipe), headings as section titles, a recipe with
// two method sections, "Show ingredients", timers found in the step's words that count down and
// end with the chime, "Stop the timer and leave?", Keep screen awake, the Experimental per-step
// ingredients, and the screen at 200% text in both themes. Runs on Chromium (phone and computer)
// and WebKit (computer), see playwright.config.ts. Time is the test clock's (no real waiting).

const key = () => ({ 'idempotency-key': crypto.randomUUID() });

async function call(page: Page, path: string, data: object) {
  const response = await page.request.fetch(`/api/v1${path}`, { method: 'POST', data, headers: key() });
  expect(response.ok(), `POST ${path}: ${await response.text()}`).toBe(true);
  return (await response.json()) as Record<string, any>;
}

const stamp = () => `${test.info().project.name.replace(/\W/g, '')}${Date.now().toString(36)}${Math.floor(Math.random() * 1296).toString(36)}`;

async function food(page: Page, name: string) {
  return (await call(page, '/foods', { name, counted_as: 'weight' })).food.id as number;
}

type Step = { kind?: 'heading'; text: string };
/** The names of the two ingredients every test recipe has (each test's own, the server is shared). */
type Names = { tamarind: string; onion: string };

/** A recipe with steps, and a tamarind and an onion line the steps mention. */
async function makeRecipe(page: Page, steps: Step[] | ((names: Names) => Step[]), name = `Sambar ${stamp()}`) {
  const tamarindName = `Tamarind ${stamp()}`;
  const onionName = `Onion ${stamp()}`;
  const tamarind = await food(page, tamarindName);
  const onion = await food(page, onionName);
  const recipe = await call(page, '/recipes', {
    name,
    serves: 4,
    lines: [
      { kind: 'heading', words: 'For the base' },
      { words: 'tamarind', food_id: tamarind, amount: 30, unit: 'g' },
      { words: 'onion', food_id: onion, amount: 3 },
    ],
    steps: typeof steps === 'function' ? steps({ tamarind: tamarindName, onion: onionName }) : steps,
  });
  return { id: recipe.id as number, name, tamarind, onion };
}

/** Four steps; the second uses both ingredients and asks for 10 minutes. */
const FOUR = (n: Names): Step[] => [
  { text: 'Boil the dal.' },
  { text: `Soak the ${n.tamarind} for 10 minutes, then chop the ${n.onion}.` },
  { text: 'Fry the mustard seeds.' },
  { text: 'Serve hot.' },
];

const cook = (page: Page) => page.getByRole('region', { name: 'Cook mode', exact: true });
const count = (page: Page) => page.getByTestId('step-count');
const text = (page: Page) => page.getByTestId('step-text');
const next = (page: Page) => page.getByRole('button', { name: 'Next →' });

/** Counts the oscillators the chime makes, and fakes the Wake Lock; no sound is made. */
async function fakeBrowserThings(page: Page, options: { wakeLock?: boolean; refuse?: boolean } = {}) {
  await page.addInitScript(({ wakeLock, refuse }) => {
    const w = window as any;
    w.__chime = { oscillators: 0, starts: [] as number[] };
    class FakeAudio {
      currentTime = 0;
      state = 'running';
      destination = {};
      resume = async () => {};
      createOscillator() {
        w.__chime.oscillators++;
        return {
          type: '',
          frequency: { value: 0 },
          connect() {},
          start: (at: number) => w.__chime.starts.push(at),
          stop() {},
        };
      }
      createGain() {
        return {
          gain: { value: 0, setValueAtTime() {}, linearRampToValueAtTime() {}, exponentialRampToValueAtTime() {} },
          connect() {},
        };
      }
    }
    w.AudioContext = FakeAudio;
    w.__wake = {
      asked: 0,
      released: 0,
      listeners: [] as (() => void)[],
      /** What a browser does when the page is hidden: it lets go of the lock by itself. */
      drop() {
        this.listeners.splice(0).forEach((f: () => void) => f());
      },
    };
    Object.defineProperty(navigator, 'wakeLock', {
      configurable: true,
      value: wakeLock
        ? {
            request: async () => {
              w.__wake.asked++;
              if (refuse) throw new Error('Low power');
              return {
                release: async () => void w.__wake.released++,
                addEventListener: (_t: string, f: () => void) => void w.__wake.listeners.push(f),
              };
            },
          }
        : undefined,
    });
  }, { wakeLock: options.wakeLock ?? true, refuse: options.refuse ?? false });
}

/** The plan can't be written, so Cook now plans nothing (and leaves the shared plan alone). */
async function refusePlanning(page: Page) {
  await page.route('**/api/v1/plan/items', (route) =>
    route.request().method() === 'POST' ? route.fulfill({ status: 500, json: { detail: 'Something broke.' } }) : route.fallback(),
  );
}

async function perStepSetting(page: Page, on: boolean) {
  const response = await page.request.fetch('/api/v1/household', { method: 'PATCH', data: { cook_per_step: on } });
  expect(response.ok(), await response.text()).toBe(true);
}

test.beforeEach(async ({ page }) => {
  await setAccountTheme(page, 'auto');
  await perStepSetting(page, false); // the household's switch is shared: every test starts off
});

test.afterEach(async ({ page }) => {
  await perStepSetting(page, false); // leave the shared household as found
});

test('Cook mode shows one big step at a time, with Back, Next, keys and a swipe', async ({ page }) => {
  await fakeBrowserThings(page);
  const { id, name } = await makeRecipe(page, FOUR);
  await page.goto(`/recipes/${id}/cook`);
  await expect(cook(page)).toBeVisible();
  await expect(page.getByRole('heading', { name, level: 1 })).toBeVisible();
  await expect(count(page)).toHaveText('Step 1 of 4');
  await expect(text(page)).toHaveText('Boil the dal.');
  // Big text: far larger than the 16 px body text.
  expect(await text(page).evaluate((el) => parseFloat(getComputedStyle(el).fontSize))).toBeGreaterThanOrEqual(28);
  await expect(page.getByRole('button', { name: '← Back' })).toBeDisabled();
  await next(page).click();
  await expect(count(page)).toHaveText('Step 2 of 4');
  await page.getByRole('button', { name: '← Back' }).click();
  await expect(count(page)).toHaveText('Step 1 of 4');
  await page.keyboard.press('ArrowRight');
  await page.keyboard.press('ArrowRight');
  await expect(count(page)).toHaveText('Step 3 of 4');
  await page.keyboard.press('ArrowLeft');
  await expect(count(page)).toHaveText('Step 2 of 4');
  // A swipe left goes on, a swipe right goes back.
  const box = (await text(page).boundingBox())!;
  const y = box.y + 10;
  await page.mouse.move(box.x + box.width - 20, y);
  await page.mouse.down();
  await page.mouse.move(box.x + 10, y, { steps: 6 });
  await page.mouse.up();
  await expect(count(page)).toHaveText('Step 3 of 4');
  await expect(page.getByTestId('slide')).toHaveAttribute('data-moving', 'false');
  await page.mouse.move(box.x + 10, y);
  await page.mouse.down();
  await page.mouse.move(box.x + box.width - 20, y, { steps: 6 });
  await page.mouse.up();
  await expect(count(page)).toHaveText('Step 2 of 4');
});

test('the Ingredients for each step box is laid out as the 0.8 mockup, in both themes at 390 px (F148)', async ({ page }) => {
  test.skip(!isPhone(page), 'the phone’s layout');
  await fakeBrowserThings(page);
  const { id } = await makeRecipe(page, FOUR);
  await page.goto(`/recipes/${id}/cook`);
  await page.getByRole('switch', { name: /Ingredients for each step/ }).click();
  const box = page.getByRole('region', { name: 'Ingredients for each step' });
  await expect(box.getByTestId('per-step')).toBeVisible();
  for (const theme of ['light', 'dark'] as const) {
    await inTheme(page, theme);
    const m = await box.evaluate((el) => {
      const r = (q: string) => el.querySelector(q)!.getBoundingClientRect();
      const style = getComputedStyle(el);
      const label = r('.label');
      const badge = r('.badge');
      const sw = r('[role="switch"]');
      const note = getComputedStyle(el.querySelector('.guess .note:last-child')!);
      return {
        padding: [style.paddingTop, style.paddingRight, style.paddingBottom, style.paddingLeft],
        border: style.borderTopWidth,
        gap: badge.top - label.bottom,
        sameLeft: badge.left === label.left,
        switchSize: [sw.width, sw.height],
        centred: Math.abs(sw.top + sw.height / 2 - (label.top + badge.bottom) / 2),
        labelFromTop: label.top - el.getBoundingClientRect().top,
        divider: getComputedStyle(el.querySelector('.guess')!).borderTopWidth,
        line: parseFloat(note.lineHeight) / parseFloat(note.fontSize),
        inside: sw.right <= el.getBoundingClientRect().right,
      };
    });
    expect(m.padding).toEqual(['16px', '16px', '16px', '16px']);
    expect(m.border).toBe('1px');
    expect(m.gap).toBe(8);
    expect(m.sameLeft).toBe(true);
    expect(m.switchSize).toEqual([52, 32]);
    expect(m.centred).toBeLessThanOrEqual(1);
    expect(m.labelFromTop).toBeGreaterThanOrEqual(16);
    expect(m.divider).toBe('1px');
    expect(m.line).toBeCloseTo(1.45, 2);
    expect(m.inside).toBe(true);
    await expectNoSidewaysScroll(page);
  }
  await inTheme(page, 'light');
});

test('"Couldn’t keep the screen awake." has its own amber line under the progress bar, not in the box (F148)', async ({ page }) => {
  test.skip(!isPhone(page), 'the phone’s layout');
  await fakeBrowserThings(page, { refuse: true });
  const { id } = await makeRecipe(page, FOUR);
  await page.goto(`/recipes/${id}/cook`);
  await page.getByRole('switch', { name: /Ingredients for each step/ }).click();
  const line = page.getByTestId('cook-asleep');
  await expect(line).toHaveText('Couldn’t keep the screen awake.');
  await expect(page.getByRole('region', { name: 'Ingredients for each step' }).getByText('Couldn’t keep')).toHaveCount(0);
  const progress = (await page.locator('.progress').boundingBox())!;
  const amber = (await line.boundingBox())!;
  expect(amber.y).toBeGreaterThanOrEqual(progress.y + progress.height);
  expect(await line.evaluate((el) => [getComputedStyle(el).paddingTop, getComputedStyle(el).paddingLeft])).toEqual(['10px', '12px']);
  await expect(page.getByText('Awake', { exact: true })).toHaveCount(0);
  await expectNoSidewaysScroll(page);
});

test('the step follows the finger, springs back when the swipe is short, and slides to the next when it is long (F145)', async ({ page }) => {
  await fakeBrowserThings(page);
  const { id } = await makeRecipe(page, FOUR);
  await page.goto(`/recipes/${id}/cook`);
  const slide = page.getByTestId('slide');
  const shift = () => slide.evaluate((el) => new DOMMatrix(getComputedStyle(el).transform).m41);
  const box = (await text(page).boundingBox())!;
  const x = box.x + box.width / 2;
  const y = box.y + 10;
  await page.mouse.move(x, y);
  await page.mouse.down();
  await page.mouse.move(x - 30, y, { steps: 3 });
  expect(await shift()).toBeLessThan(-20); // the step is with the finger
  await expect(count(page)).toHaveText('Step 1 of 4');
  await page.mouse.up(); // 30 px is not far enough
  await expect(slide).toHaveAttribute('data-moving', 'false');
  expect(await shift()).toBe(0);
  await expect(count(page)).toHaveText('Step 1 of 4');
  // Far enough: on to step 2, whose text slides in.
  await page.mouse.move(x, y);
  await page.mouse.down();
  await page.mouse.move(x - 150, y, { steps: 5 });
  expect(await shift()).toBeLessThan(-100);
  await page.mouse.up();
  await expect(count(page)).toHaveText('Step 2 of 4');
  await expect(slide).toHaveAttribute('data-moving', 'false');
  expect(await shift()).toBe(0);
  // At the first step a swipe to the right goes nowhere: it gives a little and comes back.
  await next(page).click();
  await page.getByRole('button', { name: '← Back' }).click();
  await page.getByRole('button', { name: '← Back' }).click();
  await expect(count(page)).toHaveText('Step 1 of 4');
  await page.mouse.move(x, y);
  await page.mouse.down();
  await page.mouse.move(x + 120, y, { steps: 4 });
  const given = await shift();
  expect(given).toBeGreaterThan(0);
  expect(given).toBeLessThan(60);
  await page.mouse.up();
  await expect(slide).toHaveAttribute('data-moving', 'false');
  expect(await shift()).toBe(0);
  await expect(count(page)).toHaveText('Step 1 of 4');
});

test('with “reduce motion” the step just changes: nothing slides (F145)', async ({ page }) => {
  await page.emulateMedia({ reducedMotion: 'reduce' });
  await fakeBrowserThings(page);
  const { id } = await makeRecipe(page, FOUR);
  await page.goto(`/recipes/${id}/cook`);
  const box = (await text(page).boundingBox())!;
  const y = box.y + 10;
  await page.mouse.move(box.x + box.width - 20, y);
  await page.mouse.down();
  await page.mouse.move(box.x + 10, y, { steps: 6 });
  await page.mouse.up();
  await expect(count(page)).toHaveText('Step 2 of 4');
  const slide = page.getByTestId('slide');
  await expect(slide).toHaveAttribute('data-moving', 'false');
  expect(await slide.evaluate((el) => getComputedStyle(el).transform)).toBe('none');
  // The app's own reduce-motion rule makes every transition (almost) instant.
  expect(await slide.evaluate((el) => parseFloat(getComputedStyle(el).transitionDuration))).toBeLessThan(0.001);
});

test('headings are section titles and a recipe with two method sections shows every step', async ({ page }) => {
  await fakeBrowserThings(page);
  const { id } = await makeRecipe(page, [
    { kind: 'heading', text: 'Method 1: stove' },
    { text: 'Simmer gently.' },
    { text: 'Serve hot.' },
    { kind: 'heading', text: 'Method 2: pressure cooker' },
    { text: 'Cook for 3 whistles.' },
    { text: 'Serve warm.' },
  ]);
  await page.goto(`/recipes/${id}/cook`);
  const seen: string[] = [];
  for (let i = 0; i < 4; i++) {
    await expect(count(page)).toHaveText(`Step ${i + 1} of 4`);
    seen.push(`${await page.locator('h2.section').textContent()} | ${await text(page).textContent()}`);
    if (i < 3) await next(page).click();
  }
  expect(seen).toEqual([
    'Method 1: stove | Simmer gently.',
    'Method 1: stove | Serve hot.',
    'Method 2: pressure cooker | Cook for 3 whistles.',
    'Method 2: pressure cooker | Serve warm.',
  ]);
  await expectNoLeaveButtons(page);
  await expect(page.getByRole('button', { name: '← Back' })).toBeVisible();
});

test('a recipe with no steps, and one with only a heading, do not break', async ({ page }) => {
  await fakeBrowserThings(page);
  const none = await makeRecipe(page, []);
  await page.goto(`/recipes/${none.id}/cook`);
  await expect(text(page)).toHaveText('This recipe has no steps yet.');
  await expect(page.getByRole('button', { name: 'Show ingredients' })).toBeVisible();
  const heading = await makeRecipe(page, [{ kind: 'heading', text: 'Only a heading' }]);
  await page.goto(`/recipes/${heading.id}/cook`);
  await expect(count(page)).toHaveText('No steps');
  await page.getByRole('button', { name: 'Leave Cook mode' }).click();
  await expect(page).toHaveURL(`/recipes/${heading.id}`);
});

test('Show ingredients opens the whole list on any step', async ({ page }) => {
  await fakeBrowserThings(page);
  const { id } = await makeRecipe(page, FOUR);
  await page.goto(`/recipes/${id}/cook`);
  await next(page).click();
  await page.getByRole('button', { name: 'Show ingredients' }).click();
  const sheet = page.getByRole('dialog', { name: 'All ingredients' });
  await expect(sheet).toContainText('For the base');
  await expect(sheet).toContainText(/30\sg\sTamarind/);
  await expect(sheet).toContainText(/3\sOnion/);
  await sheet.getByRole('button', { name: 'Done' }).click();
  await expect(sheet).toBeHidden();
  await expect(count(page)).toHaveText('Step 2 of 4');
});

test('a timer found in the step starts on a tap, counts down, and ends with the chime three times', async ({ page }) => {
  await fakeBrowserThings(page);
  const { id } = await makeRecipe(page, FOUR);
  await page.goto(`/recipes/${id}/cook`);
  await next(page).click();
  const card = page.getByTestId('timer');
  await expect(card).toContainText('10 minutes');
  await expect(card).toContainText('10:00');
  await expect(page.getByText('No alarm if the phone is locked or Mealwright is in the background.')).toBeVisible();
  await page.getByRole('button', { name: 'Start timer for 10 minutes' }).click();
  await page.clock.runFor(65_000);
  await expect(card).toContainText('08:5');
  expect((await page.evaluate(() => (window as any).__chime)).oscillators).toBe(0);
  // The timer counts to a deadline it looks at every 250 ms, so the rest of the ten minutes is
  // jumped in one go (fastForward fires the page's timers once): the countdown was shown ticking
  // above, and the end, the chime and its three plays are checked below as before.
  await page.clock.fastForward(540_000);
  await expect(card).toContainText('Time’s up');
  // Three chimes of two notes each, a clear gap apart.
  const chime = await page.evaluate(() => (window as any).__chime);
  expect(chime.oscillators).toBe(6);
  expect(chime.starts[2] - chime.starts[0]).toBeGreaterThan(0.5);
  await expect(page.getByRole('status').filter({ hasText: 'Timer finished' })).toContainText('10 minutes');
  await page.getByRole('button', { name: /^Done/ }).click();
  await expect(card).toContainText('10:00');
});

test('leaving with a timer running asks "Stop the timer and leave?"', async ({ page }) => {
  await fakeBrowserThings(page);
  const { id } = await makeRecipe(page, FOUR);
  await refusePlanning(page); // the way in is the recipe page (so Back has somewhere to go), planning nothing
  await page.goto(`/recipes/${id}`);
  await page.getByRole('link', { name: 'Cook now' }).click();
  await expect(page).toHaveURL(`/recipes/${id}/cook`);
  await next(page).click();
  await page.getByRole('button', { name: 'Start timer for 10 minutes' }).click();
  await page.getByRole('button', { name: 'Leave Cook mode' }).click();
  const ask = page.getByRole('dialog', { name: 'Stop the timer and leave?' });
  await expect(ask).toBeVisible();
  await ask.getByRole('button', { name: 'Stay' }).click();
  await expect(cook(page)).toBeVisible();
  await expect(page.getByTestId('timer')).toContainText('09:');
  // The browser's Back asks the same.
  await page.goBack();
  await expect(ask).toBeVisible();
  await ask.getByRole('button', { name: 'Stay' }).click();
  await expect(page).toHaveURL(`/recipes/${id}/cook`);
  await page.getByRole('button', { name: 'Leave Cook mode' }).click();
  await ask.getByRole('button', { name: 'Leave', exact: true }).click();
  await expect(page).toHaveURL(`/recipes/${id}`);
  await expect(page.getByRole('link', { name: 'Cook now' })).toBeVisible();
});

test('leaving without a timer needs no question', async ({ page }) => {
  await fakeBrowserThings(page);
  const { id } = await makeRecipe(page, FOUR);
  await page.goto(`/recipes/${id}/cook`);
  await page.getByRole('button', { name: 'Leave Cook mode' }).click();
  await expect(page).toHaveURL(`/recipes/${id}`);
});

test('Keep screen awake turns on with Cook mode and lets go on leaving; greyed where the browser cannot', async ({ page }) => {
  await fakeBrowserThings(page);
  const { id } = await makeRecipe(page, FOUR);
  await page.goto(`/recipes/${id}/cook`);
  const sw = page.getByRole('switch', { name: 'Keep screen awake' });
  await expect(sw).toHaveAttribute('aria-checked', 'true');
  expect(await page.evaluate(() => { const { asked, released } = (window as any).__wake; return { asked, released }; })).toEqual({ asked: 1, released: 0 });
  await page.getByRole('button', { name: 'Leave Cook mode' }).click();
  await expect.poll(() => page.evaluate(() => { const { asked, released } = (window as any).__wake; return { asked, released }; })).toEqual({ asked: 1, released: 1 });
});

test('Keep screen awake is greyed with the words where the browser cannot keep the screen on', async ({ page }) => {
  await fakeBrowserThings(page, { wakeLock: false });
  const { id } = await makeRecipe(page, FOUR);
  await page.goto(`/recipes/${id}/cook`);
  const sw = page.getByRole('switch', { name: 'Keep screen awake' });
  await expect(sw).toBeDisabled();
  await expect(page.getByText('This browser can’t keep the screen on')).toBeVisible();
});

test('per-step ingredients are off, then guessed from the step once switched on (Experimental)', async ({ page }) => {
  await fakeBrowserThings(page);
  const { id } = await makeRecipe(page, FOUR);
  await page.goto(`/recipes/${id}/cook`);
  await next(page).click();
  await expect(page.getByTestId('per-step')).toHaveCount(0);
  const sw = page.getByRole('switch', { name: /Ingredients for each step/ });
  await expect(sw).toHaveAttribute('aria-checked', 'false');
  await sw.click();
  const box = page.getByTestId('per-step');
  await expect(box).toContainText(/Tamarind/);
  await expect(box).toContainText(/Onion/);
  await expect(box).toContainText('Guessed from the step, so it may be wrong. Fix it when you edit the recipe.');
  await next(page).click();
  await expect(box).toContainText('No ingredient guessed for this step.');
});

test('per-step ingredients stay on for the household: on, reload, still on; another phone sees it', async ({ page }) => {
  await fakeBrowserThings(page);
  const { id } = await makeRecipe(page, FOUR);
  await page.goto(`/recipes/${id}/cook`);
  const sw = page.getByRole('switch', { name: /Ingredients for each step/ });
  await expect(sw).toHaveAttribute('aria-checked', 'false');
  await sw.click();
  await expect(sw).toHaveAttribute('aria-checked', 'true');
  await expect(page.getByTestId('per-step')).toBeVisible();
  await page.reload();
  await expect(sw).toHaveAttribute('aria-checked', 'true');
  await expect(page.getByTestId('per-step')).toBeVisible();
  // It is the household's, not this device's: nothing about it is kept in this browser.
  expect(await page.evaluate(() => localStorage.getItem('mealwright.cook.perStep'))).toBeNull();
  // Switched off from somewhere else (another phone), it is off the next time Cook mode opens.
  await perStepSetting(page, false);
  await page.reload();
  await expect(sw).toHaveAttribute('aria-checked', 'false');
  await expect(page.getByTestId('per-step')).toHaveCount(0);
});

test('a device that had the old switch on does not switch the household on', async ({ page }) => {
  await fakeBrowserThings(page);
  const { id } = await makeRecipe(page, FOUR);
  await page.goto('/');
  await page.evaluate(() => localStorage.setItem('mealwright.cook.perStep', '1'));
  await page.goto(`/recipes/${id}/cook`);
  await expect(page.getByRole('switch', { name: /Ingredients for each step/ })).toHaveAttribute('aria-checked', 'false');
  await expect(page.getByTestId('per-step')).toHaveCount(0);
});

test('when the server cannot take the per-step switch it goes back and says so', async ({ page }) => {
  await fakeBrowserThings(page);
  const { id } = await makeRecipe(page, FOUR);
  await page.goto(`/recipes/${id}/cook`);
  const sw = page.getByRole('switch', { name: /Ingredients for each step/ });
  await expect(sw).toHaveAttribute('aria-checked', 'false');
  await page.route('**/api/v1/household', (route) =>
    route.request().method() === 'PATCH' ? route.fulfill({ status: 500, json: { detail: 'Something broke.' } }) : route.fallback(),
  );
  await sw.click();
  await expect(page.getByText('Couldn’t save. Try again.')).toBeVisible();
  await expect(sw).toHaveAttribute('aria-checked', 'false');
  await expect(page.getByTestId('per-step')).toHaveCount(0);
});

/** Today's meals, and every plan item of this recipe today. */
async function plannedToday(page: Page, recipeId: number) {
  const today = ((await (await page.request.get('/api/v1/household')).json()) as { today: string }).today;
  const plan = (await (await page.request.get(`/api/v1/plan?from=${today}&to=${today}`)).json()) as {
    meals: { id: number; slot_id: number; items: { id: number; kind: string; recipe: { id: number } | null }[] }[];
  };
  return plan.meals.flatMap((m) => m.items.filter((i) => i.kind === 'recipe' && i.recipe?.id === recipeId).map((i) => ({ mealId: m.id, itemId: i.id })));
}

async function expectNoLeaveButtons(page: Page) {
  for (const name of ['Close', 'Not cooked yet', 'Not now']) {
    await expect(page.getByRole('button', { name, exact: true })).toHaveCount(0);
  }
}

function footerButtons(page: Page) {
  return page.locator('footer button');
}

async function lastStep(page: Page) {
  while ((await next(page).count()) > 0) await next(page).click();
}

test('Cook now plans the recipe into today\'s next meal first, then Cooked it is there; Undo takes it out and leaves only Back', async ({ page }) => {
  await fakeBrowserThings(page);
  const { id } = await makeRecipe(page, FOUR);
  await page.goto(`/recipes/${id}`);
  await page.getByRole('link', { name: 'Cook now' }).click();
  await expect(page).toHaveURL(new RegExp(`/recipes/${id}/cook\\?meal=\\d+$`));
  await expect(cook(page)).toBeVisible();
  const notice = page.getByTestId('cook-notice');
  await expect(notice).toContainText(/^Planned for today’s \w+/);
  expect(await plannedToday(page, id)).toHaveLength(1);
  await lastStep(page);
  await expect(page.getByRole('button', { name: 'Cooked it' })).toBeVisible();
  await expect(page.getByRole('button', { name: '← Back' })).toBeVisible();
  await expectNoLeaveButtons(page);
  await notice.getByRole('button', { name: 'Undo' }).click();
  await expect(notice).toHaveText('Taken out of today’s plan.');
  await expect(page.getByRole('button', { name: 'Cooked it' })).toHaveCount(0);
  await expectNoLeaveButtons(page);
  await expect(footerButtons(page)).toHaveText(['← Back']);
  expect(await plannedToday(page, id)).toHaveLength(0);
});

test('Cooked it from Cook now opens the review for the planned meal', async ({ page }) => {
  await fakeBrowserThings(page);
  const { id, name } = await makeRecipe(page, FOUR);
  await page.goto(`/recipes/${id}`);
  await page.getByRole('link', { name: 'Cook now' }).click();
  await expect(page.getByTestId('cook-notice')).toContainText('Planned for today’s');
  await lastStep(page);
  await page.getByRole('button', { name: 'Cooked it' }).click();
  // The meal may already hold other things planned today: the title then names them all.
  const review = page.getByRole('dialog', { name: new RegExp(`^Cooked .*${name}`) });
  await expect(review).toBeVisible();
  await review.getByRole('button', { name: 'Cancel' }).first().click();
  await expect(review).toHaveCount(0);
  for (const { itemId } of await plannedToday(page, id)) {
    await page.request.fetch(`/api/v1/plan/items/${itemId}`, { method: 'DELETE', headers: key(), maxRetries: 3 });
  }
});

test('after Undo of Cooked it, Cook mode from the same meal ends with Back and Cooked it again (F155, F156)', async ({ page }) => {
  await fakeBrowserThings(page);
  const { id, name } = await makeRecipe(page, FOUR);
  await page.goto(`/recipes/${id}`);
  await page.getByRole('link', { name: 'Cook now' }).click();
  await expect(page).toHaveURL(new RegExp(`/recipes/${id}/cook\\?meal=\\d+$`));
  const cookUrl = new URL(page.url()).pathname + new URL(page.url()).search;
  await expect(page.getByTestId('cook-notice')).toContainText('Planned for today’s');
  await lastStep(page);
  await page.getByRole('button', { name: 'Cooked it' }).click();
  const review = page.getByRole('dialog', { name: new RegExp(`^Cooked .*${name}`) });
  await review.getByRole('button', { name: 'Confirm · update pantry' }).click();
  await expect(review).toHaveCount(0);
  // Undo it from Settings → Recent changes (the toast is gone once Cook mode has left).
  await page.goto('/settings?section=recent-changes');
  const undo = page.getByRole('region', { name: 'Recent changes' }).getByRole('button', { name: new RegExp(`^Undo: Cooked ${name} \\(\\d+ portions?\\)`) });
  await undo.click();
  await expect(page.getByRole('status')).toContainText(`Undone: Cooked ${name}`);
  await page.goto(cookUrl);
  await expect(cook(page)).toBeVisible();
  await expect(next(page)).toBeVisible();
  await lastStep(page);
  await expect(footerButtons(page)).toHaveText(['← Back', 'Cooked it']);
  await expectNoLeaveButtons(page);
  for (const { itemId } of await plannedToday(page, id)) {
    await page.request.fetch(`/api/v1/plan/items/${itemId}`, { method: 'DELETE', headers: key(), maxRetries: 3 });
  }
});

test('Cook now adds nothing to the plan when the recipe is already planned today', async ({ page }) => {
  await fakeBrowserThings(page);
  const { id } = await makeRecipe(page, FOUR);
  const today = ((await (await page.request.get('/api/v1/household')).json()) as { today: string }).today;
  const slots = (await (await page.request.get('/api/v1/meal-slots')).json()) as { id: number; position: number; enabled: boolean }[];
  // Another test may have dealt with a meal today already: plan into the last one still open.
  const open = slots.filter((s) => s.enabled).sort((a, b) => b.position - a.position);
  let placed = false;
  for (const slot of open) {
    const response = await page.request.fetch('/api/v1/plan/items', { method: 'POST', data: { date: today, slot_id: slot.id, recipe_id: id }, headers: key() });
    if (response.ok()) {
      placed = true;
      break;
    }
    expect(((await response.json()) as { code: string }).code).toBe('meal_done');
  }
  expect(placed, 'every meal today has been dealt with').toBe(true);
  expect(await plannedToday(page, id)).toHaveLength(1);
  await page.goto(`/recipes/${id}`);
  await page.getByRole('link', { name: 'Cook now' }).click();
  await expect(page).toHaveURL(new RegExp(`/recipes/${id}/cook\\?meal=\\d+$`));
  await expect(cook(page)).toBeVisible();
  await expect(page.getByTestId('cook-notice')).toHaveCount(0);
  await lastStep(page);
  await expect(page.getByRole('button', { name: 'Cooked it' })).toBeVisible();
  const planned = await plannedToday(page, id);
  expect(planned).toHaveLength(1);
  await page.request.fetch(`/api/v1/plan/items/${planned[0]!.itemId}`, { method: 'DELETE', headers: key(), maxRetries: 3 });
});

test('when the plan cannot be written Cook mode still opens, without Cooked it, and says so', async ({ page }) => {
  await fakeBrowserThings(page);
  const { id } = await makeRecipe(page, FOUR);
  await refusePlanning(page);
  await page.goto(`/recipes/${id}`);
  await page.getByRole('link', { name: 'Cook now' }).click();
  await expect(page).toHaveURL(`/recipes/${id}/cook`);
  await expect(cook(page)).toBeVisible();
  await expect(page.getByTestId('cook-notice')).toHaveText('This recipe wasn’t planned.');
  await lastStep(page);
  await expect(page.getByRole('button', { name: 'Cooked it' })).toHaveCount(0);
  await expectNoLeaveButtons(page);
  await expect(footerButtons(page)).toHaveText(['← Back']);
  expect(await plannedToday(page, id)).toHaveLength(0);
});

test('the last step ends with Back alone (no meal); the cross goes back to the recipe', async ({ page }) => {
  await fakeBrowserThings(page);
  const { id } = await makeRecipe(page, FOUR);
  await page.goto(`/recipes/${id}/cook`);
  for (let i = 0; i < 3; i++) await next(page).click();
  await expect(count(page)).toHaveText('Step 4 of 4');
  await expect(next(page)).toHaveCount(0);
  await expectNoLeaveButtons(page);
  await expect(footerButtons(page)).toHaveText(['← Back']);
  await page.getByRole('button', { name: 'Leave Cook mode' }).click();
  await expect(page).toHaveURL(`/recipes/${id}`);
});

test('no outside request and no policy violation while cooking', async ({ page, baseURL }) => {
  await fakeBrowserThings(page);
  const violations: string[] = [];
  page.on('console', (m) => {
    if (/Content Security Policy|Refused to/i.test(m.text())) violations.push(m.text());
  });
  const outside: string[] = [];
  const own = new URL(baseURL!).origin;
  page.on('request', (r) => {
    const url = new URL(r.url());
    if (url.protocol.startsWith('http') && url.origin !== own) outside.push(r.url());
  });
  const { id } = await makeRecipe(page, FOUR);
  await page.goto(`/recipes/${id}/cook`);
  await next(page).click();
  await page.getByRole('button', { name: 'Start timer for 10 minutes' }).click();
  await page.clock.runFor(1_000); // a few real ticks, then the rest of the ten minutes in one jump
  await page.clock.fastForward(600_000);
  await expect(page.getByTestId('timer')).toContainText('Time’s up');
  expect(violations).toEqual([]);
  expect(outside).toEqual([]);
});

test('passes the accessibility checks in both themes, and at 200% text nothing scrolls sideways', async ({ page }) => {
  await fakeBrowserThings(page);
  const long = `${'Stir the pot slowly and keep stirring until it thickens. '.repeat(6)}Take about 10 minutes.`;
  const { id } = await makeRecipe(page, [
    { kind: 'heading', text: 'A section with quite a long name that has to wrap on a phone' },
    { text: long },
    { text: 'Serve.' },
  ]);
  await page.goto(`/recipes/${id}/cook`);
  await page.getByRole('switch', { name: /Ingredients for each step/ }).click();
  await page.getByRole('button', { name: 'Start timer for 10 minutes' }).click();
  await checkPage(page);
  await page.evaluate(() => (document.documentElement.style.fontSize = '200%'));
  for (const theme of ['light', 'dark'] as const) {
    await inTheme(page, theme);
    await expectNoSidewaysScroll(page);
    // Next stays inside the window, whatever the text size.
    const box = (await next(page).boundingBox())!;
    expect(box.y + box.height).toBeLessThanOrEqual(page.viewportSize()!.height + 1);
    await expect(page.getByRole('button', { name: 'Leave Cook mode' })).toBeVisible();
  }
  await inTheme(page, 'light');
});

test('coming back to the front asks for the screen lock again and shows the right time; leaving stops every timer', async ({ page }) => {
  await fakeBrowserThings(page);
  const { id } = await makeRecipe(page, FOUR);
  await page.goto(`/recipes/${id}/cook`);
  await next(page).click();
  await expect(page.getByRole('switch', { name: 'Keep screen awake' })).toHaveAttribute('aria-checked', 'true');
  await page.getByRole('button', { name: 'Start timer for 10 minutes' }).click();
  const asked = () => page.evaluate(() => (window as any).__wake.asked);
  expect(await asked()).toBe(1);
  const show = (state: 'hidden' | 'visible') =>
    page.evaluate((st) => {
      Object.defineProperty(document, 'visibilityState', { configurable: true, get: () => st });
      if (st === 'hidden') (window as any).__wake.drop();
      document.dispatchEvent(new Event('visibilitychange'));
    }, state);
  await show('hidden');
  // Two minutes pass while the page is hidden (the test clock jumps; a hidden page's timers
  // hardly run, so the coming back to the front is what shows the right time).
  await page.clock.fastForward(120_000);
  await show('visible');
  await expect.poll(asked).toBe(2);
  await expect(page.getByTestId('timer')).toContainText(/0(7:5\d|8:00)/);
  // Leave (the timer question first), then let the time the timer would have ended pass: nothing sounds.
  await page.getByRole('button', { name: 'Leave Cook mode' }).click();
  await page.getByRole('dialog', { name: 'Stop the timer and leave?' }).getByRole('button', { name: 'Leave', exact: true }).click();
  await expect(page).toHaveURL(`/recipes/${id}`);
  await page.clock.runFor(700_000);
  expect((await page.evaluate(() => (window as any).__chime)).oscillators).toBe(0);
});

for (const width of [320, 390, 428, 430]) {
  test(`at ${width} px the last step from a meal is Back and Cooked it on one row (F155, F156)`, async ({ page }) => {
    await fakeBrowserThings(page);
    const { id } = await makeRecipe(page, FOUR);
    await page.setViewportSize({ width, height: 700 });
    await page.goto(`/recipes/${id}`);
    await page.getByRole('link', { name: 'Cook now' }).click();
    await expect(page).toHaveURL(new RegExp(`/recipes/${id}/cook\\?meal=\\d+$`));
    await expect(cook(page)).toBeVisible();
    await lastStep(page);
    await expect(footerButtons(page)).toHaveText(['← Back', 'Cooked it']);
    await expectNoLeaveButtons(page);
    await expectNoSidewaysScroll(page);
    const [back, cooked] = await footerButtons(page).evaluateAll((buttons) =>
      buttons.map((button) => {
        const range = document.createRange();
        range.selectNodeContents(button);
        const lines = new Set([...range.getClientRects()].map((r) => Math.round(r.top))).size;
        const box = button.getBoundingClientRect();
        const text = range.getBoundingClientRect();
        return { top: Math.round(box.top), width: box.width, lines, inside: text.left >= box.left - 0.5 && text.right <= box.right + 0.5 };
      })
    );
    expect(back!.top).toBe(cooked!.top);
    expect(back!.lines).toBe(1);
    expect(cooked!.lines).toBe(1);
    expect(back!.inside && cooked!.inside).toBe(true);
    expect(cooked!.width).toBeGreaterThan(back!.width);
  });
}

// --- A meal with several recipes is cooked one recipe at a time (F157) -----------------------------

const weekdayLong = new Intl.DateTimeFormat('en-GB', { weekday: 'long', timeZone: 'UTC' });
const monthLong = new Intl.DateTimeFormat('en-GB', { month: 'long', timeZone: 'UTC' });
const planDayName = (iso: string) => {
  const d = new Date(`${iso}T12:00:00Z`);
  return `${weekdayLong.format(d)} ${d.getUTCDate()} ${monthLong.format(d)}`;
};

test('F157: cooking one recipe of a meal cooks only it; the meal is Cooked when the last one is; Undo puts back only what was pressed', async ({ page }) => {
  await fakeBrowserThings(page);
  const index = ['desktop 0.7 cook mode', 'phone 0.7 cook mode', 'webkit 0.7 cook mode'].indexOf(test.info().project.name);
  const household = (await (await page.request.get('/api/v1/household')).json()) as { today: string };
  // A week back, so the meal is empty but for these two and "Cooked it" is there for it.
  const back = new Date(`${household.today}T12:00:00Z`);
  back.setUTCDate(back.getUTCDate() - 7);
  const day = back.toISOString().slice(0, 10);
  const slots = (await (await page.request.get('/api/v1/meal-slots')).json()) as { id: number; name: string }[];
  const slot = slots.find((s) => s.name === ['Breakfast', 'Lunch', 'Dinner'][Math.max(index, 0)])!.id;
  const khichdi = await makeRecipe(page, FOUR, `Khichdi ${stamp()}`);
  const soup = await makeRecipe(page, FOUR, `Lentil soup ${stamp()}`);
  const planned = async (recipe: number) => await call(page, '/plan/items', { date: day, slot_id: slot, recipe_id: recipe, servings: 2 });
  const first = await planned(khichdi.id);
  const second = await planned(soup.id);
  const meal = first.meal_id as number;
  try {
    const flags = async () => {
      const plan = (await (await page.request.get(`/api/v1/plan?from=${day}&to=${day}`)).json()) as {
        meals: { id: number; status: string; items: { id: number; cooked: boolean }[] }[];
      };
      const m = plan.meals.find((x) => x.id === meal)!;
      return { status: m.status, cooked: m.items.map((i) => [i.id, i.cooked]) };
    };
    const cookView = async () => {
      await page.goto('/plan');
      await page.getByRole('button', { name: 'Previous week' }).click();
      await page.getByRole('group', { name: 'Show', exact: true }).getByRole('button', { name: 'Cook', exact: true }).click();
      return page.getByRole('region', { name: planDayName(day) });
    };

    // Start cooking the soup from the Plan, and confirm.
    let card = await cookView();
    await card.getByRole('button', { name: `Start cooking ${soup.name}` }).click();
    await expect(cook(page)).toBeVisible();
    await lastStep(page);
    await page.getByRole('button', { name: 'Cooked it' }).click();
    const review = page.getByRole('dialog', { name: `Cooked ${soup.name}`, exact: true });
    await expect(review).toBeVisible();
    await review.getByRole('button', { name: 'Confirm · update pantry' }).click();
    await expect(review).toHaveCount(0);
    // The toast names only what was cooked.
    const toast = page.getByRole('status').filter({ hasText: `Cooked ${soup.name} (` });
    await expect(toast).toBeVisible();
    await expect(toast).not.toContainText('more');
    expect(await flags()).toEqual({ status: 'planned', cooked: [[first.item_id, false], [second.item_id, true]] });

    // The Plan: Cooked on the soup only; the khichdi keeps Start cooking.
    card = await cookView();
    await expect(card.getByRole('button', { name: `Start cooking ${khichdi.name}` })).toBeVisible();
    await expect(card.getByRole('button', { name: `Start cooking ${soup.name}` })).toHaveCount(0);
    await expect(card.getByText('Cooked', { exact: true })).toHaveCount(1);

    // Reload of the cook address: the review lists only the khichdi, which is not cooked yet.
    await card.getByRole('button', { name: `Start cooking ${khichdi.name}` }).click();
    await expect(cook(page)).toBeVisible();
    const address = new URL(page.url()).pathname + new URL(page.url()).search;
    await page.goto(address);
    await expect(cook(page)).toBeVisible();
    await expect(next(page)).toBeVisible();
    await lastStep(page);
    await page.getByRole('button', { name: 'Cooked it' }).click();
    const second_review = page.getByRole('dialog', { name: `Cooked ${khichdi.name}`, exact: true });
    await expect(second_review).toBeVisible();
    await second_review.getByRole('button', { name: 'Confirm · update pantry' }).click();
    await expect(second_review).toHaveCount(0);
    expect((await flags()).status).toBe('cooked');

    // Recent changes names each press on its own; the Undo of the first puts back only the soup.
    await page.goto('/settings?section=recent-changes');
    const recent = page.getByRole('region', { name: 'Recent changes' });
    // (One Cooked it is one row, the pantry's with the portions; the plan's own line is folded into it.)
    await expect(recent.getByRole('button', { name: new RegExp(`^Undo: Cooked ${khichdi.name} \\(\\d+ portions?\\)`) })).toHaveCount(1);
    await recent.getByRole('button', { name: new RegExp(`^Undo: Cooked ${soup.name} \\(\\d+ portions?\\)`) }).click();
    await expect(page.getByRole('status')).toContainText(`Undone: Cooked ${soup.name}`);
    expect(await flags()).toEqual({ status: 'planned', cooked: [[first.item_id, true], [second.item_id, false]] });
  } finally {
    // Take back what this test cooked (a cooked recipe can't be removed), then clear the plan.
    const pantry = (await (await page.request.get('/api/v1/changes?area=pantry')).json()) as {
      changes: { id: number; kind: string; summary: string; can_undo: boolean }[];
    };
    for (const change of pantry.changes.filter((c) => c.kind === 'cooked' && c.can_undo && (c.summary.includes(khichdi.name) || c.summary.includes(soup.name)))) {
      await page.request.fetch(`/api/v1/changes/${change.id}/undo`, { method: 'POST', headers: key() });
    }
    for (const id of [first.item_id as number, second.item_id as number]) {
      await page.request.fetch(`/api/v1/plan/items/${id}`, { method: 'DELETE', headers: key(), maxRetries: 3 });
    }
  }
});

test('F157: reloading the cook address, Cooked it still reviews only this recipe, not the whole meal', async ({ page }) => {
  await fakeBrowserThings(page);
  const index = ['desktop 0.7 cook mode', 'phone 0.7 cook mode', 'webkit 0.7 cook mode'].indexOf(test.info().project.name);
  const household = (await (await page.request.get('/api/v1/household')).json()) as { today: string };
  const back = new Date(`${household.today}T12:00:00Z`);
  back.setUTCDate(back.getUTCDate() - 7);
  const day = back.toISOString().slice(0, 10);
  const slots = (await (await page.request.get('/api/v1/meal-slots')).json()) as { id: number; name: string }[];
  const slot = slots.find((s) => s.name === ['Breakfast', 'Lunch', 'Dinner'][Math.max(index, 0)])!.id;
  const khichdi = await makeRecipe(page, FOUR, `Khichdi ${stamp()}`);
  const soup = await makeRecipe(page, FOUR, `Lentil soup ${stamp()}`);
  const planned = async (recipe: number) => await call(page, '/plan/items', { date: day, slot_id: slot, recipe_id: recipe, servings: 2 });
  const first = await planned(khichdi.id);
  const second = await planned(soup.id);
  try {
    await page.goto('/plan');
    await page.getByRole('button', { name: 'Previous week' }).click();
    await page.getByRole('group', { name: 'Show', exact: true }).getByRole('button', { name: 'Cook', exact: true }).click();
    await page.getByRole('region', { name: planDayName(day) }).getByRole('button', { name: `Start cooking ${soup.name}` }).click();
    await expect(cook(page)).toBeVisible();
    // Reload: the screen has forgotten what it was started from, but the address names the recipe.
    await page.goto(new URL(page.url()).pathname + new URL(page.url()).search);
    await expect(cook(page)).toBeVisible();
    await expect(next(page)).toBeVisible();
    await lastStep(page);
    await page.getByRole('button', { name: 'Cooked it' }).click();
    const review = page.getByRole('dialog', { name: `Cooked ${soup.name}`, exact: true });
    await expect(review).toBeVisible();
    await expect(review.getByText(khichdi.name)).toHaveCount(0);
    await review.getByRole('button', { name: 'Confirm · update pantry' }).click();
    await expect(review).toHaveCount(0);
  } finally {
    const pantry = (await (await page.request.get('/api/v1/changes?area=pantry')).json()) as {
      changes: { id: number; kind: string; summary: string; can_undo: boolean }[];
    };
    for (const change of pantry.changes.filter((c) => c.kind === 'cooked' && c.can_undo && c.summary.includes(soup.name))) {
      await page.request.fetch(`/api/v1/changes/${change.id}/undo`, { method: 'POST', headers: key() });
    }
    for (const id of [first.item_id as number, second.item_id as number]) {
      await page.request.fetch(`/api/v1/plan/items/${id}`, { method: 'DELETE', headers: key(), maxRetries: 3 });
    }
  }
});

// --- Cooking ahead (F159, cabledrawer 6 Nov) -------------------------------------------------------

test('F159: Plan, Cook, a later day\'s meal, Start cooking, Confirm: it is cooked, no error toast, and the meal stays on its day', async ({ page }) => {
  await fakeBrowserThings(page);
  const index = ['desktop 0.7 cook mode', 'phone 0.7 cook mode', 'webkit 0.7 cook mode'].indexOf(test.info().project.name);
  const household = (await (await page.request.get('/api/v1/household')).json()) as { today: string };
  const ahead = new Date(`${household.today}T12:00:00Z`);
  ahead.setUTCDate(ahead.getUTCDate() + 2); // Monday: next week, whatever the project
  const day = ahead.toISOString().slice(0, 10);
  const slots = (await (await page.request.get('/api/v1/meal-slots')).json()) as { id: number; name: string }[];
  const slot = slots.find((s) => s.name === ['Breakfast', 'Lunch', 'Dinner'][Math.max(index, 0)])!.id;
  const soup = await makeRecipe(page, FOUR, `Lentil soup ${stamp()}`);
  const planned = await call(page, '/plan/items', { date: day, slot_id: slot, recipe_id: soup.id, servings: 2 });
  try {
    await page.goto('/plan');
    await page.getByRole('button', { name: 'Next week' }).click();
    await page.getByRole('group', { name: 'Show', exact: true }).getByRole('button', { name: 'Cook', exact: true }).click();
    await page.getByRole('region', { name: planDayName(day) }).getByRole('button', { name: `Start cooking ${soup.name}` }).click();
    await expect(cook(page)).toBeVisible();
    await lastStep(page);
    await page.getByRole('button', { name: 'Cooked it' }).click();
    const review = page.getByRole('dialog', { name: `Cooked ${soup.name}`, exact: true });
    await expect(review).toBeVisible();
    await review.getByRole('button', { name: 'Confirm · update pantry' }).click();
    await expect(review).toHaveCount(0);
    await expect(page.getByRole('status').filter({ hasText: `Cooked ${soup.name} (` })).toBeVisible();
    await expect(page.getByText(/Couldn.t save/)).toHaveCount(0);
    // F158: Cook mode has closed, and the toast with its Undo is still there a moment later.
    await expect(page).not.toHaveURL(/\/cook/);
    // The page Cook mode returns to has rendered, and the toast came with it.
    await expect(page.getByRole('heading', { level: 1, name: soup.name })).toBeVisible();
    await expect(page.getByRole('status').filter({ hasText: `Cooked ${soup.name} (` })).toBeVisible();
    await expect(page.getByRole('status').getByRole('button', { name: 'Undo' })).toBeVisible();
    const plan = (await (await page.request.get(`/api/v1/plan?from=${day}&to=${day}`)).json()) as {
      meals: { id: number; status: string; items: { id: number; cooked: boolean }[] }[];
    };
    const meal = plan.meals.find((m) => m.id === planned.meal_id)!;
    expect(meal.status).toBe('cooked');
  } finally {
    const pantry = (await (await page.request.get('/api/v1/changes?area=pantry')).json()) as {
      changes: { id: number; kind: string; summary: string; can_undo: boolean }[];
    };
    for (const change of pantry.changes.filter((c) => c.kind === 'cooked' && c.can_undo && c.summary.includes(soup.name))) {
      await page.request.fetch(`/api/v1/changes/${change.id}/undo`, { method: 'POST', headers: key() });
    }
    await page.request.fetch(`/api/v1/plan/items/${planned.item_id}`, { method: 'DELETE', headers: key(), maxRetries: 3 });
  }
});
