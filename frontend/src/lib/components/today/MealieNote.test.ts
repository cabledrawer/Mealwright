// Today's note after an import from Mealie (0.9.5): how many came in and a way to the ones
// with lines to check, or that it stopped.

import { flushSync, mount, unmount } from 'svelte';
import { afterEach, describe, expect, it } from 'vitest';
import { page } from 'vitest/browser';
import type { MealieNote as Note } from '#lib/client/today.js';
import MealieNote from './MealieNote.svelte';
import '#lib/styles/tokens.css';
import '#lib/styles/base.css';

describe('Today’s note from Mealie', () => {
  let component: ReturnType<typeof mount> | null = null;

  function show(note: Note) {
    component = mount(MealieNote, { target: document.body, props: { note } });
    flushSync();
  }

  afterEach(() => {
    if (component) unmount(component);
    component = null;
    document.body.innerHTML = '';
  });

  it('says how many came in and opens the ones to check', async () => {
    show({ id: 4, state: 'done', recipes: 202, to_check: 31 });
    await expect.element(page.getByText('202 recipes brought in from Mealie')).toBeVisible();
    await expect.element(page.getByText('31 have lines to check')).toBeVisible();
    const check = page.getByRole('link', { name: 'Check them' });
    expect(check.element().getAttribute('href')).toBe('/recipes/drafts?from=mealie');
  });

  it('with nothing to check, it opens the import', async () => {
    show({ id: 4, state: 'done', recipes: 1, to_check: 0 });
    await expect.element(page.getByText('1 recipe brought in from Mealie')).toBeVisible();
    await expect.element(page.getByRole('link', { name: 'Check them' })).not.toBeInTheDocument();
    const open = page.getByRole('link', { name: 'Open Import from Mealie' });
    expect(open.element().getAttribute('href')).toBe('/settings/your-data/mealie');
  });

  it('says when it stopped, and that what came in is kept', async () => {
    show({ id: 4, state: 'failed', recipes: 40, to_check: 0 });
    await expect.element(page.getByText('The import from Mealie stopped')).toBeVisible();
    await expect
      .element(page.getByText('Recipes brought in before it stopped are kept.'))
      .toBeVisible();
  });
});
