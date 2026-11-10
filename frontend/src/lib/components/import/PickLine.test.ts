import { flushSync, mount, unmount } from 'svelte';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { page, userEvent } from 'vitest/browser';
import PickLine from './PickLine.svelte';

// The pick-list for a line on Check (F189). Enter takes the first row only once the list answers
// what is typed now (W4d review L5): a slow answer for fewer letters could link the wrong thing.

const food = (id: number, name: string) => ({
  id,
  name,
  other_names: [],
  place: null,
  staple: false
});

describe('the pick-list', () => {
  let component: ReturnType<typeof mount> | null = null;
  afterEach(() => {
    if (component) unmount(component);
    component = null;
    document.body.innerHTML = '';
    vi.unstubAllGlobals();
  });

  it('does nothing on Enter while the answer for what is typed now has not come', async () => {
    // "dos" answers at once; "dosa" never does.
    vi.stubGlobal('fetch', (input: string) => {
      const url = new URL(String(input), 'http://x');
      const q = url.searchParams.get('q') ?? '';
      if (q !== 'dos') return new Promise<Response>(() => {});
      const body = url.pathname.endsWith('/foods')
        ? { foods: [food(3, 'Dosa mix')] }
        : { recipes: [] };
      return Promise.resolve(new Response(JSON.stringify(body), { status: 200 }));
    });
    const onpick = vi.fn();
    component = mount(PickLine, {
      target: document.body,
      props: { written: '', words: 'dos', onpick, oncancel: () => {} }
    });
    flushSync();
    await expect.element(page.getByText('Dosa mix')).toBeVisible();
    await userEvent.type(page.getByRole('searchbox', { name: 'Search' }), 'a');
    await userEvent.keyboard('{Enter}');
    expect(onpick).not.toHaveBeenCalled();
  });
});
