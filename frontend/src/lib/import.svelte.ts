// Importing a recipe, the screen's state (docs/dev/recipe-import.md): the one box, what the
// server read (the review), the choices made on the review, and Save. Nothing here is saved
// until Save, and nothing is queued: it needs the server (spec: online only).

import { ApiError, cantReach } from './api';
import { changeDraft, keepDraft, type DraftBody, type DraftOut } from './client/drafts';
import { deletePhoto } from './client/recipes';
import { drafts } from './drafts.svelte';
import {
  saveImport,
  startImport,
  type ImportReview,
  type LineLink,
  type NewIngredient,
  type ReviewLine,
  type Saved,
  type SaveBody,
  type SaveLine
} from './client/imports';
import type { CountedAs, Pints, Ref } from './client/types';
import { newChangeId } from './changeId';
import { MOST_STEPS, splitStep } from './importSteps';

/** What a line was set to on the review (a line that is matched needs no choice). */
export type Choice =
  | { kind: 'ingredient'; food: Ref; learn: boolean }
  | { kind: 'new' | 'staple'; name: string; counted_as: CountedAs; place_id: number | null };

/** Why the box didn't give a review: the server's sentence, and what the screen offers. */
export interface ImportProblem {
  code: string;
  message: string;
  /** The link switch is off: the screen links to Settings → Privacy (for an admin). */
  switchedOff: boolean;
  /** Whether the person can switch it on themselves. */
  admin: boolean;
}

/** "You already have this recipe": the recipe, for Open it / Import again as a copy. */
export interface Already {
  recipe: Ref;
  site: string;
  importedAt: string;
  photo: { list_url: string; list_width: number; list_height: number } | null;
}

/** Several links in the box (F25). */
export const LINKS_ONE_AT_A_TIME = 'Several links · one link at a time: only the first is read';

export const OFFLINE_NOTE =
  'Importing needs your Mealwright server. Try again when you’re back online.';
/** Keeping a draft didn't reach the server (proposed, for cabledrawer). */
export const DRAFT_OFFLINE =
  'Saving a draft needs your Mealwright server. Try again when you’re back online.';
const COULDNT = 'Couldn’t read that. Try again.';

export class ImportFlow {
  text = $state('');
  /** start: the box · reading: waiting for the server · review: what came across. */
  phase = $state<'start' | 'reading' | 'review'>('start');
  problem = $state<ImportProblem | null>(null);
  already = $state<Already | null>(null);
  review = $state<ImportReview | null>(null);
  choices = $state<Record<number, Choice>>({});
  /** The summary boxes the person can change on the review. */
  /** The pint this recipe's pint lines are read with now: the review's own until the switch
   *  on a US recipe is used (for this recipe only; the household's setting never changes). */
  pints = $state<Pints>('uk');
  name = $state('');
  serves = $state('');
  minutes = $state('');
  saving = $state(false);
  saveProblem = $state<{ message: string; line: number | null } | null>(null);
  /** Chosen on purpose: the Save went through once. */
  saved = $state<Saved | null>(null);

  /** The draft this review is kept in, once it has been kept as one (or was opened from one). */
  draftId = $state<number | null>(null);
  /** Keeping the draft is on its way. */
  keeping = $state(false);
  /** Keeping the draft didn't work: the server's sentence ("You have 50 drafts. …"). */
  draftProblem = $state<string | null>(null);

  /** F6: a line that took the choice made on another line, and which line that was. Not kept
   *  in a draft; it only explains "Also used for 1 more line". */
  sharedFrom = $state<Record<number, number>>({});
  /** F4: Save found lines with no ingredient. The lines to go through, one at a time, and where
   *  the person is among them; null when the sheet isn't open. */
  walk = $state<{ queue: number[]; at: number } | null>(null);
  /** F13: the step whose split is shown for a look (nothing changes until Keep the split). */
  previewStep = $state<number | null>(null);
  /** F13: the steps as they were before any split, so the split can be put back. */
  stepsBefore = $state<ImportReview['steps'] | null>(null);

  #saveKey = newChangeId();
  #draftKey = newChangeId();
  /** The boxes and choices as they were when the draft was last kept or opened. */
  #kept = '';

  get isLink(): boolean {
    return this.linkCount > 0;
  }

  /** How many links the box holds when it holds nothing but links, separated by spaces or line
   *  breaks (0 for anything else). The server reads one link at a time: the first (F25). */
  get linkCount(): number {
    const words = this.text.split(/\s+/).filter(Boolean);
    const link = (w: string) => /^(https?:\/\/|www\.)\S+$/i.test(w) || /^\S+:\/\/\S*$/.test(w);
    return words.length > 0 && words.every(link) ? words.length : 0;
  }

  /** Read what is in the box. `again`: import a link again as a copy. */
  async read(again = false): Promise<void> {
    if (this.phase === 'reading') return;
    const text = this.text.trim();
    if (!text) {
      this.problem = problemOf('nothing_given', 'Paste a link or the recipe’s text.');
      return;
    }
    this.phase = 'reading';
    this.problem = null;
    this.already = null;
    try {
      this.show(await startImport(text, again));
    } catch (error) {
      this.phase = 'start';
      if (error instanceof ApiError) this.fail(error);
      else this.problem = problemOf('failed', COULDNT);
    }
  }

  private fail(error: ApiError): void {
    if (cantReach(error)) {
      this.problem = problemOf('offline', OFFLINE_NOTE);
      return;
    }
    const body = (error.body ?? {}) as Record<string, unknown>;
    if (error.code === 'already_imported') {
      const photo = (body.photo ?? null) as Already['photo'];
      this.already = {
        recipe: body.recipe as Ref,
        site: String(body.site ?? ''),
        importedAt: String(body.imported_at ?? ''),
        photo
      };
      return;
    }
    this.problem = {
      code: error.code ?? 'failed',
      message: error.detail,
      switchedOff: error.code === 'import_switched_off',
      admin: body.admin === true
    };
  }

  private show(review: ImportReview): void {
    this.review = review;
    this.choices = {};
    this.sharedFrom = {};
    this.walk = null;
    this.previewStep = null;
    this.stepsBefore = null;
    this.pints = review.pints?.reading ?? 'uk';
    this.name = review.name;
    this.serves = review.serves === null ? '' : String(review.serves);
    this.minutes = review.time_minutes === null ? '' : String(review.time_minutes);
    this.saveProblem = null;
    this.draftId = null;
    this.draftProblem = null;
    this.#saveKey = newChangeId();
    this.#draftKey = newChangeId();
    this.phase = 'review';
  }

  // --- Drafts ---------------------------------------------------------------------------------

  /** Carry on from a draft: the review as it was kept, with every choice made so far. */
  load(draft: DraftOut): void {
    this.text = draft.text;
    this.show(draft.review);
    const kept = draft.choices;
    if (kept.name !== null) this.name = kept.name;
    if (kept.serves !== null) this.serves = kept.serves;
    if (kept.minutes !== null) this.minutes = kept.minutes;
    if (kept.pints) this.pints = kept.pints;
    const choices: Record<number, Choice> = {};
    for (const [index, choice] of Object.entries(kept.lines)) choices[Number(index)] = choice;
    this.choices = choices;
    this.draftId = draft.id;
    this.#kept = this.#state();
  }

  /** The boxes and choices, in one piece, to tell whether anything changed since. */
  #state(): string {
    const lines = Object.keys(this.choices)
      .map(Number)
      .sort((a, b) => a - b)
      .map((index) => [index, this.choices[index]]);
    return JSON.stringify([
      this.name,
      this.serves,
      this.minutes,
      this.pints,
      lines,
      this.review?.lines,
      this.review?.steps
    ]);
  }

  /** A draft this was opened from, changed since it was last kept: leaving asks. A review not
   *  kept as a draft yet always asks. */
  get unkept(): boolean {
    return this.draftId === null || this.#state() !== this.#kept;
  }

  /** What a draft keeps: the box, the review as read and the choices so far. */
  draftBody(): DraftBody | null {
    const review = this.review;
    if (!review) return null;
    const lines: DraftBody['choices']['lines'] = {};
    for (const [index, choice] of Object.entries(this.choices)) lines[index] = choice;
    return {
      text: this.text.trim(),
      review,
      choices: {
        name: this.name,
        serves: this.serves,
        minutes: this.minutes,
        pints: this.pints === (review.pints?.reading ?? 'uk') ? null : this.pints,
        lines
      }
    };
  }

  /** Keep this review as a draft (the first time), or save over the draft it was opened from.
   *  True when it is kept; otherwise `draftProblem` says why. */
  async keepAsDraft(): Promise<boolean> {
    const body = this.draftBody();
    if (!body || this.keeping) return false;
    this.keeping = true;
    this.draftProblem = null;
    try {
      const kept =
        this.draftId === null
          ? await keepDraft(body, this.#draftKey)
          : await changeDraft(this.draftId, body);
      this.draftId = kept.id;
      this.#kept = this.#state();
      void drafts.load();
      return true;
    } catch (error) {
      this.draftProblem =
        error instanceof ApiError
          ? cantReach(error)
            ? DRAFT_OFFLINE
            : error.detail
          : 'Couldn’t keep the draft. Try again.';
      return false;
    } finally {
      this.keeping = false;
    }
  }

  /** Let go of the photo this review is waiting with (F92): Discard, and going back to the box,
   *  delete it at once so ten reads that were never saved don't block the next. A draft's photo
   *  stays (the draft owns it), and a saved recipe has taken it. Never throws: a photo that can't
   *  be deleted now is deleted by the server's hourly tidy-up within 24 hours. */
  async dropPhoto(): Promise<void> {
    const shown = this.review?.photo;
    if (!shown || shown.state !== 'downloaded' || !shown.photo) return;
    if (this.draftId !== null || this.saved) return;
    const id = shown.photo.id;
    // The review no longer holds it, so a second Discard doesn't ask again.
    this.review = { ...this.review!, photo: { state: 'none', photo: null, message: null } };
    try {
      await deletePhoto(id);
    } catch {
      // gone already, or the server can't be reached: the tidy-up takes it
    }
  }

  /** Back to the box, keeping what was typed (Paste text instead, Cancel on a sheet). */
  backToBox(): void {
    void this.dropPhoto();
    this.phase = 'start';
    this.review = null;
    this.already = null;
  }

  // --- Pints ----------------------------------------------------------------------------------

  /** The card "This looks like a US recipe" shows: a US page, read for a UK household. */
  get offersPints(): boolean {
    const pints = this.review?.pints;
    return !!pints && pints.us_site && pints.household === 'uk';
  }

  /** The line as it reads with the pint chosen now: a pint line takes the amount for that
   *  pint (in ml); every other line is as it came. */
  withPints(line: ReviewLine): ReviewLine {
    if (!line.pint_ml) return line;
    const ml = this.pints === 'us' ? line.pint_ml.us_ml : line.pint_ml.uk_ml;
    if (line.amount === ml && line.unit === 'ml') return line;
    return { ...line, amount: ml, amount_text: amountWords(ml), unit: 'ml' };
  }

  /** The first line that says pints, with what it reads as in the other pint: "Switch it off
   *  and the milk reads 1.14 L (UK pints)." Null when no line says pints. */
  get otherPints(): { words: string; reads: string; kind: Pints } | null {
    const line = this.review?.lines.find((l) => l.kind === 'ingredient' && l.pint_ml);
    if (!line?.pint_ml) return null;
    const kind: Pints = this.pints === 'us' ? 'uk' : 'us';
    const ml = kind === 'us' ? line.pint_ml.us_ml : line.pint_ml.uk_ml;
    return { words: (line.food?.name ?? line.words).toLowerCase(), reads: volumeWords(ml), kind };
  }

  // --- The review's choices ---------------------------------------------------------------

  choose(index: number, choice: Choice | null): void {
    const next = { ...this.choices };
    if (choice === null) delete next[index];
    else next[index] = choice;
    this.choices = next;
    this.saveProblem = null;
  }

  /** Take back the choice on a line (Change). A line that followed another stops following. */
  unchoose(index: number): void {
    this.choose(index, null);
    if (index in this.sharedFrom) {
      const from = { ...this.sharedFrom };
      delete from[index];
      this.sharedFrom = from;
    }
  }

  // --- Fixing what was read (F30.6) ----------------------------------------------------------

  /** The amount, unit or note of a line, fixed by hand. The change lives in the review itself,
   *  so a draft keeps it and Save sends it. A line read with the pint switch stops following
   *  it once its amount or unit is changed. */
  editLine(
    index: number,
    patch: {
      amount?: number | null;
      amount_text?: string | null;
      unit?: string | null;
      note?: string | null;
    }
  ): void {
    const line = this.review?.lines[index];
    if (!line || line.kind !== 'ingredient') return;
    if (('amount' in patch || 'unit' in patch) && line.pint_ml) {
      Object.assign(line, this.withPints(line));
      line.pint_ml = null;
    }
    Object.assign(line, patch);
    if ('unit' in patch) line.size = null;
    this.saveProblem = null;
  }

  /** "Same as Onions" on a line that is to confirm (its best guess) or one picked from the list. */
  sameAs(index: number, food: Ref): void {
    const choice: Choice = { kind: 'ingredient', food, learn: true };
    this.choose(index, choice);
    this.#share(index, choice);
  }

  /** What a new ingredient for this line starts as: the reader's guess, else the line's words. */
  guessFor(index: number): NewIngredient | null {
    const line = this.review?.lines[index];
    if (!line || line.kind !== 'ingredient') return null;
    if (line.new_ingredient) return line.new_ingredient;
    const words = line.words.trim();
    return {
      name: words ? words[0]!.toUpperCase() + words.slice(1) : '',
      counted_as: 'weight',
      place: null
    };
  }

  newIngredient(index: number, staple = false): void {
    const guess = this.guessFor(index);
    if (!guess) return;
    const choice: Choice = {
      kind: staple ? 'staple' : 'new',
      name: guess.name,
      counted_as: guess.counted_as,
      place_id: guess.place?.id ?? null
    };
    this.choose(index, choice);
    this.#share(index, choice);
  }

  /** Make a new ingredient a staple, or not (the tick in the New ingredient form). The lines
   *  that took its choice follow. */
  setStaple(index: number, staple: boolean): void {
    for (const at of [index, ...this.followers(index)]) {
      const choice = this.choices[at];
      if (choice && choice.kind !== 'ingredient') {
        this.choose(at, { ...choice, kind: staple ? 'staple' : 'new' });
      }
    }
  }

  /** The lines that took this line's choice (F6), for "Also used for 1 more line". */
  followers(index: number): number[] {
    return Object.entries(this.sharedFrom)
      .filter(([, from]) => from === index)
      .map(([j]) => Number(j));
  }

  /** F6: once an ingredient is made or picked on one line, the lines of the same import that
   *  read as the same thing take the same choice. Only lines with no choice yet that still
   *  need one; each can be changed on its own. Matching is on the whole name (case and
   *  spacing ignored), never on part of one. */
  #share(index: number, choice: Choice): void {
    const review = this.review;
    const source = review?.lines[index];
    if (!review || !source) return;
    const keys = nameKeys(source, choice.kind === 'ingredient' ? null : choice.name);
    const next = { ...this.choices };
    const from = { ...this.sharedFrom };
    review.lines.forEach((line, j) => {
      if (j === index || line.kind !== 'ingredient' || next[j]) return;
      if (line.label !== 'to_confirm' && line.label !== 'needs_you') return;
      if (!nameKeys(line, null).some((key) => keys.includes(key))) return;
      next[j] = choice.kind === 'ingredient' ? { ...choice, learn: true } : { ...choice };
      from[j] = index;
    });
    this.choices = next;
    this.sharedFrom = from;
  }

  /** The ingredient a line will be tied to, or null: a choice, else a match. */
  linkOf(index: number): Choice | null {
    const chosen = this.choices[index];
    if (chosen) return chosen;
    const line = this.review?.lines[index];
    if (line && (line.label === 'matched' || line.label === 'staple') && line.food) {
      return { kind: 'ingredient', food: line.food, learn: false };
    }
    return null;
  }

  /** The header's counts as the lines stand now (F93): a line with a choice (a new ingredient,
   *  a pick, "Same as") is ready, so it counts as matched; a new staple counts as a staple;
   *  taking a choice back (Change) puts the line back where the reader had it. Headings are
   *  not counted. The same states as each line's dot. */
  get counts(): ImportReview['counts'] {
    const counts = { matched: 0, to_confirm: 0, needs_you: 0, staple: 0 };
    this.review?.lines.forEach((line, i) => {
      if (line.kind !== 'ingredient') return;
      const choice = this.choices[i];
      if (choice) counts[choice.kind === 'staple' ? 'staple' : 'matched']++;
      else if (line.label && line.label in counts) counts[line.label]++;
    });
    return counts;
  }

  /** How many lines will be saved with no ingredient behind them (words only). */
  get unlinked(): number {
    const review = this.review;
    if (!review) return 0;
    return review.lines.filter((line, i) => line.kind === 'ingredient' && !this.linkOf(i)).length;
  }

  // --- Save ---------------------------------------------------------------------------------

  /** The body Save sends: the review's recipe with the changes made on this screen. */
  body(): SaveBody | null {
    const review = this.review;
    if (!review) return null;
    const serves = this.serves.trim() === '' ? null : Number(this.serves);
    const time = this.minutes.trim() === '' ? null : Number(this.minutes);
    return {
      name: this.name.trim(),
      description: review.description,
      time_minutes: time,
      serves,
      makes: review.makes,
      tags: review.tags,
      nutrition: review.nutrition,
      lines: review.lines.map((line, i) => saveLine(this.withPints(line), this.linkOf(i))),
      steps: review.steps,
      source_url: review.source.url,
      source_author: review.author,
      photo_id: review.photo.photo?.id ?? null,
      draft_id: this.draftId
    };
  }

  /** The box for Serves or Time holds something that isn't a whole number in range. */
  get numbersOk(): boolean {
    const whole = (text: string, most: number) =>
      text.trim() === '' || (/^\d+$/.test(text.trim()) && +text >= 1 && +text <= most);
    return whole(this.serves, 99) && whole(this.minutes, 14_400);
  }

  /** Save, but with lines that have no ingredient behind them, first the sheet that goes through
   *  them one at a time (F4). `save()` itself never asks. */
  async trySave(): Promise<Saved | null> {
    const queue = this.unlinkedLines();
    if (queue.length > 0) {
      this.walk = { queue, at: 0 };
      return null;
    }
    return this.save();
  }

  /** The places of the ingredient lines with no ingredient behind them. */
  unlinkedLines(): number[] {
    const lines = this.review?.lines ?? [];
    return lines.flatMap((line, i) => (line.kind === 'ingredient' && !this.linkOf(i) ? [i] : []));
  }

  /** The line the sheet is on, or null when it isn't open. */
  get walkLine(): number | null {
    return this.walk ? (this.walk.queue[this.walk.at] ?? null) : null;
  }

  /** On to the next line that still has no ingredient (Skip, or the line was just settled).
   *  After the last one the sheet closes, or, with lines still unlinked, shows its last card. */
  walkNext(): void {
    const walk = this.walk;
    if (!walk) return;
    let at = walk.at + 1;
    while (at < walk.queue.length && this.linkOf(walk.queue[at]!)) at++;
    if (at < walk.queue.length) this.walk = { queue: walk.queue, at };
    // The last line is done. Lines still unlinked keep the sheet open on its last card (Save
    // anyway or Back to Check), so Skip never drops back to Check with the same sheet waiting.
    else this.walk = this.unlinkedLines().length > 0 ? { queue: walk.queue, at } : null;
  }

  /** Back to Check, with nothing saved. */
  walkClose(): void {
    this.walk = null;
  }

  /** Save anyway: whatever is still not linked is saved as words. */
  async saveAnyway(): Promise<Saved | null> {
    this.walk = null;
    return this.save();
  }

  // --- Steps (F13) ---------------------------------------------------------------------------

  /** How step `i` would read as shorter steps, or null when it isn't a long step. */
  splitOf(i: number): string[] | null {
    const review = this.review;
    const step = review?.steps[i];
    if (!review || !step || step.kind !== 'step') return null;
    const pieces = splitStep(step.text);
    if (!pieces) return null;
    return review.steps.length - 1 + pieces.length > MOST_STEPS ? null : pieces;
  }

  /** Keep the split of step `i`. */
  keepSplit(i: number): void {
    const review = this.review;
    const pieces = this.splitOf(i);
    if (!review || !pieces) return;
    if (!this.stepsBefore) this.stepsBefore = review.steps.map((s) => ({ ...s }));
    review.steps = [
      ...review.steps.slice(0, i),
      ...pieces.map((text) => ({ kind: 'step' as const, text })),
      ...review.steps.slice(i + 1)
    ];
    this.previewStep = null;
  }

  /** Put the steps back as the page had them. */
  putStepsBack(): void {
    if (!this.review || !this.stepsBefore) return;
    this.review.steps = this.stepsBefore;
    this.stepsBefore = null;
    this.previewStep = null;
  }

  async save(): Promise<Saved | null> {
    const body = this.body();
    if (!body || this.saving) return null;
    if (!body.name) {
      this.saveProblem = { message: 'Type a name.', line: null };
      return null;
    }
    if (!this.numbersOk) {
      this.saveProblem = {
        message: 'Serves is 1 to 99, and the time is whole minutes, up to 14,400.',
        line: null
      };
      return null;
    }
    this.saving = true;
    this.saveProblem = null;
    try {
      this.saved = await saveImport(body, this.#saveKey);
      if (this.draftId !== null) void drafts.load(); // the draft is a recipe now
      return this.saved;
    } catch (error) {
      if (error instanceof ApiError) {
        const line = (error.body as { line?: unknown } | null)?.line;
        this.saveProblem = {
          message: cantReach(error) ? OFFLINE_NOTE : error.detail,
          line: typeof line === 'number' ? line : null
        };
      } else {
        this.saveProblem = { message: 'Couldn’t save. Try again.', line: null };
      }
      return null;
    } finally {
      this.saving = false;
    }
  }
}

/** The names a line might be called, folded: its words, the reader's guess and the name
 *  "Same as" would add; plus a name typed for a new ingredient. */
function nameKeys(line: ReviewLine, typed: string | null): string[] {
  const keys: string[] = [];
  for (const text of [line.words, line.new_ingredient?.name, line.learn_name, typed]) {
    const key = (text ?? '').toLowerCase().split(/\s+/).filter(Boolean).join(' ');
    if (key && !keys.includes(key)) keys.push(key);
  }
  return keys;
}

function problemOf(code: string, message: string): ImportProblem {
  return { code, message, switchedOff: false, admin: false };
}

/** 946 → "946", 189.333 → "189.333": a number as the review shows an amount. */
export function amountWords(value: number): string {
  return String(Math.round(value * 1000) / 1000);
}

/** A volume in ml in plain words: 946 → "946 ml", 1136 → "1.14 L". */
export function volumeWords(ml: number): string {
  return ml >= 1000 ? `${Math.round(ml / 10) / 100} L` : `${amountWords(ml)} ml`;
}

function saveLine(line: ReviewLine, link: Choice | null): SaveLine {
  let sent: LineLink | null = null;
  if (line.kind === 'ingredient' && link) {
    sent =
      link.kind === 'ingredient'
        ? { kind: 'ingredient', food_id: link.food.id, learn: link.learn ? line.learn_name : null }
        : {
            kind: link.kind,
            name: link.name,
            counted_as: link.counted_as,
            place_id: link.place_id
          };
  }
  return {
    kind: line.kind,
    words: line.words,
    amount: line.amount,
    unit: line.unit,
    size_id: sent?.kind === 'ingredient' ? (line.size?.id ?? null) : null,
    note: line.note,
    link: sent
  };
}

/** "4 lines after “Tips” were left out": the sentence for the review (spec Q17). */
export function leftOutWords(heading: string, lines: number): string {
  return `${lines} ${lines === 1 ? 'line' : 'lines'} after “${heading}” ${lines === 1 ? 'was' : 'were'} left out`;
}
