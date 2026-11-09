import { flushSync, mount, unmount } from 'svelte';
import { afterEach, describe, expect, it } from 'vitest';
import { page } from 'vitest/browser';
import type { TubRow } from '#lib/client/types.js';
import PantryTub from './PantryTub.svelte';
import '../styles/tokens.css';
import '../styles/base.css';

const long: TubRow = {
  batch_id: 1,
  tub_id: 1,
  recipe_name: 'Steph’s Chickpea Curry with Spinach and Coconut',
  colour: null,
  tubs: 2,
  words: '2 tubs',
  use_by: '2026-11-12',
  days_left: 2,
  use_soon: true
};

describe('a leftover tub row on the Pantry page (F180)', () => {
  let component: ReturnType<typeof mount> | null = null;

  afterEach(() => {
    if (component) unmount(component);
    component = null;
    document.body.innerHTML = '';
  });

  for (const width of [390, 800, 1101]) {
    it(`shows a long name whole, wrapped, at ${width} px`, async () => {
      await page.viewport(width, 800);
      // A card column about as wide as the Freezer card on a 1101 px page.
      const holder = document.createElement('ul');
      holder.style.width = '300px';
      holder.style.padding = '0';
      document.body.appendChild(holder);
      component = mount(PantryTub, { target: holder, props: { tub: long } });
      flushSync();
      const name = holder.querySelector('.name') as HTMLElement;
      expect(name.textContent).toBe(long.recipe_name);
      const style = getComputedStyle(name);
      expect(style.textOverflow).not.toBe('ellipsis');
      expect(style.whiteSpace).not.toBe('nowrap');
      // Nothing is cut off: all of the text fits inside the box, on more than one line.
      expect(name.scrollWidth).toBeLessThanOrEqual(name.clientWidth);
      expect(name.getBoundingClientRect().height).toBeGreaterThan(
        parseFloat(style.lineHeight) * 1.5
      );
    });
  }
});
