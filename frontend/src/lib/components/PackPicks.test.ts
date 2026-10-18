import { flushSync, mount, unmount } from 'svelte';
import { afterEach, describe, expect, it } from 'vitest';
import { page } from 'vitest/browser';
import '$lib/styles/tokens.css';
import type { Lot } from '$lib/client/types';
import type { PantryModel } from '$lib/pantry.svelte';
import PackPicks from './PackPicks.svelte';

let component: ReturnType<typeof mount> | null = null;

afterEach(() => {
  if (component) unmount(component);
  component = null;
  document.body.innerHTML = '';
});

// A 200 g pack with 100 g left: ½.
const lot = {
  id: 7,
  open: true,
  stock: {
    amount: 100,
    display: '½ pack · about 100 g',
    as_sold: { count: 0.5, size: { id: 1, name: 'pack', plural: 'packs', amount: 200 } }
  }
} as unknown as Lot;

function render(calls: unknown[][] = [], outcome: unknown = { ok: true }) {
  const model = {
    setLeft: (...args: unknown[]) => {
      calls.push(args);
      return Promise.resolve(outcome);
    }
  } as unknown as PantryModel;
  document.body.innerHTML = '<span id="q">How much is left?</span>';
  component = mount(PackPicks, {
    target: document.body,
    props: { lot, name: 'Paneer', model, labelledby: 'q' }
  });
  flushSync();
}

describe('PackPicks', () => {
  it('is a radio group of ¼ · ½ · ¾ · Full with the current one checked', async () => {
    render();
    await expect.element(page.getByRole('radiogroup', { name: 'How much is left?' })).toBeVisible();
    await expect.element(page.getByRole('radio')).toHaveLength(4);
    await expect
      .element(page.getByRole('radio', { name: '½ left' }))
      .toHaveAttribute('aria-checked', 'true');
    await expect
      .element(page.getByRole('radio', { name: 'Full' }))
      .toHaveAttribute('aria-checked', 'false');
  });

  it('tapping one saves that fraction and checks it at once', async () => {
    const calls: unknown[][] = [];
    render(calls);
    await page.getByRole('radio', { name: '¾ left' }).click();
    expect(calls).toEqual([[7, 'Paneer', { fraction: 0.75 }]]);
    await expect
      .element(page.getByRole('radio', { name: '¾ left' }))
      .toHaveAttribute('aria-checked', 'true');
  });

  it('every mark is at least 44 px tall', async () => {
    render();
    for (const radio of page.getByRole('radio').elements()) {
      expect(radio.getBoundingClientRect().height).toBeGreaterThanOrEqual(44);
    }
  });
});
