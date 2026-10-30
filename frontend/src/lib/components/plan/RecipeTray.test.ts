import { flushSync, mount, unmount } from 'svelte';
import { afterEach, describe, expect, it } from 'vitest';
import { page } from 'vitest/browser';
import type { RecipeList } from '#lib/recipes.svelte.js';
import RecipeTray from './RecipeTray.svelte';
import '#lib/styles/tokens.css';
import '#lib/styles/base.css';

let component: ReturnType<typeof mount> | null = null;

afterEach(() => {
  if (component) unmount(component);
  component = null;
  document.body.innerHTML = '';
});

const list = { filter: 'all', query: '', recipes: [], loaded: true, problem: null, all: 0 };

function show(open: boolean) {
  component = mount(RecipeTray, {
    target: document.body,
    props: {
      list: list as unknown as RecipeList,
      disabled: false,
      open,
      onopen: () => {},
      carry: () => {
        throw new Error('not used');
      },
      onchoose: () => {}
    }
  });
  flushSync();
}

describe('the recipe tray’s round button (F41)', () => {
  for (const open of [true, false]) {
    it(`${open ? 'open' : 'closed'}: a real icon, centred in the circle, no letter`, async () => {
      show(open);
      const name = open ? 'Collapse recipe tray' : 'Open recipe tray';
      await expect.element(page.getByRole('button', { name })).toBeVisible();
      const button = page.getByRole('button', { name }).element();
      const icon = button.querySelector('svg');
      expect(icon).not.toBeNull();
      expect(button.textContent?.trim()).toBe('');
      const circle = button.getBoundingClientRect();
      const mark = icon!.getBoundingClientRect();
      expect(Math.abs(mark.x + mark.width / 2 - (circle.x + circle.width / 2))).toBeLessThanOrEqual(
        1
      );
      expect(
        Math.abs(mark.y + mark.height / 2 - (circle.y + circle.height / 2))
      ).toBeLessThanOrEqual(1);
    });
  }
});
