// S5 review r3 M2, swept to every way the app puts a tub from Tubs left into a meal (the Plan's
// sheet, its Add panel, a drag, and "Eat it on…" after Cooked it): the server is asked to refuse
// a tub that another phone has put in a meal meanwhile (409 tub_taken), not to move it out.

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { eatLeftover, type Placed } from './eatLeftover';
import { kitchen } from './freshness.svelte';
import { network } from './network.svelte';
import { PlanModel } from './plan.svelte';
import { fakeApi } from './testing/fakeApi';
import { toasts } from './toast.svelte';

const TAKEN = [
  409,
  { detail: 'That tub is already in a meal. Look again.', code: 'tub_taken' }
] as const;

beforeEach(() => network.reset());
afterEach(() => {
  toasts.dismiss();
  vi.unstubAllGlobals();
  network.reset();
});

describe('the Plan puts a tub from Tubs left', () => {
  it('asks the server to refuse a tub already in a meal', async () => {
    const requests = fakeApi({
      'POST /plan/tubs/51/place': [200, { plan: null, change: null }]
    });
    const model = new PlanModel();
    await model.placeTub(51, 'Lemon rice tub', '2026-10-18', 2);
    expect(
      requests.find((r) => r.method === 'POST' && r.path === '/plan/tubs/51/place')?.body
    ).toEqual({ date: '2026-10-18', slot_id: 2, from_tubs_left: true });
  });

  it('when refused, says so and fetches the plan again', async () => {
    fakeApi({ 'POST /plan/tubs/51/place': [...TAKEN] });
    const before = kitchen.version;
    const model = new PlanModel();
    await model.placeTub(51, 'Lemon rice tub', '2026-10-18', 2);
    expect(kitchen.version).toBe(before + 1);
    expect(toasts.current?.tone).toBe('problem');
    expect(toasts.current?.message).toContain('That tub is already in a meal. Look again.');
  });
});

describe('"Eat it on…" after Cooked it', () => {
  it('asks the server to refuse a tub already in a meal, and says the cooking is saved', async () => {
    const requests = fakeApi({
      'GET /plan/tubs-left': [
        200,
        {
          tubs: [
            { id: 41, recipe_name: 'Banana bread', cooked_on: '2026-11-02', use_by: '2026-11-05' }
          ],
          more: false
        }
      ],
      'POST /plan/tubs/41/place': [...TAKEN]
    });
    const placed: Placed = { undo: null };
    await eatLeftover(placed, 'Banana bread', '2026-11-02', 1, { day: '2026-11-07', slotId: 3 });
    expect(
      requests.find((r) => r.method === 'POST' && r.path === '/plan/tubs/41/place')?.body
    ).toEqual({ date: '2026-11-07', slot_id: 3, from_tubs_left: true });
    expect(placed.undo).toBeNull();
    expect(toasts.current?.message).toBe(
      'Cooked it is saved, but the tub isn’t planned. That tub is already in a meal. Look again. It stays in Tubs left.'
    );
  });
});
