// Which tubs a day offers (P4, F52): "The day sheet lists the oldest freezer tub first", and
// "fridge tubs past their use-by aren't offered" (cabledrawer 28 Oct). The server refuses any tub on a
// day after its use-by, so a freezer tub that ran out is left out as well.

import type { TubLeft } from './client/plan.js';

export interface TubOffer {
  /** The tubs to show: freezer tubs first (the oldest first), then the others by use-by. */
  tubs: TubLeft[];
  /** How many fridge tubs are left out because they are past their use-by by `day`. */
  pastUseBy: number;
}

/** The meal the tubs are for, so a tub is never offered before it is cooked: the meals that are
 * on (in order), and the meal each batch is cooked in on the day its tubs count from (null when it
 * is not known, or when the batch was cooked on an earlier day than that meal). */
export interface ForMeal {
  slotId: number;
  slotIds: readonly number[];
  cookSlotOf: (batchId: number, cookedOn: string) => number | null;
}

/** Whether a tub of a batch cooked on `cookedOn` may be eaten at this day (and meal): never
 * before its cook day, and on the cook day only at a meal after the cooking (spec F50 and F230,
 * cabledrawer 12 Nov: "never offer tubs for meals before their cook day"). */
function afterCooking(t: TubLeft, day: string, meal: ForMeal | undefined): boolean {
  if (day < t.cooked_on) return false;
  if (day > t.cooked_on || !meal) return true;
  const cook = meal.cookSlotOf(t.batch_id, t.cooked_on);
  if (cook === null) return true;
  const [at, cookAt] = [meal.slotIds.indexOf(meal.slotId), meal.slotIds.indexOf(cook)];
  return at < 0 || cookAt < 0 || at > cookAt;
}

/** The tubs left, ordered and filtered for a meal on `day` ("YYYY-MM-DD"). With `meal`, the
 * tubs cooked on that very day are only for meals after the cooking. */
export function tubsForDay(tubs: readonly TubLeft[], day: string, meal?: ForMeal): TubOffer {
  const usable = tubs.filter((t) => t.use_by >= day && afterCooking(t, day, meal));
  const rank = (t: TubLeft) => (t.place_kind === 'freezer' ? 0 : 1);
  const tubsOrdered = [...usable].sort(
    (a, b) => rank(a) - rank(b) || a.use_by.localeCompare(b.use_by) || a.id - b.id
  );
  return {
    tubs: tubsOrdered,
    pastUseBy: tubs.filter(
      (t) => t.use_by < day && t.place_kind !== 'freezer' && afterCooking(t, day, meal)
    ).length
  };
}

/** The most tubs the day sheet lists before "+N more tubs". */
export const MAX_TUBS_LISTED = 12;

/**
 * The tubs to list now. Every tub that is not in the freezer (the fridge ones, still in date) is
 * always listed, so a long freezer list never hides them; the freezer tubs fill what is left of
 * `limit`, the oldest first. The order stays as `tubsForDay` gave it. `hidden` is how many wait
 * behind "+N more tubs".
 */
export function tubsListed(
  tubs: readonly TubLeft[],
  expanded: boolean,
  limit = MAX_TUBS_LISTED
): { shown: TubLeft[]; hidden: number } {
  if (expanded || tubs.length <= limit) return { shown: [...tubs], hidden: 0 };
  const others = tubs.filter((t) => t.place_kind !== 'freezer').length;
  let room = Math.max(0, limit - others);
  const shown = tubs.filter((t) => {
    if (t.place_kind !== 'freezer') return true;
    if (room <= 0) return false;
    room--;
    return true;
  });
  return { shown, hidden: tubs.length - shown.length };
}
