// A step's timing for Batch cook (Experimental; 0.8 wave 6, B1; mockup Dark-BatchSteps08): hands-on
// or waiting, minutes, and what it uses, each guessed by the server from the step's words until a
// person sets it. The words are the mockup's; the ones marked proposed wait for cabledrawer
// (docs/dev/words.md, Batch cook step timings). Pure, so it is tested without a screen.

import type { StepEquipment, StepHands } from '#lib/client/recipes.js';
import { timeWords } from '#lib/timeWords.js';
import type { DraftStep } from './draft.svelte.js';

export const HANDS_CHOICES: { value: StepHands; name: string }[] = [
  { value: 'hands', name: 'Hands-on' },
  { value: 'waiting', name: 'Waiting' }
];

export const EQUIPMENT_CHOICES: { value: StepEquipment; name: string }[] = [
  { value: 'hob', name: 'Hob ring' },
  { value: 'pressure', name: 'Pressure cooker' },
  { value: 'oven', name: 'Oven' },
  { value: 'none', name: 'Nothing' }
];

export const MOST_MINUTES = 14_400;

/** What a new step is taken to be when a person sets one value before any guess is known. */
const BEFORE_A_GUESS = { hands: 'hands', minutes: 5, equipment: 'none' } as const;

export interface ShownTiming {
  hands: StepHands | null;
  minutes: number | null;
  equipment: StepEquipment | null;
  /** Each value is set by hand (true) or guessed (false). */
  handsByHand: boolean;
  minutesByHand: boolean;
  equipmentByHand: boolean;
  /** "guessed" · "set by you" · "partly guessed" (proposed, for cabledrawer) */
  mark: 'guessed' | 'set by you' | 'partly guessed';
  /** The step's words changed since the guess was read, or it was never read: the guess is made
   *  when the recipe is saved, so a guessed value is not known yet. */
  pending: boolean;
}

/** What shows for a step now: what was set by hand, else the server's guess, else nothing yet. */
export function shownTiming(step: DraftStep): ShownTiming {
  const fresh = step.guess !== null && step.guessFor.trim() === step.text.trim();
  const t = step.timing;
  const guess = fresh ? step.guess : null;
  const handsByHand = t.hands != null;
  const minutesByHand = t.minutes != null;
  const equipmentByHand = t.equipment != null;
  const all = handsByHand && minutesByHand && equipmentByHand;
  const none = !handsByHand && !minutesByHand && !equipmentByHand;
  return {
    hands: t.hands ?? guess?.hands ?? null,
    minutes: t.minutes ?? guess?.minutes ?? null,
    equipment: t.equipment ?? guess?.equipment ?? null,
    handsByHand,
    minutesByHand,
    equipmentByHand,
    mark: all ? 'set by you' : none ? 'guessed' : 'partly guessed',
    pending: !fresh && !all
  };
}

/** "Hands-on · 8 min" · "Waiting · 15 min"; empty before the guess is known. */
export function handsWords(shown: ShownTiming): string {
  if (shown.hands === null || shown.minutes === null) return '';
  const name = HANDS_CHOICES.find((c) => c.value === shown.hands)!.name;
  return `${name} · ${timeWords(shown.minutes)}`;
}

/** "Pressure cooker"; empty for Nothing (the mockup shows no tag then) and before the guess. */
export function equipmentWords(shown: ShownTiming): string {
  if (shown.equipment === null || shown.equipment === 'none') return '';
  return EQUIPMENT_CHOICES.find((c) => c.value === shown.equipment)!.name;
}

/** The first change a person makes takes all three values as theirs (what shows stays as it is,
 *  and a change in the words no longer moves them): "set by you". */
export function takeAsYours(step: DraftStep): void {
  const shown = shownTiming(step);
  if (shown.mark === 'set by you') return;
  step.timing = {
    hands: shown.hands ?? BEFORE_A_GUESS.hands,
    minutes: shown.minutes ?? BEFORE_A_GUESS.minutes,
    equipment: shown.equipment ?? BEFORE_A_GUESS.equipment
  };
}

/** "Guess again": nothing set by hand any more. */
export function guessAgain(step: DraftStep): void {
  step.timing = { hands: null, minutes: null, equipment: null };
}

/** Minutes typed in the box: a whole number from 1 to 14,400, or null. */
export function minutesFrom(text: string): number | null {
  const t = text.trim();
  if (!/^\d{1,5}$/.test(t)) return null;
  const n = Number(t);
  return n >= 1 && n <= MOST_MINUTES ? n : null;
}
