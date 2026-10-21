import { test } from './clock.ts';
import { checkPage, setAccountTheme } from './a11y.ts';

// Accessibility of every page so far (spec "UX — CORE": WCAG AA in both themes, 44 px
// touch targets, no sideways scroll). Runs in the "phone a11y" and "desktop a11y"
// projects, signed in as the test admin. New pages get a line in PAGES.

const PAGES = ['/', '/plan', '/shopping', '/pantry', '/recipes', '/recipes/new', '/settings'];

for (const path of PAGES) {
  test(`${path} passes the accessibility checks`, async ({ page }) => {
    await setAccountTheme(page, 'auto');
    await page.goto(path);
    await page.getByRole('heading', { level: 1 }).waitFor();
    await checkPage(page);
  });
}

test.describe('signed out', () => {
  test.use({ storageState: { cookies: [], origins: [] } });

  test('the sign-in page passes the accessibility checks', async ({ page }) => {
    await page.goto('/sign-in');
    await page.getByRole('heading', { level: 1 }).waitFor();
    await checkPage(page);
  });
});
