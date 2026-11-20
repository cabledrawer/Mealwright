import { test, expect, type Page } from './clock.ts';
import { mkdirSync } from 'node:fs';
import { join } from 'node:path';
import { checkPage, isPhone, setAccountTheme } from './a11y.ts';

// Settings (0.8, S1; F252: each item its own page, a list beside it): the list, Meal slots, Shops & places and Recent changes, against the
// real server, signed in as the test admin. A member (who cannot see Meal slots) is covered by
// the server's own permission tests (backend/tests/test_settings_lists.py) and the unit test
// that hides the section, because the app has no way to add a member until 0.9.
// Cooking, importing, planning and the pantry's Undo from Recent changes are in cooked.spec.ts,
// import.spec.ts and below. Runs in the "phone 0.8 settings" and "desktop 0.8 settings" projects.

const key = () => ({ 'idempotency-key': crypto.randomUUID() });
const stamp = () => `${test.info().project.name.split(' ')[0]} ${Date.now()}`;

type Json = Record<string, any>; // eslint-disable-line @typescript-eslint/no-explicit-any

async function makeFood(page: Page, name: string, extra: Json = {}) {
  const response = await page.request.post('/api/v1/foods', {
    data: { name, counted_as: 'weight', ...extra },
    headers: key(),
  });
  expect(response.status(), await response.text()).toBe(201);
  return ((await response.json()) as { food: { id: number; name: string } }).food;
}

async function stock(page: Page, foodId: number, placeId: number, grams = 100) {
  const response = await page.request.post('/api/v1/stock', {
    data: { food_id: foodId, amount: { amount: grams, unit: 'g' }, place_id: placeId },
    headers: key(),
  });
  expect(response.status(), await response.text()).toBe(201);
}

async function placeId(page: Page, name: string) {
  const places = (await (await page.request.get('/api/v1/places')).json()) as Json[];
  return places.find((p) => p.name === name)!.id as number;
}

const section = (page: Page, name: string) => page.getByRole('region', { name, exact: true });
// A past day of its own for each project and test: other specs (and this one on the other
// project) cook today's meals, and a meal that has been dealt with can't be planned again.
const OWN_DAY: Record<string, number> = { phone: 0, desktop: 1 };
function ownDay(today: string, offset: number): string {
  const d = new Date(`${today}T12:00:00Z`);
  d.setUTCDate(d.getUTCDate() - (60 + 2 * offset + (OWN_DAY[test.info().project.name.split(' ')[0]] ?? 0)));
  return d.toISOString().slice(0, 10);
}
const rowOf = (page: Page, within: string, name: string) =>
  section(page, within).getByRole('listitem').filter({ hasText: name });

/** The toast's Undo, then its "Undone: …" answer. */
async function undoFromToast(page: Page, words: RegExp | string) {
  await page.getByRole('status').getByRole('button', { name: 'Undo' }).click();
  await expect(page.getByRole('status').filter({ hasText: words })).toBeVisible();
}

test.beforeEach(async ({ page }) => {
  await setAccountTheme(page, 'auto');
});

test('the list of Settings sits beside the page, one item each, the open one marked, and the page passes the accessibility checks', async ({
  page,
}) => {
  test.skip(isPhone(page), 'the phone has its own grouped list (next test)');
  // /settings opens the first item (F252).
  await page.goto('/settings');
  await expect(page).toHaveURL(/\/settings\/appearance$/);
  const list = page.getByRole('navigation', { name: 'Settings', exact: true });
  await expect(list.getByRole('link').filter({ hasNotText: 'Finish setup' })).toHaveText([
    'Appearance',
    'Amounts',
    'Your sign-in',
    'Meal slots',
    'Shops & places',
    'Your kitchen',
    'People',
    'Sign-in for everyone',
    'API tokens',
    'Outside connections',
    'Backups & your data',
    'Recent changes',
    'About',
  ]);
  for (const group of ['Your settings', 'Kitchen settings', 'Household settings', 'Mealwright']) {
    await expect(list.getByRole('group', { name: group })).toBeVisible();
  }
  await expect(list.getByRole('link', { name: 'Appearance' })).toHaveAttribute('aria-current', 'page');
  // The main menu has folded to its icons, each with a name and a tooltip.
  const side = page.getByRole('complementary', { name: 'Sidebar' });
  await expect(side.getByText('Mealwright', { exact: true })).toHaveCount(0);
  await expect(side.getByRole('link', { name: 'Today', exact: true })).toHaveAttribute('title', 'Today');
  for (const link of await list.getByRole('link').all()) {
    expect((await link.boundingBox())!.height).toBeGreaterThanOrEqual(44);
  }
  const box = (await list.boundingBox())!;
  expect(box.x).toBeLessThan(300);
  await list.getByRole('link', { name: 'Shops & places' }).click();
  await expect(page).toHaveURL(/\/settings\/shops-places$/);
  await expect(list.getByRole('link', { name: 'Shops & places' })).toHaveAttribute('aria-current', 'page');
  await expect(list.getByRole('link', { name: 'Appearance' })).not.toHaveAttribute('aria-current');
  await expect(page.getByRole('heading', { name: 'Shops & places', level: 1 })).toBeVisible();
  // Only this item's page: nothing of Recent changes or Meal slots beside it.
  await expect(section(page, 'Recent changes')).toHaveCount(0);
  await expect(section(page, 'Meal slots')).toHaveCount(0);
  await checkPage(page);
  // An older link names a section: it goes to that item's page.
  await page.goto('/settings?section=recent-changes');
  await expect(page).toHaveURL(/\/settings\/recent-changes$/);
  await expect(section(page, 'Recent changes')).toBeVisible();
  await page.goto('/settings#about');
  await expect(page).toHaveURL(/\/settings\/about$/);
});

test('F193, F252: the phone lists Settings in four groups, each row opens its own page, with ‹ Settings back', async ({
  page,
}) => {
  test.skip(!isPhone(page), 'the phone’s layout');
  await page.goto('/settings');
  await expect(page.getByRole('heading', { level: 1, name: 'Settings' })).toBeVisible();
  // An admin whose household hasn't finished set-up has "Finish setup" first (cabledrawer 12 Nov).
  const unfinished = (await (await page.request.get('/api/v1/household')).json()).onboarding_done === false;
  // The groups, in order, with their rows (Amounts shows once the household has answered).
  for (const [group, rows] of [
    ['Your settings', [...(unfinished ? ['Finish setup'] : []), 'Appearance', 'Amounts', 'Your sign-in']],
    ['Kitchen settings', ['Meal slots', 'Shops & places', 'Your kitchen']],
    [
      'Household settings',
      ['People', 'Sign-in for everyone', 'API tokens', 'Outside connections', 'Backups & your data'],
    ],
    ['Mealwright', ['Recent changes', 'About', 'Report a problem']],
  ] as const) {
    const links = page.getByRole('navigation', { name: group }).getByRole('link');
    await expect(links).toHaveCount(rows.length);
    for (const [i, row] of rows.entries()) {
      await expect(links.nth(i)).toContainText(row);
      expect((await links.nth(i).boundingBox())!.height).toBeGreaterThanOrEqual(44);
    }
  }
  // Current values sit on the rows.
  await expect(page.getByRole('link', { name: /^Appearance/ })).toContainText(/Auto|Light|Dark/);
  await expect(page.getByRole('link', { name: /^Amounts/ })).toContainText(/UK pints|US pints/);
  await expect(page.getByRole('link', { name: /^Meal slots/ })).toContainText(/\d+ on/);
  await expect(page.getByRole('link', { name: /^Shops & places/ })).toContainText(/\d+ shops? · \d+ places?/);
  await expect(page.getByRole('link', { name: /^Your kitchen/ })).toContainText(/\d+ hob rings?/);
  await expect(page.getByRole('link', { name: /^Outside connections/ })).toContainText(/All off|\d+ on/);
  await expect(page.getByRole('link', { name: /^People/ })).toContainText(/\d+ (person|people)/);
  // The list shows no item's own controls.
  await expect(page.getByRole('switch')).toHaveCount(0);
  await checkPage(page);
  // A row opens its item alone, under its own title.
  await page.getByRole('link', { name: /^Meal slots/ }).click();
  await expect(page).toHaveURL(/\/settings\/meal-slots$/);
  await expect(page.getByRole('heading', { level: 1, name: 'Meal slots' })).toBeVisible();
  await expect(section(page, 'Meal slots')).toBeVisible();
  await expect(page.getByRole('region', { name: 'Recent changes' })).toHaveCount(0);
  await checkPage(page);
  // ‹ Settings comes back to the list.
  await page.getByRole('link', { name: 'Settings', exact: true }).first().click();
  await expect(page).toHaveURL(/\/settings$/);
  await expect(page.getByRole('heading', { level: 1, name: 'Settings' })).toBeVisible();
  await expect(page.getByRole('navigation', { name: 'Kitchen settings' })).toBeVisible();
  // Outside connections is its own page; the row goes straight to it.
  await page.getByRole('link', { name: /^Outside connections/ }).click();
  await expect(page).toHaveURL('/settings/privacy');
  // An old link with "#shops-places" opens that item.
  await page.goto('/settings#shops-places');
  await expect(page).toHaveURL(/\/settings\/shops-places$/);
  await expect(page.getByRole('heading', { level: 1, name: 'Shops & places' })).toBeVisible();
});

test('Your kitchen (Batch cook, B1): Settings shows it, Change opens the sheet, Save keeps it for the household, and the sheet passes the accessibility checks', async ({
  page,
}) => {
  await page.goto('/settings/kitchen');
  const kitchen = section(page, 'Your kitchen');
  await expect(kitchen).toBeVisible();
  await expect(kitchen).toContainText(/Hob rings\s*\d+/);
  await kitchen.getByRole('button', { name: 'Change' }).click();
  const sheet = page.getByRole('dialog', { name: 'Your kitchen' });
  await expect(sheet).toBeVisible();
  await expect(sheet).toContainText('Batch cook never plans more at once than your kitchen has.');
  for (const button of await sheet.getByRole('button').all()) {
    expect((await button.boundingBox())!.height).toBeGreaterThanOrEqual(44);
  }
  await checkPage(page);
  await sheet.getByRole('button', { name: 'Fewer hob rings' }).click();
  await sheet.getByRole('button', { name: 'More pressure cookers' }).click();
  await sheet.getByRole('radio', { name: 'No' }).click();
  const before = await (await page.request.get('/api/v1/household/kitchen')).json();
  await sheet.getByRole('button', { name: 'Save' }).click();
  await expect(sheet).toBeHidden();
  const after = await (await page.request.get('/api/v1/household/kitchen')).json();
  expect(after).toEqual({
    hob_rings: before.hob_rings - 1,
    pressure_cookers: before.pressure_cookers + 1,
    oven: false,
    asked: true,
  });
  await expect(kitchen).toContainText(new RegExp(`Hob rings\\s*${after.hob_rings}`));
  await expect(kitchen).toContainText(/Oven\s*No/);
  await expect(kitchen).not.toContainText('Not asked yet');
  // Put it back for the other projects.
  const put = await page.request.patch('/api/v1/household/kitchen', {
    data: { hob_rings: before.hob_rings, pressure_cookers: before.pressure_cookers, oven: before.oven },
    headers: key(),
  });
  expect(put.status()).toBe(200);
});

test('Meal slots: rename, reorder with Move down, switch off, and add; Undo of a rename', async ({ page }) => {
  await page.goto('/settings/meal-slots');
  const slots = section(page, 'Meal slots');
  await expect(slots.getByRole('listitem').first()).toContainText('Breakfast');
  const name = `Elevenses ${stamp()}`;
  // Rename Snack, then take it back with the toast's Undo.
  await slots.getByRole('button', { name: 'Rename Snack' }).click();
  await slots.getByRole('textbox', { name: 'Name of Snack' }).fill(name);
  await page.keyboard.press('Enter');
  await expect(rowOf(page, 'Meal slots', name)).toBeVisible();
  await expect
    .poll(async () => ((await (await page.request.get('/api/v1/meal-slots')).json()) as Json[]).map((s) => s.name))
    .toContain(name);
  await undoFromToast(page, `Undone: Renamed Snack to ${name}`);
  await expect(rowOf(page, 'Meal slots', 'Snack')).toBeVisible();
  // Reorder: Breakfast down, then up again, so the plan is left as it was.
  await slots.getByRole('button', { name: 'Move Breakfast down' }).click();
  await expect(slots.getByRole('listitem').first()).toContainText('Lunch');
  await expect
    .poll(async () => ((await (await page.request.get('/api/v1/meal-slots')).json()) as Json[])[0].name)
    .toBe('Lunch');
  await slots.getByRole('button', { name: 'Move Breakfast up' }).click();
  await expect(slots.getByRole('listitem').first()).toContainText('Breakfast');
  // Now first, its Move up greys out: the keyboard stays on the row, on Move down (review r1 L3).
  await expect(slots.getByRole('button', { name: 'Move Breakfast down' })).toBeFocused();
  // Keyboard: Move down is a real button, reachable by Tab, and works with Enter.
  await slots.getByRole('button', { name: 'Move Lunch down' }).focus();
  await page.keyboard.press('Enter');
  await expect(slots.getByRole('listitem').nth(2)).toContainText('Lunch');
  await slots.getByRole('button', { name: 'Move Lunch up' }).click();
  // Switch Snack on and off: its planned meals are kept either way.
  const snack = slots.getByRole('switch', { name: 'Show Snack in the plan' });
  const was = await snack.isChecked();
  await snack.click();
  await expect(snack).toBeChecked({ checked: !was });
  await snack.click();
  await expect(snack).toBeChecked({ checked: was });
  // No way to remove a meal.
  await expect(slots.getByRole('button', { name: /^Remove/ })).toHaveCount(0);
  await checkPage(page);
});

test('Meal slots: add a meal, last, and switch it off', async ({ page }) => {
  await page.goto('/settings/meal-slots');
  const slots = section(page, 'Meal slots');
  const name = `Supper ${stamp()}`;
  await slots.getByRole('button', { name: '+ New meal' }).click();
  await slots.getByRole('textbox', { name: 'New meal' }).fill(name);
  await slots.getByRole('button', { name: 'Add', exact: true }).click();
  await expect(slots.getByRole('listitem').last()).toContainText(name);
  // The same name again is refused in words.
  await slots.getByRole('button', { name: '+ New meal' }).click();
  await slots.getByRole('textbox', { name: 'New meal' }).fill(name.toLowerCase());
  await slots.getByRole('button', { name: 'Add', exact: true }).click();
  await expect(slots.getByText(/There’s already a meal called/)).toBeVisible();
  // Leave it switched off, so the plan's rows are as they were.
  await slots.getByRole('switch', { name: `Show ${name} in the plan` }).click();
  await expect(slots.getByRole('switch', { name: `Show ${name} in the plan` })).not.toBeChecked();
});

test('Shops: add, rename, reorder; removing one sends its ingredients to Any shop, and Undo brings it back', async ({
  page,
}) => {
  const s = stamp();
  const first = `Aldi ${s}`;
  const second = `Butcher ${s}`;
  await page.goto('/settings/shops-places');
  const shops = section(page, 'Shops');
  for (const name of [first, second]) {
    await shops.getByRole('button', { name: '+ New shop' }).click();
    await shops.getByRole('textbox', { name: 'New shop' }).fill(name);
    await shops.getByRole('button', { name: 'Add', exact: true }).click();
    await expect(rowOf(page, 'Shops', name)).toBeVisible();
  }
  const list = (await (await page.request.get('/api/v1/shops')).json()) as Json[];
  const aldi = list.find((x) => x.name === first)!;
  // An ingredient that is usually bought there.
  const milk = await makeFood(page, `Milk ${s}`, { shop_id: aldi.id });
  // Rename.
  const renamed = `Lidl ${s}`;
  await shops.getByRole('button', { name: `Rename ${first}` }).click();
  await shops.getByRole('textbox', { name: `Name of ${first}` }).fill(renamed);
  await page.keyboard.press('Enter');
  await expect(rowOf(page, 'Shops', renamed)).toBeVisible();
  // Reorder: the second one goes up, above the first.
  await shops.getByRole('button', { name: `Move ${second} up` }).click();
  // Ask the server until the move has landed (the row moves on screen before the server has it).
  await expect
    .poll(async () => {
      const order = ((await (await page.request.get('/api/v1/shops')).json()) as Json[]).map((x) => x.name);
      return order.includes(renamed) && order.indexOf(second) >= 0 && order.indexOf(second) < order.indexOf(renamed);
    })
    .toBe(true);
  await checkPage(page); // before any toast is on screen (a toast can cover a row above)
  // Remove: at once, no "Are you sure?", with Undo.
  await shops.getByRole('button', { name: `Remove ${renamed}` }).click();
  await expect(rowOf(page, 'Shops', renamed)).toHaveCount(0);
  await expect(page.getByRole('status').filter({ hasText: `Removed the shop ${renamed}` })).toBeVisible();
  await expect
    .poll(async () => ((await (await page.request.get(`/api/v1/foods/${milk.id}`)).json()) as Json).shop)
    .toBeNull();
  await undoFromToast(page, `Undone: Removed the shop ${renamed}`);
  await expect(rowOf(page, 'Shops', renamed)).toBeVisible();
  const back = (await (await page.request.get(`/api/v1/foods/${milk.id}`)).json()) as Json;
  expect(back.shop.name).toBe(renamed);
  // Clean up: the shops are removed again (their Undo stays in Recent changes).
  for (const name of [renamed, second]) {
    await shops.getByRole('button', { name: `Remove ${name}` }).click();
    await expect(rowOf(page, 'Shops', name)).toHaveCount(0);
  }
});

test('Places: add with a kind; a place with things in it asks where to move them; Undo puts it all back', async ({
  page,
}) => {
  const s = stamp();
  const name = `Cook shelf ${s}`;
  await page.goto('/settings/shops-places');
  const places = section(page, 'Places at home');
  await places.getByRole('button', { name: '+ New place' }).click();
  await places.getByRole('textbox', { name: 'New place' }).fill(name);
  await places.getByRole('combobox', { name: 'Kind' }).selectOption('cupboard');
  await places.getByRole('button', { name: 'Add', exact: true }).click();
  await expect(rowOf(page, 'Places at home', name)).toContainText('Cupboard');
  const shelf = await placeId(page, name);
  const cupboard = await placeId(page, 'Cupboard');
  // Two ingredients on the shelf, one of them usually kept there.
  const rice = await makeFood(page, `Rice ${s}`, { place_id: shelf });
  const dal = await makeFood(page, `Dal ${s}`);
  await stock(page, rice.id, shelf, 500);
  await stock(page, dal.id, shelf, 300);
  await places.getByRole('button', { name: `Remove ${name}` }).click();
  const ask = page.getByRole('form', { name: `Move things out of ${name}` });
  await expect(ask.getByText(`${name} has 2 things in it. Move them to…`)).toBeVisible();
  await expect(rowOf(page, 'Places at home', name)).toBeVisible(); // still there while asked
  await ask.getByRole('combobox', { name: 'Move them to' }).selectOption({ label: 'Cupboard' });
  await ask.getByRole('button', { name: 'Move and remove' }).click();
  await expect(rowOf(page, 'Places at home', name)).toHaveCount(0);
  await expect(page.getByRole('status').filter({ hasText: `Removed the place ${name}` })).toBeVisible();
  const lots = async () => {
    const pantry = (await (await page.request.get('/api/v1/pantry')).json()) as Json;
    return pantry.places
      .filter((p: Json) => p.groups.some((g: Json) => g.food.id === dal.id))
      .map((p: Json) => p.name);
  };
  // The screen changes at once; the server catches up a moment later.
  await expect.poll(lots).toEqual(['Cupboard']);
  await expect
    .poll(async () => ((await (await page.request.get(`/api/v1/foods/${rice.id}`)).json()) as Json).place.id)
    .toBe(cupboard);
  // Undo: the place is back, with what moved.
  await undoFromToast(page, `Undone: Removed the place ${name}`);
  await expect(rowOf(page, 'Places at home', name)).toBeVisible();
  await expect.poll(lots).toEqual([name]);
  await expect
    .poll(async () => ((await (await page.request.get(`/api/v1/foods/${rice.id}`)).json()) as Json).place.name)
    .toBe(name);
  // Use the stock up so the shelf can be removed again, without a question.
  for (const food of [rice, dal]) {
    const pantry = (await (await page.request.get('/api/v1/pantry')).json()) as Json;
    for (const p of pantry.places) {
      for (const g of p.groups.filter((g: Json) => g.food.id === food.id)) {
        for (const lot of g.lots) await page.request.post(`/api/v1/stock/${lot.id}/use`, { headers: key() });
      }
    }
  }
  await page.reload();
  await places.getByRole('button', { name: `Remove ${name}` }).click();
  await expect(rowOf(page, 'Places at home', name)).toHaveCount(0);
  await checkPage(page);
});

test('Places: the last Fridge and the last Freezer stay, and the screen says why', async ({ page }) => {
  // Other specs add their own fridges and freezers to the shared household; move their things
  // into Fridge and Freezer and remove them, so those two are the last of their kind again.
  const all = (await (await page.request.get('/api/v1/places')).json()) as Json[];
  for (const [kind, keep] of [['fridge', 'Fridge'], ['freezer', 'Freezer']]) {
    const kept = all.find((p) => p.name === keep)!;
    for (const extra of all.filter((p) => p.kind === kind && p.id !== kept.id)) {
      const gone = await page.request.delete(`/api/v1/places/${extra.id}?move_to=${kept.id}`, { headers: key() });
      expect(gone.ok(), await gone.text()).toBe(true);
    }
  }
  await page.goto('/settings/shops-places');
  const places = section(page, 'Places at home');
  await expect(places.getByRole('button', { name: 'Remove Fridge' })).toBeDisabled();
  await expect(places.getByRole('button', { name: 'Remove Freezer' })).toBeDisabled();
  await expect(places.getByText(/Mealwright needs at least one Fridge and one Freezer\./)).toBeVisible();
  // The server refuses too, with its code.
  const fridge = await placeId(page, 'Fridge');
  const refused = await page.request.delete(`/api/v1/places/${fridge}`, { headers: key() });
  expect(refused.status()).toBe(409);
  expect(((await refused.json()) as Json).code).toBe('last_of_kind');
  // Order: Spice rack up, then down again.
  await places.getByRole('button', { name: 'Move Spice rack up' }).click();
  await expect
    .poll(async () => ((await (await page.request.get('/api/v1/places')).json()) as Json[]).map((p) => p.name))
    .not.toEqual(['Fridge', 'Freezer', 'Cupboard', 'Spice rack']);
  await places.getByRole('button', { name: 'Move Spice rack down' }).click();
  await expect
    .poll(async () => ((await (await page.request.get('/api/v1/places')).json()) as Json[]).map((p) => p.name))
    .toEqual(['Fridge', 'Freezer', 'Cupboard', 'Spice rack']);
});

test('Recent changes lists a pantry change, a plan change and a removal, newest first, undoes one, and pages with Show more', async ({
  page,
}) => {
  const s = stamp();
  const food = await makeFood(page, `Lentils ${s}`);
  const cupboard = await placeId(page, 'Cupboard');
  await stock(page, food.id, cupboard, 250); // a pantry change
  const slots = (await (await page.request.get('/api/v1/meal-slots')).json()) as Json[];
  const dinner = slots.find((x) => x.name === 'Dinner')!;
  const today = ((await (await page.request.get('/api/v1/household')).json()) as Json).today as string;
  const planned = await page.request.post('/api/v1/plan/items', {
    data: { date: ownDay(today, 0), slot_id: dinner.id, ingredient_id: food.id },
    headers: key(),
  });
  expect(planned.status(), await planned.text()).toBe(201); // a plan change
  const shop = (await (
    await page.request.post('/api/v1/shops', { data: { name: `Shop ${s}` }, headers: key() })
  ).json()) as Json;
  expect((await page.request.delete(`/api/v1/shops/${shop.id}`, { headers: key() })).ok()).toBe(true);

  await page.goto('/settings/recent-changes');
  const recent = section(page, 'Recent changes');
  const rows = recent.getByRole('listitem');
  await expect(rows.first()).toContainText(`Removed the shop Shop ${s}`);
  await expect(recent.getByText(new RegExp(`Added .*Lentils ${s}`)).first()).toBeVisible();
  await expect(recent.getByText(new RegExp(`Planned .*Lentils ${s}|Lentils ${s}.*Dinner`)).first()).toBeVisible();
  await checkPage(page); // open, before any toast is on screen
  // Undo the removal from the list.
  await recent.getByRole('button', { name: `Undo: Removed the shop Shop ${s}` }).click();
  await expect(page.getByRole('status').filter({ hasText: `Undone: Removed the shop Shop ${s}` })).toBeVisible();
  await expect(recent.getByText(`Undid: Removed the shop Shop ${s}`)).toBeVisible();
  await expect(recent.getByRole('button', { name: `Undo: Removed the shop Shop ${s}` })).toHaveCount(0);
  expect(((await (await page.request.get('/api/v1/shops')).json()) as Json[]).map((x) => x.name)).toContain(`Shop ${s}`);
  // Clean up the plan and the shop.
  const item = ((await planned.json()) as Json).item_id;
  await page.request.delete(`/api/v1/plan/items/${item}`, { headers: key() });
  await page.request.delete(`/api/v1/shops/${shop.id}`, { headers: key() });
  // Show more: more than one page of changes exists after enough of them.
  for (let i = 0; i < 12; i++) {
    const made = await page.request.post('/api/v1/shops', { data: { name: `Paging ${i} ${s}` }, headers: key() });
    const id = ((await made.json()) as Json).id;
    await page.request.delete(`/api/v1/shops/${id}`, { headers: key() });
  }
  await page.reload();
  const more = recent.getByRole('button', { name: 'Show more' });
  await expect(more).toBeVisible();
  const before = await recent.getByRole('listitem').count();
  await more.click();
  await expect.poll(() => recent.getByRole('listitem').count()).toBeGreaterThan(before);
});

test('one Cooked it is one row in Recent changes, with one Undo (cabledrawer 7 Nov)', async ({ page }) => {
  const s = stamp();
  const food = await makeFood(page, `Moong ${s}`);
  await stock(page, food.id, await placeId(page, 'Cupboard'), 800);
  const slots = (await (await page.request.get('/api/v1/meal-slots')).json()) as Json[];
  const dinner = slots.find((x) => x.name === 'Dinner')!;
  const today = ((await (await page.request.get('/api/v1/household')).json()) as Json).today as string;
  const post = async (path: string, data: Json, status: number) => {
    const response = await page.request.post(`/api/v1${path}`, { data, headers: key() });
    expect(response.status(), await response.text()).toBe(status);
    return (await response.json()) as Json;
  };
  const name = `Khichdi ${s}`;
  const recipe = await post('/recipes', { name, serves: 4, lines: [{ words: 'moong', food_id: food.id, amount: 200, unit: 'g' }] }, 201);
  const planned = await post('/plan/items', { date: ownDay(today, 1), slot_id: dinner.id, recipe_id: recipe.id }, 201);
  await post(`/plan/items/${planned.item_id}/cook`, { choices: [] }, 201);
  await post(`/plan/meals/${planned.meal_id}/mark-cooked`, {}, 200); // the meal's own answer, the second change

  await page.goto('/settings/recent-changes');
  const recent = section(page, 'Recent changes');
  await expect(recent.getByRole('listitem').filter({ hasText: new RegExp(`Cooked .*${name}`) })).toHaveCount(1);
  const undo = recent.getByRole('button', { name: new RegExp(`^Undo: Cooked ${name}`) });
  await expect(undo).toHaveCount(1);
  await undo.click();
  await expect(page.getByRole('status').filter({ hasText: `Undone: Cooked ${name}` })).toBeVisible();
  await expect(recent.getByRole('button', { name: new RegExp(`^Undo: Cooked ${name}`) })).toHaveCount(0);
  await page.request.delete(`/api/v1/plan/items/${planned.item_id}`, { headers: key() });
});

test('an ingredient brought back by a Pantry Undo says so in Recent changes, and its removal loses its Undo', async ({
  page,
}) => {
  const food = await makeFood(page, `Lemon ${stamp()}`);
  const stocked = await page.request.post('/api/v1/stock', {
    data: { food_id: food.id, amount: { amount: 100, unit: 'g' } },
    headers: key(),
  });
  expect(stocked.status(), await stocked.text()).toBe(201);
  const lot = ((await stocked.json()) as { groups: { lots: { id: number }[] }[] }).groups[0].lots[0];
  const used = await page.request.post(`/api/v1/stock/${lot.id}/use`, { headers: key() });
  expect(used.ok(), await used.text()).toBe(true);
  const usedId = ((await used.json()) as { change: { id: number } }).change.id;
  const removed = await page.request.delete(`/api/v1/foods/${food.id}`, { headers: key() });
  expect(removed.ok(), await removed.text()).toBe(true);
  // Undo "Used 100 g": the stock goes back, so the ingredient comes back.
  const undone = await page.request.post(`/api/v1/changes/${usedId}/undo`, { headers: key() });
  expect(undone.ok(), await undone.text()).toBe(true);

  await page.goto('/settings/recent-changes');
  const recent = section(page, 'Recent changes');
  await expect(recent.getByText(`${food.name} is back in Ingredients`)).toBeVisible();
  await expect(recent.getByText(`Removed ${food.name} from Ingredients`)).toBeVisible();
  // Neither line has an Undo: the "back" line never does, and the removal no longer stands.
  await expect(recent.getByRole('button', { name: `Undo: ${food.name} is back in Ingredients` })).toHaveCount(0);
  await expect(recent.getByRole('button', { name: `Undo: Removed ${food.name} from Ingredients` })).toHaveCount(0);
});

test('Pantry and Ingredients have no Recent changes of their own', async ({ page }) => {
  await page.goto('/pantry');
  await expect(page.getByRole('heading', { name: 'Pantry', level: 1 })).toBeVisible();
  await expect(page.getByRole('heading', { name: 'Recent changes' })).toHaveCount(0);
  await page.goto('/recipes/ingredients');
  await expect(page.getByRole('heading', { name: 'Ingredients', level: 1 })).toBeVisible();
  await expect(page.getByRole('button', { name: /^Recent changes/ })).toHaveCount(0);
});

test('on the Plan, a member sees the Meals switches greyed, with why (review r1 M1)', async ({ page }) => {
  // The app can't add a member until 0.9, so the signed-in admin is shown as a member here.
  await page.route('**/api/v1/me', async (route) => {
    const response = await route.fetch();
    await route.fulfill({ response, json: { ...(await response.json()), role: 'member' } });
  });
  await page.goto('/plan');
  const meals = page.getByRole('group', { name: 'Meals to show' });
  await expect(meals.getByText('Only an admin can change this.')).toBeVisible();
  for (const button of await meals.getByRole('button').all()) await expect(button).toBeDisabled();
});

test('F175, F176: a change made on its page is in Recent changes when that opens, and Undo from there puts it back', async ({
  page,
}) => {
  // Each item is its own page (F252): the change is made on its page, the line and its Undo are on
  // Recent changes, and the page shows the old state when it is opened again.
  const s = stamp();
  await page.goto('/settings/meal-slots');
  const slots = section(page, 'Meal slots');
  const name = `Midday ${s}`;
  await slots.getByRole('button', { name: 'Rename Snack' }).click();
  await slots.getByRole('textbox', { name: 'Name of Snack' }).fill(name);
  await page.keyboard.press('Enter');
  await expect(rowOf(page, 'Meal slots', name)).toBeVisible();
  await page.goto('/settings/recent-changes');
  const recent = section(page, 'Recent changes');
  await expect(recent.getByText(`Renamed Snack to ${name}`).first()).toBeVisible();
  await recent.getByRole('button', { name: `Undo: Renamed Snack to ${name}` }).click();
  await page.goto('/settings/meal-slots');
  await expect(rowOf(page, 'Meal slots', 'Snack')).toBeVisible();
  await expect(rowOf(page, 'Meal slots', name)).toHaveCount(0);

  // A switch: the same.
  const snack = section(page, 'Meal slots').getByRole('switch', { name: 'Show Snack in the plan' });
  const was = await snack.isChecked();
  await snack.click();
  await expect(snack).toBeChecked({ checked: !was });
  const line = `${was ? 'Hid' : 'Showed'} Snack in the plan`;
  await page.goto('/settings/recent-changes');
  await section(page, 'Recent changes').getByRole('button', { name: `Undo: ${line}` }).first().click();
  await page.goto('/settings/meal-slots');
  await expect(section(page, 'Meal slots').getByRole('switch', { name: 'Show Snack in the plan' })).toBeChecked({
    checked: was,
  });

  // A shop: adding it, removing it, and bringing it back from Recent changes.
  await page.goto('/settings/shops-places');
  const shops = section(page, 'Shops & places');
  const shop = `Corner ${s}`;
  await shops.getByRole('button', { name: '+ New shop' }).click();
  await shops.getByRole('textbox', { name: 'New shop' }).fill(shop);
  await shops.getByRole('button', { name: 'Add', exact: true }).click();
  await expect(rowOf(page, 'Shops & places', shop)).toBeVisible();
  await shops.getByRole('button', { name: `Remove ${shop}` }).click();
  await expect(rowOf(page, 'Shops & places', shop)).toHaveCount(0);
  await page.goto('/settings/recent-changes');
  await expect(section(page, 'Recent changes').getByText(`Removed the shop ${shop}`).first()).toBeVisible();
  await section(page, 'Recent changes').getByRole('button', { name: `Undo: Removed the shop ${shop}` }).click();
  await page.goto('/settings/shops-places');
  await expect(rowOf(page, 'Shops & places', shop)).toBeVisible();
  // Leave it as it was.
  await section(page, 'Shops & places').getByRole('button', { name: `Remove ${shop}` }).click();
  await expect(rowOf(page, 'Shops & places', shop)).toHaveCount(0);
});

test('F178: "+ New shop", "+ New place" and "+ New meal" put the cursor in the name box', async ({ page }) => {
  await page.goto('/settings/shops-places');
  const shops = section(page, 'Shops & places');
  await shops.getByRole('button', { name: '+ New shop' }).click();
  await expect(shops.getByRole('textbox', { name: 'New shop' })).toBeFocused();
  await shops.getByRole('button', { name: 'Cancel' }).click();
  await shops.getByRole('button', { name: '+ New place' }).click();
  await expect(shops.getByRole('textbox', { name: 'New place' })).toBeFocused();
  await page.goto('/settings/meal-slots');
  const slots = section(page, 'Meal slots');
  await slots.getByRole('button', { name: '+ New meal' }).click();
  await expect(slots.getByRole('textbox', { name: 'New meal' })).toBeFocused();
});

test('F192: the footnote under Places at home has a space after “Move them to…”.', async ({ page }) => {
  await page.goto('/settings/shops-places');
  const places = section(page, 'Places at home');
  await expect(
    places.getByText('offers “Move them to…”. Mealwright needs at least one Fridge and one Freezer.'),
  ).toBeVisible();
});

test('F177: Meal slots and Places keep each name whole, down to a narrow column', async ({ page }) => {
  // The computer's column at about 912 px and the phone's at 390 px both broke "Breakfast" and
  // "Cupboard" in two ("Breakfa / st"). Each name sits on one line (a broken word has two boxes).
  await page.setViewportSize({ width: isPhone(page) ? 360 : 912, height: 800 });
  for (const [id, within, name] of [
    ['meal-slots', 'Meal slots', 'Breakfast'],
    ['shops-places', 'Places at home', 'Cupboard'],
  ] as const) {
    await page.goto(`/settings/${id}`);
    const row = rowOf(page, within, name).first();
    await expect(row).toBeVisible();
    const boxes = await row.getByText(name, { exact: true }).first().evaluate((el) => {
      const text = [...el.childNodes].find((n) => n.nodeType === Node.TEXT_NODE) as Text;
      const range = document.createRange();
      range.selectNodeContents(text);
      return range.getClientRects().length;
    });
    expect(boxes, `${name} on one line`).toBe(1);
  }
});

test('F177 (review): a 60-character unbroken name does not push the card sideways', async ({ page }) => {
  await page.setViewportSize({ width: isPhone(page) ? 360 : 912, height: 800 });
  const name = 'W'.repeat(60);
  const made = await page.request.post('/api/v1/shops', { data: { name }, headers: key() });
  expect(made.ok(), await made.text()).toBe(true);
  const id = ((await made.json()) as Json).id;
  try {
    await page.goto('/settings/shops-places');
    const row = rowOf(page, 'Shops', name);
    await expect(row).toBeVisible();
    const card = section(page, 'Shops');
    const [r, c] = [await row.boundingBox(), await card.boundingBox()];
    expect(r!.x + r!.width).toBeLessThanOrEqual(c!.x + c!.width + 1);
    // The name itself stays inside the card, wherever it breaks.
    const words = (await row.getByText(name).boundingBox())!;
    expect(words.x + words.width).toBeLessThanOrEqual(c!.x + c!.width + 1);
    expect(await row.evaluate((el) => el.scrollWidth <= el.clientWidth + 1)).toBe(true);
    expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(
      page.viewportSize()!.width,
    );
  } finally {
    await page.request.delete(`/api/v1/shops/${id}`, { headers: key() });
  }
});

test('Finish setup: an admin who did not finish set-up is not sent to it, and Settings has the row at the top, opening onboarding (cabledrawer 12 Nov)', async ({
  page,
}) => {
  const household = await (await page.request.get('/api/v1/household')).json();
  test.skip(household.onboarding_done !== false, 'this household finished set-up already');
  // Not sent back: the home page stays the home page.
  await page.goto('/');
  await expect(page).not.toHaveURL(/\/onboarding/);
  await page.goto('/settings');
  // A computer opens Appearance, with the list beside it; the phone has the list itself.
  const row = isPhone(page)
    ? page.getByRole('navigation', { name: 'Your settings' }).getByRole('link').first()
    : page.getByRole('navigation', { name: 'Settings', exact: true }).getByRole('link').first();
  await expect(row).toContainText('Finish setup');
  await expect(row).toContainText('A few quick things: amounts, household, shops.');
  expect((await row.boundingBox())!.height).toBeGreaterThanOrEqual(44);
  await checkPage(page);
  await row.click();
  await expect(page).toHaveURL('/onboarding');
});

/** Dark screenshots at four widths for the review, only when E2E_SHOTS_DIR is set (by hand). */
test('screenshots of the Settings list and Amounts, dark (by hand only)', async ({ page }) => {
  const dir = process.env.E2E_SHOTS_DIR;
  test.skip(!dir || !test.info().project.name.startsWith('desktop'), 'by hand, desktop project');
  mkdirSync(dir!, { recursive: true });
  await page.emulateMedia({ colorScheme: 'dark' });
  for (const width of [428, 768, 1100, 1300]) {
    await page.setViewportSize({ width, height: 900 });
    await page.goto('/settings');
    await expect(page.getByRole('link', { name: /^Amounts/ }).first()).toBeVisible(); // Amounts shows once the household has answered
    await page.screenshot({ path: join(dir!, `settings-${width}.png`), fullPage: true });
    await page.goto('/settings/amounts');
    await expect(page.getByRole('region', { name: 'Amounts', exact: true })).toBeVisible();
    await page.screenshot({ path: join(dir!, `settings-amounts-${width}.png`), fullPage: true });
  }
});
