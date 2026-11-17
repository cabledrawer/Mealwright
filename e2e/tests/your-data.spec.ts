import { mkdirSync } from 'node:fs';
import { join } from 'node:path';
import { test, expect, type Page } from './clock.ts';
import { checkPage, isPhone, setAccountTheme } from './a11y.ts';

// Settings → Your data (0.9, D1), against the real server, signed in as the test admin: the
// page from Settings, How often and Keep sent and kept, Back up now, the export download, How to
// restore, and Delete everything's guard (the words, then a wrong password). Delete everything
// itself is not run here: it would empty this worker's server under the other tests. The
// server's own tests (backend/tests/test_delete_everything.py) delete for real. A member's view
// is in the unit test (page.test.ts): the app has no way to add a member until H1.
// Runs in the "phone 0.9 your data", "desktop 0.9 your data" and "webkit 0.9 your data" projects.

async function openFromSettings(page: Page) {
  await page.goto('/settings');
  // The list is the phone's page and, on a computer, sits beside the page (F252).
  await page.getByRole('link', { name: /^Backups & your data/ }).first().click();
  await expect(page).toHaveURL(/\/settings\/your-data$/);
  await expect(page.getByRole('heading', { level: 1, name: 'Backups & your data' })).toBeVisible();
}

test.beforeEach(async ({ page }) => {
  await setAccountTheme(page, 'auto');
});

test('Your data opens from Settings, shows the backups, and passes the accessibility checks', async ({ page }) => {
  await openFromSettings(page);
  await expect(page.getByLabel('How often')).toHaveValue('daily');
  await expect(page.getByLabel('Keep')).toHaveValue('7');
  await expect(page.getByText(/^Backups sit on the same disk as Mealwright/)).toBeVisible();
  await expect(page.getByText('Undo reaches back 7 days.')).toBeVisible();
  await expect(page.getByRole('link', { name: 'Delete everything…' })).toBeVisible();
  await checkPage(page);
});

test('an admin changes how often and how many; it is kept, and put back', async ({ page }) => {
  await page.goto('/settings/your-data');
  const saved = (method: string) =>
    page.waitForResponse((r) => r.url().endsWith('/api/v1/backups') && r.request().method() === method);
  try {
    let done = saved('PATCH');
    await page.getByLabel('How often').selectOption('weekly');
    expect((await done).status()).toBe(200);
    done = saved('PATCH');
    await page.getByLabel('Keep').selectOption('14');
    expect((await done).status()).toBe(200);
    await page.reload();
    await expect(page.getByLabel('How often')).toHaveValue('weekly');
    await expect(page.getByLabel('Keep')).toHaveValue('14');
  } finally {
    const back = await page.request.patch('/api/v1/backups', { data: { every: 'daily', keep: 7 } });
    expect(back.status(), await back.text()).toBe(200);
  }
});

test('Back up now makes a backup and says all fine', async ({ page }) => {
  await page.goto('/settings/your-data');
  await page.getByRole('button', { name: 'Back up now' }).click();
  await expect(page.getByTestId('last-backup')).toHaveText(/^Today \d\d:\d\d · [\d.]+\s(bytes|KB|MB) · all fine$/);
  await expect(page.getByRole('button', { name: 'Back up now' })).toBeEnabled();
});

test('Export downloads everything as one file', async ({ page }) => {
  await page.goto('/settings/your-data');
  const download = page.waitForEvent('download');
  await page.getByRole('link', { name: 'Export' }).click();
  expect((await download).suggestedFilename()).toMatch(/^mealwright-export-\d{4}-\d\d-\d\d\.zip$/);
});

test('Export with a password saves an encrypted file, under the page\'s own security rules', async ({ page }) => {
  const refused: string[] = [];
  page.on('console', (message) => {
    if (/content security policy|refused to/i.test(message.text())) refused.push(message.text());
  });
  await page.goto('/settings/your-data');
  await page.getByLabel('Password (optional)').fill('noor and lorna 2026');
  const download = page.waitForEvent('download');
  await page.getByRole('button', { name: 'Export' }).click();
  const saved = await download;
  expect(saved.suggestedFilename()).toMatch(/^mealwright-export-\d{4}-\d\d-\d\d\.zip\.mwenc$/);
  const path = await saved.path();
  const { readFileSync } = await import('node:fs');
  const bytes = readFileSync(path);
  expect(bytes.subarray(0, 8).toString('latin1')).toBe('MWEXPORT');
  expect(bytes.includes(Buffer.from('mealwright-export.json'))).toBe(false);
  await expect(page.getByLabel('Password (optional)')).toHaveValue('');
  expect(refused).toEqual([]);
});

test('a password that is too short is refused on the page and nothing is saved', async ({ page }) => {
  await page.goto('/settings/your-data');
  await page.getByLabel('Password (optional)').fill('short');
  await page.getByRole('button', { name: 'Export' }).click();
  await expect(page.getByRole('alert')).toHaveText('Use a password of 8 to 1,024 characters.');
});

test('How to restore has the steps, and goes back to Your data', async ({ page }) => {
  await page.goto('/settings/your-data');
  await page.getByRole('link', { name: /How to restore/ }).click();
  await expect(page.getByRole('heading', { level: 1, name: 'How to restore' })).toBeVisible();
  await expect(page.getByRole('heading', { name: 'On the same server' })).toBeVisible();
  await checkPage(page, { themes: ['dark'] });
});

test('Delete everything waits for the words, and a wrong password deletes nothing', async ({ page }) => {
  await page.goto('/settings/your-data');
  await page.getByRole('link', { name: 'Delete everything…' }).click();
  await expect(page.getByRole('heading', { level: 1, name: 'Delete everything?' })).toBeVisible();
  const button = page.getByRole('button', { name: 'Delete everything' });
  await expect(button).toBeDisabled();
  await page.getByLabel(/to confirm/).fill('delete everything');
  await expect(button).toBeDisabled();
  await page.getByLabel('Your password').fill('not the password');
  await expect(button).toBeEnabled();
  await checkPage(page);
  await button.click();
  await expect(page.getByRole('alert')).toHaveText('That password isn’t right.');
  await expect(page.getByLabel('Your password')).toHaveValue('');
  // Nothing was deleted: still signed in, and Settings still opens.
  await page.goto('/settings/your-data');
  await expect(page.getByRole('heading', { level: 1, name: 'Backups & your data' })).toBeVisible();
});

// An admin who signs in only with single sign-on (0.9.5 D3): no password to type, so they
// confirm at the sign-in server. The answer that says so is made here (page.route); the
// server's side, with a real fresh sign-in, is in backend/tests/test_sso_confirm_delete.py.
const SSO_WAY = { confirm_with: 'single_sign_on', confirmed: false };

function confirmWith(page: Page, answer: object) {
  return page.route('**/api/v1/delete-everything', (route) =>
    route.request().method() === 'GET'
      ? route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(answer) })
      : route.continue(),
  );
}

test('Delete everything for a single sign-on admin asks to confirm at the sign-in server, not for a password', async ({ page }) => {
  await confirmWith(page, SSO_WAY);
  await page.goto('/settings/your-data/delete');
  await expect(page.getByRole('heading', { level: 1, name: 'Delete everything?' })).toBeVisible();
  await expect(page.getByLabel('Your password')).toHaveCount(0);
  await expect(page.getByText(/^You sign in with single sign-on, so confirm at your sign-in server/)).toBeVisible();
  await expect(page.getByRole('button', { name: 'Confirm at your sign-in server' })).toBeVisible();
  await page.getByLabel(/to confirm/).fill('delete everything');
  // The words alone aren't enough: the confirmation at the sign-in server comes first.
  await expect(page.getByRole('button', { name: 'Delete everything', exact: true })).toBeDisabled();
  await checkPage(page);
});

test('once confirmed at the sign-in server, the words are all that is left', async ({ page }) => {
  await confirmWith(page, { ...SSO_WAY, confirmed: true });
  await page.goto('/settings/your-data/delete');
  await expect(page.getByRole('status').filter({ hasText: 'Confirmed at your sign-in server. Delete within 10 minutes.' })).toBeVisible();
  const button = page.getByRole('button', { name: 'Delete everything', exact: true });
  await expect(button).toBeDisabled();
  await page.getByLabel(/to confirm/).fill('delete everything');
  await expect(button).toBeEnabled();
});

test('screenshots, dark (by hand only)', async ({ page }) => {
  test.skip(!process.env.E2E_SHOTS_DIR || !test.info().project.name.startsWith('desktop'), 'by hand, desktop project');
  const dir = process.env.E2E_SHOTS_DIR!;
  mkdirSync(dir, { recursive: true });
  await page.emulateMedia({ colorScheme: 'dark' });
  await confirmWith(page, SSO_WAY);
  for (const width of [428, 768, 1100, 1300]) {
    await page.setViewportSize({ width, height: 900 });
    await page.goto('/settings/your-data/delete');
    await expect(page.getByRole('button', { name: 'Confirm at your sign-in server' })).toBeVisible();
    await page.screenshot({ path: join(dir, `delete-everything-sso-${width}.png`), fullPage: true });
  }
});

test('screenshots of the export password, dark (by hand only)', async ({ page }) => {
  test.skip(!process.env.E2E_SHOTS_DIR || !test.info().project.name.startsWith('desktop'), 'by hand, desktop project');
  const dir = process.env.E2E_SHOTS_DIR!;
  mkdirSync(dir, { recursive: true });
  await page.emulateMedia({ colorScheme: 'dark' });
  for (const width of [428, 768, 1100, 1300]) {
    await page.setViewportSize({ width, height: 900 });
    await page.goto('/settings/your-data');
    await page.getByLabel('Password (optional)').fill('noor and lorna');
    await page.locator('#export').scrollIntoViewIfNeeded();
    await page.screenshot({ path: join(dir, `your-data-export-${width}.png`), fullPage: true });
    await page.getByLabel('Password (optional)').fill('short');
    await page.getByRole('button', { name: 'Export' }).click();
    await expect(page.getByRole('alert')).toBeVisible();
    await page.screenshot({ path: join(dir, `your-data-export-too-short-${width}.png`), fullPage: true });
  }
});

// R6: keeping fewer backups than there are asks for the password first. The count is stood in
// for (the server's own tests make real backups and delete them), so nothing is deleted here.
async function pretendThereAreFour(page: Page, count = 4) {
  await page.route('**/api/v1/backups', async (route) => {
    if (route.request().method() !== 'GET') return route.continue();
    const response = await route.fetch();
    await route.fulfill({ response, json: { ...(await response.json()), count } });
  });
}

test('lowering Keep so that backups go asks for the password, and Cancel changes nothing', async ({ page }) => {
  await pretendThereAreFour(page);
  const sent: string[] = [];
  page.on('request', (request) => {
    if (request.method() === 'PATCH' && request.url().endsWith('/api/v1/backups')) sent.push(request.postData() ?? '');
  });
  await page.goto('/settings/your-data');
  await page.getByLabel('Keep').selectOption('2');
  await expect(page.getByText('This deletes the 2 oldest backups.')).toBeVisible();
  await expect(page.getByLabel('Your password')).toBeVisible();
  await expect(page.getByRole('button', { name: 'Keep fewer backups' })).toBeDisabled();
  await checkPage(page);
  expect(sent).toEqual([]);
  await page.getByRole('button', { name: 'Cancel' }).click();
  await expect(page.getByLabel('Keep')).toHaveValue('7');
  await expect(page.getByLabel('Your password')).toHaveCount(0);
  expect(sent).toEqual([]);
});

test('Back up now at a full folder asks for the password first, and Cancel makes nothing', async ({ page }) => {
  await pretendThereAreFour(page, 7);
  const sent: string[] = [];
  page.on('request', (request) => {
    if (request.method() === 'POST' && request.url().endsWith('/api/v1/backups')) sent.push(request.postData() ?? '');
  });
  await page.goto('/settings/your-data');
  await page.getByRole('button', { name: 'Back up now' }).click();
  await expect(page.getByText('This replaces the oldest backup.')).toBeVisible();
  await expect(page.getByLabel('Your password')).toBeVisible();
  await checkPage(page);
  expect(sent).toEqual([]);
  await page.getByRole('button', { name: 'Cancel' }).click();
  await expect(page.getByLabel('Your password')).toHaveCount(0);
  expect(sent).toEqual([]);
});

/** Dark screenshots at four widths for the review, only when E2E_SHOTS_DIR is set (by hand). */
test('screenshot of the Keep box, dark (by hand only)', async ({ page }) => {
  const dir = process.env.E2E_SHOTS_DIR;
  test.skip(!dir || !test.info().project.name.startsWith('desktop'), 'by hand, desktop project');
  mkdirSync(dir!, { recursive: true });
  await page.emulateMedia({ colorScheme: 'dark' });
  await pretendThereAreFour(page);
  for (const width of [428, 768, 1100, 1300]) {
    await page.setViewportSize({ width, height: 900 });
    await page.goto('/settings/your-data');
    await page.getByLabel('Keep').selectOption('2');
    await expect(page.getByLabel('Your password')).toBeVisible();
    await page.screenshot({ path: join(dir!, `your-data-keep-${width}.png`), fullPage: true });
  }
});

test('screenshot of the Back up now box, dark (by hand only)', async ({ page }) => {
  const dir = process.env.E2E_SHOTS_DIR;
  test.skip(!dir || !test.info().project.name.startsWith('desktop'), 'by hand, desktop project');
  mkdirSync(dir!, { recursive: true });
  await page.emulateMedia({ colorScheme: 'dark' });
  await pretendThereAreFour(page, 7);
  for (const width of [428, 768, 1100, 1300]) {
    await page.setViewportSize({ width, height: 900 });
    await page.goto('/settings/your-data');
    await page.getByRole('button', { name: 'Back up now' }).click();
    await expect(page.getByLabel('Your password')).toBeVisible();
    await page.screenshot({ path: join(dir!, `your-data-backup-now-${width}.png`), fullPage: true });
  }
});
