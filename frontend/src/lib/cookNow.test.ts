import { afterEach, describe, expect, it, vi } from 'vitest';
import type { MealSlot, PlanMeal } from './client/plan';
import { undoHistory } from './undo.svelte';
import { cookTarget } from './cookTargets';
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
      servings: null,
      note: null,
      eating: null,
      cooked: false
    })),
    eater_member_ids: []
  };
}

describe('which meal today Cook now plans the recipe into', () => {
  it('does not reuse a recipe of a part-cooked meal that is cooked already (F157)', () => {
    const part = meal(7, 2, 'planned', [5, 9]);
    part.items[0]!.cooked = true;
    expect(cookSpot(TODAY, slots, [part], 5)).toEqual({ kind: 'new', slotId: 1 });
    expect(cookSpot(TODAY, slots, [part], 9)).toEqual({ kind: 'planned', meal: part });
  });

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

  it('else the first meal that is on today, in order, with no meal at all', () => {
    expect(cookSpot(TODAY, slots, [], 5)).toEqual({ kind: 'new', slotId: 1 });
    expect(cookSpot(TODAY, slots, [meal(1, 1, 'cooked', [9])], 5)).toEqual({
      kind: 'new',
      slotId: 2
    });
  });

  it('an empty meal is preferred over one that already has something planned', () => {
    expect(cookSpot(TODAY, slots, [meal(1, 1, 'planned', [9])], 5)).toEqual({
      kind: 'new',
      slotId: 2
    });
  });

  it('skips a meal marked “didn’t cook” and one that was moved: the server refuses both', () => {
    const meals = [meal(1, 1, 'didnt', [9]), meal(2, 2, 'moved', [9])];
    expect(cookSpot(TODAY, slots, meals, 5)).toEqual({ kind: 'new', slotId: 3 });
  });

  it('goes by the order of the meals, not their ids, and never into one that is switched off', () => {
    const meals = [meal(1, 1, 'cooked', [9]), meal(2, 2, 'cooked', [9])];
    expect(cookSpot(TODAY, slots, meals, 5)).toEqual({ kind: 'new', slotId: 3 });
  });

  it('with no empty meal, the first one that is still planned (the recipe is added to it)', () => {
    const meals = [meal(1, 1, 'cooked', [9]), meal(2, 2, 'didnt', [9]), meal(3, 3, 'planned', [9])];
    expect(cookSpot(TODAY, slots, meals, 5)).toEqual({ kind: 'new', slotId: 3 });
  });

  it('when every meal today is cooked, missed or moved, nothing is open', () => {
    const meals = [meal(1, 1, 'cooked', [9]), meal(2, 2, 'didnt', [9]), meal(3, 3, 'moved', [9])];
    expect(cookSpot(TODAY, slots, meals, 5)).toBeNull();
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

  it('Undo of an earlier Cook now does not touch the screen of another recipe’s Cook now', async () => {
    undoHistory.clear();
    serve([]);
    const now = new CookNow();
    await now.start(5); // adds recipe 5; its Undo stays on Ctrl+Z's list
    now.leave();
    serve([meal(7, 2, 'planned', [6])]);
    await now.start(6); // rule 1: already planned, nothing added
    expect(now.mealId).toBe(7);
    expect(await undoHistory.undoLast()).toBe(true); // undoes recipe 5's plan item
    expect(now.undone).toBe(false);
    expect(now.text).toBeNull();
    expect(now.canUndo).toBe(false);
    expect(now.mealId).toBe(7);
    undoHistory.clear();
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

  it('already planned in a meal with another recipe: only this recipe’s item is for Cooked it', async () => {
    serve([meal(7, 2, 'planned', [9, 5, 5])]);
    const now = new CookNow();
    await now.start(5);
    expect(now.mealId).toBe(7);
    expect(now.itemId).toBe(71); // the first item of recipe 5 (meal 7, position 1)
  });

  it('the same recipe twice, the first cooked: Cooked it reviews the second copy', async () => {
    const twice = meal(7, 2, 'planned', [5, 5]);
    twice.items[0]!.cooked = true;
    serve([twice]);
    const now = new CookNow();
    await now.start(5);
    expect(now.mealId).toBe(7);
    expect(now.itemId).toBe(71);
  });

  it('when every meal today is cooked, nothing is written and the one line says so', async () => {
    const calls = serve([
      meal(1, 1, 'cooked', [9]),
      meal(2, 2, 'didnt', [9]),
      meal(3, 3, 'moved', [9])
    ]);
    const now = new CookNow();
    await now.start(5);
    expect(calls.filter((c) => c.startsWith('POST'))).toEqual([]);
    expect(now.mealId).toBeNull();
    expect(now.text).toBe(NOT_PLANNED);
  });

  it('added to a meal that holds other recipes, only the new item is for Cooked it', async () => {
    serve([meal(1, 1, 'cooked', [9]), meal(2, 2, 'cooked', [9]), meal(70, 3, 'planned', [9])]);
    const now = new CookNow();
    await now.start(5);
    expect(now.mealId).toBe(70);
    expect(now.itemId).toBe(700);
  });

  it('a reply lost on the way back: tries once more with the same key, and plans one item', async () => {
    const keys: string[] = [];
    let items = 0;
    vi.stubGlobal('fetch', async (url: string, init: RequestInit) => {
      if (url === '/api/v1/household') return json({ today: TODAY });
      if (url === '/api/v1/meal-slots') return json(slots);
      if (url.startsWith('/api/v1/plan?'))
        return json({ start: TODAY, end: TODAY, meals: [], batch_cooks: [], tubs: [] });
      if (url === '/api/v1/plan/items') {
        const key = new Headers(init.headers).get('Idempotency-Key') ?? '';
        const first = !keys.includes(key);
        keys.push(key);
        if (first) items++; // the server did the work
        if (keys.length === 1) throw new TypeError('reply lost');
        return json({
          change: { id: 41, can_undo: true, summary: 'x' },
          meal_id: 70,
          item_id: 700
        });
      }
      return new Response('{}', { status: 404 });
    });
    const now = new CookNow();
    await now.start(5);
    expect(keys).toHaveLength(2);
    expect(keys[0]).toBe(keys[1]);
    expect(items).toBe(1);
    expect(now.mealId).toBe(70);
    expect(now.text).toBe('Planned for today’s Breakfast');
    expect(now.canUndo).toBe(true);
  });

  it.each([409, 400])('a %i on the plan write is not tried again', async (status) => {
    let posts = 0;
    vi.stubGlobal('fetch', async (url: string, init: RequestInit) => {
      if (url === '/api/v1/household') return json({ today: TODAY });
      if (url === '/api/v1/meal-slots') return json(slots);
      if (url.startsWith('/api/v1/plan?'))
        return json({ start: TODAY, end: TODAY, meals: [], batch_cooks: [], tubs: [] });
      if (url === '/api/v1/plan/items' && init.method === 'POST') {
        posts++;
        return new Response('{"detail":"no"}', { status });
      }
      return new Response('{}', { status: 404 });
    });
    const now = new CookNow();
    await now.start(5);
    expect(posts).toBe(1);
    expect(now.text).toBe(NOT_PLANNED);
    expect(now.mealId).toBeNull();
  });

  it('what the Cooked it screen passes to cookTarget: just this recipe’s item, so one part', async () => {
    const planned = meal(7, 2, 'planned', [9, 5]);
    serve([planned]);
    const now = new CookNow();
    await now.start(5);
    const only = now.onlyItem(5, planned);
    expect(only?.id).toBe(71);
    const target = cookTarget(null, planned, 'x', only);
    expect(target.parts.map((p) => p.itemId)).toEqual([71]);
    expect(target.title).toBe('Cooked R5');
    // Another recipe's Cook mode, or another meal: the whole meal.
    expect(now.onlyItem(6, planned)).toBeNull();
    expect(now.onlyItem(5, meal(8, 2, 'planned', [5]))).toBeNull();
  });

  it('when the second try can’t reach the server either, the “wasn’t planned” line', async () => {
    vi.stubGlobal('fetch', async (url: string) => {
      if (url === '/api/v1/household') return json({ today: TODAY });
      if (url === '/api/v1/meal-slots') return json(slots);
      if (url.startsWith('/api/v1/plan?'))
        return json({ start: TODAY, end: TODAY, meals: [], batch_cooks: [], tubs: [] });
      throw new TypeError('down');
    });
    const now = new CookNow();
    await now.start(5);
    expect(now.mealId).toBeNull();
    expect(now.text).toBe(NOT_PLANNED);
  });

  it('the notice is for this recipe and this ?meal= only, and is gone once Cook mode is left', async () => {
    serve([]);
    const now = new CookNow();
    await now.start(5);
    expect(now.noticeFor(5, 70)).toEqual({ text: 'Planned for today’s Breakfast', canUndo: true });
    expect(now.noticeFor(5, 71)).toBeNull(); // a different ?meal=
    expect(now.noticeFor(5, null)).toBeNull(); // no ?meal= (going back in history)
    expect(now.noticeFor(6, 70)).toBeNull(); // another recipe
    now.leave();
    expect(now.noticeFor(5, 70)).toBeNull();
    expect(now.mealId).toBeNull();
  });

  it('the “wasn’t planned” line belongs to a Cook mode opened with no ?meal=', async () => {
    serve([], { failWrite: true });
    const now = new CookNow();
    await now.start(5);
    expect(now.noticeFor(5, null)).toEqual({ text: NOT_PLANNED, canUndo: false });
    expect(now.noticeFor(5, 70)).toBeNull();
    now.leave();
    expect(now.noticeFor(5, null)).toBeNull();
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
  it('Start cooking from the Plan: this item of this meal, no notice, and nothing planned', () => {
    const planned = meal(7, 2, 'planned', [9, 5]);
    const now = new CookNow();
    now.open(5, 7, 71);
    expect(now.noticeFor(5, 7)).toBeNull();
    expect(now.canUndo).toBe(false);
    expect(now.onlyItem(5, planned)?.id).toBe(71);
    // Another recipe's Cook mode, or another meal: the whole meal.
    expect(now.onlyItem(6, planned)).toBeNull();
    expect(now.onlyItem(5, meal(8, 2, 'planned', [5]))).toBeNull();
    now.leave();
    expect(now.onlyItem(5, planned)).toBeNull();
  });
});
