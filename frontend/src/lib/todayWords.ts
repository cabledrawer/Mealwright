// The words on Today, worked out from what the server sent. Pure, so each is tested on its own
// (todayWords.test.ts). Dates are the household's ("2026-10-25"): nothing here reads this
// device's clock or time zone. Every line is proposed, for cabledrawer (docs/dev/words.md section 22).

import type { Plan } from './client/plan';
import { addDays } from './dates';
import { dayLong, dayOfMonth, dayShort } from './planDates';
import { itemName } from './planMeals';

/** The day a meal was planned for, from the card's point of view: "Yesterday", "Fri 23". */
export function whenWords(day: string, today: string): string {
  if (day === addDays(today, -1)) return 'Yesterday';
  if (day === today) return 'Today';
  return `${dayShort(day)} ${dayOfMonth(day)}`;
}

/** "Today", "Tomorrow", "Monday": the next-cook line and the move button. */
export function dayWords(day: string, today: string): string {
  if (day === today) return 'Today';
  if (day === addDays(today, 1)) return 'Tomorrow';
  return dayLong(day);
}

/** "today", "tomorrow", "Mon 26": inside a sentence or on the Move button. */
export function dayInSentence(day: string, today: string): string {
  if (day === today) return 'today';
  if (day === addDays(today, 1)) return 'tomorrow';
  return `${dayShort(day)} ${dayOfMonth(day)}`;
}

/** What is in a meal slot on a day, for Move it. */
export type Spot =
  | { state: 'free' }
  /** The meal there has food: the move adds alongside. `what` names the first thing. */
  | { state: 'alongside'; what: string }
  /** The meal there was cooked, skipped or moved: it is locked. */
  | { state: 'done' };

export function spotAt(plan: Plan, day: string, slotId: number): Spot {
  const meal = plan.meals.find((m) => m.date === day && m.slot_id === slotId);
  if (!meal || meal.items.length === 0) return { state: 'free' };
  if (meal.status !== 'planned') return { state: 'done' };
  const first = meal.items[0]!;
  const tub = plan.tubs.find((t) => t.id === first.tub_id);
  const batch = plan.batch_cooks.find((b) => b.id === tub?.batch_id);
  const what =
    first.kind === 'tub' && tub && batch
      ? `${batch.recipe_name} · tub ${tub.number} of ${batch.tub_count}`
      : itemName(first, plan);
  return { state: 'alongside', what };
}

/** The word beside a meal in Move it. */
export function spotWords(spot: Spot): string {
  return spot.state === 'free' ? 'free' : spot.state === 'done' ? 'already done' : 'adds alongside';
}

/** The tubs count in Any left over?: "None", "1 tub", "3 tubs". */
export const tubsWords = (count: number) =>
  count <= 0 ? 'None' : count === 1 ? '1 tub' : `${count} tubs`;

/** "1 meal", "2 meals", for a day in This week. */
export const mealsWords = (count: number) =>
  count === 0 ? 'Nothing planned' : count === 1 ? '1 meal' : `${count} meals`;

/** How many are waiting behind the one on the card: "1 more meal to answer". */
export const moreWords = (count: number) =>
  count === 1 ? '1 more meal to answer' : `${count} more meals to answer`;
