// The Stocktake: place by place, each answer saved as it is tapped (contract 6.5a).

import { api } from '#lib/api.js';
import type { AmountOut, Change, CountedAs, PackSuggestion, Place, Size } from './types';

const key = (idempotencyKey: string) => ({ idempotencyKey });

/** What was answered. The server sends numbers as text ("0.5"). */
export interface StocktakeAnswer {
  /** The open packet's share: 0 (None), 0.25, 0.5, 0.75 or 1 (Full). */
  fraction: string | null;
  /** Whole packets besides the open one. */
  more: number;
  /** For an ingredient counted one by one. */
  count: string | null;
}

export interface StocktakeRow {
  food: { id: number; name: string; counted_as: CountedAs };
  staple: boolean;
  restocked_on: string | null;
  restocked_days_ago: number | null;
  /** Put here with "+ Something else", not usually kept here. */
  added: boolean;
  answered: boolean;
  /** All of it in this place now, as sold. */
  stock: AmountOut;
  /** Its Usual size; null means "ask once" (never for a staple or a counted ingredient). */
  pack: Size | null;
  pack_suggestions: PackSuggestion[];
  answer: StocktakeAnswer | null;
  /** What is there now as the picks read it (answered or not): the open packet's share, and
   *  the whole packets besides it. */
  fraction_now: string | null;
  more_now: number;
  /** Counted one by one (a count, or a pack word of "tin"): − / + with `count_now`, no
   *  fractions. The server decides; the screen follows. */
  counted: boolean;
  count_now: string | null;
  /** The word for the count ("tin", "tins"); null: none. */
  count_word: string | null;
  count_word_plural: string | null;
}

export interface StocktakeStep extends Place {
  finished: boolean;
  answered: number;
  total: number;
}

export interface Stocktake {
  places: StocktakeStep[];
  /** The first place not finished; null when they all are. */
  current_place_id: number | null;
  started: boolean;
  complete: boolean;
}

export interface StocktakePlace {
  place: Place;
  /** "Place 3 of 5". */
  number: number;
  of: number;
  finished: boolean;
  answered: number;
  total: number;
  previous: Place | null;
  next: Place | null;
  rows: StocktakeRow[];
}

export interface StocktakeWrite {
  /** Null when nothing changed (it was already so). */
  change: Change | null;
  row: StocktakeRow;
  answered: number;
  total: number;
}

/** What a tap sends: a pick (with whole packets besides), or a count. */
export type AnswerBody = { fraction: number; more?: number } | { count: number };

export const getStocktake = () => api<Stocktake>('GET', '/stocktake');

export const getStocktakePlace = (placeId: number) =>
  api<StocktakePlace>('GET', `/stocktake/places/${placeId}`);

const at = (placeId: number, foodId: number) => `/stocktake/places/${placeId}/foods/${foodId}`;

export const answerFood = (
  placeId: number,
  foodId: number,
  body: AnswerBody,
  idempotencyKey: string
) => api<StocktakeWrite>('POST', `${at(placeId, foodId)}/answer`, body, key(idempotencyKey));

export const makeStapleHere = (placeId: number, foodId: number, idempotencyKey: string) =>
  api<StocktakeWrite>('POST', `${at(placeId, foodId)}/make-staple`, {}, key(idempotencyKey));

/** The pack size asked once: it becomes the Usual size. */
export const setPackSize = (
  placeId: number,
  foodId: number,
  size: { name: string; amount: number | { amount: number; unit: string } },
  idempotencyKey: string
) => api<StocktakeWrite>('POST', `${at(placeId, foodId)}/set-size`, size, key(idempotencyKey));

/** "+ Something else in the Cupboard": count this ingredient here too. */
export const addSomethingElse = (placeId: number, foodId: number) =>
  api<StocktakeWrite>('POST', `/stocktake/places/${placeId}/foods`, { food_id: foodId });

export const finishPlace = (placeId: number) =>
  api<Stocktake>('POST', `/stocktake/places/${placeId}/finish`, {});

export const restartStocktake = () => api<Stocktake>('POST', '/stocktake/restart', {});
