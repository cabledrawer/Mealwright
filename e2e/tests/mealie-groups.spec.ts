import { deflateRawSync, crc32 } from 'node:zlib';
import { test, expect } from './clock.ts';
import { checkPage, expectNoSidewaysScroll, isPhone, setAccountTheme } from './a11y.ts';

// Drafts from Mealie, fixed by ingredient (cabledrawer 15 Nov, 0.9.5-beta.2), against the real
// server as the test admin: two drafts that both use one unreadable ingredient, the By
// ingredient list (most-used first), one answer (a new ingredient with its pantry place) going
// into both, the recipe that is complete moving to Recipes, the toast's Undo putting it all
// back, and Skip for now changing nothing. The file is made here with made-up names, new each
// run, and every test undoes its import. Runs in "phone 0.9.5 mealie groups" and
// "desktop 0.9.5 mealie groups".

const SOUP = '1b4e28ba2fa111d2883f0016d3cca4a1';
const STEW = '2c5f39cb3fb211d2883f0016d3cca4a2';

/** Letters only, so the made-up ingredient is never read as an amount or a unit. */
const word = () =>
  `${test.info().project.name.length}${Date.now() % 1000000}`.replace(/\d/g, (d) => 'abcdefghij'[Number(d)]!);

const line = (recipe: string, at: number, text: string) => ({
  recipe_id: recipe,
  position: at,
  quantity: 0,
  unit_id: null,
  food_id: null,
  note: text,
  original_text: text,
});

function database(tag: string, herb: string, root: string, more = false) {
  const recipe = (id: string, name: string) => ({ id, slug: id, name: `${name} ${tag}`, recipe_yield: '4', org_url: null });
  return {
    recipes: [recipe(SOUP, 'Lorna’s soup'), recipe(STEW, 'Sam’s stew')],
    recipes_ingredients: [
      line(SOUP, 0, `2 tbsp ${herb}`),
      line(STEW, 0, `${herb}, dark`),
      line(STEW, 1, `a thumb of ${root}`),
      ...(more ? [line(SOUP, 1, `a pinch of ${herb}`)] : []),
    ],
    recipe_instructions: [
      { recipe_id: SOUP, position: 0, title: '', text: 'Cook it.' },
      { recipe_id: STEW, position: 0, title: '', text: 'Cook it longer.' },
    ],
    ingredient_foods: [],
    ingredient_units: [],
    tags: [],
    recipes_to_tags: [],
    group_meal_plans: [],
    shopping_lists: [],
    users: [],
    cookbooks: [],
  };
}

/** A zip with one deflated member, database.json: the smallest Mealie backup. */
function zip(data: unknown): Buffer {
  const name = Buffer.from('database.json');
  const raw = Buffer.from(JSON.stringify(data));
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


async function undoAny(page: import('@playwright/test').Page) {
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

async function bringIn(page: import('@playwright/test').Page, tag: string, herb: string, root: string, more = false) {
  const sent = await page.request.post('/api/v1/mealie-imports?file_name=mealie_2026.11.10.zip', {
    data: zip(database(tag, herb, root, more)),
    headers: { 'content-type': 'application/zip' },
  });
  expect(sent.status(), await sent.text()).toBe(201);
  const job = await sent.json();
  const start = await page.request.post(`/api/v1/mealie-imports/${job.id}/start`, { data: { leave_out: [], photos: false } });
  expect(start.status(), await start.text()).toBe(202);
  await expect
    .poll(async () => (await (await page.request.get(`/api/v1/mealie-imports/${job.id}`)).json()).state, { timeout: 30_000 })
    .toBe('done');
}

async function recipeNames(page: import('@playwright/test').Page, tag: string) {
  const answer = await page.request.get(`/api/v1/recipes?q=${encodeURIComponent(tag)}`);
  return JSON.stringify(await answer.json());
}

test('one answer goes into every draft that uses the ingredient; Undo puts it back; Skip changes nothing', async ({ page }) => {
  const tag = word();
  const herb = `zorbo${word()}`;
  const root = `quimby${word()}`;
  await bringIn(page, tag, herb, root);
  await page.goto('/recipes/drafts?from=mealie');
  await expect(page.getByRole('button', { name: 'By ingredient' })).toBeVisible();
  await page.getByRole('button', { name: 'By ingredient' }).click();
  await expect(page.getByText(/ingredients? (still )?to answer/)).toBeVisible();
  await expectNoSidewaysScroll(page);
  await checkPage(page);

  // The most-used first: the herb (in 2 drafts) is above the root (in 1).
  const rows = page.getByRole('group', { name: 'Ingredients to answer' }).getByRole('button');
  await expect(rows.filter({ hasText: herb })).toBeVisible();
  const text = (await rows.allInnerTexts()).join('\n');
  expect(text.indexOf(herb)).toBeLessThan(text.indexOf(root));
  await rows.filter({ hasText: herb }).click();

  // Skip for now sends nothing: the drafts are still two.
  const before = (await (await page.request.get('/api/v1/recipes/drafts')).json()).count;
  const skip = page.getByRole('button', { name: isPhone(page) ? 'Skip' : 'Skip for now' });
  await skip.click();
  expect((await (await page.request.get('/api/v1/recipes/drafts')).json()).count).toBe(before);
  if (isPhone(page)) await rows.filter({ hasText: herb }).click();
  else await rows.filter({ hasText: herb }).click();

  // The phone's answer is a page of its own: every button is at least 44 px.
  if (isPhone(page)) {
    for (const target of [
      page.getByRole('button', { name: 'Back to the list' }),
      page.getByRole('button', { name: 'Skip' }),
      page.getByRole('button', { name: /^Use for all/ }),
      page.getByRole('button', { name: 'A new ingredient' }),
    ]) {
      expect((await target.boundingBox())!.height).toBeGreaterThanOrEqual(44);
    }
  }
  await page.getByRole('button', { name: 'A new ingredient' }).click();
  await page.getByRole('button', { name: 'Fridge' }).click();
  await checkPage(page);
  await page.getByRole('button', { name: /^Use for all/ }).click();
  await expect(page.getByText(/Answered .* in 2 drafts · 1 recipe moved to Recipes/)).toBeVisible();
  // Lorna's soup had only that line: it is a recipe now; Sam's stew still waits for the root.
  expect(await recipeNames(page, tag)).toContain('Lorna’s soup');
  const drafts = JSON.stringify(await (await page.request.get('/api/v1/recipes/drafts')).json());
  expect(drafts).toContain('Sam’s stew');
  expect(drafts).not.toContain('Lorna’s soup');

  await page.getByRole('button', { name: 'Undo', exact: true }).click();
  await expect
    .poll(async () => JSON.stringify(await (await page.request.get('/api/v1/recipes/drafts')).json()))
    .toContain('Lorna’s soup');
});

// F259 (hand test 20 Nov): "+ more" under the group's two lines as written is a button that
// shows every way the lines are written, from the server.
test('+ more shows every way an ingredient is written, and Show fewer hides them again', async ({ page }) => {
  const tag = word();
  const herb = `zorbo${word()}`;
  const root = `quimby${word()}`;
  await bringIn(page, tag, herb, root, true);
  await page.goto('/recipes/drafts?from=mealie');
  await page.getByRole('button', { name: 'By ingredient' }).click();
  const rows = page.getByRole('group', { name: 'Ingredients to answer' }).getByRole('button');
  await rows.filter({ hasText: herb }).click();
  const more = page.getByRole('button', { name: '+ more' });
  await expect(more).toHaveAttribute('aria-expanded', 'false');
  const ways = page.waitForResponse((r) => r.url().includes('/api/v1/recipes/drafts/by-food/lines?key='));
  await more.click();
  expect((await ways).status()).toBe(200);
  for (const written of [`2 tbsp ${herb}`, `${herb}, dark`, `a pinch of ${herb}`]) {
    await expect(page.getByText(written, { exact: true })).toBeVisible();
  }
  await expectNoSidewaysScroll(page);
  await checkPage(page);
  await page.getByRole('button', { name: 'Show fewer' }).click();
  await expect(page.getByRole('button', { name: '+ more' })).toBeVisible();
});
