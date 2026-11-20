// Batch cook (Experimental; 0.8 wave 6, B2; docs/dev/api-endpoints.md 6.3a-2): suggestions of recipes to
// cook together, and the sessions "Plan this batch" makes. Online only, like the rest of the plan.

import { api } from '#lib/api.js';
import type { BatchBody, BatchPreview, PlanWrite } from './plan';

export interface BatchPick {
  recipe_id: number;
  name: string;
  /** The recipe's steps added up. */
  minutes: number;
  /** Why it was picked, in words ("Shares onion and tomato prep with Sambar; …"). */
  why: string;
  use_soon: { foods: string[]; days_left: number } | null;
}

export interface BatchSuggestions {
  day: string;
  count: number;
  picks: BatchPick[];
  together_minutes: number;
  one_by_one_minutes: number;
  /** How many recipes could be picked at all (the ones with at least one step). */
  pool: number;
  /** The next days with no cooking planned; the first is the default. */
  free_days: string[];
  kitchen: { hob_rings: number; pressure_cookers: number; oven: boolean; asked: boolean };
}

export interface SuggestionAsk {
  day?: string;
  count?: number;
  keep?: number[];
  skip?: number[];
}

export function getSuggestions(ask: SuggestionAsk): Promise<BatchSuggestions> {
  const query = new URLSearchParams();
  if (ask.day) query.set('day', ask.day);
  if (ask.count) query.set('count', String(ask.count));
  for (const id of ask.keep ?? []) query.append('keep', String(id));
  for (const id of ask.skip ?? []) query.append('skip', String(id));
  const text = query.toString();
  return api<BatchSuggestions>('GET', `/batch-cook/suggestions${text ? `?${text}` : ''}`);
}

/** One recipe of a session, with its Cook once choices. */
export interface SessionRecipe extends BatchBody {
  recipe_id: number;
  /** The Optional lines it will use (left out: every one counts) and the way of cooking it, for a
   * recipe with two (left out: the one used last), as adding it to the plan asks. */
  optional_use?: number[];
  method_id?: number;
}

export interface SessionBody {
  date: string;
  /** Left out, the server picks the meal (a change keeps its own). */
  slot_id?: number;
  /** The session being changed: the preview then has it taken off first. */
  session_id?: number;
  recipes: SessionRecipe[];
}

/** Where the last recipe's tubs would land, after the ones before it. */
export const previewSession = (body: SessionBody) =>
  api<BatchPreview>('POST', '/batch-cook/sessions/preview', body);

export const makeSession = (body: SessionBody, key: string) =>
  api<PlanWrite>('POST', '/batch-cook/sessions', body, { idempotencyKey: key });

export const changeSession = (id: number, body: SessionBody, key: string) =>
  api<PlanWrite>('PUT', `/batch-cook/sessions/${id}`, body, { idempotencyKey: key });

export const removeSession = (id: number, key: string) =>
  api<PlanWrite>('DELETE', `/batch-cook/sessions/${id}`, undefined, { idempotencyKey: key });

export interface SessionRead {
  id: number;
  cook_day: string;
  slot_id: number | null;
  together_minutes: number | null;
  one_by_one_minutes: number | null;
  recipes: {
    batch_id: number;
    recipe_id: number | null;
    recipe_name: string;
    tub_count: number;
    pattern: string;
    colour: string | null;
  }[];
}

export const getSession = (id: number) => api<SessionRead>('GET', `/batch-cook/sessions/${id}`);
