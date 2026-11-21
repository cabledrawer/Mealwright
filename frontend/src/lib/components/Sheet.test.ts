import { flushSync, mount, unmount } from 'svelte';
import { afterEach, describe, expect, it } from 'vitest';
import { page, userEvent } from 'vitest/browser';
import '#lib/styles/tokens.css';
import '#lib/styles/base.css';
import SheetFixture from '#lib/testing/SheetFixture.svelte';

let component: ReturnType<typeof mount> | null = null;

afterEach(() => {
  if (component) unmount(component);
  component = null;
  document.body.innerHTML = '';
});

async function open(props: Record<string, unknown> = {}) {
  const log: string[] = [];
  component = mount(SheetFixture, { target: document.body, props: { ...props, log } });
  flushSync();
  const opener = page.getByRole('button', { name: 'Open it' });
  await opener.click();
  return { log, opener };
}

describe('Sheet', () => {
  it('is a modal dialog named by its one level-2 title', async () => {
    await open();
    const dialog = page.getByRole('dialog', { name: 'Remove Onion?' });
    await expect.element(dialog).toBeVisible();
    await expect
      .element(dialog.getByRole('heading', { level: 2 }))
      .toHaveTextContent('Remove Onion?');
    expect(document.querySelector('dialog')?.matches(':modal')).toBe(true);
  });

  it('moves the focus into the dialog when it opens (F271)', async () => {
    await open();
    await expect.element(page.getByRole('dialog')).toBeVisible();
    expect(document.querySelector('dialog')?.contains(document.activeElement)).toBe(true);
  });

  it('keeps the focus off the page behind while it is open', async () => {
    await open();
    for (let i = 0; i < 6; i++) {
      await userEvent.tab();
      // Inside the dialog, or on the browser's own bar (then body); never on the page behind.
      const at = document.activeElement;
      expect(at === document.body || document.querySelector('dialog')?.contains(at)).toBe(true);
      expect(at?.textContent).not.toBe('Open it');
    }
  });

  it('Escape does the Cancel choice and gives the focus back to what opened it', async () => {
    const { log, opener } = await open();
    await userEvent.keyboard('{Escape}');
    flushSync();
    expect(log).toEqual(['close']);
    expect(document.querySelector('dialog')).toBeNull();
    await expect.element(opener).toHaveFocus();
  });

  it('a tap outside does the Cancel choice', async () => {
    const { log } = await open();
    const dialog = document.querySelector('dialog')!;
    dialog.dispatchEvent(new MouseEvent('click', { bubbles: true }));
    flushSync();
    expect(log).toEqual(['close']);
  });

  it('a tap inside does not close it', async () => {
    const { log } = await open();
    await page.getByRole('button', { name: 'Last' }).click();
    expect(log).toEqual([]);
  });

  it('a must-answer sheet ignores a tap outside, but Escape still cancels', async () => {
    const { log } = await open({ outside: false });
    document.querySelector('dialog')!.dispatchEvent(new MouseEvent('click', { bubbles: true }));
    flushSync();
    expect(log).toEqual([]);
    await userEvent.keyboard('{Escape}');
    expect(log).toEqual(['close']);
  });

  it('a locked sheet (saving) ignores both', async () => {
    const { log } = await open({ locked: true });
    document.querySelector('dialog')!.dispatchEvent(new MouseEvent('click', { bubbles: true }));
    await userEvent.keyboard('{Escape}');
    flushSync();
    expect(log).toEqual([]);
    expect(document.querySelector('dialog')?.open).toBe(true);
  });

  it('taller than the screen: it stays inside the screen and scrolls to its last button', async () => {
    await open({ tall: true });
    const dialog = document.querySelector('dialog')!;
    const box = dialog.getBoundingClientRect();
    expect(box.height).toBeLessThanOrEqual(window.innerHeight);
    expect(dialog.scrollHeight).toBeGreaterThan(dialog.clientHeight);
    const last = page.getByRole('button', { name: 'Last' });
    (last.element() as HTMLElement).scrollIntoView();
    const at = (last.element() as HTMLElement).getBoundingClientRect();
    expect(at.bottom).toBeLessThanOrEqual(window.innerHeight);
    expect(at.top).toBeGreaterThanOrEqual(0);
  });
});
