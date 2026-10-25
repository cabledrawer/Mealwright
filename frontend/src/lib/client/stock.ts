// Stock: the Pantry screen and every change to what's in it (contract 6.4).

import { api } from '#lib/api.js';
import type { AmountIn, Answer, Pantry, PantryFilter, StockWrite, UseSoonLot } from './types';

const key = (idempotencyKey: string) => ({ idempotencyKey });

/** Ask-once answers go inside the amount (contract 4.4). */
function withAnswers(amount: AmountIn, answers: Answer[]): AmountIn {
  return answers.length ? { ...amount, answers } : amount;
}

/** The pantry. `search` looks at every name an ingredient has (the server does the matching). */
export function getPantry(filter: PantryFilter = 'all', search = ''): Promise<Pantry> {
  const params = new URLSearchParams();
  if (filter !== 'all') params.set('filter', filter);
  if (search.trim()) params.set('q', search.trim());
  const query = params.toString();
  return api<Pantry>('GET', query ? `/pantry?${query}` : '/pantry');
}

export const getUseSoon = () => api<{ lots: UseSoonLot[] }>('GET', '/pantry/use-soon');

export interface NewStock {
  food_id: number;
  amount: AmountIn;
  place_id?: number;
  use_by?: string | null;
}

/** Add to pantry. */
export const addStock = (stock: NewStock, idempotencyKey: string, answers: Answer[] = []) =>
  api<StockWrite>(
    'POST',
    '/stock',
    { ...stock, amount: withAnswers(stock.amount, answers) },
    key(idempotencyKey)
  );

/** What's left of one packet: a ¼ ½ ¾ Full pick, or a typed amount. */
export const setLeft = (
  lotId: number,
  left: { fraction: number } | { amount: AmountIn },
  idempotencyKey: string,
  answers: Answer[] = []
) =>
  api<StockWrite>(
    'POST',
    `/stock/${lotId}/left`,
    'amount' in left ? { amount: withAnswers(left.amount, answers) } : left,
    key(idempotencyKey)
  );

/** Used it (all of it, unless an amount is given). */
export const usedLot = (lotId: number, idempotencyKey: string) =>
  api<StockWrite>('POST', `/stock/${lotId}/used`, {}, key(idempotencyKey));

export const binnedLot = (lotId: number, idempotencyKey: string) =>
  api<StockWrite>('POST', `/stock/${lotId}/binned`, {}, key(idempotencyKey));

/** To the freezer, with a new use-by (3 months unless given). */
export const toFreezer = (lotId: number, idempotencyKey: string, useBy?: string) =>
  api<StockWrite>(
    'POST',
    `/stock/${lotId}/to-freezer`,
    useBy ? { use_by: useBy } : {},
    key(idempotencyKey)
  );

export const moveLot = (lotId: number, placeId: number, idempotencyKey: string) =>
  api<StockWrite>('POST', `/stock/${lotId}/move`, { place_id: placeId }, key(idempotencyKey));

export const setUseBy = (lotId: number, useBy: string | null, idempotencyKey: string) =>
  api<StockWrite>('PATCH', `/stock/${lotId}`, { use_by: useBy }, key(idempotencyKey));

/** "How much did you use?" on a food in a place: the oldest / soonest packets go first. */
export const foodUsed = (
  foodId: number,
  amount: AmountIn,
  placeId: number,
  idempotencyKey: string,
  answers: Answer[] = []
) =>
  api<StockWrite>(
    'POST',
    `/foods/${foodId}/used`,
    { amount: withAnswers(amount, answers), place_id: placeId },
    key(idempotencyKey)
  );

/** "3 left" on a food in a place (0 = none left). */
export const foodLeft = (
  foodId: number,
  amount: AmountIn,
  placeId: number,
  idempotencyKey: string,
  answers: Answer[] = []
) =>
  api<StockWrite>(
    'POST',
    `/foods/${foodId}/left`,
    { amount: withAnswers(amount, answers), place_id: placeId },
    key(idempotencyKey)
  );
