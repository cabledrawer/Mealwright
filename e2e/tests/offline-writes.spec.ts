import { test, expect, type Page } from './clock.ts';

// FE12 and F264: offline, every button that only the server can act on is greyed out (or says why
// when tapped), and "New recipe" is one of them. One screen from each section; the shopping list
// is the one place that keeps working (offline.spec.ts). Each page is opened with the server up,
// then the device goes offline, so no page has to load offline here.
async function openThenGoOffline(page: Page, path: string) {
  await page.goto(path);
  await expect(page.getByRole('heading', { level: 1 })).toBeVisible();
  await page.waitForLoadState('networkidle');
  await page.context().setOffline(true);
}

test.afterEach(async ({ page }) => {
  await page.context().setOffline(false);
});

test('Recipes: “New recipe” is greyed out offline and opens nothing (F264)', async ({ page }) => {
  await openThenGoOffline(page, '/recipes');
  const button = page.getByRole('button', { name: 'New recipe' });
  await expect(button).toBeDisabled();
  await button.click({ force: true });
  await expect(page.getByRole('dialog')).toHaveCount(0);
  await page.context().setOffline(false);
  await expect(button).toBeEnabled();
});

test('Settings: the shops and places add buttons are greyed out offline', async ({ page }) => {
  await openThenGoOffline(page, '/settings/shops-places');
  for (const add of await page.getByRole('button', { name: 'Add', exact: true }).all()) {
    await expect(add).toBeDisabled();
  }
});

test('Settings: your kitchen cannot be changed offline', async ({ page }) => {
  await openThenGoOffline(page, '/settings/kitchen');
  await expect(page.getByRole('button', { name: 'Change', exact: true })).toBeDisabled();
});
