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
  /** The step's id on the server (M3: the step that waits is found by it); null for a draft. */
  id?: number;
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
      ...(step.id === undefined ? {} : { id: step.id }),
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
const MAX_SECONDS = 24 * 3600;

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
  return timers.filter((t) => t.seconds <= MAX_SECONDS);
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

// F142 (cabledrawer 3 Nov): the guesses were poor. Three things made them so, each fixed below.

/** Chilli is spelt chilli, chili, chile, chillies, chilies...: all one word for matching. */
const CHILLI = /\bchill?(?:ies|is|i|es|e)\b/gi;
const fold = (text: string) => text.toLowerCase().replace(CHILLI, 'chilli');

/** Words a recipe puts before a name that a step often leaves out ("dried red chillies" on the
 *  line, "the red chillies" in the step). */
const MODIFIERS = new Set([
  'dried',
  'dry',
  'fresh',
  'raw',
  'ripe',
  'whole',
  'frozen',
  'large',
  'small'
]);

/** The part of a plant a word names. Seeds and leaves of one plant are different ingredients
 *  ("coriander seeds" is not "coriander leaves"). */
const PART_WORDS: Record<string, string> = {
  seed: 'seed',
  seeds: 'seed',
  leaf: 'leaf',
  leaves: 'leaf',
  stalk: 'stalk',
  stalks: 'stalk',
  stem: 'stalk',
  stems: 'stalk',
  root: 'root',
  roots: 'root',
  flower: 'flower',
  flowers: 'flower'
};
const partsIn = (text: string): Set<string> =>
  new Set(
    (fold(text).match(/\p{L}+/gu) ?? []).flatMap((word) =>
      PART_WORDS[word] === undefined ? [] : [PART_WORDS[word]!]
    )
  );

/** What a line is called, for matching: its ingredient's name and other names, the recipe it is,
 *  and the words as typed (without a note after a comma or a bracket), each also without a
 *  leading "dried", "fresh"... so "dried red chilies" is found as "red chillies". */
function namesOf(line: RecipeLine): string[] {
  const typed = line.words.split(/[,(;]/)[0]!.trim();
  const named = [line.food?.name, ...(line.food?.other_names ?? []), line.recipe?.name, typed]
    .filter((n): n is string => typeof n === 'string')
    .map((n) => fold(n).trim())
    .filter((n) => n !== '' && n.split(/\s+/).length <= 5);
  const all = new Set<string>();
  for (const name of named) {
    all.add(name);
    const words = name.split(/\s+/);
    let from = 0;
    while (from < words.length - 1 && MODIFIERS.has(words[from]!)) from++;
    if (from > 0) all.add(words.slice(from).join(' '));
  }
  return [...all];
}

/** Whether the step's words include `form` as whole words, as a different part of the plant
 *  than the line is (the line says leaves, the step says "coriander seeds") not counting. */
function mentions(text: string, form: string, parts: Set<string>): boolean {
  const found = new RegExp(`(?<![\\p{L}\\d])${escape(form)}(?![\\p{L}\\d])(\\s+\\p{L}+)?`, 'giu');
  for (const match of text.matchAll(found)) {
    const next = (match[1] ?? '').trim();
    const part = PART_WORDS[next];
    // The step names another part of the plant than the line does: not this line.
    if (part !== undefined && parts.size > 0 && !parts.has(part)) continue;
    return true;
  }
  return false;
}

/**
 * The ingredient lines a step uses. The links the server holds (set by hand, or guessed
 * when the recipe was saved) win; without any, the guess is made here from the step's words:
 * a step uses an ingredient when its words include the ingredient's name, its plural or one of
 * its other names (cabledrawer 31 Oct), spelt any way and with or without "dried", "fresh"... (F142
 * case c), and not when the step names another part of the plant ("coriander seeds" is not
 * "coriander leaves", F142 case a). Headings are never ingredients.
 */
export function stepLines(step: CookStep, lines: RecipeLine[]): RecipeLine[] {
  const ingredients = lines.filter((l) => l.kind === 'ingredient');
  if (step.linked.length > 0) {
    const set = new Set(step.linked);
    return ingredients.filter((l) => set.has(l.id));
  }
  const text = fold(step.text);
  return ingredients.filter((line) => {
    const parts = partsIn(
      [line.words, line.food?.name, ...(line.food?.other_names ?? [])].join(' ')
    );
    return namesOf(line).some((name) =>
      nameForms(name).some((form) => mentions(text, form, parts))
    );
  });
}

/**
 * The lines that more than one step uses (F142 case b): "2 cups water" is used by the dal, the
 * vegetables and the sambar, and showing the full amount on each of them says it is used three
 * times over. A shared line is shown without its amount in a step's own list (the step's words
 * say how much, and "Show ingredients" has the full amount). Proposed, for cabledrawer.
 */
export function sharedLineIds(steps: CookStep[], lines: RecipeLine[]): Set<number> {
  const uses = new Map<number, number>();
  for (const step of steps) {
    for (const line of stepLines(step, lines)) uses.set(line.id, (uses.get(line.id) ?? 0) + 1);
  }
  return new Set([...uses].filter(([, n]) => n > 1).map(([id]) => id));
}
