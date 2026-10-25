import { flushSync, mount, unmount } from 'svelte';
import { afterEach, describe, expect, it } from 'vitest';
import { page, userEvent } from 'vitest/browser';
import '#lib/styles/tokens.css';
import type { Lot } from '#lib/client/types.js';
import type { PantryModel } from '#lib/pantry.svelte.js';
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

function render(calls: unknown[][] = [], outcome: unknown = { ok: true }, width?: number) {
  const model = {
    setLeft: (...args: unknown[]) => {
      calls.push(args);
      return Promise.resolve(outcome);
    }
  } as unknown as PantryModel;
  document.body.innerHTML = '<span id="q">How much is left?</span><div id="box"></div>';
  const box = document.getElementById('box')!;
  if (width) box.style.width = `${width}px`;
  component = mount(PackPicks, {
    target: box,
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

  it('a save that fails leaves the saved amount ticked, not the tapped one', async () => {
    render([], { ok: false, error: new Error('offline') });
    await page.getByRole('radio', { name: '¼ left' }).click();
    await expect
      .element(page.getByRole('radio', { name: '½ left' }))
      .toHaveAttribute('aria-checked', 'true');
    await expect
      .element(page.getByRole('radio', { name: '¼ left' }))
      .toHaveAttribute('aria-checked', 'false');
  });

  it('in a narrow column (desktop Pantry) the marks go two by two, each 44 px wide with its text inside', async () => {
    render([], { ok: true }, 170);
    const radios = page.getByRole('radio').elements();
    expect(radios[2]!.getBoundingClientRect().top).toBeGreaterThan(
      radios[0]!.getBoundingClientRect().bottom - 1
    );
    for (const radio of radios) {
      expect(radio.getBoundingClientRect().width).toBeGreaterThanOrEqual(44);
      expect(radio.scrollWidth).toBeLessThanOrEqual(radio.clientWidth);
    }
  });

  it('with room, the four marks sit in one row', async () => {
    render([], { ok: true }, 360);
    const tops = page
      .getByRole('radio')
      .elements()
      .map((r) => r.getBoundingClientRect().top);
    expect(new Set(tops).size).toBe(1);
  });

  describe('arrow keys', () => {
    const focused = () =>
      (document.activeElement as HTMLElement | null)?.getAttribute('aria-label');

    it('only the chosen mark is in the Tab order', async () => {
      render();
      const radios = page.getByRole('radio').elements() as HTMLElement[];
      expect(radios.map((r) => r.tabIndex)).toEqual([-1, 0, -1, -1]);
    });

    it('the arrows move focus round the marks without saving; Space chooses', async () => {
      const calls: unknown[][] = [];
      render(calls);
      (page.getByRole('radio', { name: '½ left' }).element() as HTMLElement).focus();
      await userEvent.keyboard('{ArrowRight}');
      expect(focused()).toBe('¾ left');
      await userEvent.keyboard('{ArrowRight}');
      expect(focused()).toBe('Full');
      await userEvent.keyboard('{ArrowRight}');
      expect(focused()).toBe('¼ left');
      await userEvent.keyboard('{ArrowLeft}');
      expect(focused()).toBe('Full');
      await userEvent.keyboard('{Home}');
      expect(focused()).toBe('¼ left');
      expect(calls).toEqual([]);
      await userEvent.keyboard('{ArrowDown}');
      await userEvent.keyboard(' ');
      expect(calls).toEqual([[7, 'Paneer', { fraction: 0.5 }]]);
    });
  });
});
