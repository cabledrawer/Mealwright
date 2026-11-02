import { test, expect, type Page } from './clock.ts';
import { checkPage, expectTouchTargets } from './a11y.ts';

// The app shell (0.1): the five pages and Settings, the bottom tabs on phones and the
// collapsible sidebar on desktop, and the Auto · Light · Dark switch. Each test runs
// twice, in the "phone" and "desktop" projects (see playwright.config.ts), signed in
// as the test admin.

const PAGES = [
  { path: '/', title: 'Today', tab: 'Today' },
  { path: '/plan', title: 'Plan', tab: 'Plan' },
  { path: '/shopping', title: 'Shopping', tab: 'Shop' },
  { path: '/pantry', title: 'Pantry', tab: 'Pantry' },
  // On desktop the sidebar shows Recipes as a tree, and marks All recipes.
  { path: '/recipes', title: 'Recipes', tab: 'Recipes', sidebar: 'All recipes' },
];

const GROUND = { light: 'rgb(245, 246, 244)', dark: 'rgb(17, 22, 20)' };

type Violation = { directive: string; blockedURI: string; sample: string };

const isPhone = (page: Page) => (page.viewportSize()?.width ?? 0) < 768;

/** Record CSP violations and anything sent anywhere other than the app itself. */
async function watch(page: Page, baseURL: string) {
  const outside: string[] = [];
  await page.route(
    (url) => url.origin !== baseURL,
    (route) => {
      outside.push(route.request().url());
      return route.abort();
    },
  );
  await page.addInitScript(() => {
    const seen: Violation[] = [];
    (window as unknown as { violations: Violation[] }).violations = seen;
    document.addEventListener('securitypolicyviolation', (event) => {
      seen.push({
        directive: event.effectiveDirective,
        blockedURI: event.blockedURI,
        sample: event.sample,
      });
    });
  });
  return {
    outside,
    async violations() {
      return page.evaluate(() => (window as unknown as { violations: Violation[] }).violations);
    },
  };
}

function mainNav(page: Page) {
  return isPhone(page)
    ? page.locator('.tabbar-slot').getByRole('navigation', { name: 'Main' })
    : page.getByRole('complementary', { name: 'Sidebar' }).getByRole('navigation', {
        name: 'Main',
      });
}

test.beforeEach(async ({ page }) => {
  await page.emulateMedia({ colorScheme: 'light' });
  // Signed in as the test admin (global-setup.ts). The theme is saved to the account,
  // so start every test from Auto.
  const reset = await page.request.put('/api/v1/me/preferences', { data: { theme: 'auto' } });
  expect(reset.ok()).toBe(true);
});

test('every page opens, with its title and the right tab marked', async ({ page, baseURL }) => {
  const watcher = await watch(page, baseURL!);
  for (const { path, title, sidebar } of PAGES) {
    await page.goto(path);
    await expect(page.getByRole('heading', { level: 1 })).toHaveText(title);
    await expect(page).toHaveTitle(`${title} · Mealwright`);
    await expect(mainNav(page).locator('[aria-current="page"]')).toHaveCount(1);
    await expect(mainNav(page).locator('[aria-current="page"]')).toContainText(
      isPhone(page) ? PAGES.find((p) => p.path === path)!.tab : (sidebar ?? title),
    );
  }
  expect(await watcher.violations()).toEqual([]);
  expect(watcher.outside).toEqual([]);
});

test('every page uses curly apostrophes on screen, never a straight one', async ({ page }) => {
  // Word list section 11, ruling 3. The text, and what is read out or shown in attributes.
  const straight = /[A-Za-z]'[A-Za-z]/;
  for (const path of [...PAGES.map((p) => p.path), '/recipes/ingredients', '/recipes/new', '/settings']) {
    await page.goto(path);
    await expect(page.getByRole('heading', { level: 1 })).toBeVisible();
    const texts = await page.evaluate(() => [
      document.body.innerText,
      ...[...document.querySelectorAll('[aria-label], [title], [placeholder], [alt], [aria-description]')].flatMap(
        (el) =>
          ['aria-label', 'title', 'placeholder', 'alt', 'aria-description']
            .map((name) => el.getAttribute(name) ?? '')
            .filter(Boolean),
      ),
    ]);
    const found = texts.flatMap((text) => text.split('\n')).filter((line) => straight.test(line));
    expect(found, path).toEqual([]);
  }
});

test('the main navigation moves between pages', async ({ page, baseURL }) => {
  const watcher = await watch(page, baseURL!);
  await page.goto('/');
  for (const { path, title, tab } of [...PAGES.slice(1), PAGES[0]!]) {
    await mainNav(page)
      .getByRole('link', { name: isPhone(page) ? tab : title, exact: true })
      .click();
    await expect(page).toHaveURL(path);
    await expect(page.getByRole('heading', { level: 1 })).toHaveText(title);
  }
  // Screen readers hear the new page's name; nobody sees it (it's hidden by our CSS,
  // not by an inline style, which the CSP would block).
  const announcer = page.locator('#svelte-announcer');
  await expect(announcer).toHaveText('Today · Mealwright');
  expect(await announcer.boundingBox()).toMatchObject({ width: 1, height: 1 });
  expect(await announcer.getAttribute('style')).toBeNull();
  expect(await watcher.violations()).toEqual([]);
  expect(watcher.outside).toEqual([]);
});

test('phones get bottom tabs, desktops get the sidebar', async ({ page }) => {
  await page.goto('/');
  const tabs = page.locator('.tabbar-slot').getByRole('navigation', { name: 'Main' });
  const sidebar = page.getByRole('complementary', { name: 'Sidebar' });
  if (isPhone(page)) {
    await expect(tabs).toBeVisible();
    await expect(sidebar).toBeHidden();
    const box = (await tabs.boundingBox())!;
    expect(box.y + box.height).toBeCloseTo(page.viewportSize()!.height, 0);
  } else {
    await expect(sidebar).toBeVisible();
    await expect(tabs).toBeHidden();
  }
});

test('pages never scroll sideways', async ({ page }) => {
  for (const path of [...PAGES.map((p) => p.path), '/settings']) {
    await page.goto(path);
    await expect(page.getByRole('heading', { level: 1 })).toBeVisible();
    const sideways = await page.evaluate(
      () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
    );
    expect(sideways, path).toBeLessThanOrEqual(0);
  }
});

test('on phones every button and link is at least 44 px', async ({ page }) => {
  test.skip(!isPhone(page), 'touch targets are a phone rule');
  for (const path of ['/', '/settings']) {
    await page.goto(path);
    await expect(page.getByRole('heading', { level: 1 })).toBeVisible();
    // Settings' Amounts arrives after the heading; wait for it, so it is always measured.
    if (path === '/settings') await expect(page.getByRole('heading', { name: 'Amounts' })).toBeVisible();
    // The shared check: it counts a switch's larger invisible touch area (the pint switch in
    // Settings), which measuring the visible box alone missed whenever Amounts had loaded.
    await expectTouchTargets(page);
  }
});

test('phones: at 200% text every tab label is whole, on one line, with a gap to the next', async ({ page }) => {
  test.skip(!isPhone(page), 'the bottom tabs are a phone thing');
  await page.goto('/pantry');
  await page.evaluate(() => (document.documentElement.style.fontSize = '200%'));
  const tabs = page.getByRole('navigation', { name: 'Main' });
  await expect(tabs.getByRole('link', { name: 'Recipes' })).toBeVisible();
  const labels = await tabs.locator('a span').evaluateAll((spans) =>
    spans.map((span) => {
      const range = document.createRange();
      range.selectNodeContents(span);
      const { left, right } = range.getBoundingClientRect();
      const link = span.closest('a')!.getBoundingClientRect();
      return {
        text: span.textContent,
        left,
        right,
        lines: range.getClientRects().length,
        inLink: left >= link.left && right <= link.right,
      };
    }),
  );
  expect(labels.map((l) => l.text)).toEqual(['Today', 'Plan', 'Shop', 'Pantry', 'Recipes']);
  const width = page.viewportSize()!.width;
  for (const [i, label] of labels.entries()) {
    expect(label.lines, label.text!).toBe(1);
    expect(label.inLink, label.text!).toBe(true);
    expect(label.left, label.text!).toBeGreaterThanOrEqual(0);
    expect(label.right, label.text!).toBeLessThanOrEqual(width);
    // At least 4 px between one label and the next, so "Pantry" and "Recipes" never touch.
    if (i > 0) expect(label.left - labels[i - 1]!.right, label.text!).toBeGreaterThanOrEqual(4);
  }
});

test('the page header stays put on phones while the page scrolls', async ({ page }) => {
  test.skip(!isPhone(page), 'phone layout only');
  await page.goto('/');
  await expect(page.getByRole('heading', { level: 1 })).toBeVisible();
  // Make the page long enough to scroll.
  await page.evaluate(() => {
    const filler = document.createElement('div');
    filler.style.height = '3000px'; // set from script, which the CSP allows
    document.querySelector('main')!.append(filler);
  });
  await page.mouse.wheel(0, 1200);
  await expect.poll(() => page.evaluate(() => window.scrollY)).toBeGreaterThan(500);
  const header = (await page.locator('header.page-header').boundingBox())!;
  expect(header.y).toBeCloseTo(0, 0);
});

test.describe('theme', () => {
  async function ground(page: Page) {
    return page.evaluate(() => getComputedStyle(document.documentElement).backgroundColor);
  }

  async function themeControls(page: Page) {
    if (isPhone(page)) {
      // Phones find the theme switch in Settings, behind the round button at the top.
      await page.getByRole('link', { name: 'Settings' }).first().click();
      await expect(page.getByRole('heading', { level: 1 })).toHaveText('Settings');
      return page.locator('main').getByRole('group', { name: 'Theme' });
    }
    return page.getByRole('complementary', { name: 'Sidebar' }).getByRole('group', {
      name: 'Theme',
    });
  }

  test('Auto follows the device', async ({ page }) => {
    await page.goto('/');
    expect(await ground(page)).toBe(GROUND.light);
    await page.emulateMedia({ colorScheme: 'dark' });
    await expect.poll(() => ground(page)).toBe(GROUND.dark);
    await page.emulateMedia({ colorScheme: 'light' });
    await expect.poll(() => ground(page)).toBe(GROUND.light);
  });

  test('Dark and Light override the device, and are remembered', async ({ page }) => {
    await page.goto('/');
    const group = await themeControls(page);
    await expect(group.getByRole('button', { name: 'Auto' })).toHaveAttribute(
      'aria-pressed',
      'true',
    );

    await group.getByRole('button', { name: 'Dark' }).click();
    await expect(group.getByRole('button', { name: 'Dark' })).toHaveAttribute(
      'aria-pressed',
      'true',
    );
    expect(await ground(page)).toBe(GROUND.dark);

    // Still dark after a reload, and already dark before the app has started.
    await page.goto('/plan', { waitUntil: 'commit' });
    await page.waitForFunction(() => document.readyState !== 'loading');
    expect(await page.evaluate(() => document.documentElement.dataset.theme)).toBe('dark');
    expect(await ground(page)).toBe(GROUND.dark);

    await page.emulateMedia({ colorScheme: 'dark' });
    const group2 = await themeControls(page);
    await group2.getByRole('button', { name: 'Light' }).click();
    expect(await ground(page)).toBe(GROUND.light);
    await page.reload();
    expect(await ground(page)).toBe(GROUND.light);

    await (await themeControls(page)).getByRole('button', { name: 'Auto' }).click();
    expect(await ground(page)).toBe(GROUND.dark);
  });

  test('the dark theme is its own palette, not inverted colours', async ({ page }) => {
    await page.emulateMedia({ colorScheme: 'dark' });
    await page.goto('/');
    const colours = await page.evaluate(() => {
      const s = getComputedStyle(document.documentElement);
      return { text: s.color, accent: s.getPropertyValue('--color-accent').trim() };
    });
    expect(colours).toEqual({ text: 'rgb(233, 238, 235)', accent: '#6fcf9e' });
  });
});

test.describe('desktop sidebar', () => {
  test.skip(({ viewport }) => (viewport?.width ?? 0) < 768, 'desktop layout only');

  test('Recipes’ tree is All recipes, Import, Drafts and Ingredients (Import is its own item, F113)', async ({ page }) => {
    await page.goto('/recipes/ingredients');
    const sidebar = page.getByRole('complementary', { name: 'Sidebar' });
    await expect(sidebar.getByRole('group', { name: 'Recipes' }).getByRole('link')).toHaveText([
      'All recipes',
      'Import',
      /^Drafts\s*\d*$/,
      'Ingredients',
    ]);
    await expect(sidebar.getByRole('link', { name: /^Drafts/ })).toHaveAttribute('href', '/recipes/drafts');
  });

  test('collapses to icons, and is remembered', async ({ page }) => {
    await page.goto('/');
    const sidebar = page.getByRole('complementary', { name: 'Sidebar' });
    expect((await sidebar.boundingBox())!.width).toBeGreaterThan(200);
    await expect(sidebar.getByText('Mealwright', { exact: true })).toBeVisible();

    await sidebar.getByRole('button', { name: 'Collapse sidebar' }).click();
    await expect.poll(async () => (await sidebar.boundingBox())!.width).toBe(72);
    // Icons keep their names for screen readers and as tooltips.
    const plan = sidebar.getByRole('link', { name: 'Plan', exact: true });
    await expect(plan).toHaveAttribute('title', 'Plan');
    await expect(sidebar.getByText('Mealwright', { exact: true })).toHaveCount(0);

    await page.reload();
    await expect.poll(async () => (await sidebar.boundingBox())!.width).toBe(72);
    await plan.click();
    await expect(page).toHaveURL('/plan');
    await expect.poll(async () => (await sidebar.boundingBox())!.width).toBe(72);

    await sidebar.getByRole('button', { name: 'Expand sidebar' }).click();
    await expect.poll(async () => (await sidebar.boundingBox())!.width).toBeGreaterThan(200);
    await page.reload();
    await expect.poll(async () => (await sidebar.boundingBox())!.width).toBeGreaterThan(200);
  });

  test('collapsed, Recipes opens a pop-out with its pages and the current one marked', async ({
    page,
  }) => {
    await page.goto('/recipes/ingredients');
    const sidebar = page.getByRole('complementary', { name: 'Sidebar' });
    await sidebar.getByRole('button', { name: 'Collapse sidebar' }).click();
    const icon = sidebar.getByRole('button', { name: 'Recipes' });
    await expect(icon).toHaveAttribute('aria-haspopup', 'menu');
    await icon.click();
    const menu = page.getByRole('menu', { name: 'Recipes' });
    await expect(menu.getByRole('menuitem')).toHaveText(['All recipes', 'Import', 'Drafts', 'Ingredients']);
    await expect(menu.getByRole('menuitem', { name: 'Ingredients' })).toHaveAttribute(
      'aria-current',
      'page',
    );
    await checkPage(page);

    // It stays inside the window and Esc puts focus back on the icon.
    const box = (await menu.boundingBox())!;
    const iconBox = (await icon.boundingBox())!;
    expect(box.x).toBeGreaterThanOrEqual(iconBox.x + iconBox.width);
    expect(box.y + box.height).toBeLessThanOrEqual(page.viewportSize()!.height);
    await page.keyboard.press('Escape');
    await expect(menu).toBeHidden();
    await expect(icon).toBeFocused();

    // Choosing a page goes there, and the sidebar stays collapsed.
    await icon.click();
    await menu.getByRole('menuitem', { name: 'Ingredients' }).click();
    await expect(page).toHaveURL('/recipes/ingredients');
    await expect(menu).toBeHidden();
    await expect.poll(async () => (await sidebar.boundingBox())!.width).toBe(72);
  });

  test('collapsed, the Recipes pop-out sits above a page full of rows, so Drafts opens Drafts', async ({
    page,
  }) => {
    // Enough ingredients that their rows lie under every item of the pop-out (0.6: the rows
    // used to be painted over it, so a click on a menu item opened an ingredient).
    const stamp = `${test.info().project.name} ${Date.now()}`;
    for (let n = 1; n <= 12; n++) {
      const made = await page.request.post('/api/v1/foods', {
        data: { name: `Aaa pop-out ${n} ${stamp}`, counted_as: 'weight' },
        headers: { 'idempotency-key': crypto.randomUUID() },
      });
      expect(made.status(), await made.text()).toBe(201);
    }
    await page.goto('/recipes/ingredients');
    await expect(page.getByRole('button', { name: new RegExp(`^Aaa pop-out 12 ${stamp}`) })).toBeVisible();
    const sidebar = page.getByRole('complementary', { name: 'Sidebar' });
    await sidebar.getByRole('button', { name: 'Collapse sidebar' }).click();
    await sidebar.getByRole('button', { name: 'Recipes' }).click();
    const menu = page.getByRole('menu', { name: 'Recipes' });
    await expect(menu.getByRole('menuitem')).toHaveCount(3);

    // Whatever is at the middle of each menu item is that item, not a row underneath.
    for (const item of await menu.getByRole('menuitem').all()) {
      const box = (await item.boundingBox())!;
      const onTop = await page.evaluate(
        ([x, y]) => document.elementFromPoint(x, y)?.closest('[role="menuitem"]')?.textContent?.trim() ?? null,
        [box.x + box.width / 2, box.y + box.height / 2],
      );
      expect(onTop).toBe((await item.textContent())?.trim());
    }

    await menu.getByRole('menuitem', { name: 'Drafts' }).click();
    await expect(page).toHaveURL('/recipes/drafts');
  });

  test('collapsed, the theme is one button that steps through Auto, Light, Dark', async ({
    page,
  }) => {
    await page.goto('/');
    const sidebar = page.getByRole('complementary', { name: 'Sidebar' });
    await sidebar.getByRole('button', { name: 'Collapse sidebar' }).click();
    const button = sidebar.getByRole('button', { name: /^Theme:/ });
    await expect(button).toHaveAccessibleName('Theme: Auto. Switch to Light');
    await button.click();
    await expect(button).toHaveAccessibleName('Theme: Light. Switch to Dark');
    await button.click();
    await expect(button).toHaveAccessibleName('Theme: Dark. Switch to Auto');
    expect(await page.evaluate(() => document.documentElement.dataset.theme)).toBe('dark');
    await button.click();
    await expect(button).toHaveAccessibleName('Theme: Auto. Switch to Light');
  });
});

test('fonts come from the app itself', async ({ page, baseURL }) => {
  const fonts: string[] = [];
  page.on('response', (response) => {
    if (response.request().resourceType() === 'font') fonts.push(response.url());
  });
  const watcher = await watch(page, baseURL!);
  await page.goto('/');
  await expect(page.getByRole('heading', { level: 1 })).toBeVisible();
  await page.evaluate(() => document.fonts.ready);
  const used = await page.evaluate(() =>
    [...document.fonts].filter((f) => f.status === 'loaded').map((f) => f.family),
  );
  expect(used).toContain('Plus Jakarta Sans Variable');
  expect(fonts.length).toBeGreaterThan(0);
  for (const url of fonts) expect(url.startsWith(`${baseURL}/_app/`), url).toBe(true);
  expect(watcher.outside).toEqual([]);
});

test('a page link opened directly works (the backend serves the app for it)', async ({
  page,
}) => {
  const response = await page.goto('/pantry');
  expect(response!.status()).toBe(200);
  await expect(page.getByRole('heading', { level: 1 })).toHaveText('Pantry');
});

test('keyboard users can skip straight to the page', async ({ page }) => {
  test.skip(isPhone(page), 'keyboard use is a desktop concern');
  await page.goto('/');
  await expect(page.getByRole('heading', { level: 1 })).toBeVisible();
  await page.keyboard.press('Tab');
  const skip = page.getByRole('link', { name: 'Skip to content' });
  await expect(skip).toBeFocused();
  await expect(skip).toBeInViewport();
  await page.keyboard.press('Enter');
  await expect(page.locator('main')).toBeFocused();
});
