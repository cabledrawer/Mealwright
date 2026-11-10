import { test, expect, type Page } from './clock.ts';
import { checkPage, expectNoSidewaysScroll, isPhone, setAccountTheme } from './a11y.ts';

// Check on the phone (0.7, F141, cabledrawer 3 Nov): Focus (the default) and One at a time, chosen in
// Settings → Appearance, and the computer's Check screen that stays as it was. Runs on Chromium
// and WebKit at phone size, and on a computer. The recipe is pasted (the path that never goes
// online); the drafts are the real server's, and each test deletes its own.

test.use({ serviceWorkers: 'block' });

type Json = Record<string, any>; // eslint-disable-line @typescript-eslint/no-explicit-any

const unique = (name: string) => `${name} ${test.info().project.name.replace(/\D/g, '')}${Date.now() % 100000}`;

test.beforeEach(async ({ page }) => {
  await setAccountTheme(page, 'auto');
});

/** This device's choice for the Check screen, set before the app starts (as Settings keeps it). */
async function chooseMode(page: Page, mode: 'focus' | 'one') {
  await page.addInitScript((value) => {
    if (value === 'one') localStorage.setItem('mealwright.checkMode', 'one');
    else localStorage.removeItem('mealwright.checkMode');
  }, mode);
}

/** Paste a recipe with two lines that need a choice and two steps, and read it. */
async function checking(page: Page, title: string, hing: string, masala: string) {
  await page.goto('/recipes/import');
  await page
    .getByLabel('Paste a link or the recipe’s text')
    .fill(`${title}\nIngredients\n¼ tsp ${hing}\n1 tsp ${masala}\nMethod\n1. Boil.\n2. Fry.\n`);
  await page.getByRole('button', { name: 'Read the recipe' }).click();
  await expect(page.getByRole('heading', { level: 1 })).toBeVisible();
}

async function draftsNamed(page: Page, title: string): Promise<Json[]> {
  const list = (await (await page.request.get('/api/v1/recipes/drafts')).json()) as Json;
  return list.drafts.filter((d: Json) => d.name === title);
}

async function deleteDrafts(page: Page, title: string) {
  for (const draft of await draftsNamed(page, title)) await page.request.delete(`/api/v1/recipes/drafts/${draft.id}`);
}

test('Focus: no menu, the ingredients get the screen, Close keeps the draft and the choices', async ({ page }) => {
  test.skip(!isPhone(page), 'the phone’s layout');
  await chooseMode(page, 'focus');
  const title = unique('Dal tadka');
  await checking(page, title, unique('Hing'), unique('Masala'));
  await expect(page.getByText('Step 2 of 3 · nothing saved yet')).toBeVisible();
  // The app's menu is gone; the page is its own, with Close and Save at the foot.
  await expect(page.getByRole('navigation', { name: 'Main' })).toBeHidden();
  const close = page.getByRole('button', { name: /^Close/ });
  await expect(close).toContainText('Kept in Drafts');
  await expect(close).toBeInViewport({ ratio: 1 });
  await expect(page.getByRole('button', { name: 'Save recipe' })).toBeInViewport({ ratio: 1 });
  // The title and the bar leave the list most of the screen (hand test: it was about half).
  const viewport = page.viewportSize()!;
  const first = await page.getByRole('button', { name: 'New ingredient' }).first().boundingBox();
  const saveBox = await page.getByRole('button', { name: 'Save recipe' }).boundingBox();
  expect(first && first.y < viewport.height / 2).toBe(true);
  expect(saveBox && saveBox.y + saveBox.height <= viewport.height).toBe(true);
  await checkPage(page);
  // A choice, then Close: the draft is on Drafts with it.
  await page.getByRole('button', { name: 'Treat as staple' }).first().click();
  await close.click();
  await expect(page).toHaveURL(/\/recipes\/drafts$/);
  await expect(page.getByText(title)).toBeVisible();
  expect(await draftsNamed(page, title)).toHaveLength(1);
  // It reopens with the choice kept, and Close on it, unchanged, just leaves.
  await page.getByRole('link', { name: `Carry on ${title}` }).click();
  await expect(page).toHaveURL(/\/recipes\/drafts\/\d+$/);
  await expect(page.getByText(/Made a staple when you save/)).toBeVisible();
  await page.getByRole('button', { name: /^Close/ }).click();
  await expect(page).toHaveURL(/\/recipes\/drafts$/);
  await deleteDrafts(page, title);
});

test('One at a time: each line that needs you, then every step; Close keeps the draft', async ({ page }) => {
  test.skip(!isPhone(page), 'the phone’s layout');
  await chooseMode(page, 'one');
  const title = unique('Rasam');
  await checking(page, title, unique('Hing'), unique('Masala'));
  const header = page.getByRole('heading', { level: 1 });
  await expect(header).toHaveText('Ingredients · 1 of 2 to check');
  await expect(page.getByRole('navigation', { name: 'Main' })).toBeHidden();
  await expect(page.getByRole('button', { name: /^← Back/ })).toBeDisabled();
  await checkPage(page);
  // The first line: a choice, then on to the next.
  await page.getByRole('button', { name: 'Treat as staple' }).click();
  await page.getByRole('button', { name: /^Next/ }).click();
  await expect(header).toHaveText('Ingredients · 2 of 2 to check');
  await page.getByRole('button', { name: /^Next/ }).click();
  // Every step, not only long ones.
  await expect(header).toHaveText('Method · step 1 of 2');
  await expect(page.getByText('Boil.', { exact: true })).toBeVisible();
  await checkPage(page);
  await page.getByRole('button', { name: 'Remove step' }).click();
  await expect(page.getByText('Removed step 1')).toBeVisible();
  await expect(header).toHaveText('Method · step 1 of 1');
  await page.getByRole('button', { name: 'Undo', exact: true }).click();
  // The walk stays on the step it was on; the restored one is before it.
  await expect(header).toHaveText('Method · step 2 of 2');
  await page.getByRole('button', { name: /^← Back/ }).click();
  await expect(header).toHaveText('Method · step 1 of 2');
  await expect(page.getByText('Boil.', { exact: true })).toBeVisible();
  await page.getByRole('button', { name: /^Next/ }).click();
  await expect(page.getByRole('button', { name: 'Save recipe' })).toBeVisible();
  // Back, then Close: the draft keeps the choice made on the first line.
  await page.getByRole('button', { name: /^← Back/ }).click();
  await page.getByRole('button', { name: 'Close (kept in Drafts)' }).click();
  await expect(page).toHaveURL(/\/recipes\/drafts$/);
  const [draft] = await draftsNamed(page, title);
  const kept = (await (await page.request.get(`/api/v1/recipes/drafts/${draft!.id}`)).json()) as Json;
  expect(Object.values(kept.choices.lines as Json).map((c) => (c as Json).kind)).toEqual(['staple']);
  await deleteDrafts(page, title);
});

test('One at a time: Add a line goes to the new line, which is named and has the usual choices (F187)', async ({ page }) => {
  test.skip(!isPhone(page), 'the phone’s layout');
  await chooseMode(page, 'one');
  const title = unique('Rasam');
  await checking(page, title, unique('Hing'), unique('Masala'));
  const header = page.getByRole('heading', { level: 1 });
  await expect(header).toHaveText('Ingredients · 1 of 2 to check');
  await page.getByRole('button', { name: 'Add a line', exact: true }).click();
  // The new line is at the end of its section: a third stop, with its name box ready.
  await expect(header).toHaveText('Ingredients · 3 of 3 to check');
  const name = page.getByLabel('What is it?');
  await expect(name).toBeFocused();
  await checkPage(page);
  const curry = unique('Curry leaves');
  await name.fill(curry);
  await name.press('Enter');
  await expect(header).toHaveText('Ingredients · 3 of 3 to check');
  for (const choice of ['Pick an ingredient', 'Made in this recipe', 'Made in another recipe', 'Treat as staple']) {
    await expect(page.getByRole('button', { name: choice, exact: true })).toBeVisible();
  }
  await page.getByRole('button', { name: 'Treat as staple', exact: true }).click();
  await expect(page.getByText('New staple:')).toBeVisible();
  // Close keeps the draft with the new line and its choice.
  await page.getByRole('button', { name: 'Close (kept in Drafts)' }).click();
  await expect(page).toHaveURL(/\/recipes\/drafts$/);
  const [draft] = await draftsNamed(page, title);
  const kept = (await (await page.request.get(`/api/v1/recipes/drafts/${draft!.id}`)).json()) as Json;
  expect(kept.review.lines).toHaveLength(3);
  expect(kept.review.lines[2]).toMatchObject({ written: '', words: curry });
  expect(kept.choices.lines['2']).toMatchObject({ kind: 'staple', name: curry });
  await deleteDrafts(page, title);
});

test('One at a time and Focus: the title is in from the edge, and the step note is under it (cabledrawer 9 Nov)', async ({ page }) => {
  test.skip(!isPhone(page), 'the phone’s layout');
  await chooseMode(page, 'one');
  await checking(page, unique('Rasam'), unique('Hing'), unique('Masala'));
  const title = page.getByRole('heading', { level: 1 });
  const close = (await page.getByRole('button', { name: 'Close (kept in Drafts)' }).boundingBox())!;
  const t = (await title.boundingBox())!;
  expect(t.x).toBeGreaterThanOrEqual(close.x + close.width);
  const note = (await page.getByText(/· nothing saved yet$/).boundingBox())!;
  expect(note.y).toBeGreaterThanOrEqual(t.y + t.height - 2);
  await expectNoSidewaysScroll(page);
});

test('One at a time: See all shows the whole list, and a reopened draft starts One at a time again', async ({ page }) => {
  test.skip(!isPhone(page), 'the phone’s layout');
  await chooseMode(page, 'one');
  const title = unique('Kootu');
  await checking(page, title, unique('Hing'), unique('Masala'));
  await page.getByRole('button', { name: 'Close (kept in Drafts)' }).click();
  await expect(page).toHaveURL(/\/recipes\/drafts$/);
  await page.getByRole('link', { name: `Carry on ${title}` }).click();
  await expect(page.getByRole('heading', { level: 1 })).toHaveText('Ingredients · 1 of 2 to check');
  await page.getByRole('button', { name: 'See all' }).click();
  await expect(page.getByRole('button', { name: /^Close/ })).toContainText('Kept in Drafts');
  await expect(page.getByRole('button', { name: 'Save recipe' })).toBeVisible();
  await expect(page.getByRole('button', { name: /^Next/ })).toHaveCount(0);
  await deleteDrafts(page, title);
});

test('Settings → Appearance chooses it, on this device: Focus until changed', async ({ page }) => {
  test.skip(!isPhone(page), 'the phone’s layout');
  await page.goto('/settings?section=appearance');
  const focus = page.getByRole('radio', { name: /^Focus/ });
  const one = page.getByRole('radio', { name: /^One at a time/ });
  await expect(page.getByText('Checking a recipe on the phone')).toBeVisible();
  await expect(focus).toBeChecked();
  await checkPage(page);
  await one.check();
  await page.reload();
  await expect(one).toBeChecked();
  const title = unique('Thoran');
  await checking(page, title, unique('Hing'), unique('Masala'));
  await expect(page.getByRole('heading', { level: 1 })).toHaveText('Ingredients · 1 of 2 to check');
  await page.getByRole('button', { name: 'Close (kept in Drafts)' }).click();
  await expect(page).toHaveURL(/\/recipes\/drafts$/);
  await deleteDrafts(page, title);
  await page.goto('/settings?section=appearance');
  await focus.check();
  await expect(focus).toBeChecked();
});

test('a computer keeps today’s Check screen, whatever the phone’s choice is', async ({ page }) => {
  test.skip(isPhone(page), 'the computer’s layout');
  await chooseMode(page, 'one');
  await checking(page, unique('Pongal'), unique('Hing'), unique('Masala'));
  await expect(page.getByRole('heading', { level: 1 })).toHaveText('Check before saving');
  await expect(page.getByRole('list', { name: 'Import steps' })).toBeVisible();
  await expect(page.getByRole('button', { name: 'Cancel', exact: true })).toBeVisible();
  await expect(page.getByRole('button', { name: 'Save recipe' })).toBeVisible();
  await expect(page.getByRole('button', { name: /^Next/ })).toHaveCount(0);
  await expect(page.getByRole('button', { name: /^Close/ })).toHaveCount(0);
  await expect(page.getByRole('navigation', { name: 'Main' }).or(page.getByRole('navigation', { name: 'Sidebar' })).first()).toBeVisible();
});

const opacity = (button: ReturnType<Page['getByRole']>) => button.evaluate((el) => Number(getComputedStyle(el).opacity));

test('Focus: with a step box open Close looks greyed like Save recipe (F154)', async ({ page }) => {
  test.skip(!isPhone(page), 'the phone’s layout');
  await chooseMode(page, 'focus');
  await checking(page, unique('Pongal'), unique('Hing'), unique('Masala'));
  const close = page.getByRole('button', { name: /^Close/ });
  const save = page.getByRole('button', { name: 'Save recipe' });
  expect(await opacity(close)).toBe(1);
  await page.getByRole('button', { name: /^Change step 1/ }).click();
  await expect(close).toBeDisabled();
  await expect(save).toBeDisabled();
  expect(await opacity(close)).toBeLessThan(1);
  expect(await opacity(close)).toBe(await opacity(save));
});

test('One at a time: with a step box open Close, See all, Back and Next look greyed (F154)', async ({ page }) => {
  test.skip(!isPhone(page), 'the phone’s layout');
  await chooseMode(page, 'one');
  await checking(page, unique('Upma'), unique('Hing'), unique('Masala'));
  await page.getByRole('button', { name: /^Next/ }).click();
  await page.getByRole('button', { name: /^Next/ }).click(); // step 1
  const buttons = [
    page.getByRole('button', { name: 'Close (kept in Drafts)' }),
    page.getByRole('button', { name: 'See all' }),
    page.getByRole('button', { name: /^← Back/ }),
    page.getByRole('button', { name: /^Next/ }),
  ];
  for (const button of buttons) expect(await opacity(button)).toBe(1);
  await page.getByRole('button', { name: 'Change the words' }).click();
  for (const button of buttons) {
    await expect(button).toBeDisabled();
    expect(await opacity(button)).toBeLessThan(1);
  }
});

test('One at a time: the first screen starts with the recipe’s name, Serves and minutes (F141 follow-up)', async ({ page }) => {
  test.skip(!isPhone(page), 'the phone’s layout');
  await chooseMode(page, 'one');
  const title = unique('Kootu');
  await checking(page, title, unique('Hing'), unique('Masala'));
  const name = page.getByLabel('Name').first();
  await expect(name).toHaveValue(title);
  await expect(page.getByLabel('Serves')).toBeVisible();
  await expect(page.getByLabel('Minutes')).toBeVisible();
  const nameBox = (await name.boundingBox())!;
  const lineBox = (await page.getByRole('button', { name: 'Treat as staple' }).boundingBox())!;
  expect(nameBox.y).toBeLessThan(lineBox.y);
  await checkPage(page);
  await page.getByRole('button', { name: /^Next/ }).click();
  await expect(page.getByLabel('Serves')).toHaveCount(0);
});

test('One at a time: a swipe left is Next, right is Back, and it waits while a step box is open (F145)', async ({ page }) => {
  test.skip(!isPhone(page), 'the phone’s layout');
  await chooseMode(page, 'one');
  await checking(page, unique('Rava'), unique('Hing'), unique('Masala'));
  const header = page.getByRole('heading', { level: 1 });
  const swipe = async (dx: number) => {
    const y = 600;
    const x = dx < 0 ? 340 : 50;
    await page.mouse.move(x, y);
    await page.mouse.down();
    await page.mouse.move(x + dx, y, { steps: 6 });
    await page.mouse.up();
  };
  await expect(header).toHaveText('Ingredients · 1 of 2 to check');
  await swipe(-250);
  await expect(header).toHaveText('Ingredients · 2 of 2 to check');
  await swipe(250);
  await expect(header).toHaveText('Ingredients · 1 of 2 to check');
  await swipe(-250);
  await swipe(-250);
  await expect(header).toHaveText('Method · step 1 of 2');
  await page.getByRole('button', { name: 'Change the words' }).click();
  await swipe(-250);
  await expect(page.getByLabel('Words of step 1')).toBeVisible();
  await expect(header).toHaveText('Method · step 1 of 2');
  await page.getByRole('button', { name: 'Done' }).click();
  await swipe(-250);
  await expect(header).toHaveText('Method · step 2 of 2');
});

/** No connection: every call to the server fails and the device says it is offline. (The page's
 *  own files still load, as they do from the service worker's copy on a phone, so the toast
 *  that Close shows is not lost with the page.) */
async function goOffline(page: Page) {
  await page.route('**/api/v1/**', (route) => route.abort('internetdisconnected'));
  await page.evaluate(() => window.dispatchEvent(new Event('offline')));
  // The page's own note comes after a short while; Close works before it, and after.
  await expect(page.getByText('You’re offline. Save when you’re back online.')).toBeVisible();
}

async function backOnline(page: Page) {
  await page.unroute('**/api/v1/**');
  await page.evaluate(() => window.dispatchEvent(new Event('online')));
}

test('F174, One at a time: Close works offline, says so and leaves; nothing was kept', async ({ page }) => {
  test.skip(!isPhone(page), 'the phone’s layout');
  await chooseMode(page, 'one');
  const title = unique('Sambar offline');
  await checking(page, title, unique('Hing'), unique('Masala'));
  await page.getByRole('button', { name: 'Treat as staple' }).click();
  await goOffline(page);
  const close = page.getByRole('button', { name: 'Close (kept in Drafts)' });
  await expect(close).toBeEnabled();
  await close.click();
  await expect(page.getByText('You’re offline: changes since then won’t be kept')).toBeVisible();
  await expect(page).toHaveURL(/\/recipes$/);
  await backOnline(page);
  expect(await draftsNamed(page, title)).toHaveLength(0);
});

test('F174, a draft opened again: Close works offline and the draft stays as it was last kept', async ({ page }) => {
  test.skip(!isPhone(page), 'the phone’s layout');
  await chooseMode(page, 'one');
  const title = unique('Kootu offline');
  await checking(page, title, unique('Hing'), unique('Masala'));
  await page.getByRole('button', { name: 'Close (kept in Drafts)' }).click();
  await expect(page).toHaveURL(/\/recipes\/drafts$/);
  const [before] = await draftsNamed(page, title);
  await page.getByRole('link', { name: `Carry on ${title}` }).click();
  await page.getByRole('button', { name: 'See all' }).click();
  // A change since the draft was last kept (the name), then the connection goes.
  await page.getByRole('button', { name: 'Treat as staple' }).first().click();
  await goOffline(page);
  const close = page.getByRole('button', { name: /^Close/ });
  await expect(close).toBeEnabled();
  await close.click();
  await expect(page.getByText('You’re offline: changes since then won’t be kept')).toBeVisible();
  await expect(page).toHaveURL(/\/recipes$/);
  await backOnline(page);
  const [after] = await draftsNamed(page, title);
  expect(after!.id).toBe(before!.id);
  const kept = (await (await page.request.get(`/api/v1/recipes/drafts/${after!.id}`)).json()) as Json;
  expect(Object.keys(kept.choices.lines as Json)).toHaveLength(0); // as last kept: no choice yet
  await deleteDrafts(page, title);
});

test('F174, a keep still on its way when the connection goes: Close works at once, says so and leaves', async ({ page }) => {
  test.skip(!isPhone(page), 'the phone’s layout');
  await chooseMode(page, 'one');
  const title = unique('Rasam hung');
  await checking(page, title, unique('Hing'), unique('Masala'));
  await page.getByRole('button', { name: 'Treat as staple' }).click();
  // The server never answers the draft: the keep is on its way for good.
  let release: () => void = () => {};
  const stuck = new Promise<void>((resolve) => (release = resolve));
  await page.route('**/api/v1/recipes/drafts', async (route) => {
    if (route.request().method() !== 'POST') return route.fallback();
    await stuck;
    await route.abort('internetdisconnected');
  });
  const close = page.getByRole('button', { name: 'Close (kept in Drafts)' });
  await close.click();
  await expect(close).toBeDisabled(); // keeping, with the connection still up
  await goOffline(page);
  await expect(close).toBeEnabled();
  await close.click();
  await expect(page.getByText('You’re offline: changes since then won’t be kept')).toBeVisible();
  await expect(page).toHaveURL(/\/recipes$/);
  release();
  await page.unroute('**/api/v1/recipes/drafts');
  await backOnline(page);
  expect(await draftsNamed(page, title)).toHaveLength(0);
});

test('One at a time: "Make this its own recipe" is above a line of the section, and a draft keeps it (F190)', async ({ page }) => {
  test.skip(!isPhone(page), 'the phone’s layout');
  await chooseMode(page, 'one');
  const title = unique('Masala dosa');
  const dal = unique('Urad dal');
  await page.goto('/recipes/import');
  await page
    .getByLabel('Paste a link or the recipe’s text')
    .fill(`${title}\nIngredients\nFor the batter\n1 cup ${dal}\n2 cups ${unique('Idli rice')}\nFor the dosa\n1 tbsp ${unique('Ghee')}\nMethod\nFor the batter:\n1. Soak it.\nFor the dosa:\n1. Fry it.\n`);
  await page.getByRole('button', { name: 'Read the recipe' }).click();
  await expect(page.getByRole('heading', { level: 1 })).toHaveText('Ingredients · 1 of 3 to check');
  // The first line is in the batter: its section is named above it, with the button.
  await expect(page.getByText('For the batter', { exact: true })).toBeVisible();
  await page.getByRole('button', { name: 'Make this its own recipe' }).click();
  const sheet = page.getByRole('dialog', { name: /its own recipe\?$/ });
  await expect(sheet).toContainText('with its 2 lines and 1 step, kept as Made ahead');
  await sheet.getByLabel('How much it makes').fill('3');
  await checkPage(page);
  await sheet.getByRole('button', { name: 'Make it its own recipe' }).click();
  await expect(page.getByText('Its own recipe:')).toContainText('3 cups');
  // The section's lines are still checked here, one at a time.
  await expect(page.getByRole('heading', { level: 1 })).toHaveText('Ingredients · 1 of 3 to check');
  await page.getByRole('button', { name: 'Close (kept in Drafts)' }).click();
  await expect(page).toHaveURL(/\/recipes\/drafts$/);
  const [draft] = await draftsNamed(page, title);
  const kept = (await (await page.request.get(`/api/v1/recipes/drafts/${draft!.id}`)).json()) as Json;
  const batter = kept.review.lines.find((l: Json) => l.kind === 'heading' && l.words === 'For the batter');
  expect(batter.own).toMatchObject({ name: 'Batter', amount: 3, unit: 'cup' });
  // Carrying on from the draft: it is still its own recipe.
  await page.getByRole('link', { name: `Carry on ${title}` }).click();
  await expect(page.getByText('Its own recipe:')).toContainText('Batter · 3 cups');
  await deleteDrafts(page, title);
});
