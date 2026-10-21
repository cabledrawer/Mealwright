import { FIXED_DAY, FIXED_MOMENT, expect, test, type Page } from './clock.ts';
import { PORTS, SHOTS_AUTH_FILE, local } from './servers.ts';

// Saved screenshots (spec "Keeping the UI good", item 6): Pantry, Shopping, All recipes, the recipe page,
// Ingredients and the recipe editor (New recipe and Edit recipe), phone-light
// (390 × 844) and desktop-dark (1440 × 900), both taken at two device pixels per screen pixel
// (so the images are 780 × 1688 and 2880 × 1800), each compared with the approved image saved in
// tests/screens.spec.ts-snapshots/. ./check fails if one changes.
//
// When a change to how a screen looks is meant, update the images and say so in the pull
// request, so the checker can look at the before and after:
//
//   cd e2e && E2E_APP_PORT=18300 npx playwright test tests/screens.spec.ts --update-snapshots
//
// What keeps them the same every time: their own server with fixed test data
// (review/seed-shots.ts, "shots" in servers.ts); one fixed date and time for the server and the
// browser (tests/clock.ts), with the browser's clock stopped there; animations off; the
// bundled fonts; and nothing on these screens shows a live clock.

test.use({
  storageState: SHOTS_AUTH_FILE,
  baseURL: local(PORTS.shots),
  locale: 'en-GB',
  timezoneId: 'Europe/London',
  reducedMotion: 'reduce',
});

async function settle(page: Page) {
  await page.evaluate(() => document.fonts.ready);
  // The photo of the page: nothing under the pointer, no blinking caret.
  await page.mouse.move(0, 0);
}

test.beforeEach(async ({ page }) => {
  await page.clock.setFixedTime(FIXED_MOMENT);
});

test('the server and the browser are on the tests’ fixed day', async ({ page }) => {
  const { today } = (await (await page.request.get('/api/v1/household')).json()) as { today: string };
  expect(today).toBe(FIXED_DAY);
  await page.goto('/pantry');
  expect(await page.evaluate(() => new Date().toLocaleDateString('en-CA', { timeZone: 'Europe/London' }))).toBe(FIXED_DAY);
});

test('Pantry looks the way it was approved', async ({ page }) => {
  await page.goto('/pantry');
  await expect(page.getByRole('heading', { name: 'Pantry', level: 1 })).toBeVisible();
  await expect(page.getByText('Toor dal').first()).toBeVisible();
  await settle(page);
  await expect(page).toHaveScreenshot('pantry.png', { scale: 'device' });
});

test('Shopping looks the way it was approved', async ({ page }) => {
  await page.goto('/shopping');
  await expect(page.getByRole('heading', { name: 'Shopping', level: 1 })).toBeVisible();
  await expect(page.getByText('10 to buy')).toBeVisible();
  await expect(page.getByText(/· saved$/)).toBeVisible();
  await settle(page);
  await expect(page).toHaveScreenshot('shopping.png', { scale: 'device' });
});

test('All recipes looks the way it was approved', async ({ page }) => {
  await page.goto('/recipes');
  await expect(page.getByRole('heading', { name: 'Recipes', level: 1 })).toBeVisible();
  await expect(page.getByText('6 recipes')).toBeVisible();
  await expect(page.getByText('Uses spinach (today)')).toBeVisible();
  await settle(page);
  await expect(page).toHaveScreenshot('recipes.png', { scale: 'device' });
});

test('The recipe page looks the way it was approved', async ({ page }) => {
  await page.goto('/recipes');
  await page.getByRole('link', { name: /^Sambar/ }).click();
  await expect(page.getByRole('heading', { name: 'Sambar', level: 1 })).toBeVisible();
  await expect(page.getByText('1 missing')).toBeVisible();
  await expect(page.getByText('Cupboard').first()).toBeVisible();
  await settle(page);
  await expect(page).toHaveScreenshot('recipe.png', { scale: 'device' });
});

test('Ingredients looks the way it was approved', async ({ page }) => {
  await page.goto('/recipes/ingredients');
  await expect(page.getByRole('heading', { name: 'Ingredients', level: 1 })).toBeVisible();
  await expect(page.getByRole('button', { name: /^Not in any recipe · \d+$/ })).toBeVisible();
  // Some rows say how many recipes use them, and on a computer the first one's editor lists them.
  await expect(page.getByText(/^Used in \d+ recipes?$/).first()).toBeAttached();
  if (page.viewportSize()!.width >= 768) {
    await expect(page.getByRole('complementary', { name: /^Edit/ }).getByRole('heading', { name: /^Used in/ })).toBeVisible();
  }
  await settle(page);
  await expect(page).toHaveScreenshot('ingredients.png', { scale: 'device' });
});

test('New recipe looks the way it was approved', async ({ page }) => {
  await page.goto('/recipes/new');
  await expect(page.getByRole('heading', { name: 'New recipe', level: 1 })).toBeVisible();
  await settle(page);
  await expect(page).toHaveScreenshot('new-recipe.png', { scale: 'device' });
});

test('Edit recipe looks the way it was approved', async ({ page }) => {
  // The seeded Sambar, as in the mockups, opened the way people open it: its page, then Edit.
  // (A Sambar of its own would be a second one in All recipes and the computer's list pane.)
  await page.goto('/recipes');
  await page.getByRole('link', { name: /^Sambar/ }).click();
  await expect(page.getByRole('heading', { name: 'Sambar', level: 1 })).toBeVisible();
  await page.getByRole('link', { name: 'Edit', exact: true }).click();
  await expect(page.getByRole('heading', { name: 'Edit recipe', level: 1 })).toBeVisible();
  await expect(page.getByRole('textbox', { name: 'Name', exact: true })).toHaveValue('Sambar');
  await expect(page.getByRole('textbox', { name: 'Step 4', exact: true })).toHaveValue(/mustard-seed tempering/);
  await settle(page);
  await expect(page).toHaveScreenshot('edit-recipe.png', { scale: 'device' });
});
