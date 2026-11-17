import { test, expect, type Page } from './clock.ts';
import { checkPage, isPhone, setAccountTheme } from './a11y.ts';

// Settings' layout (beta 2, B8, F252): on a computer the main menu folds to its icons and the
// grouped list of Settings sits beside the page, the open item marked; on the phone /settings is
// that list and each row opens its own page with ‹ Settings back. The Household group is for
// admins only: a member isn't shown it, and an address in it says "Only admins can change this."
// with nothing of it loaded. The settings themselves are in settings.spec.ts and the specs of each
// page. Runs in the "phone beta2 settings layout" and "desktop beta2 settings layout" projects.

const HOUSEHOLD_ITEMS = [
  'People',
  'Sign-in for everyone',
  'API tokens',
  'Outside connections',
  'Backups & your data',
];

test.beforeEach(async ({ page }) => {
  await setAccountTheme(page, 'auto');
});

/** The signed-in admin, shown as a member (the app has no member in these tests' household). */
async function asMember(page: Page) {
  await page.route('**/api/v1/me', async (route) => {
    const response = await route.fetch();
    await route.fulfill({ response, json: { ...(await response.json()), role: 'member' } });
  });
}

const list = (page: Page) => page.getByRole('navigation', { name: 'Settings', exact: true });

test('a computer: the main menu folds to icons with names and tooltips, and the list sits beside the page', async ({
  page,
}) => {
  test.skip(isPhone(page), 'the computer’s layout');
  await page.goto('/settings/amounts');
  await expect(page.getByRole('heading', { level: 1, name: 'Amounts' })).toBeVisible();
  const side = page.getByRole('complementary', { name: 'Sidebar' });
  // Folded: no words, but each icon has its name and a tooltip.
  await expect(side.getByText('Mealwright', { exact: true })).toHaveCount(0);
  for (const name of ['Today', 'Plan', 'Shopping', 'Pantry']) {
    const link = side.getByRole('link', { name, exact: true });
    await expect(link).toHaveAttribute('title', name);
    await expect(link).toHaveAttribute('aria-label', name);
  }
  // The list is beside the page, to the right of the folded menu, the open item marked.
  const sideBox = (await side.boundingBox())!;
  const listBox = (await list(page).boundingBox())!;
  expect(listBox.x).toBeGreaterThanOrEqual(sideBox.x + sideBox.width - 1);
  const content = (await page.getByRole('heading', { level: 1, name: 'Amounts' }).boundingBox())!;
  expect(content.x).toBeGreaterThan(listBox.x + listBox.width - 1);
  await expect(list(page).getByRole('link', { name: 'Amounts', exact: true })).toHaveAttribute('aria-current', 'page');
  await expect(list(page).getByRole('link', { name: 'Appearance', exact: true })).not.toHaveAttribute('aria-current');
  await checkPage(page);
  // The way back to the app: the menu opens out again on any other page.
  await side.getByRole('link', { name: 'Show the menu' }).click();
  await expect(page).toHaveURL('/');
  await expect(side.getByRole('link', { name: 'Today', exact: true })).toContainText('Today');
});

test('a computer: /settings opens Appearance, and each item shows only its own page', async ({ page }) => {
  test.skip(isPhone(page), 'the computer’s layout');
  await page.goto('/settings');
  await expect(page).toHaveURL('/settings/appearance');
  await expect(page.getByRole('heading', { level: 1, name: 'Appearance' })).toBeVisible();
  for (const [item, path] of [
    ['Amounts', '/settings/amounts'],
    ['Your sign-in', '/settings/sign-in'],
    ['Meal slots', '/settings/meal-slots'],
    ['Your kitchen', '/settings/kitchen'],
    ['People', '/settings/household'],
    ['Sign-in for everyone', '/settings/sign-in-everyone'],
    ['API tokens', '/settings/api-tokens'],
    ['Outside connections', '/settings/privacy'],
    ['Backups & your data', '/settings/your-data'],
    ['Recent changes', '/settings/recent-changes'],
    ['About', '/settings/about'],
  ] as const) {
    await list(page).getByRole('link', { name: item, exact: true }).click();
    await expect(page).toHaveURL(path);
    await expect(page.getByRole('heading', { level: 1, name: item })).toBeVisible();
    await expect(list(page).getByRole('link', { name: item, exact: true })).toHaveAttribute(
      'aria-current',
      'page',
    );
    await expect(list(page).locator('[aria-current="page"]')).toHaveCount(1);
  }
});

test('older links still work: an anchor or a section name goes to its item', async ({ page }) => {
  for (const [old, now] of [
    ['/settings#about', '/settings/about'],
    ['/settings#shops-places', '/settings/shops-places'],
    ['/settings?section=household', '/settings/household'],
    ['/settings?section=sign-in', '/settings/sign-in'],
    ['/settings?section=privacy', '/settings/privacy'],
    ['/settings?section=your-data', '/settings/your-data'],
  ] as const) {
    await page.goto(old);
    await expect(page, old).toHaveURL(now);
  }
});

test('a phone: /settings is the grouped list, a row opens its own page, ‹ Settings comes back', async ({
  page,
}) => {
  test.skip(!isPhone(page), 'the phone’s layout');
  await page.goto('/settings');
  await expect(page).toHaveURL('/settings');
  await expect(page.getByRole('heading', { level: 1, name: 'Settings' })).toBeVisible();
  for (const group of ['Your settings', 'Kitchen settings', 'Household settings', 'Mealwright']) {
    await expect(page.getByRole('navigation', { name: group })).toBeVisible();
  }
  await checkPage(page);
  await page.getByRole('link', { name: /^Backups & your data/ }).click();
  await expect(page).toHaveURL('/settings/your-data');
  await expect(page.getByRole('heading', { level: 1, name: 'Backups & your data' })).toBeVisible();
  await page.getByRole('link', { name: 'Settings', exact: true }).first().click();
  await expect(page).toHaveURL('/settings');
  // A page under an item goes back to the item, not to the list.
  await page.goto('/settings/your-data/restore');
  await page.getByRole('link', { name: 'Backups & your data' }).first().click();
  await expect(page).toHaveURL('/settings/your-data');
});

test('a member is not shown the Household group, and an address in it says only admins can change it', async ({
  page,
}) => {
  await asMember(page);
  const asked: string[] = [];
  page.on('request', (request) => asked.push(new URL(request.url()).pathname));
  await page.goto('/settings');
  if (isPhone(page)) {
    await expect(page.getByRole('heading', { level: 1, name: 'Settings' })).toBeVisible();
    await expect(page.getByRole('link', { name: /^Appearance/ })).toBeVisible();
    await expect(page.getByRole('navigation', { name: 'Household settings' })).toHaveCount(0);
    for (const item of HOUSEHOLD_ITEMS) {
      await expect(page.getByRole('link', { name: new RegExp(`^${item}`) })).toHaveCount(0);
    }
    await checkPage(page);
  } else {
    await expect(page).toHaveURL('/settings/appearance');
    await expect(list(page).getByRole('link', { name: 'Appearance', exact: true })).toBeVisible();
    await expect(list(page).getByRole('group', { name: 'Household settings' })).toHaveCount(0);
    for (const item of HOUSEHOLD_ITEMS) {
      await expect(list(page).getByRole('link', { name: item, exact: true })).toHaveCount(0);
    }
  }
  await expect(page.getByText('admins only')).toHaveCount(0);
  asked.length = 0;
  for (const path of [
    '/settings/household',
    '/settings/sign-in-everyone',
    '/settings/api-tokens',
    '/settings/privacy',
    '/settings/your-data',
  ]) {
    await page.goto(path);
    await expect(page.getByText('Only admins can change this.'), path).toBeVisible();
    await expect(page.getByRole('switch')).toHaveCount(0);
  }
  await checkPage(page);
  // Nothing of the Household group was asked for.
  expect(asked.filter((p) => /\/api\/v1\/(people|privacy|api-tokens|sso|backups|export)/.test(p))).toEqual([]);
});
