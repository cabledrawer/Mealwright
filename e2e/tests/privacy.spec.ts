import { test, expect, type Page } from './clock.ts';
import { checkPage, expectNoSidewaysScroll, isPhone, setAccountTheme } from './a11y.ts';

// Settings → Privacy (0.5 PR 4): the switches for outside connections and "Your own network",
// against the real server, signed in as the test admin. A member (who sees the same page and
// changes nothing) and the failed, slow and offline states are covered with answers made up
// in the browser, because the app has no way to add a member until 0.8. The server's own
// permission rules are in backend/tests/test_privacy.py.
// Runs in the "phone 0.5 privacy" and "desktop 0.5 privacy" projects.

const IMPORT = 'Recipe import from links';
const PHOTOS = 'Download recipe photos';
const ADD = 'Add a name or address';

/** Every test leaves both switches off and the list empty, as it found them. */
async function reset(page: Page) {
  for (const name of ['recipe_import', 'recipe_photos']) {
    await page.request.put(`/api/v1/privacy/switches/${name}`, { data: { on: false } });
  }
  const list = await (await page.request.get('/api/v1/privacy/own-network')).json();
  for (const entry of list.entries as { id: number }[]) {
    await page.request.delete(`/api/v1/privacy/own-network/${entry.id}`);
  }
}

async function addViaApi(page: Page, value: string) {
  const response = await page.request.post('/api/v1/privacy/own-network', { data: { value } });
  expect(response.status(), await response.text()).toBe(201);
}

test.beforeEach(async ({ page }) => {
  await setAccountTheme(page, 'auto');
  await reset(page);
});

test.afterEach(async ({ page }) => {
  await reset(page);
});

test('Settings leads to Privacy, which starts with everything off, and passes the accessibility checks', async ({
  page,
}) => {
  await page.goto('/settings');
  // A computer's Settings has the Privacy section with this link in it; the phone's list has a
  // Privacy row that goes straight to the page (F193).
  await page
    .getByRole('link', { name: isPhone(page) ? /^Privacy/ : /Outside connections/ })
    .click();
  await expect(page).toHaveURL('/settings/privacy');
  await expect(page.getByRole('heading', { level: 1, name: 'Privacy' })).toBeVisible();
  await expect(page.getByText('Nothing leaves this server unless you switch it on.')).toBeVisible();
  await expect(page.getByRole('switch', { name: IMPORT })).not.toBeChecked();
  await expect(page.getByRole('switch', { name: PHOTOS })).not.toBeChecked();
  // The empty list.
  await expect(
    page.getByText('Nothing added yet. Every address on your own network is blocked.'),
  ).toBeVisible();
  await expect(page.getByRole('list', { name: 'Allowed on your own network' })).toHaveCount(0);
  await checkPage(page);
  // The way back.
  await page.getByRole('link', { name: 'Settings' }).first().click();
  await expect(page).toHaveURL('/settings');
});

test('an admin switches each connection on and off, and it stays', async ({ page }) => {
  await page.goto('/settings/privacy');
  const importSwitch = page.getByRole('switch', { name: IMPORT });
  const photoSwitch = page.getByRole('switch', { name: PHOTOS });
  await importSwitch.click();
  await expect(importSwitch).toBeChecked();
  await expect(photoSwitch).not.toBeChecked();
  await expect
    .poll(async () => (await (await page.request.get('/api/v1/privacy/switches')).json()).switches)
    .toEqual([
      { connection: 'recipe_import', on: true },
      { connection: 'recipe_photos', on: false },
    ]);
  await photoSwitch.click();
  await page.reload();
  await expect(importSwitch).toBeChecked();
  await expect(photoSwitch).toBeChecked();
  await checkPage(page); // the switches on
  await importSwitch.click();
  await expect(importSwitch).not.toBeChecked();
  await page.reload();
  await expect(importSwitch).not.toBeChecked();
  await expect(photoSwitch).toBeChecked();
});

test('an admin adds to "Your own network" and takes off, with Undo', async ({ page }) => {
  await page.goto('/settings/privacy');
  const box = page.getByRole('textbox', { name: ADD });
  await box.fill('Wiki.Home.Example');
  await page.getByRole('button', { name: 'Add', exact: true }).click();
  const list = page.getByRole('list', { name: 'Allowed on your own network' });
  await expect(list.getByText('wiki.home.example', { exact: true })).toBeVisible();
  await expect(list.getByText('A name · added by Tess, 17 Oct')).toBeVisible();
  await expect(box).toHaveValue('');
  await expect(page.getByText('Added wiki.home.example to Your own network')).toBeVisible();

  await box.fill('192.168.1.77/24');
  await box.press('Enter');
  await expect(list.getByText('192.168.1.0/24', { exact: true })).toBeVisible();
  await expect(list.getByText('A range · 256 addresses · added by Tess, 17 Oct')).toBeVisible();

  await page.reload();
  await expect(list.getByText('wiki.home.example', { exact: true })).toBeVisible();
  await expect(list.getByRole('listitem')).toHaveCount(2);
  await checkPage(page); // two entries

  await page.getByRole('button', { name: 'Remove wiki.home.example' }).click();
  await expect(list.getByText('wiki.home.example', { exact: true })).toHaveCount(0);
  await expect(page.getByText('Removed wiki.home.example from Your own network')).toBeVisible();
  await page.getByRole('button', { name: 'Undo', exact: true }).click();
  await expect(list.getByText('wiki.home.example', { exact: true })).toBeVisible();
  await page.reload();
  await expect(list.getByRole('listitem')).toHaveCount(2);
  await page.getByRole('button', { name: 'Remove 192.168.1.0/24' }).click();
  await page.getByRole('button', { name: 'Remove wiki.home.example' }).click();
  await expect(page.getByText('Nothing added yet.')).toBeVisible();
});

test('the server’s own sentence says why something can’t be added', async ({ page }) => {
  await page.goto('/settings/privacy');
  const box = page.getByRole('textbox', { name: ADD });
  const add = page.getByRole('button', { name: 'Add', exact: true });
  await box.fill('localhost');
  await add.click();
  await expect(page.getByRole('alert')).toContainText(
    'That can’t be added: this server itself (localhost), link-local and cloud “metadata” addresses are always blocked.',
  );
  await expect(box).toHaveValue('localhost');
  await box.fill('10.0.0.0/7');
  await add.click();
  await expect(page.getByRole('alert')).toContainText('That range is too wide. Add a smaller one, like 192.168.1.0/24.');
  await box.fill('what is this');
  await add.click();
  await expect(page.getByRole('alert')).toContainText('Type a name (wiki.home.example)');
  await checkPage(page); // with an error showing
  await box.fill('nas.home.lan');
  await add.click();
  await expect(page.getByRole('list', { name: 'Allowed on your own network' })).toBeVisible();
  await expect(box).toHaveValue('');
  await box.fill('NAS.home.lan');
  await add.click();
  await expect(page.getByRole('alert')).toHaveText('That’s already on the list.');
  await expect(page.getByRole('list', { name: 'Allowed on your own network' }).getByRole('listitem')).toHaveCount(1);
});

test('long names and many entries fit, at 100% and 200% text, and nothing scrolls sideways', async ({
  page,
}) => {
  const long =
    'a-very-long-name-for-a-wiki-on-the-home-server.in-the-spare-room.under-the-stairs.home.example.org';
  await addViaApi(page, long);
  for (let i = 1; i <= 12; i++) await addViaApi(page, `server${i}.home.example`);
  await page.goto('/settings/privacy');
  const list = page.getByRole('list', { name: 'Allowed on your own network' });
  await expect(list.getByRole('listitem')).toHaveCount(13);
  for (const size of ['100%', '200%']) {
    await page.evaluate((s) => (document.documentElement.style.fontSize = s), size);
    await expectNoSidewaysScroll(page);
    // The long name wraps inside its card, and its Remove button stays on screen.
    const name = list.getByText(long, { exact: true });
    const box = (await name.boundingBox())!;
    const remove = (await page.getByRole('button', { name: `Remove ${long}` }).boundingBox())!;
    const width = page.viewportSize()!.width;
    expect(box.x + box.width).toBeLessThanOrEqual(width);
    expect(remove.x + remove.width).toBeLessThanOrEqual(width + 1);
    expect(remove.width).toBeGreaterThanOrEqual(44);
    expect(remove.height).toBeGreaterThanOrEqual(44);
  }
  await page.evaluate(() => (document.documentElement.style.fontSize = ''));
  await checkPage(page);
});

test('the links from the import screen land on the right part, with the page still loading', async ({
  page,
}) => {
  for (let i = 1; i <= 12; i++) await addViaApi(page, `server${i}.home.example`);
  await page.goto('/settings/privacy#your-own-network');
  const heading = page.getByRole('heading', { level: 2, name: 'Your own network' });
  await expect(heading).toBeVisible();
  await expect(page.getByRole('list', { name: 'Allowed on your own network' })).toBeVisible();
  await expect
    .poll(async () => (await heading.boundingBox())!.y, { message: 'the heading is on screen' })
    .toBeLessThan(page.viewportSize()!.height);
  await page.goto('/settings/privacy#outside-connections');
  await expect(page.getByRole('heading', { level: 2, name: 'Outside connections' })).toBeInViewport();
});

test.describe('states made up in the browser', () => {
  const SWITCHES = (can: boolean) => ({
    switches: [
      { connection: 'recipe_import', on: true },
      { connection: 'recipe_photos', on: false },
    ],
    can_change: can,
  });
  const LIST = (can: boolean) => ({
    entries: [
      { id: 1, kind: 'name', value: 'wiki.home.example', addresses: null, added_by: 'Tess', added_on: '2026-10-22' },
      { id: 2, kind: 'range', value: '192.168.1.0/24', addresses: 256, added_by: 'Tess', added_on: '2026-10-22' },
    ],
    limit: 100,
    can_change: can,
  });

  test('a member sees the switches and the list, with a note, and can change neither', async ({ page }) => {
    await page.route('**/api/v1/privacy/switches', (route) => route.fulfill({ json: SWITCHES(false) }));
    await page.route('**/api/v1/privacy/own-network', (route) => route.fulfill({ json: LIST(false) }));
    await page.goto('/settings/privacy');
    await expect(page.getByRole('switch', { name: IMPORT })).toBeChecked();
    await expect(page.getByRole('switch', { name: IMPORT })).toBeDisabled();
    await expect(page.getByRole('switch', { name: PHOTOS })).toBeDisabled();
    await expect(
      page.getByText('Only an admin can change these, because they decide what Mealwright may contact.').first(),
    ).toBeVisible();
    await expect(page.getByText('wiki.home.example', { exact: true })).toBeVisible();
    await expect(page.getByRole('button', { name: /^Remove / })).toHaveCount(0);
    await expect(page.getByRole('textbox', { name: ADD })).toHaveCount(0);
    await checkPage(page);
  });

  test('while it loads, it says so', async ({ page }) => {
    let release!: () => void;
    const held = new Promise<void>((done) => (release = done));
    await page.route('**/api/v1/privacy/switches', async (route) => {
      await held;
      await route.fulfill({ json: SWITCHES(true) });
    });
    await page.goto('/settings/privacy');
    await expect(page.getByText('Loading…')).toBeVisible();
    await expect(page.getByRole('switch')).toHaveCount(0);
    await checkPage(page);
    release();
    await expect(page.getByRole('switch', { name: IMPORT })).toBeChecked();
  });

  test('when it can’t be loaded, it says why and Try again looks again', async ({ page }) => {
    let broken = true;
    await page.route('**/api/v1/privacy/switches', (route) =>
      broken
        ? route.fulfill({ status: 500, json: { detail: 'Something went wrong. Try again.' } })
        : route.fulfill({ json: SWITCHES(true) }),
    );
    await page.goto('/settings/privacy');
    await expect(page.getByRole('alert')).toContainText('Something went wrong. Try again.');
    await expect(page.getByRole('switch')).toHaveCount(0);
    await checkPage(page);
    broken = false;
    await page.getByRole('button', { name: 'Try again' }).click();
    await expect(page.getByRole('switch', { name: IMPORT })).toBeChecked();
  });

  test('a switch the server refuses goes back, and says why', async ({ page }) => {
    await page.route('**/api/v1/privacy/switches/recipe_photos', (route) =>
      route.fulfill({
        status: 403,
        json: { detail: 'Only the household’s admin can change this.', code: 'admins_only' },
      }),
    );
    await page.goto('/settings/privacy');
    const photos = page.getByRole('switch', { name: PHOTOS });
    await photos.click();
    await expect(page.getByRole('alert')).toHaveText('Only the household’s admin can change this.');
    await expect(photos).not.toBeChecked();
    await checkPage(page);
  });

  test('offline, it shows what was last loaded and can’t be changed, and says why', async ({ page, context }) => {
    await addViaApi(page, 'wiki.home.example');
    await page.request.put('/api/v1/privacy/switches/recipe_import', { data: { on: true } });
    await page.goto('/settings/privacy');
    await expect(page.getByRole('switch', { name: IMPORT })).toBeChecked();
    await context.setOffline(true);
    await expect(
      page.getByText('You’re offline. This is as it was when you last looked', { exact: false }).first(),
    ).toBeVisible({ timeout: 10_000 });
    await expect(page.getByRole('switch', { name: IMPORT })).toBeChecked();
    await expect(page.getByRole('switch', { name: IMPORT })).toBeDisabled();
    await expect(page.getByRole('switch', { name: PHOTOS })).toBeDisabled();
    await expect(page.getByText('wiki.home.example', { exact: true })).toBeVisible();
    await expect(page.getByRole('button', { name: 'Remove wiki.home.example' })).toBeDisabled();
    await expect(page.getByRole('textbox', { name: ADD })).toBeDisabled();
    await expect(page.getByRole('button', { name: 'Add', exact: true })).toBeDisabled();
    // The whole page is scanned, the offline bar and any toast included.
    await checkPage(page);
    await context.setOffline(false);
    await expect(page.getByRole('switch', { name: IMPORT })).toBeEnabled({ timeout: 20_000 });
  });
});
