import { mkdirSync } from 'node:fs';
import { join } from 'node:path';
import { test, expect, request, type Page } from './clock.ts';

// Settings → Sign-in → API tokens (0.9, O2): an admin makes a token, sees it once, and another
// app uses it with "Authorization: Bearer"; deleting asks first and stops it at once. Against
// the worker's own server, signed in as the admin. The rules a token meets (read only, what it
// can never do, ending, its admin made a member) are in backend/tests/test_api_tokens.py.
// Runs on phone, desktop and WebKit.

const isPhone = () => test.info().project.name.startsWith('phone');

async function openTokens(page: Page) {
  await page.goto('/settings/api-tokens');
  await expect(page.getByRole('heading', { name: 'API tokens', level: 1 })).toBeVisible();
  await expect(page.getByRole('button', { name: 'Make token' })).toBeVisible();
}

/** Make a token on the screen; gives back the token as shown, once. */
async function make(page: Page, name: string, can: 'Read only' | 'Read and change') {
  await page.getByLabel('Name').fill(name);
  await page.getByRole('button', { name: can }).click();
  await page.getByRole('button', { name: 'Make token' }).click();
  const shown = page.getByRole('status', { name: 'Your new token' });
  await expect(shown).toHaveText(/^mw_r[ow]_/);
  return (await shown.textContent())!.trim();
}

test('Settings → Sign-in has the API tokens row, with the count, leading to the list', async ({
  page,
}) => {
  await page.goto('/settings?section=sign-in');
  await expect(page.getByRole('heading', { name: 'For the household (admins)' })).toBeVisible();
  const row = page.getByRole('link', { name: /API tokens/ });
  await expect(row).toBeVisible();
  await expect(page.getByTestId('api-token-count')).toHaveText(/^\d+$/);
  await row.click();
  await expect(page).toHaveURL(/\/settings\/api-tokens$/);
  await expect(page.getByRole('heading', { name: 'API tokens', level: 1 })).toBeVisible();
  // Back to Sign-in.
  await page.getByRole('link', { name: 'Sign-in' }).first().click();
  await expect(page).toHaveURL(/\/settings/);
});

test('a token is shown once, works for another app, and stops when deleted', async ({
  page,
  app,
}) => {
  await openTokens(page);
  const name = `Home Assistant ${test.info().project.name}`;
  const token = await make(page, name, 'Read only');
  expect(token).toMatch(/^mw_ro_[A-Za-z0-9_-]{43}$/);
  await expect(page.getByText('You won’t see this token again.', { exact: false })).toBeVisible();
  await expect(page.getByRole('button', { name: 'Copy' })).toBeVisible();
  const listed = page.getByTestId('api-tokens').getByRole('listitem').filter({ hasText: name });
  await expect(listed).toContainText('Read-only · expires');
  await expect(listed).toContainText('never used');

  await page.getByRole('button', { name: 'Done' }).click();
  await expect(page.getByText(token)).toHaveCount(0);
  await page.reload();
  await expect(page.getByText(name)).toBeVisible();
  await expect(page.getByText(token)).toHaveCount(0);

  // Another app: no cookie, only the token.
  const other = await request.newContext({
    baseURL: app.url,
    extraHTTPHeaders: { Authorization: `Bearer ${token}` },
    // No cookie: the test runner would otherwise give it the admin's saved sign-in.
    storageState: { cookies: [], origins: [] },
  });
  expect((await other.get('/api/v1/me')).status()).toBe(200);
  const write = await other.patch('/api/v1/household', { data: { cook_per_step: true } });
  expect(write.status()).toBe(403);
  expect((await write.json()).code).toBe('read_only_token');
  await page.reload();
  await expect(
    page.getByTestId('api-tokens').getByRole('listitem').filter({ hasText: name }),
  ).toContainText('used just now');

  // Deleting asks first; Keep it keeps it.
  const del = page.getByRole('button', { name: `Delete ${name} token` });
  await del.click();
  const ask = page.getByRole('alertdialog', { name: `Delete the ${name} token?` });
  await expect(ask).toBeVisible();
  await ask.getByRole('button', { name: 'Keep it' }).click();
  await expect(ask).toHaveCount(0);
  expect((await other.get('/api/v1/me')).status()).toBe(200);

  await del.click();
  await ask.getByRole('button', { name: 'Delete', exact: true }).click();
  // The page also says "Deleted <name>." for screen readers, so look at the list.
  await expect(
    page.getByTestId('api-tokens').getByRole('listitem').filter({ hasText: name }),
  ).toHaveCount(0);
  const refused = await other.get('/api/v1/me');
  expect(refused.status()).toBe(401);
  expect((await refused.json()).code).toBe('bad_token');
  await other.dispose();
});

test('a read-and-change token that never expires can change the kitchen', async ({ page, app }) => {
  await openTokens(page);
  await page.getByRole('button', { name: 'Never' }).click();
  const name = `Backup script ${test.info().project.name}`;
  const token = await make(page, name, 'Read and change');
  expect(token.startsWith('mw_rw_')).toBe(true);
  await expect(
    page.getByTestId('api-tokens').getByRole('listitem').filter({ hasText: name }),
  ).toContainText('Full access · never expires · never used');
  await page.getByRole('button', { name: 'Done' }).click();

  const other = await request.newContext({
    baseURL: app.url,
    extraHTTPHeaders: { Authorization: `Bearer ${token}` },
    // No cookie: the test runner would otherwise give it the admin's saved sign-in.
    storageState: { cookies: [], origins: [] },
  });
  // It never makes tokens, nor changes passwords.
  const tokens = await other.get('/api/v1/api-tokens');
  expect(tokens.status()).toBe(403);
  expect((await tokens.json()).code).toBe('not_for_tokens');
  const sessions = await other.delete('/api/v1/me/sessions/others');
  expect(sessions.status()).toBe(403);
  await other.dispose();

  // Tidy up, so the other tests in this worker see their own tokens only.
  await page.getByRole('button', { name: `Delete ${name} token` }).click();
  await page.getByRole('alertdialog').getByRole('button', { name: 'Delete', exact: true }).click();
  await expect(
    page.getByTestId('api-tokens').getByRole('listitem').filter({ hasText: name }),
  ).toHaveCount(0);
});

test('fits the screen, and touch targets are 44 px', async ({ page }) => {
  await openTokens(page);
  const width = page.viewportSize()!.width;
  const scroll = await page.evaluate(() => document.documentElement.scrollWidth);
  expect(scroll).toBeLessThanOrEqual(width);
  for (const name of ['Read only', 'Read and change', 'Never', '30 days', '1 year', 'Pick a date']) {
    const box = (await page.getByRole('button', { name, exact: true }).boundingBox())!;
    expect(box.height, name).toBeGreaterThanOrEqual(44);
  }
  if (isPhone()) {
    await page.getByRole('button', { name: 'Pick a date' }).click();
    await expect(page.getByLabel('Last day it works')).toBeVisible();
  }
});

/** Dark screenshots at four widths for the review, only when E2E_SHOTS_DIR is set (by hand). */
test('screenshots, dark (by hand only)', async ({ page, app }) => {
  const dir = process.env.E2E_SHOTS_DIR;
  test.skip(!dir || !test.info().project.name.startsWith('desktop'), 'by hand, desktop project');
  mkdirSync(dir!, { recursive: true });
  await page.emulateMedia({ colorScheme: 'dark' });
  const shot = async (screen: string, open: () => Promise<void>) => {
    for (const width of [428, 768, 1100, 1300]) {
      await page.setViewportSize({ width, height: 900 });
      await open();
      await page.screenshot({ path: join(dir!, `${screen}-${width}.png`), fullPage: true });
    }
  };
  for (const [name, scope] of [
    ['Home Assistant', 'read'],
    ['Backup script', 'full'],
  ]) {
    const response = await page.request.post('/api/v1/api-tokens', {
      data: { name, scope, expires_on: null },
    });
    expect(response.status(), await response.text()).toBe(201);
    if (scope === 'read') {
      // One that has been used, so the list shows both "used" and "never used".
      const other = await request.newContext({
        baseURL: app.url,
        extraHTTPHeaders: { Authorization: `Bearer ${(await response.json()).token}` },
        storageState: { cookies: [], origins: [] },
      });
      await other.get('/api/v1/me');
      await other.dispose();
    }
  }
  await shot('settings-signin', async () => {
    await page.goto('/settings?section=sign-in');
    await expect(page.getByTestId('api-token-count')).toBeVisible();
  });
  await shot('api-tokens', () => openTokens(page));
  await shot('api-tokens-ask', async () => {
    await openTokens(page);
    await page.getByRole('button', { name: 'Delete Home Assistant token' }).click();
    await expect(page.getByRole('alertdialog')).toBeVisible();
  });
  await shot('api-tokens-shown', async () => {
    await openTokens(page);
    await page.getByLabel('Name').fill('Shopping widget');
    await page.getByRole('button', { name: 'Make token' }).click();
    await expect(page.getByRole('status', { name: 'Your new token' })).toHaveText(/^mw_r/);
  });
  // Tidy up: this worker's other tests count the tokens.
  const list = await (await page.request.get('/api/v1/api-tokens')).json();
  for (const t of list.tokens as { id: number }[]) {
    await page.request.delete(`/api/v1/api-tokens/${t.id}`);
  }
});
