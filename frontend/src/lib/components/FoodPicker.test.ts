// F265 (cabledrawer 21 Nov): Escape in "Find an ingredient" closes the sheet around it, unless
// the picker has a Cancel of its own (then Escape does that, and only that).
import { flushSync, mount, unmount } from 'svelte';
import { afterEach, describe, expect, it } from 'vitest';
import { page, userEvent } from 'vitest/browser';
import '#lib/styles/tokens.css';
import '#lib/styles/base.css';
import FoodPickerSheetFixture from '#lib/testing/FoodPickerSheetFixture.svelte';

let component: ReturnType<typeof mount> | null = null;

afterEach(() => {
  if (component) unmount(component);
  component = null;
  document.body.innerHTML = '';
});

async function open(withCancel: boolean) {
  const log: string[] = [];
  component = mount(FoodPickerSheetFixture, { target: document.body, props: { withCancel, log } });
  flushSync();
  const opener = page.getByRole('button', { name: 'Open it' });
  await opener.click();
  await expect.element(page.getByRole('searchbox', { name: 'Find an ingredient' })).toHaveFocus();
  return { log, opener };
}

describe('FoodPicker inside a sheet', () => {
  it('Escape with the focus in the box closes the sheet when the picker has no Cancel', async () => {
    const { log, opener } = await open(false);
    await userEvent.keyboard('{Escape}');
    flushSync();
    expect(log).toEqual(['sheet closed']);
    expect(document.querySelector('dialog')).toBeNull();
    await expect.element(opener).toHaveFocus();
    // A second Escape has nothing left to close.
    await userEvent.keyboard('{Escape}');
    expect(log).toEqual(['sheet closed']);
  });

  it('with a Cancel of its own, Escape does that and leaves the sheet open', async () => {
    const { log } = await open(true);
    await userEvent.keyboard('{Escape}');
    flushSync();
    expect(log).toEqual(['picker cancelled']);
    expect(document.querySelector('dialog')).not.toBeNull();
  });
});
