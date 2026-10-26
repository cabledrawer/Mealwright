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
  /** Choose something to plan on a day (and a meal, when it's known). */
  add: (day: string, slotId: number | null) => void;
  /** Show one day's meals (Month). */
  openDay: (day: string) => void;
  carryMeal: (meal: PlanMeal) => Carried;
  carryItem: (meal: PlanMeal, item: PlanItem) => Carried;
}

/** What the menu is for. */
export type PlanTarget =
  | { kind: 'meal'; meal: PlanMeal }
  | { kind: 'item'; meal: PlanMeal; item: PlanItem }
  | { kind: 'recipe'; recipe: { id: number; name: string } }
  | { kind: 'tubleft'; tub: TubLeft }
  | { kind: 'day'; day: string };
