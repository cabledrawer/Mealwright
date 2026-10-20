import { expect, test, type Page } from '@playwright/test';
import { PORTS, SHOTS_AUTH_FILE, local } from './servers.ts';

// Saved screenshots (spec "Keeping the UI good", item 6): Pantry, Shopping, All recipes, the recipe page and Ingredients, phone-light
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
// (review/seed-shots.ts, "shots" in servers.ts); the browser's clock fixed; dates from the
// server moved to a fixed "today" (below), because the server uses the real date; animations
// off; the bundled fonts; and nothing on these screens shows a live clock.

/** The day every date on screen is moved to: a Saturday. */
const TODAY = '2026-10-17';
const DAY_MS = 24 * 60 * 60 * 1000;

test.use({
  storageState: SHOTS_AUTH_FILE,
  baseURL: local(PORTS.shots),
  locale: 'en-GB',
  timezoneId: 'Europe/London',
  reducedMotion: 'reduce',
});

const daysBetween = (from: string, to: string) =>
  Math.round((Date.parse(`${to}T12:00:00Z`) - Date.parse(`${from}T12:00:00Z`)) / DAY_MS);

/** Every YYYY-MM-DD in the server's answers moves by the same number of days, so the screen
 *  reads as if the server's today were TODAY ("days left" stay the same). */
async function fixTheDate(page: Page) {
  const real = (await (await page.request.get('/api/v1/household')).json()).today as string;
  const shift = daysBetween(real, TODAY);
  await page.route(/\/api\/v1\//, async (route) => {
    const request = route.request();
    if (request.method() !== 'GET' || (await request.headerValue('accept'))?.includes('event-stream')) {
      return route.continue();
    }
    const response = await route.fetch();
    if (!response.headers()['content-type']?.includes('application/json')) {
      return route.fulfill({ response });
    }
    const body = (await response.text()).replace(/\b(\d{4})-(\d{2})-(\d{2})\b/g, (day) => {
      const moved = new Date(Date.parse(`${day}T12:00:00Z`) + shift * DAY_MS);
      return moved.toISOString().slice(0, 10);
    });
    return route.fulfill({ response, body });
  });
}

async function settle(page: Page) {
  await page.evaluate(() => document.fonts.ready);
  // The photo of the page: nothing under the pointer, no blinking caret.
  await page.mouse.move(0, 0);
}

test.beforeEach(async ({ page }) => {
  await page.clock.setFixedTime(new Date(`${TODAY}T10:00:00Z`));
  await fixTheDate(page);
});

// A request still on its way when the test ends would be reported as an error of the test.
test.afterEach(async ({ page }) => {
  await page.unrouteAll({ behavior: 'ignoreErrors' });
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
