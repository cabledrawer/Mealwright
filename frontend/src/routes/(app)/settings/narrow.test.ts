// F253 (0.9.5-beta.3): Settings with the main menu unfolded on a narrow computer screen (768 px:
// 768 − 248 px menu − 2 × 40 px page margins leaves 440 px). The page's heading must not break
// inside a word, and the Theme switch must stay inside its card with room to spare.

import { flushSync, mount, unmount } from 'svelte';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { page } from 'vitest/browser';
import { session } from '#lib/session.svelte.js';
import { fakeApi } from '#lib/testing/fakeApi.js';
import { ME } from '#lib/testing/fakeShopping.js';
import Fixture from '#lib/testing/SettingsPageFixture.svelte';
import '#lib/styles/tokens.css';
import '#lib/styles/base.css';

vi.mock('$app/navigation', () => ({ goto: vi.fn(async () => {}) }));
vi.mock('$app/state', () => ({
  page: {
    url: new URL('http://localhost/settings/appearance'),
    route: { id: '/(app)/settings/appearance' }
  }
}));

/** Each word of the element's text sits on one line (none is cut in two). */
function wordsWhole(element: Element): string[] {
  const cut: string[] = [];
  const text = element.firstChild;
  if (!text || text.nodeType !== Node.TEXT_NODE) throw new Error('no text');
  const words = text.textContent!.matchAll(/\S+/g);
  for (const word of words) {
    const range = document.createRange();
    range.setStart(text, word.index);
    range.setEnd(text, word.index + word[0].length);
    const tops = new Set([...range.getClientRects()].map((rect) => Math.round(rect.top)));
    if (tops.size > 1) cut.push(word[0]);
  }
  return cut;
}

describe('Settings in a narrow room (F253)', () => {
  let component: ReturnType<typeof mount> | null = null;

  beforeEach(async () => {
    await page.viewport(768, 900);
    session.me = { ...ME, role: 'admin' };
    fakeApi({ 'GET /household': [200, { name: 'Home', pints: 'uk', onboarding_done: true }] });
  });

  afterEach(() => {
    if (component) unmount(component);
    component = null;
    document.body.innerHTML = '';
    session.me = null;
  });

  it.each([440, 520, 691, 1028])(
    'at %i px of room the heading is whole and the switch clears the card edge',
    async (width) => {
      component = mount(Fixture, { target: document.body, props: { width } });
      flushSync();
      const heading = page.getByRole('heading', { level: 1, name: 'Appearance' });
      await expect.element(heading).toBeVisible();
      expect(wordsWhole(heading.element())).toEqual([]);
      const theme = page.getByRole('group', { name: 'Theme' }).element().getBoundingClientRect();
      const card = page
        .getByRole('group', { name: 'Theme' })
        .element()
        .closest('.card')!
        .getBoundingClientRect();
      expect(theme.right).toBeLessThanOrEqual(card.right - 12);
      expect(theme.left).toBeGreaterThanOrEqual(card.left + 12);
      // The Settings list stays beside the page, every item still there to pick.
      const list = page.getByRole('navigation', { name: 'Settings' });
      await expect.element(list).toBeVisible();
      expect(list.element().getBoundingClientRect().right).toBeLessThanOrEqual(
        heading.element().getBoundingClientRect().left
      );
    }
  );
});
