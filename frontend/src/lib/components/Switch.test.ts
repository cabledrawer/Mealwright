import { flushSync, mount, unmount } from 'svelte';
import { afterEach, describe, expect, it } from 'vitest';
import { page, userEvent } from 'vitest/browser';
import '$lib/styles/tokens.css';
import Switch from './Switch.svelte';

let component: ReturnType<typeof mount> | null = null;

afterEach(() => {
  if (component) unmount(component);
  component = null;
  document.body.innerHTML = '';
});

function render(props: Record<string, unknown>) {
  component = mount(Switch, { target: document.body, props });
  flushSync();
  return page.getByRole('switch');
}

describe('Switch', () => {
  it('is a real switch with a name, off by default', async () => {
    const sw = render({ label: 'Remember this phone' });
    await expect.element(sw).toHaveAccessibleName('Remember this phone');
    await expect.element(sw).toHaveAttribute('aria-checked', 'false');
  });

  it('switches on and off with a click, and says so', async () => {
    const changes: boolean[] = [];
    const sw = render({ label: 'Use', onchange: (v: boolean) => changes.push(v) });
    await sw.click();
    await expect.element(sw).toHaveAttribute('aria-checked', 'true');
    await sw.click();
    await expect.element(sw).toHaveAttribute('aria-checked', 'false');
    expect(changes).toEqual([true, false]);
  });

  it('works from the keyboard (Space and Enter)', async () => {
    const sw = render({ label: 'Use' });
    (sw.element() as HTMLElement).focus();
    await userEvent.keyboard(' ');
    await expect.element(sw).toHaveAttribute('aria-checked', 'true');
    await userEvent.keyboard('{Enter}');
    await expect.element(sw).toHaveAttribute('aria-checked', 'false');
  });

  it('can start on', async () => {
    const sw = render({ label: 'Use', checked: true });
    await expect.element(sw).toHaveAttribute('aria-checked', 'true');
  });

  it('does nothing when disabled', async () => {
    const changes: boolean[] = [];
    const sw = render({ label: 'Use', disabled: true, onchange: (v: boolean) => changes.push(v) });
    await sw.click({ force: true });
    await expect.element(sw).toHaveAttribute('aria-checked', 'false');
    expect(changes).toEqual([]);
  });

  it('can be named by visible text next to it', async () => {
    const text = document.createElement('span');
    text.id = 'remember-label';
    text.textContent = 'Remember for next time';
    document.body.append(text);
    const sw = render({ labelledby: 'remember-label' });
    await expect.element(sw).toHaveAccessibleName('Remember for next time');
  });

  it('is green when on, and easy to hit (44 px touch area)', async () => {
    const sw = render({ label: 'Use', checked: true });
    const el = sw.element() as HTMLElement;
    expect(getComputedStyle(el).backgroundColor).toBe('rgb(46, 125, 91)');
    const area = getComputedStyle(el, '::before');
    const box = el.getBoundingClientRect();
    expect(box.width - 2 * parseFloat(area.left)).toBeGreaterThanOrEqual(44);
    expect(box.height - 2 * parseFloat(area.top)).toBeGreaterThanOrEqual(44);
  });
});
