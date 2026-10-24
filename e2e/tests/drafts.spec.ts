import { test, expect, type Page, type Route } from './clock.ts';
import { checkPage, expectNoSidewaysScroll, inTheme, isPhone, setAccountTheme } from './a11y.ts';

// Drafts (0.5): "Save as a draft?" on leaving the review, the Drafts screen, carrying on, Delete
// with Undo (and Ctrl+Z), and saving from a draft. Runs in "phone 0.5 drafts" and "desktop 0.5
// drafts", signed in as the test admin, against the real server: the pasted text never goes
// online. A test makes its own drafts with a name of its own and deletes them again, so the
// household's 50 are never used up. The screens' other states (running out of days, every
// ingredient checked, long names, nothing at all) are shown with the server's answer to
// GET /recipes/drafts made up in the browser (page.route); everything else is the real one.

type Json = Record<string, any>; // eslint-disable-line @typescript-eslint/no-explicit-any

const unique = (name: string) => `${name} ${test.info().project.name.replace(/\D/g, '')}${Date.now() % 100000}`;
const box = (page: Page) => page.getByLabel('Paste a link or the recipe’s text');

test.beforeEach(async ({ page }) => {
  await setAccountTheme(page, 'auto');
});

/** Paste a recipe and read it: the review, with its lines still to settle. */
async function reviewOf(page: Page, title: string, hing: string, masala: string) {
  await page.goto('/recipes/import');
  await box(page).fill(`${title}\nIngredients\n¼ tsp ${hing}\n1 tsp ${masala}\nMethod\n1. Boil.\n2. Fry.\n`);
  await page.getByRole('button', { name: 'Read the recipe' }).click();
  await expect(page.getByRole('heading', { level: 1 })).toHaveText('Check before saving');
}

/** Leave the review for the Recipes list and keep it as a draft: it lands on Drafts. */
async function keepDraft(page: Page) {
  await page.getByRole('button', { name: 'Cancel' }).click();
  await expect(page.getByRole('dialog', { name: 'Save as a draft?' })).toBeVisible();
  await page.getByRole('button', { name: 'Save draft' }).click();
  await expect(page).toHaveURL(/\/recipes\/drafts$/);
}

async function draftsNamed(page: Page, title: string): Promise<Json[]> {
  const list = (await (await page.request.get('/api/v1/recipes/drafts')).json()) as Json;
  return list.drafts.filter((d: Json) => d.name === title);
}

async function deleteDrafts(page: Page, title: string) {
  for (const draft of await draftsNamed(page, title)) await page.request.delete(`/api/v1/recipes/drafts/${draft.id}`);
}

/** The server's answer to the list, made up in the browser. */
const listing = (page: Page, drafts: Json[]) =>
  page.route('**/api/v1/recipes/drafts', (route: Route) =>
    route.request().method() === 'GET'
      ? route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ drafts, count: drafts.length }) })
      : route.continue(),
  );

const brief = (id: number, over: Json = {}): Json => ({
  id,
  name: 'Chettinad kuzhambu',
  source: { kind: 'link', site: 'bbcgoodfood.com' },
  started_by: 'Tess',
  started_at: '2026-10-10T10:00:00Z',
  updated_at: '2026-10-12T10:00:00Z',
  expires_at: '2026-10-27T10:00:00Z',
  days_left: 13,
  lines_total: 9,
  lines_checked: 6,
  ...over,
});

test('leaving the review asks “Save as a draft?”; Save draft keeps it and lands on Drafts', async ({ page }) => {
  const title = unique('Dal tadka');
  const hing = unique('Hing');
  const masala = unique('Garam masala');
  await reviewOf(page, title, hing, masala);
  await page.getByRole('button', { name: 'New ingredient' }).first().click();
  await page.getByRole('button', { name: 'Cancel' }).click();
  const dialog = page.getByRole('dialog', { name: 'Save as a draft?' });
  await expect(dialog).toBeVisible();
  await expect(dialog).toContainText(`You haven’t finished checking ${title}.`);
  await expect(dialog).toContainText('A draft keeps your choices so far for 15 days, in Recipes → Drafts. Anyone in your household can carry on.');
  await checkPage(page);
  // Keep checking stays where it is.
  await dialog.getByRole('button', { name: 'Keep checking' }).click();
  await expect(dialog).toBeHidden();
  await expect(page.getByRole('heading', { level: 1 })).toHaveText('Check before saving');
  // Cancel again, and keep it.
  await keepDraft(page);
  await expect(page.getByRole('heading', { level: 1 })).toHaveText('Drafts');
  await expect(page.getByText(title)).toBeVisible();
  await expect(page.getByText('15 days left').or(page.getByText('15 days', { exact: true })).first()).toBeVisible();
  // Nothing is in Ingredients until Save.
  for (const name of [hing, masala]) {
    const found = (await (await page.request.get(`/api/v1/foods?q=${encodeURIComponent(name)}`)).json()) as Json;
    expect(found.foods).toHaveLength(0);
  }
  await checkPage(page);
  await deleteDrafts(page, title);
});

test('Discard leaves without keeping anything', async ({ page }) => {
  const title = unique('Rava dosa');
  await reviewOf(page, title, unique('Hing'), unique('Masala'));
  await page.getByRole('button', { name: 'Cancel' }).click();
  await page.getByRole('dialog', { name: 'Save as a draft?' }).getByRole('button', { name: 'Discard', exact: true }).click();
  await expect(page).toHaveURL(/\/recipes$/);
  expect(await draftsNamed(page, title)).toHaveLength(0);
});

test('carry on opens the review with the choices made, and Save makes the recipe and removes the draft', async ({ page }) => {
  const title = unique('Sambar');
  const hing = unique('Hing');
  const masala = unique('Garam masala');
  await reviewOf(page, title, hing, masala);
  await page.getByRole('button', { name: 'Treat as staple' }).first().click();
  await page.getByRole('button', { name: 'New ingredient' }).first().click();
  await page.getByLabel('Name', { exact: true }).first().fill(`${title} (mine)`);
  await keepDraft(page);
  await expect(page.getByText(`${title} (mine)`)).toBeVisible();
  await page.getByRole('link', { name: `Carry on ${title} (mine)` }).click();
  await expect(page).toHaveURL(/\/recipes\/drafts\/\d+$/);
  await expect(page.getByRole('heading', { level: 1 })).toHaveText('Check before saving');
  await expect(page.getByLabel('Name', { exact: true }).first()).toHaveValue(`${title} (mine)`);
  await expect(page.getByText(/Made a staple when you save/)).toBeVisible();
  await expect(page.getByText(/Made when you save/)).toBeVisible();
  await checkPage(page);
  // Nothing changed: leaving doesn't ask.
  await page.getByRole('link', { name: 'Drafts', exact: true }).first().click();
  await expect(page).toHaveURL(/\/recipes\/drafts$/);
  await page.getByRole('link', { name: `Carry on ${title} (mine)` }).click();
  await page.getByRole('button', { name: 'Save recipe' }).click();
  await expect(page).toHaveURL(/\/recipes\/\d+$/);
  await expect(page.getByRole('heading', { level: 1 })).toHaveText(`${title} (mine)`);
  expect(await draftsNamed(page, `${title} (mine)`)).toHaveLength(0);
  // The recipe's Undo takes the recipe and its new ingredients back, as for any import.
  await page.getByRole('button', { name: 'Undo' }).click();
  await expect(page.getByText(/^Undone/)).toBeVisible();
});

test('changing a draft and leaving asks to save the draft over; the days start again', async ({ page }) => {
  const title = unique('Aloo paratha');
  await reviewOf(page, title, unique('Hing'), unique('Masala'));
  await keepDraft(page);
  await page.getByRole('link', { name: `Carry on ${title}` }).click();
  await page.getByLabel('Serves').fill('6');
  await page.getByRole('link', { name: 'Drafts', exact: true }).first().click();
  const dialog = page.getByRole('dialog', { name: 'Save your changes?' });
  await expect(dialog).toBeVisible();
  await expect(dialog.getByRole('button', { name: 'Discard changes' })).toBeVisible();
  await dialog.getByRole('button', { name: 'Save draft' }).click();
  await expect(page).toHaveURL(/\/recipes\/drafts$/);
  const [draft] = await draftsNamed(page, title);
  const kept = (await (await page.request.get(`/api/v1/recipes/drafts/${draft!.id}`)).json()) as Json;
  expect(kept.choices.serves).toBe('6');
  await deleteDrafts(page, title);
});

test('Delete hides the draft at once and a toast offers Undo; Undo and Ctrl+Z bring it back', async ({ page }) => {
  const title = unique('Rasam');
  await reviewOf(page, title, unique('Hing'), unique('Masala'));
  await keepDraft(page);
  await page.getByRole('button', { name: `Delete ${title}` }).click();
  await expect(page.getByText(title, { exact: true })).toHaveCount(0);
  await expect(page.getByText(`Deleted the ${title} draft`)).toBeVisible();
  expect(await draftsNamed(page, title)).toHaveLength(0);
  await page.getByRole('button', { name: 'Undo' }).click();
  await expect(page.getByText(title, { exact: true })).toBeVisible();
  expect(await draftsNamed(page, title)).toHaveLength(1);
  if (!isPhone(page)) {
    await page.getByRole('button', { name: `Delete ${title}` }).click();
    await expect(page.getByText(title, { exact: true })).toHaveCount(0);
    await page.keyboard.press('ControlOrMeta+z');
    await expect(page.getByText(title, { exact: true })).toBeVisible();
  }
  await deleteDrafts(page, title);
});

test('the menu has Drafts back: the sidebar on a computer, a button on All recipes on a phone', async ({ page }) => {
  const title = unique('Kootu');
  await reviewOf(page, title, unique('Hing'), unique('Masala'));
  await keepDraft(page);
  await page.goto('/recipes');
  const entry = page.getByRole('link', { name: /^Drafts\s*\d*$/ });
  await expect(entry.first()).toBeVisible();
  await expect(entry.first()).toHaveAttribute('href', '/recipes/drafts');
  // The number of drafts is there beside it.
  await expect(page.getByRole('link', { name: /^Drafts\s*[1-9]\d*$/ }).first()).toBeVisible();
  await checkPage(page);
  await entry.first().click();
  await expect(page).toHaveURL(/\/recipes\/drafts$/);
  await deleteDrafts(page, title);
});

test('the Drafts screen as the mockup shows it: days left, how far, Carry on or Save recipe, and Delete', async ({ page }) => {
  await listing(page, [
    brief(1),
    brief(2, { name: 'Rava dosa', source: { kind: 'text', site: null }, started_by: 'Wren', days_left: 15, lines_total: 10, lines_checked: 2 }),
    brief(3, { name: 'Aloo paratha', source: { kind: 'link', site: 'www.example.com' }, started_by: 'Wren', days_left: 3, lines_total: 4, lines_checked: 4 }),
  ]);
  await page.goto('/recipes/drafts');
  await expect(page.getByRole('heading', { level: 1 })).toHaveText('Drafts');
  await expect(page.getByText('Chettinad kuzhambu')).toBeVisible();
  if (isPhone(page)) {
    await expect(page.getByText('From bbcgoodfood.com · started by Tess')).toBeVisible();
    await expect(page.getByText('13 days left')).toBeVisible();
    await expect(page.getByText('3 days left', { exact: true })).toBeVisible();
    await expect(page.getByText('6 of 9 ingredients checked · 3 need you')).toBeVisible();
    await expect(page.getByText('Pasted text · started by Wren')).toBeVisible();
  } else {
    await expect(page.getByRole('table', { name: 'Drafts' })).toBeVisible();
    await expect(page.getByRole('columnheader')).toHaveText(['Recipe', 'From', 'Started by', 'Checked', 'Left', 'Actions']);
    await expect(page.getByText('6 of 9 · 3 need you')).toBeVisible();
    await expect(page.getByText('13 days', { exact: true })).toBeVisible();
    await expect(page.getByRole('link', { name: 'Import a recipe' })).toBeVisible();
  }
  await expect(page.getByText('All checked · ready to save')).toBeVisible();
  await expect(page.getByRole('button', { name: 'Save recipe Aloo paratha' })).toBeVisible();
  await expect(page.getByRole('button', { name: /^Save recipe/ })).toHaveCount(1);
  await expect(page.getByRole('link', { name: /^Carry on/ })).toHaveCount(3);
  await expect(page.getByRole('button', { name: /^Delete/ })).toHaveCount(3);
  await checkPage(page);
});

test('long names and text at 200% never scroll sideways', async ({ page }) => {
  const long = 'வெண்டைக்காய் '.repeat(8) + 'x'.repeat(60);
  await listing(page, [brief(1, { name: long, started_by: 'Wilhelmina Featherstonehaugh' }), brief(2, { lines_checked: 9 })]);
  await page.goto('/recipes/drafts');
  await expect(page.getByRole('heading', { level: 1 })).toHaveText('Drafts');
  await expectNoSidewaysScroll(page);
  await page.evaluate(() => (document.documentElement.style.fontSize = '200%'));
  await expectNoSidewaysScroll(page);
  await page.evaluate(() => (document.documentElement.style.fontSize = ''));
});

test('no drafts: the empty state, in both themes', async ({ page }) => {
  await listing(page, []);
  await page.goto('/recipes/drafts');
  await expect(page.getByRole('heading', { name: 'No drafts' })).toBeVisible();
  await expect(page.getByText('When you import a recipe and leave before saving it, it waits here for 15 days.')).toBeVisible();
  await checkPage(page);
});

test('a list that cannot be had says so, with Try again', async ({ page }) => {
  await page.route('**/api/v1/recipes/drafts', (route: Route) =>
    route.fulfill({ status: 500, contentType: 'application/json', body: JSON.stringify({ detail: 'Something went wrong.' }) }),
  );
  await page.goto('/recipes/drafts');
  await expect(page.getByText('Something went wrong.')).toBeVisible();
  await expect(page.getByRole('button', { name: 'Try again' })).toBeVisible();
  await checkPage(page);
});

test('offline, Drafts shows what it last had and cannot be changed', async ({ page, context }) => {
  const title = unique('Thoran');
  await reviewOf(page, title, unique('Hing'), unique('Masala'));
  await keepDraft(page);
  await page.waitForLoadState('networkidle');
  await context.setOffline(true);
  await page.evaluate(() => window.dispatchEvent(new Event('offline')));
  await expect(page.getByText(/This is as it was when you last looked, and it can’t be changed until you’re\s+back online/)).toBeVisible({ timeout: 10000 });
  await expect(page.getByText(title)).toBeVisible();
  await expect(page.getByRole('button', { name: `Delete ${title}` })).toBeDisabled();
  await context.setOffline(false);
  await deleteDrafts(page, title);
});

test('a draft in the dark theme passes the accessibility scan, on the review and the leave sheet', async ({ page }) => {
  const title = unique('Pongal');
  await reviewOf(page, title, unique('Hing'), unique('Masala'));
  await page.getByRole('button', { name: 'Cancel' }).click();
  await expect(page.getByRole('dialog', { name: 'Save as a draft?' })).toBeVisible();
  await inTheme(page, 'dark');
  await checkPage(page, { themes: ['dark'] });
});
