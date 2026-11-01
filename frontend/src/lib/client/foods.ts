// Foods, places and shops (contract 6.2 and 6.3).

import { api } from '#lib/api.js';
import type {
  Answer,
  Food,
  FoodFilter,
  FoodList,
  FoodPatch,
  FoodWrite,
  Place,
  PlaceKind,
  Shop
} from './types';

const key = (idempotencyKey: string) => ({ idempotencyKey });

export function listFoods(
  options: { q?: string; filter?: FoodFilter; after?: string | null; limit?: number } = {}
): Promise<FoodList> {
  const params = new URLSearchParams();
  if (options.q?.trim()) params.set('q', options.q.trim());
  if (options.filter && options.filter !== 'all') params.set('filter', options.filter);
  if (options.after) params.set('after', options.after);
  if (options.limit) params.set('limit', String(options.limit));
  const query = params.toString();
  return api<FoodList>('GET', `/foods${query ? `?${query}` : ''}`);
}

export const getFood = (id: number) => api<Food>('GET', `/foods/${id}`);

export const createFood = (
  body: { name: string; counted_as?: Food['counted_as']; place_id?: number; staple?: boolean },
  idempotencyKey: string
) => api<FoodWrite>('POST', '/foods', body, key(idempotencyKey));

/**
 * Save one field. Ask-once answers go inside an amount (running low at), or next to the
 * field otherwise (changing how it's counted).
 */
export function patchFood(
  id: number,
  patch: FoodPatch,
  idempotencyKey: string,
  answers: Answer[] = []
) {
  let body: Record<string, unknown> = { ...patch };
  if (answers.length) {
    if ('running_low_at' in patch && patch.running_low_at) {
      body = { running_low_at: { ...patch.running_low_at, answers } };
    } else {
      body = { ...patch, answers };
    }
  }
  return api<FoodWrite>('PATCH', `/foods/${id}`, body, key(idempotencyKey));
}

export const removeFood = (id: number, idempotencyKey: string) =>
  api<{ change: FoodWrite['change']; food?: Food }>(
    'DELETE',
    `/foods/${id}`,
    undefined,
    key(idempotencyKey)
  );

export const addOtherName = (id: number, name: string, idempotencyKey: string) =>
  api<FoodWrite>('POST', `/foods/${id}/other-names`, { name }, key(idempotencyKey));

export const removeOtherName = (id: number, nameId: number, idempotencyKey: string) =>
  api<FoodWrite>('DELETE', `/foods/${id}/other-names/${nameId}`, undefined, key(idempotencyKey));

export const addSize = (
  id: number,
  size: { name: string; amount: { amount: number; unit: string } },
  idempotencyKey: string,
  answers: Answer[] = []
) =>
  api<FoodWrite>(
    'POST',
    `/foods/${id}/sizes`,
    answers.length ? { ...size, amount: { ...size.amount, answers } } : size,
    key(idempotencyKey)
  );

export const patchSize = (
  id: number,
  sizeId: number,
  patch: { usual: true } | { name: string } | { amount: number },
  idempotencyKey: string
) => api<FoodWrite>('PATCH', `/foods/${id}/sizes/${sizeId}`, patch, key(idempotencyKey));

export const removeSize = (id: number, sizeId: number, idempotencyKey: string) =>
  api<FoodWrite>('DELETE', `/foods/${id}/sizes/${sizeId}`, undefined, key(idempotencyKey));

export const addStandIn = (id: number, standInId: number, idempotencyKey: string) =>
  api<FoodWrite>(
    'POST',
    `/foods/${id}/stand-ins`,
    { food_id: standInId, both_ways: false },
    key(idempotencyKey)
  );

export const removeStandIn = (id: number, standInId: number, idempotencyKey: string) =>
  api<FoodWrite>('DELETE', `/foods/${id}/stand-ins/${standInId}`, undefined, key(idempotencyKey));

/** "Not the same": hides a Maybe-the-same pair for good. Quiet; no Undo. */
export const notTheSame = (id: number, otherId: number) =>
  api<void>('POST', `/foods/${id}/not-the-same`, { food_id: otherId });

export const mergeFood = (
  id: number,
  intoId: number,
  idempotencyKey: string,
  answers: Answer[] = []
) =>
  api<FoodWrite>('POST', `/foods/${id}/merge`, { into_id: intoId, answers }, key(idempotencyKey));

/** Turn one of a food's other names back into its own food (revived, if it came from a merge). */
export const splitFood = (id: number, otherNameId: number, idempotencyKey: string) =>
  api<FoodWrite>('POST', `/foods/${id}/split`, { other_name_id: otherNameId }, key(idempotencyKey));

export const getPlaces = () => api<Place[]>('GET', '/places');

export const getShops = () => api<Shop[]>('GET', '/shops');

/** Adds a shop, or returns the one already called that, so "+ Shop" never makes doubles. */
export const addShop = (name: string) => api<Shop>('POST', '/shops', { name });

/** Adds a place (last in the order). A name the household already has is a 409 `place_exists`
 *  carrying that place, so "+ Place" picks it instead of making a double. */
export const addPlace = (name: string, kind: PlaceKind) =>
  api<Place>('POST', '/places', { name, kind });
