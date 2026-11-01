// What the Plan's parts (the grid, the day list, the month, the sheets) ask the page to do.
// One object, passed down, so each part stays small.

import type { PlanItem, PlanMeal, TubLeft } from './client/plan';
import type { Carried } from './planDrag.svelte';
import type { PlanModel } from './plan.svelte';

export interface PlanActions {
  model: PlanModel;
  /** Offline: the plan can be read but not changed. */
  readonly: boolean;
  /** The computer's layout (iPads too): things can be dragged. The phone uses the sheet. */
  desktop: boolean;
  /** Open the menu for a meal (Move to… · Copy to… · Leftovers on… · Remove). */
  openMeal: (meal: PlanMeal) => void;
  /** Open the menu for one thing in a meal. */
  openItem: (meal: PlanMeal, item: PlanItem) => void;
  /** Open "Cook once, eat for…" for a planned recipe. */
  openCookOnce: (meal: PlanMeal, item: PlanItem) => void;
  /** Open the "Cooked it" review for a meal. */
  openCooked: (meal: PlanMeal) => void;
  /** Choose something to plan on a day (and a meal, when it's known). */
  add: (day: string, slotId: number | null) => void;
  /** Show one day's meals (Month). */
  openDay: (day: string) => void;
  carryMeal: (meal: PlanMeal) => Carried;
  carryItem: (meal: PlanMeal, item: PlanItem) => Carried;
  /** A COOK card (or the EAT card of its cook-day meal): moves the cooking, with its EAT card. */
  carryCook: (meal: PlanMeal) => Carried;
}

/** What the menu is for. */
export type PlanTarget =
  | { kind: 'meal'; meal: PlanMeal }
  | { kind: 'item'; meal: PlanMeal; item: PlanItem }
  /** `ahead`: from the recipe page, where the picker offers the next 14 days (not the Plan's tray). */
  | { kind: 'recipe'; recipe: { id: number; name: string }; ahead?: true }
  | { kind: 'tubleft'; tub: TubLeft }
  | { kind: 'day'; day: string };

/**
 * The day-and-meal picker on its own, where there is no Plan screen around it (the recipe page's
 * Plan it): only the model and whether the plan can be changed matter; nothing here opens a menu
 * or drags.
 */
export function pickerActions(model: PlanModel, readonly: () => boolean): PlanActions {
  const nothing = { label: '', zones: false, drop: () => {} };
  return {
    model,
    get readonly() {
      return readonly();
    },
    desktop: true,
    openMeal: () => {},
    openItem: () => {},
    openCookOnce: () => {},
    openCooked: () => {},
    add: () => {},
    openDay: () => {},
    carryMeal: () => nothing,
    carryItem: () => nothing,
    carryCook: () => nothing
  };
}
