// Importing a recipe from a link or pasted text (docs/dev/recipe-import.md, "The import's
// API"): the review, and Save. Online only: nothing here is queued. The server does the
// reading; the screen only shows it and sends the choices back.

import { api } from '#lib/api.js';
import type { Change, CountedAs, Ref } from './types';
import type { Nutrition, PhotoOut, SizeRef } from './recipes';

export type Label = 'matched' | 'to_confirm' | 'needs_you' | 'staple';

export interface NewIngredient {
  name: string;
  counted_as: CountedAs;
  place: Ref | null;
}

/** One line of the review: as written, as read, and what it is in the kitchen. */
export interface ReviewLine {
  kind: 'ingredient' | 'heading';
  written: string;
  /** What the saved line will hold. */
  words: string;
  amount: number | null;
  amount_text: string | null;
  unit: string | null;
  size: SizeRef | null;
  note: string | null;
  readable: boolean;
  label: Label | null;
  food: Ref | null;
  place: string | null;
  matched_by: string | null;
  counts: boolean;
  new_ingredient: NewIngredient | null;
  learn_name: string | null;
}

export interface ReviewPhoto {
  state: 'downloaded' | 'off' | 'none' | 'failed';
  photo: PhotoOut | null;
  message: string | null;
}

export interface ImportReview {
  source: { kind: 'link' | 'text'; url: string | null; site: string | null };
  name: string;
  description: string | null;
  author: string | null;
  time_minutes: number | null;
  serves: number | null;
  makes: { amount: number; unit: string } | null;
  tags: string[];
  nutrition: Nutrition;
  photo: ReviewPhoto;
  lines: ReviewLine[];
  steps: { kind: 'step' | 'heading'; text: string }[];
  counts: { matched: number; to_confirm: number; needs_you: number; staple: number };
  lines_cut: boolean;
  steps_cut: boolean;
  steps_shortened: number;
  left_out: { heading: string; lines: number }[];
}

/** How a line is tied to an ingredient when it is saved. */
export type LineLink =
  | { kind: 'ingredient'; food_id: number; learn?: string | null }
  | { kind: 'new' | 'staple'; name: string; counted_as: CountedAs; place_id: number | null };

export interface SaveLine {
  kind: 'ingredient' | 'heading';
  words: string;
  amount: number | null;
  unit: string | null;
  size_id: number | null;
  note: string | null;
  link: LineLink | null;
}

export interface SaveBody {
  name: string;
  description: string | null;
  time_minutes: number | null;
  serves: number | null;
  makes: { amount: number; unit: string } | null;
  tags: string[];
  nutrition: Nutrition;
  lines: SaveLine[];
  steps: { kind: 'step' | 'heading'; text: string }[];
  source_url: string | null;
  source_author: string | null;
  photo_id: number | null;
  /** Saving from a draft: its id. The draft is removed in the same save. */
  draft_id?: number | null;
}

export interface Saved {
  recipe: Ref;
  change: Change;
  new_ingredients: Ref[];
  learned: number;
}

/** A link can take a while (up to 30 seconds), so the wait is longer than for other requests. */
const IMPORT_TIMEOUT_MS = 60_000;

export const startImport = (text: string, again = false) =>
  api<ImportReview>('POST', '/recipes/import', { text, again }, { timeoutMs: IMPORT_TIMEOUT_MS });

export const saveImport = (body: SaveBody, idempotencyKey: string) =>
  api<Saved>('POST', '/recipes/import/save', body, { idempotencyKey });
