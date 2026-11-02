import { test, expect, type Page } from './clock.ts';
import { checkPage, expectNoSidewaysScroll, expectTouchTargets, isPhone, setAccountTheme } from './a11y.ts';

// Restock dates, "How much?" and navigation (0.7: K5, N1, F113), against the real server, signed
// in as the test admin. Runs on a phone, a desktop and WebKit.

type Json = Record<string, any>; // eslint-disable-line @typescript-eslint/no-explicit-any

const unique = (name: string) => `${name} ${test.info().project.name.replace(/\D/g, '')}${Date.now() % 100000}`;
const key = () => ({ 'idempotency-key': crypto.randomUUID() });

async function makeStaple(page: Page, name: string): Promise<number> {
  const made = await page.request.post('/api/v1/foods', { data: { name, staple: true }, headers: key() });
  expect(made.status(), await made.text()).toBe(201);
  return ((await made.json()) as Json).food.id;
}

/** The household's today, and the day `days` earlier ("2026-10-17" and "2026-09-26"). */
async function daysAgo(page: Page, days: number): Promise<{ iso: string; words: string }> {
  const { today } = (await (await page.request.get('/api/v1/household')).json()) as { today: string };
  const day = new Date(`${today}T12:00:00Z`);
  day.setUTCDate(day.getUTCDate() - days);
  return {
    iso: day.toISOString().slice(0, 10),
    words: day.toLocaleDateString('en-GB', { day: 'numeric', month: 'short', timeZone: 'UTC' }),
  };
}

async function restockedOn(page: Page, id: number, iso: string) {
  const sent = await page.request.patch(`/api/v1/foods/${id}`, { data: { restocked_on: iso }, headers: key() });
  expect(sent.status(), await sent.text()).toBe(200);
}

test.beforeEach(async ({ page }) => {
  await setAccountTheme(page, 'auto');
});

test('a restocked staple: the chip says Restocked 26 Sep, and Never restocked says nothing', async ({ page }) => {
  const [fresh, never] = [unique('Cumin'), unique('Mace')];
  const id = await makeStaple(page, fresh);
  await makeStaple(page, never);
  const when = await daysAgo(page, 21);
  await restockedOn(page, id, when.iso);
  await page.goto('/pantry');
  const chip = page.getByRole('button', { name: new RegExp(`^(Add )?${fresh}`) });
  await expect(chip).toContainText(`Restocked ${when.words}`);
  await expect(page.getByRole('button', { name: new RegExp(`${never}`) })).not.toContainText('Restocked');
  await checkPage(page);
});

test('the Ingredients column says Restocked 3 weeks ago, and a tap shows the date', async ({ page }) => {
  const name = unique('Turmeric');
  const id = await makeStaple(page, name);
  const when = await daysAgo(page, 21);
  await restockedOn(page, id, when.iso);
  await page.goto('/recipes/ingredients');
  await page.getByRole('searchbox', { name: 'Search ingredients' }).fill(name);
  const list = page.getByRole('region', { name: 'All ingredients' });
  if (isPhone(page)) {
    // The phone's row says it under the name; the date is in the editor a tap opens.
    await expect(list.getByRole('button', { name: new RegExp(name) })).toContainText('Restocked 3 weeks ago');
    return;
  }
  const row = list.getByRole('listitem').filter({ hasText: name });
  const column = row.getByRole('button', { name: 'Restocked 3 weeks ago' });
  await expect(column).toBeVisible();
  await expect(column).toHaveAttribute('title', new RegExp(when.words));
  await expect(column).toHaveAttribute('aria-expanded', 'false');
  await column.click();
  await expect(row.getByRole('button', { name: new RegExp(`^Restocked .*${when.words}`) })).toHaveAttribute(
    'aria-expanded',
    'true',
  );
  await row.locator('button.when').click();
  await expect(row.locator('button.when')).toHaveAttribute('aria-expanded', 'false');
  await expect(column).toBeVisible();
});

test('the editor changes the date, refuses tomorrow, and Restocked sets it to now, with Undo', async ({ page }) => {
  const name = unique('Asafoetida');
  const id = await makeStaple(page, name);
  await page.goto('/recipes/ingredients');
  await page.getByRole('searchbox', { name: 'Search ingredients' }).fill(name);
  await page.getByRole('region', { name: 'All ingredients' }).getByRole('button', { name: new RegExp(`^${name}`) }).click();
  const editor = isPhone(page)
    ? page.getByRole('dialog', { name: `Edit ${name}` })
    : page.getByRole('complementary', { name: `Edit ${name}` });
  const date = editor.getByLabel('Date restocked');
  await expect(editor.getByText(/^Not restocked yet/)).toBeVisible();

  const five = await daysAgo(page, 5);
  await date.fill(five.iso);
  await expect(editor.getByText(`Restocked 5 days ago · `, { exact: false })).toBeVisible();
  await expect
    .poll(async () => ((await (await page.request.get(`/api/v1/foods/${id}`)).json()) as Json).restocked_on)
    .toBe(five.iso);
  const saved = await (await page.request.get(`/api/v1/foods/${id}`)).json();
  expect(saved.restocked_days_ago).toBe(5);

  // The date field stops at today.
  const today = await daysAgo(page, 0);
  await expect(date).toHaveAttribute('max', today.iso);

  // The server refuses a day after today.
  const tomorrow = await daysAgo(page, -1);
  const refused = await page.request.patch(`/api/v1/foods/${id}`, { data: { restocked_on: tomorrow.iso }, headers: key() });
  expect(refused.status()).toBe(422);

  await editor.getByRole('button', { name: 'Restocked', exact: true }).click();
  await expect(editor.getByText('Restocked today · ')).toBeVisible();
  // Saved: the toast is then the server's, with its Undo.
  await expect
    .poll(async () => ((await (await page.request.get(`/api/v1/foods/${id}`)).json()) as Json).restocked_days_ago)
    .toBe(0);
  const status = page.getByRole('status').filter({ hasText: `${name} restocked` });
  await expect(status).toBeVisible();
  await status.getByRole('button', { name: 'Undo' }).click();
  await expect(editor.getByText('Restocked 5 days ago · ')).toBeVisible();
});

test('a day typed under a newer Shopping tick wins: the chip shows the typed day (cabledrawer 2 Nov)', async ({
  page,
}) => {
  const name = unique('Fenugreek');
  const id = await makeStaple(page, name);
  // Ticked on Shopping just now (another phone): the staple is restocked today.
  const login = ((await (await page.request.get('/api/v1/me')).json()) as Json).id;
  const { lists } = (await (await page.request.get('/api/v1/shopping/lists')).json()) as Json;
  const list = lists.find((l: Json) => l.main).id;
  const item = crypto.randomUUID();
  for (const fields of [
    { kind: 'add', list_id: list, item_id: item, food_id: id },
    { kind: 'tick', item_id: item },
  ]) {
    const sent = await page.request.post('/api/v1/shopping/actions', {
      data: {
        protocol: 1,
        device_id: '11111111-2222-4333-8444-555555555555',
        login_id: login,
        since: 0,
        sent_at: new Date().toISOString(),
        actions: [{ id: crypto.randomUUID(), made_at: new Date().toISOString(), seen: 0, ...fields }],
      },
    });
    expect(sent.ok(), await sent.text()).toBe(true);
  }
  await expect
    .poll(async () => ((await (await page.request.get(`/api/v1/foods/${id}`)).json()) as Json).restocked_days_ago)
    .toBe(0);

  // An earlier day typed in the editor is kept, and shown.
  await page.goto('/recipes/ingredients');
  await page.getByRole('searchbox', { name: 'Search ingredients' }).fill(name);
  await page.getByRole('region', { name: 'All ingredients' }).getByRole('button', { name: new RegExp(`^${name}`) }).click();
  const editor = isPhone(page)
    ? page.getByRole('dialog', { name: `Edit ${name}` })
    : page.getByRole('complementary', { name: `Edit ${name}` });
  const four = await daysAgo(page, 4);
  await editor.getByLabel('Date restocked').fill(four.iso);
  await expect(editor.getByText('Restocked 4 days ago · ', { exact: false })).toBeVisible();
  await expect
    .poll(async () => ((await (await page.request.get(`/api/v1/foods/${id}`)).json()) as Json).restocked_on)
    .toBe(four.iso);

  await page.goto('/pantry');
  const chip = page.getByRole('button', { name: new RegExp(`^(Add )?${name}`) });
  await expect(chip).toContainText(`Restocked ${four.words}`);
});

test('How much? for a new ingredient offers 100 g · 250 g · 500 g · 1 kg, then Type an amount, and a choice is kept', async ({
  page,
}) => {
  const name = unique('Poppy seeds');
  const made = await page.request.post('/api/v1/foods', { data: { name, counted_as: 'weight' }, headers: key() });
  expect(made.status()).toBe(201);
  const foodId = ((await made.json()) as Json).food.id;
  const lists = (await (await page.request.get('/api/v1/shopping/lists')).json()) as Json;
  const main = (lists.lists ?? lists).find((l: Json) => l.main).id;
  const added = await page.request.post(`/api/v1/shopping/lists/${main}/items`, { data: { food_id: foodId }, headers: key() });
  expect(added.ok(), await added.text()).toBe(true);
  await page.goto('/shopping');
  await page.getByRole('checkbox', { name: `Tick ${name}` }).click();
  const row = page.getByRole('listitem').filter({ hasText: name });
  await expect(row.getByText('How much?')).toBeVisible();
  await expect(row.getByRole('radio')).toHaveText(['100 g', '250 g', '500 g', '1 kg', 'Type an amount']);
  await row.getByRole('radio', { name: '100 g', exact: true }).click();
  await expect(row.getByText('Pantry gets 1 pack · 100 g.')).toBeVisible();
  await row.getByRole('button', { name: 'Done' }).click();
  await expect
    .poll(async () => {
      const stock = (await (await page.request.get(`/api/v1/pantry?q=${encodeURIComponent(name)}`)).json()) as Json;
      return JSON.stringify(stock.places);
    })
    .toContain('100');
});

test('New recipe opens a small choice: Add by hand · Import from a link, with keys and focus', async ({ page }) => {
  await page.goto('/recipes');
  const button = page.getByRole('button', { name: 'New recipe', exact: true });
  await button.focus();
  await page.keyboard.press('Enter');
  await expect(page.getByRole('menu', { name: 'New recipe' }).getByRole('menuitem')).toHaveText(['Add by hand', 'Import from a link']);
  await expect(page.getByRole('menuitem', { name: 'Add by hand' })).toBeFocused();
  for (const item of await page.getByRole('menuitem').all()) {
    expect((await item.boundingBox())!.height).toBeGreaterThanOrEqual(44);
  }
  await page.keyboard.press('Escape');
  await expect(page.getByRole('menu')).toHaveCount(0);
  await expect(button).toBeFocused();
  await button.click();
  await page.getByRole('menuitem', { name: 'Import from a link' }).click();
  await expect(page).toHaveURL(/\/recipes\/import$/);
  await expect(page.getByRole('heading', { level: 1 })).toHaveText('Import a recipe');
  // The sidebar (or the phone's button) marks Import as the current page.
  if (!isPhone(page)) {
    await expect(page.getByRole('group', { name: 'Recipes' }).getByRole('link', { name: 'Import', exact: true })).toHaveAttribute(
      'aria-current',
      'page',
    );
  }
  await checkPage(page);
});

test('Import is its own item: the sidebar on a computer, a button beside Drafts and Ingredients on a phone', async ({ page }) => {
  await page.goto('/recipes');
  if (isPhone(page)) {
    await expect(page.getByRole('navigation', { name: 'Recipes' }).getByRole('link')).toHaveText([
      'Import',
      /^Drafts\s*\d*$/,
      'Ingredients',
    ]);
  } else {
    await expect(page.getByRole('group', { name: 'Recipes' }).getByRole('link')).toHaveText([
      'All recipes',
      'Import',
      /^Drafts\s*\d*$/,
      'Ingredients',
    ]);
  }
  await page.getByRole('link', { name: 'Import', exact: true }).click();
  await expect(page).toHaveURL(/\/recipes\/import$/);
});

test('the version is small grey text: in the sidebar foot on a computer, at the bottom of Settings on a phone', async ({ page }) => {
  await page.goto(isPhone(page) ? '/settings' : '/');
  // (The sidebar is in the page on a phone too, hidden: only the one that shows counts.)
  const version = page.locator('p.version:visible');
  await expect(version).toHaveText(/^Mealwright \d+\.\d+\.\d+/);
  await expect(version).toHaveCount(1);
  if (!isPhone(page)) {
    await expect(page.getByRole('complementary', { name: 'Sidebar' }).getByText(/^Mealwright \d/)).toBeVisible();
  }
  await checkPage(page);
});

test('Settings is a cog beside the avatar: in the phone header (44 px), and after the name in the sidebar', async ({ page }) => {
  await page.goto('/recipes');
  const link = page.getByRole('link', { name: /· Settings$/ });
  await expect(link).toHaveCount(1);
  await expect(link).toBeVisible();
  const box = (await link.boundingBox())!;
  if (isPhone(page)) {
    // The avatar and the cog, each 44 px, in one link.
    expect(box.height).toBeGreaterThanOrEqual(44);
    expect(box.width).toBeGreaterThanOrEqual(88);
    await expectTouchTargets(page);
  } else {
    await expect(link.locator('.cog')).toBeVisible();
  }
  await link.click();
  await expect(page.getByRole('heading', { name: 'Settings', level: 1 })).toBeVisible();
});

test('on a phone the Pantry tab remembers Pantry · Ingredients', async ({ page }) => {
  test.skip(!isPhone(page), 'the switch is the phone’s');
  await page.goto('/pantry');
  const switcher = page.getByRole('navigation', { name: 'Pantry or Ingredients' });
  await expect(switcher.getByRole('link', { name: 'Pantry' })).toHaveAttribute('aria-current', 'page');
  const tab = page.getByRole('navigation', { name: 'Main' }).getByRole('link', { name: 'Pantry' });
  await expect(tab).toHaveAttribute('href', '/pantry');

  await switcher.getByRole('link', { name: 'Ingredients' }).click();
  await expect(page).toHaveURL(/\/recipes\/ingredients\?from=pantry$/);
  await expect(switcher.getByRole('link', { name: 'Ingredients' })).toHaveAttribute('aria-current', 'page');
  // Ingredients seen this way is the Pantry tab's; there is no way "up" to Recipes.
  await expect(tab).toHaveAttribute('aria-current', 'page');
  await expect(page.getByRole('navigation', { name: 'Main' }).getByRole('link', { name: 'Recipes' })).not.toHaveAttribute(
    'aria-current',
    'page',
  );

  // Away and back: the Pantry tab opens where it was left.
  await page.goto('/shopping');
  await page.getByRole('navigation', { name: 'Main' }).getByRole('link', { name: 'Pantry' }).click();
  await expect(page).toHaveURL(/\/recipes\/ingredients\?from=pantry$/);
  await page.reload();
  await expect(page.getByRole('navigation', { name: 'Main' }).getByRole('link', { name: 'Pantry' })).toHaveAttribute(
    'href',
    /ingredients\?from=pantry$/,
  );

  await switcher.getByRole('link', { name: 'Pantry' }).click();
  await expect(page).toHaveURL(/\/pantry$/);
  await page.goto('/plan');
  await page.getByRole('navigation', { name: 'Main' }).getByRole('link', { name: 'Pantry' }).click();
  await expect(page).toHaveURL(/\/pantry$/);
  await checkPage(page);
});

test('the Pantry tab works with storage blocked: it opens Pantry', async ({ page }) => {
  test.skip(!isPhone(page), 'the switch is the phone’s');
  await page.addInitScript(() => {
    Object.defineProperty(window, 'localStorage', {
      get() {
        throw new DOMException('blocked', 'SecurityError');
      },
    });
  });
  await page.goto('/shopping');
  await page.getByRole('navigation', { name: 'Main' }).getByRole('link', { name: 'Pantry' }).click();
  await expect(page).toHaveURL(/\/pantry$/);
  await page.getByRole('navigation', { name: 'Pantry or Ingredients' }).getByRole('link', { name: 'Ingredients' }).click();
  await expect(page).toHaveURL(/\/recipes\/ingredients\?from=pantry$/);
});

test('on a 320 px phone, dark, at 200% text: header cog and avatar, the switch, the New recipe choice and the Restocked row fit', async ({
  page,
}) => {
  test.skip(!isPhone(page), 'a phone layout');
  await setAccountTheme(page, 'dark');
  await page.setViewportSize({ width: 320, height: 700 });
  const big = () => page.evaluate(() => (document.documentElement.style.fontSize = '200%'));
  const tall = async (what: ReturnType<Page['locator']>) => {
    await expect(what).toBeVisible();
    expect((await what.boundingBox())!.height).toBeGreaterThanOrEqual(44);
  };

  await page.goto('/pantry');
  await big();
  await tall(page.getByRole('link', { name: /· Settings$/ }));
  const settings = (await page.getByRole('link', { name: /· Settings$/ }).boundingBox())!;
  expect(settings.x + settings.width).toBeLessThanOrEqual(320);
  const switcher = page.getByRole('navigation', { name: 'Pantry or Ingredients' });
  await tall(switcher.getByRole('link', { name: 'Pantry' }));
  await tall(switcher.getByRole('link', { name: 'Ingredients' }));
  await expectNoSidewaysScroll(page);

  await page.goto('/recipes');
  await big();
  const button = page.getByRole('button', { name: 'New recipe', exact: true });
  await tall(button);
  await button.click();
  await tall(page.getByRole('menuitem', { name: 'Add by hand' }));
  await tall(page.getByRole('menuitem', { name: 'Import from a link' }));
  await expectNoSidewaysScroll(page);

  const name = unique('Saffron');
  await makeStaple(page, name);
  await page.goto('/recipes/ingredients');
  await page.getByRole('searchbox', { name: 'Search ingredients' }).fill(name);
  await page.getByRole('region', { name: 'All ingredients' }).getByRole('button', { name: new RegExp(`^${name}`) }).click();
  const editor = page.getByRole('dialog', { name: `Edit ${name}` });
  await expect(editor.getByLabel('Date restocked')).toBeVisible();
  await big();
  const date = editor.getByLabel('Date restocked');
  await date.scrollIntoViewIfNeeded();
  await tall(date);
  await tall(editor.getByRole('button', { name: 'Restocked', exact: true }));
  await expectNoSidewaysScroll(page);
  const box = (await date.boundingBox())!;
  expect(box.x + box.width).toBeLessThanOrEqual(320);
});
