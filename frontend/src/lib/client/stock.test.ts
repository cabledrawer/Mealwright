import { afterEach, describe, expect, it, vi } from 'vitest';
import { fakeApi } from '#lib/testing/fakeApi.js';
import { addStock, getPantry, moveLot, setLeft, setUseBy, toFreezer, usedLot } from './stock';

afterEach(() => vi.unstubAllGlobals());

const ok = { change: null, groups: [], short_by: null };

describe('stock', () => {
  it('reads the pantry, with a filter when one is chosen', async () => {
    const requests = fakeApi({
      'GET /pantry': [200, {}],
      'GET /pantry?filter=use_soon': [200, {}],
      'GET /pantry?q=thuvaram': [200, {}]
    });
    await getPantry();
    await getPantry('use_soon');
    await getPantry('all', ' thuvaram ');
    expect(requests.map((r) => r.url)).toEqual([
      '/pantry',
      '/pantry?filter=use_soon',
      '/pantry?q=thuvaram'
    ]);
  });

  it('adds stock with its change ID, and ask-once answers inside the amount', async () => {
    const requests = fakeApi({ 'POST /stock': [201, ok] });
    const answer = { kind: 'size' as const, food_id: 9, name: 'loaf', amount: 20 };
    await addStock({ food_id: 9, amount: { amount: 1, unit: 'loaf' }, place_id: 3 }, 'k1', [
      answer
    ]);
    expect(requests[0]!.body).toEqual({
      food_id: 9,
      amount: { amount: 1, unit: 'loaf', answers: [answer] },
      place_id: 3
    });
    expect(requests[0]!.headers['idempotency-key']).toBe('k1');
  });

  it('sends each packet change to its own address', async () => {
    const requests = fakeApi({
      'POST /stock/5/left': [200, ok],
      'POST /stock/5/used': [200, ok],
      'POST /stock/5/to-freezer': [200, ok],
      'POST /stock/5/move': [200, ok],
      'PATCH /stock/5': [200, ok]
    });
    await setLeft(5, { fraction: 0.5 }, 'a');
    await usedLot(5, 'b');
    await toFreezer(5, 'c');
    await moveLot(5, 2, 'd');
    await setUseBy(5, '2026-10-22', 'e');
    expect(requests.map((r) => [r.method, r.path, r.body])).toEqual([
      ['POST', '/stock/5/left', { fraction: 0.5 }],
      ['POST', '/stock/5/used', {}],
      ['POST', '/stock/5/to-freezer', {}],
      ['POST', '/stock/5/move', { place_id: 2 }],
      ['PATCH', '/stock/5', { use_by: '2026-10-22' }]
    ]);
  });
});
