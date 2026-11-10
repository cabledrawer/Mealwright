import { afterEach, describe, expect, it, vi } from 'vitest';
import type { PackChoice } from '#lib/client/foods.js';
import { fakeApi } from '#lib/testing/fakeApi.js';
import { useSize } from './useSize';
import type { ListItem } from './types';

afterEach(() => vi.unstubAllGlobals());

const choice = (over: Partial<PackChoice>): PackChoice => ({
  size_id: 2,
  name: 'small tin',
  plural: 'small tins',
  amount: 200,
  packs: 3,
  buy: '3 small tins · 200 ml',
  over: 'nothing left over',
  usual: false,
  chosen: false,
  least: true,
  text: 'Or 3 small tins · 200 ml: nothing left over',
  ...over
});

const item = { id: 'i1', food_id: 7 } as ListItem;

function model() {
  const calls: unknown[][] = [];
  return {
    calls,
    setAmount: (...args: unknown[]) => {
      calls.push(args);
      return Promise.resolve();
    }
  };
}

describe('Use this', () => {
  it('changes the line to that many of an own size', async () => {
    const requests = fakeApi({});
    const m = model();
    await useSize(m as never, item, 7, choice({}), false);
    expect(m.calls).toEqual([[item, 600, 2]]);
    expect(requests).toEqual([]);
  });

  it('makes a common size first, and makes it the usual one when asked', async () => {
    const requests = fakeApi({
      'POST /foods/7/sizes': [
        201,
        { change: null, food: { sizes: [{ id: 9, name: 'carton', amount: 1000 }] } }
      ]
    });
    const m = model();
    await useSize(
      m as never,
      item,
      7,
      choice({ size_id: null, name: 'carton', amount: 1000, packs: 1 }),
      true
    );
    expect(requests[0]!.body).toEqual({ name: 'carton', amount: 1000, usual: true });
    expect(m.calls).toEqual([[item, 1000, 9]]);
  });

  it('makes an own size the usual one with the switch, without making a new size', async () => {
    const requests = fakeApi({ 'PATCH /foods/7/sizes/2': [200, { change: null, food: {} }] });
    const m = model();
    await useSize(m as never, item, 7, choice({}), true);
    expect(requests[0]!.body).toEqual({ usual: true });
    expect(m.calls).toHaveLength(1);
  });

  it('leaves the line alone when the size is the one it is already in', async () => {
    fakeApi({});
    const m = model();
    await useSize(m as never, item, 7, choice({ chosen: true }), false);
    expect(m.calls).toEqual([]);
  });
});
