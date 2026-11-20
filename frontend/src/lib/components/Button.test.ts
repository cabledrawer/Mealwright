import { flushSync, mount, unmount } from 'svelte';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { page } from 'vitest/browser';
import '#lib/styles/tokens.css';
import ButtonFixture from '#lib/testing/ButtonFixture.svelte';

let component: ReturnType<typeof mount> | null = null;

afterEach(() => {
  if (component) unmount(component);
  component = null;
  document.body.innerHTML = '';
});

function render(props: Record<string, unknown> = {}) {
  component = mount(ButtonFixture, { target: document.body, props });
  flushSync();
}

describe('Button', () => {
  it('is a button that says its words and runs onclick', async () => {
    const onclick = vi.fn();
    render({ onclick });
    await page.getByRole('button', { name: 'Save' }).click();
    expect(onclick).toHaveBeenCalledOnce();
  });

  it('does nothing while disabled', async () => {
    const onclick = vi.fn();
    render({ onclick, disabled: true });
    await expect.element(page.getByRole('button', { name: 'Save' })).toBeDisabled();
    expect(onclick).not.toHaveBeenCalled();
  });

  it('passes data-testid and aria attributes on to the button', async () => {
    render({ testid: 'the-one', describedby: 'why' });
    const button = page.getByTestId('the-one');
    await expect.element(button).toHaveAttribute('aria-describedby', 'why');
  });

  it('has a main, a quiet, a danger and a small look that differ', async () => {
    render({ both: true });
    const look = (name: string) =>
      getComputedStyle(page.getByRole('button', { name }).element()).backgroundColor;
    expect(look('Quiet')).not.toBe(look('Save'));
    expect(look('Danger')).not.toBe(look('Save'));
    const small = page.getByRole('button', { name: 'Small' }).element() as HTMLElement;
    const main = page.getByRole('button', { name: 'Save' }).element() as HTMLElement;
    expect(small.getBoundingClientRect().height).toBeLessThan(main.getBoundingClientRect().height);
  });

  it('has the older looks as variants: a line, words only, soft, green, stop and warn', async () => {
    render({ looks: true });
    const style = (name: string) =>
      getComputedStyle(page.getByRole('button', { name, exact: true }).element());
    expect(style('Outline').borderTopWidth).toBe('1px');
    expect(style('Outline').backgroundColor).toBe('rgba(0, 0, 0, 0)');
    expect(style('Plain').backgroundColor).toBe('rgba(0, 0, 0, 0)');
    expect(style('Plain').borderTopWidth).toBe('0px');
    const fills = ['Soft', 'Yes', 'Stop', 'Warn', 'Save'].map((n) => style(n).backgroundColor);
    expect(new Set(fills).size).toBe(fills.length);
  });
});
