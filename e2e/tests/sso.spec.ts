import { mkdirSync } from 'node:fs';
import { join } from 'node:path';
import { test, expect, type Page } from './clock.ts';

// Single sign-on (0.9 O1): the "Sign in with …" button, the callback page, Settings › Sign-in's
// rows and the setup screen. The sign-in server is a fake one: the requests that would reach it
// (start, finish) are answered here (page.route), as are the setup's answers, so nothing in the
// worker's server changes for the other tests. The server's side, with fake providers, is in
// backend/tests/test_sso.py and test_sso_api.py; real ones in e2e/scripts/sso-providers.mjs.
// Runs on phone, desktop and WebKit.

const isPhone = () => test.info().project.name.startsWith('phone');

const SETUP = {
  issuer: 'https://id.example.org',
  client_id: 'mealwright',
  secret_set: true,
  button_name: 'Authentik',
  redirect_uri: null as string | null,
  group_claim: 'groups',
  group_roles: [
    { group: 'mealwright-admins', role: 'admin' },
    { group: 'family', role: 'member' },
  ],
  anyone_else: 'none',
  make_accounts: true,
  password_sign_in: true,
  admin_linked: false,
  switch_on: true,
  test: null as object | null,
};

function answer(page: Page, path: string, body: unknown, status = 200) {
  return page.route(`**/api/v1${path}`, (route) =>
    route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(body) }),
  );
}

function signInOptions(page: Page, password: boolean, button: string | null = 'Authentik') {
  return answer(page, '/sign-in-options', { password, sso_button: button });
}

/** Dark screenshots at four widths for the review, only when E2E_SHOTS_DIR is set (by hand). */
async function shots(page: Page, screen: string, open: () => Promise<void>) {
  const dir = process.env.E2E_SHOTS_DIR;
  if (!dir || !test.info().project.name.startsWith('desktop')) return;
  mkdirSync(dir, { recursive: true });
  await page.emulateMedia({ colorScheme: 'dark' });
  for (const width of [428, 768, 1100, 1300]) {
    await page.setViewportSize({ width, height: 900 });
    await open();
    await page.screenshot({ path: join(dir, `${screen}-${width}.png`), fullPage: true });
  }
}

test.describe('signed out', () => {
  test.use({ storageState: { cookies: [], origins: [] } });

  test('the button sits under the password form, and goes to the sign-in server with Remember', async ({ page }) => {
    await signInOptions(page, true);
    await page.goto('/sign-in');
    const button = page.getByRole('link', { name: 'Sign in with Authentik' });
    await expect(button).toBeVisible();
    await expect(page.getByLabel('Password', { exact: true })).toBeVisible();
    await expect(page.locator('.or')).toHaveText('or');
    await expect(button).toHaveAttribute('href', '/api/v1/sso/start?remember=false');
    await page.getByRole('switch', { name: /Remember this/ }).click();
    await expect(button).toHaveAttribute('href', '/api/v1/sso/start?remember=true');
  });

  test('with password sign-in off, only the button shows', async ({ page }) => {
    await signInOptions(page, false);
    await page.goto('/sign-in');
    await expect(page.getByRole('link', { name: 'Sign in with Authentik' })).toBeVisible();
    await expect(page.getByLabel('Password', { exact: true })).toHaveCount(0);
    await expect(page.getByLabel('Username')).toHaveCount(0);
    await expect(page.locator('.or')).toHaveCount(0);
    await expect(page.getByRole('switch', { name: /Remember this/ })).toBeVisible();
  });

  test('cancelled at the sign-in server: says so once, with a way back, and leaves no code in the address', async ({ page }) => {
    await signInOptions(page, true);
    // The fake sign-in server sends the browser straight back, cancelled.
    await page.route('**/api/v1/sso/start*', (route) =>
      route.fulfill({ status: 303, headers: { location: '/auth/callback?state=s1&error=access_denied' } }),
    );
    const posted: unknown[] = [];
    await page.route('**/api/v1/sso/finish', (route) => {
      posted.push(route.request().postDataJSON());
      return route.fulfill({
        status: 400,
        contentType: 'application/json',
        body: JSON.stringify({ detail: 'Signing in was cancelled at your sign-in server.', code: 'cancelled' }),
      });
    });
    await page.goto('/sign-in');
    await page.getByRole('link', { name: 'Sign in with Authentik' }).click();
    await expect(page.getByRole('alert')).toHaveText('Signing in was cancelled at your sign-in server.');
    expect(posted).toEqual([{ state: 's1', code: null, error: 'access_denied' }]);
    await expect(page).toHaveURL(/\/auth\/callback$/);
    await page.getByRole('link', { name: 'Back to sign in' }).click();
    await expect(page).toHaveURL(/\/sign-in$/);
  });

  test('a refusal sent back to the sign-in page shows its sentence, never the code', async ({ page }) => {
    await signInOptions(page, true);
    await page.goto('/sign-in?sso=not_let_in');
    await expect(page.getByRole('alert')).toHaveText(
      'Your sign-in server doesn’t put you in a group Mealwright lets in. Ask your household’s admin.',
    );
  });
});

test('the callback signs in once and goes on to the app', async ({ page }) => {
  const me = await (await page.request.get('/api/v1/me')).json();
  let posts = 0;
  await page.route('**/api/v1/sso/finish', (route) => {
    posts += 1;
    return route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ done: 'signed_in', me, test: null }) });
  });
  await page.goto('/auth/callback?state=s2&code=c2');
  await expect(page).not.toHaveURL(/auth\/callback/);
  await expect(page.getByRole('navigation').first()).toBeVisible();
  expect(posts).toBe(1);
});

test('Settings › Sign-in: the Single sign-on row, and password sign-in can’t go off yet', async ({ page }) => {
  await page.goto('/settings?section=sign-in');
  const row = page.getByRole('link', { name: /Single sign-on/ });
  await expect(row).toBeVisible();
  await expect(row).toContainText(isPhone() ? 'Set up on a computer' : 'Not set up');
  const passwords = page.getByRole('switch', { name: 'Password sign-in' });
  await expect(passwords).toBeChecked();
  await expect(passwords).toBeDisabled();
  await expect(
    page.getByText('Password sign-in can only be turned off while an admin can sign in with single sign-on.'),
  ).toBeVisible();
  await shots(page, 'settings-sign-in', async () => {
    await page.goto('/settings?section=sign-in');
    await expect(page.getByRole('switch', { name: 'Password sign-in' })).toBeVisible();
  });
});

test.describe('the setup screen', () => {
  test('a phone says to set it up on a computer, and asks the server nothing', async ({ page }) => {
    test.skip(!isPhone(), 'phones only');
    let asked = false;
    await page.route('**/api/v1/sso/settings', (route) => {
      asked = true;
      return route.continue();
    });
    await page.goto('/settings/sso');
    await expect(page.getByText('Set up on a computer')).toBeVisible();
    expect(asked).toBe(false);
  });

  test('shows the saved setup, never the secret, and saves the groups', async ({ page }) => {
    test.skip(isPhone(), 'set up on a computer');
    const sent: Record<string, unknown>[] = [];
    await page.route('**/api/v1/sso/settings', (route) => {
      if (route.request().method() === 'PUT') {
        const body = route.request().postDataJSON();
        sent.push(body);
        return route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify({ ...SETUP, ...body, client_secret: undefined, redirect_uri: body.redirect_uri }),
        });
      }
      return route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(SETUP) });
    });
    await page.goto('/settings/sso');
    await expect(page.getByLabel('Issuer address')).toHaveValue('https://id.example.org');
    await expect(page.getByLabel('Client secret')).toHaveValue('');
    const origin = new URL(page.url()).origin;
    await expect(page.getByText(`${origin}/auth/callback`, { exact: true })).toBeVisible();
    await expect(page.getByRole('switch', { name: 'Allow password sign-in' })).toBeDisabled();

    await page.getByRole('button', { name: '+ Add a group' }).click();
    await page.getByRole('textbox', { name: 'Group' }).nth(2).fill('guests');
    await page.getByRole('button', { name: 'Save' }).click();
    await expect(page.getByRole('status')).toHaveText('Saved.');
    expect(sent).toHaveLength(1);
    expect(sent[0]).toMatchObject({
      issuer: 'https://id.example.org',
      client_secret: '',
      redirect_uri: `${origin}/auth/callback`,
      group_roles: [
        { group: 'mealwright-admins', role: 'admin' },
        { group: 'family', role: 'member' },
        { group: 'guests', role: 'member' },
      ],
      anyone_else: 'none',
    });
  });

  test('screenshots, dark (by hand only)', async ({ page }) => {
    test.skip(!process.env.E2E_SHOTS_DIR || !test.info().project.name.startsWith('desktop'), 'by hand, desktop project');
    await answer(page, '/sso/settings', { ...SETUP, redirect_uri: null });
    await shots(page, 'sso-setup', async () => {
      await page.goto('/settings/sso');
      await expect(page.getByRole('heading', { level: 1 })).toBeVisible();
      await expect(page.getByText(/Set up on a computer|Your sign-in server/).first()).toBeVisible();
    });
    const context = await page.context().browser()!.newContext({ baseURL: new URL(page.url()).origin, colorScheme: 'dark' });
    const out = await context.newPage();
    await signInOptions(out, true);
    await shots(out, 'sign-in', async () => {
      await out.goto('/sign-in');
      await expect(out.getByRole('link', { name: 'Sign in with Authentik' })).toBeVisible();
    });
    await out.unroute('**/api/v1/sign-in-options');
    await signInOptions(out, false);
    await shots(out, 'sign-in-sso-only', async () => {
      await out.goto('/sign-in');
      await expect(out.getByRole('link', { name: 'Sign in with Authentik' })).toBeVisible();
    });
    await context.close();
  });
});
