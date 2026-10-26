// The meal plan (docs/dev/api-0.2.md section 6.3a): read, and written in 0.6 PR 3. Online
// only, like the Pantry: nothing here touches the offline queue.

import { api } from '#lib/api.js';
import type { Change, Ref } from './types';

export interface MealSlot {
  id: number;
  name: string;
  position: number;
  enabled: boolean;
}

export interface PlanRecipe extends Ref {
  /** Removed, but still inside the undo window. */
  removed: boolean;
  /** The small photo's address, or null. */
  photo_url: string | null;
  time_minutes: number | null;
  /** Per serving; null is unknown. */
  kcal: number | null;
}

export interface PlanItem {
  id: number;
  position: number;
  kind: 'recipe' | 'tub' | 'ingredient';
  recipe: PlanRecipe | null;
  tub_id: number | null;
  ingredient: (Ref & { removed: boolean }) | null;
  /** The name of a recipe or ingredient deleted for good (recipe and ingredient are then null). */
  kept_name: string | null;
  servings: number | null;
}

export interface PlanMeal {
  id: number;
  date: string;
  slot_id: number;
  status: 'planned' | 'cooked' | 'didnt' | 'moved';
  items: PlanItem[];
  /** One serving of each item added up; null when none has kcal. */
  kcal: number | null;
}

export interface PlanBatch {
  id: number;
  recipe_id: number | null;
  recipe_name: string;
  cook_meal_id: number | null;
  cooked_on: string;
  tub_count: number;
  pattern: 'lunches' | 'lunch_dinner' | 'dinners' | 'pick';
  prep_note: string | null;
  colour: string | null;
}

export interface PlanTub {
  id: number;
  batch_id: number;
  amount_quarters: number;
  /** "tub 2 of 4": 2. */
  number: number;
  place_id: number | null;
  member_login_id: number | null;
  use_by: string;
}

export interface Plan {
  start: string;
  end: string;
  meals: PlanMeal[];
  batch_cooks: PlanBatch[];
  tubs: PlanTub[];
}

/** What every plan write answers: the change (with its Undo) and where the meal ended up. */
export interface PlanWrite {
  change: Change | null;
  meal_id: number | null;
  item_id: number | null;
}

export type DropMode = 'move' | 'copy' | 'leftovers';

export const getMealSlots = () => api<MealSlot[]>('GET', '/meal-slots');

export const getPlan = (from: string, to: string) =>
  api<Plan>('GET', `/plan?from=${from}&to=${to}`);

export const planItem = (
  body: { date: string; slot_id: number; recipe_id?: number; ingredient_id?: number },
  key: string
) => api<PlanWrite>('POST', '/plan/items', body, { idempotencyKey: key });

export const removePlanItem = (id: number, key: string) =>
  api<PlanWrite>('DELETE', `/plan/items/${id}`, undefined, { idempotencyKey: key });

export const removePlanMeal = (id: number, key: string) =>
  api<PlanWrite>('DELETE', `/plan/meals/${id}`, undefined, { idempotencyKey: key });

export const movePlanItem = (
  id: number,
  to: { date: string; slot_id: number; mode: DropMode },
  key: string
) => api<PlanWrite>('POST', `/plan/items/${id}/move`, to, { idempotencyKey: key });

export const movePlanMeal = (
  id: number,
  to: { date: string; slot_id: number; mode: DropMode },
  key: string
) => api<PlanWrite>('POST', `/plan/meals/${id}/move`, to, { idempotencyKey: key });

export const switchMealSlot = (id: number, enabled: boolean, key: string) =>
  api<PlanWrite>('PATCH', `/meal-slots/${id}`, { enabled }, { idempotencyKey: key });
