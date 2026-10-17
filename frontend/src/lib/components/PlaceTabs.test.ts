import { flushSync, mount, unmount } from 'svelte';
import { afterEach, describe, expect, it } from 'vitest';
import { page } from 'vitest/browser';
import PlaceTabs, { type Tab } from './PlaceTabs.svelte';
import '../styles/tokens.css';
import '../styles/base.css';

const places: Tab[] = ['Fridge', 'Freezer', 'Cupboard', 'Spice rack'].map((label) => ({
  id: label,
  label
}));

describe('the phone place tabs', () => {
  let component: ReturnType<typeof mount> | null = null;
  let box: HTMLElement | null = null;

  afterEach(() => {
    if (component) unmount(component);
    box?.remove();
    component = null;
  });

  async function render(tabs: Tab[]) {
    box = document.createElement('div');
    box.style.width = '350px';
    document.body.append(box);
    component = mount(PlaceTabs, { target: box, props: { tabs, selected: 'All', panelId: 'p' } });
    flushSync();
    await new Promise((resolve) => setTimeout(resolve, 50));
    flushSync();
    const list = page.getByRole('tablist', { name: 'Where' });
    const names = (await list.getByRole('tab').all()).map((t) => t.element().textContent?.trim());
    expect((list.element() as HTMLElement).scrollWidth).toBeLessThanOrEqual(350);
    return names;
  }

  it('keeps pinned tabs, in order, and puts the rest that don’t fit under More', async () => {
    const names = await render([
      { id: 'All', label: 'All', pinned: true },
      ...places,
      { id: 'soon', label: 'Use soon', pinned: true }
    ]);
    expect(names[0]).toBe('All');
    expect(names.at(-1)).toBe('Use soon');
    expect(names).toContain('More');
  });

  it('with Use soon not pinned, it is the first to go under More', async () => {
    const names = await render([
      { id: 'All', label: 'All', pinned: true },
      ...places,
      { id: 'soon', label: 'Use soon' }
    ]);
    expect(names).toContain('Cupboard');
    expect(names).not.toContain('Use soon');
    expect(names.at(-1)).toBe('More');
  });
});
