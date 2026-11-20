import { mkdirSync } from 'node:fs';
import { join } from 'node:path';
import { test, expect, request, type Browser, type Page } from './clock.ts';
import { checkPage, isPhone, setAccountTheme } from './a11y.ts';
import { key } from './helpers.ts';

// Settings › People (0.9 A1): the household's people, the Person screen, giving someone a
// login (sign-in link → choose a password → sign in), removing someone and Undo, and "Who's this?"
// on a shared login, against the real server, signed in as the test admin. Every test removes the
// people it added, so the Plan's "Who's eating" on this worker's server is as it was.
// Runs in the "phone 0.9 household", "desktop 0.9 household" and "webkit 0.9 household" projects.

type Json = Record<string, any>; // eslint-disable-line @typescript-eslint/no-explicit-any

/** A short mark of its own for each test and project, so names and usernames never clash. */
const mark = () => `${test.info().project.name.split(' ')[0]!.slice(0, 1)}${Date.now().toString(36).slice(-5)}`;
const PASSWORD = 'a-long-kitchen-password';

async function addPerson(page: Page, name: string, extra: Json = {}) {
  const response = await page.request.post('/api/v1/people', { data: { name, ...extra }, headers: key() });
  expect(response.status(), await response.text()).toBe(201);
  const found = (await response.json()) as Json;
  return found.people.find((p: Json) => p.name === name) as Json;
}

/**
 * A person with a login and their own password, as if they had used their sign-in link. The link
 * is used signed out (`baseURL`, with no cookies): where the admin is signed in, it refuses (Pe2).
 */
async function personWhoSignsIn(page: Page, baseURL: string, name: string, username: string, extra: Json = {}) {
  const made = await addPerson(page, name);
  const link = await page.request.post(`/api/v1/people/${made.id}/login`, {
    data: { username, role: 'member' },
    headers: key(),
  });
  expect(link.status(), await link.text()).toBe(201);
  const path = ((await link.json()) as Json).path as string;
  const token = path.replace(/^\/join#/, '');
  // Signed out: inside a test, a new context would otherwise start with the project's saved
  // sign-in (the admin's).
  const signedOut = await request.newContext({
    baseURL,
    storageState: { cookies: [], origins: [] },
    ignoreHTTPSErrors: test.info().project.use.ignoreHTTPSErrors,
  });
  try {
    const joined = await signedOut.post('/api/v1/join', { data: { token, password: PASSWORD } });
    expect(joined.status(), await joined.text()).toBe(200);
  } finally {
    await signedOut.dispose();
  }
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
  // Signed out: a context made here would otherwise start with the project's saved
  // sign-in (the admin's): /sign-in sends a signed-in browser straight on, and a link page
  // refuses (Pe2).
  return browser.newContext({
    baseURL,
    storageState: { cookies: [], origins: [] },
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

test('the Settings row opens People; add a person, who opens to choose their colour and portion, saved as they are picked; Save goes back to the list', async ({
  page,
}) => {
  const name = `Joss ${mark()}`;
  await page.goto('/settings');
  if (isPhone(page)) {
    await expect(page.getByRole('link', { name: /^People/ })).toContainText('1 person');
    await page.getByRole('link', { name: /^People/ }).click();
  } else {
    await page.getByRole('navigation', { name: 'Settings', exact: true }).getByRole('link', { name: 'People' }).click();
  }
  await expect(page).toHaveURL('/settings/people');
  await expect(page.getByRole('heading', { level: 1, name: 'People' })).toBeVisible();
  await expect(peopleList(page).getByRole('link')).toHaveCount(1);
  await expect(peopleList(page).getByRole('link').first()).toContainText('Tess (you)');
  await expect(page.getByRole('switch', { name: 'Ask “Who’s this?”' })).toHaveAttribute('aria-checked', 'false');
  await checkPage(page);

  await page.getByRole('button', { name: '+ Add a person' }).click();
  await expect(page.getByLabel('Name', { exact: true })).toBeFocused();
  await page.getByLabel('Name', { exact: true }).fill(name);
  await page.getByRole('button', { name: 'Add', exact: true }).click();
  await expect(page.getByRole('heading', { level: 1, name })).toBeVisible();
  await expect(page).toHaveURL(/\/settings\/people\/\d+$/);
  await checkPage(page);

  await page.getByRole('button', { name: 'Violet' }).click();
  await expect(page.getByRole('button', { name: 'Violet' })).toHaveAttribute('aria-pressed', 'true');
  await page.getByRole('button', { name: '½ portion', exact: true }).click();
  await expect(page.getByRole('button', { name: '½ portion', exact: true })).toHaveAttribute('aria-pressed', 'true');
  // The colour and the portion are saved as they are picked, before Save is pressed (hunt L4).
  await expect
    .poll(async () =>
      ((await (await page.request.get('/api/v1/people')).json()) as Json).people.find((p: Json) => p.name === name),
    )
    .toMatchObject({ colour: 'violet', portion_quarters: 2 });
  await page.getByRole('button', { name: 'Save' }).click();
  await expect(page).toHaveURL('/settings/people');
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
  await page.goto(`/settings/people/${made.id}`);
  await page.getByRole('button', { name: 'Give a login' }).click();
  await expect(page.getByLabel('Username')).toHaveValue(`rafe.${m.toLowerCase()}`);
  await page.getByLabel('Username').fill(username);
  await page.getByRole('button', { name: 'Make the sign-in link' }).click();
  const made_ = page.getByRole('status').filter({ hasText: 'Sign-in link made.' });
  await expect(made_).toContainText(`It works once, for 24 hours: send it to ${name} to choose a password.`);
  await expect(page.getByRole('button', { name: 'Copy the link' })).toBeVisible();
  await checkPage(page);
  const link = (await made_.locator('.mono').textContent())!.trim();
  // The secret follows a `#`: a browser never sends it to the server (cabledrawer 13 Nov).
  expect(link).toMatch(/\/join#[\w-]+$/);
  const path = new URL(link).pathname + new URL(link).hash;

  // Opened here, where the admin is signed in, the link refuses and stays unused (Pe2).
  await page.goto(path);
  await expect(page.getByRole('heading', { level: 1, name: "This link can’t be used here" })).toBeVisible();
  await expect(page.getByText('The link hasn’t been used.', { exact: false })).toBeVisible();
  expect(page.url()).not.toContain('#');
  await expect(page.getByText(name)).toHaveCount(0);
  await checkPage(page);
  await page.getByRole('link', { name: 'Go to Today' }).click();
  await expect(page).toHaveURL('/');

  const theirs = await anotherBrowser(browser, app.url);
  try {
    const them = await theirs.newPage();
    const asked: string[] = [];
    them.on('request', (request) => asked.push(request.url()));
    await them.goto(path);
    await expect(them.getByRole('heading', { level: 1, name: 'Welcome' })).toBeVisible();
    // The address bar has lost the secret, and no request carried it in its address.
    expect(them.url()).not.toContain('#');
    expect(asked.filter((url) => url.includes(path.split('#')[1]!))).toEqual([]);
    // Nobody is named before the password is set.
    await expect(them.getByText(username)).toHaveCount(0);
    await expect(them.getByText(name)).toHaveCount(0);
    await checkPage(them);
    await them.getByLabel('Password', { exact: true }).fill('too short');
    await them.getByRole('button', { name: 'Save my password' }).click();
    await expect(them.getByRole('alert')).toHaveText('Use at least 12 characters.');
    await them.getByLabel('Password', { exact: true }).fill(PASSWORD);
    await them.getByRole('button', { name: 'Save my password' }).click();
    // Signed in straight away, in the app (F254, cabledrawer 20 Nov).
    await expect(them).toHaveURL('/');
    const me = await them.request.get('/api/v1/me');
    expect(me.status()).toBe(200);
    expect((await me.json()).username).toBe(username);
    // The link works once.
    const again = await theirs.newPage();
    await theirs.clearCookies();
    await again.goto(path);
    await expect(again.getByRole('alert')).toBeVisible();
    await expect(again.getByRole('heading', { name: /Welcome/ })).toHaveCount(0);
  } finally {
    await theirs.close();
  }

  await page.goto('/settings/people');
  await expect(peopleList(page).getByRole('link', { name: new RegExp(name) })).toContainText('Member · signs in · 1 portion');
});

test('Reset password: a one-time link where they choose a new password; the Person page says when a link was used (Pe1)', async ({
  page,
  browser,
  app,
}) => {
  const m = mark();
  const name = `Lorna ${m}`;
  const username = `lorna.${m}`;
  const NEW_PASSWORD = 'a-new-kitchen-password';
  const made = await personWhoSignsIn(page, app.url, name, username);
  await page.goto(`/settings/people/${made.id}`);
  // Their sign-in link was used just now: an admin can spot a link someone else used.
  await expect(page.getByText(/^Link used today \d{2}:\d{2}$/)).toBeVisible();
  await page.getByRole('button', { name: 'Reset password' }).click();
  const panel = page.getByRole('status').filter({ hasText: 'Reset link made.' });
  await expect(panel).toContainText(
    `It works once, for 24 hours. Send it to ${name}: they pick a new password, and their recipes, plans and history stay as they are.`,
  );
  await expect(page.getByRole('button', { name: 'Copy the link' })).toBeVisible();
  await checkPage(page);
  const link = (await panel.locator('.mono').textContent())!.trim();
  expect(link).toMatch(/\/reset#[\w-]+$/);
  const path = new URL(link).pathname + new URL(link).hash;

  const theirs = await anotherBrowser(browser, app.url);
  try {
    const them = await theirs.newPage();
    const asked: string[] = [];
    them.on('request', (request) => asked.push(request.url()));
    await them.goto(path);
    await expect(them.getByRole('heading', { level: 1, name: 'Choose a new password' })).toBeVisible();
    expect(them.url()).not.toContain('#');
    expect(asked.filter((url) => url.includes(path.split('#')[1]!))).toEqual([]);
    await expect(them.getByText(username)).toHaveCount(0);
    await expect(them.getByText(name)).toHaveCount(0);
    await checkPage(them);
    await them.getByLabel('Password', { exact: true }).fill(NEW_PASSWORD);
    await them.getByRole('button', { name: 'Save my password' }).click();
    // Signed in straight away (F254); then signed out, the new password signs in and the old
    // one doesn't.
    await expect(them).toHaveURL('/');
    expect((await them.request.delete('/api/v1/session')).status()).toBe(204);
    const old = await them.request.post('/api/v1/session', {
      data: { username, password: PASSWORD, remember: false },
    });
    expect(old.status()).toBe(401);
    await them.goto('/sign-in');
    await them.getByLabel('Username').fill(username);
    await them.getByLabel('Password', { exact: true }).fill(NEW_PASSWORD);
    await them.getByRole('button', { name: 'Sign in' }).click();
    await expect(them).not.toHaveURL(/\/sign-in/);
  } finally {
    await theirs.close();
  }

  // Back on the Person page: no reset link waits any more, and its use shows.
  await page.reload();
  await expect(page.getByText(/^Link used today \d{2}:\d{2}$/)).toBeVisible();
  await expect(page.getByText(`${name} hasn’t used the reset link yet.`)).toHaveCount(0);
});

test('remove a person: they leave the list, and Undo brings them back', async ({ page }) => {
  const name = `Mira ${mark()}`;
  const made = await addPerson(page, name, { colour: 'blue' });
  await page.goto('/settings/people');
  await peopleList(page).getByRole('link', { name: new RegExp(name) }).click();
  await expect(page.getByText(`Recent changes shows “${name} (removed)”. Undo for 7 days.`, { exact: false })).toBeVisible();
  await page.getByRole('button', { name: `Remove ${name}` }).click();
  await expect(page).toHaveURL('/settings/people');
  await expect(peopleList(page).getByRole('link', { name: new RegExp(name) })).toHaveCount(0);
  await page.getByRole('status').getByRole('button', { name: 'Undo' }).click();
  await expect(page.getByRole('status').filter({ hasText: 'Undone' })).toBeVisible();
  await expect(peopleList(page).getByRole('link', { name: new RegExp(name) })).toBeVisible();
  // Nobody can remove themselves: the admin's own page has no Remove.
  const me = ((await (await page.request.get('/api/v1/people')).json()) as Json).people.find((p: Json) => p.is_me);
  await page.goto(`/settings/people/${me.id}`);
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
  await personWhoSignsIn(page, app.url, tablet, username, { shared: true });

  // The switch, on the Household screen.
  await page.goto('/settings/people');
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
    await page.goto('/settings/recent-changes');
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

// --- Single sign-on: "Who is this?" and the Person page (0.9.5 Pe3/M2) ---------------------------
// The sign-in server's side is in the backend tests; here the page's own answers are the real
// ones with the single sign-on parts added (page.route), so nothing in the worker's server changes.

const WAITING = { id: 7, username: 'lorna.s', signed_in_at: new Date().toISOString(), role: 'member' };

/** GET /people as the server answers it, with single sign-on set up, `waiting` sign-ins, and
 *  `linked` (a name → the sign-in server's username) for the people it links. */
async function withSso(page: Page, waiting: Json[], linked: Record<string, string> = {}) {
  await page.route('**/api/v1/people', async (route) => {
    if (route.request().method() !== 'GET') return route.continue();
    const real = await route.fetch();
    const body = (await real.json()) as Json;
    body.single_sign_on = true;
    body.waiting = waiting;
    for (const person of body.people as Json[]) {
      const username = linked[person.name as string];
      if (username && person.login) Object.assign(person.login, { sso_linked: true, sso_username: username });
    }
    return route.fulfill({ response: real, json: body });
  });
}

test('Who is this? lists a waiting sign-in and links it to the person picked', async ({ page, app }) => {
  const lorna = `Lorna ${mark()}`;
  const made = await personWhoSignsIn(page, app.url, lorna, `lorna${mark()}`);
  await withSso(page, [WAITING]);
  const linked: Json[] = [];
  await page.route('**/api/v1/people/sso-accounts/7/link', (route) => {
    linked.push(route.request().postDataJSON());
    return route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ people: [], waiting: [] }) });
  });
  await page.goto('/settings/people');
  await expect(page.getByText('1 sign-in waiting')).toBeVisible();
  await expect(page.getByText(/^lorna\.s signed in with single sign-on .* and doesn’t match anyone here\.$/)).toBeVisible();
  await page.getByRole('button', { name: 'Who is this?' }).click();
  const sheet = page.getByRole('dialog', { name: 'Who is lorna.s?' });
  await expect(sheet).toBeVisible();
  await expect(sheet.getByRole('button', { name: 'Not someone I know: refuse' })).toBeVisible();
  await expect(sheet.getByRole('radio', { name: 'A new person' })).toBeVisible();
  await expect(sheet.getByRole('button', { name: 'Choose who it is' })).toBeDisabled();
  await checkPage(page);
  await sheet.getByRole('radio', { name: new RegExp(lorna) }).click();
  await sheet.getByRole('button', { name: `Link to ${lorna}` }).click();
  await expect.poll(() => linked).toEqual([{ member_id: made.id }]);
});

test('the Person page says who a linked person is, Unlink unlinks them, and Link… offers the waiting sign-ins', async ({ page, app }) => {
  const lorna = `Lorna ${mark()}`;
  const made = await personWhoSignsIn(page, app.url, lorna, `lorna${mark()}`);
  await withSso(page, [WAITING], { [lorna]: 'lorna.s' });
  const unlinked: string[] = [];
  await page.route(`**/api/v1/people/${made.id}/sso`, (route) => {
    unlinked.push(route.request().method());
    return route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ people: [], waiting: [] }) });
  });
  await page.goto(`/settings/people/${made.id}`);
  await expect(page.getByText('Single sign-on', { exact: true })).toBeVisible();
  await expect(page.getByText('Linked to lorna.s on your sign-in server')).toBeVisible();
  await checkPage(page);
  await page.getByRole('button', { name: 'Unlink' }).click();
  await expect.poll(() => unlinked).toEqual(['DELETE']);
});

test('an unlinked person shows how they get linked, and Link… opens the waiting sign-ins', async ({ page, app }) => {
  const lorna = `Lorna ${mark()}`;
  const made = await personWhoSignsIn(page, app.url, lorna, `lorna${mark()}`);
  await withSso(page, [WAITING]);
  await page.goto(`/settings/people/${made.id}`);
  await expect(page.getByText(/^Not linked\. Linked automatically only if they have never signed in and the sign-in server’s username is the same as here/)).toBeVisible();
  await page.getByRole('button', { name: 'Link…' }).click();
  const sheet = page.getByRole('dialog', { name: `Link ${lorna} to a sign-in` });
  await expect(sheet).toBeVisible();
  await expect(sheet.getByRole('radio', { name: /lorna\.s/ })).toBeVisible();
  await checkPage(page);
  await page.keyboard.press('Escape');
  await expect(sheet).toBeHidden();
});

test('screenshots, dark (by hand only)', async ({ page, app }) => {
  test.skip(!process.env.E2E_SHOTS_DIR || !test.info().project.name.startsWith('desktop'), 'by hand, desktop project');
  const dir = process.env.E2E_SHOTS_DIR!;
  mkdirSync(dir, { recursive: true });
  const lorna = `Lorna ${mark()}`;
  const made = await personWhoSignsIn(page, app.url, lorna, `lorna${mark()}`);
  await page.emulateMedia({ colorScheme: 'dark' });
  const shoot = async (screen: string, open: () => Promise<void>) => {
    for (const width of [428, 768, 1100, 1300]) {
      await page.setViewportSize({ width, height: 900 });
      await open();
      await page.screenshot({ path: join(dir, `${screen}-${width}.png`), fullPage: true });
    }
  };
  await withSso(page, [WAITING]);
  await shoot('household-who-is-this', async () => {
    await page.goto('/settings/people');
    await expect(page.getByText('1 sign-in waiting')).toBeVisible();
    await page.getByRole('button', { name: 'Who is this?' }).click();
    await expect(page.getByRole('dialog', { name: 'Who is lorna.s?' })).toBeVisible();
  });
  await shoot('person-unlinked', async () => {
    await page.goto(`/settings/people/${made.id}`);
    await expect(page.getByRole('button', { name: 'Link…' })).toBeVisible();
  });
  await shoot('person-link-sheet', async () => {
    await page.goto(`/settings/people/${made.id}`);
    await page.getByRole('button', { name: 'Link…' }).click();
    await expect(page.getByRole('dialog', { name: `Link ${lorna} to a sign-in` })).toBeVisible();
  });
  await page.unrouteAll({ behavior: 'ignoreErrors' });
  await withSso(page, [], { [lorna]: 'lorna.s' });
  await shoot('person-linked', async () => {
    await page.goto(`/settings/people/${made.id}`);
    await expect(page.getByRole('button', { name: 'Unlink' })).toBeVisible();
  });
  // The Shared login line (Pe7) and a colour saved as it is picked (L4).
  await page.unrouteAll({ behavior: 'ignoreErrors' });
  await shoot('person-shared-login-line', async () => {
    await page.goto(`/settings/people/${made.id}`);
    await expect(page.getByText('A shared login isn’t counted as someone who eats.')).toBeVisible();
  });
  const noor = `Noor ${mark()}`;
  const made2 = await page.request.post('/api/v1/people', { data: { name: noor, colour: 'amber' } });
  expect(made2.ok(), await made2.text()).toBe(true);
  const noorId = ((await (await page.request.get('/api/v1/people')).json()) as Json).people.find((p: Json) => p.name === noor).id;
  await shoot('person-colour-picked', async () => {
    await page.goto(`/settings/people/${noorId}`);
    await page.getByRole('button', { name: 'Violet' }).click();
    await expect(page.getByRole('button', { name: 'Violet' })).toHaveAttribute('aria-pressed', 'true');
    await page.getByRole('button', { name: 'Amber' }).click();
  });
});
