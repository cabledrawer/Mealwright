// The plan works backwards (0.8 wave 5, M3, F124; cabledrawer 31 Oct and 9 Nov): the words of "When
// will you start it?", "Start tonight at 21:00", "Done yesterday 21:40" and "Fermented 10 h 20 min
// · needed 8–12 h", and which meals of a plan need starting when. Pure, so it is tested on its own
// (startWords.test.ts). The words are in docs/dev/words.md section 56; the mockups'
// (Dark-PlanStart08, Dark-TodayTonight08, Dark-CookDay2-08) are agreed, the rest is proposed, for
// cabledrawer. Every time here is the household's own wall clock, as the server says it.

import type { Plan, PlanAhead, PlanItem, PlanMeal } from './client/plan';
import { addDays } from './dates';
import { dayShort } from './planDates';
import { timeWords, waitLength, type StepWait } from './timeWords';

/** "8–12 h", "4–24 h", "8 h"; anything that is not whole hours is said as the recipe page says
 *  it ("90 min", "4 h – overnight"). */
export function waitRange(wait: StepWait): string {
  const whole = (n: number) => n % 60 === 0;
  if (wait.overnight || !whole(wait.min_minutes) || !whole(wait.max_minutes)) {
    return waitLength(wait);
  }
  const low = wait.min_minutes / 60;
  const high = wait.max_minutes / 60;
  return high > low ? `${low}–${high} h` : `${low} h`;
}

/** "Fri 21:00": one of the times offered. */
export const startOptionWords = (day: string, time: string) => `${dayShort(day)} ${time}`;

/** The base verb of a kind of wait: "It has to ferment first." */
const VERBS: Record<string, [verb: string, done: string, noun: string]> = {
  marinate: ['marinate', 'Marinated', 'Marinate'],
  soak: ['soak', 'Soaked', 'Soak'],
  ferment: ['ferment', 'Fermented', 'Ferment'],
  rest: ['rest', 'Rested', 'Rest'],
  chill: ['chill', 'Chilled', 'Chill'],
  prove: ['prove', 'Proved', 'Prove']
};

/** "It has to ferment first." (proposed, for cabledrawer; the mockup says "The batter has to
 *  ferment first.", about its one recipe). */
export const hasToWords = (kind: string) => `It has to ${VERBS[kind]?.[0] ?? 'wait'} first.`;

/** "Fermented", "Soaked": what has been done for a while. */
export const doneVerb = (kind: string) => VERBS[kind]?.[1] ?? 'Waited';

/** "Ferment", "Soak": the name of the wait on a card. */
export const kindName = (kind: string) => VERBS[kind]?.[2] ?? 'Wait';

/** "Start tonight at 21:00" in the evening, "Start at 07:00" earlier in the day. */
export function startWords(time: string): string {
  return Number(time.slice(0, 2)) >= 17 ? `Start tonight at ${time}` : `Start at ${time}`;
}

/** The step's own words cut to its first sentence, for a card's title ("Soak the rice."). */
export function stepTitle(text: string, most = 90): string {
  const first = text.split(/(?<=[.!?])\s/)[0] ?? text;
  const line = first.replace(/[.!?]$/, '').trim();
  const cut = line.length > most ? `${line.slice(0, most - 1).trimEnd()}…` : line;
  return cut;
}

/** "Done yesterday 21:40", "Done today 08:10", "Done Thu 21:40". */
export function doneWords(day: string, time: string, today: string): string {
  const word =
    day === today ? 'today' : day === addDays(today, -1) ? 'yesterday' : dayShort(day);
  return `Done ${word} ${time}`;
}

/** "Fermented 10 h 20 min": how long it has waited. */
export function waitedWords(kind: string, minutes: number): string {
  return `${doneVerb(kind)} ${timeWords(minutes)}`;
}

/** "needed 8–12 h". */
export const neededWords = (wait: StepWait) => `needed ${waitRange(wait)}`;

/** Is it waited long enough (at least the shortest length)? */
export const waitedEnough = (wait: StepWait, minutes: number) => minutes >= wait.min_minutes;

/** "Sat breakfast": where a meal is, for "For Sat breakfast". */
export const forMeal = (day: string, slotName: string) =>
  `${dayShort(day)} ${slotName.toLocaleLowerCase()}`;

/** One thing to start: a planned recipe whose long wait is to begin on a day. */
export interface StartEntry {
  key: string;
  meal: PlanMeal;
  item: PlanItem;
  ahead: PlanAhead;
  /** The day to start it, and the time. */
  day: string;
  time: string;
}

/**
 * The recipes of a plan that are to be started on `day` and have not been: a planned meal (not
 * cooked), a recipe with a long wait that has a start time on that day and is not begun yet.
 * In the order of their times.
 */
export function startsOn(plan: Plan | null, day: string): StartEntry[] {
  return startsWhere(plan, (start) => start === day);
}

/** What is to be started today, or should have been already (a start that has gone by and was
 *  not marked), for a meal still to come: Today's "Start tonight" cards. */
export function startsByNow(plan: Plan | null, today: string): StartEntry[] {
  return startsWhere(plan, (start) => start <= today, today);
}

function startsWhere(
  plan: Plan | null,
  wanted: (day: string) => boolean,
  mealsFrom: string | null = null
): StartEntry[] {
  if (!plan) return [];
  const found: StartEntry[] = [];
  for (const meal of plan.meals) {
    if (meal.status !== 'planned') continue;
    if (mealsFrom !== null && meal.date < mealsFrom) continue;
    for (const item of meal.items) {
      const ahead = item.ahead;
      if (!ahead || item.cooked || !ahead.start_day || !ahead.start_time) continue;
      if (ahead.started_time !== null || !wanted(ahead.start_day)) continue;
      found.push({
        key: `${meal.id}-${item.id}`,
        meal,
        item,
        ahead,
        day: ahead.start_day,
        time: ahead.start_time
      });
    }
  }
  return found.sort((a, b) => a.day.localeCompare(b.day) || a.time.localeCompare(b.time));
}

/** The recipes of a plan that have a long wait with no time set yet (for a quiet line on the
 *  meal: "No start time yet"). */
export const needsStartTime = (item: PlanItem): boolean =>
  !!item.ahead && !item.cooked && !item.ahead.start_time && item.ahead.started_time === null;
