// Optional ingredients (R3, cabledrawer 6 and 9 Nov): a recipe with Optional lines asks which the
// meal will use, in every way a recipe is added to the plan, and again from the meal.

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import type { PlanItem } from './client/plan';
import { network } from './network.svelte';
import { optionalAsk, optionalQuestionWords, stateWords } from './optionalAsk.svelte';
import { PlanModel } from './plan.svelte';
import { fakeApi } from './testing/fakeApi';
import { toasts } from './toast.svelte';

const NB = '\u00a0'; // a number and its unit never split

const line = (
  id: number,
  words: string,
  amount: string,
  unit: string | null,
  optional: boolean
) => ({
  id,
  kind: 'ingredient',
  words,
  amount: Number(amount),
  amount_text: amount,
  unit,
  size: null,
  food: null,
  recipe: null,
  link: 'none',
  note: null,
  optional
});

const BIRYANI = {
  id: 5,
  name: 'Mutton biryani',
  serves: 6,
  lines: [
    line(1, 'Mutton', '1', 'kg', false),
    line(2, 'Raw papaya paste', '2', 'tbsp', true),
    line(3, 'Kewra water', '0.5', 'tsp', true)
  ],
  steps: []
};
const STOCK = {
  lines: [
    { line_id: 2, food: { id: 9, name: 'Papaya' }, state: 'missing', place: null },
    { line_id: 3, food: { id: 8, name: 'Kewra' }, state: 'in_stock', place: 'Cupboard' }
  ],
  counted: 2,
  missing: 1,
  stock_unchecked: false
};
const PLAIN = { ...BIRYANI, id: 6, name: 'Plain rice', lines: [BIRYANI.lines[0]] };

beforeEach(() => network.reset());
afterEach(() => {
  optionalAsk.dismiss();
  toasts.dismiss();
  vi.unstubAllGlobals();
  network.reset();
});

describe('the words', () => {
  it('says where an optional line is in the pantry', () => {
    const at = (state: 'in_stock' | 'staple' | 'short' | 'missing', place: string | null) =>
      stateWords({ line_id: 1, food: { id: 1, name: 'x' }, state, place });
    expect(at('missing', null)).toBe('not in the pantry');
    expect(at('in_stock', 'Cupboard')).toBe('in the cupboard');
    expect(at('in_stock', null)).toBe('in the pantry');
    expect(at('staple', null)).toBe('a staple');
    expect(at('short', null)).toBe('not enough in the pantry');
    expect(stateWords(undefined)).toBe('');
  });

  it('counts the optional ingredients', () => {
    expect(optionalQuestionWords(2)).toBe(
      'This recipe has 2 optional ingredients. Will you use them?'
    );
    expect(optionalQuestionWords(1)).toBe(
      'This recipe has 1 optional ingredient. Will you use it?'
    );
  });
});

describe('asking', () => {
  it('shows each optional line with its amount and pantry state, all ticked to begin with', async () => {
    fakeApi({ 'GET /recipes/5': [200, BIRYANI], 'GET /recipes/5/stock': [200, STOCK] });
    const answer = optionalAsk.ask({ id: 5 }, 'Sat dinner');
    await vi.waitFor(() => expect(optionalAsk.current).not.toBeNull());
    const question = optionalAsk.current!.question;
    expect(question.recipeName).toBe('Mutton biryani');
    expect(question.where).toBe('Sat dinner');
    expect(question.rows.map((r) => [r.words, r.detail])).toEqual([
      ['Raw papaya paste', `2${NB}tbsp · not in the pantry`],
      ['Kewra water', `0.5${NB}tsp · in the cupboard`]
    ]);
    expect(question.ticked).toEqual([2, 3]);
    optionalAsk.answer([2]);
    expect(await answer).toEqual([2]);
    expect(optionalAsk.current).toBeNull();
  });

  it('starts with what the meal has now when it is changed, and Cancel answers null', async () => {
    fakeApi({ 'GET /recipes/5': [200, BIRYANI], 'GET /recipes/5/stock': [200, STOCK] });
    const answer = optionalAsk.ask({ id: 5 }, 'Sat dinner', { skipped: [3], button: 'Save' });
    await vi.waitFor(() => expect(optionalAsk.current).not.toBeNull());
    expect(optionalAsk.current!.question.ticked).toEqual([2]);
    expect(optionalAsk.current!.question.button).toBe('Save');
    optionalAsk.dismiss();
    expect(await answer).toBeNull();
  });

  it('asks nothing of a recipe with no optional line, or that is known to have none', async () => {
    const requests = fakeApi({ 'GET /recipes/6': [200, PLAIN] });
    expect(await optionalAsk.ask({ id: 6 }, 'Sat dinner')).toBeUndefined();
    expect(await optionalAsk.ask({ id: 5, optionalCount: 0 }, 'Sat dinner')).toBeUndefined();
    expect(requests.map((r) => r.path)).toEqual(['/recipes/6', '/recipes/6/stock']);
    expect(optionalAsk.current).toBeNull();
  });

  it('goes on without asking when the recipe cannot be read', async () => {
    fakeApi({});
    expect(await optionalAsk.ask({ id: 5 }, 'Sat dinner')).toBeUndefined();
  });
});

describe('every way a recipe is added to the plan asks, through PlanModel.add', () => {
  const body = (requests: ReturnType<typeof fakeApi>) =>
    requests.find((r) => r.method === 'POST' && r.path === '/plan/items')?.body;

  it('sends the lines that were ticked', async () => {
    const requests = fakeApi({
      'GET /recipes/5': [200, BIRYANI],
      'GET /recipes/5/stock': [200, STOCK],
      'POST /plan/items': [200, { change: null, meal_id: 1, item_id: 2 }]
    });
    const model = new PlanModel();
    const added = model.add({ recipe: { id: 5, name: 'Mutton biryani' } }, '2026-11-14', 3);
    await vi.waitFor(() => expect(optionalAsk.current).not.toBeNull());
    expect(optionalAsk.current!.question.where).toBe('Sat meal');
    optionalAsk.answer([3]);
    expect((await added).ok).toBe(true);
    expect(body(requests)).toEqual({
      date: '2026-11-14',
      slot_id: 3,
      recipe_id: 5,
      optional_use: [3]
    });
  });

  it('plans nothing when the question is cancelled', async () => {
    const requests = fakeApi({
      'GET /recipes/5': [200, BIRYANI],
      'GET /recipes/5/stock': [200, STOCK],
      'POST /plan/items': [200, { change: null, meal_id: 1, item_id: 2 }]
    });
    const model = new PlanModel();
    const added = model.add({ recipe: { id: 5, name: 'Mutton biryani' } }, '2026-11-14', 3);
    await vi.waitFor(() => expect(optionalAsk.current).not.toBeNull());
    optionalAsk.dismiss();
    const outcome = await added;
    expect(outcome.ok === false && outcome.cancelled).toBe(true);
    expect(body(requests)).toBeUndefined();
  });

  it('a recipe the list says has none is planned at once, with no question', async () => {
    const requests = fakeApi({
      'POST /plan/items': [200, { change: null, meal_id: 1, item_id: 2 }]
    });
    const model = new PlanModel();
    await model.add({ recipe: { id: 6, name: 'Plain rice', optional_count: 0 } }, '2026-11-14', 3);
    expect(optionalAsk.current).toBeNull();
    expect(body(requests)).toEqual({ date: '2026-11-14', slot_id: 3, recipe_id: 6 });
    expect(requests.some((r) => r.path.startsWith('/recipes'))).toBe(false);
  });

  it('a plain ingredient is never asked about', async () => {
    const requests = fakeApi({
      'POST /plan/items': [200, { change: null, meal_id: 1, item_id: 2 }]
    });
    const model = new PlanModel();
    await model.add({ ingredient: { id: 9, name: 'Fruit' } }, '2026-11-14', 3);
    expect(body(requests)).toEqual({ date: '2026-11-14', slot_id: 3, ingredient_id: 9 });
  });

  it('changing the answer from the meal sends the new ticks', async () => {
    const requests = fakeApi({
      'GET /recipes/5': [200, BIRYANI],
      'GET /recipes/5/stock': [200, STOCK],
      'PUT /plan/items/77/optional': [200, { change: null, meal_id: 1, item_id: 77 }]
    });
    const model = new PlanModel();
    const item = {
      id: 77,
      kind: 'recipe',
      recipe: { id: 5, name: 'Mutton biryani', removed: false, optional_count: 2 },
      optional_skipped: [3]
    } as unknown as PlanItem;
    const changed = model.changeOptional(item, '2026-11-14');
    await vi.waitFor(() => expect(optionalAsk.current).not.toBeNull());
    expect(optionalAsk.current!.question.ticked).toEqual([2]);
    optionalAsk.answer([2, 3]);
    await changed;
    expect(requests.find((r) => r.method === 'PUT')?.body).toEqual({ use: [2, 3] });
  });
});
