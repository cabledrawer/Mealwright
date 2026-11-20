import { flushSync, mount, unmount } from 'svelte';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { page } from 'vitest/browser';
import { toasts } from '#lib/toast.svelte';
import Lazy from './Lazy.svelte';
import Loading from './Loading.svelte';

let component: ReturnType<typeof mount> | null = null;

beforeEach(() => toasts.dismiss());
afterEach(() => {
  if (component) unmount(component);
  component = null;
  document.body.innerHTML = '';
  toasts.dismiss();
});

function render(props: Record<string, unknown>) {
  component = mount(Lazy as never, { target: document.body, props });
  flushSync();
}

describe('Lazy', () => {
  it('shows the loaded component with the other props handed on', async () => {
    render({ load: () => Promise.resolve({ default: Loading }), what: 'Loading the plan…' });
    await expect.element(page.getByRole('status')).toHaveTextContent('Loading the plan…');
    expect(toasts.current).toBeNull();
  });

  it('a failed fetch says so with a real Try again that fetches again, and runs onfail', async () => {
    const load = vi
      .fn<() => Promise<{ default: typeof Loading }>>()
      .mockRejectedValueOnce(new Error('offline'))
      .mockResolvedValue({ default: Loading });
    const onfail = vi.fn();
    render({ load, onfail });
    await vi.waitFor(() => expect(toasts.current?.message).toBe('Couldn’t open that. Try again.'));
    expect(toasts.current?.tone).toBe('problem');
    expect(toasts.current?.action?.label).toBe('Try again');
    expect(onfail).toHaveBeenCalledTimes(1);
    toasts.act();
    await expect.element(page.getByRole('status')).toHaveTextContent('Loading…');
    expect(load).toHaveBeenCalledTimes(2);
  });
});
