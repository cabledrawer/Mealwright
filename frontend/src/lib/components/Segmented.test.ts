import { flushSync, mount, unmount } from 'svelte';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { page, userEvent } from 'vitest/browser';
import '#lib/styles/tokens.css';
import Segmented from './Segmented.svelte';

let component: ReturnType<typeof mount> | null = null;

afterEach(() => {
  if (component) unmount(component);
  component = null;
  document.body.innerHTML = '';
});

const options = [
  { value: 'a', label: 'Auto' },
  { value: 'l', label: 'Light' },
  { value: 'd', label: 'Dark' }
];

function render(props: Record<string, unknown> = {}) {
  const onchange = vi.fn();
  component = mount(Segmented, {
    target: document.body,
    props: { options, value: 'l', onchange, label: 'Theme', ...props }
  });
  flushSync();
  return onchange;
}

describe('Segmented', () => {
  it('is a labelled radiogroup with the current one checked', async () => {
    render();
    const group = page.getByRole('radiogroup', { name: 'Theme' });
    await expect
      .element(group.getByRole('radio', { name: 'Light' }))
      .toHaveAttribute('aria-checked', 'true');
    await expect
      .element(group.getByRole('radio', { name: 'Dark' }))
      .toHaveAttribute('aria-checked', 'false');
  });

  it('tells which one was chosen when one is tapped', async () => {
    const onchange = render();
    await page.getByRole('radio', { name: 'Dark' }).click();
    expect(onchange).toHaveBeenCalledWith('d');
  });

  it('moves with the arrow keys', async () => {
    const onchange = render();
    (document.querySelector('[aria-checked="true"]') as HTMLElement).focus();
    await userEvent.keyboard('{ArrowRight}');
    expect(onchange).toHaveBeenCalledWith('d');
  });

  it('chooses nothing while it is disabled', async () => {
    const onchange = render({ disabled: true });
    await expect.element(page.getByRole('radio', { name: 'Dark' })).toBeDisabled();
    expect(onchange).not.toHaveBeenCalled();
  });
});
