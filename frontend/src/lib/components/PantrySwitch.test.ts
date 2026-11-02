import { flushSync, mount, unmount } from 'svelte';
import { afterEach, beforeEach, describe, expect, it } from 'vitest';
import { page } from 'vitest/browser';
import { pantrySide, rememberSide } from '#lib/pantrySide.svelte.js';
import PantrySwitch from './PantrySwitch.svelte';
import TabBar from './TabBar.svelte';
import '../styles/tokens.css';
import '../styles/base.css';

describe('the phone’s Pantry · Ingredients switch (F76, N1)', () => {
  let component: ReturnType<typeof mount> | null = null;

  beforeEach(async () => {
    localStorage.clear();
    rememberSide('pantry');
    await page.viewport(390, 800);
  });

  afterEach(() => {
    if (component) unmount(component);
    component = null;
    document.body.innerHTML = '';
    localStorage.clear();
  });

  it('has the two views as links, the current one marked', async () => {
    component = mount(PantrySwitch, { target: document.body, props: { current: 'ingredients' } });
    flushSync();
    await expect
      .element(page.getByRole('link', { name: 'Pantry' }))
      .toHaveAttribute('href', '/pantry');
    await expect
      .element(page.getByRole('link', { name: 'Ingredients' }))
      .toHaveAttribute('href', '/recipes/ingredients?from=pantry');
    await expect
      .element(page.getByRole('link', { name: 'Ingredients' }))
      .toHaveAttribute('aria-current', 'page');
    expect(
      page
        .getByRole('link')
        .elements()
        .filter((a) => a.getAttribute('aria-current') === 'page')
    ).toHaveLength(1);
  });

  it('is 44 px tall to tap', async () => {
    component = mount(PantrySwitch, { target: document.body, props: { current: 'pantry' } });
    flushSync();
    for (const link of page.getByRole('link').elements()) {
      expect(link.getBoundingClientRect().height).toBeGreaterThanOrEqual(44);
    }
  });

  it('remembers the choice, and the Pantry tab then opens it', async () => {
    const tabs = mount(TabBar, { target: document.body });
    component = mount(PantrySwitch, { target: document.body, props: { current: 'pantry' } });
    flushSync();
    const tab = page
      .getByRole('navigation', { name: 'Main' })
      .getByRole('link', { name: 'Pantry' });
    await expect.element(tab).toHaveAttribute('href', '/pantry');
    // Tap Ingredients (the link goes nowhere in this test: the click is stopped).
    const link = page.getByRole('navigation', { name: 'Pantry or Ingredients' }).getByRole('link', {
      name: 'Ingredients'
    });
    link.element().addEventListener('click', (event) => event.preventDefault());
    await link.click();
    expect(pantrySide.value).toBe('ingredients');
    expect(localStorage.getItem('mealwright.pantry-side')).toBe('ingredients');
    await expect.element(tab).toHaveAttribute('href', '/recipes/ingredients?from=pantry');
    rememberSide('pantry');
    await expect.element(tab).toHaveAttribute('href', '/pantry');
    unmount(tabs);
  });
});
