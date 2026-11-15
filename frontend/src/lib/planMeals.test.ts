import { describe, expect, it } from 'vitest';
import type { MealSlot, Plan, PlanBatch, PlanItem, PlanMeal } from './client/plan';
import {
  afterCook,
  batchColour,
  dayAfterCook,
  eatenItems,
  colourOfBatch,
  cookBatchOfItem,
  itemName,
  leftName,
  mealColour,
  mealName,
  sessionTag,
  sessionsOn,
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
  eating: null,
  cooked: false
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
  eating: null,
  cooked: false
};
const meal = (items: PlanItem[], kcal: number | null = null): PlanMeal => ({
  id: 1,
  date: '2026-10-19',
  slot_id: 1,
  status: 'planned',
  eater_member_ids: [],
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
    expect(mealName(meal([note(5, 'At Tess’s')]))).toBe('At Tess’s');
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
    // A recipe that waits (M1): the active time and the wait, short.
    dosa.recipe = {
      ...dosa.recipe!,
      time_minutes: 25,
      wait: { kind: 'ferment', min_minutes: 480, max_minutes: 720, overnight: false }
    };
    expect(recipeMeta(dosa)).toBe('serves 4 · 25\u00a0min + 8\u00a0h – 12\u00a0h · 123 kcal each');
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
          member_id: null,
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
      member_id: 4,
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
      eater_member_ids: [],
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
    expect(whoseTub(tub, [{ member_id: 4, name: 'Wren', colour: null, portion_quarters: 4 }])).toBe(
      'Wren'
    );
    expect(whoseTub(tub, [])).toBeNull();
    // A removed owner: named with "(removed)" when the plan names them, not "Everyone" (Pe6).
    expect(whoseTub(tub, [], [{ member_id: 4, name: 'Wren' }])).toBe('Wren (removed)');
  });

  it('says how long a tub keeps', () => {
    expect(useByWords('2026-10-26', '2026-10-26')).toBe('use by today');
    expect(useByWords('2026-10-27', '2026-10-26')).toBe('use by tomorrow');
    expect(useByWords('2026-10-29', '2026-10-26')).toBe('3 days left');
    expect(useByWords('2026-10-25', '2026-10-26')).toBe('Date passed');
    expect(useByWords('2026-10-22', '2026-10-26')).toBe('Date passed');
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

describe('a meal cooked in parts (F162)', () => {
  it('names only the things not cooked yet for an answer or a move', () => {
    const soup = { ...recipe(2, 'Lentil soup'), cooked: true };
    const bread = recipe(1, 'Banana bread');
    expect(leftName(meal([soup, bread]))).toBe('Banana bread');
    expect(leftName(meal([bread, recipe(3, 'Raita'), soup]))).toBe('Banana bread and 1 more');
    expect(leftName(meal([{ ...bread, cooked: true }]))).toBe('Banana bread');
  });
});

describe('Batch cook sessions on the plan (B2)', () => {
  const batch = (over: Partial<PlanBatch>): PlanBatch => ({
    id: 1,
    recipe_id: 1,
    recipe_name: 'Sambar',
    cook_meal_id: null,
    cooked_on: '2026-11-15',
    tub_count: 3,
    pattern: 'dinners',
    prep_note: null,
    colour: 'blue',
    portions: 4,
    portions_left: 0,
    session_id: null,
    ...over
  });

  it('a batch made in a session says Batch · and its cook day; a plain one says nothing', () => {
    expect(sessionTag(batch({ session_id: 7 }))).toBe('Batch · Sun');
    expect(sessionTag(batch({ session_id: null }))).toBeNull();
    expect(sessionTag(undefined)).toBeNull();
  });

  it('finds the sessions cooked on a day', () => {
    const session = (id: number, cook_day: string) => ({
      id,
      cook_day,
      together_minutes: null,
      one_by_one_minutes: null,
      start_day: null,
      start_time: null
    });
    const plan = {
      start: '',
      end: '',
      meals: [],
      batch_cooks: [],
      tubs: [],
      batch_sessions: [session(1, '2026-11-15'), session(2, '2026-11-16')]
    };
    expect(sessionsOn(plan, '2026-11-15').map((s) => s.id)).toEqual([1]);
    expect(sessionsOn(plan, '2026-11-20')).toEqual([]);
    expect(sessionsOn(null, '2026-11-15')).toEqual([]);
  });
});

describe('what is eaten at a meal after a session’s Cooked it (F233)', () => {
  const batchOf = (recipeId: number, session: number | null): PlanBatch => ({
    id: recipeId,
    recipe_id: recipeId,
    recipe_name: `Dish ${recipeId}`,
    cook_meal_id: 1,
    cooked_on: '2026-10-19',
    tub_count: 2,
    pattern: 'dinners',
    prep_note: null,
    colour: 'blue',
    portions: 3,
    portions_left: 0,
    session_id: session
  });
  const planOf = (batches: PlanBatch[]): Plan => ({
    start: '',
    end: '',
    meals: [],
    batch_cooks: batches,
    tubs: []
  });
  const cooked = (item: PlanItem): PlanItem => ({ ...item, cooked: true });
  const tub = (): PlanItem => ({ ...recipe(7, 'x'), kind: 'tub', recipe: null, tub_id: 70 });

  it('leaves out the recipes the session cooked, once they are cooked, and keeps the tub', () => {
    const items = [tub(), cooked(recipe(1, 'Paneer')), cooked(recipe(2, 'Dal'))];
    const plan = planOf([batchOf(1, 5), batchOf(2, 5)]);
    expect(eatenItems(meal(items), plan).map((i) => i.id)).toEqual([7]);
  });

  it('the Plan’s "N things" counts only what is eaten there, with the server’s kcal', () => {
    const items = [tub(), cooked(recipe(1, 'Paneer')), cooked(recipe(2, 'Dal'))];
    const plan = planOf([batchOf(1, 5), batchOf(2, 5)]);
    expect(mealTotals(meal(items, 400), plan)).toBe('1 thing · 400 kcal each');
    expect(mealTotals(meal(items, 1600))).toBe('3 things · 1600 kcal each'); // no plan: as before
  });

  it('keeps them before Cooked it', () => {
    const items = [tub(), recipe(1, 'Paneer'), recipe(2, 'Dal')];
    const plan = planOf([batchOf(1, 5), batchOf(2, 5)]);
    expect(eatenItems(meal(items), plan)).toHaveLength(3);
  });

  it('keeps all of them when nothing else is eaten there', () => {
    const items = [cooked(recipe(1, 'Paneer')), cooked(recipe(2, 'Dal'))];
    const plan = planOf([batchOf(1, 5), batchOf(2, 5)]);
    expect(eatenItems(meal(items), plan)).toHaveLength(2);
  });

  it('keeps a Cook once recipe outside a session', () => {
    const items = [tub(), cooked(recipe(1, 'Paneer'))];
    expect(eatenItems(meal(items), planOf([batchOf(1, null)]))).toHaveLength(2);
  });

  it('keeps a second copy of the same recipe: only the cooking is left out', () => {
    const items = [cooked(recipe(1, 'Paneer')), recipe(3, 'Paneer'), tub()];
    items[1]!.recipe = { ...items[1]!.recipe!, id: 1 };
    expect(eatenItems(meal(items), planOf([batchOf(1, 5)])).map((i) => i.id)).toEqual([3, 7]);
  });
});
