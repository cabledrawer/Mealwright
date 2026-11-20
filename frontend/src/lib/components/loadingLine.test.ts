import { flushSync, mount, unmount } from 'svelte';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { page } from 'vitest/browser';
import IngredientEditor from './IngredientEditor.svelte';
import '#lib/styles/tokens.css';
import '#lib/styles/base.css';

// FE15: "Loading…" is the one shared line (role="status"), not words in a heading.
describe('the ingredient editor while it waits for the server', () => {
  let component: ReturnType<typeof mount> | null = null;
  afterEach(() => {
    if (component) unmount(component);
    component = null;
    document.body.innerHTML = '';
    vi.unstubAllGlobals();
  });

  it('shows the shared Loading line under an "Ingredient" heading', async () => {
    vi.stubGlobal('fetch', () => new Promise<Response>(() => {}));
    component = mount(IngredientEditor, {
      target: document.body,
      props: { foodId: 1, variant: 'panel' }
    });
    flushSync();
    await expect.element(page.getByRole('status')).toHaveTextContent('Loading…');
    await expect.element(page.getByRole('heading', { name: 'Ingredient' })).toBeVisible();
    expect(page.getByRole('heading', { name: 'Loading…' }).elements()).toEqual([]);
  });
});
