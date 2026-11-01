import { describe, expect, it } from 'vitest';
import type { Plan, PlanItem, PlanMeal } from './client/plan';
import {
  withEaters,
  withItemDropped,
  withMealDropped,
  withoutItem,
  withoutMeal,
  withServings
} from './planEdits';

const item = (id: number, name: string, kcal: number | null = null): PlanItem => ({
  id,
  position: 0,
  kind: 'recipe',
  recipe: { id, name, removed: false, photo_url: null, time_minutes: null, kcal },
  tub_id: null,
  ingredient: null,
  kept_name: null,
  servings: null,
  note: null,
  eating: null
});
const meal = (id: number, date: string, slot: number, items: PlanItem[]): PlanMeal => ({
  id,
  date,
  slot_id: slot,
  status: 'planned',
  eater_login_ids: [],
  items,
  kcal: null
});
const plan = (): Plan => ({
  start: '2026-10-19',
  end: '2026-10-25',
  meals: [
    meal(1, '2026-10-19', 3, [item(11, 'Sambar', 300), item(12, 'Dosa', 290)]),
    meal(2, '2026-10-20', 3, [item(21, 'Rajma')])
  ],
  batch_cooks: [],
  tubs: []
});
const shape = (p: Plan) =>
  p.meals
    .map((m) => `${m.date}/${m.slot_id}: ${m.items.map((i) => i.recipe?.name).join('+')}`)
    .sort();

describe('the plan straight after a change', () => {
  it('takes an item out, and its meal when it was the last', () => {
    expect(shape(withoutItem(plan(), 11))).toEqual(['2026-10-19/3: Dosa', '2026-10-20/3: Rajma']);
    expect(shape(withoutItem(plan(), 21))).toEqual(['2026-10-19/3: Sambar+Dosa']);
  });

  it('takes a meal out', () => {
    expect(shape(withoutMeal(plan(), 1))).toEqual(['2026-10-20/3: Rajma']);
  });

  it('moves a meal to an empty slot, or in alongside a filled one', () => {
    expect(shape(withMealDropped(plan(), 2, '2026-10-22', 1, 'move'))).toContain(
      '2026-10-22/1: Rajma'
    );
    expect(shape(withMealDropped(plan(), 2, '2026-10-19', 3, 'move'))).toEqual([
      '2026-10-19/3: Sambar+Dosa+Rajma'
    ]);
  });

  it('copies a meal and leaves the first where it was', () => {
    const next = withMealDropped(plan(), 1, '2026-10-21', 3, 'copy');
    expect(shape(next)).toEqual([
      '2026-10-19/3: Sambar+Dosa',
      '2026-10-20/3: Rajma',
      '2026-10-21/3: Sambar+Dosa'
    ]);
    // The copies have ids of their own, below zero until the server answers.
    expect(next.meals.at(-1)?.items.every((i) => i.id < 0)).toBe(true);
  });

  it('adds up the kcal of what is left', () => {
    expect(withoutItem(plan(), 12).meals[0]?.kcal).toBe(300);
    expect(plan().meals[0]?.items).toHaveLength(2); // the old plan is not touched
  });

  it('moves and copies one item', () => {
    expect(shape(withItemDropped(plan(), 11, '2026-10-20', 3, 'move'))).toEqual([
      '2026-10-19/3: Dosa',
      '2026-10-20/3: Rajma+Sambar'
    ]);
    expect(shape(withItemDropped(plan(), 11, '2026-10-22', 1, 'copy'))).toEqual([
      '2026-10-19/3: Sambar+Dosa',
      '2026-10-20/3: Rajma',
      '2026-10-22/1: Sambar'
    ]);
  });

  it('does nothing when dropped where it already is', () => {
    expect(withMealDropped(plan(), 1, '2026-10-19', 3, 'move')).toEqual(plan());
    expect(withItemDropped(plan(), 11, '2026-10-19', 3, 'copy')).toEqual(plan());
  });
});

describe('Serves - N + and who is eating, straight after a change', () => {
  it('sets how many a recipe is for, on a meal planned before the update too', () => {
    const before = plan();
    expect(before.meals[0]?.items[0]?.servings).toBeNull(); // no number set
    const next = withServings(before, 11, 6);
    expect(next.meals[0]?.items[0]).toMatchObject({ servings: 6, eating: 6 });
    expect(next.meals[0]?.items[1]).toMatchObject({ servings: null }); // only that recipe
    expect(before.meals[0]?.items[0]?.servings).toBeNull(); // the old plan is not touched
  });

  it('leaves anything that is not a recipe alone', () => {
    const base = plan();
    base.meals[1]!.items[0] = { ...base.meals[1]!.items[0]!, kind: 'note', note: 'Eating out' };
    expect(withServings(base, 21, 4).meals[1]?.items[0]).toMatchObject({ servings: null });
  });

  it('ticks people for a meal, in order, and an empty list is everyone', () => {
    const next = withEaters(plan(), 1, [3, 1]);
    expect(next.meals[0]?.eater_login_ids).toEqual([1, 3]);
    expect(next.meals[1]?.eater_login_ids).toEqual([]);
    expect(withEaters(next, 1, []).meals[0]?.eater_login_ids).toEqual([]);
  });
});
