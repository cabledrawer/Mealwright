import { flushSync, mount, unmount } from 'svelte';
import { afterEach, describe, expect, it } from 'vitest';
import '#lib/styles/tokens.css';
import ButtonRowFixture from '#lib/testing/ButtonRowFixture.svelte';
import buttonRowSource from './ButtonRow.svelte?raw';
import sheetSource from './Sheet.svelte?raw';

// cabledrawer 20 Nov: the Tab order is the order on the screen, at every width. So the foot of a
// sheet is never reversed with CSS: the source order is the screen order.
let component: ReturnType<typeof mount> | null = null;

afterEach(() => {
  if (component) unmount(component);
  component = null;
  document.body.innerHTML = '';
});

function positions(stack: boolean) {
  component = mount(ButtonRowFixture, { target: document.body, props: { stack } });
  flushSync();
  return [...document.querySelectorAll('button')].map((b) => b.getBoundingClientRect());
}

describe('ButtonRow', () => {
  it('shows the buttons in the order they are in the source (side by side)', () => {
    const at = positions(false);
    expect(at).toHaveLength(3);
    // Left to right, or (if they wrap) top to bottom: never back the other way.
    for (let i = 1; i < at.length; i++) {
      const [now, before] = [at[i]!, at[i - 1]!];
      const after = now.top > before.top || now.left > before.left;
      expect(after, `button ${i} comes after button ${i - 1}`).toBe(true);
    }
  });

  it('shows stacked buttons top to bottom in the order of the source', () => {
    const at = positions(true);
    for (let i = 1; i < at.length; i++) expect(at[i]!.top).toBeGreaterThan(at[i - 1]!.top);
  });

  it('never reverses the order with CSS (ButtonRow and Sheet)', () => {
    for (const source of [buttonRowSource, sheetSource]) {
      expect(source).not.toMatch(/row-reverse|column-reverse|[^-\w]order\s*:/);
    }
  });
});
