import { describe, expect, it } from 'vitest';
import type { Plan, PlanBatch, PlanItem, PlanMeal } from './client/plan';
import { cookTarget, cookedStaysNote, cookedTitle } from './cookTargets';

const recipe = (id: number, name: string, recipeId = id): PlanItem => ({
  id,
  position: id,
  kind: 'recipe',
  recipe: { id: recipeId, name, removed: false, serves: 4 } as unknown as PlanItem['recipe'],
  tub_id: null,
  food: null,
  kept_name: null,
  note: null,
  servings: 4,
  eating: null,
  cooked: false
});

const meal = (items: PlanItem[]): PlanMeal => ({
  id: 7,
  date: '2026-10-15',
  slot_id: 1,
  status: 'planned',
  items,
  kcal: null,
  eater_member_ids: []
});

const batch = (recipeId: number): PlanBatch =>
  ({
    id: 3,
    recipe_id: recipeId,
    recipe_name: 'Rasam',
    cook_meal_id: 7,
    cooked_on: '2026-10-15',
    tub_count: 4
  }) as PlanBatch;

const plan = (batches: PlanBatch[] = []) =>
  ({ batch_cooks: batches, tubs: [], meals: [] }) as unknown as Plan;

describe('what "Cooked it" is about', () => {
  it("one tab for each recipe, in the meal's order", () => {
    const m = meal([recipe(1, 'Dosa'), recipe(2, 'Chutney')]);
    const t = cookTarget(plan(), m, 'Thu 15 Oct · dinner');
    expect(t.title).toBe('Cooked Dosa and Chutney');
    expect(t.mealId).toBe(7);
    expect(t.parts).toEqual([
      { itemId: 1, batchId: null, name: 'Dosa' },
      { itemId: 2, batchId: null, name: 'Chutney' }
    ]);
  });

  it('a recipe a batch was made from is cooked as the batch', () => {
    const m = meal([recipe(1, 'Dosa'), recipe(2, 'Rasam', 22)]);
    const t = cookTarget(plan([batch(22)]), m, '');
    expect(t.parts.map((p) => [p.itemId, p.batchId])).toEqual([
      [1, null],
      [null, 3]
    ]);
  });

  it('only one recipe of the meal, from its own menu', () => {
    const m = meal([recipe(1, 'Dosa'), recipe(2, 'Chutney')]);
    expect(cookTarget(plan(), m, '', m.items[1]).parts.map((p) => p.name)).toEqual(['Chutney']);
  });

  it('leaves out a recipe already cooked, so a second open reviews what is left (F157)', () => {
    const m = meal([{ ...recipe(1, 'Dosa'), cooked: true }, recipe(2, 'Chutney')]);
    const t = cookTarget(plan(), m, '');
    expect(t.title).toBe('Cooked Chutney');
    expect(t.parts.map((p) => p.name)).toEqual(['Chutney']);
    // Asked for the one that is cooked already: nothing to review.
    expect(cookTarget(plan(), m, '', m.items[0]).parts).toEqual([]);
  });

  it('a tub or a plain ingredient takes nothing, and a meal without a recipe has no parts', () => {
    const tub: PlanItem = { ...recipe(5, 'x'), kind: 'tub', recipe: null, tub_id: 9 };
    const t = cookTarget(plan(), meal([tub]), 'x');
    expect(t.parts).toEqual([]);
  });

  it('says the names in a sentence', () => {
    expect(cookedTitle(['A'])).toBe('Cooked A');
    expect(cookedTitle(['A', 'B', 'C'])).toBe('Cooked A, B and C');
  });
});

describe('the Plan panel’s note for cooked recipes (F163)', () => {
  it('names the cooked recipes, in both forms', () => {
    expect(cookedStaysNote(['Banana bread'])).toBe(
      'Banana bread was cooked. Undo its Cooked it to move or remove it.'
    );
    expect(cookedStaysNote(['Banana bread', 'Lentil soup'])).toBe(
      'Banana bread and Lentil soup were cooked. Undo their Cooked it to move or remove them.'
    );
  });
});

describe('what the review leaves out and names (F158, F133)', () => {
  it('leaves out a recipe taken out of the recipe list', () => {
    const gone = recipe(2, 'Old stew');
    gone.recipe!.removed = true;
    const t = cookTarget(plan(), meal([recipe(1, 'Dosa'), gone]), '');
    expect(t.parts.map((p) => p.name)).toEqual(['Dosa']);
    expect(t.title).toBe('Cooked Dosa');
  });

  it('names every tub and recipe of a meal that has nothing to cook', () => {
    const tub = (id: number): PlanItem => ({
      ...recipe(id, ''),
      kind: 'tub',
      recipe: null,
      tub_id: id
    });
    const t = cookTarget(plan(), meal([tub(1), tub(2)]), '');
    expect(t.parts).toEqual([]);
    expect(t.title).toBe('Cooked Tub and Tub');
  });
});
