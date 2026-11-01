// "Cook now" from a recipe (cabledrawer 1 Nov): the recipe is first planned into today's next meal,
// with an Undo, so "Cooked it" works at the end of Cook mode and the pantry stays right. The
// choice of meal and the notice words are proposed, for cabledrawer.
//
// Which meal (meal slots have names and an order, no times):
//   1. the recipe is already planned today in a meal that is not cooked yet: that meal, nothing
//      new is planned;
//   2. else the first meal that is on today, in order, with nothing cooked yet;
//   3. else (every meal today is cooked) the last meal that is on.
//
// Offline, or the plan can't be written: Cook mode still opens, without "Cooked it", and one
// line says the recipe wasn't planned.

import { newChangeId } from './changeId';
import { serverUndo } from './client/changes';
import { getHousehold } from './client/household';
import { getMealSlots, getPlan, planItem, type MealSlot, type PlanMeal } from './client/plan';
import { kitchen } from './freshness.svelte';
import { network } from './network.svelte';
import { slotsOn } from './planMeals';
import { undoHistory, type UndoEntry } from './undo.svelte';

export const NOT_PLANNED = 'This recipe wasn’t planned.';
export const TAKEN_OUT = 'Taken out of today’s plan.';

export type CookSpot = { kind: 'planned'; meal: PlanMeal } | { kind: 'new'; slotId: number } | null;

const hasRecipe = (meal: PlanMeal, recipeId: number) =>
  meal.items.some((i) => i.kind === 'recipe' && i.recipe?.id === recipeId);

/** Today's next meal for a recipe to be cooked in (see the top of this file). */
export function cookSpot(
  today: string,
  slots: MealSlot[],
  meals: PlanMeal[],
  recipeId: number
): CookSpot {
  const on = slotsOn(slots);
  const here = meals.filter((m) => m.date === today);
  for (const slot of on) {
    const meal = here.find((m) => m.slot_id === slot.id);
    if (meal && meal.status === 'planned' && hasRecipe(meal, recipeId))
      return { kind: 'planned', meal };
  }
  const open = on.find((s) => !here.some((m) => m.slot_id === s.id && m.status === 'cooked'));
  const slot = open ?? on.at(-1);
  return slot ? { kind: 'new', slotId: slot.id } : null;
}

/** What the recipe page's Cook now came to, for the Cook mode screen it opens. */
export class CookNow {
  /** The meal Cook mode can answer with "Cooked it"; null: none. */
  mealId = $state<number | null>(null);
  /** The recipe it is about (so another recipe's Cook mode shows none of this). */
  recipeId = $state<number | null>(null);
  /** The words to show: where it was planned, or that it wasn't. */
  text = $state<string | null>(null);
  /** Undo is there while the plan item can still be taken out. */
  canUndo = $state(false);
  /** The plan item was taken out again: no "Cooked it". */
  undone = $state(false);
  busy = $state(false);

  #entry: UndoEntry | null = null;

  /** Plan the recipe into today's next meal. Never throws: a failure is the "wasn't planned" line. */
  async start(recipeId: number): Promise<void> {
    if (this.busy) return;
    this.busy = true;
    this.#reset(recipeId);
    try {
      if (network.offline) throw new Error('offline');
      const today = (await getHousehold()).today;
      const [slots, plan] = await Promise.all([getMealSlots(), getPlan(today, today)]);
      const spot = cookSpot(today, slots, plan.meals, recipeId);
      if (!spot) throw new Error('no meal is on');
      if (spot.kind === 'planned') {
        this.mealId = spot.meal.id; // already planned: nothing new is added
        return;
      }
      const write = await planItem(
        { date: today, slot_id: spot.slotId, recipe_id: recipeId },
        newChangeId()
      );
      kitchen.changed();
      if (write.meal_id === null) throw new Error('no meal');
      const slotName = slots.find((s) => s.id === spot.slotId)?.name ?? 'meal';
      this.mealId = write.meal_id;
      this.text = `Planned for today’s ${slotName}`;
      const change = write.change;
      if (change?.can_undo) {
        const undo = serverUndo(change.id);
        this.#entry = {
          label: this.text,
          needsServer: true,
          undo: async () => {
            const message = await undo();
            this.undone = true;
            this.canUndo = false;
            this.text = TAKEN_OUT;
            return message;
          }
        };
        // On the list for Ctrl+Z; no toast, because Cook mode covers the toast's place.
        undoHistory.record(this.#entry, { toast: false });
        this.canUndo = true;
      }
    } catch {
      this.mealId = null;
      this.text = NOT_PLANNED;
    } finally {
      this.busy = false;
    }
  }

  /** The notice's Undo. */
  async undo(): Promise<void> {
    if (this.#entry) await undoHistory.undo(this.#entry);
  }

  #reset(recipeId: number) {
    this.mealId = null;
    this.recipeId = recipeId;
    this.text = null;
    this.canUndo = false;
    this.undone = false;
    this.#entry = null;
  }
}

export const cookNow = new CookNow();
