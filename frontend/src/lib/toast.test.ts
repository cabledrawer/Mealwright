import { flushSync, mount, unmount } from 'svelte';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { page, userEvent } from 'vitest/browser';
import Toast from './components/Toast.svelte';
import { TOAST_MS, toasts } from './toast.svelte';
import './styles/tokens.css';
import './styles/base.css';

beforeEach(() => {
  vi.useFakeTimers();
  toasts.dismiss();
});

afterEach(() => {
  toasts.dismiss();
  vi.useRealTimers();
});

describe('toasts', () => {
  it('shows one message at a time; a new one replaces the last', () => {
    toasts.show('Toor dal moved to Fridge');
    toasts.show('Milk used up');
    expect(toasts.current?.message).toBe('Milk used up');
  });

  it('goes away by itself after a few seconds', () => {
    toasts.show('Saved');
    vi.advanceTimersByTime(TOAST_MS - 1);
    expect(toasts.current).not.toBeNull();
    vi.advanceTimersByTime(1);
    expect(toasts.current).toBeNull();
  });

  it('waits while paused, then still gives time to read it', () => {
    toasts.show('Saved');
    vi.advanceTimersByTime(TOAST_MS - 100);
    toasts.pause();
    vi.advanceTimersByTime(60_000);
    expect(toasts.current).not.toBeNull();
    toasts.resume();
    vi.advanceTimersByTime(1500);
    expect(toasts.current).not.toBeNull();
    vi.advanceTimersByTime(500);
    expect(toasts.current).toBeNull();
  });

  it("an old toast's timer never closes a newer one", () => {
    toasts.show('First');
    vi.advanceTimersByTime(TOAST_MS - 10);
    toasts.show('Second');
    vi.advanceTimersByTime(20);
    expect(toasts.current?.message).toBe('Second');
  });

  it('dismiss(id) only closes that toast', () => {
    const first = toasts.show('First');
    toasts.show('Second');
    toasts.dismiss(first);
    expect(toasts.current?.message).toBe('Second');
  });

  it('pressing the button closes the toast and runs its action', () => {
    const run = vi.fn();
    toasts.show('Toor dal moved', { action: { label: 'Undo', run } });
    toasts.act();
    expect(run).toHaveBeenCalledOnce();
    expect(toasts.current).toBeNull();
  });
});

describe('Toast', () => {
  let component: ReturnType<typeof mount> | null = null;

  // The page checks below wait using real timers.
  beforeEach(() => vi.useRealTimers());

  afterEach(() => {
    if (component) unmount(component);
    component = null;
  });

  function render() {
    component = mount(Toast, { target: document.body });
    flushSync();
  }

  it('is a polite live region that is there before any message', async () => {
    render();
    const region = page.getByRole('status');
    await expect.element(region).toBeInTheDocument();
    await expect.element(region).toHaveAttribute('aria-live', 'polite');
    await expect.element(region).toHaveTextContent('');
  });

  it('shows the message and an Undo button that works with the keyboard', async () => {
    const run = vi.fn();
    render();
    toasts.show('Toor dal moved to Fridge', { action: { label: 'Undo', run } });
    flushSync();
    await expect.element(page.getByRole('status')).toMatchTextContent(/Toor dal moved to Fridge/);
    const undo = page.getByRole('button', { name: 'Undo' });
    (undo.element() as HTMLElement).focus();
    await userEvent.keyboard('{Enter}');
    expect(run).toHaveBeenCalledOnce();
    flushSync();
    await expect.element(page.getByRole('status')).toHaveTextContent('');
  });

  it('stays while the keyboard is on its button', async () => {
    vi.useFakeTimers();
    render();
    toasts.show('Saved', { action: { label: 'Undo', run: () => {} } });
    flushSync();
    (page.getByRole('button', { name: 'Undo' }).element() as HTMLElement).focus();
    vi.advanceTimersByTime(TOAST_MS * 3);
    expect(toasts.current?.message).toBe('Saved');
  });

  it('has a button at least 44 × 44 px', async () => {
    render();
    toasts.show('Saved', { action: { label: 'Undo', run: () => {} } });
    flushSync();
    const box = page.getByRole('button', { name: 'Undo' }).element().getBoundingClientRect();
    expect(box.width).toBeGreaterThanOrEqual(44);
    expect(box.height).toBeGreaterThanOrEqual(44);
  });

  it('can still be used while a modal sheet is open, and comes back after', async () => {
    render();
    const dialog = document.createElement('dialog');
    dialog.innerHTML = '<p>Sheet</p>';
    document.body.append(dialog);
    dialog.showModal();
    const run = vi.fn();
    toasts.show('Toor dal is a staple', { action: { label: 'Undo', run } });
    flushSync();
    const region = document.querySelector('[role="status"]')!;
    expect(dialog.contains(region)).toBe(true);
    await page.getByRole('button', { name: 'Undo' }).click();
    expect(run).toHaveBeenCalledOnce();
    dialog.close();
    await vi.waitFor(() => expect(dialog.contains(region)).toBe(false));
    dialog.remove();
  });
});
