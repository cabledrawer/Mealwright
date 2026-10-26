// What a meal card says, worked out from the plan the server sent. Pure, so it is tested
// on its own (planMeals.test.ts).

import type { MealSlot, Person, Plan, PlanBatch, PlanItem, PlanMeal, PlanTub } from './client/plan';

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

/** The tub a meal item is, and the batch it came from. */
export function tubOf(
  plan: Plan | null,
  item: PlanItem
): { tub: PlanTub; batch: PlanBatch } | null {
  const tub = plan?.tubs.find((t) => t.id === item.tub_id);
  const batch = plan?.batch_cooks.find((b) => b.id === tub?.batch_id);
  return tub && batch ? { tub, batch } : null;
}

/** The batch cook that was cooked for this meal (its cook day), if any. */
export const cookBatchOf = (plan: Plan | null, meal: PlanMeal): PlanBatch | null =>
  plan?.batch_cooks.find((b) => b.cook_meal_id === meal.id) ?? null;

/** The batch cook that a recipe item was cooked for (its meal is the batch's cook meal). */
export const cookBatchOfItem = (
  plan: Plan | null,
  meal: PlanMeal,
  item: PlanItem
): PlanBatch | null =>
  item.kind !== 'recipe'
    ? null
    : (plan?.batch_cooks.find(
        (b) =>
          b.cook_meal_id === meal.id &&
          (item.recipe ? b.recipe_id === item.recipe.id : b.recipe_name === item.kept_name)
      ) ?? null);

/** The names of the batch colours, in the order of the design's tokens --batch-1 … --batch-6. */
export const BATCH_PALETTE = ['purple', 'amber', 'green', 'blue', 'rose', 'teal'];

/** How many batch colours the design has (tokens --batch-1 … --batch-6). */
export const BATCH_COLOURS = 6;

/** One colour per batch: the same batch always gets the same colour. */
export const batchColour = (batchId: number) => ((batchId - 1) % BATCH_COLOURS) + 1;

/** The design's colour number (1 to 6) for a batch: its palette name, else by its id. */
export function colourOfBatch(batch: { id: number; colour: string | null }): number {
  const at = batch.colour ? BATCH_PALETTE.indexOf(batch.colour) : -1;
  return at >= 0 ? at + 1 : batchColour(batch.id);
}

/** The colour number of a meal that holds a tub or was cooked for a batch, else null. */
export function mealColour(plan: Plan | null, meal: PlanMeal): number | null {
  const id = batchOfMeal(plan, meal);
  const batch =
    (id === null ? cookBatchOf(plan, meal) : plan?.batch_cooks.find((b) => b.id === id)) ?? null;
  return batch ? colourOfBatch(batch) : null;
}

/** Whose a tub is, in words: the person's name, or null when it is nobody's in particular. */
export const whoseTub = (tub: PlanTub, people: Person[]): string | null =>
  people.find((p) => p.login_id === tub.member_login_id)?.name ?? null;

/** "3 days left", "use by today", "use by yesterday": for a tub's use-by day. */
export function useByWords(useBy: string, today: string): string {
  const days = Math.round((Date.parse(useBy) - Date.parse(today)) / 86_400_000);
  if (days === 0) return 'use by today';
  if (days === 1) return 'use by tomorrow';
  if (days < 0) return days === -1 ? 'use by yesterday' : `${-days} days past use-by`;
  return `${days} days left`;
}
