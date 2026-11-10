import { test, expect, type Page } from './clock.ts';
import { checkPage, setAccountTheme } from './a11y.ts';

// Check screen, F111 (0.7): change a step's words, take a step out, Undo; nothing is kept until
// Save. Runs on Chromium (phone and computer) and WebKit, see playwright.config.ts. The recipe is
// pasted (the path that never goes online); Save and the recipe page are the real server's.

test.use({ serviceWorkers: 'block' });

const unique = (name: string) => `${name} ${test.info().project.name.replace(/\D/g, '')}${Date.now() % 100000}`;

test.beforeEach(async ({ page }) => {
  await setAccountTheme(page, 'auto');
});

/** A pasted recipe with three steps, on the Check screen. */
async function checking(page: Page, title: string, ingredient: string) {
  await page.goto('/recipes/import');
  await page
    .getByLabel('Paste a link or the recipe’s text')
    .fill(`${title}\nIngredients\n1 cup ${ingredient}\nMethod\n1. Soak the rice.\n2. Fry the onion.\n3. Add the spices.\n`);
  await page.getByRole('button', { name: 'Read the recipe' }).click();
  await expect(page.getByRole('heading', { level: 1 })).toHaveText('Check before saving');
  await expect(page.getByText('Method · 3 steps found')).toBeVisible();
}

test('tap a step to change its words: Enter is Done, Escape is Cancel, an empty step offers Remove', async ({ page }) => {
  await checking(page, unique('Pilau'), unique('Rice'));
  await checkPage(page);
  await page.getByRole('button', { name: /^Change step 2/ }).click();
  const words = page.getByRole('textbox', { name: 'Words of step 2' });
  await expect(words).toBeFocused();
  await words.fill('Burn the onion.');
  await page.keyboard.press('Escape');
  await expect(page.getByRole('button', { name: 'Change step 2: Fry the onion.' })).toBeFocused();
  await page.getByRole('button', { name: /^Change step 2/ }).click();
  await words.fill('   ');
  await page.keyboard.press('Enter');
  await expect(page.getByRole('alert').getByText(/can’t be empty/)).toBeVisible();
  await words.fill('Fry the onion until golden.');
  await page.keyboard.press('Enter');
  await expect(page.getByRole('button', { name: 'Change step 2: Fry the onion until golden.' })).toBeFocused();
});

test('Remove step has Undo, putting it back in place; Save keeps the edited method and nothing sooner', async ({ page }) => {
  const title = unique('Pilau');
  await checking(page, title, unique('Rice'));
  await page.getByRole('button', { name: /^Change step 3/ }).click();
  await page.getByRole('textbox', { name: 'Words of step 3' }).fill('Add the cumin.');
  await page.getByRole('button', { name: 'Done' }).click();
  await page.getByRole('button', { name: 'Remove step 1' }).click();
  await expect(page.getByText('Method · 2 steps found')).toBeVisible();
  await expect(page.getByText('Removed step 1')).toBeVisible();
  // Undo puts it first again, and the numbers follow.
  await page.getByRole('button', { name: 'Undo', exact: true }).click();
  await expect(page.getByText('Method · 3 steps found')).toBeVisible();
  await expect(page.getByRole('button', { name: 'Change step 1: Soak the rice.' })).toBeVisible();
  // Take the second out for good, then Save: the recipe has the edited method.
  await page.getByRole('button', { name: 'Remove step 2' }).click();
  await expect(page.getByText('Method · 2 steps found')).toBeVisible();
  await page.getByRole('button', { name: 'New ingredient' }).first().click();
  await page.getByRole('button', { name: 'Save recipe' }).click();
  await expect(page).toHaveURL(/\/recipes\/\d+$/);
  await expect(page.getByText('Soak the rice.')).toBeVisible();
  await expect(page.getByText('Add the cumin.')).toBeVisible();
  await expect(page.getByText('Fry the onion.')).toHaveCount(0);
});

test('a step that waits: Check suggests it, Yes keeps it, Save shows the split time and the chip (M1)', async ({ page }) => {
  const title = unique('Dosa');
  await page.goto('/recipes/import');
  await page
    .getByLabel('Paste a link or the recipe’s text')
    .fill(`${title}\nIngredients\n1 cup ${unique('Rice')}\nMethod\n1. Soak the rice overnight.\n2. Grind it and ferment 8-12 hours.\n3. Cook on a hot pan.\n`);
  await page.getByRole('button', { name: 'Read the recipe' }).click();
  await expect(page.getByRole('heading', { level: 1 })).toHaveText('Check before saving');
  await expect(page.getByText('Method · 3 steps found')).toBeVisible();
  // The reader's two suggestions, each with its answers; the third step has none.
  await expect(page.getByText('To confirm', { exact: true })).toHaveCount(2);
  await expect(page.getByText('Soak · overnight')).toBeVisible();
  await expect(page.getByText(/Ferment · 8\s*h – 12\s*h/)).toBeVisible();
  await page.getByRole('button', { name: 'Yes, it waits' }).first().click();
  await expect(page.getByText('To confirm', { exact: true })).toHaveCount(1);
  await page.getByRole('button', { name: 'No wait' }).last().click(); // the ferment
  await expect(page.getByText(/Ferment ·/)).toHaveCount(0);
  await page.getByRole('button', { name: 'New ingredient' }).first().click();
  await page.getByRole('button', { name: 'Save recipe' }).click();
  await expect(page).toHaveURL(/\/recipes\/\d+$/);
  await expect(page.getByText('overnight soaking')).toBeVisible();
  await expect(page.getByText('Soak · overnight')).toBeVisible();
  await expect(page.getByText(/Ferment ·/)).toHaveCount(0);
});
