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
  nextFreeMeals,
  recipeMeta,
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
  servings: null,
  note: null,
  eating: null
});
const fruit: PlanItem = {
  id: 9,
  position: 9,
  kind: 'ingredient',
  recipe: null,
  tub_id: null,
  ingredient: { id: 1, name: 'Banana', removed: false },
  kept_name: null,
  servings: null,
  note: null,
  eating: null
};
const meal = (items: PlanItem[], kcal: number | null = null): PlanMeal => ({
  id: 1,
  date: '2026-10-19',
  slot_id: 1,
  status: 'planned',
  eater_login_ids: [],
  items,
  kcal
});

const note = (id: number, text: string): PlanItem => ({
  ...fruit,
  id,
  kind: 'note',
  ingredient: null,
  note: text
});

describe('a note in a meal (0.7 P1)', () => {
  it('is called by its text, and counted as a note', () => {
    expect(itemName(note(5, 'Eating out'))).toBe('Eating out');
    expect(mealName(meal([note(5, 'At Amma’s')]))).toBe('At Amma’s');
    expect(mealTotals(meal([note(5, 'Takeaway')]))).toBe('1 note');
    expect(mealTotals(meal([note(5, 'Takeaway'), note(6, 'Ice cream')]))).toBe('2 notes');
    expect(mealTotals(meal([note(5, 'Takeaway'), recipe(1, 'Dosa')]))).toBe('2 things');
  });
});

describe('a meal card’s words', () => {
  it('counts recipes and adds the kcal', () => {
    expect(mealTotals(meal([recipe(1, 'Dosa'), recipe(2, 'Chutney')], 590))).toBe(
      '2 recipes · 590 kcal each'
    );
    expect(mealTotals(meal([recipe(1, 'Dosa')]))).toBe('1 recipe');
  });

  it('a recipe card says the servings, the time and the kcal each (F116)', () => {
    const dosa = recipe(1, 'Dosa');
    dosa.servings = 4;
    dosa.recipe = { ...dosa.recipe!, time_minutes: 15, kcal: 123 };
    expect(recipeMeta(dosa)).toBe('serves 4 · 15\u00a0min · 123 kcal each');
    dosa.recipe = { ...dosa.recipe!, time_minutes: 745 };
    expect(recipeMeta(dosa)).toBe('serves 4 · 12\u00a0h\u00a025\u00a0min · 123 kcal each');
    // A meal with no Serves of its own shows the recipe's; a recipe without any, none.
    const older = recipe(3, 'Rasam');
    older.recipe = { ...older.recipe!, serves: 6, kcal: 80 };
    expect(recipeMeta(older)).toBe('serves 6 · 80 kcal each');
    older.servings = 4;
    expect(recipeMeta(older)).toBe('serves 4 · 80 kcal each');
    older.servings = null;
    older.recipe = { ...older.recipe!, serves: null };
    expect(recipeMeta(older)).toBe('80 kcal each');
    // Nothing known, nothing said; no Serves set on the meal, none shown.
    expect(recipeMeta(recipe(2, 'Chutney'))).toBe('');
  });

  it('says ingredients, or things when they are mixed', () => {
    expect(mealTotals(meal([fruit]))).toBe('1 ingredient');
    expect(mealTotals(meal([recipe(1, 'Dosa'), fruit], 230))).toBe('2 things · 230 kcal each');
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
          colour: null,
          portions: 1,
          portions_left: 0
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
      colour: 'green',
      portions: 1,
      portions_left: 0
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
    const meal = (id: number, items: PlanItem[] = []): PlanMeal => ({
      id,
      date: '2026-10-18',
      slot_id: 1,
      status: 'planned',
      eater_login_ids: [],
      items,
      kcal: null
    });
    expect(tubOf(plan, tubItem)).toEqual({ tub, batch });
    expect(tubOf(plan, fruit)).toBeNull();
    expect(cookBatchOfItem(plan, meal(50, [recipeItem]), recipeItem)).toEqual(batch);
    expect(cookBatchOfItem(plan, meal(51, [recipeItem]), recipeItem)).toBeNull();
    expect(cookBatchOfItem(plan, meal(50, [fruit]), fruit)).toBeNull();
    // Two copies of the cooked recipe: only the first (by position, then id) is the cooking.
    const copy: PlanItem = {
      ...recipeItem,
      id: recipeItem.id + 100,
      position: recipeItem.position + 1
    };
    const both = meal(50, [copy, recipeItem]);
    expect(cookBatchOfItem(plan, both, recipeItem)).toEqual(batch);
    expect(cookBatchOfItem(plan, both, copy)).toBeNull();
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

describe('nextFreeMeals (F65)', () => {
  const slots = [
    { id: 1, name: 'Breakfast', position: 1, enabled: true },
    { id: 2, name: 'Lunch', position: 2, enabled: true },
    { id: 3, name: 'Dinner', position: 3, enabled: true }
  ];
  const plan = {
    start: '2026-10-17',
    end: '2026-10-20',
    meals: [
      { date: '2026-10-18', slot_id: 3 },
      { date: '2026-10-19', slot_id: 1 }
    ],
    batch_cooks: [],
    tubs: []
  } as unknown as Plan;

  it('skips the filled meals and anything before the cooking', () => {
    const found = nextFreeMeals(plan, slots, { date: '2026-10-18', slot_id: 3 }, '2026-10-17', 3);
    expect(found).toEqual([
      { day: '2026-10-19', slotId: 2 },
      { day: '2026-10-19', slotId: 3 },
      { day: '2026-10-20', slotId: 1 }
    ]);
  });

  it('never offers a past day, and has nothing without a plan', () => {
    const found = nextFreeMeals(plan, slots, { date: '2026-10-17', slot_id: 1 }, '2026-10-19', 2);
    expect(found.every((f) => f.day >= '2026-10-19')).toBe(true);
    expect(nextFreeMeals(null, slots, { date: '2026-10-17', slot_id: 1 }, '2026-10-17')).toEqual(
      []
    );
  });
});

describe('nextFreeMeals stops at the tub’s use-by', () => {
  const slots = [
    { id: 1, name: 'Breakfast', position: 1, enabled: true },
    { id: 2, name: 'Lunch', position: 2, enabled: true }
  ];
  const plan = {
    start: '2026-10-17',
    end: '2026-10-25',
    meals: [],
    batch_cooks: [],
    tubs: []
  } as unknown as Plan;
  it('offers nothing past it, and nothing at all when no meal fits', () => {
    const cook = { date: '2026-10-17', slot_id: 1 };
    const found = nextFreeMeals(plan, slots, cook, '2026-10-17', 20, '2026-10-18');
    expect(found.every((f) => f.day <= '2026-10-18')).toBe(true);
    expect(found).toHaveLength(3);
    expect(nextFreeMeals(plan, slots, cook, '2026-10-20', 20, '2026-10-18')).toEqual([]);
  });
});
