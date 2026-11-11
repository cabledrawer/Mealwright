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
  if (isPhone(page)) {
    await page.getByRole('navigation', { name: 'Household settings' }).getByRole('link', { name: /^Your data/ }).click();
  } else {
    await page.getByRole('link', { name: /Backups, export and starting again/ }).click();
  }
  await expect(page).toHaveURL(/\/settings\/your-data$/);
  await expect(page.getByRole('heading', { level: 1, name: 'Your data' })).toBeVisible();
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
  await expect(page.getByRole('heading', { level: 1, name: 'Your data' })).toBeVisible();
});
