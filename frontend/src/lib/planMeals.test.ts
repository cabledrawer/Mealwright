import { describe, expect, it } from 'vitest';
import type { Plan, PlanItem, PlanMeal } from './client/plan';
import { batchColour, mealName, mealTotals, tubWords } from './planMeals';

const recipe = (id: number, name: string): PlanItem => ({
  id,
  position: id,
  kind: 'recipe',
  recipe: { id, name, removed: false, photo_url: null, time_minutes: null, kcal: null },
  tub_id: null,
  ingredient: null,
  servings: null
});
const fruit: PlanItem = {
  id: 9,
  position: 9,
  kind: 'ingredient',
  recipe: null,
  tub_id: null,
  ingredient: { id: 1, name: 'Banana', removed: false },
  servings: null
};
const meal = (items: PlanItem[], kcal: number | null = null): PlanMeal => ({
  id: 1,
  date: '2026-10-19',
  slot_id: 1,
  status: 'planned',
  items,
  kcal
});

describe('a meal card’s words', () => {
  it('counts recipes and adds the kcal', () => {
    expect(mealTotals(meal([recipe(1, 'Dosa'), recipe(2, 'Chutney')], 590))).toBe(
      '2 recipes · 590 kcal'
    );
    expect(mealTotals(meal([recipe(1, 'Dosa')]))).toBe('1 recipe');
  });

  it('says ingredients, or things when they are mixed', () => {
    expect(mealTotals(meal([fruit]))).toBe('1 ingredient');
    expect(mealTotals(meal([recipe(1, 'Dosa'), fruit], 230))).toBe('2 things · 230 kcal');
  });

  it('names a meal by its first thing', () => {
    expect(mealName(meal([recipe(1, 'Dosa')]))).toBe('Dosa');
    expect(mealName(meal([recipe(1, 'Dosa'), fruit]))).toBe('Dosa and 1 more');
  });

  it('words a tub by its batch', () => {
    const plan: Plan = {
      start: '',
      end: '',
      meals: [],
      batch_cooks: [
        {
          id: 3,
          recipe_id: 1,
          recipe_name: 'Chana masala',
          cook_meal_id: null,
          cooked_on: '2026-10-18',
          tub_count: 4,
          pattern: 'pick',
          prep_note: null,
          colour: null
        }
      ],
      tubs: [
        {
          id: 7,
          batch_id: 3,
          amount_quarters: 4,
          number: 2,
          place_id: null,
          member_login_id: null,
          use_by: '2026-10-21'
        }
      ]
    };
    const tub: PlanItem = { ...fruit, kind: 'tub', ingredient: null, tub_id: 7 };
    expect(tubWords(tub, plan)).toBe('Tub 2 of 4');
    expect(tubWords(fruit, plan)).toBeNull();
  });

  it('gives one batch one colour, cycling through the six', () => {
    expect(batchColour(1)).toBe(1);
    expect(batchColour(6)).toBe(6);
    expect(batchColour(7)).toBe(1);
  });
});
