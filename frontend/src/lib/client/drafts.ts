// Drafts: imports left unfinished, kept for 15 days (docs/dev/recipe-import.md, "Drafts").
// Online only, like the import: nothing here is queued.

import { api } from '#lib/api.js';
import type { Change, CountedAs, Pints, Ref } from './types';
import type { ImportReview } from './imports';

/** What one line was set to on the review, as a draft keeps it. */
export type DraftChoice =
  | { kind: 'ingredient'; food: Ref; learn: boolean }
  | { kind: 'new' | 'staple'; name: string; counted_as: CountedAs; place_id: number | null }
  /** "Made in this recipe" (F108): saved as words only. */
  | { kind: 'here' }
  /** "Made in another recipe" (F188): the recipe's link, and where the pantry keeps it. */
  | { kind: 'recipe'; recipe: Ref; place_id: number | null };

/** Every choice so far: the boxes on top (null: as read) and a choice per settled line. */
export interface DraftChoices {
  name: string | null;
  serves: string | null;
  minutes: string | null;
  /** The pints switch on a US recipe; null (or missing): as the review read it. */
  pints?: Pints | null;
  /** The line's place in the review → its choice (JSON keys are text). */
  lines: Record<string, DraftChoice>;
}

/** A draft in the Drafts list. */
export interface DraftBrief {
  id: number;
  name: string;
  source: { kind: 'link' | 'text' | 'mealie'; site: string | null };
  started_by: string;
  started_at: string;
  updated_at: string;
  expires_at: string;
  /** 15 for a draft changed just now, 1 on its last day. */
  days_left: number;
  /** Ingredient lines, and how many are tied to an ingredient (matched, or chosen). */
  lines_total: number;
  lines_checked: number;
  /** The first few lines still to check, as written (0.9.5: shown for a draft from Mealie). */
  waiting?: string[];
}

export interface DraftList {
  drafts: DraftBrief[];
  count: number;
}

/** A draft to carry on with. */
export interface DraftOut extends DraftBrief {
  text: string;
  review: ImportReview;
  choices: DraftChoices;
}

export interface DraftBody {
  text: string;
  review: ImportReview;
  choices: DraftChoices;
}

export const listDrafts = () => api<DraftList>('GET', '/recipes/drafts');

export const getDraft = (id: number | string) => api<DraftOut>('GET', `/recipes/drafts/${id}`);

export const keepDraft = (body: DraftBody, idempotencyKey: string) =>
  api<DraftOut>('POST', '/recipes/drafts', body, { idempotencyKey });

export const changeDraft = (id: number, body: DraftBody) =>
  api<DraftOut>('PUT', `/recipes/drafts/${id}`, body);

export const deleteDraft = (id: number, idempotencyKey: string) =>
  api<{ change: Change }>('DELETE', `/recipes/drafts/${id}`, undefined, { idempotencyKey });

// Fixing Mealie drafts by ingredient (spec "Fixing Mealie drafts by ingredient", cabledrawer
// 15 Nov, 0.9.5-beta.2; backend api/v1/drafts.py). The lines nobody could read are grouped by
// ingredient across every draft; one answer goes into each draft that uses it. Online only.

/** One group: an ingredient still unanswered in some drafts. */
export interface IngredientGroup {
  /** What an answer names the group by. */
  key: string;
  name: string;
  /** How many drafts use it, and how many lines. */
  drafts: number;
  lines: number;
  /** Up to two of the lines as written. */
  examples: string[];
  /** An ingredient the household has that it may be. */
  suggestion: Ref | null;
  /** The first guess for a new ingredient: its name and where it is kept. */
  new_name: string;
  new_place: Ref | null;
}

export interface IngredientGroups {
  /** Most-used first (the first `limit`). */
  groups: IngredientGroup[];
  /** Every group still unanswered. */
  total: number;
  drafts: number;
  recipes_ready: number;
  places: Ref[];
}

/** Every way one group's lines are written, most-used first (F259: what "+ more" shows). */
export interface GroupLines {
  key: string;
  /** The first 200, each with how many lines write it that way. */
  lines: { written: string; count: number }[];
  /** Every different way it is written. */
  total: number;
}

/** One answer for a group: an ingredient the household has, a new one, or plain text. */
export type GroupAnswer =
  | { key: string; kind: 'ingredient'; food_id: number }
  | { key: string; kind: 'new'; name: string; place_id: number | null }
  | { key: string; kind: 'text' };

export interface GroupAnswered {
  change: Change;
  drafts: number;
  moved: number;
  food: Ref | null;
}

export const listGroups = (limit?: number) =>
  api<IngredientGroups>('GET', `/recipes/drafts/by-food${limit ? `?limit=${limit}` : ''}`);

export const groupLines = (key: string) =>
  api<GroupLines>('GET', `/recipes/drafts/by-food/lines?key=${encodeURIComponent(key)}`);

export const answerGroup = (body: GroupAnswer, idempotencyKey: string) =>
  api<GroupAnswered>('POST', '/recipes/drafts/by-food/answer', body, { idempotencyKey });
