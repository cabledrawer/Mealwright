// What a meal card says, worked out from the plan the server sent. Pure, so it is tested
// on its own (planMeals.test.ts).

import type { MealSlot, Plan, PlanItem, PlanMeal } from './client/plan';

/** A thing in a meal, in words: the recipe's name, the ingredient's name, or the tub's. */
export function itemName(item: PlanItem, plan: Plan | null = null): string {
  if (item.recipe) return item.recipe.name;
  if (item.ingredient) return item.ingredient.name;
  if (item.kept_name) return item.kept_name; // deleted for good: past meals still say what it was
  const tub = plan?.tubs.find((t) => t.id === item.tub_id);
  const batch = plan?.batch_cooks.find((b) => b.id === tub?.batch_id);
  return batch ? `${batch.recipe_name} tub` : 'Tub';
}

/** "Tub 2 of 4", for a tub in a meal; null for anything else. */
export function tubWords(item: PlanItem, plan: Plan): string | null {
  const tub = plan.tubs.find((t) => t.id === item.tub_id);
  const batch = plan.batch_cooks.find((b) => b.id === tub?.batch_id);
  return tub && batch ? `Tub ${tub.number} of ${batch.tub_count}` : null;
}

/** "2 recipes · 590 kcal", "1 ingredient", "3 things · 80 kcal". Proposed, for cabledrawer. */
export function mealTotals(meal: PlanMeal): string {
  const n = meal.items.length;
  const all = (kind: PlanItem['kind']) => meal.items.every((i) => i.kind === kind);
  const noun = all('recipe')
    ? n === 1
      ? 'recipe'
      : 'recipes'
    : all('ingredient')
      ? n === 1
        ? 'ingredient'
        : 'ingredients'
      : n === 1
        ? 'thing'
        : 'things';
  const kcal = meal.kcal === null ? '' : ` · ${meal.kcal} kcal`;
  return `${n} ${noun}${kcal}`;
}

/** A meal's name for the screen reader and the toast: its first thing, "and 1 more". */
export function mealName(meal: PlanMeal, plan: Plan | null = null): string {
  const first = meal.items[0];
  if (!first) return 'Empty meal';
  const name = itemName(first, plan);
  return meal.items.length === 1 ? name : `${name} and ${meal.items.length - 1} more`;
}

/** The meals of one day and slot (there is at most one). */
export function mealAt(plan: Plan | null, day: string, slotId: number): PlanMeal | null {
  return plan?.meals.find((m) => m.date === day && m.slot_id === slotId) ?? null;
}

/** The slots that are on, in order. */
export const slotsOn = (slots: MealSlot[]) =>
  slots.filter((s) => s.enabled).sort((a, b) => a.position - b.position || a.id - b.id);

/** The batch cooked on a day, if any (its cook day). */
export function cookedOn(plan: Plan | null, day: string) {
  return plan?.batch_cooks.filter((b) => b.cooked_on === day) ?? [];
}

/** Which batch a meal belongs to, by its tubs: for the colour in the Month view. */
export function batchOfMeal(plan: Plan | null, meal: PlanMeal): number | null {
  for (const item of meal.items) {
    const tub = plan?.tubs.find((t) => t.id === item.tub_id);
    if (tub) return tub.batch_id;
  }
  return null;
}

/** How many batch colours the design has (tokens --batch-1 … --batch-6). */
export const BATCH_COLOURS = 6;

/** One colour per batch: the same batch always gets the same colour. */
export const batchColour = (batchId: number) => ((batchId - 1) % BATCH_COLOURS) + 1;
