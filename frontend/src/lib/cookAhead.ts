// Cook mode on day two (M3, F124; cabledrawer 31 Oct and 9 Nov, mockup CookDay2-08): when the recipe's
// long wait was begun, Cook mode starts at the step after it, with the steps up to it folded
// ("1–3 · Soak, grind and leave the batter · Done yesterday 21:40") and how long it has waited
// against how long it needs ("Fermented 10 h 20 min · needed 8–12 h"). Pure, so it is tested on
// its own (cookAhead.test.ts). Words: docs/dev/words.md section 56.

import type { PlanAhead } from './client/plan';
import type { CookStep } from './cookSteps';
import { addDays } from './dates';
import { doneWords, neededWords, stepTitle, waitedEnough, waitedWords } from './startWords';

export interface AheadView {
  /** The index (in Cook mode's steps) of the step that waits. */
  index: number;
  /** The wait was begun: Cook mode starts after it. */
  begun: boolean;
  /** "1–3", or "1": the steps folded away. */
  range: string;
  /** "Soak, grind and leave the batter". */
  title: string;
  /** "Done yesterday 21:40". */
  done: string | null;
  /** "Fermented 10 h 20 min", "needed 8–12 h". */
  waited: string | null;
  needed: string;
  /** It has waited at least the shortest it needs. */
  enough: boolean;
  /** 2 for the day after it was begun; null on the day itself. */
  day: number | null;
}

/** How many days after `from` is `to` (whole days, both "2026-11-13" style). */
function daysAfter(from: string, to: string): number {
  let n = 0;
  for (let d = from; d < to && n < 400; d = addDays(d, 1)) n += 1;
  return n;
}

/**
 * What Cook mode shows of a recipe's long wait, or null when the step that waits is not among the
 * steps (the way of cooking was changed, or the recipe edited): then nothing is folded.
 */
export function aheadView(ahead: PlanAhead, steps: CookStep[], today: string): AheadView | null {
  const index = steps.findIndex((s) => s.id === ahead.step_id);
  if (index < 0) return null;
  const begun = ahead.started_time !== null && ahead.started_day !== null;
  const gap = begun ? daysAfter(ahead.started_day!, today) : 0;
  const minutes = ahead.waited_minutes;
  return {
    index,
    begun,
    range: index === 0 ? '1' : `1–${index + 1}`,
    title: stepTitle(ahead.step_text),
    done: begun ? doneWords(ahead.started_day!, ahead.started_time!, today) : null,
    waited: begun && minutes !== null ? waitedWords(ahead.wait.kind, minutes) : null,
    needed: neededWords(ahead.wait),
    enough: minutes !== null && waitedEnough(ahead.wait, minutes),
    day: gap >= 1 ? gap + 1 : null
  };
}
