// "Leftovers on…" (0.7 P1; cabledrawer 28 Oct): a batch makes a fixed number of portions, its tubs
// plus the cook-day meal. These work out which meals the sheet offers and what it says about
// the portions, from what the server sent. Pure, so they are tested on their own
// (portions.test.ts). Words marked "proposed, for cabledrawer" are in docs/dev/words.md section 28.

import type { MealSlot, Plan, PlanMeal, Portions } from './client/plan';
import { addDays } from './planDates';
import { afterCook, mealName } from './planMeals';

/** One meal the sheet lists. */
export interface LeftoverRow {
  day: string;
  slotId: number;
  /** free: nothing there; has: something else is planned there (it goes alongside);
   * planned: a tub of this batch is already there. */
  state: 'free' | 'has' | 'planned';
  /** What is already planned there, for "has". */
  what: string | null;
  /** The use-by day: the last one offered. */
  last: boolean;
}

/** The most days the sheet lists (a plan read is at most 62 days). */
export const MOST_LEFTOVER_DAYS = 62;

/** The first and last day of the meals offered: the cook day (or today, if later) to the use-by. */
export function offeredDays(
  cookDate: string,
  today: string,
  useBy: string
): { first: string; last: string } {
  const first = cookDate > today ? cookDate : today;
  const limit = addDays(first, MOST_LEFTOVER_DAYS - 1);
  return { first, last: useBy < limit ? useBy : limit };
}

/**
 * Only meals after the cook meal and before the use-by are offered (never a past day; F50).
 * `slotsOn` are the meals that are on, in order. `plan` covers the offered days; `batchId` is the
 * batch whose tubs show as already planned.
 */
export function leftoverRows(args: {
  cook: { date: string; slot_id: number };
  today: string;
  useBy: string;
  slotsOn: MealSlot[];
  plan: Plan | null;
  batchId: number | null;
}): LeftoverRow[] {
  const { cook, today, useBy, slotsOn, plan, batchId } = args;
  const { first, last } = offeredDays(cook.date, today, useBy);
  const tubs = new Set((plan?.tubs ?? []).filter((t) => t.batch_id === batchId).map((t) => t.id));
  const rows: LeftoverRow[] = [];
  for (let day = first; day <= last; day = addDays(day, 1)) {
    for (const slot of slotsOn) {
      if (!afterCook(day, slot.id, cook, today, slotsOn)) continue;
      const meal: PlanMeal | null =
        plan?.meals.find((m) => m.date === day && m.slot_id === slot.id) ?? null;
      const mine = meal?.items.some((i) => i.tub_id !== null && tubs.has(i.tub_id)) ?? false;
      rows.push({
        day,
        slotId: slot.id,
        state: mine ? 'planned' : meal && meal.items.length ? 'has' : 'free',
        what: !mine && meal && meal.items.length ? mealName(meal, plan) : null,
        last: day === useBy
      });
    }
  }
  return rows;
}

/** What the bar above the list shows, one part per portion. */
export type BarPart = 'cook' | 'planned' | 'picked' | 'free' | 'over';

/**
 * One part for each portion: the cook-day meal, the tubs already planned, the ones just picked,
 * the ones still free; and a part for each meal picked beyond the portions left.
 */
export function portionBar(p: Portions, picked: number): BarPart[] {
  const left = p.left ?? 0;
  const planned = Math.max(0, (p.tubs ?? 0) - left);
  const within = Math.min(picked, left);
  return [
    ...Array<BarPart>(p.cook_day ?? 0).fill('cook'),
    ...Array<BarPart>(planned).fill('planned'),
    ...Array<BarPart>(within).fill('picked'),
    ...Array<BarPart>(left - within).fill('free'),
    ...Array<BarPart>(Math.max(0, picked - left)).fill('over')
  ];
}

const tubs = (n: number) => `${n} ${n === 1 ? 'tub' : 'tubs'}`;

/** "6 portions: 2 eaten on the cook day, 3 tubs planned, 1 left" (read aloud with the bar). */
export function barLabel(p: Portions): string {
  const planned = Math.max(0, (p.tubs ?? 0) - (p.left ?? 0));
  return `${p.portions} portions: ${p.cook_day} eaten on the cook day, ${tubs(planned)} planned, ${p.left} left`;
}

/**
 * "Makes 6 · 2 eaten Sun · 3 tubs planned · 2 picked, only 1 left" (proposed, for cabledrawer; the
 * mockup's words). `cookDay` is the short name of the cook day ("Sun").
 */
export function portionsLine(p: Portions, picked: number, cookDay: string): string {
  const planned = Math.max(0, (p.tubs ?? 0) - (p.left ?? 0));
  const left = p.left ?? 0;
  const tail =
    picked === 0
      ? `${left} left`
      : picked <= left
        ? `${picked} picked, ${left - picked} left`
        : `${picked} picked, ${left === 0 ? 'none left' : `only ${left} left`}`;
  return `Makes ${p.portions} · ${p.cook_day} eaten ${cookDay} · ${tubs(planned)} planned · ${tail}`;
}

/** The meals picked beyond the portions left: the latest ones (the earliest take the portions). */
export function shortRows(rows: LeftoverRow[], picked: Set<string>, left: number): LeftoverRow[] {
  return rows.filter((r) => picked.has(rowKey(r))).slice(left);
}

export const rowKey = (r: { day: string; slotId: number }) => `${r.day}|${r.slotId}`;

/** "Plan 2 tubs" (the mockup's button). */
export const planWords = (n: number) => `Plan ${tubs(n)}`;
