// What a meal card says, worked out from the plan the server sent. Pure, so it is tested
// on its own (planMeals.test.ts).

import type { MealSlot, Person, Plan, PlanBatch, PlanItem, PlanMeal, PlanTub } from './client/plan';
import { dayShort } from './planDates';
import { timePlusWait } from './timeWords';

/** A thing in a meal, in words: the recipe's name, the ingredient's name, or the tub's. */
export function itemName(item: PlanItem, plan: Plan | null = null): string {
  if (item.note) return item.note; // "Eating out", "At Amma’s"
  if (item.recipe) return item.recipe.name;
  if (item.ingredient) return item.ingredient.name;
  if (item.kept_name) return item.kept_name; // deleted for good: past meals still say what it was
  const tub = plan?.tubs.find((t) => t.id === item.tub_id);
  const batch = plan?.batch_cooks.find((b) => b.id === tub?.batch_id);
  return batch ? `${batch.recipe_name} tub` : 'Tub';
}

/**
 * What is eaten at a meal (F233, cabledrawer 12 Nov): once a Batch cook session's Cooked it is done,
 * the recipes it cooked in its cook-day meal are not part of what is eaten there, so the meal's
 * name leaves them out (the server leaves their kcal out). A meal with nothing else in it keeps
 * them. Before Cooked it, and for a Cook once outside a session, every item counts.
 */
export function eatenItems(meal: PlanMeal, plan: Plan | null): PlanItem[] {
  if (!plan) return meal.items;
  const cooked = new Set<number>();
  for (const batch of plan.batch_cooks) {
    if (batch.session_id == null || batch.cook_meal_id !== meal.id) continue;
    // The cooking is the first copy of the recipe in the meal (as the server picks it).
    const cooking = meal.items.find((i) => i.kind === 'recipe' && i.recipe?.id === batch.recipe_id);
    if (cooking?.cooked) cooked.add(cooking.id);
  }
  const eaten = meal.items.filter((i) => !cooked.has(i.id));
  return eaten.length > 0 ? eaten : meal.items;
}

/** "Tub 2 of 4", for a tub in a meal; null for anything else. */
export function tubWords(item: PlanItem, plan: Plan): string | null {
  const tub = plan.tubs.find((t) => t.id === item.tub_id);
  const batch = plan.batch_cooks.find((b) => b.id === tub?.batch_id);
  return tub && batch ? `Tub ${tub.number} of ${batch.tub_count}` : null;
}

/**
 * A recipe card's small line (F116): "serves 4 · 15 min · 123 kcal each", each part only when it
 * is known. The serves part follows the meal's own Serves, else the recipe's own.
 */
export function recipeMeta(item: PlanItem): string {
  const parts: string[] = [];
  const serves = item.servings ?? item.recipe?.serves;
  if (serves) parts.push(`serves ${serves}`);
  const time = timePlusWait(item.recipe?.time_minutes ?? null, item.recipe?.wait);
  if (time) parts.push(time);
  if (item.recipe?.kcal != null) parts.push(`${item.recipe.kcal} kcal each`);
  return parts.join(' · ');
}

/** "2 recipes · 590 kcal each", "1 ingredient", "3 things · 80 kcal each". Proposed, for cabledrawer. */
export function mealTotals(meal: PlanMeal, plan: Plan | null = null): string {
  // Only what is eaten at the meal counts (F233, Plan; proposed, for cabledrawer), as on Today.
  const items = eatenItems(meal, plan);
  const n = items.length;
  const all = (kind: PlanItem['kind']) => items.every((i) => i.kind === kind);
  const noun = all('recipe')
    ? n === 1
      ? 'recipe'
      : 'recipes'
    : all('ingredient')
      ? n === 1
        ? 'ingredient'
        : 'ingredients'
      : all('note')
        ? n === 1
          ? 'note'
          : 'notes'
        : n === 1
          ? 'thing'
          : 'things';
  // A meal's kcal is one serving of each recipe, so it reads "each" (F116, cabledrawer 31 Oct).
  const kcal = meal.kcal === null ? '' : ` · ${meal.kcal} kcal each`;
  return `${n} ${noun}${kcal}`;
}

/** What a meal's answer is about: its things not cooked yet (F162), else all of them. */
export function leftName(meal: PlanMeal, plan: Plan | null = null): string {
  const left = meal.items.filter((i) => !i.cooked);
  const items = left.length ? left : meal.items;
  const first = items[0];
  if (!first) return 'Empty meal';
  const name = itemName(first, plan);
  return items.length === 1 ? name : `${name} and ${items.length - 1} more`;
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

/** A meal item that is cooking: a recipe in a meal still to cook or already cooked (not a tub
 * eaten, an ingredient or a note). The same rule as the Cook view's list (planCook.ts). */
export function isCooking(meal: PlanMeal, item: PlanItem): boolean {
  return item.kind === 'recipe' && (meal.status === 'planned' || meal.status === 'cooked');
}

/** Whether a day has any cooking: a batch's cook day or a recipe cooked fresh (F167). */
export function cooksOn(plan: Plan | null, day: string): boolean {
  if (cookedOn(plan, day).length > 0) return true;
  return !!plan?.meals.some((m) => m.date === day && m.items.some((i) => isCooking(m, i)));
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

/**
 * The batch cook that a recipe item was cooked for (its meal is the batch's cook meal). Only
 * one item is the cooking: the first copy of the recipe by position, then id, as on the server;
 * a second copy of the same recipe in that meal is an ordinary item.
 */
export const cookBatchOfItem = (
  plan: Plan | null,
  meal: PlanMeal,
  item: PlanItem
): PlanBatch | null => {
  if (item.kind !== 'recipe') return null;
  const cooks = (batch: PlanBatch, other: PlanItem) =>
    other.kind === 'recipe' &&
    (other.recipe ? batch.recipe_id === other.recipe.id : batch.recipe_name === other.kept_name);
  const batch = plan?.batch_cooks.find((b) => b.cook_meal_id === meal.id && cooks(b, item));
  if (!batch) return null;
  const first = [...meal.items]
    .sort((a, b) => a.position - b.position || a.id - b.id)
    .find((other) => cooks(batch, other));
  return first?.id === item.id ? batch : null;
};

/** "Batch · Sun": the small tag on a meal made in a Batch cook session (B2), by its cook day. */
export const sessionTag = (batch: PlanBatch | null | undefined): string | null =>
  batch?.session_id ? `Batch · ${dayShort(batch.cooked_on)}` : null;

/** The tag for a whole meal: its cook-day batch's, else its first tub's batch's. */
export function sessionTagOfMeal(plan: Plan | null, meal: PlanMeal): string | null {
  for (const item of meal.items) {
    const tag = sessionTag(tubOf(plan, item)?.batch ?? cookBatchOfItem(plan, meal, item));
    if (tag) return tag;
  }
  return null;
}

/** The Batch cook sessions cooked on this day (the cards above the day, B2). */
export const sessionsOn = (plan: Plan | null, day: string) =>
  (plan?.batch_sessions ?? []).filter((s) => s.cook_day === day);

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
export const whoseTub = (
  tub: PlanTub,
  people: Person[],
  removed: RemovedPerson[] = []
): string | null => {
  const gone = removed.find((p) => p.member_id === tub.member_id);
  return (
    people.find((p) => p.member_id === tub.member_id)?.name ??
    (gone ? removedName(gone.name) : null)
  );
};

/** A removed person the plan still names, with the name they had (0.9.5 Pe6). */
export interface RemovedPerson {
  member_id: number;
  name: string;
}

/** "Lorna (removed)": how a removed person reads on a past meal or a tub (cabledrawer 13 Nov). */
export const removedName = (name: string): string => `${name} (removed)`;

/** "3 days left", "use by today", "use by yesterday": for a tub's use-by day. Days left count
 * from the day the batch is cooked when that is still to come (F48: a tub cooked on Saturday has
 * its 3 days from Saturday, not "6 days left" on Wednesday). */
export function useByWords(useBy: string, today: string, cookedOn: string | null = null): string {
  const from = cookedOn !== null && cookedOn > today && cookedOn <= useBy ? cookedOn : today;
  const days = Math.round((Date.parse(useBy) - Date.parse(from)) / 86_400_000);
  if (days === 0) return 'use by today';
  if (days === 1) return 'use by tomorrow';
  if (days < 0) return days === -1 ? 'use by yesterday' : `${-days} days past use-by`;
  return `${days} days left`;
}

/**
 * Whether leftovers (and tubs) may go to this day and meal: after the meal that was cooked, and
 * never in the past (F50, cabledrawer 28 Oct: "just dont show dates befor eth cooked date"). `slots`
 * are the meals that are on, in order. Days are "YYYY-MM-DD".
 */
export function afterCook(
  day: string,
  slotId: number,
  cook: { date: string; slot_id: number },
  today: string,
  slots: MealSlot[]
): boolean {
  if (day < today || day < cook.date) return false;
  if (day > cook.date) return true;
  const order = slots.map((s) => s.id);
  const [at, cookAt] = [order.indexOf(slotId), order.indexOf(cook.slot_id)];
  return at >= 0 && at > cookAt;
}

/** Whether any meal on this day is after the cook meal (so the day is worth offering). */
export function dayAfterCook(
  day: string,
  cook: { date: string; slot_id: number },
  today: string,
  slots: MealSlot[]
): boolean {
  return slots.some((s) => afterCook(day, s.id, cook, today, slots));
}

/**
 * The next meals with nothing planned in them, after a meal and from today on, in the weeks the
 * plan on screen holds (F65: "Eat it on…" in "Any left over?"). `after` is the cook meal.
 */
export function nextFreeMeals(
  plan: Plan | null,
  slots: MealSlot[],
  after: { date: string; slot_id: number },
  today: string,
  limit = 4,
  /** The last day a tub may be eaten (its use-by), when it is known. */
  until: string | null = null
): { day: string; slotId: number }[] {
  if (!plan) return [];
  const found: { day: string; slotId: number }[] = [];
  for (
    let day = after.date > today ? after.date : today;
    day <= plan.end && (until === null || day <= until);
    day = nextDay(day)
  ) {
    for (const slot of slots) {
      if (found.length >= limit) return found;
      if (day < plan.start || !afterCook(day, slot.id, after, today, slots)) continue;
      if (!plan.meals.some((m) => m.date === day && m.slot_id === slot.id))
        found.push({ day, slotId: slot.id });
    }
  }
  return found;
}

const nextDay = (iso: string) => {
  const d = new Date(`${iso}T12:00:00Z`);
  d.setUTCDate(d.getUTCDate() + 1);
  return d.toISOString().slice(0, 10);
};
