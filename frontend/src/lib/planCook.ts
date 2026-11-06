// The Plan's Cook view (spec "The Plan redesign, 0.7.0"): cooking by day. Fresh meals and
// batches, how much (× scale, makes N, eat N now, where each tub goes, spare tubs), prep ahead
// and, from the stock check, what is still to buy. Worked out from the plan the server sent.
// Pure, so it is tested on its own (planCook.test.ts).

import type { RecipeStock } from './client/recipes';
import type { MealSlot, Plan, PlanBatch, PlanItem, PlanMeal } from './client/plan';
import { dayShort } from './planDates';
import { cookBatchOfItem, itemName } from './planMeals';

export interface CookEntry {
  key: string;
  meal: PlanMeal;
  item: PlanItem;
  slotName: string;
  name: string;
  /** The recipe to cook; null when it was deleted for good (nothing to start). */
  recipeId: number | null;
  batch: PlanBatch | null;
  /** Fresh: how many people it is for; null when unknown. */
  serves: number | null;
  minutes: number | null;
  /** A batch: how many times the recipe, as "1.5"; null when the recipe has no Serves. */
  scale: string | null;
  /** A batch: its portions. */
  makes: number | null;
  /** A batch: portions eaten on the cook day. */
  eatNow: number;
  /** A batch: where each tub goes ("Mon lunch"), soonest first. */
  tubs: string[];
  /** A batch: portions not in any meal yet. */
  spare: number;
  prep: string | null;
  /** The meal was already cooked: nothing to start. */
  cooked: boolean;
}

export interface CookDay {
  day: string;
  entries: CookEntry[];
  /** Time at the stove for what is known; null when no recipe has a time. */
  minutes: number | null;
}

/** "1.5", "2", "0.75": a scale with up to two decimals and no trailing zeros. */
export function scaleWords(scale: number): string {
  return String(Math.round(scale * 100) / 100);
}

function tubPlaces(plan: Plan, slots: MealSlot[], batch: PlanBatch): string[] {
  const places: { date: string; at: number; words: string }[] = [];
  for (const tub of plan.tubs.filter((t) => t.batch_id === batch.id)) {
    const meal = plan.meals.find((m) => m.items.some((i) => i.tub_id === tub.id));
    if (!meal) continue;
    const slot = slots.find((s) => s.id === meal.slot_id);
    places.push({
      date: meal.date,
      at: slot?.position ?? 0,
      words: `${dayShort(meal.date)} ${(slot?.name ?? 'meal').toLowerCase()}`
    });
  }
  return places.sort((a, b) => a.date.localeCompare(b.date) || a.at - b.at).map((p) => p.words);
}

/** The recipes to cook on each day of `days` that has any, in meal order. */
export function cookDays(
  plan: Plan | null,
  slotsOn: MealSlot[],
  days: string[],
  allSlots: MealSlot[] = slotsOn
): CookDay[] {
  if (!plan) return [];
  const out: CookDay[] = [];
  for (const day of days) {
    const entries: CookEntry[] = [];
    for (const slot of slotsOn) {
      const meal = plan.meals.find((m) => m.date === day && m.slot_id === slot.id);
      if (!meal || (meal.status !== 'planned' && meal.status !== 'cooked')) continue;
      for (const item of meal.items) {
        if (item.kind !== 'recipe') continue;
        const batch = cookBatchOfItem(plan, meal, item);
        const recipe = item.recipe;
        const serves = recipe?.serves ?? null;
        entries.push({
          key: `${meal.id}-${item.id}`,
          meal,
          item,
          slotName: slot.name,
          name: itemName(item, plan),
          recipeId: recipe && !recipe.removed ? recipe.id : null,
          batch,
          serves: batch ? null : item.eating,
          minutes: recipe?.time_minutes ?? null,
          scale: batch && serves ? scaleWords(batch.portions / serves) : null,
          makes: batch ? batch.portions : null,
          eatNow: batch ? Math.max(0, batch.portions - batch.tub_count) : 0,
          tubs: batch ? tubPlaces(plan, allSlots, batch) : [],
          spare: batch ? batch.portions_left : 0,
          prep: batch?.prep_note ?? null,
          cooked: item.cooked
        });
      }
    }
    if (!entries.length) continue;
    const times = entries.flatMap((e) => (e.minutes === null ? [] : [e.minutes]));
    out.push({
      day,
      entries,
      minutes: times.length ? times.reduce((a, b) => a + b, 0) : null
    });
  }
  return out;
}

/** The ingredients a recipe still needs bought (short or missing), once each, as written. */
export function stillToBuy(stock: RecipeStock): string[] {
  const names: string[] = [];
  for (const line of stock.lines) {
    if (line.state !== 'short' && line.state !== 'missing') continue;
    if (!names.includes(line.food.name)) names.push(line.food.name);
  }
  return names;
}
