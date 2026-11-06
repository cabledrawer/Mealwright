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
  /** The recipe's own default servings, or null. */
  serves?: number | null;
}

export interface PlanItem {
  id: number;
  position: number;
  kind: 'recipe' | 'tub' | 'ingredient' | 'note';
  recipe: PlanRecipe | null;
  tub_id: number | null;
  ingredient: (Ref & { removed: boolean }) | null;
  /** The name of a recipe or ingredient deleted for good (recipe and ingredient are then null). */
  kept_name: string | null;
  servings: number | null;
  /** A note's text ("Eating out"); null for anything else. */
  note: string | null;
  /**
   * Serves − N +: how many people a recipe is for now. Its own `servings` once set; else the
   * recipe's Serves (a meal planned before 0.7 has none set); one for a batch's cook meal.
   * null for anything but a recipe, and for a recipe with no Serves.
   */
  eating: number | null;
  /**
   * This recipe has been cooked (F157): its own "Cooked it", its Cook once batch's, or its meal was
   * marked cooked before 0.7.0 (a meal with several recipes is cooked one at a time).
   */
  cooked: boolean;
}

export interface PlanMeal {
  id: number;
  date: string;
  slot_id: number;
  status: 'planned' | 'cooked' | 'didnt' | 'moved';
  items: PlanItem[];
  /** One serving of each item added up; null when none has kcal. */
  kcal: number | null;
  /** Who is eating, by sign-in (proposed, for cabledrawer; member profiles come in 0.8). Empty: everyone. */
  eater_login_ids: number[];
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
  /** A palette name ("purple", "amber", "green", "blue", "rose", "teal"), or null. */
  colour: string | null;
  /** Portions (0.7): the tubs plus the cook-day meal, and how many are not planned yet. */
  portions: number;
  portions_left: number;
}

export interface PlanTub {
  id: number;
  batch_id: number;
  amount_quarters: number;
  /** "tub 2 of 4": 2. */
  number: number;
  place_id: number | null;
  /** Where it is: the fridge or the freezer (null: no place). */
  place_kind: 'fridge' | 'freezer' | 'cupboard' | null;
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
  /** Cook once: the batch cook that was made. */
  batch_id?: number | null;
}

export type DropMode = 'move' | 'copy' | 'leftovers';

export const getMealSlots = () => api<MealSlot[]>('GET', '/meal-slots');

export const getPlan = (from: string, to: string) =>
  api<Plan>('GET', `/plan?from=${from}&to=${to}`);

export const planItem = (
  body: {
    date: string;
    slot_id: number;
    recipe_id?: number;
    ingredient_id?: number;
    note?: string;
  },
  key: string
) => api<PlanWrite>('POST', '/plan/items', body, { idempotencyKey: key });

/** Serves − N +: how many people a planned recipe is for. */
export const setPlanServings = (id: number, servings: number, key: string) =>
  api<PlanWrite>('PATCH', `/plan/items/${id}`, { servings }, { idempotencyKey: key });

/** Who is eating a meal (an empty list: everyone). */
export const setPlanEaters = (mealId: number, loginIds: number[], key: string) =>
  api<PlanWrite>(
    'PUT',
    `/plan/meals/${mealId}/eaters`,
    { login_ids: loginIds },
    { idempotencyKey: key }
  );

export const removePlanItem = (id: number, key: string) =>
  api<PlanWrite>('DELETE', `/plan/items/${id}`, undefined, { idempotencyKey: key });

export const removePlanMeal = (id: number, key: string) =>
  api<PlanWrite>('DELETE', `/plan/meals/${id}`, undefined, { idempotencyKey: key });

export const movePlanItem = (
  id: number,
  to: { date: string; slot_id: number; mode: DropMode; if_none_left?: WhenNoneLeft },
  key: string
) => api<PlanWrite>('POST', `/plan/items/${id}/move`, to, { idempotencyKey: key });

export const movePlanMeal = (
  id: number,
  to: { date: string; slot_id: number; mode: DropMode; if_none_left?: WhenNoneLeft },
  key: string
) => api<PlanWrite>('POST', `/plan/meals/${id}/move`, to, { idempotencyKey: key });

export const switchMealSlot = (id: number, enabled: boolean, key: string) =>
  api<PlanWrite>('PATCH', `/meal-slots/${id}`, { enabled }, { idempotencyKey: key });

// --- Cook once, eat for… (PR 4) ------------------------------------------------------------

export type Pattern = 'lunches' | 'lunch_dinner' | 'dinners' | 'pick';

/** A day and a meal. */
export interface Spot {
  date: string;
  slot_id: number;
}

export interface BatchBody {
  tub_count: number;
  pattern: Pattern;
  member_login_ids: number[];
  extras_to_freezer: boolean;
  prep_note?: string;
  /** The person's own choice, one per tub (null: not in a meal). Left out: the pattern picks. */
  placements?: (Spot | null)[];
}

export interface PreviewTub {
  number: number;
  date: string | null;
  slot_id: number | null;
  place_kind: 'fridge' | 'freezer';
  member_login_id: number | null;
  use_by: string;
  /** The meal it lands in already had food. */
  meal_has_food: boolean;
}

export interface BatchPreview {
  recipe_id: number;
  recipe_name: string;
  recipe_serves: number | null;
  cook_date: string;
  cook_meal_id: number;
  colour: string;
  tubs: PreviewTub[];
  placed: number;
  per_tub: { kcal: number | null; protein_g: number | null; fibre_g: number | null };
}

export interface Person {
  login_id: number;
  name: string;
}

export interface TubLeft {
  id: number;
  batch_id: number;
  number: number;
  tub_count: number;
  recipe_name: string;
  colour: string | null;
  cooked_on: string;
  amount_quarters: number;
  place_id: number | null;
  place_kind: 'fridge' | 'freezer' | 'cupboard' | null;
  member_login_id: number | null;
  use_by: string;
}

export const getPeople = () => api<Person[]>('GET', '/plan/people');

export const getTubsLeft = () => api<{ tubs: TubLeft[]; more: boolean }>('GET', '/plan/tubs-left');

export const previewBatch = (itemId: number, body: BatchBody) =>
  api<BatchPreview>('POST', `/plan/items/${itemId}/batch/preview`, body);

export const makeBatch = (itemId: number, body: BatchBody, key: string) =>
  api<PlanWrite>('POST', `/plan/items/${itemId}/batch`, body, { idempotencyKey: key });

export const placeTub = (id: number, to: Spot, key: string) =>
  api<PlanWrite>('POST', `/plan/tubs/${id}/place`, to, { idempotencyKey: key });

export const editTub = (
  id: number,
  fields: { member_login_id?: number | null; use_by?: string },
  key: string
) => api<PlanWrite>('PATCH', `/plan/tubs/${id}`, fields, { idempotencyKey: key });

export const tubToFreezer = (id: number, key: string) =>
  api<PlanWrite>('POST', `/plan/tubs/${id}/freezer`, undefined, { idempotencyKey: key });

export const fillFromFreezer = (from: string, to: string, key: string) =>
  api<PlanWrite>('POST', '/plan/fill-from-freezer', { from, to }, { idempotencyKey: key });

// --- Portions and "Leftovers on…" (0.7 P1) ------------------------------------------------------

export interface Portions {
  recipe_name: string;
  /** false: no batch yet, the first leftovers make one (the counts are then null). */
  has_batch: boolean;
  batch_id: number | null;
  /** The tubs plus the cook-day meal. */
  portions: number | null;
  cook_day: number | null;
  tubs: number | null;
  /** Tubs already planned in a meal. */
  in_meals: number | null;
  left: number | null;
  /** The last day a tub of this batch can go in a meal. */
  use_by: string;
  /** The use-by of each spare tub, soonest first: a tub goes only in a meal on or before it. */
  spare_use_by: string[];
}

export type WhenNoneLeft = 'ask' | 'cook_more' | 'add_anyway';

export const getPortions = (itemId: number) =>
  api<Portions>('GET', `/plan/items/${itemId}/portions`);

export const planLeftovers = (
  itemId: number,
  meals: Spot[],
  ifNoneLeft: WhenNoneLeft,
  key: string
) =>
  api<PlanWrite>(
    'POST',
    `/plan/items/${itemId}/leftovers`,
    { meals, if_none_left: ifNoneLeft },
    { idempotencyKey: key }
  );
