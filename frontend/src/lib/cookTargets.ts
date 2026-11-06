// What "Cooked it" is about, worked out from the plan: one tab for each recipe in a meal. A
// recipe that a Cook once batch was made from is cooked as the batch (once, for the cook day and
// its tubs); the others are cooked together as the meal. Pure, so it is tested without a screen.

import type { Plan, PlanBatch, PlanItem, PlanMeal } from './client/plan';
import type { CookPart, CookTarget } from './cookReview.svelte';
import { cookBatchOfItem, itemName } from './planMeals';

/** A recipe of a meal that can be cooked (a tub or a plain ingredient takes nothing). */
/** A recipe taken out of the recipe list can't be cooked, so the review leaves it out (F158). */
export const isCookable = (item: PlanItem) =>
  item.kind === 'recipe' && !!item.recipe && !item.recipe.removed;

function partOf(plan: Plan | null, meal: PlanMeal, item: PlanItem): CookPart {
  const batch: PlanBatch | null = cookBatchOfItem(plan, meal, item);
  const name = itemName(item, plan);
  return batch
    ? { itemId: null, batchId: batch.id, name }
    : { itemId: item.id, batchId: null, name };
}

/** "A", "A and B", "A, B and C". */
export function joinNames(names: string[]): string {
  return names.length <= 1
    ? (names[0] ?? '')
    : `${names.slice(0, -1).join(', ')} and ${names[names.length - 1]}`;
}

/** The Plan panel's note for a meal with cooked recipes in it (F163, cabledrawer 6 Nov). */
export function cookedStaysNote(names: string[]): string {
  const one = names.length === 1;
  return `${joinNames(names)} ${one ? 'was' : 'were'} cooked. Undo ${one ? 'its' : 'their'} Cooked it to move or remove ${one ? 'it' : 'them'}.`;
}

/** "Cooked Sambar", "Cooked Sambar and Rasam": the title, and the toast's start. */
export function cookedTitle(names: string[]): string {
  if (names.length === 0) return 'Cooked it';
  if (names.length === 1) return `Cooked ${names[0]}`;
  return `Cooked ${names.slice(0, -1).join(', ')} and ${names[names.length - 1]}`;
}

/**
 * The whole meal, or just one of its recipes (`only`, from the Plan's menu for one thing in it).
 * A meal with no recipe has no parts: it can still be answered, with nothing to take.
 */
export function cookTarget(
  plan: Plan | null,
  meal: PlanMeal,
  subtitle: string,
  only: PlanItem | null = null
): CookTarget {
  // A recipe cooked already is not reviewed again (F157): a second open reviews what is left.
  const items = (only ? [only] : meal.items).filter((i) => isCookable(i) && !i.cooked);
  const parts = items.map((item) => partOf(plan, meal, item));
  return {
    title: cookedTitle(parts.length ? parts.map((p) => p.name) : everyName(plan, meal)),
    subtitle,
    mealId: meal.id,
    parts
  };
}

/** A meal with no recipe to cook (tubs, ingredients): its title names every thing in it. */
function everyName(plan: Plan | null, meal: PlanMeal): string[] {
  const names = meal.items.filter((i) => i.kind !== 'note').map((i) => itemName(i, plan));
  return names.length ? names : ['it'];
}
