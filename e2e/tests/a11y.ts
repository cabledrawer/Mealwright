// Accessibility checks for browser tests (spec "UX — CORE": WCAG AA in both themes,
// touch targets of at least 44 px, vertical scrolling only).
//
//   import { checkPage } from './a11y.ts';
//   await page.goto('/pantry');
//   await checkPage(page);            // axe in light and dark, plus the phone checks
//
// Or use the pieces on their own: inTheme, expectNoAxeViolations, expectTouchTargets,
// expectNoSidewaysScroll, expectFieldsDontZoom.
//
// axe-core runs inside the page from the local node_modules copy; it sends nothing
// anywhere.
import { AxeBuilder } from '@axe-core/playwright';
import { expect, type Page } from '@playwright/test';

export type Theme = 'light' | 'dark';
export const THEMES: readonly Theme[] = ['light', 'dark'];

/** The WCAG 2.0, 2.1 and 2.2 rules at levels A and AA. */
export const WCAG_AA_TAGS = ['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa', 'wcag22aa'];

/** The phone layout is anything narrower than the desktop breakpoint (768 px). */
export const isPhone = (page: Page) => (page.viewportSize()?.width ?? 0) < 768;

/** The minimum touch target from the spec (principle 1, CLAUDE.md UX rules). */
export const MIN_TARGET = 44;

/**
 * Show the page in a theme. Uses the device setting with the account on Auto, so it
 * works on signed-out pages too. Call setAccountTheme first if the test changed it.
 */
export async function inTheme(page: Page, theme: Theme) {
  await page.emulateMedia({ colorScheme: theme });
  await expect(page.locator('html')).toHaveAttribute('data-theme', theme);
}

/** Put the signed-in account back on Auto, so the device setting decides the theme. */
export async function setAccountTheme(page: Page, theme: 'auto' | Theme = 'auto') {
  const response = await page.request.put('/api/v1/me/preferences', { data: { theme } });
  expect(response.ok(), `couldn’t set the account theme: ${response.status()}`).toBe(true);
}

export type AxeOptions = {
  /** CSS selectors to leave out of the scan. Say why in a comment next to each. */
  exclude?: string[];
  /** axe rule IDs to switch off. Say why in a comment next to each. */
  disableRules?: string[];
};

/**
 * Wait until every fade, slide and colour change that will end has ended, so a scan never sees
 * a page half-way through one (on a busy machine a 180 ms fade can still be running when the
 * scan starts, and its half-faded colours fail the contrast rule). Animations that never end
 * (a spinner) are left alone.
 */
export async function waitForAnimations(page: Page) {
  await page.evaluate(() =>
    Promise.all(
      document
        .getAnimations()
        .filter((a) => a.effect?.getComputedTiming().iterations !== Infinity)
        .map((a) => a.finished.catch(() => undefined)),
    ),
  );
}

/** Run axe with the WCAG 2 A and AA rules and fail with a readable list of problems. */
export async function expectNoAxeViolations(page: Page, label: string, options: AxeOptions = {}) {
  await waitForAnimations(page);
  let builder = new AxeBuilder({ page }).withTags(WCAG_AA_TAGS);
  for (const selector of options.exclude ?? []) builder = builder.exclude(selector);
  if (options.disableRules?.length) builder = builder.disableRules(options.disableRules);
  const { violations } = await builder.analyze();
  const report = violations.flatMap((v) =>
    v.nodes.map(
      (node) =>
        `[${v.impact ?? '?'}] ${v.id}: ${v.help}\n    at ${node.target.join(' ')}\n    ${node.failureSummary?.replace(/\n/g, '\n    ') ?? ''}`,
    ),
  );
  expect(report, `axe found problems (${label}):\n${report.join('\n')}`).toEqual([]);
}

type TooSmall = { what: string; width: number; height: number };

/**
 * Every visible button, link, form field, tab, switch and the like is at least
 * 44 × 44 px. Links inside running text are exempt (as in WCAG 2.5.8), and so is a
 * skip link parked above the page until it gets focus. A real checkbox or radio that
 * is hidden behind a custom control is measured by its label. An invisible larger touch
 * area made with ::before or ::after (as the Switch has) counts.
 * `allow` takes CSS selectors that may be smaller; say why in a comment next to each.
 */
export async function expectTouchTargets(page: Page, allow: string[] = []) {
  const small: TooSmall[] = await page.evaluate(
    ({ min, allow }) => {
      const selector = [
        'a[href]',
        'button',
        'input:not([type="hidden"])',
        'select',
        'textarea',
        'summary',
        '[role="button"]',
        '[role="link"]',
        '[role="tab"]',
        '[role="switch"]',
        '[role="checkbox"]',
        '[role="radio"]',
        '[role="menuitem"]',
        '[role="option"]',
        '[tabindex]:not([tabindex="-1"])',
      ].join(',');
      const describe = (el: Element) => {
        const name =
          el.getAttribute('aria-label') ??
          (el as HTMLElement).innerText?.trim().slice(0, 40) ??
          (el as HTMLInputElement).name ??
          '';
        const cls = el.classList.length ? `.${[...el.classList].slice(0, 2).join('.')}` : '';
        return `<${el.tagName.toLowerCase()}${cls}> "${name}"`;
      };
      const hiddenInput = (el: Element) => {
        if (!(el instanceof HTMLInputElement) || !['checkbox', 'radio'].includes(el.type)) return false;
        const style = getComputedStyle(el);
        const box = el.getBoundingClientRect();
        return style.opacity === '0' || box.width <= 2 || box.height <= 2;
      };
      const inRunningText = (el: Element) => {
        if (el.tagName !== 'A' || getComputedStyle(el).display !== 'inline') return false;
        const parent = el.parentElement;
        if (!parent) return false;
        const text = parent.textContent?.trim() ?? '';
        const own = el.textContent?.trim() ?? '';
        return text.length > own.length; // there is other text around the link
      };
      // A small control can have a bigger invisible touch area from an absolutely
      // positioned ::before or ::after with negative insets (as the Switch does).
      const hitArea = (el: Element, box: DOMRect): [number, number] => {
        let [width, height] = [box.width, box.height];
        if (getComputedStyle(el).position === 'static') return [width, height];
        for (const pseudo of ['::before', '::after']) {
          const p = getComputedStyle(el, pseudo);
          if (p.content === 'none' || p.position !== 'absolute' || p.pointerEvents === 'none') continue;
          const px = (v: string) => (v.endsWith('px') ? parseFloat(v) : NaN);
          const [top, right, bottom, left] = [p.top, p.right, p.bottom, p.left].map(px);
          if ([top, right, bottom, left].some(Number.isNaN)) continue;
          width = Math.max(width, box.width - left - right);
          height = Math.max(height, box.height - top - bottom);
        }
        return [width, height];
      };
      const out: { what: string; width: number; height: number }[] = [];
      for (const found of document.querySelectorAll(selector)) {
        if (allow.some((a) => found.matches(a))) continue;
        if (found.closest('[aria-hidden="true"], [inert]')) continue;
        if (!found.checkVisibility({ checkOpacity: false, checkVisibilityCSS: true })) continue;
        let el: Element = found;
        if (hiddenInput(found)) {
          const input = found as HTMLInputElement;
          const label = input.closest('label') ?? input.labels?.[0];
          if (!label) {
            out.push({ what: `${describe(found)} (hidden, with no label to tap)`, width: 0, height: 0 });
            continue;
          }
          el = label;
        }
        const box = el.getBoundingClientRect();
        if (box.width === 0 && box.height === 0) continue;
        // A "skip to content" link that is off-screen or clipped until focused.
        const style = getComputedStyle(el);
        if (style.clip === 'rect(0px, 0px, 0px, 0px)' || style.clipPath === 'inset(50%)') continue;
        if (box.bottom + scrollY <= 0 || box.right + scrollX <= 0) continue;
        if (inRunningText(el)) continue;
        const [width, height] = hitArea(el, box);
        if (width < min || height < min) {
          out.push({ what: describe(el), width: Math.round(width), height: Math.round(height) });
        }
      }
      return out;
    },
    { min: MIN_TARGET, allow },
  );
  const report = small.map((s) => `${s.what}: ${s.width} × ${s.height} px`);
  expect(report, `touch targets under ${MIN_TARGET} × ${MIN_TARGET} px:\n${report.join('\n')}`).toEqual([]);
}

/** The page never scrolls sideways (principle 14); checked at the current width. */
export async function expectNoSidewaysScroll(page: Page) {
  const widths = await page.evaluate(() => {
    const root = document.scrollingElement ?? document.documentElement;
    const wide: string[] = [];
    // Anything poking out past the right edge of the screen, for a useful message.
    for (const el of document.body.querySelectorAll('*')) {
      const box = el.getBoundingClientRect();
      if (box.right > window.innerWidth + 1 && el.checkVisibility()) {
        wide.push(`<${el.tagName.toLowerCase()}${el.id ? '#' + el.id : ''}${el.className && typeof el.className === 'string' ? '.' + el.className.trim().split(/\s+/).slice(0, 2).join('.') : ''}> right edge ${Math.round(box.right)}`);
      }
    }
    return { scroll: root.scrollWidth, client: root.clientWidth, wide: wide.slice(0, 10) };
  });
  expect(
    widths.scroll,
    `page scrolls sideways (${widths.scroll} > ${widths.client} px):\n${widths.wide.join('\n')}`,
  ).toBeLessThanOrEqual(widths.client);
}

/**
 * Every text box, list box and the like uses a font of at least 16 px, so iOS never zooms
 * the page in when one gets the focus (cabledrawer 20 Oct, hand test). Checked on every size:
 * an iPad in the wide layout zooms too.
 */
export async function expectFieldsDontZoom(page: Page) {
  const small: string[] = await page.evaluate(() => {
    const out: string[] = [];
    const selector =
      'input:not([type="hidden"]):not([type="checkbox"]):not([type="radio"]), select, textarea';
    for (const el of document.querySelectorAll(selector)) {
      if (!el.checkVisibility({ checkOpacity: false, checkVisibilityCSS: true })) continue;
      const px = parseFloat(getComputedStyle(el).fontSize);
      if (px < 16) {
        const name = el.getAttribute('aria-label') ?? el.getAttribute('name') ?? '';
        const cls = el.classList.length ? `.${[...el.classList].slice(0, 2).join('.')}` : '';
        out.push(`<${el.tagName.toLowerCase()}${cls}> "${name}": ${px} px`);
      }
    }
    return out;
  });
  expect(small, `fields under 16 px (iOS would zoom in):\n${small.join('\n')}`).toEqual([]);
}

export type CheckOptions = AxeOptions & {
  /** Selectors allowed to be under 44 px (phone only). Say why next to each. */
  smallTargets?: string[];
  /** Themes to scan; both by default. */
  themes?: readonly Theme[];
};

/**
 * The standard accessibility pass for a page that is already open: axe (WCAG 2 AA) in
 * light and dark, and on the phone project also 44 px targets and no sideways scroll.
 * Leaves the page in the light theme.
 */
export async function checkPage(page: Page, options: CheckOptions = {}) {
  const where = new URL(page.url()).pathname;
  for (const theme of options.themes ?? THEMES) {
    await inTheme(page, theme);
    await expectNoAxeViolations(page, `${where}, ${isPhone(page) ? 'phone' : 'desktop'}, ${theme}`, options);
  }
  await expectFieldsDontZoom(page);
  if (isPhone(page)) {
    await expectTouchTargets(page, options.smallTargets);
    await expectNoSidewaysScroll(page);
  }
  await inTheme(page, 'light');
}
