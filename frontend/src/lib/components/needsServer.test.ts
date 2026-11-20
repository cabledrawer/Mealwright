import { flushSync, mount, unmount } from 'svelte';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { page } from 'vitest/browser';
import { network } from '#lib/network.svelte.js';
import NeedsServer from './NeedsServer.svelte';
import YourKitchen from './YourKitchen.svelte';
import '#lib/styles/tokens.css';
import '#lib/styles/base.css';

// FE12: a screen that only the server can save says so offline and greys its write buttons.
describe('the shared offline note and the write buttons it sits beside', () => {
  let component: ReturnType<typeof mount> | null = null;
  afterEach(() => {
    if (component) unmount(component);
    component = null;
    document.body.innerHTML = '';
    network.reset();
    vi.unstubAllGlobals();
  });

  it('shows nothing while online and one status line offline', async () => {
    component = mount(NeedsServer, { target: document.body });
    flushSync();
    expect(page.getByRole('status').elements()).toEqual([]);
    network.offline = true;
    flushSync();
    await expect.element(page.getByRole('status')).toBeVisible();
  });

  it('"Your kitchen": Save is greyed out offline and the note shows', async () => {
    const save = vi.fn(async (k) => k);
    network.offline = true;
    component = mount(YourKitchen, {
      target: document.body,
      props: {
        open: true,
        kitchen: { hob_rings: 4, pressure_cookers: 1, oven: true, asked: true },
        onsaved: vi.fn(),
        onclose: vi.fn(),
        save
      }
    });
    flushSync();
    await expect.element(page.getByRole('button', { name: 'Save' })).toBeDisabled();
    await expect.element(page.getByRole('status')).toBeVisible();
    expect(save).not.toHaveBeenCalled();
  });
});
