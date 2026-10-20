import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { network } from './network.svelte';
import { PantryList } from './pantryList.svelte';
import { session } from './session.svelte';
import { fakeShopping, ME, sampleCopy } from './testing/fakeShopping';
import { dropPhone, freshPhone } from './testing/phone';
import { toasts } from './toast.svelte';
import { undoHistory } from './undo.svelte';

// Several ingredients added at once ("1 missing · Add to the list" on the recipe page with more
// than one missing): each goes through the same add action as one tap, so what is queued is
// exactly what adding them by hand sends. Only the toast and the Undo are shared.

// On the sample copy's main list these are not unticked lines: Tahini is only on the party
// list, Coriander and Paneer are ticked.
const TAHINI = { id: 7, name: 'Tahini' };
const CORIANDER = { id: 2, name: 'Coriander' };
const PANEER = { id: 4, name: 'Paneer' };

describe('adding several ingredients to the shopping list', () => {
  let server: ReturnType<typeof fakeShopping>;
  let list: PantryList;

  const adds = () => server.actions.filter((a) => a.kind === 'add');
  /** An action without the ids made fresh each time. */
  const shape = (a: Record<string, unknown>) => ({
    kind: a.kind,
    list_id: a.list_id,
    food_id: a.food_id
  });

  async function open() {
    server = fakeShopping(sampleCopy());
    list = new PantryList();
    await list.refresh();
  }

  beforeEach(() => {
    freshPhone();
    session.me = { ...ME };
    undoHistory.clear();
    toasts.dismiss();
  });

  afterEach(async () => {
    await dropPhone();
    vi.unstubAllGlobals();
    network.reset();
  });

  it('queues exactly what one tap each queues', async () => {
    await open();
    await list.tap(TAHINI);
    await list.tap(CORIANDER);
    await list.tap(PANEER);
    const byHand = adds().map(shape);
    await dropPhone();
    freshPhone();
    await open();
    await list.tapMany([TAHINI, CORIANDER, PANEER]);
    await vi.waitFor(() => expect(adds()).toHaveLength(3));
    expect(adds().map(shape)).toEqual(byHand);
    // Each add has its own change ID and its own line, as when added one by one.
    expect(new Set(adds().map((a) => a.id)).size).toBe(3);
    expect(new Set(adds().map((a) => a.item_id)).size).toBe(3);
  });

  it('shows one toast for all of them, with one Undo', async () => {
    await open();
    await list.tapMany([TAHINI, CORIANDER, PANEER]);
    expect(toasts.current?.message).toBe('3 ingredients added to the shopping list');
    expect(toasts.current?.action?.label).toBe('Undo');
    await vi.waitFor(() => expect(adds()).toHaveLength(3));
    for (const food of [TAHINI, CORIANDER, PANEER]) expect(list.onList(food.id)).toBe(true);
  });

  it('Undo takes them all back, newest first', async () => {
    await open();
    await list.tapMany([TAHINI, CORIANDER, PANEER]);
    await vi.waitFor(() => expect(adds()).toHaveLength(3));
    toasts.act();
    await vi.waitFor(() => expect(server.actions.filter((a) => a.kind === 'undo')).toHaveLength(3));
    const undone = server.actions.filter((a) => a.kind === 'undo').map((a) => a.undoes);
    expect(undone).toEqual(
      adds()
        .map((a) => a.id)
        .reverse()
    );
    await vi.waitFor(() => {
      for (const food of [TAHINI, CORIANDER, PANEER]) expect(list.onList(food.id)).toBe(false);
    });
    expect(toasts.current?.message).toBe('Undone: 3 ingredients added to the shopping list');
  });

  it('Ctrl+Z (undo last) takes them all back too', async () => {
    await open();
    await list.tapMany([TAHINI, CORIANDER]);
    await vi.waitFor(() => expect(adds()).toHaveLength(2));
    await undoHistory.undoLast();
    await vi.waitFor(() => expect(server.actions.filter((a) => a.kind === 'undo')).toHaveLength(2));
  });

  it('leaves out what is already on the list, and one left is a plain single add', async () => {
    await open();
    await list.tap(TAHINI);
    toasts.dismiss();
    await list.tapMany([TAHINI, CORIANDER]);
    expect(toasts.current?.message).toBe('Coriander added to the shopping list');
    await vi.waitFor(() => expect(adds()).toHaveLength(2));
    toasts.dismiss();
    await list.tapMany([TAHINI, CORIANDER]);
    expect(toasts.current).toBeNull(); // everything was there already
    expect(adds()).toHaveLength(2);
  });

  it('keeps them while the connection is failing, and sends each once when it is back', async () => {
    await open();
    const working = fetch;
    let down = true;
    vi.stubGlobal('fetch', async (input: string, init?: RequestInit) => {
      if (down) throw new TypeError('Failed to fetch');
      return working(input, init);
    });
    await list.tapMany([TAHINI, CORIANDER, PANEER]);
    // The toast and the lines are there at once, with nothing sent yet.
    expect(toasts.current?.message).toBe('3 ingredients added to the shopping list');
    expect(list.onList(TAHINI.id)).toBe(true);
    expect(adds()).toHaveLength(0);
    down = false;
    network.reset();
    const { shoppingSync } = await import('./shopping/sync.svelte');
    await shoppingSync.send();
    await vi.waitFor(() => expect(adds()).toHaveLength(3));
    await new Promise((resolve) => setTimeout(resolve, 100));
    expect(adds()).toHaveLength(3);
  });
});
