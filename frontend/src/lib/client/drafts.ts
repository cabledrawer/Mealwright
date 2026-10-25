// Drafts: imports left unfinished, kept for 15 days (docs/dev/recipe-import.md, "Drafts").
// Online only, like the import: nothing here is queued.

import { api } from '#lib/api.js';
import type { Change, CountedAs, Ref } from './types';
import type { ImportReview } from './imports';

/** What one line was set to on the review, as a draft keeps it. */
export type DraftChoice =
  | { kind: 'ingredient'; food: Ref; learn: boolean }
  | { kind: 'new' | 'staple'; name: string; counted_as: CountedAs; place_id: number | null };

/** Every choice so far: the boxes on top (null: as read) and a choice per settled line. */
export interface DraftChoices {
  name: string | null;
  serves: string | null;
  minutes: string | null;
  /** The line's place in the review → its choice (JSON keys are text). */
  lines: Record<string, DraftChoice>;
}

/** A draft in the Drafts list. */
export interface DraftBrief {
  id: number;
  name: string;
  source: { kind: 'link' | 'text'; site: string | null };
  started_by: string;
  started_at: string;
  updated_at: string;
  expires_at: string;
  /** 15 for a draft changed just now, 1 on its last day. */
  days_left: number;
  /** Ingredient lines, and how many are tied to an ingredient (matched, or chosen). */
  lines_total: number;
  lines_checked: number;
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
