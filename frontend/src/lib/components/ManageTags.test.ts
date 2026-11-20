import { flushSync, mount, unmount } from 'svelte';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { page, userEvent } from 'vitest/browser';
import ManageTags from './ManageTags.svelte';
import '../styles/tokens.css';
import '../styles/base.css';

vi.mock('#lib/client/recipes.js', async (original) => ({
  ...(await original<typeof import('#lib/client/recipes.js')>()),
  listTags: async () => ({
    tags: [
      { id: 1, name: 'south-indian', recipes: 2 },
      { id: 2, name: 'South Indian', recipes: 1 },
      { id: 3, name: 'quick', recipes: 4 }
    ]
  })
}));

// "Manage tags" is the shared Sheet: the title is its one heading, Escape and Close close it.
describe('"Manage tags" sheet', () => {
  let component: ReturnType<typeof mount> | null = null;
  afterEach(() => {
    if (component) unmount(component);
    component = null;
  });

  const show = () => {
    const onclose = vi.fn();
    component = mount(ManageTags, { target: document.body, props: { onclose } });
    flushSync();
    return onclose;
  };

  it('lists the tags in a dialog called "Manage tags"', async () => {
    show();
    await expect.element(page.getByRole('dialog', { name: 'Manage tags' })).toBeVisible();
    await expect.element(page.getByText('3 tags')).toBeVisible();
    await expect.element(page.getByText(/looks like South Indian/)).toBeVisible();
  });

  it('Escape closes it', async () => {
    const onclose = show();
    await expect.element(page.getByText('3 tags')).toBeVisible();
    await userEvent.keyboard('{Escape}');
    await vi.waitFor(() => expect(onclose).toHaveBeenCalled());
  });

  it('Close closes it; Merge into… asks, and Cancel comes back to the list', async () => {
    const onclose = show();
    await page.getByRole('button', { name: 'Merge quick into…' }).click();
    await expect.element(page.getByRole('button', { name: 'Merge', exact: true })).toBeVisible();
    await page.getByRole('button', { name: 'Cancel' }).click();
    await expect.element(page.getByRole('button', { name: 'Merge quick into…' })).toHaveFocus();
    await page.getByRole('button', { name: 'Close' }).click();
    expect(onclose).toHaveBeenCalled();
  });
});
