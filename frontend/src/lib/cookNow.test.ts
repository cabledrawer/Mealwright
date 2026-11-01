import { afterEach, describe, expect, it, vi } from 'vitest';
import type { MealSlot, PlanMeal } from './client/plan';
import { CookNow, NOT_PLANNED, TAKEN_OUT, cookSpot } from './cookNow.svelte';

const slots: MealSlot[] = [
  { id: 3, name: 'Dinner', position: 3, enabled: true },
  { id: 1, name: 'Breakfast', position: 1, enabled: true },
  { id: 2, name: 'Lunch', position: 2, enabled: true },
  { id: 4, name: 'Snack', position: 4, enabled: false }
];
const TODAY = '2026-11-01';

function meal(
  id: number,
  slot_id: number,
  status: PlanMeal['status'],
  recipeIds: number[],
  date = TODAY
): PlanMeal {
  return {
    id,
    date,
    slot_id,
    status,
    kcal: null,
    items: recipeIds.map((r, i) => ({
      id: id * 10 + i,
      position: i,
      kind: 'recipe' as const,
      recipe: {
        id: r,
        name: `R${r}`,
        removed: false,
        photo_url: null,
        time_minutes: null,
        kcal: null
      },
      tub_id: null,
      ingredient: null,
      kept_name: null,
      servings: null
    }))
  };
}

describe('which meal today Cook now plans the recipe into', () => {
  it('uses the meal that already has the recipe, if it is not cooked yet, and plans nothing new', () => {
    const planned = meal(7, 2, 'planned', [5]);
    expect(cookSpot(TODAY, slots, [meal(6, 1, 'planned', [9]), planned], 5)).toEqual({
      kind: 'planned',
      meal: planned
    });
  });

  it('skips a meal that has the recipe but is cooked, or is on another day', () => {
    const meals = [meal(7, 1, 'cooked', [5]), meal(8, 2, 'planned', [5], '2026-11-02')];
    expect(cookSpot(TODAY, slots, meals, 5)).toEqual({ kind: 'new', slotId: 2 });
  });

  it('else the first meal that is on today, in order, with nothing cooked', () => {
    expect(cookSpot(TODAY, slots, [], 5)).toEqual({ kind: 'new', slotId: 1 });
    expect(cookSpot(TODAY, slots, [meal(1, 1, 'cooked', [9])], 5)).toEqual({
      kind: 'new',
      slotId: 2
    });
    // A meal with something else planned still counts as nothing cooked.
    expect(cookSpot(TODAY, slots, [meal(1, 1, 'planned', [9])], 5)).toEqual({
      kind: 'new',
      slotId: 1
    });
  });

  it('goes by the order of the meals, not their ids, and never into one that is switched off', () => {
    const meals = [meal(1, 1, 'cooked', [9]), meal(2, 2, 'cooked', [9])];
    expect(cookSpot(TODAY, slots, meals, 5)).toEqual({ kind: 'new', slotId: 3 });
  });

  it('when every meal today is cooked, the last one that is on', () => {
    const meals = [meal(1, 1, 'cooked', [9]), meal(2, 2, 'cooked', [9]), meal(3, 3, 'cooked', [9])];
    expect(cookSpot(TODAY, slots, meals, 5)).toEqual({ kind: 'new', slotId: 3 });
  });

  it('is nothing when no meal is on', () => {
    expect(
      cookSpot(
        TODAY,
        slots.map((s) => ({ ...s, enabled: false })),
        [],
        5
      )
    ).toBeNull();
  });
});

const json = (body: unknown) =>
  new Response(JSON.stringify(body), {
    status: 200,
    headers: { 'content-type': 'application/json' }
  });

function serve(plan: PlanMeal[], options: { failWrite?: boolean } = {}) {
  const calls: string[] = [];
  vi.stubGlobal('fetch', async (url: string, init: RequestInit) => {
    calls.push(`${init.method} ${url}`);
    if (url === '/api/v1/household') return json({ today: TODAY });
    if (url === '/api/v1/meal-slots') return json(slots);
    if (url.startsWith('/api/v1/plan?'))
      return json({ start: TODAY, end: TODAY, meals: plan, batch_cooks: [], tubs: [] });
    if (url === '/api/v1/plan/items' && init.method === 'POST') {
      if (options.failWrite) return new Response('{"detail":"no"}', { status: 500 });
      return json({ change: { id: 41, can_undo: true, summary: 'x' }, meal_id: 70, item_id: 700 });
    }
    if (url === '/api/v1/changes/41/undo') {
      return json({
        result: 'done',
        message: 'Done',
        change: { id: 42 },
        undone: null,
        groups: [],
        food: null
      });
    }
    return new Response('{}', { status: 404 });
  });
  return calls;
}

afterEach(() => vi.unstubAllGlobals());

describe('Cook now plans first', () => {
  it('plans the recipe into today’s next meal, says where, and Undo takes it out', async () => {
    const calls = serve([]);
    const now = new CookNow();
    await now.start(5);
    expect(calls).toContain('POST /api/v1/plan/items');
    expect(now.mealId).toBe(70);
    expect(now.text).toBe('Planned for today’s Breakfast');
    expect(now.canUndo).toBe(true);
    await now.undo();
    expect(calls).toContain('POST /api/v1/changes/41/undo');
    expect(now.undone).toBe(true);
    expect(now.text).toBe(TAKEN_OUT);
    expect(now.canUndo).toBe(false);
  });

  it('adds nothing when the recipe is already planned in a meal today', async () => {
    const calls = serve([meal(7, 2, 'planned', [5])]);
    const now = new CookNow();
    await now.start(5);
    expect(calls.filter((c) => c.startsWith('POST'))).toEqual([]);
    expect(now.mealId).toBe(7);
    expect(now.text).toBeNull();
    expect(now.canUndo).toBe(false);
  });

  it('when the plan can’t be written, there is no meal and one line says so', async () => {
    serve([], { failWrite: true });
    const now = new CookNow();
    await now.start(5);
    expect(now.mealId).toBeNull();
    expect(now.text).toBe(NOT_PLANNED);
  });

  it('when the server can’t be reached, the same', async () => {
    vi.stubGlobal('fetch', async () => {
      throw new TypeError('down');
    });
    const now = new CookNow();
    await now.start(5);
    expect(now.mealId).toBeNull();
    expect(now.text).toBe(NOT_PLANNED);
  });
});
