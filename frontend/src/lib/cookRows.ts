// The "Cooked it" review's rows: what each one shows and what it sends back. Pure, so the
// rules are tested without a screen. The words are proposed, for cabledrawer (words.md section 28).

import { readNumber } from './amountText.js';
import type { CookChoice, CookRow, Need } from './client/cook';
import type { Answer, Ask } from './client/types';
import { NBSP } from './words.js';


/** What the person did on one row (a row they never touched is as the server proposed it). */
export interface RowState {
  /** The Use switch; undefined: as proposed. */
  use?: boolean;
  /** Typed in the pantry's unit: how much was used, or how much is left. */
  mode: 'used' | 'left';
  value: number | null;
  /** "Bought some — used them". */
  bought: boolean;
  /** The row's own tick for the shopping list; undefined: as proposed. */
  addToList?: boolean;
  /** Take from the freezer too. */
  fromFreezer: boolean;
}

export const newRowState = (): RowState => ({
  mode: 'used',
  value: null,
  bought: false,
  fromFreezer: false
});

/** g and ml: under 10 to one place (at least 0.1), from 10 whole; counts to two places (F132). */
export function roundForScreen(n: number, unit: 'g' | 'ml' | 'count' | null = null): number {
  if (unit === 'count' || unit == null) return Math.round(n * 100) / 100;
  if (n === 0) return 0;
  const sign = n < 0 ? -1 : 1;
  const abs = Math.abs(n);
  if (abs < 10) {
    const rounded = Math.round(abs * 10) / 10;
    return sign * (rounded === 0 ? 0.1 : rounded);
  }
  return sign * Math.round(abs);
}

/** 1.5 as "1½", 0.5 as "½", 2 as "2"; anything else to two places. g and ml use roundForScreen. */
export function numberWords(n: number, unit: 'g' | 'ml' | 'count' | null = null): string {
  if (unit === 'g' || unit === 'ml') return String(roundForScreen(n, unit));
  const whole = Math.floor(n + 1e-9);
  const rest = Math.round((n - whole) * 100) / 100;
  const part = ({ 0.25: '¼', 0.5: '½', 0.75: '¾' } as Record<number, string>)[rest];
  if (rest === 0) return String(whole);
  if (part) return whole === 0 ? part : `${whole}${part}`;
  return String(Math.round(n * 100) / 100);
}

/** "300 g", "250 ml", or just the number for a count. */
export function amountWords(n: number, unit: 'g' | 'ml' | 'count' | null): string {
  const text = numberWords(n, unit);
  return unit === 'g' || unit === 'ml' ? `${text}${NBSP}${unit}` : text;
}

/**
 * An ingredient's name as a row of the "Cooked it" review shows it (RF5): the first letter a
 * capital, the rest as written, so "toor dal", "Onion" and "chicken thighs" read alike
 * ("Toor dal", "Onion", "Chicken thighs"), as the ingredient lists and the mockup do. A name
 * with other capitals in it ("TVP") keeps them.
 */
export const upperFirst = (name: string) =>
  name ? `${name.charAt(0).toLocaleUpperCase('en-GB')}${name.slice(1)}` : name;

/** An ingredient's name inside a sentence: "Eggs" is "eggs", "MSG" stays (F133). */
export const nameInSentence = (name: string) =>
  name.length > 1 && /[a-z]/.test(name[1]!) ? `${name[0]!.toLowerCase()}${name.slice(1)}` : name;

/**
 * What goes on the shopping list, for "Add … to the shopping list" (F133, cabledrawer 6 Nov): a bare
 * count says what it counts, "2 left" is "2 eggs"; an amount with a unit or a size word stays.
 */
export function listAmountWords(amount: string, name: string): string {
  const text = amount.replace(/[\s\u00a0]+left$/, '').trim();
  return /^[\d.,½¼¾\s\u00a0]+$/.test(text) ? `${text} ${nameInSentence(name)}` : text;
}

/** The ingredient's own take: the first one that is not a stand-in. */
export const ownTake = (row: CookRow) => row.takes.find((t) => !t.stand_in) ?? null;

/** Whether a row has a Use switch to show: an ingredient that is not a staple. */
export const hasSwitch = (row: CookRow) =>
  row.food !== null && row.status !== 'staple' && row.status !== 'not_linked';

/** Whether the row needs an answer from the person before it can be worked out. */
export const needsAnswer = (row: CookRow) =>
  row.status === 'ask' || (row.status === 'no_amount' && row.count_note !== null);

/** What the Use switch shows now. An unanswered question starts off: it never blocks (F106). */
export function isUsed(row: CookRow, state: RowState | undefined): boolean {
  if (state?.bought) return false;
  if (state?.use !== undefined) return state.use;
  if (row.status === 'ask' || row.status === 'no_amount') return false;
  return row.use;
}

export interface Shown {
  /** The Use switch. */
  use: boolean;
  /** Taken in all, in the pantry's unit. */
  taken: number;
  before: number | null;
  after: number | null;
}

/** What a row would take now, with the person's say on it. */
export function shown(row: CookRow, state: RowState | undefined): Shown {
  const use = isUsed(row, state);
  const own = ownTake(row);
  const before = own?.before.amount ?? row.takes[0]?.before.amount ?? null;
  const proposed = row.takes.reduce((sum, t) => sum + t.amount.amount, 0);
  if (!use) return { use, taken: 0, before, after: before };
  if (state?.value != null && before !== null) {
    const taken =
      state.mode === 'used' ? Math.min(state.value, before) : Math.max(before - state.value, 0);
    return { use, taken, before, after: before - taken };
  }
  return { use, taken: proposed, before, after: before === null ? null : before - proposed };
}

/** The choices to send: only the rows the person touched; the rest are as proposed. */
export function choicesOf(rows: CookRow[], states: Record<string, RowState>): CookChoice[] {
  const out: CookChoice[] = [];
  for (const row of rows) {
    const state = states[row.key];
    if (!state || !hasSwitch(row)) continue;
    if (state.bought) {
      out.push({ key: row.key, bought: true });
      continue;
    }
    const choice: CookChoice = { key: row.key };
    let touched = false;
    const use = isUsed(row, state);
    if (state.use !== undefined || use !== row.use) {
      choice.use = use;
      touched = true;
    }
    if (use && state.value != null) {
      const unit = row.unit ?? 'g';
      choice[state.mode === 'used' ? 'used' : 'left'] = { amount: state.value, unit };
      touched = true;
    }
    if (state.fromFreezer) {
      choice.from_freezer = true;
      touched = true;
    }
    if (state.addToList !== undefined && state.addToList !== row.add_to_list) {
      choice.add_to_list = state.addToList;
      touched = true;
    }
    if (touched) out.push(choice);
  }
  return out;
}

const round = (n: number, places = 3) => Math.round(n * 10 ** places) / 10 ** places;

/**
 * What a typed amount in the pantry's unit says about the conversion, as the answer the server
 * saves (F106). Null when one number cannot settle it (cups against a count: two figures are
 * missing), or the figure is not sensible; the screen then asks the old way.
 */
export function conversionAnswer(
  ask: Ask,
  need: Need | null,
  pantry: 'g' | 'ml' | 'count' | null,
  typed: number,
  remember: boolean
): Answer | null {
  if (!need || !pantry || !(typed > 0) || !(need.amount > 0)) return null;
  let grams: number | null = null;
  if (ask.kind === 'weight_per_ml') {
    const cup = ask.cup_ml ?? 0;
    if (!(cup > 0)) return null;
    if (need.unit === 'g' && pantry === 'ml') grams = (need.amount / typed) * cup;
    else if (need.unit === 'ml' && pantry === 'g') grams = (typed / need.amount) * cup;
  } else if (ask.kind === 'item_weight') {
    if (need.unit === 'item' && pantry === 'g') grams = typed / need.amount;
    else if (need.unit === 'g' && pantry === 'count') grams = need.amount / typed;
  }
  if (grams === null) return null;
  grams = round(grams, 2);
  const most = ask.kind === 'weight_per_ml' ? 2000 : 50000;
  if (!(grams > 0) || grams > most) return null;
  return { kind: ask.kind, food_id: ask.food_id, grams, remember } as Answer;
}

/** "2 cloves" and the amount typed for them: the ingredient's size "clove" (F89). */
export function sizeAnswer(
  foodId: number,
  note: { count: number; word: string },
  typed: number
): Answer | null {
  if (!(typed > 0) || !(note.count > 0)) return null;
  const amount = round(typed / note.count, 3);
  return amount > 0 ? { kind: 'size', food_id: foodId, name: note.word, amount } : null;
}

/** Keep one answer for each question: a newer one replaces the older (same ingredient and kind). */
export const MAX_ANSWERS = 20;

/** Say so when an answer cannot be kept because the server takes at most MAX_ANSWERS. */
export const TOO_MANY_ANSWERS = 'Too many questions at once. Answer these first, then Confirm.';

export function withAnswer(answers: Answer[], next: Answer): Answer[] {
  const same = (a: Answer) =>
    a.food_id === next.food_id &&
    a.kind === next.kind &&
    (a.kind !== 'size' || (next.kind === 'size' && a.name === next.name));
  const rest = answers.filter((a) => !same(a));
  return rest.length >= MAX_ANSWERS ? answers : [...rest, next];
}

/** The unit word next to a typed amount: "g", "ml", or the ingredient's count word. */
export const unitLabel = (row: CookRow): string =>
  row.unit === 'g' || row.unit === 'ml' ? row.unit : (row.unit_word ?? row.food?.name ?? '');

/** A typed amount: "2", "1,5", "¼", "1½", "1/2", "10/3". NaN when it isn't one. The reader is
 * the one in amountText.ts (FE3), so "10/3" is ten thirds here too. */
export function parseAmountText(text: string): number {
  const t = text.trim();
  if (/^\.\d+$/.test(t)) return Number(t);
  if (/^0+(?:[.,]0+)?$/.test(t)) return 0; // nothing taken is a real answer here
  return readNumber(t) ?? NaN;
}

/** The recipe's own words for a row, "1½ tbsp jaggery": each side keeps its own unit (F106). */
export const recipeSays = (row: CookRow): string =>
  row.lines.map((l) => [l.amount, l.unit, l.words].filter((part) => part).join(' ')).join(' + ');

/** Whether a row's recipe side and pantry side are in different units (so it says both). */
export const unitsDiffer = (row: CookRow): boolean =>
  row.estimate || row.status === 'ask' || (row.status === 'no_amount' && row.count_note !== null);

/** How many rows would change the pantry (the footer line). */
export function changeCount(rows: CookRow[], states: Record<string, RowState>): number {
  return rows.filter((row) => shown(row, states[row.key]).taken > 0).length;
}
