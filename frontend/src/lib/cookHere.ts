// "Cook once here…" (F52): the recipe is planned in the meal, and Cook once opens for it. What
// Cook once needs (the meal's day and meal, the item and its recipe) is all in what the add
// answered and what was picked, so nothing is fetched or searched for again.

import type { PlanItem, PlanMeal, PlanWrite } from './client/plan.js';

/** The meal and item Cook once opens for, or null when the add's answer has no meal or item. */
export function cookTargetOf(
  write: Pick<PlanWrite, 'meal_id' | 'item_id'>,
  day: string,
  slotId: number,
  recipe: { id: number; name: string }
): { meal: PlanMeal; item: PlanItem } | null {
  if (write.meal_id === null || write.item_id === null) return null;
  const item: PlanItem = {
    id: write.item_id,
    position: 0,
    kind: 'recipe',
    recipe: {
      id: recipe.id,
      name: recipe.name,
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
  };
  const meal: PlanMeal = {
    id: write.meal_id,
    date: day,
    slot_id: slotId,
    status: 'planned',
    items: [item],
    kcal: null,
    eater_login_ids: []
  };
  return { meal, item };
}
