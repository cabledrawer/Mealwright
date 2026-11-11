// Importing a recipe from a link or pasted text (docs/dev/recipe-import.md, "The import's
// API"): the review, and Save. Online only: nothing here is queued. The server does the
// reading; the screen only shows it and sends the choices back.

import { api } from '#lib/api.js';
import type { Change, CountedAs, Pints, Ref } from './types';
import type { Nutrition, PhotoOut, SizeRef } from './recipes';
import type { StepWait } from '#lib/timeWords.js';

export type Label = 'matched' | 'to_confirm' | 'needs_you' | 'staple';

export interface NewIngredient {
  name: string;
  counted_as: CountedAs;
  place: Ref | null;
}

/** A heading made its own recipe on Check (F190, cabledrawer 8 Nov): the new Made ahead recipe's name and
 *  what it makes. Kept in the review, so a draft keeps it; the server never sets it. */
export interface OwnRecipe {
  name: string;
  amount: number;
  unit: string;
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
  /** Set when the line says pints: what it comes to in each kind of pint, in ml. */
  pint_ml?: { uk_ml: number; us_ml: number } | null;
  /** Optional: "(optional)" was in the line, or it is under "For serving". The person can switch it. */
  optional?: boolean;
  /** A heading only: the section is made its own recipe (F190). */
  own?: OwnRecipe | null;
  /** The other choice of an "or" line, as a line of its own (F217); never set on that line itself. */
  alternative?: ReviewLine | null;
}

/** A step on the review: "wait" is the reader's suggestion, kept once the person says Yes, it
 *  waits (`wait_confirmed`; only the review and a draft hold that, Save never sends it). */
export interface ReviewStep {
  kind: 'step' | 'heading';
  text: string;
  optional?: boolean;
  wait?: StepWait | null;
  wait_confirmed?: boolean;
  /** Check only: the Waits boxes on this step aren't right yet, so Save waits (never sent). */
  wait_invalid?: boolean;
}

/** A step as Save sends it. */
export interface SaveStep {
  kind: 'step' | 'heading';
  text: string;
  optional?: boolean;
  wait?: StepWait | null;
}

/** Pints on a review: the household's own, whether the page looks American, and the pint the
 *  lines were read with (a US page is read with US pints while the household's are UK). */
export interface ReviewPints {
  household: Pints;
  us_site: boolean;
  reading: Pints;
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
  /** The page's own total time, before suggested waits came off `time_minutes` (M1). */
  page_time_minutes?: number | null;
  serves: number | null;
  makes: { amount: number; unit: string } | null;
  tags: string[];
  nutrition: Nutrition;
  photo: ReviewPhoto;
  lines: ReviewLine[];
  steps: ReviewStep[];
  /** Two ways of cooking it found in the method (M2): the first's name and the second. */
  method_name?: string | null;
  second_method?: { name: string; steps: ReviewStep[] } | null;
  counts: { matched: number; to_confirm: number; needs_you: number; staple: number };
  lines_cut: boolean;
  steps_cut: boolean;
  steps_shortened: number;
  left_out: { heading: string; lines: number }[];
  /** Always sent by the server; optional here so a review kept before 0.6 still fits. */
  pints?: ReviewPints;
  /** Several links were pasted: how many were left unread (the first is the review). */
  more_links?: number;
}

/** How a line is tied to an ingredient when it is saved. */
export type LineLink =
  | { kind: 'ingredient'; food_id: number; learn?: string | null }
  | { kind: 'new' | 'staple'; name: string; counted_as: CountedAs; place_id: number | null }
  /** Another recipe of the household makes it (F188); `place_id`: where the pantry keeps it. */
  | { kind: 'recipe'; recipe_id: number; place_id: number | null }
  /** The recipe this same save makes from a section (F190): its place in `own_recipes`. */
  | { kind: 'own_recipe'; own_recipe: number };

export interface SaveLine {
  kind: 'ingredient' | 'heading';
  words: string;
  amount: number | null;
  unit: string | null;
  size_id: number | null;
  note: string | null;
  link: LineLink | null;
  optional?: boolean;
}

/** A section made its own recipe, saved with the main one (F190): a Made ahead recipe. */
export interface SaveOwnRecipe {
  name: string;
  makes: { amount: number; unit: string };
  lines: SaveLine[];
  steps: SaveStep[];
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
  steps: SaveStep[];
  /** Sections made their own recipes: both are saved together or not at all, with one Undo. */
  own_recipes?: SaveOwnRecipe[];
  method_name?: string | null;
  second_method?: { name: string; steps: SaveStep[] } | null;
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
