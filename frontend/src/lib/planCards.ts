// The cards of one meal in the Plan's Both week (spec "The Plan redesign, 0.7.0"): COOK and EAT
// are separate cards. A batch's cook-day meal is a COOK card plus an EAT card; a tub is an EAT
// card; a fresh recipe has a pan on it. Worked out from the plan the server sent. Pure, so it is
// tested on its own (planCards.test.ts).

import type { MealSlot, Person, Plan, PlanBatch, PlanItem, PlanMeal } from './client/plan';
import { eaterNames } from './planEat';
import {
  colourOfBatch,
  cookBatchOfItem,
  itemName,
  recipeMeta,
  sessionTag,
  tubOf,
  whoseTub
} from './planMeals';
import { timeWords } from './timeWords';

export interface WeekCard {
  key: string;
  item: PlanItem;
  /** COOK (blue, pan), EAT (batch colour, plate), a fresh recipe (pan), or anything else. */
  role: 'cook' | 'eat' | 'fresh' | 'plain';
  /** The small line above the name: "Cook · 1 h", "Eat", "Eat · tub 2 of 4". */
  eyebrow: string | null;
  /** The name for the screen reader (and the menu): "Chana masala tub". */
  name: string;
  /** The name shown on the card. */
  shown: string;
  /** The small line under the name. */
  meta: string | null;
  /** A second small line (the batch's prep note). */
  prep: string | null;
  /** People's names on an EAT card. */
  who: string[];
  /** The batch colour (1 to 6) of a COOK dot or an EAT card. */
  colour: number | null;
  /** An EAT card of a tub that falls before its batch is cooked (amber, "Before the cook day"). */
  before: boolean;
  /** The batch a COOK card is for. */
  batch: PlanBatch | null;
  /** "Batch · Sun" when it was made in a Batch cook session (B2). */
  session: string | null;
}

/** Where a batch is cooked: its cook meal when the plan holds it, else its cook day alone. */
export function cookPlace(plan: Plan, batch: PlanBatch): { date: string; slot_id: number | null } {
  const meal =
    batch.cook_meal_id === null ? null : plan.meals.find((m) => m.id === batch.cook_meal_id);
  return meal
    ? { date: meal.date, slot_id: meal.slot_id }
    : { date: batch.cooked_on, slot_id: null };
}

/**
 * Whether a day and meal come before the cooking (or are the cook meal itself). With the cook
 * day only (the cook meal is outside the weeks fetched) the meals of that day are not judged.
 */
export function beforeCook(
  day: string,
  slotId: number,
  cook: { date: string; slot_id: number | null },
  slots: MealSlot[]
): boolean {
  if (day < cook.date) return true;
  if (day > cook.date || cook.slot_id === null) return false;
  const order = slots.map((s) => s.id);
  const [at, cookAt] = [order.indexOf(slotId), order.indexOf(cook.slot_id)];
  return at >= 0 && cookAt >= 0 && at <= cookAt;
}

/** "Makes 6 · 4 tubs". */
export function makesWords(batch: PlanBatch): string {
  const tubs = `${batch.tub_count} ${batch.tub_count === 1 ? 'tub' : 'tubs'}`;
  return `Makes ${batch.portions} · ${tubs}`;
}

export function weekCards(
  plan: Plan,
  meal: PlanMeal,
  people: Person[],
  slots: MealSlot[]
): WeekCard[] {
  const cards: WeekCard[] = [];
  const base = {
    prep: null,
    who: [],
    colour: null,
    before: false,
    batch: null,
    meta: null,
    session: null
  };
  for (const item of meal.items) {
    const name = itemName(item, plan);
    const found = tubOf(plan, item);
    if (found) {
      const { tub, batch } = found;
      const last = tub.number === batch.tub_count && batch.tub_count > 1;
      const who = whoseTub(tub, people, plan.removed_people);
      cards.push({
        ...base,
        key: `e${item.id}`,
        item,
        role: 'eat',
        eyebrow: last ? 'Eat · last tub' : `Eat · tub ${tub.number} of ${batch.tub_count}`,
        name,
        shown: batch.recipe_name,
        who: who ? [who] : [],
        colour: colourOfBatch(batch),
        before: beforeCook(meal.date, meal.slot_id, cookPlace(plan, batch), slots),
        session: sessionTag(batch)
      });
      continue;
    }
    const batch = cookBatchOfItem(plan, meal, item);
    if (batch) {
      const minutes = item.recipe?.time_minutes;
      cards.push({
        ...base,
        key: `c${item.id}`,
        item,
        role: 'cook',
        eyebrow: minutes ? `Cook · ${timeWords(minutes)}` : 'Cook',
        name,
        shown: name,
        meta: makesWords(batch),
        prep: batch.prep_note,
        colour: colourOfBatch(batch),
        batch,
        session: sessionTag(batch)
      });
      cards.push({
        ...base,
        key: `e${item.id}`,
        item,
        role: 'eat',
        eyebrow: 'Eat',
        name,
        shown: name,
        who: eaterNames(meal, people, plan.removed_people),
        colour: colourOfBatch(batch),
        session: sessionTag(batch)
      });
      continue;
    }
    cards.push({
      ...base,
      key: `i${item.id}`,
      item,
      role: item.kind === 'recipe' ? 'fresh' : 'plain',
      eyebrow: null,
      name,
      shown: name,
      meta: item.kind === 'note' ? 'Note' : recipeMeta(item) || null
    });
  }
  return cards;
}
