// The Plan's Eat view (spec "The Plan redesign, 0.7.0"): what each person eats at each meal and
// where it comes from ("2 tubs from Thu · Tess, Wren"). Worked out from the plan the server
// sent, with no new request. Pure, so it is tested on its own (planEat.test.ts).

import type { MealSlot, Person, Plan, PlanBatch, PlanMeal } from './client/plan';
import { dayShort } from './planDates';
import { colourOfBatch, cookBatchOfItem, cookedOn, itemName, tubOf, whoseTub } from './planMeals';

export interface EatRow {
  key: string;
  /** What is eaten: a recipe, an ingredient, a note, or a batch's tub. */
  name: string;
  /** Where it comes from, and for whom: "2 tubs from Thu · Tess, Wren". */
  source: string | null;
  /** "fresh" on its own; a batch's cook-day meal or tub carries the batch colour instead. */
  fresh: boolean;
  /** The batch colour (1 to 6), or null. */
  colour: number | null;
  /** A tub (soft colour) or the cook-day meal (solid colour). */
  solid: boolean;
}

export interface EatMeal {
  slot: MealSlot;
  meal: PlanMeal | null;
  rows: EatRow[];
}

export interface EatDay {
  day: string;
  meals: EatMeal[];
  /** One serving of every meal added up; null when none has kcal. */
  kcal: number | null;
  /** Whether a batch is cooked on this day (the "You cook today →" link). */
  cooks: boolean;
}

/** The people ticked for a meal; empty when it is for everyone (nothing to say). */
export function eaterNames(meal: PlanMeal, people: Person[]): string[] {
  if (meal.eater_login_ids.length === 0) return [];
  return people.filter((p) => meal.eater_login_ids.includes(p.login_id)).map((p) => p.name);
}

const joined = (parts: (string | null)[]) => parts.filter((p) => p).join(' · ');

/** The rows of one meal: one for each recipe, ingredient or note, one for each batch's tubs. */
export function eatRows(plan: Plan, meal: PlanMeal, people: Person[]): EatRow[] {
  const rows: EatRow[] = [];
  const eaters = eaterNames(meal, people);
  const tubGroups = new Map<number, { batch: PlanBatch; whose: (string | null)[]; at: number }>();
  for (const item of meal.items) {
    if (item.kind === 'tub') {
      const found = tubOf(plan, item);
      if (found) {
        const group = tubGroups.get(found.batch.id);
        if (group) group.whose.push(whoseTub(found.tub, people));
        else {
          tubGroups.set(found.batch.id, {
            batch: found.batch,
            whose: [whoseTub(found.tub, people)],
            at: rows.length
          });
          rows.push({
            key: `t${found.batch.id}`,
            name: '',
            source: null,
            fresh: false,
            colour: null,
            solid: false
          });
        }
        continue;
      }
    }
    const batch = cookBatchOfItem(plan, meal, item);
    if (batch) {
      rows.push({
        key: `i${item.id}`,
        name: itemName(item, plan),
        source: joined(['Freshly made', eaters.join(', ') || null]),
        fresh: false,
        colour: colourOfBatch(batch),
        solid: true
      });
    } else {
      rows.push({
        key: `i${item.id}`,
        name: itemName(item, plan),
        source: eaters.length && item.kind === 'recipe' ? eaters.join(', ') : null,
        fresh: item.kind === 'recipe',
        colour: null,
        solid: false
      });
    }
  }
  for (const [batchId, group] of tubGroups) {
    const row = rows[group.at]!;
    const n = group.whose.length;
    const named = [...new Set(group.whose.filter((w): w is string => !!w))];
    const who = named.length ? named : eaters;
    row.name = group.batch.recipe_name;
    row.source = joined([
      `${n === 1 ? 'Tub' : `${n} tubs`} from ${dayShort(group.batch.cooked_on)}`,
      who.join(', ') || null
    ]);
    row.colour = colourOfBatch(group.batch);
    row.key = `t${batchId}`;
  }
  return rows;
}

/** Every day on show, with its meals that are on (empty ones too, so they can be added to). */
export function eatDays(
  plan: Plan | null,
  slotsOn: MealSlot[],
  people: Person[],
  days: string[]
): EatDay[] {
  if (!plan) return [];
  return days.map((day) => {
    const meals = slotsOn.map((slot) => {
      const meal = plan.meals.find((m) => m.date === day && m.slot_id === slot.id) ?? null;
      return { slot, meal, rows: meal ? eatRows(plan, meal, people) : [] };
    });
    const kcals = meals.flatMap((m) => (m.meal?.kcal != null ? [m.meal.kcal] : []));
    return {
      day,
      meals,
      kcal: kcals.length ? kcals.reduce((a, b) => a + b, 0) : null,
      cooks: cookedOn(plan, day).length > 0
    };
  });
}
