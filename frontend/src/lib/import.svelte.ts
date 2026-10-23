// Importing a recipe, the screen's state (docs/dev/recipe-import.md): the one box, what the
// server read (the review), the choices made on the review, and Save. Nothing here is saved
// until Save, and nothing is queued: it needs the server (spec: online only).

import { ApiError, cantReach } from './api';
import {
  saveImport,
  startImport,
  type ImportReview,
  type LineLink,
  type ReviewLine,
  type Saved,
  type SaveBody,
  type SaveLine
} from './client/imports';
import type { CountedAs, Ref } from './client/types';
import { newChangeId } from './changeId';

/** What a line was set to on the review (a line that is matched needs no choice). */
export type Choice =
  | { kind: 'food'; food: Ref; learn: boolean }
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

export const OFFLINE_NOTE =
  'Importing needs your Mealwright server. Try again when you’re back online.';
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
  name = $state('');
  serves = $state('');
  minutes = $state('');
  saving = $state(false);
  saveProblem = $state<{ message: string; line: number | null } | null>(null);
  /** Chosen on purpose: the Save went through once. */
  saved = $state<Saved | null>(null);

  #saveKey = newChangeId();

  get isLink(): boolean {
    return (
      /^\s*(https?:\/\/|www\.)\S+\s*$/i.test(this.text) || /^\s*\S+:\/\/\S*\s*$/.test(this.text)
    );
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
      this.problem = problemOf('offline', error.status === 0 ? OFFLINE_NOTE : error.detail);
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
    this.name = review.name;
    this.serves = review.serves === null ? '' : String(review.serves);
    this.minutes = review.time_minutes === null ? '' : String(review.time_minutes);
    this.saveProblem = null;
    this.#saveKey = newChangeId();
    this.phase = 'review';
  }

  /** Back to the box, keeping what was typed (Paste text instead, Cancel on a sheet). */
  backToBox(): void {
    this.phase = 'start';
    this.review = null;
    this.already = null;
  }

  // --- The review's choices ---------------------------------------------------------------

  choose(index: number, choice: Choice | null): void {
    const next = { ...this.choices };
    if (choice === null) delete next[index];
    else next[index] = choice;
    this.choices = next;
    this.saveProblem = null;
  }

  /** "Same as Onions" on a line that is to confirm (its best guess) or one picked from the list. */
  sameAs(index: number, food: Ref): void {
    this.choose(index, { kind: 'food', food, learn: true });
  }

  newIngredient(index: number, staple = false): void {
    const line = this.review?.lines[index];
    if (!line?.new_ingredient) return;
    const guess = line.new_ingredient;
    this.choose(index, {
      kind: staple ? 'staple' : 'new',
      name: guess.name,
      counted_as: guess.counted_as,
      place_id: guess.place?.id ?? null
    });
  }

  /** The ingredient a line will be tied to, or null: a choice, else a match. */
  linkOf(index: number): Choice | null {
    const chosen = this.choices[index];
    if (chosen) return chosen;
    const line = this.review?.lines[index];
    if (line && (line.label === 'matched' || line.label === 'staple') && line.food) {
      return { kind: 'food', food: line.food, learn: false };
    }
    return null;
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
      lines: review.lines.map((line, i) => saveLine(line, this.linkOf(i))),
      steps: review.steps,
      source_url: review.source.url,
      source_author: review.author,
      photo_id: review.photo.photo?.id ?? null
    };
  }

  /** The box for Serves or Time holds something that isn't a whole number in range. */
  get numbersOk(): boolean {
    const whole = (text: string, most: number) =>
      text.trim() === '' || (/^\d+$/.test(text.trim()) && +text >= 1 && +text <= most);
    return whole(this.serves, 99) && whole(this.minutes, 14_400);
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

function problemOf(code: string, message: string): ImportProblem {
  return { code, message, switchedOff: false, admin: false };
}

function saveLine(line: ReviewLine, link: Choice | null): SaveLine {
  let sent: LineLink | null = null;
  if (line.kind === 'ingredient' && link) {
    sent =
      link.kind === 'food'
        ? { kind: 'food', food_id: link.food.id, learn: link.learn ? line.learn_name : null }
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
    size_id: sent?.kind === 'food' ? (line.size?.id ?? null) : null,
    note: line.note,
    link: sent
  };
}

/** "4 lines after “Tips” were left out": the sentence for the review (spec Q17). */
export function leftOutWords(heading: string, lines: number): string {
  return `${lines} ${lines === 1 ? 'line' : 'lines'} after “${heading}” ${lines === 1 ? 'was' : 'were'} left out`;
}
