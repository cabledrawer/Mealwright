import { expect, test, type Page } from '@playwright/test';

// Keyboard-only use (spec "Keeping the UI good", item 7): on every built desktop screen,
// Tab reaches everything you can click, and you can always see where you are. Each test
// presses Tab through a whole screen and checks:
//   1. every control on the screen that is meant to be in the Tab order was reached;
//   2. every stop showed a focus ring (an outline or a shadow around it).
// Groups that are used with the arrow keys (the tabs, the radio groups) take one Tab stop
// for the whole group, so their other parts are not expected in the Tab order.

const CONTROLS =
  'a[href], button, input:not([type="hidden"]), select, textarea, summary, [role="switch"], [role="checkbox"], [role="radio"], [role="tab"], [tabindex]';

type Stop = { label: string; ring: boolean; tag: string };

/** The page's controls that Tab should reach, as names. */
async function expected(page: Page): Promise<string[]> {
  return page.evaluate((selector) => {
    const names: string[] = [];
    for (const el of document.querySelectorAll<HTMLElement>(selector)) {
      if (el.tabIndex < 0) continue; // out of the Tab order on purpose (arrow-key groups)
      if ((el as HTMLButtonElement).disabled) continue;
      const box = el.getBoundingClientRect();
      const style = getComputedStyle(el);
      if (style.visibility === 'hidden' || style.display === 'none') continue;
      if (el.closest('[hidden], [inert]')) continue;
      if (box.width === 0 && box.height === 0) continue;
      if (el.matches('main[tabindex="-1"]')) continue;
      names.push(describe(el));
    }
    return names;

    function describe(el: HTMLElement): string {
      const text = (el.getAttribute('aria-label') ?? el.textContent ?? '').trim().replace(/\s+/g, ' ');
      return `${el.tagName.toLowerCase()} "${text.slice(0, 50)}" ${el.getAttribute('href') ?? ''}`.trim();
    }
  }, CONTROLS);
}

/** Press Tab through the page. Returns where focus stopped, until it comes back round. */
async function tabThrough(page: Page, limit = 400): Promise<Stop[]> {
  await page.evaluate(() => (document.activeElement as HTMLElement | null)?.blur());
  const stops: Stop[] = [];
  const seen = new Set<string>();
  for (let i = 0; i < limit; i++) {
    await page.keyboard.press('Tab');
    const stop = await page.evaluate(() => {
      const el = document.activeElement as HTMLElement | null;
      if (!el || el === document.body) return null;
      // A ring is an outline, or a box-shadow (some controls draw theirs that way). Text boxes
      // draw it round the box that holds them (":focus-within"), so look up to three
      // levels out as well, but never as far as the page itself.
      // Some rows draw theirs on a ::after that covers the whole row, so look there too (only
      // at a pseudo-element that is really drawn, which has content).
      const drawn = (style: CSSStyleDeclaration) =>
        (style.outlineStyle !== 'none' && parseFloat(style.outlineWidth) > 0) || style.boxShadow !== 'none';
      const hasRing = (node: Element) =>
        drawn(getComputedStyle(node)) ||
        (['::before', '::after'] as const).some((pseudo) => {
          const style = getComputedStyle(node, pseudo);
          return style.content !== 'none' && style.content !== 'normal' && drawn(style);
        });
      let ring = hasRing(el);
      let up: Element | null = el.parentElement;
      for (let i = 0; i < 3 && !ring && up && up !== document.body && up.tagName !== 'MAIN'; i++) {
        ring = hasRing(up);
        up = up.parentElement;
      }
      const text = (el.getAttribute('aria-label') ?? el.textContent ?? '').trim().replace(/\s+/g, ' ');
      return {
        label: `${el.tagName.toLowerCase()} "${text.slice(0, 50)}" ${el.getAttribute('href') ?? ''}`.trim(),
        ring,
        tag: el.tagName.toLowerCase(),
        id: `${el.tagName}|${text}|${el.getAttribute('href')}|${Math.round(el.getBoundingClientRect().top + scrollY)}|${Math.round(el.getBoundingClientRect().left)}`
      };
    });
    if (!stop) break; // left the page (to the browser's own bar): the loop is closed
    if (seen.has(stop.id)) break;
    seen.add(stop.id);
    stops.push({ label: stop.label, ring: stop.ring, tag: stop.tag });
  }
  return stops;
}

/** Wait until the page has finished filling in: the list of controls (with their names) stays
 *  the same for half a second. Some names change once the page's data arrives (Ingredients'
 *  "Recent changes" button gains its count), and measuring before that made the test race
 *  the page. This waits for the page; it never skips a control. */
async function pageSettled(page: Page): Promise<string[]> {
  let last = await expected(page);
  let same = 0;
  for (let i = 0; i < 100 && same < 5; i++) {
    await page.waitForTimeout(100);
    const now = await expected(page);
    same = JSON.stringify(now) === JSON.stringify(last) ? same + 1 : 0;
    last = now;
  }
  return last;
}

async function checkKeyboard(page: Page, name: string) {
  const want = await pageSettled(page);
  const stops = await tabThrough(page);
  expect(stops.length, `${name}: Tab found something to stop on`).toBeGreaterThan(3);

  const reached = new Set(stops.map((s) => s.label));
  const missed = want.filter((label) => !reached.has(label));
  expect(missed, `${name}: controls Tab never reached`).toEqual([]);

  const bare = stops.filter((s) => !s.ring).map((s) => s.label);
  expect(bare, `${name}: stops with no visible focus ring`).toEqual([]);
}

test.describe('signed in', () => {
  test.beforeEach(async ({ page }, info) => {
    test.skip(info.project.name !== 'desktop keyboard', 'desktop screens only');
    await page.emulateMedia({ reducedMotion: 'reduce' });
  });

  test('Pantry', async ({ page }) => {
    await page.goto('/pantry');
    await expect(page.getByRole('heading', { name: 'Pantry', level: 1 })).toBeVisible();
    await checkKeyboard(page, 'Pantry');
  });

  test('Shopping', async ({ page }) => {
    await page.goto('/shopping');
    await expect(page.getByRole('heading', { name: 'Shopping', level: 1 })).toBeVisible();
    await checkKeyboard(page, 'Shopping');
  });

  test('Ingredients', async ({ page }) => {
    await page.goto('/recipes/ingredients');
    await expect(page.getByRole('heading', { name: 'Ingredients', level: 1 })).toBeVisible();
    await checkKeyboard(page, 'Ingredients');
  });

  test('Settings', async ({ page }) => {
    await page.goto('/settings');
    await expect(page.getByRole('heading', { name: 'Settings', level: 1 })).toBeVisible();
    await checkKeyboard(page, 'Settings');
  });
});

test.describe('signed out', () => {
  test.use({ storageState: { cookies: [], origins: [] } });

  test('Sign in', async ({ page }, info) => {
    test.skip(info.project.name !== 'desktop keyboard', 'desktop screens only');
    await page.goto('/sign-in');
    await expect(page.getByRole('heading', { level: 1 })).toBeVisible();
    await checkKeyboard(page, 'Sign in');
  });
});
