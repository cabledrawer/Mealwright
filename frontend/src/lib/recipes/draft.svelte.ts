// The recipe being typed in the editor. Nothing here is saved until Save (cabledrawer 19 Oct,
// question 27): this is a copy of the recipe, changed freely, then sent whole.

import { untrack } from 'svelte';
import { ApiError } from '#lib/api.js';
import {
  deletePhoto,
  uploadPhoto,
  type LineIn,
  type LineOut,
  type Nutrition,
  type PhotoOut,
  type RecipeIn,
  type RecipeOut
} from '#lib/client/recipes.js';
import type { Ref } from '#lib/client/types.js';
import { linkedWords } from './linkedWords';
import { toasts } from '#lib/toast.svelte.js';
import type { StepWait } from '#lib/timeWords.js';

export const MAX_LINES = 200;
export const MAX_STEPS = 100;
export const MAX_TAGS = 20;
export const MAX_TAG_CHARS = 40;
export const LINE_UNITS = ['g', 'kg', 'ml', 'l', 'tsp', 'tbsp', 'cup', 'pinch'] as const;
export const NUTRIENTS: (keyof Nutrition)[] = ['kcal', 'protein', 'carbs', 'fat', 'fibre'];
/** The "Makes" units with a button of their own; anything else is a count word ("dosas"). */
export const MAKES_UNITS = ['l', 'ml', 'g', 'kg'] as const;
export const COUNT = 'count';
/** The API's own codes for a refused photo (upload, attach, delete), whatever words they come with. */
const PHOTO_CODES = new Set([
  'photo_too_big',
  'too_many_photos_waiting',
  'too_many_pixels',
  'not_a_photo',
  'photo_in_use'
]);

export interface SizeRef {
  id: number;
  name: string;
  plural: string;
}

export interface DraftLine {
  key: string;
  /** The saved line's id, sent back so an ingredient merge can follow it. */
  id: number | null;
  kind: 'ingredient' | 'heading';
  /** The recipe's own words (cabledrawer 19 Oct, question 14). */
  words: string;
  amount: string;
  /** '' is "none" (a count: 10 shallots), a unit code, or `size:<id>`. */
  unit: string;
  food: Ref | null;
  recipe: Ref | null;
  /** The recipe this line used was deleted; the link is kept for Undo. */
  recipeRemoved: boolean;
  note: string;
  /** Optional: adding the recipe to the plan asks whether it will be used. */
  optional: boolean;
}

export interface DraftStep {
  key: string;
  kind: 'step' | 'heading';
  text: string;
  /** An Optional step. */
  optional: boolean;
  /** The step waits (marinate, soak, ferment...); null when it doesn't. */
  wait: StepWait | null;
  /** The Waits boxes don't make a wait that can be kept (not saved with the draft): Save is
   *  blocked until they are put right or the wait is taken off. */
  waitInvalid?: boolean;
}

/** The editor's boxes as the tab keeps them (see `toCarried`). */
export interface Carried {
  /** The saved recipe's version this was typed on; null for a new recipe. */
  version: number | null;
  name: string;
  description: string;
  time: string;
  serves: number | null;
  makesAmount: string;
  makesUnit: string;
  makesWord: string;
  madeAhead: boolean;
  homemadeName: string;
  tags: string[];
  nutrition: Record<keyof Nutrition, string>;
  lines: DraftLine[];
  steps: DraftStep[];
  source: string;
  sizes: Record<number, SizeRef[]>;
  photoRemoved: boolean;
}

export type PhotoChange = 'none' | 'removed' | 'new';

export interface DraftPhoto {
  /** What shows now: the recipe's own photo, or the new upload. */
  shown: PhotoOut | null;
  /** none: leave `photo_id` out · removed: send null · new: send the upload's id. */
  change: PhotoChange;
  /** The picture being uploaded now. */
  uploading: File | null;
  /** The file behind the upload. */
  file: File | null;
  error: string | null;
}

let counter = 0;
export const nextKey = (prefix: string) => `${prefix}${++counter}`;

export function blankLine(kind: DraftLine['kind'] = 'ingredient'): DraftLine {
  return {
    key: nextKey('l'),
    id: null,
    kind,
    words: '',
    amount: '',
    unit: '',
    food: null,
    recipe: null,
    recipeRemoved: false,
    note: '',
    optional: false
  };
}

/** A wait read back from what the tab kept (anything odd is no wait). */
function waitFrom(value: unknown): StepWait | null {
  const w = value as Partial<StepWait> | null | undefined;
  if (
    !w ||
    typeof w.kind !== 'string' ||
    !Number.isInteger(w.min_minutes) ||
    !Number.isInteger(w.max_minutes)
  ) {
    return null;
  }
  return {
    kind: w.kind,
    min_minutes: w.min_minutes!,
    max_minutes: w.max_minutes!,
    overnight: !!w.overnight
  };
}

export function blankStep(kind: DraftStep['kind'] = 'step'): DraftStep {
  return { key: nextKey('s'), kind, text: '', optional: false, wait: null };
}

function lineFrom(line: LineOut): DraftLine {
  const unit = line.size ? `size:${line.size.id}` : (line.unit ?? '');
  return {
    key: nextKey('l'),
    id: line.id,
    kind: line.kind,
    // A line saved as "thu" and linked to Toor Dal opens as "Toor Dal" (cabledrawer 25 Oct).
    words: linkedWords(line.words, line.food),
    amount: line.amount_text ?? '',
    unit,
    food: line.food,
    recipe: line.recipe,
    recipeRemoved: line.link === 'recipe_removed',
    note: line.note ?? '',
    optional: !!line.optional
  };
}

const text = (n: number | null | undefined) => (n === null || n === undefined ? '' : String(n));

/** Where a message goes: `name`, `line:<key>`, `line:<key>.amount`, `step:<key>`, `nutrition.kcal`… */
export type Errors = Record<string, string>;

export interface Built {
  body: RecipeIn;
  /** The key of the line (or step) at each place in the body, for putting a refusal on the right box. */
  lineKeys: string[];
  stepKeys: string[];
  errors: Errors;
}

const NUMBER = /^\d+([.,]\d+)?$/;
const emptyLine = (l: DraftLine) =>
  !l.words.trim() && !l.food && !l.recipe && !l.amount.trim() && !l.note.trim();

export class RecipeDraft {
  name = $state('');
  description = $state('');
  time = $state('');
  serves = $state<number | null>(4);
  makesAmount = $state('');
  /** l, ml, g, kg or `count`. */
  makesUnit = $state('l');
  /** The count word when `makesUnit` is `count`: "dosas". */
  makesWord = $state('');
  madeAhead = $state(false);
  homemadeName = $state('');
  tags = $state<string[]>([]);
  nutrition = $state<Record<keyof Nutrition, string>>({
    kcal: '',
    protein: '',
    carbs: '',
    fat: '',
    fibre: ''
  });
  /** The editor was opened from "Update nutrition": Save says the figures were looked at. */
  nutritionChecked = $state(false);
  lines = $state<DraftLine[]>([blankLine()]);
  steps = $state<DraftStep[]>([blankStep()]);
  source = $state('');
  photo = $state<DraftPhoto>({
    shown: null,
    change: 'none',
    uploading: null,
    file: null,
    error: null
  });
  /** The recipe's own pantry ingredient, once saved with Made ahead on. */
  homemade = $state<Ref | null>(null);
  /** The ingredients' own sizes, for the unit list of each line (by ingredient id). */
  sizes = $state<Record<number, SizeRef[]>>({});

  /** The recipe as it was opened (null: a new one) and the version the save must name. */
  opened = $state<RecipeOut | null>(null);
  #initial = '';
  /** Counts the picks (and the times the editor was given up), so an old upload knows it is old. */
  #picks = 0;
  /** Left with "Changes not saved": kept for Undo, so a finished upload is kept with it. */
  #parked = false;

  static from(recipe: RecipeOut): RecipeDraft {
    const draft = new RecipeDraft();
    draft.load(recipe);
    return draft;
  }

  load(recipe: RecipeOut): void {
    this.opened = recipe;
    this.name = recipe.name;
    this.description = recipe.description ?? '';
    this.time = text(recipe.time_minutes);
    this.serves = recipe.serves;
    const unit = recipe.makes?.unit ?? 'l';
    const known = (MAKES_UNITS as readonly string[]).includes(unit);
    this.makesAmount = recipe.makes?.amount_text ?? '';
    this.makesUnit = recipe.makes && !known ? COUNT : unit;
    this.makesWord = recipe.makes && !known ? unit : '';
    this.madeAhead = recipe.made_ahead;
    this.homemade = recipe.homemade;
    this.homemadeName = '';
    this.tags = [...recipe.tags];
    for (const n of NUTRIENTS) this.nutrition[n] = text(recipe.nutrition[n]);
    this.lines = recipe.lines.map(lineFrom);
    this.steps = recipe.steps.map((s) => ({
      key: nextKey('s'),
      kind: s.kind,
      text: s.text,
      optional: !!s.optional,
      wait: s.wait ? { ...s.wait } : null
    }));
    this.source = recipe.source_note ?? '';
    this.photo = { shown: recipe.photo, change: 'none', uploading: null, file: null, error: null };
    for (const line of recipe.lines) {
      if (line.food && line.size) this.sizes[line.food.id] = [line.size];
    }
    this.markSaved();
  }

  /** The editor now shows what is saved: no unsaved changes. */
  markSaved(): void {
    this.#initial = this.snapshot();
  }

  /** Everything that would be sent, as one string, to tell whether anything changed. */
  snapshot(): string {
    return JSON.stringify([
      this.name,
      this.description,
      this.time,
      this.serves,
      this.makesAmount,
      this.makesUnit,
      this.makesWord,
      this.madeAhead,
      this.homemadeName,
      this.tags,
      this.nutrition,
      this.lines.map((l) => [
        l.id,
        l.kind,
        l.words,
        l.amount,
        l.unit,
        l.food?.id,
        l.recipe?.id,
        l.note,
        l.optional
      ]),
      this.steps.map((s) => [s.kind, s.text, s.optional, s.wait]),
      this.source,
      this.photo.change,
      this.photo.shown?.id
    ]);
  }

  get dirty(): boolean {
    return this.snapshot() !== this.#initial;
  }

  /** Put back what a cancelled editor held (Undo of "Changes not saved"). */
  restore(from: RecipeDraft): void {
    this.opened = from.opened;
    this.homemade = from.homemade;
    this.name = from.name;
    this.description = from.description;
    this.time = from.time;
    this.serves = from.serves;
    this.makesAmount = from.makesAmount;
    this.makesUnit = from.makesUnit;
    this.makesWord = from.makesWord;
    this.madeAhead = from.madeAhead;
    this.homemadeName = from.homemadeName;
    this.tags = [...from.tags];
    this.nutrition = { ...from.nutrition };
    this.lines = from.lines.map((l) => ({ ...l }));
    this.steps = from.steps.map((s) => ({ ...s, wait: s.wait ? { ...s.wait } : null }));
    this.source = from.source;
    this.sizes = { ...from.sizes };
    this.photo = { ...from.photo, uploading: null };
    this.#initial = from.#initial;
  }

  /**
   * What the tab keeps while the editor is open (sessionStorage; see carry.ts). Not the photo:
   * an upload waiting to be saved is not kept, only a photo taken off.
   */
  toCarried(): Carried {
    return {
      version: this.opened?.version ?? null,
      name: this.name,
      description: this.description,
      time: this.time,
      serves: this.serves,
      makesAmount: this.makesAmount,
      makesUnit: this.makesUnit,
      makesWord: this.makesWord,
      madeAhead: this.madeAhead,
      homemadeName: this.homemadeName,
      tags: [...this.tags],
      nutrition: { ...this.nutrition },
      lines: this.lines.map((l) => ({ ...l })),
      steps: this.steps.map((s) => ({ ...s, wait: s.wait ? { ...s.wait } : null })),
      source: this.source,
      sizes: { ...this.sizes },
      photoRemoved: this.photo.change === 'removed'
    };
  }

  /**
   * Put back what the tab kept, on top of the recipe as just loaded. Anything that isn't the
   * shape `toCarried` writes is ignored and nothing changes (returns false). A draft made on an
   * older version keeps that version, so Save meets the "Someone changed this" note rather than
   * quietly writing over their change.
   */
  applyCarried(raw: unknown): boolean {
    const c = raw as Partial<Carried> | null;
    const str = (v: unknown) => typeof v === 'string';
    if (
      !c ||
      typeof c !== 'object' ||
      !str(c.name) ||
      !Array.isArray(c.lines) ||
      !Array.isArray(c.steps) ||
      !Array.isArray(c.tags) ||
      !c.nutrition ||
      typeof c.nutrition !== 'object'
    ) {
      return false;
    }
    const line = (l: Partial<DraftLine>): DraftLine => ({
      ...blankLine(l.kind === 'heading' ? 'heading' : 'ingredient'),
      id: typeof l.id === 'number' ? l.id : null,
      words: str(l.words) ? l.words! : '',
      amount: str(l.amount) ? l.amount! : '',
      unit: str(l.unit) ? l.unit! : '',
      food: l.food ?? null,
      recipe: l.recipe ?? null,
      recipeRemoved: !!l.recipeRemoved,
      note: str(l.note) ? l.note! : '',
      optional: !!l.optional
    });
    const step = (s: Partial<DraftStep>): DraftStep => ({
      ...blankStep(s.kind === 'heading' ? 'heading' : 'step'),
      text: str(s.text) ? s.text! : '',
      optional: !!s.optional,
      wait: waitFrom(s.wait)
    });
    const keep = (v: unknown, fallback: string) => (str(v) ? (v as string) : fallback);
    this.name = c.name!;
    this.description = keep(c.description, '');
    this.time = keep(c.time, '');
    this.serves = typeof c.serves === 'number' ? c.serves : null;
    this.makesAmount = keep(c.makesAmount, '');
    this.makesUnit = keep(c.makesUnit, 'l');
    this.makesWord = keep(c.makesWord, '');
    this.madeAhead = !!c.madeAhead;
    this.homemadeName = keep(c.homemadeName, '');
    this.tags = c.tags.filter(str) as string[];
    for (const n of NUTRIENTS) this.nutrition[n] = keep(c.nutrition[n], '');
    this.lines = c.lines.length ? c.lines.map(line) : [blankLine()];
    this.steps = c.steps.length ? c.steps.map(step) : [blankStep()];
    this.source = keep(c.source, '');
    this.sizes = { ...this.sizes, ...(c.sizes ?? {}) };
    if (c.photoRemoved && this.opened?.photo) {
      this.photo = { shown: null, change: 'removed', uploading: null, file: null, error: null };
    }
    if (this.opened && typeof c.version === 'number' && c.version !== this.opened.version) {
      this.opened = { ...this.opened, version: c.version };
    }
    return true;
  }

  // --- Photo ----------------------------------------------------------------------------------

  /** Upload the picked photo at once; the answer's id goes in `photo_id` on Save. */
  async pickPhoto(file: File): Promise<void> {
    const before = this.photo.shown;
    const mine = ++this.#picks;
    this.photo = { ...this.photo, uploading: file, error: null };
    try {
      const uploaded = await uploadPhoto(file);
      if (mine !== this.#picks) {
        // The editor was given up (or another photo picked) while this was going up: nobody
        // will save it, so give its place back now rather than after 24 hours, and show nothing.
        void deletePhoto(uploaded.id).catch(() => {});
        return;
      }
      // An earlier unsaved upload this one replaces gives its place back.
      if (this.photo.change === 'new' && before) void deletePhoto(before.id).catch(() => {});
      this.photo = { shown: uploaded, change: 'new', uploading: null, file, error: null };
    } catch (error) {
      if (mine !== this.#picks) return;
      // The server's own words ("That photo is bigger than 15 MB."); the old photo stays.
      const message = error instanceof ApiError ? error.detail : 'Couldn’t upload the photo.';
      this.photo = { ...this.photo, uploading: null, error: message };
    }
  }

  /** "Remove photo": a photo already saved goes on Save (`photo_id: null`); an upload goes now. */
  removePhoto(): void {
    const shown = this.photo.shown;
    if (this.photo.change === 'new' && shown) void deletePhoto(shown.id).catch(() => {});
    const had = this.opened?.photo ?? null;
    this.photo = {
      shown: null,
      change: had ? 'removed' : 'none',
      uploading: null,
      file: null,
      error: null
    };
  }

  /**
   * The editor was given up and nothing can bring it back: an upload that no recipe took gives
   * its place back, one still going up is deleted the moment it lands (see `pickPhoto`), and the
   * photo goes back to how the recipe was opened, so a deleted upload's id is never sent.
   */
  discardUpload(): void {
    this.#picks++;
    this.#parked = false;
    const shown = this.photo.shown;
    if (this.photo.change === 'new' && shown) {
      void deletePhoto(shown.id).catch(() => {});
      this.photo = {
        shown: this.opened?.photo ?? null,
        change: 'none',
        uploading: null,
        file: null,
        error: null
      };
    } else if (this.photo.uploading) {
      this.photo = { ...this.photo, uploading: null };
    }
  }

  /** Cancelled with "Changes not saved": while Undo can still be used, the upload is kept. */
  park(): void {
    this.#parked = true;
  }

  /** Undo was used: the editor is open again, with its upload. */
  resume(): void {
    this.#parked = false;
  }

  /** Undo can no longer be used (its toast is gone, or another editor was opened). */
  release(): void {
    if (this.#parked) this.discardUpload();
  }

  // --- Sending --------------------------------------------------------------------------------

  /** The body for POST or PUT, and what is wrong with the boxes if anything is. */
  build(): Built {
    const errors: Errors = {};
    const lineKeys: string[] = [];
    const stepKeys: string[] = [];
    const clean = (v: string) => v.trim();

    const minutes = clean(this.time);
    let time: number | null = null;
    if (minutes) {
      time = /^\d+$/.test(minutes) ? Number(minutes) : NaN;
      if (!(time >= 1 && time <= 14_400)) {
        errors.time = 'Use whole minutes, from 1 to 14,400.';
        time = null;
      }
    }

    let makes: RecipeIn['makes'] = null;
    if (clean(this.makesAmount)) {
      const unit = this.makesUnit === COUNT ? clean(this.makesWord) : this.makesUnit;
      if (!unit) errors.makes = 'Say what it makes, like dosas.';
      else makes = { amount: clean(this.makesAmount), unit };
    }

    const nutrition = {} as RecipeIn['nutrition'];
    for (const n of NUTRIENTS) {
      const value = clean(this.nutrition[n]);
      if (!value) nutrition[n] = null;
      else if (NUMBER.test(value)) nutrition[n] = value.replace(',', '.');
      else {
        nutrition[n] = null;
        errors[`nutrition.${n}`] = 'Use a number like 320 or 14.5, or leave it empty.';
      }
    }

    const lines: LineIn[] = [];
    for (const line of this.lines) {
      if (emptyLine(line)) continue;
      if (line.kind === 'heading') {
        if (!clean(line.words)) continue;
        lines.push({
          ...(line.id ? { id: line.id } : {}),
          kind: 'heading',
          words: clean(line.words)
        });
      } else {
        const size = line.unit.startsWith('size:') ? Number(line.unit.slice(5)) : null;
        const unit = size === null && line.unit ? line.unit : null;
        if (!clean(line.words) && !line.food && !line.recipe) {
          errors[`line:${line.key}`] = 'Type what it is, or pick an ingredient.';
        }
        lines.push({
          ...(line.id ? { id: line.id } : {}),
          kind: 'ingredient',
          words: clean(line.words),
          amount: clean(line.amount) || null,
          unit,
          size_id: size,
          food_id: line.food?.id ?? null,
          recipe_id: line.recipe?.id ?? null,
          note: clean(line.note) || null,
          optional: line.optional
        });
      }
      lineKeys.push(line.key);
    }

    const steps: RecipeIn['steps'] = [];
    for (const step of this.steps) {
      if (!clean(step.text)) continue;
      if (step.kind === 'step' && step.wait && step.waitInvalid) {
        errors[`wait:${step.key}`] = 'Type how long it waits, such as 4 hours.';
      }
      steps.push({
        kind: step.kind,
        text: step.kind === 'heading' ? clean(step.text) : step.text.trim(),
        optional: step.kind === 'step' && step.optional,
        wait: step.kind === 'step' && step.wait ? { ...step.wait } : null
      });
      stepKeys.push(step.key);
    }

    const body: RecipeIn = {
      name: clean(this.name),
      description: clean(this.description) || null,
      time_minutes: time,
      serves: this.serves,
      makes,
      made_ahead: this.madeAhead,
      homemade_name: this.madeAhead && clean(this.homemadeName) ? clean(this.homemadeName) : null,
      tags: [...this.tags],
      nutrition,
      lines,
      steps,
      source_note: clean(this.source) || null
    };
    // Opened from "Update nutrition": saving counts as looking at the figures (R3).
    if (this.nutritionChecked) body.nutrition_checked = true;
    // "Remove photo" says so with null; a photo left alone leaves the field out (cabledrawer 20 Oct).
    if (this.photo.change === 'removed') body.photo_id = null;
    else if (this.photo.change === 'new' && this.photo.shown) body.photo_id = this.photo.shown.id;
    return { body, lineKeys, stepKeys, errors };
  }

  /** Put a refusal from the server on the box it is about. Returns the first box's id. */
  explain(error: ApiError, built: Built): Errors {
    const errors: Errors = {};
    const data = (error.body ?? {}) as Record<string, unknown>;
    const line = typeof data.line === 'number' ? built.lineKeys[data.line] : undefined;
    if (line && (error.code === 'recipe_loop' || error.status === 404)) {
      errors[`line:${line}`] = error.detail;
    } else if (error.code === 'name_taken') {
      errors.homemade = error.detail;
    } else if (
      (error.code && PHOTO_CODES.has(error.code)) ||
      // Saving with an upload that is gone: a 404 with no line in it, while a new photo is waiting.
      (error.status === 404 && error.code === 'not_found' && !line && this.photo.change === 'new')
    ) {
      errors.photo = error.detail;
    } else if (error.status === 422 && Array.isArray(data.detail)) {
      for (const item of data.detail as { loc?: (string | number)[]; msg?: string }[]) {
        const [, field, index, sub] = item.loc ?? [];
        const msg = (item.msg ?? error.detail).replace(/^Value error, /, '');
        if (field === 'lines' && typeof index === 'number' && built.lineKeys[index]) {
          errors[`line:${built.lineKeys[index]}${sub === 'amount' ? '.amount' : ''}`] = msg;
        } else if (field === 'steps' && typeof index === 'number' && built.stepKeys[index]) {
          errors[`step:${built.stepKeys[index]}`] = msg;
        } else if (field === 'nutrition' && typeof index === 'string') {
          errors[`nutrition.${index}`] = msg;
        } else if (field === 'time_minutes') errors.time = msg;
        else if (field === 'makes') errors.makes = msg;
        else if (field === 'source_note') errors.source = msg;
        else if (field === 'description') errors.description = msg;
        else if (field === 'tags') errors.tags = msg;
        else if (field === 'homemade_name') errors.homemade = msg;
        else if (field === 'name') errors.name = msg;
        else errors.form = msg;
      }
    }
    return errors;
  }
}

/**
 * "Changes not saved · Undo": once that toast is gone (timed out, or replaced by another), Undo
 * is no longer offered, so the kept upload is deleted. Pressing Undo calls `resume()` first, so a
 * draft that is open again is left alone.
 */
export function releaseWhenToastGoes(draft: RecipeDraft, toastId: number | undefined): void {
  if (toastId === undefined) {
    draft.release();
    return;
  }
  const stop = $effect.root(() => {
    $effect(() => {
      if (toasts.current?.id === toastId) return;
      untrack(() => draft.release());
      queueMicrotask(() => stop());
    });
  });
}
