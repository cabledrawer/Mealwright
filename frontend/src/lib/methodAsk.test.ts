// Two cooking methods when planning (M2, cabledrawer 9 Nov): a recipe with two ways of cooking it asks
// which one (the one used last is pre-picked), in every way a recipe is added to the plan, and
// again from the meal.

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import type { PlanItem } from './client/plan';
import { methodAsk } from './methodAsk.svelte';
import { network } from './network.svelte';
import { optionalAsk } from './optionalAsk.svelte';
import { PlanModel } from './plan.svelte';
import { fakeApi } from './testing/fakeApi';
import { toasts } from './toast.svelte';

const line = (id: number, words: string, optional = false) => ({
  id,
  kind: 'ingredient',
  words,
  amount: 1,
  amount_text: '1',
  unit: 'kg',
  size: null,
  food: null,
  recipe: null,
  link: 'none',
  note: null,
  optional
});

const CURRY = {
  id: 5,
  name: 'Chicken curry',
  serves: 4,
  lines: [line(1, 'Chicken')],
  steps: [],
  methods: [
    { id: 10, name: 'Stovetop', time_minutes: 45, used_last: false },
    { id: 11, name: 'Instant Pot', time_minutes: 30, used_last: true }
  ],
  second_method: {
    id: 11,
    name: 'Instant Pot',
    time_minutes: 30,
    used_last: true,
    lines: [line(2, 'Stock'), line(3, 'Kewra', true)],
    steps: []
  }
};
const STOCK = { lines: [], counted: 0, missing: 0, stock_unchecked: false };
const PLAIN = { ...CURRY, id: 6, methods: [CURRY.methods[0]], second_method: null };

beforeEach(() => network.reset());
afterEach(() => {
  methodAsk.dismiss();
  optionalAsk.dismiss();
  toasts.dismiss();
  vi.unstubAllGlobals();
  network.reset();
});

describe('asking', () => {
  it('pre-picks the way used last, and answers with the id picked', async () => {
    fakeApi({ 'GET /recipes/5': [200, CURRY] });
    const answer = methodAsk.ask({ id: 5 }, 'Sat dinner');
    await vi.waitFor(() => expect(methodAsk.current).not.toBeNull());
    const question = methodAsk.current!.question;
    expect(question.methods.map((m) => m.name)).toEqual(['Stovetop', 'Instant Pot']);
    expect(question.picked).toBe(11);
    expect(question.button).toBe('Add to plan');
    methodAsk.answer(10);
    expect(await answer).toBe(10);
  });

  it('starts with the meal’s own way when it is changed, and Cancel answers null', async () => {
    fakeApi({ 'GET /recipes/5': [200, CURRY] });
    const answer = methodAsk.ask({ id: 5 }, 'Sat dinner', { current: 10, button: 'Save' });
    await vi.waitFor(() => expect(methodAsk.current).not.toBeNull());
    expect(methodAsk.current!.question.picked).toBe(10);
    methodAsk.dismiss();
    expect(await answer).toBeNull();
  });

  it('asks nothing of a recipe with one way, or that is known to have one', async () => {
    const requests = fakeApi({ 'GET /recipes/6': [200, PLAIN] });
    expect(await methodAsk.ask({ id: 6 }, 'Sat dinner')).toBeUndefined();
    expect(await methodAsk.ask({ id: 5, methodCount: 1 }, 'Sat dinner')).toBeUndefined();
    expect(requests.map((r) => r.path)).toEqual(['/recipes/6']);
  });
});

describe('every way a recipe is added to the plan asks, through PlanModel.add', () => {
  const body = (requests: ReturnType<typeof fakeApi>) =>
    requests.find((r) => r.method === 'POST' && r.path === '/plan/items')?.body;

  it('sends the way picked, then asks about the optional lines of that way', async () => {
    const requests = fakeApi({
      'GET /recipes/5': [200, CURRY],
      'GET /recipes/5/stock': [200, STOCK],
      'POST /plan/items': [200, { change: null, meal_id: 1, item_id: 2 }]
    });
    const added = new PlanModel().add(
      { recipe: { id: 5, name: 'Chicken curry', method_count: 2 } },
      '2026-11-14',
      3
    );
    await vi.waitFor(() => expect(methodAsk.current).not.toBeNull());
    methodAsk.answer(11);
    await vi.waitFor(() => expect(optionalAsk.current).not.toBeNull());
    // The Instant Pot's own optional line, not the Stovetop's.
    expect(optionalAsk.current!.question.rows.map((r) => r.words)).toEqual(['Kewra']);
    expect(requests.some((r) => r.path === '/recipes/5/stock')).toBe(true);
    optionalAsk.answer([3]);
    expect((await added).ok).toBe(true);
    expect(body(requests)).toEqual({
      date: '2026-11-14',
      slot_id: 3,
      recipe_id: 5,
      method_id: 11,
      optional_use: [3]
    });
  });

  it('plans nothing when the question is cancelled', async () => {
    const requests = fakeApi({
      'GET /recipes/5': [200, CURRY],
      'POST /plan/items': [200, { change: null, meal_id: 1, item_id: 2 }]
    });
    const added = new PlanModel().add(
      { recipe: { id: 5, name: 'Chicken curry' } },
      '2026-11-14',
      3
    );
    await vi.waitFor(() => expect(methodAsk.current).not.toBeNull());
    methodAsk.dismiss();
    const outcome = await added;
    expect(outcome.ok === false && outcome.cancelled).toBe(true);
    expect(body(requests)).toBeUndefined();
  });

  it('a recipe the list says has one way is planned at once, with no question', async () => {
    const requests = fakeApi({
      'POST /plan/items': [200, { change: null, meal_id: 1, item_id: 2 }]
    });
    await new PlanModel().add(
      { recipe: { id: 6, name: 'Plain rice', optional_count: 0, method_count: 1 } },
      '2026-11-14',
      3
    );
    expect(methodAsk.current).toBeNull();
    expect(body(requests)).toEqual({ date: '2026-11-14', slot_id: 3, recipe_id: 6 });
    expect(requests.some((r) => r.path.startsWith('/recipes'))).toBe(false);
  });

  it('changing the way from the meal sends the new one, and the same way sends nothing', async () => {
    const requests = fakeApi({
      'GET /recipes/5': [200, CURRY],
      'PUT /plan/items/77/method': [200, { change: null, meal_id: 1, item_id: 77 }]
    });
    const model = new PlanModel();
    const item = {
      id: 77,
      kind: 'recipe',
      recipe: { id: 5, name: 'Chicken curry', removed: false, methods: CURRY.methods },
      method_id: 11
    } as unknown as PlanItem;
    const changed = model.changeMethod(item, '2026-11-14');
    await vi.waitFor(() => expect(methodAsk.current).not.toBeNull());
    expect(methodAsk.current!.question.picked).toBe(11);
    methodAsk.answer(10);
    await changed;
    expect(requests.find((r) => r.method === 'PUT')?.body).toEqual({ method_id: 10 });
    const again = model.changeMethod({ ...item, method_id: 10 } as PlanItem, '2026-11-14');
    await vi.waitFor(() => expect(methodAsk.current).not.toBeNull());
    methodAsk.answer(10);
    await again;
    expect(requests.filter((r) => r.method === 'PUT')).toHaveLength(1);
  });
});
