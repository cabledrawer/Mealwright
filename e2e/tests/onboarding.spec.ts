import { test, expect, type Page } from './clock.ts';
import { mkdirSync } from 'node:fs';
import { join } from 'node:path';
import { checkPage, isPhone, setAccountTheme } from './a11y.ts';

// Full Onboarding (0.9 U2), against the real server, signed in as the test admin. This worker's
// server was set up through /api/v1/setup, so its household hasn't finished onboarding yet: these
// tests never press the last Skip or Finish (that is sign-in.spec.ts's first run, on the fresh server), so
// a retry finds it the same. Every test takes away what it added (the person, the shop, the
// starter pack and the Amounts choice), so the household the other screens share is as it was.
// Runs in the "phone 0.9 onboarding" and "desktop 0.9 onboarding" projects.

type Json = Record<string, any>; // eslint-disable-line @typescript-eslint/no-explicit-any

const key = () => ({ 'idempotency-key': crypto.randomUUID() });
/** A short mark of its own for each test and project, so names never clash. */
const mark = () => `${test.info().project.name.slice(0, 1)}${Date.now().toString(36).slice(-4)}`;

async function json(page: Page, path: string): Promise<Json> {
  const response = await page.request.get(`/api/v1${path}`);
  expect(response.status(), await response.text()).toBe(200);
  return (await response.json()) as Json;
}

async function foodNames(page: Page): Promise<Set<string>> {
  return new Set(((await json(page, '/foods?limit=500')).foods as Json[]).map((f) => f.name));
}

/** Take away whatever the test added, through the same public API. */
async function tidy(page: Page, person: string, shop: string) {
  const changes = (await json(page, '/changes')).changes as Json[];
  const pack = changes.find((c) => /^Added the Baking starter pack/.test(c.summary) && !c.undone);
  if (pack?.can_undo) {
    const undone = await page.request.post(`/api/v1/changes/${pack.id}/undo`, { headers: key() });
    expect(undone.ok(), await undone.text()).toBe(true);
  }
  for (const p of (await json(page, '/people')).people as Json[]) {
    if (p.name !== person) continue;
    const gone = await page.request.delete(`/api/v1/people/${p.id}`, { headers: key() });
    expect(gone.ok(), await gone.text()).toBe(true);
  }
  for (const s of (await (await page.request.get('/api/v1/shops')).json()).shops as Json[]) {
    if (s.name !== shop) continue;
    const gone = await page.request.delete(`/api/v1/shops/${s.id}`, { headers: key() });
    expect(gone.ok(), await gone.text()).toBe(true);
  }
  const back = await page.request.patch('/api/v1/household', {
    data: { amounts_shown: 'as_written' },
    headers: key(),
  });
  expect(back.ok(), await back.text()).toBe(true);
}

const STEPS = [
  'How do you measure?',
  'Who eats here?',
  'Where do you shop?',
  'Start with common ingredients?',
  'You’re set',
] as const;

/** On the phone, Next to the step with this title. */
async function nextTo(page: Page, title: (typeof STEPS)[number]) {
  await page.getByRole('button', { name: 'Next' }).click();
  await expect(page.getByRole('heading', { level: 1, name: title })).toBeVisible();
}

test.beforeEach(async ({ page }) => {
  await setAccountTheme(page, 'auto');
});

test('each step saves through the same settings: Amounts, people, shops and a starter pack', async ({
  page,
}) => {
  const person = `Onb ${mark()}`;
  const shop = `Grocer ${mark()}`;
  try {
    await page.goto('/onboarding');
    const phone = isPhone(page);
    if (phone) {
      await expect(page.getByText('Step 2 of 6')).toBeVisible();
      await expect(page.getByRole('heading', { level: 1, name: STEPS[0] })).toBeVisible();
      // On the phone it is a page of its own: no bottom tabs.
      await expect(page.getByRole('navigation', { name: 'Main' })).toBeHidden();
    } else {
      await expect(
        page.getByRole('heading', { level: 1, name: 'Welcome to Mealwright. Five quick things.' }),
      ).toBeVisible();
    }
    // The phone's Skip passes over one step; the computer page draws none.
    await expect(page.getByRole('button', { name: 'Skip' })).toHaveCount(phone ? 1 : 0);

    // Amounts: the 1.0 choices only; cups come after 1.0.
    await expect(page.getByRole('radio', { name: 'As the recipe says (cups stay cups)' })).toBeChecked();
    await expect(page.getByText(/Cups and ounces as a choice come after version 1\.0\./)).toBeVisible();
    await page.getByRole('radio', { name: 'Metric: grams and ml' }).click();
    await expect.poll(async () => (await json(page, '/household')).amounts_shown).toBe('metric');

    // Who eats here: a name only, no login.
    if (phone) await nextTo(page, 'Who eats here?');
    await page.getByRole('button', { name: '+ Add a person' }).click();
    await page.getByLabel('Name', { exact: true }).fill(person);
    await page.getByRole('button', { name: 'Add', exact: true }).click();
    await expect(page.getByRole('list', { name: 'People' }).getByText(person)).toBeVisible();
    const added = ((await json(page, '/people')).people as Json[]).find((p) => p.name === person);
    expect(added?.login ?? null).toBeNull();

    // Shops: optional; added by name.
    if (phone) await nextTo(page, 'Where do you shop?');
    await page.getByRole('button', { name: '+ Add a shop' }).click();
    await page.getByLabel('New shop').fill(shop);
    await page.getByRole('button', { name: 'Add', exact: true }).click();
    await expect(page.getByRole('list', { name: 'Shops' }).getByText(shop)).toBeVisible();

    // Starter packs: the same picker as Ingredients.
    if (phone) await nextTo(page, 'Start with common ingredients?');
    await page.getByRole('button', { name: 'Add a starter pack' }).click();
    const dialog = page.getByRole('dialog');
    await dialog.getByRole('button', { name: /^Baking/ }).click();
    await expect(dialog.getByRole('heading', { name: 'Baking starter pack' })).toBeVisible();
    await dialog.getByRole('button', { name: /^Add \d+ ingredients$/ }).click();
    await expect(page.getByText(/^Added the Baking starter pack: \d+ ingredients$/)).toBeVisible();
    await expect.poll(async () => (await foodNames(page)).has('self-raising flour')).toBe(true);

    if (phone) {
      await nextTo(page, 'You’re set');
      await expect(page.getByRole('button', { name: 'Go to Today' })).toBeVisible();
    }

    // Every choice shows where it lives: Settings › Amounts, Household, Shops and Ingredients.
    await page.goto('/settings/amounts');
    await expect(page.getByRole('radio', { name: 'Metric: grams and ml' })).toBeChecked();
    await page.goto('/settings/people');
    await expect(page.getByText(person, { exact: true }).first()).toBeVisible();
    await page.goto('/settings/shops-places');
    await expect(page.getByText(shop).first()).toBeVisible();
    await page.goto('/recipes/ingredients');
    await expect(page.getByText('self-raising flour', { exact: true }).first()).toBeVisible();

    // Nothing here finished onboarding: only the last Skip (step 5), Finish setup and Go to Today do.
    expect((await json(page, '/household')).onboarding_done).toBe(false);
  } finally {
    await tidy(page, person, shop);
  }
});

test('every step passes the accessibility checks, light and dark', async ({ page }) => {
  await page.goto('/onboarding');
  if (!isPhone(page)) {
    await expect(page.getByRole('button', { name: 'Finish setup' })).toBeVisible();
    await checkPage(page);
    return;
  }
  await expect(page.getByRole('heading', { level: 1, name: STEPS[0] })).toBeVisible();
  await checkPage(page);
  for (const title of STEPS.slice(1)) {
    await nextTo(page, title);
    await checkPage(page);
  }
});

// cabledrawer's review pictures (dark, 428, 768, 1100 and 1300 px), kept in this test's output folder,
// or in E2E_SHOTS_DIR when that names a folder (by hand).
test('review pictures of each step, dark', async ({ page }) => {
  test.skip(!test.info().project.name.startsWith('desktop'), 'once, on the computer project');
  const shots = (name: string) => {
    const dir = process.env.E2E_SHOTS_DIR;
    if (!dir) return test.info().outputPath(name);
    mkdirSync(dir, { recursive: true });
    return join(dir, name);
  };
  await setAccountTheme(page, 'dark');
  try {
    for (const width of [428, 768, 1100, 1300]) {
      await page.setViewportSize({ width, height: width < 768 ? 926 : 900 });
      await page.goto('/onboarding');
      if (width < 768) {
        await expect(page.getByRole('heading', { level: 1, name: STEPS[0] })).toBeVisible();
        for (const [i, title] of STEPS.entries()) {
          if (i) await nextTo(page, title);
          await page.screenshot({ path: shots(`onboarding-step${i + 2}-${width}.png`) });
        }
      } else {
        await expect(page.getByRole('button', { name: 'Finish setup' })).toBeVisible();
        await page.screenshot({
          path: shots(`onboarding-${width}.png`),
          fullPage: true,
        });
      }
    }
  } finally {
    await setAccountTheme(page, 'auto');
  }
});
