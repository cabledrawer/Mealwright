import { test, expect, request, testNow, type Page } from './clock.ts';
import { ADMIN, PORTS, insecure, local } from './servers.ts';

// Signing in, first-run setup, signing out, and the plain http:// rules (spec
// section 7; Sign in and Onboarding in "Layout decisions"). Runs on a desktop-sized
// browser with no saved session.

const SECURE_NEEDED =
  'Signing in needs a secure connection. Open Mealwright at its https:// address, through your reverse proxy.';
const PLAIN_WARNING =
  "This connection isn’t secure. Passwords travel unencrypted. Use only for testing on a network you trust.";

const heading = (page: Page) => page.getByRole('heading', { level: 1 });

async function signIn(page: Page, password = ADMIN.password) {
  await page.getByLabel('Username').fill(ADMIN.username);
  await page.getByLabel('Password', { exact: true }).fill(password);
  await page.getByRole('button', { name: 'Sign in' }).click();
}

test.describe('first run', () => {
  test.use({ baseURL: local(PORTS.fresh) });

  test('the first person creates the admin account, then lands on Today', async ({ page }) => {
    // Any page leads to setup while there's no account yet.
    await page.goto('/pantry');
    await expect(page).toHaveURL('/setup');
    await expect(heading(page)).toHaveText('Welcome! First, your account');
    await expect(page.getByRole('link', { name: /skip/i })).toHaveCount(0);

    // Says what's missing before asking the server.
    await page.getByRole('button', { name: 'Create account' }).click();
    await expect(page.getByLabel('Your name')).toBeFocused();
    await expect(page.getByText('Enter your name.')).toBeVisible();
    await expect(page.getByText('Choose a username.')).toBeVisible();
    await expect(page.getByText('Use at least 10 characters.')).toBeVisible();

    await page.getByLabel('Your name').fill(ADMIN.name);
    await page.getByLabel('Username').fill('Not Allowed!');
    await page.getByLabel('Password', { exact: true }).fill('short');
    await expect(
      page.getByText('Use up to 50 lowercase letters, numbers, dots, dashes or underscores.'),
    ).toBeVisible();
    await expect(page.getByLabel('Username')).toHaveAttribute('aria-invalid', 'true');

    // Show reveals the password while typing.
    await page.getByRole('button', { name: 'Show password' }).click();
    await expect(page.getByLabel('Password', { exact: true })).toHaveAttribute('type', 'text');
    await page.getByRole('button', { name: 'Hide password' }).click();
    await expect(page.getByLabel('Password', { exact: true })).toHaveAttribute('type', 'password');

    await page.getByLabel('Username').fill('Tess'); // stored in lowercase
    await page.getByLabel('Password', { exact: true }).fill(ADMIN.password);
    await page.getByRole('button', { name: 'Create account' }).click();

    await expect(page).toHaveURL('/');
    await expect(heading(page)).toHaveText('Today');
    await expect(page.getByRole('link', { name: 'Tess · Settings' }).first()).toBeVisible();

    // Setup works only once.
    await page.goto('/setup');
    await expect(page).toHaveURL('/');
  });
});

test.describe('signing in', () => {
  test('goes back to the page you were heading for', async ({ page }) => {
    await page.goto('/pantry');
    await expect(page).toHaveURL('/sign-in?next=%2Fpantry');
    await expect(heading(page)).toHaveText('Welcome back');
    await expect(page.getByText(PLAIN_WARNING)).toHaveCount(0); // 127.0.0.1 counts as secure
    await signIn(page);
    await expect(page).toHaveURL('/pantry');
    await expect(heading(page)).toHaveText('Pantry');
  });

  test('a wrong password says so, and clears the password', async ({ page }) => {
    await page.goto('/sign-in');
    await signIn(page, 'not-the-password');
    await expect(page.getByRole('alert')).toHaveText("That username and password don’t match.");
    await expect(page.getByLabel('Password', { exact: true })).toHaveValue('');
    await expect(page).toHaveURL('/sign-in');
  });

  test('shows the server’s reason as it is', async ({ page }) => {
    await page.route('**/api/v1/session', (route) =>
      route.fulfill({
        status: 429,
        contentType: 'application/json',
        body: JSON.stringify({ detail: 'Too many tries. Wait 2 minutes.' }),
      }),
    );
    await page.goto('/sign-in');
    await signIn(page);
    await expect(page.getByRole('alert')).toHaveText('Too many tries. Wait 2 minutes.');
  });

  test('"Remember this computer" keeps you signed in for 30 days', async ({ page, context }) => {
    await page.goto('/sign-in');
    const remember = page.getByRole('switch', { name: 'Remember this computer' });
    await expect(remember).toHaveAttribute('aria-checked', 'true');
    // "for 30 days" is the small text under it (section 11, ruling 2 of the word list).
    await expect(remember).toHaveAccessibleDescription('for 30 days');
    await expect(page.getByText('Stay signed in')).toHaveCount(0);
    await signIn(page);
    await expect(heading(page)).toHaveText('Today');
    const [cookie] = await context.cookies();
    const days = (cookie!.expires - Date.now() / 1000) / 86400;
    expect(days).toBeGreaterThan(29);
    expect(cookie).toMatchObject({ httpOnly: true, sameSite: 'Lax' });
  });

  test('without "Remember", the session ends with the browser', async ({ page, context }) => {
    await page.goto('/sign-in');
    await page.getByRole('switch', { name: 'Remember this computer' }).click();
    await signIn(page);
    await expect(heading(page)).toHaveText('Today');
    const [cookie] = await context.cookies();
    expect(cookie!.expires).toBe(-1);
  });

  test('a signed-in person going to sign in goes straight on', async ({ page }) => {
    await page.goto('/sign-in');
    await signIn(page);
    await expect(heading(page)).toHaveText('Today');
    await page.goto('/sign-in?next=%2Fplan');
    await expect(page).toHaveURL('/plan');
  });

  test('never sends you to another site afterwards', async ({ page }) => {
    await page.goto('/sign-in?next=%2F%2Fevil.example%2F');
    await signIn(page);
    await expect(page).toHaveURL('/');
  });

  test('a wipe that couldn’t delete the offline copy: the form is disabled until Try again has (cabledrawer 18 Oct)', async ({
    page,
  }) => {
    // A wipe before this reload couldn't delete the phone database: its flag says so (sync
    // protocol section 12). Nothing else is needed: Try again then deletes what's there.
    await page.goto('/sign-in');
    await page.evaluate(() => localStorage.setItem('mealwright.wipe-pending', 'failed'));
    await page.reload();
    await expect(page.getByRole('status')).toHaveText(
      "This computer couldn’t delete its offline copy of the household. Nobody can sign in on it until that’s done. Close other Mealwright tabs or restart the browser, then Try again.",
    );
    const form = [
      page.getByLabel('Username'),
      page.getByLabel('Password', { exact: true }),
      page.getByRole('switch', { name: 'Remember this computer' }),
      page.getByRole('button', { name: 'Sign in' }),
    ];
    for (const control of form) await expect(control).toBeDisabled();
    // Only Try again works. Once it has deleted it, the message goes and the form comes back.
    await page.getByRole('button', { name: 'Try again' }).click();
    await expect(page.getByText(/couldn’t delete/)).toHaveCount(0);
    for (const control of form) await expect(control).toBeEnabled();
    expect(await page.evaluate(() => localStorage.getItem('mealwright.wipe-pending'))).toBeNull();
    await signIn(page);
    await expect(heading(page)).toHaveText('Today');
  });

  test('on a phone, it says "Remember this phone"', async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    await page.goto('/sign-in');
    await expect(page.getByRole('switch', { name: 'Remember this phone' })).toBeVisible();
    await expect(page.getByRole('switch', { name: 'Remember this phone' })).toHaveAccessibleDescription(
      'for 30 days',
    );
    const sideways = await page.evaluate(
      () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
    );
    expect(sideways).toBeLessThanOrEqual(0);
  });
});

test.describe('signed in', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/sign-in');
    await signIn(page);
    await expect(heading(page)).toHaveText('Today');
  });

  test.afterEach(async ({ page }) => {
    await page.request.put('/api/v1/me/preferences', { data: { theme: 'auto' } });
  });

  test('Sign out (in Settings) returns to sign in', async ({ page }) => {
    await page.getByRole('link', { name: 'Tess · Settings' }).click();
    await expect(page.getByText('Signed in as tess')).toBeVisible();
    await page.getByRole('button', { name: 'Sign out' }).click();
    await expect(page).toHaveURL('/sign-in');
    await page.goto('/plan');
    await expect(page).toHaveURL('/sign-in?next=%2Fplan');
  });

  test('the theme is saved to your account and follows you to another device', async ({
    page,
    browser,
    app,
  }) => {
    await page
      .getByRole('complementary', { name: 'Sidebar' })
      .getByRole('button', { name: 'Dark' })
      .click();
    await expect.poll(async () => (await (await page.request.get('/api/v1/me')).json()).theme).toBe(
      'dark',
    );

    // Another browser, which has never seen Mealwright, signs in and gets Dark.
    const other = await browser.newContext({ baseURL: app.url, colorScheme: 'light' });
    await other.clock.install({ time: testNow() });
    const second = await other.newPage();
    await second.goto('/sign-in');
    await expect(second.locator('html')).toHaveAttribute('data-theme', 'light');
    await signIn(second);
    await expect(heading(second)).toHaveText('Today');
    await expect(second.locator('html')).toHaveAttribute('data-theme', 'dark');
    await other.close();
  });

  test('when the session ends, the next action leads to sign in, then back', async ({
    page,
    context,
  }) => {
    await page.getByRole('link', { name: 'Plan', exact: true }).click();
    await expect(heading(page)).toHaveText('Plan');
    // The plan loads after its heading shows; wait for it, so the click below is the next action.
    await expect(page.getByRole('group', { name: 'Week plan' })).toBeVisible();
    await context.clearCookies(); // as if the session had expired
    await page
      .getByRole('complementary', { name: 'Sidebar' })
      .getByRole('button', { name: 'Light' })
      .click();
    await expect(page).toHaveURL('/sign-in?next=%2Fplan');
    await signIn(page);
    await expect(page).toHaveURL('/plan');
  });
});

test.describe('plain http:// on the network', () => {
  test('refused: says so before anyone types a password (first run)', async ({ page }) => {
    await page.goto(`${insecure(PORTS.strict)}/`);
    await expect(page).toHaveURL(`${insecure(PORTS.strict)}/setup`);
    await expect(page.getByRole('alert')).toContainText(SECURE_NEEDED);
    await expect(page.getByLabel('Password', { exact: true })).toHaveCount(0);
    await expect(page.getByRole('button', { name: 'Create account' })).toHaveCount(0);
  });

  test('refused: says so on sign in, and works on a secure address', async ({ page }) => {
    // Set the server up from outside the browser (no Origin header, as a script would).
    const api = await request.newContext({ baseURL: local(PORTS.strict) });
    const created = await api.post('/api/v1/setup', { data: ADMIN });
    expect([201, 409]).toContain(created.status());
    await api.dispose();

    await page.goto(`${insecure(PORTS.strict)}/sign-in`);
    await expect(page.getByRole('alert')).toContainText(SECURE_NEEDED);
    await expect(page.getByLabel('Password', { exact: true })).toHaveCount(0);

    // The server refuses too, with its own explanation, even if a page tried.
    const refused = await page.evaluate(async () => {
      const response = await fetch('/api/v1/session', {
        method: 'POST',
        headers: { 'content-type': 'application/json' },
        body: JSON.stringify({ username: 'tess', password: 'kitchen-secret-2026' }),
      });
      return { status: response.status, body: await response.json() };
    });
    expect(refused.status).toBe(400);
    expect(refused.body.detail).toContain('Signing in needs a secure connection.');

    // 127.0.0.1 is a secure context to the browser, so signing in works there.
    await page.goto(`${local(PORTS.strict)}/sign-in`);
    await expect(page.getByText(SECURE_NEEDED)).toHaveCount(0);
    await signIn(page);
    await expect(page).toHaveURL(`${local(PORTS.strict)}/`);
    await expect(heading(page)).toHaveText('Today');
  });

  test('allowed for testing: a clear warning, and signing in works', async ({ page, app }) => {
    await page.goto(`${app.insecureUrl}/sign-in`);
    await expect(page.getByRole('status')).toHaveText(PLAIN_WARNING);
    await signIn(page);
    await expect(page).toHaveURL(`${app.insecureUrl}/`);
    await expect(heading(page)).toHaveText('Today');
  });
});
