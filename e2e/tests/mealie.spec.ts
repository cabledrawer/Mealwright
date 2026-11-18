import { deflateRawSync, crc32 } from 'node:zlib';
import { test, expect, request, testNow, type Page } from './clock.ts';
import { checkPage, expectNoSidewaysScroll, isPhone, setAccountTheme } from './a11y.ts';

// Import from Mealie (0.9.5, cabledrawer 13 Nov), against the real server, signed in as the test
// admin: the row in Your data, a Mealie backup file chosen and shown before anything is added,
// Bring in (the import runs on the server and the screen asks how far it has got), Done, the
// drafts it left in Drafts under From Mealie, and one Undo that takes it all out again. The file
// is made here: made-up recipes and made-up people, names of its own each run, so a recipe is
// never "already here" from another test. Every test undoes its import, so the worker's server
// is left as it was. The table's other states (many recipes, search, chips) are in the unit test
// (frontend/src/routes/(app)/settings/your-data/mealie/page.test.ts).
// Runs in "phone 0.9.5 mealie", "desktop 0.9.5 mealie" and "webkit 0.9.5 mealie".

const DAL = '1b4e28ba2fa111d2883f0016d3cca427';
const SOUP = '2c5f39cb3fb211d2883f0016d3cca428';
const CURRY = '3d6f39cb3fb211d2883f0016d3cca429';
const LENTILS = '9a0e7c1a000040008000000000000002';
const STOCK = '9a0e7c1a000040008000000000000003';
const GRAM = '7b1d6e2f000040008000000000000003';

const run = () => `${test.info().project.name.replace(/\D/g, '')}${Date.now() % 100000}`;

const line = (recipe: string, at: number, text: string, food: string | null = null, quantity = 0) => ({
  recipe_id: recipe,
  position: at,
  quantity,
  unit_id: food && quantity ? GRAM : null,
  food_id: food,
  note: food ? '' : text,
  original_text: food ? null : text,
});

/** Three recipes: the dal's and the curry's every line names a Mealie food (read), Lorna's
 *  soup has a line nobody could read (it waits in Drafts). */
function database(tag: string) {
  const recipe = (id: string, name: string) => ({ id, slug: id, name: `${name} ${tag}`, recipe_yield: '4', org_url: null });
  return {
    recipes: [recipe(DAL, 'Red lentil dal'), recipe(SOUP, 'Lorna’s soup'), recipe(CURRY, 'Sam’s curry')],
    recipes_ingredients: [
      line(DAL, 0, '', LENTILS, 200),
      line(DAL, 1, '', STOCK, 500),
      line(SOUP, 0, '', STOCK, 1000),
      line(SOUP, 1, 'a handful of whatever is in the garden'),
      line(CURRY, 0, '', LENTILS, 100),
    ],
    recipe_instructions: [
      { recipe_id: DAL, position: 0, title: '', text: 'Simmer the lentils.' },
      { recipe_id: SOUP, position: 0, title: '', text: 'Cook it all.' },
      { recipe_id: CURRY, position: 0, title: '', text: 'Fry, then simmer.' },
    ],
    ingredient_foods: [
      { id: LENTILS, name: 'Red lentils' },
      { id: STOCK, name: 'Vegetable stock' },
    ],
    ingredient_units: [{ id: GRAM, name: 'gram', abbreviation: 'g', use_abbreviation: true }],
    tags: [],
    recipes_to_tags: [],
    group_meal_plans: [{}, {}],
    shopping_lists: [{}],
    users: [{ username: 'noor' }],
    cookbooks: [],
  };
}

/** A zip with one deflated member, database.json: the smallest Mealie backup. */
function backup(tag: string): Buffer {
  const name = Buffer.from('database.json');
  const raw = Buffer.from(JSON.stringify(database(tag)));
  const packed = deflateRawSync(raw);
  const crc = crc32(raw);
  const local = Buffer.alloc(30);
  local.writeUInt32LE(0x04034b50, 0);
  local.writeUInt16LE(20, 4);
  local.writeUInt16LE(8, 8);
  local.writeUInt32LE(crc, 14);
  local.writeUInt32LE(packed.length, 18);
  local.writeUInt32LE(raw.length, 22);
  local.writeUInt16LE(name.length, 26);
  const central = Buffer.alloc(46);
  central.writeUInt32LE(0x02014b50, 0);
  central.writeUInt16LE(20, 4);
  central.writeUInt16LE(20, 6);
  central.writeUInt16LE(8, 10);
  central.writeUInt32LE(crc, 16);
  central.writeUInt32LE(packed.length, 20);
  central.writeUInt32LE(raw.length, 24);
  central.writeUInt16LE(name.length, 28);
  const centralAt = local.length + name.length + packed.length;
  const end = Buffer.alloc(22);
  end.writeUInt32LE(0x06054b50, 0);
  end.writeUInt16LE(1, 8);
  end.writeUInt16LE(1, 10);
  end.writeUInt32LE(central.length + name.length, 12);
  end.writeUInt32LE(centralAt, 16);
  return Buffer.concat([local, name, packed, central, name, end]);
}

async function openFromYourData(page: Page) {
  await page.goto('/settings/your-data');
  await page.getByRole('link', { name: /Import from Mealie/ }).click();
  await expect(page).toHaveURL(/\/settings\/your-data\/mealie$/);
  await expect(page.getByRole('heading', { level: 1, name: 'Import from Mealie' })).toBeVisible();
}

async function choose(page: Page, tag: string) {
  await page.locator('input[type="file"]').setInputFiles({
    name: 'mealie_2026.11.10.zip',
    mimeType: 'application/zip',
    buffer: backup(tag),
  });
}

/** Whatever a test left behind, its import is undone (an import still open on the preview is
 *  cancelled), so the next test starts on the start screen. */
async function undoAny(page: Page) {
  const current = await page.request.get('/api/v1/mealie-imports/current');
  const job = (await current.json()).current;
  if (!job) return;
  if (job.state === 'ready') await page.request.delete(`/api/v1/mealie-imports/${job.id}`);
  else if (job.state === 'done' || job.state === 'failed') await page.request.post(`/api/v1/mealie-imports/${job.id}/undo`);
}

test.beforeEach(async ({ page }) => {
  await setAccountTheme(page, 'auto');
  await undoAny(page);
});

test.afterEach(async ({ page }) => {
  await undoAny(page);
});

test('the file is shown before anything is added; Cancel adds nothing', async ({ page }) => {
  const tag = run();
  await openFromYourData(page);
  await expect(page.getByText(/It never connects to Mealie or to the internet/)).toBeVisible();
  await checkPage(page);
  await choose(page, tag);
  // The file is read in a child process that starts cold (about 1.5 s alone here, longer when
  // the machine is busy with the other browser runs), so this waits as long as the other
  // tests wait for the server's work.
  if (isPhone(page)) {
    await expect(page.getByRole('heading', { name: 'In this file' })).toBeVisible({ timeout: 30_000 });
  } else {
    await expect(page.getByRole('row', { name: new RegExp(`Sam’s curry ${tag}`) })).toBeVisible({ timeout: 30_000 });
  }
  await expect(page.getByText('Not brought in: 2 meal plans, 1 shopping list, 1 user.')).toBeVisible();
  await expect(page.getByRole('button', { name: 'Bring in 3 recipes' })).toBeEnabled();
  await expectNoSidewaysScroll(page);
  await checkPage(page);
  // Nothing is in Recipes yet.
  const before = await page.request.get(`/api/v1/recipes?q=${encodeURIComponent(tag)}`);
  expect(JSON.stringify(await before.json())).not.toContain(tag);
  await page.getByRole('button', { name: 'Cancel' }).click();
  // Back on the start screen (the computer's drop area says "Choose file…").
  const again = isPhone(page) ? 'Choose the Mealie file (.zip)' : 'Choose file…';
  await expect(page.getByRole('button', { name: again })).toBeVisible();
});

test('Bring in runs on the server; Done leads to the draft to check; Undo takes it all out', async ({ page }) => {
  test.skip(!isPhone(page), 'the computer’s Done is the next test');
  const tag = run();
  await openFromYourData(page);
  await choose(page, tag);
  await page.getByRole('button', { name: 'Bring in 3 recipes' }).click();
  await expect(page.getByText('3 recipes brought in')).toBeVisible({ timeout: 30_000 });
  await expect(page.getByText(/From mealie_2026\.11\.10\.zip, today \d\d:\d\d/)).toBeVisible();
  await checkPage(page);

  await page.getByRole('link', { name: 'Check the 1' }).click();
  await expect(page).toHaveURL(/\/recipes\/drafts\?from=mealie$/);
  await expect(page.getByRole('button', { name: 'From Mealie 1' })).toHaveAttribute('aria-pressed', 'true');
  await expect(page.getByText(`Lorna’s soup ${tag}`)).toBeVisible();
  await expect(page.getByText('“a handful of whatever is in the garden”')).toBeVisible();
  await expect(page.getByRole('button', { name: 'Save all 1 as they are' })).toBeVisible();
  await checkPage(page);

  await page.goto('/settings/your-data/mealie');
  await page.getByRole('button', { name: 'Undo', exact: true }).click();
  await expect(page.getByText('Import undone')).toBeVisible();
  await expect(page.getByText(/Took out 3 recipes/)).toBeVisible();
  const after = await page.request.get('/api/v1/recipes/drafts');
  expect(JSON.stringify(await after.json())).not.toContain(tag);
});

test('on a computer: an unticked recipe is left out, Save all, then Undo', async ({ page }) => {
  test.skip(isPhone(page), 'the table is the computer’s');
  const tag = run();
  await openFromYourData(page);
  await expect(page.getByRole('list', { name: 'Steps' })).toBeVisible();
  await choose(page, tag);
  // Every target on the table is at least 44 px (round 1, review 3): the chips, the search
  // and the tick box's whole cell, which unticks from its corner.
  const curry = page.getByRole('checkbox', { name: `Bring in Sam’s curry ${tag}` });
  const cell = page.locator('label.hit').filter({ has: curry });
  for (const target of [
    page.getByRole('button', { name: /^All \d+$/ }),
    page.getByRole('searchbox', { name: 'Find a recipe' }),
    cell,
  ]) {
    expect((await target.boundingBox())!.height).toBeGreaterThanOrEqual(44);
  }
  expect((await cell.boundingBox())!.width).toBeGreaterThanOrEqual(44);
  await cell.click({ position: { x: 3, y: 3 } });
  await expect(curry).not.toBeChecked();
  await page.getByRole('button', { name: 'Bring in 2 recipes' }).click();
  await expect(page.getByText(/2 recipes brought in/)).toBeVisible({ timeout: 30_000 });
  await expect(page.getByRole('heading', { name: '1 recipe to check' })).toBeVisible();
  await expect(page.getByRole('link', { name: `Check Lorna’s soup ${tag}` })).toBeVisible();
  await checkPage(page);

  await page.getByRole('button', { name: 'Save all as they are' }).click();
  await expect(page.getByRole('heading', { name: '1 recipe to check' })).toBeHidden();
  const drafts = await page.request.get('/api/v1/recipes/drafts');
  expect(JSON.stringify(await drafts.json())).not.toContain(tag);

  await page.getByRole('button', { name: 'Undo', exact: true }).click();
  await expect(page.getByText('Import undone')).toBeVisible();
  await expect(page.getByText(/Took out 2 recipes/)).toBeVisible();
});

// Round 2 (review 2): a member sees the Today note and can open and check a draft, but has none
// of the admin's buttons (the server refuses them anyway). The import page itself is admins only
// since Settings2 (cabledrawer 18 Nov, Q13): a member who opens its address is told so instead.
test('a member sees the Today note and Drafts, not the import page', async ({ page, browser, app }) => {
  const tag = run();
  const key = () => ({ 'idempotency-key': crypto.randomUUID() });
  const name = `Sam ${tag}`;
  const username = `sam${tag}`;
  const password = 'a-long-kitchen-password';
  const added = await page.request.post('/api/v1/people', { data: { name }, headers: key() });
  expect(added.status(), await added.text()).toBe(201);
  const person = (await added.json()).people.find((p: { name: string }) => p.name === name);
  try {
    const link = await page.request.post(`/api/v1/people/${person.id}/login`, {
      data: { username, role: 'member' },
      headers: key(),
    });
    expect(link.status(), await link.text()).toBe(201);
    const token = ((await link.json()).path as string).replace(/^\/join#/, '');
    const signedOut = await request.newContext({
      baseURL: app.url,
      storageState: { cookies: [], origins: [] },
      ignoreHTTPSErrors: test.info().project.use.ignoreHTTPSErrors,
    });
    try {
      const joined = await signedOut.post('/api/v1/join', { data: { token, password } });
      expect(joined.status(), await joined.text()).toBe(200);
    } finally {
      await signedOut.dispose();
    }

    // The admin brings an import in (through the API), so there is a Done and a draft.
    const sent = await page.request.post('/api/v1/mealie-imports?file_name=mealie_2026.11.10.zip', {
      data: backup(tag),
      headers: { 'content-type': 'application/zip' },
    });
    expect(sent.status(), await sent.text()).toBe(201);
    const job = await sent.json();
    const start = await page.request.post(`/api/v1/mealie-imports/${job.id}/start`, {
      data: { leave_out: [], photos: false },
    });
    expect(start.status(), await start.text()).toBe(202);
    await expect
      .poll(async () => (await (await page.request.get(`/api/v1/mealie-imports/${job.id}`)).json()).state, {
        timeout: 30_000,
      })
      .toBe('done');

    const use = test.info().project.use;
    const theirs = await browser.newContext({
      baseURL: app.url,
      storageState: { cookies: [], origins: [] },
      viewport: use.viewport,
      hasTouch: use.hasTouch,
      isMobile: use.browserName === 'chromium' ? use.isMobile : undefined,
      userAgent: use.userAgent,
      deviceScaleFactor: use.deviceScaleFactor,
    });
    // The tests' clock, as the server's (a second browser doesn't get it by itself).
    await theirs.clock.install({ time: testNow() });
    try {
      const them = await theirs.newPage();
      await them.goto('/sign-in');
      await them.getByLabel('Username').fill(username);
      await them.getByLabel('Password', { exact: true }).fill(password);
      await them.getByRole('button', { name: 'Sign in' }).click();
      await expect(them).not.toHaveURL(/\/sign-in/);

      // Today: the note, with the way to the drafts but no arrow to the import.
      await them.goto('/');
      const note = them.getByTestId('today-mealie');
      await expect(note).toContainText('3 recipes brought in from Mealie');
      await expect(note.getByRole('link', { name: 'Check them' })).toBeVisible();

      // The import page is admins only (cabledrawer 18 Nov, Q13): its address says so, and shows
      // nothing of the import and no button that changes anything.
      await them.goto('/settings/your-data/mealie');
      await expect(them.getByText('Only admins can change this.')).toBeVisible();
      await expect(them.getByText('3 recipes brought in')).toHaveCount(0);
      await expect(them.getByRole('button', { name: /Undo|Save all|Import another/ })).toHaveCount(0);

      // Drafts: the draft opens, with no Save all.
      await them.goto('/recipes/drafts?from=mealie');
      await expect(them.getByText(`Lorna’s soup ${tag}`)).toBeVisible();
      await expect(them.getByRole('button', { name: /^Save all/ })).toHaveCount(0);
      await them.getByRole('link', { name: new RegExp(`Lorna’s soup ${tag}`) }).click();
      await expect(them).toHaveURL(/\/recipes\/drafts\/\d+/);
    } finally {
      await theirs.close();
    }
  } finally {
    await page.request.delete(`/api/v1/people/${person.id}`, { headers: key() });
  }
});
