// What "Cooked it" is about, worked out from the plan: one tab for each recipe in a meal. A
// recipe that a Cook once batch was made from is cooked as the batch (once, for the cook day and
// its tubs); the others are cooked together as the meal. Pure, so it is tested without a screen.

import type { Plan, PlanBatch, PlanItem, PlanMeal } from './client/plan';
import type { CookPart, CookTarget } from './cookReview.svelte';
import { cookBatchOfItem, itemName } from './planMeals';

/** A recipe of a meal that can be cooked (a tub or a plain ingredient takes nothing). */
export const isCookable = (item: PlanItem) => item.kind === 'recipe';

function partOf(plan: Plan | null, meal: PlanMeal, item: PlanItem): CookPart {
  const batch: PlanBatch | null = cookBatchOfItem(plan, meal, item);
  const name = itemName(item, plan);
  return batch
    ? { itemId: null, batchId: batch.id, name }
    : { itemId: item.id, batchId: null, name };
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
  const items = (only ? [only] : meal.items).filter(isCookable);
  const parts = items.map((item) => partOf(plan, meal, item));
  return {
    title: cookedTitle(parts.length ? parts.map((p) => p.name) : [mealNameOf(plan, meal)]),
    subtitle,
    mealId: meal.id,
    parts
  };
}

function mealNameOf(plan: Plan | null, meal: PlanMeal): string {
  const first = meal.items[0];
  return first ? itemName(first, plan) : 'it';
}
