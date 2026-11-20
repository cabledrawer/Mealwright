import { flushSync, mount, unmount } from 'svelte';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { page, userEvent } from 'vitest/browser';
import YourKitchen from './YourKitchen.svelte';
import '../styles/tokens.css';
import '../styles/base.css';

// "Your kitchen" is the shared Sheet: titled, closes on Escape, focus starts on the first stepper
// button, and Save sends what was set.
describe('"Your kitchen" sheet', () => {
  let component: ReturnType<typeof mount> | null = null;
  afterEach(() => {
    if (component) unmount(component);
    component = null;
  });

  const show = () => {
    const onclose = vi.fn();
    const onsaved = vi.fn();
    const save = vi.fn(async (kitchen) => kitchen);
    component = mount(YourKitchen, {
      target: document.body,
      props: {
        open: true,
        kitchen: { hob_rings: 4, pressure_cookers: 1, oven: true, asked: true },
        onsaved,
        onclose,
        save
      }
    });
    flushSync();
    return { onclose, onsaved, save };
  };

  it('is a dialog called "Your kitchen" with the focus on the first stepper button', async () => {
    show();
    await expect.element(page.getByRole('dialog', { name: 'Your kitchen' })).toBeVisible();
    await vi.waitFor(() => expect(document.activeElement?.closest('.stepper')).not.toBeNull());
  });

  it('Escape closes it without saving', async () => {
    const { onclose, save } = show();
    await expect.element(page.getByRole('dialog', { name: 'Your kitchen' })).toBeVisible();
    await userEvent.keyboard('{Escape}');
    await vi.waitFor(() => expect(onclose).toHaveBeenCalled());
    expect(save).not.toHaveBeenCalled();
  });

  it('Save sends the kitchen as set', async () => {
    const { onsaved, save } = show();
    await page.getByRole('radio', { name: 'No' }).click();
    await page.getByRole('button', { name: 'Save', exact: true }).click();
    await vi.waitFor(() => expect(onsaved).toHaveBeenCalled());
    expect(save).toHaveBeenCalledWith({ hob_rings: 4, pressure_cookers: 1, oven: false });
  });
});
