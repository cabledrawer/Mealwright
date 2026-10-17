import { test, expect, type Page } from '@playwright/test';

// The app shell (0.1): the five pages and Settings, the bottom tabs on phones and the
// collapsible sidebar on desktop, and the Auto · Light · Dark switch. Each test runs
// twice, in the "phone" and "desktop" projects (see playwright.config.ts).

const PAGES = [
  { path: '/', title: 'Today', tab: 'Today' },
  { path: '/plan', title: 'Plan', tab: 'Plan' },
  { path: '/shopping', title: 'Shopping', tab: 'Shop' },
  { path: '/pantry', title: 'Pantry', tab: 'Pantry' },
  { path: '/recipes', title: 'Recipes', tab: 'Recipes' },
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
});

test('every page opens, with its title and the right tab marked', async ({ page, baseURL }) => {
  const watcher = await watch(page, baseURL!);
  for (const { path, title } of PAGES) {
    await page.goto(path);
    await expect(page.getByRole('heading', { level: 1 })).toHaveText(title);
    await expect(page).toHaveTitle(`${title} · Mealwright`);
    await expect(mainNav(page).locator('[aria-current="page"]')).toHaveCount(1);
    await expect(mainNav(page).locator('[aria-current="page"]')).toContainText(
      isPhone(page) ? PAGES.find((p) => p.path === path)!.tab : title,
    );
  }
  expect(await watcher.violations()).toEqual([]);
  expect(watcher.outside).toEqual([]);
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
    const small = await page.evaluate(() =>
      [...document.querySelectorAll('a, button')]
        .filter((el) => el.checkVisibility() && el.id !== 'svelte-announcer')
        .filter((el) => !el.matches('.skip'))
        .map((el) => ({ el, box: el.getBoundingClientRect() }))
        .filter(({ box }) => box.width < 44 || box.height < 44)
        .map(({ el, box }) => `${el.textContent?.trim() || el.getAttribute('aria-label')}: ${Math.round(box.width)}×${Math.round(box.height)}`),
    );
    expect(small, path).toEqual([]);
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
