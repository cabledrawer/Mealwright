// The paths that reach the plan questions (add a recipe, change its way or its start, move,
// Done already, Today's Move it, the Batch cook way question) fetch code the first time they are
// used. When that fetch fails (cabledrawer 15 Nov): the toast says "Couldn’t open that. Try
// again.", the action ends as if cancelled with nothing changed, and the next try fetches again.

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import type { PlanItem } from './client/plan';
import type { TodayData } from './client/today';
import { loaders } from './lazyModules';
import { methodAsk } from './methodAsk.svelte';
import { network } from './network.svelte';
import { optionalAsk } from './optionalAsk.svelte';
import { PlanModel } from './plan.svelte';
import { startAsk } from './startAsk.svelte';
import { fakeApi } from './testing/fakeApi';
import { toasts } from './toast.svelte';
import { TodayModel } from './today.svelte';

const WORDS = 'Couldn’t open that. Try again.';
const original = { ...loaders };

/** Make the next fetch of `name` fail once; later ones work. Returns the spy. */
function failOnce<K extends keyof typeof loaders>(name: K) {
  const spy = vi
    .fn<() => Promise<unknown>>()
    .mockRejectedValueOnce(new Error('offline'))
    .mockImplementation(original[name]);
  (loaders as Record<string, unknown>)[name] = spy;
  return spy;
}

const FERMENT = { kind: 'ferment', min_minutes: 480, max_minutes: 720, overnight: false };
const OPTIONS = {
  wait: FERMENT,
  eats_at: '08:00',
  options: [{ day: '2026-11-13', time: '21:00', ready_by: '08:00', ready_by_day: '2026-11-14' }]
};
const WRITE = [200, { change: null, meal_id: 1, item_id: 77 }] as [number, unknown];
const METHODS = [
  { id: 10, name: 'Stovetop', time_minutes: 45, used_last: false },
  { id: 11, name: 'Instant Pot', time_minutes: 30, used_last: true }
];
const CURRY = { id: 5, name: 'Curry', serves: 4, lines: [], steps: [], methods: METHODS };
const AHEAD = {
  step_id: 3,
  step_text: 'Soak.',
  wait: FERMENT,
  active_minutes: 30,
  eats_at: '08:00',
  start_day: '2026-11-13',
  start_time: '20:00',
  started_day: null,
  started_time: null,
  waited_minutes: null
};
const item = {
  id: 77,
  kind: 'recipe',
  recipe: { id: 5, name: 'Masala dosa', removed: false },
  method_id: 11,
  ahead: AHEAD
} as unknown as PlanItem;

function planModel() {
  const model = new PlanModel();
  model.plan = {
    start: '2026-11-14',
    end: '2026-11-14',
    meals: [
      {
        id: 1,
        date: '2026-11-14',
        slot_id: 1,
        status: 'planned',
        items: [item],
        kcal: null,
        eater_member_ids: []
      }
    ],
    batch_cooks: [],
    tubs: []
  };
  model.slots = [{ id: 1, name: 'Breakfast', position: 1, enabled: true }];
  return model;
}

beforeEach(() => {
  network.reset();
  toasts.dismiss();
});
afterEach(() => {
  Object.assign(loaders, original);
  startAsk.dismiss();
  methodAsk.dismiss();
  optionalAsk.dismiss();
  toasts.dismiss();
  vi.unstubAllGlobals();
  network.reset();
});

describe('adding a recipe', () => {
  it('cancels, plans nothing and toasts when the way-of-cooking question’s code fails; the next try asks', async () => {
    const requests = fakeApi({ 'GET /recipes/5': [200, CURRY], 'POST /plan/items': WRITE });
    const spy = failOnce('methodAsk');
    const model = planModel();
    const recipe = { id: 5, name: 'Curry', method_count: 2, optional_count: 0 };
    const outcome = await model.add({ recipe }, '2026-11-14', 1);
    expect(outcome).toEqual({ ok: false, error: null, cancelled: true });
    expect(toasts.current?.message).toBe(WORDS);
    expect(requests.filter((r) => r.method === 'POST')).toHaveLength(0);

    const again = model.add({ recipe }, '2026-11-14', 1);
    await vi.waitFor(() => expect(methodAsk.current).not.toBeNull());
    expect(spy).toHaveBeenCalledTimes(2);
    methodAsk.answer(10);
    expect((await again).ok).toBe(true);
    expect(requests.find((r) => r.method === 'POST')?.body).toMatchObject({ method_id: 10 });
  });

  it('cancels, plans nothing and toasts when the start question’s code fails; the next try asks', async () => {
    const requests = fakeApi({
      'GET /plan/start-options': [200, OPTIONS],
      'POST /plan/items': WRITE
    });
    const spy = failOnce('startAsk');
    const model = planModel();
    const recipe = { id: 5, name: 'Masala dosa', method_count: 1, optional_count: 0 };
    const outcome = await model.add({ recipe }, '2026-11-14', 1);
    expect(outcome).toEqual({ ok: false, error: null, cancelled: true });
    expect(toasts.current?.message).toBe(WORDS);
    expect(requests.filter((r) => r.method === 'POST')).toHaveLength(0);

    const again = model.add({ recipe }, '2026-11-14', 1);
    await vi.waitFor(() => expect(startAsk.current).not.toBeNull());
    expect(spy).toHaveBeenCalledTimes(2);
    startAsk.answer({ day: '2026-11-13', time: '21:00' });
    expect((await again).ok).toBe(true);
  });
});

describe('a meal on the plan', () => {
  it('changing its way changes nothing and toasts when the code fails; the next try asks', async () => {
    const requests = fakeApi({
      'GET /recipes/5': [200, CURRY],
      'PATCH /plan/items/77': WRITE
    });
    const spy = failOnce('methodAsk');
    const model = planModel();
    await model.changeMethod(item, '2026-11-14');
    expect(toasts.current?.message).toBe(WORDS);
    expect(requests).toHaveLength(0);

    const again = model.changeMethod(item, '2026-11-14');
    await vi.waitFor(() => expect(methodAsk.current).not.toBeNull());
    expect(spy).toHaveBeenCalledTimes(2);
    methodAsk.answer(10);
    await again;
    expect(requests.find((r) => r.method === 'PATCH')?.body).toEqual({ method_id: 10 });
  });

  it('changing its start changes nothing and toasts when the code fails; the next try asks', async () => {
    const requests = fakeApi({
      'GET /plan/start-options': [200, OPTIONS],
      'PATCH /plan/items/77': WRITE
    });
    const spy = failOnce('startAsk');
    const model = planModel();
    await model.changeStart(item, '2026-11-14');
    expect(toasts.current?.message).toBe(WORDS);
    expect(requests).toHaveLength(0);

    const again = model.changeStart(item, '2026-11-14');
    await vi.waitFor(() => expect(startAsk.current).not.toBeNull());
    expect(spy).toHaveBeenCalledTimes(2);
    startAsk.answer({ day: '2026-11-13', time: '21:00' });
    await again;
    expect(requests.find((r) => r.method === 'PATCH')?.body).toEqual({
      start: { day: '2026-11-13', time: '21:00' }
    });
  });

  it('moving it moves nothing and toasts when the start question’s code fails; the next try asks', async () => {
    const requests = fakeApi({
      'GET /plan/start-options': [200, OPTIONS],
      'POST /plan/items/77/move': WRITE
    });
    const spy = failOnce('startAsk');
    const model = planModel();
    const outcome = await model.drop({ item: 77 }, '2026-11-15', 1, 'move');
    expect(outcome).toEqual({ ok: false, error: null, cancelled: true });
    expect(toasts.current?.message).toBe(WORDS);
    expect(requests.filter((r) => r.method === 'POST')).toHaveLength(0);

    const again = model.drop({ item: 77 }, '2026-11-15', 1, 'move');
    await vi.waitFor(() => expect(startAsk.current).not.toBeNull());
    expect(spy).toHaveBeenCalledTimes(2);
    startAsk.answer({ day: '2026-11-14', time: '21:00' });
    await again;
    expect(requests.find((r) => r.path === '/plan/items/77/move')?.body).toMatchObject({
      mode: 'move',
      start: { day: '2026-11-14', time: '21:00' }
    });
  });

  it('Done already marks nothing and toasts when the code fails; the next try marks it', async () => {
    const requests = fakeApi({ 'PATCH /plan/items/77': WRITE });
    const spy = failOnce('startNow');
    const model = planModel();
    const outcome = await model.markStarted(item);
    expect(outcome).toEqual({ ok: false, error: null, cancelled: true });
    expect(toasts.current?.message).toBe(WORDS);
    expect(requests).toHaveLength(0);

    await model.markStarted(item);
    expect(spy).toHaveBeenCalledTimes(2);
    expect(requests[0]!.body).toEqual({ started: true });
  });
});

describe('the questions’ own code', () => {
  it('the optional question: cancelled with a toast when optionalQuestion fails, then asks', async () => {
    fakeApi({
      'GET /recipes/5': [200, { ...CURRY, lines: [] }],
      'GET /recipes/5/stock': [200, { lines: [], counted: 0, missing: 0, stock_unchecked: false }]
    });
    const spy = failOnce('optionalQuestion');
    expect(await optionalAsk.ask({ id: 5 }, 'Sat dinner')).toBeNull();
    expect(toasts.current?.message).toBe(WORDS);
    expect(optionalAsk.current).toBeNull();
    await optionalAsk.ask({ id: 5 }, 'Sat dinner'); // no optional lines: nothing to ask, but it was fetched
    expect(spy).toHaveBeenCalledTimes(2);
  });

  it('the start question: cancelled with a toast when ./client/plan fails, then asks', async () => {
    fakeApi({ 'GET /plan/start-options': [200, OPTIONS] });
    const spy = failOnce('clientPlan');
    const meal = { day: '2026-11-14', slotId: 1, slotName: 'Breakfast' };
    expect(await startAsk.ask({ id: 5, name: 'Dosa' }, meal)).toBeNull();
    expect(toasts.current?.message).toBe(WORDS);
    expect(startAsk.current).toBeNull();
    const again = startAsk.ask({ id: 5, name: 'Dosa' }, meal);
    await vi.waitFor(() => expect(startAsk.current).not.toBeNull());
    expect(spy).toHaveBeenCalledTimes(2);
    startAsk.answer({ day: '2026-11-13', time: '21:00' });
    expect(await again).toEqual({ day: '2026-11-13', time: '21:00' });
  });

  it('the start question: cancelled with a toast when ./startWords fails, then asks', async () => {
    fakeApi({ 'GET /plan/start-options': [200, OPTIONS] });
    const spy = failOnce('startWords');
    const meal = { day: '2026-11-14', slotId: 1, slotName: 'Breakfast' };
    expect(await startAsk.ask({ id: 5, name: 'Dosa' }, meal)).toBeNull();
    expect(toasts.current?.message).toBe(WORDS);
    expect(startAsk.current).toBeNull();
    expect(optionalAsk.startOpen).toBe(false);
    const again = startAsk.ask({ id: 5, name: 'Dosa' }, meal);
    await vi.waitFor(() => expect(startAsk.current).not.toBeNull());
    expect(spy).toHaveBeenCalledTimes(2);
    startAsk.answer({ day: '2026-11-13', time: '21:00' });
    expect(await again).toEqual({ day: '2026-11-13', time: '21:00' });
  });
});

describe('Today’s Move it', () => {
  it('moves nothing and toasts when the start question’s code fails; the next try asks', async () => {
    const requests = fakeApi({
      'GET /plan/start-options': [200, OPTIONS],
      'POST /meals/1/move': WRITE
    });
    const spy = failOnce('startAsk');
    const model = new TodayModel();
    model.data = {
      slots: [{ id: 1, name: 'Breakfast' }],
      plan: { start: '2026-11-14', end: '2026-11-14', meals: [{ id: 1, items: [item] }] }
    } as unknown as TodayData;
    const waiting = { meal_id: 1, date: '2026-11-14', slot_id: 1 } as never;
    expect(await model.move(waiting, '2026-11-15', 1)).toBeUndefined();
    expect(toasts.current?.message).toBe(WORDS);
    expect(requests).toHaveLength(0);

    const again = model.move(waiting, '2026-11-15', 1);
    await vi.waitFor(() => expect(startAsk.current).not.toBeNull());
    expect(spy).toHaveBeenCalledTimes(2);
    startAsk.dismiss();
    await again;
  });
});
