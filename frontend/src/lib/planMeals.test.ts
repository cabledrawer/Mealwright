import { describe, expect, it } from 'vitest';
import type { MealSlot, Plan, PlanItem, PlanMeal } from './client/plan';
import {
  afterCook,
  batchColour,
  dayAfterCook,
  colourOfBatch,
  cookBatchOfItem,
  itemName,
  mealColour,
  mealName,
  mealTotals,
  tubOf,
  tubWords,
  useByWords,
  whoseTub
} from './planMeals';

const recipe = (id: number, name: string): PlanItem => ({
  id,
  position: id,
  kind: 'recipe',
  recipe: { id, name, removed: false, photo_url: null, time_minutes: null, kcal: null },
  tub_id: null,
  ingredient: null,
  kept_name: null,
  servings: null
});
const fruit: PlanItem = {
  id: 9,
  position: 9,
  kind: 'ingredient',
  recipe: null,
  tub_id: null,
  ingredient: { id: 1, name: 'Banana', removed: false },
  kept_name: null,
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

  it('names a recipe or ingredient deleted for good by the name it kept', () => {
    const gone = { ...recipe(4, 'Sambar'), recipe: null, kept_name: 'Sambar' };
    const goneFruit = { ...fruit, ingredient: null, kept_name: 'Banana' };
    expect([itemName(gone), itemName(goneFruit)]).toEqual(['Sambar', 'Banana']);
    expect(mealName(meal([gone, goneFruit]))).toBe('Sambar and 1 more');
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
          place_kind: null,
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

  it('names a batch colour from its palette name, or by its id when it has none', () => {
    expect(colourOfBatch({ id: 9, colour: 'amber' })).toBe(2);
    expect(colourOfBatch({ id: 9, colour: 'teal' })).toBe(6);
    expect(colourOfBatch({ id: 9, colour: null })).toBe(batchColour(9));
    expect(colourOfBatch({ id: 2, colour: 'not-a-colour' })).toBe(batchColour(2));
  });

  it('finds the tub and batch of a meal item, and the batch a recipe was cooked for', () => {
    const batch = {
      id: 3,
      recipe_id: 1,
      recipe_name: 'Chana masala',
      cook_meal_id: 50,
      cooked_on: '2026-10-18',
      tub_count: 2,
      pattern: 'pick' as const,
      prep_note: null,
      colour: 'green'
    };
    const tub = {
      id: 7,
      batch_id: 3,
      amount_quarters: 4,
      number: 1,
      place_id: 1,
      place_kind: 'fridge' as const,
      member_login_id: 4,
      use_by: '2026-10-21'
    };
    const plan: Plan = { start: '', end: '', meals: [], batch_cooks: [batch], tubs: [tub] };
    const recipeItem: PlanItem = {
      ...fruit,
      kind: 'recipe',
      ingredient: null,
      recipe: {
        id: 1,
        name: 'Chana masala',
        removed: false,
        photo_url: null,
        time_minutes: null,
        kcal: null
      }
    };
    const tubItem: PlanItem = { ...fruit, kind: 'tub', ingredient: null, tub_id: 7 };
    const meal = (id: number): PlanMeal => ({
      id,
      date: '2026-10-18',
      slot_id: 1,
      status: 'planned',
      items: [],
      kcal: null
    });
    expect(tubOf(plan, tubItem)).toEqual({ tub, batch });
    expect(tubOf(plan, fruit)).toBeNull();
    expect(cookBatchOfItem(plan, meal(50), recipeItem)).toEqual(batch);
    expect(cookBatchOfItem(plan, meal(51), recipeItem)).toBeNull();
    expect(cookBatchOfItem(plan, meal(50), fruit)).toBeNull();
    // A meal's colour: the batch's, whether it holds the tub or was the cook day.
    expect(mealColour(plan, { ...meal(50) })).toBe(3);
    expect(mealColour(plan, { ...meal(60), items: [tubItem] })).toBe(3);
    expect(mealColour(plan, meal(61))).toBeNull();
    expect(whoseTub(tub, [{ login_id: 4, name: 'Wren' }])).toBe('Wren');
    expect(whoseTub(tub, [])).toBeNull();
  });

  it('says how long a tub keeps', () => {
    expect(useByWords('2026-10-26', '2026-10-26')).toBe('use by today');
    expect(useByWords('2026-10-27', '2026-10-26')).toBe('use by tomorrow');
    expect(useByWords('2026-10-29', '2026-10-26')).toBe('3 days left');
    expect(useByWords('2026-10-25', '2026-10-26')).toBe('use by yesterday');
    expect(useByWords('2026-10-22', '2026-10-26')).toBe('4 days past use-by');
  });

  it('counts days left from the cook day when the batch is not cooked yet (F48)', () => {
    // Cooked Sat 31 Oct, 3 days in the fridge: use by Tue 3 Nov. On Wed 28 Oct it is not made
    // yet, so it says 3 days left, never 6.
    expect(useByWords('2026-11-03', '2026-10-28', '2026-10-31')).toBe('3 days left');
    // Once cooked, it counts from today as before.
    expect(useByWords('2026-11-03', '2026-11-01', '2026-10-31')).toBe('2 days left');
    expect(useByWords('2026-11-03', '2026-11-03', '2026-10-31')).toBe('use by today');
  });
});

describe('where leftovers may go (F50)', () => {
  const slot = (id: number, name: string): MealSlot =>
    ({ id, name, position: id, enabled: true }) as MealSlot;
  const slots = [slot(1, 'Breakfast'), slot(2, 'Lunch'), slot(3, 'Dinner')];
  const cook = { date: '2026-10-29', slot_id: 3 }; // Thursday dinner
  const today = '2026-10-28';

  it('offers only meals after the cook meal', () => {
    expect(afterCook('2026-10-29', 1, cook, today, slots)).toBe(false);
    expect(afterCook('2026-10-29', 3, cook, today, slots)).toBe(false); // the cook meal itself
    expect(afterCook('2026-10-28', 3, cook, today, slots)).toBe(false);
    expect(afterCook('2026-10-30', 1, cook, today, slots)).toBe(true);
    const earlier = { date: '2026-10-29', slot_id: 2 };
    expect(afterCook('2026-10-29', 3, earlier, today, slots)).toBe(true);
    expect(afterCook('2026-10-29', 2, earlier, today, slots)).toBe(false);
  });

  it('never offers a past day, even when the cooking was in the past', () => {
    const old = { date: '2026-10-26', slot_id: 1 };
    expect(afterCook('2026-10-27', 2, old, today, slots)).toBe(false);
    expect(afterCook('2026-10-28', 1, old, today, slots)).toBe(true);
  });

  it('knows which days have any meal to offer', () => {
    expect(dayAfterCook('2026-10-29', cook, today, slots)).toBe(false);
    expect(dayAfterCook('2026-10-30', cook, today, slots)).toBe(true);
    expect(dayAfterCook('2026-10-26', cook, today, slots)).toBe(false);
  });
});
