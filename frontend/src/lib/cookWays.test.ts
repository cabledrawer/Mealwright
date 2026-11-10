// Telling the meal which way was cooked (M2): Cook mode's pick, set again by Cooked it when it
// could not be saved the first time.

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { setMealWay } from './cookWays';
import { network } from './network.svelte';
import { fakeApi } from './testing/fakeApi';

beforeEach(() => network.reset());
afterEach(() => {
  vi.unstubAllGlobals();
  network.reset();
});

describe('setMealWay', () => {
  it('sets the meal to the way, and does nothing when it already is', async () => {
    const requests = fakeApi({
      'PUT /plan/items/77/method': [200, { change: null, meal_id: 1, item_id: 77 }]
    });
    expect(await setMealWay({ id: 77, method_id: 10 }, 11)).toBe(true);
    expect(requests.find((r) => r.method === 'PUT')?.body).toEqual({ method_id: 11 });
    expect(await setMealWay({ id: 77, method_id: 11 }, 11)).toBe(true);
    expect(requests.filter((r) => r.method === 'PUT')).toHaveLength(1);
  });

  it('says false when the server refuses, or when it is offline (nothing is asked)', async () => {
    fakeApi({ 'PUT /plan/items/77/method': [409, { detail: 'No', code: 'meal_done' }] });
    expect(await setMealWay({ id: 77, method_id: 10 }, 11)).toBe(false);
    const requests = fakeApi({});
    network.offline = true;
    expect(await setMealWay({ id: 77, method_id: 10 }, 11)).toBe(false);
    expect(requests).toHaveLength(0);
  });
});
