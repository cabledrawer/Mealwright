// "Wren’s version": a Sheet over the editor. Escape and Back to my edit both just close it;
// Save mine anyway is the other choice and waits while the save can't go.
import { flushSync, mount, unmount } from 'svelte';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { page, userEvent } from 'vitest/browser';
import type { RecipeOut } from '#lib/client/recipes.js';
import ConflictSheet from './ConflictSheet.svelte';
import '#lib/styles/tokens.css';
import '#lib/styles/base.css';

let component: ReturnType<typeof mount> | null = null;
afterEach(() => {
  if (component) unmount(component);
  component = null;
  document.body.innerHTML = '';
});

const recipe = (serves: number) =>
  ({
    id: 1,
    name: 'Sambar',
    description: null,
    time_minutes: 50,
    serves,
    lines: [],
    steps: [],
    tags: []
  }) as unknown as RecipeOut;

function show(busy = false) {
  const onclose = vi.fn();
  const onsave = vi.fn();
  component = mount(ConflictSheet, {
    target: document.body,
    props: {
      who: 'Wren',
      opened: recipe(6),
      theirs: recipe(8),
      phone: false,
      busy,
      onclose,
      onsave
    }
  });
  flushSync();
  return { onclose, onsave };
}

describe('the conflict sheet', () => {
  it('is a dialog called "Wren’s version", and Escape closes it', async () => {
    const { onclose } = show();
    await expect.element(page.getByRole('dialog', { name: 'Wren’s version' })).toBeVisible();
    await userEvent.keyboard('{Escape}');
    await vi.waitFor(() => expect(onclose).toHaveBeenCalledTimes(1));
  });

  it('has Back to my edit and Save mine anyway', async () => {
    const { onclose, onsave } = show();
    await page.getByRole('button', { name: 'Back to my edit' }).click();
    expect(onclose).toHaveBeenCalledTimes(1);
    await page.getByRole('button', { name: 'Save mine anyway' }).click();
    expect(onsave).toHaveBeenCalledTimes(1);
  });

  it('cannot save mine while busy', async () => {
    show(true);
    await expect.element(page.getByRole('button', { name: 'Save mine anyway' })).toBeDisabled();
  });
});
