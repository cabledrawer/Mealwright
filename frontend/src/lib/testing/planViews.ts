// A small plan for the Eat and Cook views' tests (not shipped: only the test files import it).
// Sat 17 Oct 2026: Pongal for breakfast. Sun 18: Veg biryani cooked as a batch for dinner (6
// portions: 4 tubs and 2 now), tubs in Mon lunch, Mon dinner and Tue lunch (two), 2 portions left.

import type {
  MealSlot,
  Person,
  Plan,
  PlanBatch,
  PlanItem,
  PlanMeal,
  PlanTub
} from '../client/plan';

export const SLOTS: MealSlot[] = [
  { id: 1, name: 'Breakfast', position: 1, enabled: true },
  { id: 2, name: 'Lunch', position: 2, enabled: true },
  { id: 3, name: 'Dinner', position: 3, enabled: true }
];

export const PEOPLE: Person[] = [
  { login_id: 10, name: 'Tess' },
  { login_id: 11, name: 'Alex' }
];

export const recipeItem = (
  id: number,
  recipeId: number,
  name: string,
  extra: Partial<PlanItem> = {}
): PlanItem => ({
  id,
  position: id,
  kind: 'recipe',
  recipe: {
    id: recipeId,
    name,
    removed: false,
    photo_url: null,
    time_minutes: 30,
    kcal: null,
    serves: 2
  },
  tub_id: null,
  ingredient: null,
  kept_name: null,
  servings: null,
  note: null,
  eating: 2,
  cooked: false,
  ...extra
});

export const tubItem = (id: number, tubId: number): PlanItem => ({
  id,
  position: id,
  kind: 'tub',
  recipe: null,
  tub_id: tubId,
  ingredient: null,
  kept_name: null,
  servings: null,
  note: null,
  eating: null,
  cooked: false
});

export const noteItem = (id: number, text: string): PlanItem => ({
  id,
  position: id,
  kind: 'note',
  recipe: null,
  tub_id: null,
  ingredient: null,
  kept_name: null,
  servings: null,
  note: text,
  eating: null,
  cooked: false
});

export const mealOf = (
  id: number,
  date: string,
  slot_id: number,
  items: PlanItem[],
  extra: Partial<PlanMeal> = {}
): PlanMeal => ({
  id,
  date,
  slot_id,
  status: 'planned',
  items,
  kcal: null,
  eater_login_ids: [],
  ...extra
});

export const BATCH: PlanBatch = {
  id: 1,
  recipe_id: 7,
  recipe_name: 'Veg biryani',
  cook_meal_id: 3,
  cooked_on: '2026-10-18',
  tub_count: 4,
  pattern: 'pick',
  prep_note: 'Soak the rice',
  colour: 'green',
  portions: 6,
  portions_left: 2
};

const tub = (id: number, number: number, who: number | null): PlanTub => ({
  id,
  batch_id: 1,
  amount_quarters: 4,
  number,
  place_id: null,
  place_kind: 'fridge',
  member_login_id: who,
  use_by: '2026-10-21'
});

export function samplePlan(): Plan {
  return {
    start: '2026-10-17',
    end: '2026-10-23',
    meals: [
      mealOf(1, '2026-10-17', 1, [recipeItem(1, 5, 'Pongal')], { kcal: 400 }),
      mealOf(3, '2026-10-18', 3, [recipeItem(3, 7, 'Veg biryani', { eating: 2 })], {
        kcal: 700,
        eater_login_ids: [10, 11]
      }),
      mealOf(4, '2026-10-19', 2, [tubItem(4, 21)]),
      mealOf(5, '2026-10-19', 3, [tubItem(5, 22)], { eater_login_ids: [11] }),
      mealOf(6, '2026-10-20', 2, [tubItem(6, 23), tubItem(7, 24)])
    ],
    batch_cooks: [BATCH],
    tubs: [tub(21, 1, 10), tub(22, 2, null), tub(23, 3, 10), tub(24, 4, 11)]
  };
}
