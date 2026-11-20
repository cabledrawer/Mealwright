// A time in minutes, in words (F114, cabledrawer 31 Oct): "45 min" up to an hour, then hours and
// minutes ("1 h", "2 h 5 min", "12 h 25 min"). The one place a time in minutes is turned into
// text; every list, card and page uses it. A no-break space keeps a number with its unit.

import { NBSP } from './words.js';

export function timeWords(minutes: number): string {
  const total = Math.round(minutes);
  if (total < 60) return `${total}${NBSP}min`;
  const hours = Math.floor(total / 60);
  const rest = total % 60;
  return rest === 0 ? `${hours}${NBSP}h` : `${hours}${NBSP}h${NBSP}${rest}${NBSP}min`;
}

// --- Steps that wait (M1; cabledrawer 31 Oct and 9 Nov) -------------------------------------------

/** A wait on a step, or all of a recipe's waits added up (`kind` is then "wait" if they differ). */
export interface StepWait {
  kind: string;
  min_minutes: number;
  max_minutes: number;
  /** The range ends at "overnight" (counted as 12 h). */
  overnight: boolean;
}

/** The kinds a step can wait for, in the order the Waits field offers them: the name of the kind,
 *  and the word the time line uses ("plus 4 h – overnight marinating"). Words in docs/dev/words.md. */
export const WAIT_KINDS = [
  { kind: 'marinate', name: 'Marinate', doing: 'marinating' },
  { kind: 'soak', name: 'Soak', doing: 'soaking' },
  { kind: 'ferment', name: 'Ferment', doing: 'fermenting' },
  { kind: 'rest', name: 'Rest', doing: 'resting' },
  { kind: 'chill', name: 'Chill', doing: 'chilling' },
  { kind: 'prove', name: 'Prove', doing: 'proving' }
] as const;

/** "Marinate", "Soak"... ("Wait" for the waits of a recipe added up). */
export function waitName(kind: string): string {
  return WAIT_KINDS.find((k) => k.kind === kind)?.name ?? 'Wait';
}

/** "marinating", "soaking"... ("waiting" when the kinds differ). */
export function waitDoing(kind: string): string {
  return WAIT_KINDS.find((k) => k.kind === kind)?.doing ?? 'waiting';
}

/** The length of a wait: "90 min", "8 h – 12 h", "4 h – overnight", "overnight". "Overnight" is
 *  stored as 12 h, so it is said only while the longest end is exactly that: a range that goes
 *  past 12 h (Ends overnight with a longer Longest, or two overnight waits added up) is shown as
 *  the numbers it is, and a shortest above 12 h is never "overnight". */
export function waitLength(wait: StepWait): string {
  const low = timeWords(wait.min_minutes);
  const plain =
    wait.max_minutes > wait.min_minutes ? `${low} – ${timeWords(wait.max_minutes)}` : low;
  if (!wait.overnight || wait.max_minutes > 720) return plain;
  return wait.min_minutes >= wait.max_minutes ? 'overnight' : `${low} – overnight`;
}

/** A recipe's time as two parts: the active time ("45 min active" once it has a wait, "45 min"
 *  without) and the wait ("plus 4 h – overnight marinating"; no "plus" without active time). */
export function timeParts(
  minutes: number | null,
  wait: StepWait | null | undefined
): { active: string | null; wait: string | null } {
  if (!wait) return { active: minutes === null ? null : timeWords(minutes), wait: null };
  const waiting = `${waitLength(wait)} ${waitDoing(wait.kind)}`;
  return minutes === null
    ? { active: null, wait: waiting }
    : { active: `${timeWords(minutes)} active`, wait: `plus ${waiting}` };
}

/** A recipe's time with its waits: "45 min active · plus 4 h – overnight marinating", or just
 *  "45 min" when nothing waits, or "4 h – overnight marinating" when there is no active time. */
export function timeWithWait(minutes: number | null, wait: StepWait | null | undefined): string {
  const { active, wait: waiting } = timeParts(minutes, wait);
  return [active, waiting].filter(Boolean).join(' · ');
}

/** The short form for a card or a list line: "45 min + 4 h – overnight". */
export function timePlusWait(minutes: number | null, wait: StepWait | null | undefined): string {
  if (!wait) return minutes === null ? '' : timeWords(minutes);
  return minutes === null ? waitLength(wait) : `${timeWords(minutes)} + ${waitLength(wait)}`;
}

/** All the waits of some steps added up (the same sum the server makes); null when none wait. */
export function sumWaits(steps: { kind: string; wait?: StepWait | null }[]): StepWait | null {
  const waits = steps.filter((s) => s.kind === 'step' && s.wait).map((s) => s.wait!);
  if (waits.length === 0) return null;
  const kinds = new Set(waits.map((w) => w.kind));
  return {
    kind: kinds.size === 1 ? waits[0]!.kind : 'wait',
    min_minutes: waits.reduce((n, w) => n + w.min_minutes, 0),
    max_minutes: waits.reduce((n, w) => n + w.max_minutes, 0),
    overnight: waits.some((w) => w.overnight)
  };
}

/** The page's total time without the waits now on the steps (the same rule as the server's
 *  `active_time`: the longest waits come off if the total held them, else the shortest; if it
 *  held neither, or would be left with nothing, the total stays). */
export function activeTime(
  total: number | null,
  waits: { min_minutes: number; max_minutes: number }[]
): number | null {
  if (total === null) return null;
  const longest = waits.reduce((n, w) => n + (w.max_minutes || w.min_minutes), 0);
  const shortest = waits.reduce((n, w) => n + w.min_minutes, 0);
  for (const take of [longest, shortest]) if (take && total - take >= 1) return total - take;
  return total;
}
