// Importing a recipe, the screen's state (docs/dev/recipe-import.md): the one box, what the
// server read (the review), the choices made on the review, and Save. Nothing here is saved
// until Save, and nothing is queued: it needs the server (spec: online only).

import { ApiError, cantReach } from './api';
import { changeDraft, keepDraft, type DraftBody, type DraftOut } from './client/drafts';
import { listFoods } from './client/foods';
import { deletePhoto, listRecipes } from './client/recipes';
import { fold } from './recipes/search';
import { drafts } from './drafts.svelte';
import { needsServer } from './downWords';
import { network } from './network.svelte';
import {
  saveImport,
  startImport,
  type ImportReview,
  type LineLink,
  type NewIngredient,
  type ReviewLine,
  type Saved,
  type SaveBody,
  type SaveLine,
  type SaveOwnRecipe
} from './client/imports';
import type { CountedAs, FoodRow, Pints, Ref } from './client/types';
import { newChangeId } from './changeId';
import { toasts } from './toast.svelte';
import { undoHistory, type UndoEntry } from './undo.svelte';
import { renamedLine } from './importRename';
import { MOST_STEPS, splitStep } from './importSteps';
import { unitFor } from './recipeAmounts';
import { activeTime, sumWaits, type StepWait } from './timeWords';
import { leftOut, ownIndexOf, ownParts, ownSteps, type OwnPart } from './importOwn';

/** What a line was set to on the review (a line that is matched needs no choice). */
export type Choice =
  | { kind: 'ingredient'; food: Ref; learn: boolean }
  | { kind: 'new' | 'staple'; name: string; counted_as: CountedAs; place_id: number | null }
  /** "Made in this recipe" (F108): saved as words only, never linked, never taken from the
   *  pantry, and not counted as unlinked. */
  | { kind: 'here' }
  /** "Made in another recipe" (F188, cabledrawer 8 Nov): the line uses that recipe, the same link a
   *  recipe line made in the editor has. `place_id`: where the pantry keeps it (Fridge,
   *  Freezer, Cupboard), given to the recipe's made-ahead ingredient when it has no place yet. */
  | { kind: 'recipe'; recipe: Ref; place_id: number | null };

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

/** What to do when a site wouldn't let the server read its page (F115, cabledrawer 31 Oct; the
 *  wording is proposed, for cabledrawer). */
export const PASTE_INSTEAD_STEPS = [
  'Open the recipe in your browser. Tip: the page’s “Print recipe” button gives a cleaner copy.',
  'Select from the title to the end of the method, and copy it.',
  'Paste it here, in place of the link. Pasted text never goes online.'
] as const;

/** The device has no network. With a network but no answer from the server the words are
 *  SERVER_DOWN_TRY_LATER instead: use `offlineNote()` (cabledrawer 30 Oct). */
export const OFFLINE_NOTE =
  'Importing needs your Mealwright server. Try again when you’re back online.';
/** Keeping a draft didn't reach the server (proposed, for cabledrawer): the device has no network. */
export const DRAFT_OFFLINE =
  'Saving a draft needs your Mealwright server. Try again when you’re back online.';
/** What importing says when the server can't be reached, chosen by the cause. */
export const offlineNote = (): string => needsServer(network.deviceOffline, OFFLINE_NOTE);
/** Close in Check with no connection (F174, cabledrawer 7 Nov): it leaves, and the draft stays as it was
 *  last kept. */
export const CLOSE_OFFLINE = 'You’re offline: changes since then won’t be kept';

/** The same for keeping a draft. */
export const draftOfflineNote = (): string => needsServer(network.deviceOffline, DRAFT_OFFLINE);
const COULDNT = 'Couldn’t read that. Try again.';

/** Where each line Save sent came from in the review (F190). */
interface SentLines {
  main: (number | null)[];
  own: number[][];
}

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
  #minutes = $state('');
  /** The person typed in the Minutes box (kept as typed in a draft): Check leaves it alone. */
  minutesTyped = false;
  get minutes(): string {
    return this.#minutes;
  }
  set minutes(text: string) {
    this.#minutes = text;
    this.minutesTyped = true;
  }
  /** Minutes worked out from the waits (M1): not typed, so a later wait answer may change it. */
  setMinutesWorkedOut(text: string): void {
    this.#minutes = text;
  }
  /** Work the Minutes box out again from the page's own total and the waits the steps have now
   *  (M1 fix: "No wait" gives the minutes back). Leaves it alone once it was typed in, or when
   *  the page gave no total. */
  reworkMinutes(): void {
    const review = this.review;
    if (!review || this.minutesTyped || review.page_time_minutes == null) return;
    const waits = review.steps.flatMap((s) => (s.kind === 'step' && s.wait ? [s.wait] : []));
    const time = activeTime(
      review.page_time_minutes,
      waits.map((w) => ({ min_minutes: w.min_minutes, max_minutes: w.max_minutes }))
    );
    this.setMinutesWorkedOut(time === null ? '' : String(time));
  }
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
  /** The server's code for it ("too_many_drafts"), when it answered. */
  draftProblemCode = $state<string | null>(null);

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

  /** The links the box holds when it holds nothing but links, separated by spaces or line
   *  breaks (none for anything else). Several are read one after another, each into its own
   *  draft (F25, F110; `importLinks.svelte.ts`). */
  get links(): string[] {
    const words = this.text.split(/\s+/).filter(Boolean);
    const link = (w: string) => /^(https?:\/\/|www\.)\S+$/i.test(w) || /^\S+:\/\/\S*$/.test(w);
    return words.length > 0 && words.every(link) ? words : [];
  }

  get linkCount(): number {
    return this.links.length;
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
      this.problem = problemOf('offline', offlineNote());
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
    // A site that refused the server: the link is cleared so the box is ready for the pasted
    // text (F115). The other causes keep the link, so it can be fixed or tried again.
    if (error.code === 'site_refused') this.text = '';
  }

  private show(review: ImportReview): void {
    this.review = review;
    this.choices = {};
    this.sharedFrom = {};
    this.walk = null;
    this.previewStep = null;
    this.stepsBefore = null;
    this.#stepUndos = [];
    this.pints = review.pints?.reading ?? 'uk';
    this.name = review.name;
    this.serves = review.serves === null ? '' : String(review.serves);
    this.#minutes = review.time_minutes === null ? '' : String(review.time_minutes);
    this.minutesTyped = false;
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
    else this.reworkMinutes(); // not typed: worked out from the waits the draft's steps have
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
      this.review?.steps,
      this.review?.second_method?.steps
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
        minutes: this.minutesTyped ? this.minutes : null, // worked out again when it is opened
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
    this.draftProblemCode = null;
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
      this.draftProblemCode = error instanceof ApiError ? (error.code ?? null) : null;
      this.draftProblem =
        error instanceof ApiError
          ? cantReach(error)
            ? draftOfflineNote()
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
      optional?: boolean;
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
  /** Edit the name read (F214): the line takes the corrected name, any choice on it goes, and it
   *  is matched again by that name (`importRename.ts`). False when the name is empty. */
  async renameLine(
    index: number,
    name: string,
    find: (query: string) => Promise<FoodRow[]>
  ): Promise<boolean> {
    const line = this.review?.lines[index];
    if (!line || line.kind !== 'ingredient' || !name.trim()) return false;
    const patch = await renamedLine(line, name, find);
    // The review moved on while the lookup was out (a line removed or added): the same line only.
    if (this.review?.lines[index] !== line) return true;
    this.unchoose(index);
    Object.assign(line, patch);
    this.saveProblem = null;
    return true;
  }

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
      if (choice && (choice.kind === 'new' || choice.kind === 'staple')) {
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
    const keys = nameKeys(
      source,
      choice.kind === 'new' || choice.kind === 'staple' ? choice.name : null
    );
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

  // --- Adding a line (F187) ---------------------------------------------------------------------

  /** Where a new line goes at the end of each section, and what its button says: the section is
   *  the lines under one heading (the lines before the first heading are a section of their own).
   *  `at` is the place in the review the new line takes (the next heading's, or the end). */
  get sectionEnds(): { at: number; label: string }[] {
    const lines = this.review?.lines ?? [];
    const ends: { at: number; label: string }[] = [];
    let label = 'Add a line';
    let started = false; // a section before the first heading only counts when it has lines
    lines.forEach((line, i) => {
      if (line.kind === 'heading') {
        if (started || i > 0) ends.push({ at: i, label });
        label = addLineWords(line.words);
        started = true;
      }
    });
    ends.push({ at: lines.length, label });
    return ends;
  }

  /** How many lines the recipe may hold (the server's limit). */
  get canAddLine(): boolean {
    return (this.review?.lines.length ?? 0) < MOST_LINES;
  }

  /** A new, empty ingredient line at `at`: the person names it, and it gets the same choices as
   *  any line. Returns its place. It is not saved while it has no name. */
  addLine(at: number): number {
    const review = this.review;
    if (!review || !this.canAddLine) return -1;
    const place = Math.max(0, Math.min(at, review.lines.length));
    review.lines.splice(place, 0, {
      kind: 'ingredient',
      written: '',
      words: '',
      amount: null,
      amount_text: null,
      unit: null,
      size: null,
      note: null,
      readable: true,
      label: 'needs_you',
      food: null,
      place: null,
      matched_by: null,
      counts: true,
      new_ingredient: null,
      learn_name: null,
      pint_ml: null
    });
    this.#remap((i) => (i >= place ? i + 1 : i));
    return place;
  }

  /** Give an added line its name. An ingredient with exactly that name (or another name of it)
   *  is the line's ingredient, as the reader does for a line it reads; otherwise the line needs
   *  a choice. False when the name is empty. */
  async nameLine(index: number, typed: string): Promise<boolean> {
    const review = this.review;
    const line = review?.lines[index];
    const name = typed.replace(/\s+/g, ' ').trim();
    if (!review || !line || line.kind !== 'ingredient' || !name) return false;
    const found = await exactIngredient(name);
    // A slow answer for a screen that has moved on: nothing to change.
    if (this.review !== review || review.lines[index] !== line) return false;
    Object.assign(line, {
      words: name,
      readable: true,
      label: found ? (found.staple ? 'staple' : 'matched') : 'needs_you',
      food: found ? { id: found.id, name: found.name } : null,
      place: found?.place?.name ?? null,
      matched_by: found ? name : null,
      counts: !found?.staple,
      new_ingredient: {
        name: name[0]!.toUpperCase() + name.slice(1),
        counted_as: 'weight',
        place: null
      }
    } satisfies Partial<ReviewLine>);
    this.saveProblem = null;
    return true;
  }

  /** An added line the person gives up on before naming it: it goes, with no Undo (nothing was
   *  in it). */
  dropBlank(index: number): void {
    const lines = this.review?.lines;
    if (!lines || !lines[index] || !isBlank(lines[index]!)) return;
    lines.splice(index, 1);
    this.#remap((i) => (i === index ? null : i > index ? i - 1 : i));
  }

  // --- Taking a line out, or making it two (F105, F109) ---------------------------------------

  /** The Undo entries for lines taken out or split, so leaving the screen can forget them. */
  #takenOut: UndoEntry[] = [];

  /** Lines moved to other places: the choices and the "also used for" notes follow them. `to`
   *  gives a line's new place, or null when the line is gone (its choice and notes go too). */
  #remap(to: (place: number) => number | null): void {
    const choices: Record<number, Choice> = {};
    for (const [i, kept] of Object.entries(this.choices)) {
      const place = to(Number(i));
      if (place !== null) choices[place] = kept;
    }
    const notes: Record<number, number> = {};
    for (const [i, from] of Object.entries(this.sharedFrom)) {
      const place = to(Number(i));
      const source = to(from);
      if (place !== null && source !== null) notes[place] = source;
    }
    this.choices = choices;
    this.sharedFrom = notes;
    this.saveProblem = null;
  }

  /** Take `gone` (which stand in `at`) out of the review and put `put` there instead, with an
   *  Undo that reverses it. Lines are found again by themselves, not by number: other lines
   *  may have moved since. The one line taken out keeps its choice for the Undo. */
  #swap(at: number, gone: ReviewLine[], put: ReviewLine[], label: string): void {
    const review = this.review;
    if (!review) return;
    const lines = review.lines;
    const choice = gone.length === 1 ? this.choices[at] : undefined;
    const source =
      gone.length === 1 && this.sharedFrom[at] !== undefined ? lines[this.sharedFrom[at]!] : null;
    const followers = gone.length === 1 ? this.followers(at).map((j) => lines[j]!) : [];
    const after = lines[at + gone.length];
    const moved = put.length - gone.length;
    lines.splice(at, gone.length, ...put);
    // The lines as the review now holds them (what is stored can differ from what was handed in).
    const placed = lines.slice(at, at + put.length);
    this.#remap((i) => (i >= at + gone.length ? i + moved : i >= at ? null : i));

    const entry: UndoEntry = {
      label,
      undo: () => {
        const now = this.review?.lines;
        if (this.review !== review || !now) return false; // another recipe is on the screen now
        const first = placed.length ? now.indexOf(placed[0]!) : -1;
        if (first >= 0 && placed.some((line, k) => now[first + k] !== line)) return false;
        let from = first;
        if (from < 0) {
          const next = after ? now.indexOf(after) : now.length;
          from = next >= 0 ? next : Math.min(at, now.length);
        }
        now.splice(from, first < 0 ? 0 : placed.length, ...gone);
        const gap = first < 0 ? 0 : placed.length;
        const shift = gone.length - gap;
        this.#remap((i) => (i >= from + gap ? i + shift : i >= from ? null : i));
        if (choice) {
          this.choices = { ...this.choices, [from]: choice };
          const origin = source ? now.indexOf(source) : -1;
          if (origin >= 0) this.sharedFrom = { ...this.sharedFrom, [from]: origin };
        }
        for (const follower of followers) {
          const j = now.indexOf(follower);
          if (j >= 0 && this.choices[j]) this.sharedFrom = { ...this.sharedFrom, [j]: from };
        }
      }
    };
    this.#takenOut.push(entry);
    undoHistory.record(entry);
  }

  /** Remove line: the line is taken out of the review, so it is not saved, not counted and not
   *  in the Save warning. The toast's Undo (and Ctrl+Z) puts it back where it was. */
  removeLine(index: number): void {
    const line = this.review?.lines[index];
    if (!line || line.kind !== 'ingredient') return;
    this.#swap(index, [line], [], `Removed “${shorter(line.written)}”`);
  }

  /** Split into two: one line that is really two ingredients ("water and broth") becomes two
   *  lines with the names given, each with no amount and the note "4½ cups together" when the
   *  line had one. The two are looked up in the household's ingredients by exact name, as the
   *  reader does for its own. False when the names can't be used. */
  async splitLine(index: number, names: [string, string]): Promise<boolean> {
    const review = this.review;
    const line = review?.lines[index];
    if (!review || !line || line.kind !== 'ingredient') return false;
    const [first, second] = names.map((n) => n.replace(/\s+/g, ' ').trim());
    if (!first || !second || first.toLowerCase() === second.toLowerCase()) return false;
    const found = await Promise.all([first, second].map((name) => exactIngredient(name)));
    // A slow answer for a screen that has moved on: nothing to change.
    if (this.review !== review || review.lines[index] !== line) return false;
    const note = [togetherNote(line), keptNote(line)].filter(Boolean).join(', ') || null;
    const made = [first, second].map((name, n): ReviewLine => ({
      kind: 'ingredient',
      written: line.written,
      words: name,
      amount: null,
      amount_text: null,
      unit: null,
      size: null,
      note,
      readable: true,
      label: found[n] ? (found[n]!.staple ? 'staple' : 'matched') : 'needs_you',
      food: found[n] ? { id: found[n]!.id, name: found[n]!.name } : null,
      place: found[n]?.place?.name ?? null,
      matched_by: found[n] ? name : null,
      counts: false,
      new_ingredient: {
        name: name[0]!.toUpperCase() + name.slice(1),
        counted_as: 'weight',
        place: null
      },
      learn_name: null,
      pint_ml: null
    }));
    this.#swap(index, [line], made, `Split “${shorter(line.written)}” into two`);
    return true;
  }

  /** Use this instead (F217): the line's "or" choice becomes the line, and the first choice
   *  becomes the "or" choice, so the person can swap back. The note of each already holds the
   *  other (the reader wrote both), so Save needs nothing new. Undo puts the first back. */
  useAlternative(index: number): void {
    const line = this.review?.lines[index];
    const other = line?.alternative;
    if (!line || line.kind !== 'ingredient' || !other) return;
    const now: ReviewLine = {
      ...other,
      optional: line.optional,
      alternative: { ...line, alternative: null }
    };
    this.#swap(
      index,
      [line],
      [now],
      `Used “${shorter(other.words)}” instead of “${shorter(line.words)}”`
    );
  }

  /** An Undo for a section made its own recipe (F190) joins the lines', so leaving the screen
   *  forgets it too. */
  keepLineUndo(entry: UndoEntry): void {
    this.#takenOut.push(entry);
  }

  /** An Undo for a step taken out (F111) joins the lines', so leaving the screen forgets it too. */
  keepStepUndo(entry: UndoEntry): void {
    this.#takenOut.push(entry);
    this.#stepUndos.push(entry);
  }

  /** The Undo entries for steps taken out since the review was read; Put the steps back as they
   *  were makes them stale, so it forgets them. */
  #stepUndos: UndoEntry[] = [];

  /** Forget the Undo for lines taken out: the screen is going, and they would have nowhere to
   *  go back to. */
  forgetTakenOut(): void {
    this.#takenOut.forEach((entry) => undoHistory.forget(entry));
    this.#takenOut = [];
  }

  /** F108: a line made earlier in the same recipe ("2 tsp spice mix (from the spice blend)"):
   *  saved as words only. */
  madeHere(index: number): void {
    const choice: Choice = { kind: 'here' };
    this.choose(index, choice);
    this.#share(index, choice);
  }

  /** F108: "Made in this recipe" comes first when the note says "from the …", or the name is
   *  one of the recipe's own section headings ("For the spice blend" is "spice blend"). */
  offersMadeHere(index: number): boolean {
    const lines = this.review?.lines ?? [];
    const line = lines[index];
    if (!line || line.kind !== 'ingredient') return false;
    const flat = (text: string) => text.toLowerCase().replace(/\s+/g, ' ').trim();
    if (/\bfrom the\b/i.test(line.note ?? '')) return true;
    const name = flat(line.words);
    return lines.some((other) => {
      if (other.kind !== 'heading') return false;
      const core = flat(
        other.words.replace(/^(for|to make|make)\s+(the\s+)?/i, '').replace(/^the\s+/i, '')
      );
      return core !== '' && (core === name || core === flat(line.new_ingredient?.name ?? ''));
    });
  }

  /** F188: the line uses another recipe. */
  useRecipe(index: number, recipe: Ref, placeId: number | null = null): void {
    const choice: Choice = { kind: 'recipe', recipe, place_id: placeId };
    // Lines that took this line's New ingredient follow it to the recipe.
    const followers = this.followers(index);
    this.choose(index, choice);
    for (const at of followers) this.choose(at, { ...choice });
    this.#share(index, choice);
  }

  /** The ingredient a line will be tied to, or null: a choice, else a match. */
  linkOf(index: number): Choice | null {
    const chosen = this.choices[index];
    if (chosen) return chosen;
    // The line that stands for a section made its own recipe is that recipe, once it is saved.
    const section = this.ownUseOf(index);
    if (section)
      return { kind: 'recipe', recipe: { id: 0, name: section.own.name }, place_id: null };
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
      if (line.kind !== 'ingredient' || isBlank(line)) return;
      const choice = this.choices[i];
      if (!choice && this.ownUseOf(i)) counts.matched++;
      else if (choice) counts[choice.kind === 'staple' ? 'staple' : 'matched']++;
      else if (line.label && line.label in counts) counts[line.label]++;
    });
    return counts;
  }

  /** How many lines will be saved with no ingredient behind them (words only). */
  get unlinked(): number {
    const review = this.review;
    if (!review) return 0;
    return review.lines.filter(
      (line, i) => line.kind === 'ingredient' && !isBlank(line) && !this.linkOf(i)
    ).length;
  }

  // --- Save ---------------------------------------------------------------------------------

  /** Where each line Save sent came from in the review (F190): the line numbers the server's
   *  refusal names are the sent ones, and a section made its own recipe moves lines about.
   *  `null`: a line the review doesn't hold as such (the one that stands for a section). */
  #sent: SentLines = { main: [], own: [] };

  /** The sections made their own recipes, as the review stands. */
  get ownParts(): OwnPart[] {
    return this.review ? ownParts(this.review) : [];
  }

  /** The place of the line that stands for a section in the main recipe ("Dosa batter, as
   *  above"): it is saved as the link to the new recipe, so it needs no ingredient. */
  ownUseOf(index: number): OwnPart | null {
    const parts = this.ownParts;
    const at = ownIndexOf(parts, index, true);
    return at >= 0 ? parts[at]! : null;
  }

  /** The body Save sends: the review's recipe with the changes made on this screen. */
  body(): SaveBody | null {
    const review = this.review;
    if (!review) return null;
    const serves = this.serves.trim() === '' ? null : Number(this.serves);
    const time = this.minutes.trim() === '' ? null : Number(this.minutes);
    const parts = ownParts(review);
    const out = leftOut(parts);
    const sent: SentLines = { main: [], own: parts.map(() => []) };
    const lines: SaveLine[] = [];
    const own: SaveOwnRecipe[] = parts.map((part) => ({
      name: part.own.name,
      makes: { amount: part.own.amount, unit: part.own.unit },
      lines: [],
      steps: ownSteps(review.steps, part)
    }));
    review.lines.forEach((line, i) => {
      // A line added on Check and never named is not saved (F187).
      if (isBlank(line)) return;
      const k = parts.findIndex((part) => part.heading === i || part.section.lines.includes(i));
      if (k >= 0) {
        // A section made its own recipe: its lines go to that recipe, with their own choices; the
        // main recipe gets one line in the heading's place (unless a line already says it).
        if (line.kind === 'ingredient') {
          own[k]!.lines.push(saveLine(this.withPints(line), this.linkOf(i)));
          sent.own[k]!.push(i);
        } else if (parts[k]!.section.use === null) {
          lines.push(ownLine(parts[k]!, k));
          sent.main.push(null);
        }
        return;
      }
      const at = parts.findIndex((part) => part.section.use === i);
      lines.push(
        at >= 0
          ? { ...ownLine(parts[at]!, at, line), note: line.note, optional: !!line.optional }
          : saveLine(this.withPints(line), this.linkOf(i))
      );
      sent.main.push(i);
    });
    this.#sent = sent;
    return {
      name: this.name.trim(),
      description: review.description,
      time_minutes: time,
      serves,
      makes: review.makes,
      tags: review.tags,
      nutrition: review.nutrition,
      lines,
      // What Save sends: not whether the person has confirmed the wait.
      steps: review.steps.flatMap((s, i) =>
        out.steps.has(i) ? [] : [{ kind: s.kind, text: s.text, optional: s.optional, wait: s.wait }]
      ),
      ...(own.length > 0 ? { own_recipes: own } : {}),
      // Two ways of cooking it found on the page (M2): both start with these ingredients.
      ...(review.second_method
        ? {
            method_name: review.method_name ?? null,
            second_method: {
              name: review.second_method.name,
              steps: review.second_method.steps.map((s) => ({
                kind: s.kind,
                text: s.text,
                optional: s.optional,
                wait: s.wait
              }))
            }
          }
        : {}),
      source_url: review.source.url,
      source_author: review.author,
      photo_id: review.photo.photo?.id ?? null,
      draft_id: this.draftId
    };
  }

  /** All the steps' waits added up, for the time line under the Minutes box (M1). */
  get waitTotal(): StepWait | null {
    return sumWaits(this.review?.steps ?? []);
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
    return lines.flatMap((line, i) =>
      line.kind === 'ingredient' && !isBlank(line) && !this.linkOf(i) ? [i] : []
    );
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
      ...pieces.map((text, n) => ({
        kind: 'step' as const,
        text,
        // The wait goes to the piece that talks about it (the first one, if none does).
        ...(waitPiece(pieces, review.steps[i]?.wait) === n
          ? { wait: review.steps[i]!.wait, wait_confirmed: review.steps[i]!.wait_confirmed }
          : {})
      })),
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
    // A reset: the steps taken out since can't be put back into steps that are not those any more.
    for (const entry of this.#stepUndos) {
      undoHistory.forget(entry);
      if (toasts.current?.message === entry.label) toasts.dismiss();
    }
    this.#stepUndos = [];
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
    if (
      this.review?.steps.some((s) => s.wait_invalid) ||
      this.review?.second_method?.steps.some((s) => s.wait_invalid)
    ) {
      this.saveProblem = { message: 'Type how long it waits, such as 4 hours.', line: null };
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
        const found = error.body as { line?: unknown; own_recipe?: unknown } | null;
        const sentAt = typeof found?.line === 'number' ? found.line : null;
        const section = typeof found?.own_recipe === 'number' ? found.own_recipe : null;
        // The server counts the lines it was sent: back to the review's own places (F190).
        const line =
          sentAt === null
            ? null
            : section === null
              ? (this.#sent.main[sentAt] ?? null)
              : (this.#sent.own[section]?.[sentAt] ?? null);
        this.saveProblem = {
          message: cantReach(error) ? offlineNote() : error.detail,
          line
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

/** Which piece of a split step carries its wait: the first that has a waiting word in it. */
function waitPiece(pieces: string[], wait: unknown): number {
  if (!wait) return -1;
  const found = pieces.findIndex((p) =>
    /\b(marinat|soak|ferment|rest|chill|refrigerat|prov(e|ing)|proof)/i.test(p)
  );
  return found < 0 ? 0 : found;
}

function saveLine(line: ReviewLine, link: Choice | null): SaveLine {
  let sent: LineLink | null = null;
  if (line.kind === 'ingredient' && link && link.kind !== 'here') {
    sent =
      link.kind === 'ingredient'
        ? { kind: 'ingredient', food_id: link.food.id, learn: link.learn ? line.learn_name : null }
        : link.kind === 'recipe'
          ? { kind: 'recipe', recipe_id: link.recipe.id, place_id: link.place_id }
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
    link: sent,
    optional: line.kind === 'ingredient' && !!line.optional
  };
}

/** The one line the main recipe gets for a section made its own recipe: "Dosa batter · 4 cups",
 *  or the amount the line that stands for it already says (F190). */
function ownLine(part: OwnPart, place: number, stands?: ReviewLine): SaveLine {
  const said = stands && stands.amount !== null && stands.amount !== undefined;
  return {
    kind: 'ingredient',
    words: part.own.name,
    amount: said ? stands.amount : part.own.amount,
    unit: said ? stands.unit : part.own.unit,
    size_id: null,
    note: null,
    link: { kind: 'own_recipe', own_recipe: place },
    optional: false
  };
}

/** The ingredient with exactly this name (or another name of it), or null: the household's own,
 *  from the server's search. A search that fails is no match: the line asks the person. Null too
 *  when a recipe has exactly this name, so the person chooses and the recipe is offered first
 *  (F189, cabledrawer 8 Nov), as the reader does for the lines it reads. */
async function exactIngredient(name: string): Promise<FoodRow | null> {
  try {
    const key = fold(name);
    const [{ foods }, { recipes }] = await Promise.all([
      listFoods({ q: name, limit: 8 }),
      listRecipes({ q: name, limit: 100 })
    ]);
    if (recipes.some((recipe) => fold(recipe.name) === key)) return null;
    return (
      foods.find(
        (food) => fold(food.name) === key || food.other_names.some((other) => fold(other) === key)
      ) ?? null
    );
  } catch {
    return null;
  }
}

/** "4½ cups together": the amount a line had, now shared by the two it was split into. */
function togetherNote(line: ReviewLine): string {
  if (line.amount === null) return '';
  const number = line.amount_text ?? amountWords(line.amount);
  const word = line.size
    ? line.amount > 1
      ? line.size.plural
      : line.size.name
    : line.unit
      ? unitFor(line.unit, line.amount)
      : '';
  return `${number}${word ? `\u00a0${word}` : ''} together`;
}

/** The line's own note, but not the "as written" copy of an amount that is gone. */
function keptNote(line: ReviewLine): string {
  return line.note && !line.note.startsWith('as written:') ? line.note : '';
}

/** A line as it reads in a toast: cut at 40 characters, at a word where it can. */
function shorter(text: string): string {
  const one = text.replace(/\s+/g, ' ').trim();
  if (one.length <= 40) return one;
  return `${(one.slice(0, 40).replace(/\s+\S*$/, '') || one.slice(0, 40)).trimEnd()}…`;
}

/** "4 lines after “Tips” were left out": the sentence for the review (spec Q17). */
export function leftOutWords(heading: string, lines: number): string {
  return `${lines} ${lines === 1 ? 'line' : 'lines'} after “${heading}” ${lines === 1 ? 'was' : 'were'} left out`;
}

/** The ingredient lines and headings a recipe may hold: the server's limit. */
export const MOST_LINES = 200;

/** A line added on Check that has no name yet: not counted, not saved (F187). */
export function isBlank(line: ReviewLine): boolean {
  return line.kind === 'ingredient' && line.written === '' && line.words.trim() === '';
}

/** The button at the end of a section (F187; mockup Dark-CheckSections08-Phone): "For the batter"
 *  is "Add a line to the batter"; any other heading is named in quotes; no heading, no name. */
export function addLineWords(heading: string): string {
  const text = heading.replace(/\s+/g, ' ').trim();
  const named = /^(?:for|to make|make)\s+(the\s+.+)$/i.exec(text);
  if (named) return `Add a line to ${named[1]!.toLowerCase()}`;
  return text ? `Add a line to “${text}”` : 'Add a line';
}
