// "Cook now" from a recipe (cabledrawer 1 Nov): the recipe is first planned into today's next meal,
// with an Undo, so "Cooked it" works at the end of Cook mode and the pantry stays right. The
// choice of meal and the notice words are proposed, for cabledrawer.
//
// Which meal (meal slots have names and an order, no times):
//   1. the recipe is already planned today in a meal that is not cooked yet: that meal, nothing
//      new is planned, and "Cooked it" reviews only this recipe's item there (cabledrawer 1 Nov);
//   2. else the first meal that is on today, in order, with no meal at all yet;
//   3. else the first meal that is on today whose meal is still planned (the recipe is added to
//      it, and "Cooked it" then reviews only this recipe, not the others in that meal);
//   4. else nothing is open (the server refuses a meal that is cooked, "didn't cook" or moved):
//      no plan write, and Cook mode opens without "Cooked it" and with the "wasn't planned" line.
// Rules 2 to 4 are proposed, for cabledrawer (1 Nov, after the checker found that the first version
// chose meals the server refuses).
//
// Offline, or the plan can't be written: Cook mode still opens, without "Cooked it", and one
// line says the recipe wasn't planned.

import { cantReach } from './api';
import { forgetOnWipe } from './offline/wipeHooks';
import { newChangeId } from './changeId';
import { serverUndo } from './client/changes';
import { getHousehold } from './client/household';
import {
  getMealSlots,
  getPlan,
  planItem,
  type MealSlot,
  type PlanItem,
  type PlanMeal,
  type PlanWrite
} from './client/plan';
import { kitchen } from './freshness.svelte';
import { network } from './network.svelte';
import { optionalAsk } from './optionalAsk.svelte';
import { slotsOn } from './planMeals';
import { undoHistory, type UndoEntry } from './undo.svelte';

export const NOT_PLANNED = 'This recipe wasn’t planned.';
export const TAKEN_OUT = 'Removed from today’s plan.';

export type CookSpot = { kind: 'planned'; meal: PlanMeal } | { kind: 'new'; slotId: number } | null;

const hasRecipe = (meal: PlanMeal, recipeId: number) =>
  meal.items.some((i) => i.kind === 'recipe' && !i.cooked && i.recipe?.id === recipeId);

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
  const empty = on.find((s) => !here.some((m) => m.slot_id === s.id));
  if (empty) return { kind: 'new', slotId: empty.id };
  const room = on.find((s) => here.some((m) => m.slot_id === s.id && m.status === 'planned'));
  return room ? { kind: 'new', slotId: room.id } : null;
}

/** What the recipe page's Cook now came to, for the Cook mode screen it opens. */
export class CookNow {
  /** The meal Cook mode can answer with "Cooked it"; null: none. */
  mealId = $state<number | null>(null);
  /** The plan item "Cooked it" reviews (this recipe's, added or already planned); null: the meal. */
  itemId = $state<number | null>(null);
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
        // cabledrawer 1 Nov: as in rule 3, Cooked it reviews only this recipe's item
        // (the first one if the meal has it twice), not the other recipes in that meal.
        this.itemId =
          spot.meal.items.find((i) => i.kind === 'recipe' && i.recipe?.id === recipeId && !i.cooked)
            ?.id ?? null;
        return;
      }
      const slotName = slots.find((s) => s.id === spot.slotId)?.name ?? 'meal';
      // Optional ingredients (R3): asked here too, before the recipe is planned for today.
      const use = await optionalAsk.ask({ id: recipeId }, `today ${slotName.toLocaleLowerCase()}`);
      if (use === null) throw new Error('cancelled'); // not planned; Cook mode still opens
      const body: { date: string; slot_id: number; recipe_id: number; optional_use?: number[] } = {
        date: today,
        slot_id: spot.slotId,
        recipe_id: recipeId,
        ...(use === undefined ? {} : { optional_use: use })
      };
      const key = newChangeId();
      let write: PlanWrite;
      try {
        write = await planItem(body, key);
      } catch (error) {
        if (!cantReach(error)) throw error;
        // The reply may have been lost after the server did it: ask again with the same key,
        // which the server answers with the same item instead of adding a second.
        write = await planItem(body, key);
      }
      kitchen.changed();
      if (write.meal_id === null) throw new Error('no meal');
      this.mealId = write.meal_id;
      this.itemId = write.item_id ?? null;
      this.text = `Planned for today’s ${slotName}`;
      const change = write.change;
      if (change?.can_undo) {
        const undo = serverUndo(change.id);
        const entry: UndoEntry = {
          label: this.text,
          needsServer: true,
          undo: async () => {
            const message = await undo();
            // The plan item is removed either way, but the screen changes only if it is still
            // this Cook now's (another recipe's Cook mode may be open by now).
            if (this.#entry === entry) {
              this.undone = true;
              this.canUndo = false;
              this.text = TAKEN_OUT;
            }
            return message;
          }
        };
        this.#entry = entry;
        // On the list for Ctrl+Z; no toast, because Cook mode covers the toast's place.
        undoHistory.record(entry, { toast: false });
        this.canUndo = true;
      }
    } catch {
      this.mealId = null;
      this.text = NOT_PLANNED;
    } finally {
      this.busy = false;
    }
  }

  /**
   * "Start cooking" from the Plan: the recipe is already planned in this meal, so nothing is
   * planned and there is no notice; Cook mode opens for this item and "Cooked it" reviews only it.
   */
  open(recipeId: number, mealId: number, itemId: number): void {
    this.#reset(recipeId);
    this.mealId = mealId;
    this.itemId = itemId;
  }

  /** The notice for a Cook mode page: only for this recipe and the ?meal= it was opened with
   *  (so a later visit, such as going back in history, shows none). */
  noticeFor(recipeId: number, mealId: number | null): { text: string; canUndo: boolean } | null {
    if (this.recipeId !== recipeId || !this.text || this.mealId !== mealId) return null;
    // After Undo the meal is still named in the address, but the item is gone: keep the line.
    return { text: this.text, canUndo: this.canUndo };
  }

  /** The one plan item of `meal` that "Cooked it" reviews for this recipe; null: the whole meal. */
  onlyItem(recipeId: number, meal: PlanMeal): PlanItem | null {
    if (this.recipeId !== recipeId || this.mealId !== meal.id || !this.itemId) return null;
    return meal.items.find((i) => i.id === this.itemId) ?? null;
  }

  /** Cook mode was left: forget it, so the notice doesn't come back on a later visit. */
  leave(): void {
    this.#reset(null);
  }

  /** The notice's Undo. */
  async undo(): Promise<void> {
    if (this.#entry) await undoHistory.undo(this.#entry);
  }

  #reset(recipeId: number | null) {
    this.mealId = null;
    this.itemId = null;
    this.recipeId = recipeId;
    this.text = null;
    this.canUndo = false;
    this.undone = false;
    this.#entry = null;
  }
}

export const cookNow = new CookNow();

// What Cook now planned (a meal, a plan item, the words about it) is one person's: gone when the
// browser is wiped (another person signing in), but kept when the same person signs in again
// after a session ended mid-cook, so "Cooked it" and the notice with its Undo are still there.
forgetOnWipe(() => cookNow.leave());
