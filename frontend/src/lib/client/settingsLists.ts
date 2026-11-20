// Settings › Meal slots and Shops & places (docs/dev/api-endpoints.md 4.1, 4.5, 5): ordering,
// renaming, adding and removing. Shops and places can be managed by anyone in the household;
// meal slots by admins only (the server says so with 403 `admins_only`).

import { api } from '#lib/api.js';
import type { Place, PlaceKind, Shop } from './types';
import type { MealSlot, PlanWrite } from './plan';

const key = (idempotencyKey: string) => ({ idempotencyKey });

/** What a removal answers: the change, which carries the Undo. */
export interface Removed {
  change: import('./types').Change | null;
}

// --- Meal slots (admins) ----------------------------------------------------------------------

export const renameMealSlot = (id: number, name: string, idempotencyKey: string) =>
  api<PlanWrite>('PATCH', `/meal-slots/${id}`, { name }, key(idempotencyKey));

export const addMealSlot = (name: string) => api<MealSlot>('POST', '/meal-slots', { name });

export const orderMealSlots = (ids: number[], idempotencyKey: string) =>
  api<PlanWrite>('PUT', '/meal-slots/order', { ids }, key(idempotencyKey));

// --- Shops ------------------------------------------------------------------------------------

export const renameShop = (id: number, name: string) =>
  api<Shop>('PATCH', `/shops/${id}`, { name });

export const orderShops = (ids: number[]) => api<Shop[]>('PUT', '/shops/order', { ids });

export const removeShop = (id: number, idempotencyKey: string) =>
  api<Removed>('DELETE', `/shops/${id}`, undefined, key(idempotencyKey));

// --- Places -----------------------------------------------------------------------------------

export const renamePlace = (id: number, name: string) =>
  api<Place>('PATCH', `/places/${id}`, { name });

export const orderPlaces = (ids: number[]) => api<Place[]>('PUT', '/places/order', { ids });

/** Removes a place. With things in it the server answers 409 `place_not_empty` (with `things`);
 *  send `moveTo` and they go there first. */
export const removePlace = (id: number, idempotencyKey: string, moveTo?: number) =>
  api<Removed>(
    'DELETE',
    `/places/${id}${moveTo === undefined ? '' : `?move_to=${moveTo}`}`,
    undefined,
    key(idempotencyKey)
  );

export type { PlaceKind };
