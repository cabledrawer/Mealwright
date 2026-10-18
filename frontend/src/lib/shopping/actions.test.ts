import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { ApiError } from '$lib/api';
import { changeOf, fakeApi } from '$lib/testing/fakeApi';
import { food } from '$lib/testing/fakeShopping';
import { session } from '$lib/session.svelte';
import { makeAction, sendAction, setSendContext, wireAmount } from './actions';

const dal = food(5, 'Toor dal', 'dry_goods', {
  sizes: [{ id: 12, name: 'packet', plural: 'packets', amount: 500, usual: true }]
});
const volume = food(6, 'Milk', 'dairy', { counted_as: 'volume' });

beforeEach(() => {
  session.me = { id: 1, name: 'Tess', username: 'k', role: 'admin', theme: 'auto' };
  setSendContext({
    food: (id) => [dal, volume].find((f) => f.id === id),
    foodOfItem: (id) => (id === 'milk-line' ? 6 : 5),
    cursor: () => 77
  });
});

afterEach(() => vi.unstubAllGlobals());

describe('makeAction', () => {
  it('fills in the envelope: ID, time, and the counter number the device had seen', () => {
    const action = makeAction({ kind: 'delete', item_id: 'x' });
    expect(action.id).toMatch(/^[0-9a-f-]{36}$/);
    expect(action.seen).toBe(77);
    expect(new Date(action.made_at).getTime()).not.toBeNaN();
  });
});

describe('wireAmount (base amounts to the one-at-a-time requests)', () => {
  it('uses the base unit, or the size when there is one', () => {
    expect(wireAmount(5, 250, null)).toEqual({ amount: 250, unit: 'g' });
    expect(wireAmount(6, 2000, null)).toEqual({ amount: 2000, unit: 'ml' });
    expect(wireAmount(5, 750, 12)).toEqual({ amount: 1.5, size_id: 12 });
  });
});

describe('sendAction', () => {
  it('add → POST the item with the action ID as the key and the phone-made item ID', async () => {
    const requests = fakeApi({
      'POST /shopping/lists/L/items': [
        201,
        { item: { id: 'item-1' }, merged: true, change: changeOf(900, 'Added') }
      ]
    });
    const action = makeAction({
      kind: 'add',
      list_id: 'L',
      item_id: 'item-1',
      food_id: 5,
      amount: 500,
      size_id: 12
    });
    const result = await sendAction(action);
    expect(result).toMatchObject({ status: 'merged', item_id: 'item-1' });
    expect(requests[0]!.body).toEqual({
      id: 'item-1',
      food_id: 5,
      amount: { amount: 1, size_id: 12 }
    });
    expect(requests[0]!.headers['idempotency-key']).toBe(action.id);
  });

  it('add with no shop given leaves shop_id out (the usual shop); null means Any shop', async () => {
    const requests = fakeApi({
      'POST /shopping/lists/L/items': [201, { item: { id: 'a' }, merged: false, change: null }]
    });
    await sendAction(makeAction({ kind: 'add', list_id: 'L', item_id: 'a', food_id: 5 }));
    await sendAction(
      makeAction({ kind: 'add', list_id: 'L', item_id: 'a', food_id: 5, shop_id: null })
    );
    expect('shop_id' in (requests[0]!.body as object)).toBe(false);
    expect(requests[1]!.body).toMatchObject({ shop_id: null });
  });

  it('set_amount, delete, lists and clear_ticked use the one-at-a-time requests', async () => {
    const requests = fakeApi({
      'PATCH /shopping/items/milk-line': [
        200,
        { item: {}, merged: false, change: changeOf(1, 'x') }
      ],
      'DELETE /shopping/items/a': [200, { item: null, merged: false, change: changeOf(2, 'x') }],
      'POST /shopping/lists': [201, { change: changeOf(3, 'x') }],
      'PATCH /shopping/lists/L': [200, { change: changeOf(4, 'x') }],
      'DELETE /shopping/lists/L': [200, { change: changeOf(5, 'x') }],
      'POST /shopping/lists/L/clear-ticked': [200, { cleared: ['a'], change: changeOf(6, 'x') }]
    });
    await sendAction(makeAction({ kind: 'set_amount', item_id: 'milk-line', amount: 2000 }));
    await sendAction(makeAction({ kind: 'delete', item_id: 'a' }));
    await sendAction(makeAction({ kind: 'create_list', list_id: 'N', name: 'Party' }));
    await sendAction(makeAction({ kind: 'rename_list', list_id: 'L', name: 'Weekly' }));
    await sendAction(makeAction({ kind: 'remove_list', list_id: 'L' }));
    await sendAction(makeAction({ kind: 'clear_ticked', list_id: 'L', item_ids: ['a'] }));
    expect(requests.map((r) => `${r.method} ${r.path}`)).toEqual([
      'PATCH /shopping/items/milk-line',
      'DELETE /shopping/items/a',
      'POST /shopping/lists',
      'PATCH /shopping/lists/L',
      'DELETE /shopping/lists/L',
      'POST /shopping/lists/L/clear-ticked'
    ]);
    expect(requests[0]!.body).toEqual({ amount: { amount: 2000, unit: 'ml' } });
    expect(requests[2]!.body).toEqual({ id: 'N', name: 'Party' });
  });

  it('Undo of an action PR 2 recorded uses that change’s own Undo', async () => {
    const requests = fakeApi({
      'DELETE /shopping/items/a': [200, { item: null, merged: false, change: changeOf(77, 'x') }],
      'POST /changes/77/undo': [200, { result: 'done', message: '', change: changeOf(78, 'u') }]
    });
    const del = makeAction({ kind: 'delete', item_id: 'a' });
    await sendAction(del);
    const result = await sendAction(makeAction({ kind: 'undo', undoes: del.id }));
    expect(result.status).toBe('applied');
    expect(requests.at(-1)!.path).toBe('/changes/77/undo');
  });

  it('tick, untick, put_away, different_pack and the rest go to POST /shopping/actions as an envelope', async () => {
    const requests = fakeApi({
      'POST /shopping/actions': (request) => {
        const id = (request.body as { actions: { id: string }[] }).actions[0]!.id;
        return [200, { results: [{ id, status: 'applied', change: null }] }];
      }
    });
    await sendAction(makeAction({ kind: 'tick', item_id: 'a' }));
    await sendAction(makeAction({ kind: 'untick', item_id: 'a', tick_ids: ['t'] }));
    await sendAction(makeAction({ kind: 'put_away', item_id: 'a', place_id: 2, tick_ids: ['t'] }));
    await sendAction(
      makeAction({ kind: 'different_pack', item_id: 'a', tick_id: 't', count: 1, pack: 400 })
    );
    await sendAction(makeAction({ kind: 'answer_double_tick', question_id: 5, answer: 'one' }));
    await sendAction(makeAction({ kind: 'dismiss_note', note_id: 3 }));
    await sendAction(makeAction({ kind: 'undo', undoes: 'unknown-id' }));
    const kinds = requests.map((r) => (r.body as { actions: { kind: string }[] }).actions[0]!.kind);
    expect(kinds).toEqual([
      'tick',
      'untick',
      'put_away',
      'different_pack',
      'answer_double_tick',
      'dismiss_note',
      'undo'
    ]);
    expect(requests[0]!.body).toMatchObject({ protocol: 1, login_id: 1, since: 77 });
    expect((requests[0]!.body as { device_id: string }).device_id).toMatch(/^[0-9a-f-]{36}$/);
  });

  it('a refused action is an error with the server’s sentence', async () => {
    fakeApi({
      'POST /shopping/actions': (request) => [
        200,
        {
          results: [
            {
              id: (request.body as { actions: { id: string }[] }).actions[0]!.id,
              status: 'refused',
              reason: 'bad_action',
              message: 'That change couldn’t be saved.'
            }
          ]
        }
      ]
    });
    await expect(sendAction(makeAction({ kind: 'tick', item_id: 'a' }))).rejects.toBeInstanceOf(
      ApiError
    );
  });
});
