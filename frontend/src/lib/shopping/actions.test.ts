import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { ApiError } from '#lib/api.js';
import { fakeApi } from '#lib/testing/fakeApi.js';
import { sampleCopy } from '#lib/testing/fakeShopping.js';
import { dropPhone, freshPhone } from '#lib/testing/phone.js';
import { session } from '#lib/session.svelte.js';
import { deviceId, makeAction, setSendContext } from './actions';
import { sendAction, shoppingSync } from './sync.svelte';

beforeEach(() => {
  freshPhone();
  session.me = { id: 1, name: 'Tess', username: 'k', role: 'admin', theme: 'auto' };
  setSendContext({ cursor: () => 77 });
});

afterEach(async () => {
  await dropPhone();
  vi.unstubAllGlobals();
});

const answering = (extra: Record<string, unknown> = {}) =>
  fakeApi({
    'POST /shopping/actions': (request) => {
      const id = (request.body as { actions: { id: string }[] }).actions[0]!.id;
      return [
        200,
        {
          results: [{ id, status: 'applied', change: null, ...extra }],
          changes: { ...sampleCopy(), cursor: 78, reset: false }
        }
      ];
    }
  });

describe('makeAction', () => {
  it('fills in the envelope: ID, time, and the counter number the device had seen', () => {
    const action = makeAction({ kind: 'delete', item_id: 'x' });
    expect(action.id).toMatch(/^[0-9a-f-]{36}$/);
    expect(action.seen).toBe(77);
    expect(new Date(action.made_at).getTime()).not.toBeNaN();
  });
});

describe('deviceId', () => {
  it('is a lower-case UUID, kept on this device', () => {
    expect(deviceId()).toMatch(/^[0-9a-f]{8}(-[0-9a-f]{4}){3}-[0-9a-f]{12}$/);
    expect(deviceId()).toBe(deviceId());
  });
});

describe('sendAction (through the queue)', () => {
  it('sends every kind as a batch of one in the envelope of sync-protocol 4.1', async () => {
    const requests = answering();
    const kinds = [
      makeAction({ kind: 'create_list', list_id: 'N', name: 'Party' }),
      makeAction({ kind: 'rename_list', list_id: 'L', name: 'Weekly' }),
      makeAction({ kind: 'remove_list', list_id: 'L' }),
      makeAction({ kind: 'add', list_id: 'L', item_id: 'a', food_id: 5, amount: 500, size_id: 12 }),
      makeAction({ kind: 'set_amount', item_id: 'a', amount: 2000 }),
      makeAction({ kind: 'delete', item_id: 'a' }),
      makeAction({ kind: 'tick', item_id: 'a' }),
      makeAction({ kind: 'untick', item_id: 'a', tick_ids: ['t'] }),
      makeAction({ kind: 'put_away', item_id: 'a', place_id: 2, tick_ids: ['t'] }),
      makeAction({ kind: 'different_pack', item_id: 'a', tick_id: 't', count: 1, pack: 400 }),
      makeAction({ kind: 'clear_ticked', list_id: 'L', item_ids: ['a'] }),
      makeAction({ kind: 'answer_double_tick', question_id: 5, answer: 'one' }),
      makeAction({ kind: 'dismiss_note', note_id: 3 }),
      makeAction({ kind: 'undo', undoes: 'x' })
    ];
    for (const action of kinds) await sendAction(action);
    expect(requests.every((r) => r.path === '/shopping/actions')).toBe(true);
    const sent = requests.map((r) => r.body as { actions: Record<string, unknown>[] });
    expect(sent.map((b) => b.actions[0])).toEqual(kinds);
    // `since` is the cursor of the copy kept on the phone (none yet here).
    expect(sent[0]).toMatchObject({ protocol: 1, login_id: 1, since: 0 });
    expect(sent[1]).toMatchObject({ since: shoppingSync.copy!.cursor });
    expect((sent[0] as unknown as { device_id: string }).device_id).toMatch(/^[0-9a-f-]{36}$/);
    expect(sent[3]!.actions[0]).toMatchObject({ amount: 500, size_id: 12 }); // base amounts
  });

  it('add with new_food carries the packet sizes in base amounts', async () => {
    const requests = answering({ food_id: 90 });
    const result = await sendAction(
      makeAction({
        kind: 'add',
        list_id: 'L',
        item_id: 'a',
        new_food: {
          name: 'Tahini',
          counted_as: 'weight',
          staple: false,
          sizes: [{ name: 'jar', amount: 250 }]
        }
      })
    );
    expect(result.food_id).toBe(90);
    expect(requests).toHaveLength(1); // one request: no separate ingredient or size calls
    expect(
      (requests[0]!.body as { actions: { new_food: unknown }[] }).actions[0]!.new_food
    ).toEqual({
      name: 'Tahini',
      counted_as: 'weight',
      staple: false,
      sizes: [{ name: 'jar', amount: 250 }]
    });
  });

  it('hands back the changes that came with the answer', async () => {
    answering();
    const result = await sendAction(makeAction({ kind: 'tick', item_id: 'a' }));
    expect(result.changes?.cursor).toBe(78);
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
