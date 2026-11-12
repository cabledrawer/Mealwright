import { test, expect, type Browser, type Page } from './clock.ts';
import { checkPage, isPhone, setAccountTheme } from './a11y.ts';

// Settings → Household (0.9 A1): the household's people, the Person screen, giving someone a
// login (sign-in link → choose a password → sign in), removing someone and Undo, and "Who's this?"
// on a shared login, against the real server, signed in as the test admin. Every test removes the
// people it added, so the Plan's "Who's eating" on this worker's server is as it was.
// Runs in the "phone 0.9 household", "desktop 0.9 household" and "webkit 0.9 household" projects.

type Json = Record<string, any>; // eslint-disable-line @typescript-eslint/no-explicit-any

const key = () => ({ 'idempotency-key': crypto.randomUUID() });
/** A short mark of its own for each test and project, so names and usernames never clash. */
const mark = () => `${test.info().project.name.split(' ')[0].slice(0, 1)}${Date.now().toString(36).slice(-5)}`;
const PASSWORD = 'a-long-kitchen-password';

async function addPerson(page: Page, name: string, extra: Json = {}) {
  const response = await page.request.post('/api/v1/people', { data: { name, ...extra }, headers: key() });
  expect(response.status(), await response.text()).toBe(201);
  const found = (await response.json()) as Json;
  return found.people.find((p: Json) => p.name === name) as Json;
}

/** A person with a login and their own password, as if they had used their sign-in link. */
async function personWhoSignsIn(page: Page, name: string, username: string, extra: Json = {}) {
  const made = await addPerson(page, name);
  const link = await page.request.post(`/api/v1/people/${made.id}/login`, {
    data: { username, role: 'member' },
    headers: key(),
  });
  expect(link.status(), await link.text()).toBe(201);
  const path = ((await link.json()) as Json).path as string;
  const joined = await page.request.post(`/api/v1${path}`, { data: { password: PASSWORD } });
  expect(joined.status(), await joined.text()).toBe(204);
  if (Object.keys(extra).length) {
    const changed = await page.request.patch(`/api/v1/people/${made.id}`, { data: extra, headers: key() });
    expect(changed.status(), await changed.text()).toBe(200);
  }
  return made;
}

/** Everyone but the admin goes, and the "Who's this?" switch goes off. */
async function tidy(page: Page) {
  const found = (await (await page.request.get('/api/v1/people')).json()) as Json;
  for (const person of found.people as Json[]) {
    if (person.is_me) continue;
    const gone = await page.request.delete(`/api/v1/people/${person.id}`, { headers: key() });
    expect(gone.ok(), await gone.text()).toBe(true);
  }
  if (found.ask_whos_this) {
    await page.request.put('/api/v1/people/ask-whos-this', { data: { on: false }, headers: key() });
  }
}

/** A second browser, signed out, the same size as this project's. */
async function anotherBrowser(browser: Browser, baseURL: string) {
  const use = test.info().project.use;
  return browser.newContext({
    baseURL,
    viewport: use.viewport,
    hasTouch: use.hasTouch,
    isMobile: use.browserName === 'chromium' ? use.isMobile : undefined,
    userAgent: use.userAgent,
    deviceScaleFactor: use.deviceScaleFactor,
  });
}

async function signIn(page: Page, username: string) {
  await page.goto('/sign-in');
  await page.getByLabel('Username').fill(username);
  await page.getByLabel('Password', { exact: true }).fill(PASSWORD);
  await page.getByRole('button', { name: 'Sign in' }).click();
  await expect(page).not.toHaveURL(/\/sign-in/);
}

const peopleList = (page: Page) => page.getByRole('list', { name: 'People' });

test.beforeEach(async ({ page }) => {
  await setAccountTheme(page, 'auto');
  await tidy(page);
});

test.afterEach(async ({ page }) => {
  await tidy(page);
});

test('the Settings row opens Household; add a person, who opens to choose their colour and portion; Save shows them in the list', async ({
  page,
}) => {
  const name = `Joss ${mark()}`;
  await page.goto('/settings');
  if (isPhone(page)) {
    await expect(page.getByRole('link', { name: /^Household/ })).toContainText('1 person');
    await page.getByRole('link', { name: /^Household/ }).click();
  } else {
    await page.getByRole('navigation', { name: 'Settings sections' }).getByRole('button', { name: 'Household' }).click();
    await page.getByRole('region', { name: 'Household', exact: true }).getByRole('link', { name: /People/ }).click();
  }
  await expect(page).toHaveURL('/settings/household');
  await expect(page.getByRole('heading', { level: 1, name: 'Household' })).toBeVisible();
  await expect(peopleList(page).getByRole('link')).toHaveCount(1);
  await expect(peopleList(page).getByRole('link').first()).toContainText('Tess (you)');
  await expect(page.getByRole('switch', { name: 'Ask “Who’s this?”' })).toHaveAttribute('aria-checked', 'false');
  await checkPage(page);

  await page.getByRole('button', { name: '+ Add a person' }).click();
  await expect(page.getByLabel('Name', { exact: true })).toBeFocused();
  await page.getByLabel('Name', { exact: true }).fill(name);
  await page.getByRole('button', { name: 'Add', exact: true }).click();
  await expect(page.getByRole('heading', { level: 1, name })).toBeVisible();
  await expect(page).toHaveURL(/\/settings\/household\/\d+$/);
  await checkPage(page);

  await page.getByRole('button', { name: 'Violet' }).click();
  await expect(page.getByRole('button', { name: 'Violet' })).toHaveAttribute('aria-pressed', 'true');
  await page.getByRole('button', { name: '½ portion', exact: true }).click();
  await expect(page.getByRole('button', { name: '½ portion', exact: true })).toHaveAttribute('aria-pressed', 'true');
  await page.getByRole('button', { name: 'Save' }).click();
  await expect(page).toHaveURL('/settings/household');
  const row = peopleList(page).getByRole('link', { name: new RegExp(name) });
  await expect(row).toContainText('Profile only · ½ portion');
  expect(
    ((await (await page.request.get('/api/v1/people')).json()) as Json).people.find((p: Json) => p.name === name),
  ).toMatchObject({ colour: 'violet', portion_quarters: 2 });
});

test('give a login: the sign-in link opens "Choose a password", which then lets them sign in; the link works once', async ({
  page,
  browser,
  app,
}) => {
  const m = mark();
  const name = `Rafe ${m}`;
  const username = `rafe.${m}`;
  const made = await addPerson(page, name);
  await page.goto(`/settings/household/${made.id}`);
  await page.getByRole('button', { name: 'Give a login' }).click();
  await expect(page.getByLabel('Username')).toHaveValue(`rafe.${m.toLowerCase()}`);
  await page.getByLabel('Username').fill(username);
  await page.getByRole('button', { name: 'Make the sign-in link' }).click();
  const made_ = page.getByRole('status').filter({ hasText: 'Sign-in link made.' });
  await expect(made_).toContainText(`It works once, for 24 hours: send it to ${name} to choose a password.`);
  await expect(page.getByRole('button', { name: 'Copy the link' })).toBeVisible();
  await checkPage(page);
  const link = (await made_.locator('.mono').textContent())!.trim();
  expect(link).toMatch(/\/join\/[\w-]+$/);
  const path = new URL(link).pathname;

  const theirs = await anotherBrowser(browser, app.url);
  try {
    const them = await theirs.newPage();
    await them.goto(path);
    await expect(them.getByRole('heading', { level: 1, name: `Welcome, ${name}` })).toBeVisible();
    await expect(them.getByText(`Username: ${username}`)).toBeVisible();
    await checkPage(them);
    await them.getByLabel('Password', { exact: true }).fill('too short');
    await them.getByRole('button', { name: 'Save my password' }).click();
    await expect(them.getByRole('alert')).toHaveText('Use at least 12 characters.');
    await them.getByLabel('Password', { exact: true }).fill(PASSWORD);
    await them.getByRole('button', { name: 'Save my password' }).click();
    await expect(them.getByRole('heading', { level: 1, name: 'You’re all set' })).toBeVisible();
    await them.getByRole('link', { name: 'Sign in' }).click();
    await signIn(them, username);
    // The link works once.
    const again = await theirs.newPage();
    await theirs.clearCookies();
    await again.goto(path);
    await expect(again.getByRole('alert')).toBeVisible();
    await expect(again.getByRole('heading', { name: /Welcome/ })).toHaveCount(0);
  } finally {
    await theirs.close();
  }

  await page.goto('/settings/household');
  await expect(peopleList(page).getByRole('link', { name: new RegExp(name) })).toContainText('Member · signs in · 1 portion');
});

test('remove a person: they leave the list, and Undo brings them back', async ({ page }) => {
  const name = `Mira ${mark()}`;
  const made = await addPerson(page, name, { colour: 'blue' });
  await page.goto('/settings/household');
  await peopleList(page).getByRole('link', { name: new RegExp(name) }).click();
  await expect(page.getByText(`Recent changes shows “${name} (removed)”. Undo for 7 days.`, { exact: false })).toBeVisible();
  await page.getByRole('button', { name: `Remove ${name}` }).click();
  await expect(page).toHaveURL('/settings/household');
  await expect(peopleList(page).getByRole('link', { name: new RegExp(name) })).toHaveCount(0);
  await page.getByRole('status').getByRole('button', { name: 'Undo' }).click();
  await expect(page.getByRole('status').filter({ hasText: 'Undone' })).toBeVisible();
  await expect(peopleList(page).getByRole('link', { name: new RegExp(name) })).toBeVisible();
  // Nobody can remove themselves: the admin's own page has no Remove.
  const me = ((await (await page.request.get('/api/v1/people')).json()) as Json).people.find((p: Json) => p.is_me);
  await page.goto(`/settings/household/${me.id}`);
  await expect(page.getByRole('button', { name: 'Save' })).toBeVisible();
  await expect(page.getByRole('button', { name: /^Remove/ })).toHaveCount(0);
  expect(made.id).toBeGreaterThan(0);
});

test('a shared login asks “Who’s this?” when the switch is on; the pick is who Recent changes names', async ({
  page,
  browser,
  app,
}) => {
  // Two browsers, two sign-ins and a page check: more than the usual 30 s on a slow phone run.
  test.slow();
  const m = mark();
  const eater = `Joss ${m}`;
  const tablet = `Tablet ${m}`;
  const username = `tablet.${m}`;
  await addPerson(page, eater, { colour: 'amber' });
  await personWhoSignsIn(page, tablet, username, { shared: true });

  // The switch, on the Household screen.
  await page.goto('/settings/household');
  // The switch turns on at once; wait for the server to have it before asking the server.
  const saved = page.waitForResponse(
    (r) => r.url().endsWith('/api/v1/people/ask-whos-this') && r.request().method() === 'PUT',
  );
  await page.getByRole('switch', { name: 'Ask “Who’s this?”' }).click();
  expect((await saved).status()).toBe(200);
  await expect(page.getByRole('switch', { name: 'Ask “Who’s this?”' })).toHaveAttribute('aria-checked', 'true');
  expect(((await (await page.request.get('/api/v1/people')).json()) as Json).ask_whos_this).toBe(true);

  const theirs = await anotherBrowser(browser, app.url);
  try {
    const them = await theirs.newPage();
    await signIn(them, username);
    const sheet = them.getByRole('dialog', { name: 'Who’s this?' });
    await expect(sheet).toBeVisible();
    await expect(sheet).toContainText(`This is ${tablet}.`);
    // The shared login's own person doesn't eat, so isn't offered.
    await expect(sheet.getByRole('button', { name: eater })).toBeVisible();
    await expect(sheet.getByRole('button', { name: tablet })).toHaveCount(0);
    await expect(sheet.getByRole('button', { name: 'Just looking (don’t ask again for an hour)' })).toBeVisible();
    await checkPage(them);
    await sheet.getByRole('button', { name: eater }).click();
    await expect(sheet).toBeHidden();
    // A change made now is the picked person's.
    const shop = await them.request.post('/api/v1/shops', { data: { name: `Shop ${m}` }, headers: key() });
    expect(shop.ok(), await shop.text()).toBe(true);
    const shopId = ((await shop.json()) as Json).id;
    await page.goto('/settings?section=recent-changes');
    const row = page.getByRole('region', { name: 'Recent changes' }).getByRole('listitem').filter({ hasText: `Shop ${m}` });
    await expect(row).toContainText(eater);
    await page.request.delete(`/api/v1/shops/${shopId}`, { headers: key() });

    // "Just looking": a reload asks again only after the hour.
    await them.request.put('/api/v1/whos-this', { data: { member_id: null } });
    await them.reload();
    await expect(sheet).toBeVisible();
    await sheet.getByRole('button', { name: 'Just looking (don’t ask again for an hour)' }).click();
    await expect(sheet).toBeHidden();
    const asked = them.waitForResponse((r) => r.url().endsWith('/api/v1/whos-this') && r.request().method() === 'GET');
    await them.reload();
    expect(((await (await asked).json()) as Json).picked).toBeNull();
    await expect(sheet).toBeHidden();
  } finally {
    await theirs.close();
  }
});
