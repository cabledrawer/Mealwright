import { flushSync, mount, unmount } from 'svelte';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { page } from 'vitest/browser';
import Toast from '#lib/components/Toast.svelte';
import { network } from '#lib/network.svelte.js';
import { session } from '#lib/session.svelte.js';
import { shoppingSync } from '#lib/shopping/sync.svelte.js';
import { fakeShopping, ME, sampleCopy } from '#lib/testing/fakeShopping.js';
import { samplePantry } from '#lib/testing/fakePantry.js';
import { dropPhone, freshPhone } from '#lib/testing/phone.js';
import { toasts } from '#lib/toast.svelte.js';
import { undoHistory } from '#lib/undo.svelte.js';
import Pantry from './+page.svelte';
import '#lib/styles/tokens.css';
import '#lib/styles/base.css';

// Tap a staple, and "+ List" on a running-low row, add to the main shopping list through
// Shopping's own add action and waiting list (spec, cabledrawer 18 Oct, 0.3).

describe('Pantry → the shopping list', () => {
  const mounted: ReturnType<typeof mount>[] = [];
  let server: ReturnType<typeof fakeShopping>;
  /** The connection to the server is failing (fetch rejects, as when there is no signal). */
  let down = false;
  /** While set, the shopping list's answer is held back (the list hasn't arrived yet). */
  let hold: Promise<void> | null = null;

  const adds = () => server.actions.filter((a) => a.kind === 'add');

  async function render(width: number, listArrives = true) {
    const sample = samplePantry();
    server = fakeShopping(sampleCopy(), {
      'GET /pantry': [200, sample.pantry],
      'GET /pantry/use-soon': [200, { lots: [] }],
      'GET /changes?limit=8&area=pantry': [200, { changes: [], next: null }]
    });
    const working = fetch;
    vi.stubGlobal('fetch', async (input: string, init?: RequestInit) => {
      if (down) throw new TypeError('Failed to fetch');
      if (hold && String(input).includes('/shopping/changes')) await hold;
      return working(input, init);
    });
    await page.viewport(width, 1000);
    for (const component of [Pantry, Toast]) {
      const target = document.body.appendChild(document.createElement('div'));
      mounted.push(mount(component, { target }));
    }
    flushSync();
    await expect.element(page.getByRole('heading', { name: 'Pantry', level: 1 })).toBeVisible();
    if (!listArrives) return;
    // The shopping list has arrived, so a tap knows what is on it.
    await vi.waitFor(() =>
      expect(server.requests.some((r) => r.path === '/shopping/changes')).toBe(true)
    );
  }

  beforeEach(() => {
    down = false;
    hold = null;
    freshPhone();
    session.me = { ...ME };
    undoHistory.clear();
    toasts.dismiss();
  });

  afterEach(async () => {
    await dropPhone();
    for (const component of mounted.splice(0)) unmount(component);
    document.body.innerHTML = '';
    vi.unstubAllGlobals();
    network.reset();
  });

  const chip = (label: string) => page.getByRole('button', { name: label, exact: true });

  it('a staple chip says what a tap does, and a tap adds it to the main list with Undo', async () => {
    await render(1300);
    await chip('Add Salt to the shopping list').click();
    await vi.waitFor(() =>
      expect(adds()).toMatchObject([{ kind: 'add', list_id: 'main', food_id: 60 }])
    );
    await vi.waitFor(() => expect(toasts.current?.message).toBe('Salt added to the shopping list'));
    expect(toasts.current?.action?.label).toBe('Undo');
    // The tick: the chip is now "on the shopping list".
    await expect.element(chip('Salt, on the shopping list')).toBeVisible();
    expect(chip('Salt, on the shopping list').element().querySelector('svg')).not.toBeNull();
    // Turmeric is untouched.
    await expect.element(chip('Add Turmeric to the shopping list')).toBeVisible();
  });

  it('tapping a ticked chip adds nothing more and says it is already there', async () => {
    await render(1300);
    await chip('Add Salt to the shopping list').click();
    await expect.element(chip('Salt, on the shopping list')).toBeVisible();
    toasts.dismiss();
    await chip('Salt, on the shopping list').click();
    expect(toasts.current?.message).toBe('Salt is already on the shopping list.');
    expect(toasts.current?.action).toBeUndefined();
    // And it doesn't remove it: still ticked, and nothing sent but the one add.
    await expect.element(chip('Salt, on the shopping list')).toBeVisible();
    await new Promise((resolve) => setTimeout(resolve, 100));
    expect(adds()).toHaveLength(1);
    expect(server.actions.filter((a) => a.kind === 'delete')).toHaveLength(0);
  });

  it('two quick taps are one add', async () => {
    await render(1300);
    const button = chip('Add Salt to the shopping list').element() as HTMLElement;
    button.click();
    button.click();
    await new Promise((resolve) => setTimeout(resolve, 200));
    expect(adds()).toHaveLength(1);
  });

  it('two quick taps before the shopping list has arrived add it once', async () => {
    let arrive!: () => void;
    hold = new Promise<void>((resolve) => (arrive = resolve));
    await render(1300, false);
    await expect.element(chip('Add Salt to the shopping list')).toBeVisible();
    const button = chip('Add Salt to the shopping list').element() as HTMLElement;
    button.click();
    expect(toasts.current).toBeNull();
    button.click();
    // The second tap is the same tap.
    expect(toasts.current?.message).toBe('Salt is already on the shopping list.');
    arrive();
    await vi.waitFor(() => expect(adds()).toHaveLength(1));
    await expect.element(chip('Salt, on the shopping list')).toBeVisible();
    await new Promise((resolve) => setTimeout(resolve, 200));
    expect(adds()).toHaveLength(1);
  });

  it('Undo takes the staple off the list again, and the tick goes', async () => {
    await render(1300);
    await chip('Add Salt to the shopping list').click();
    await expect.element(chip('Salt, on the shopping list')).toBeVisible();
    await page.getByRole('button', { name: 'Undo' }).click();
    await vi.waitFor(() => expect(server.actions.some((a) => a.kind === 'undo')).toBe(true));
    await expect.element(chip('Add Salt to the shopping list')).toBeVisible();
  });

  it('an item already on the list shows its tick from the start', async () => {
    const sample = samplePantry();
    const copy = sampleCopy();
    copy.foods.push({ ...copy.foods[0]!, id: 61, name: 'Turmeric', staple: true });
    copy.items.push({ ...copy.items[0]!, id: 'i-turmeric', food_id: 61, ticks: [] });
    server = fakeShopping(copy, {
      'GET /pantry': [200, sample.pantry],
      'GET /pantry/use-soon': [200, { lots: [] }],
      'GET /changes?limit=8&area=pantry': [200, { changes: [], next: null }]
    });
    mounted.push(mount(Pantry, { target: document.body }));
    await expect.element(chip('Turmeric, on the shopping list')).toBeVisible();
    await expect.element(chip('Add Salt to the shopping list')).toBeVisible();
  });

  it('"+ List" on a running-low row works the same way', async () => {
    await render(1300);
    await page.getByRole('button', { name: 'Add Basmati rice to the shopping list' }).click();
    await vi.waitFor(() =>
      expect(adds()).toMatchObject([{ kind: 'add', list_id: 'main', food_id: 41 }])
    );
    await vi.waitFor(() =>
      expect(toasts.current?.message).toBe('Basmati rice added to the shopping list')
    );
    expect(toasts.current?.action?.label).toBe('Undo');
    const ticked = page.getByRole('button', { name: 'Basmati rice, on the shopping list' });
    await expect.element(ticked).toBeVisible();
    toasts.dismiss();
    await ticked.click();
    expect(toasts.current?.message).toBe('Basmati rice is already on the shopping list.');
    await new Promise((resolve) => setTimeout(resolve, 100));
    expect(adds()).toHaveLength(1);
  });

  it('"+ List" is only on running-low rows (phone too)', async () => {
    await render(390);
    await expect
      .element(page.getByRole('button', { name: 'Add Basmati rice to the shopping list' }))
      .toBeVisible();
    expect(
      page.getByRole('button', { name: /^Add Toor dal to the shopping list/ }).elements()
    ).toHaveLength(0);
  });

  it('"Edit staples" opens Ingredients with the Staples filter', async () => {
    await render(1300);
    await expect
      .element(page.getByRole('link', { name: 'Edit staples' }))
      .toHaveAttribute('href', '/recipes/ingredients?filter=staples');
  });

  // cabledrawer 18 Oct: while the connection is failing, a tap is kept in the waiting list and
  // sent once the server is back. Never lost, never doubled. (Pantry itself still shows its
  // offline note once the bar says Offline: the tap is made before that.)
  it('taps made while the connection is failing wait, then each is sent exactly once', async () => {
    await render(1300);
    down = true;
    await chip('Add Salt to the shopping list').click();
    await page.getByRole('button', { name: 'Add Basmati rice to the shopping list' }).click();
    // Both show their tick, and both are waiting on this phone.
    await expect.element(chip('Salt, on the shopping list')).toBeVisible();
    await expect
      .element(page.getByRole('button', { name: 'Basmati rice, on the shopping list' }))
      .toBeVisible();
    await vi.waitFor(() => expect(shoppingSync.waiting).toBe(2));
    expect(adds()).toHaveLength(0);
    expect(toasts.current?.message).toBe('Basmati rice added to the shopping list');
    // Tapping them again while they wait is still "already on the list".
    await chip('Salt, on the shopping list').click();
    expect(toasts.current?.message).toBe('Salt is already on the shopping list.');
    // The server is back: each is sent once.
    down = false;
    await shoppingSync.send();
    await vi.waitFor(() => expect(shoppingSync.waiting).toBe(0));
    expect(
      adds()
        .map((a) => a.food_id)
        .sort()
    ).toEqual([41, 60]);
    // And nothing is sent twice by what follows.
    await shoppingSync.send();
    await new Promise((resolve) => setTimeout(resolve, 100));
    expect(adds()).toHaveLength(2);
  });
});
