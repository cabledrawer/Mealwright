// What Cook mode shows, worked out from a recipe (spec section 6, "Cook mode"): the method as
// one step at a time, the timers found in a step's words, and the ingredients a step seems to
// use. Pure, so it is tested without a screen.
//
// A heading is a section title, never a step and never counted ("Step 2 of 4" counts steps
// only; the same rule as the recipe page, F112). A recipe with two method sections shows all
// its steps in order, each under the title of its section. A heading with no step under it
// shows nothing.

import type { RecipeLine } from './client/recipes';
import type { StepWait } from './timeWords';

/** The steps of a recipe as the server sends them (`lines` are the links to ingredient lines). */
export interface StepIn {
  id?: number;
  kind: 'step' | 'heading';
  text: string;
  lines?: { line_id: number; line: number; kind: 'guessed' | 'by_hand' }[];
  /** A wait on the step (marinate, soak...), M1. */
  wait?: StepWait | null;
}

export interface CookStep {
  /** From 1, steps only. */
  number: number;
  /** How many steps the recipe has. */
  total: number;
  /** The title of the section it is in, or null before any heading. */
  section: string | null;
  text: string;
  /** The ingredient lines the server linked to it (set by hand or guessed), as line ids. */
  linked: number[];
  /** The wait on the step, for the NEXT line (M2). */
  wait?: StepWait | null;
}

/** The steps in order, each with its section, skipping headings and empty steps. */
export function cookSteps(steps: StepIn[]): CookStep[] {
  const found: Omit<CookStep, 'number' | 'total'>[] = [];
  let section: string | null = null;
  for (const step of steps) {
    const text = step.text.trim();
    if (step.kind === 'heading') {
      section = text === '' ? null : text;
      continue;
    }
    if (text === '') continue;
    found.push({
      section,
      text,
      linked: (step.lines ?? []).map((l) => l.line_id),
      ...(step.wait ? { wait: step.wait } : {})
    });
  }
  return found.map((step, i) => ({ ...step, number: i + 1, total: found.length }));
}

// --- Timers in a step's words ------------------------------------------------------------

export interface FoundTimer {
  /** The words as written: "10 minutes", "1 hour 30 minutes". */
  words: string;
  seconds: number;
  /** Where the words start in the step, for tests and for ordering. */
  at: number;
}

const FRACTIONS: Record<string, number> = {
  '¼': 0.25,
  '½': 0.5,
  '¾': 0.75,
  '⅓': 1 / 3,
  '⅔': 2 / 3,
  '⅛': 0.125
};
const FRACTION_CLASS = '[¼½¾⅓⅔⅛]';
// A number: 1.5 · 1½ · 1 1/2 · 1/2 · ½ · 10. (A comma is not read as a decimal point: "1,5" could
// be a thousand.)
const NUMBER = `\\d+[.]\\d+|\\d+\\s?${FRACTION_CLASS}|\\d+\\s+\\d/\\d|\\d/\\d|${FRACTION_CLASS}|\\d+`;
const UNIT = 'hours?|hrs?|h|minutes?|mins?|seconds?|secs?';
// "10 minutes", "10-15 minutes", "10 to 15 minutes", "1 h". The unit is not the start of a word.
const PART = new RegExp(
  `(?<![\\p{L}\\d./])(${NUMBER})(?:\\s*(?:-|–|—|to)\\s*(?:${NUMBER}))?\\s*(${UNIT})(?![\\p{L}])`,
  'giu'
);
/** The most a timer can be (a day): anything longer is not a cooking time. */
const MOST_SECONDS = 24 * 3600;

function amountOf(words: string): number {
  const text = words.trim();
  const whole = /^(\d+)\s?([¼½¾⅓⅔⅛])$/.exec(text);
  if (whole) return Number(whole[1]) + (FRACTIONS[whole[2]!] ?? 0);
  if (text in FRACTIONS) return FRACTIONS[text]!;
  const mixed = /^(\d+)\s+(\d)\/(\d)$/.exec(text);
  if (mixed) return Number(mixed[1]) + Number(mixed[2]) / Number(mixed[3]);
  const simple = /^(\d)\/(\d)$/.exec(text);
  if (simple) return Number(simple[1]) / Number(simple[2]);
  return Number(text);
}

const secondsPer = (unit: string): number => {
  const u = unit.toLowerCase();
  return u.startsWith('h') ? 3600 : u.startsWith('m') ? 60 : 1;
};

/**
 * The timers a step's words ask for, in order: "simmer for 10 minutes" gives 10 minutes. A range
 * ("10-15 minutes") starts at its shorter end, so the food is never past it. "1 hour 30
 * minutes" is one timer.
 */
export function findTimers(text: string): FoundTimer[] {
  const parts: { at: number; end: number; seconds: number; unit: number }[] = [];
  for (const match of text.matchAll(PART)) {
    const value = amountOf(match[1]!);
    const unit = secondsPer(match[2]!);
    const seconds = Math.round(value * unit);
    if (!Number.isFinite(seconds) || seconds <= 0) continue;
    parts.push({ at: match.index, end: match.index + match[0].length, seconds, unit });
  }
  const timers: FoundTimer[] = [];
  let last: (typeof parts)[number] | null = null;
  for (const part of parts) {
    const gap = last ? text.slice(last.end, part.at) : '';
    // "1 hour 30 minutes", "1 hour and 30 minutes": a smaller unit straight after a larger.
    if (last && part.unit < last.unit && /^\s*(?:and\s+|,\s*)?$/i.test(gap)) {
      const open = timers[timers.length - 1]!;
      open.seconds += part.seconds;
      open.words = text.slice(open.at, part.end);
    } else {
      timers.push({ words: text.slice(part.at, part.end), seconds: part.seconds, at: part.at });
    }
    last = part;
  }
  return timers.filter((t) => t.seconds <= MOST_SECONDS);
}

/** 600 → "10:00", 5400 → "1:30:00". */
export function clock(seconds: number): string {
  const total = Math.max(0, Math.ceil(seconds));
  const h = Math.floor(total / 3600);
  const m = Math.floor((total % 3600) / 60);
  const s = total % 60;
  const two = (n: number) => String(n).padStart(2, '0');
  return h > 0 ? `${h}:${two(m)}:${two(s)}` : `${two(m)}:${two(s)}`;
}

// --- The ingredients a step seems to use -------------------------------------------------

/** The ways a name can be written in a step: the name itself and its plural. */
export function nameForms(name: string): string[] {
  const base = name.trim().toLowerCase();
  if (base === '') return [];
  const forms = new Set<string>([base]);
  if (/[^aeiou]y$/.test(base)) forms.add(`${base.slice(0, -1)}ies`);
  else if (/(s|x|z|ch|sh|o)$/.test(base)) forms.add(`${base}es`);
  else forms.add(`${base}s`);
  // Written the other way round: "onions" for an ingredient named "Onion" is the plural above;
  // an ingredient named "Chickpeas" is also met as "chickpea".
  if (base.endsWith('ies')) forms.add(`${base.slice(0, -3)}y`);
  else if (base.endsWith('s') && base.length > 3) forms.add(base.slice(0, -1));
  return [...forms];
}

const escape = (text: string) => text.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');

/** Whether the step's words include `form` as whole words. */
function mentions(text: string, form: string): boolean {
  return new RegExp(`(?<![\\p{L}\\d])${escape(form)}(?![\\p{L}\\d])`, 'iu').test(text);
}

/**
 * The ingredient lines a step uses. The links the server holds (set by hand, or guessed
 * when the recipe was saved) win; without any, the guess is made here from the step's words:
 * a step uses an ingredient when its words include the ingredient's name, its plural or one of
 * its other names (cabledrawer 31 Oct). Headings are never ingredients.
 */
export function stepLines(step: CookStep, lines: RecipeLine[]): RecipeLine[] {
  const ingredients = lines.filter((l) => l.kind === 'ingredient');
  if (step.linked.length > 0) {
    const set = new Set(step.linked);
    return ingredients.filter((l) => set.has(l.id));
  }
  return ingredients.filter((line) => {
    const names = [line.food?.name, ...(line.food?.other_names ?? []), line.recipe?.name];
    return names
      .filter((n): n is string => typeof n === 'string')
      .some((name) => nameForms(name).some((form) => mentions(step.text, form)));
  });
}
