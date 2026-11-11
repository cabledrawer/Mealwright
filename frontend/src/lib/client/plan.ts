// The meal plan (docs/dev/api-0.2.md section 6.3a): read, and written in 0.6 PR 3. Online
// only, like the Pantry: nothing here touches the offline queue.

import { api } from '#lib/api.js';
import type { Change, Ref } from './types';
import type { StepWait } from '#lib/timeWords.js';

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
  /** All the recipe's waits added up (marinate, soak...); null when none. */
  wait?: StepWait | null;
  /** Per serving; null is unknown. */
  kcal: number | null;
  /** The recipe's own default servings, or null. */
  serves?: number | null;
  /** How many of its ingredient lines are Optional (R3): the meal can be asked which it uses. */
  optional_count?: number;
  /** The ways of cooking it (M2): empty for a recipe with one. */
  methods?: { id: number; name: string }[];
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
  /** The ids of the recipe's Optional lines this meal will not use (R3). Empty: all count. */
  optional_skipped?: number[];
  /** The way of cooking it this meal uses, for a recipe with two (M2). */
  method_id?: number | null;
  method?: string | null;
  /** The long wait to start ahead (M3): null when there is none, or the recipe is cooked. */
  ahead?: PlanAhead | null;
}

/** A recipe's long wait in a planned meal (M3, F124): times are the household's own wall clock. */
export interface PlanAhead {
  step_id: number;
  /** The step that waits, in its own words. */
  step_text: string;
  wait: StepWait;
  /** The recipe's own working time in this way of cooking it; null when unknown. */
  active_minutes: number | null;
  /** When the meal is eaten ("08:00"). */
  eats_at: string;
  /** When the wait will be started; null: not set. */
  start_day: string | null;
  start_time: string | null;
  /** When it was begun; null: not yet. */
  started_day: string | null;
  started_time: string | null;
  /** How long it has waited, in minutes, as of this answer; null: not begun. */
  waited_minutes: number | null;
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
  /** The Batch cook session it was made in (B2), or null. */
  session_id?: number | null;
}

/** A Batch cook (Experimental) session: its recipes are the batch cooks with its id. */
export interface PlanSession {
  id: number;
  cook_day: string;
  /** The rough "about X together" and "one by one" minutes it was planned with. */
  together_minutes: number | null;
  one_by_one_minutes: number | null;
  /** When the first start-ahead of its recipes begins ("from 10:00"), in the household's time. */
  start_day: string | null;
  start_time: string | null;
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
  batch_sessions?: PlanSession[];
}

/** What every plan write answers: the change (with its Undo) and where the meal ended up. */
export interface PlanWrite {
  change: Change | null;
  meal_id: number | null;
  item_id: number | null;
  /** Cook once: the batch cook that was made. */
  batch_id?: number | null;
  /** Batch cook: the session that was made. */
  session_id?: number | null;
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
    /** The recipe's Optional lines the person will use (R3). Left out: every line counts. */
    optional_use?: number[];
    /** The way of cooking a recipe with two the meal uses (M2). Left out: the one used last. */
    method_id?: number;
    /** When the recipe's long wait will be started (M3): a day and a clock time. */
    start?: StartAt;
  },
  key: string
) => api<PlanWrite>('POST', '/plan/items', body, { idempotencyKey: key });

/** A day and a clock time on the household's wall clock. */
export interface StartAt {
  day: string;
  /** "21:00". */
  time: string;
}

/** When a planned recipe's long wait will be started (M3); null takes the time away. */
export const setPlanStart = (id: number, start: StartAt | null, key: string) =>
  api<PlanWrite>('PUT', `/plan/items/${id}/start`, { start }, { idempotencyKey: key });

/** The long wait is begun (M3): "Done already", or Cook mode past its step. */
export const setPlanStarted = (id: number, started: boolean, key: string) =>
  api<PlanWrite>('PUT', `/plan/items/${id}/started`, { started }, { idempotencyKey: key });

export interface StartOption extends StartAt {
  /** The time the dish is ready by if it is started then ("08:00"). */
  ready_by: string;
  ready_by_day: string;
}

export interface StartOptions {
  /** The wait that is started ahead; null when the recipe has none (nothing to ask). */
  wait: StepWait | null;
  /** The meal's usual time. */
  eats_at: string;
  options: StartOption[];
}

export const getStartOptions = (
  recipeId: number,
  day: string,
  slotId: number,
  methodId?: number | null
) =>
  api<StartOptions>(
    'GET',
    `/plan/start-options?recipe_id=${recipeId}&date=${day}&slot_id=${slotId}${
      methodId ? `&method_id=${methodId}` : ''
    }`
  );

/** Which Optional ingredients a planned recipe will use (R3). */
export const setPlanOptional = (id: number, use: number[], key: string) =>
  api<PlanWrite>('PUT', `/plan/items/${id}/optional`, { use }, { idempotencyKey: key });

/** Which way of cooking a planned recipe uses (M2). */
export const setPlanMethod = (id: number, methodId: number, key: string) =>
  api<PlanWrite>(
    'PUT',
    `/plan/items/${id}/method`,
    { method_id: methodId },
    { idempotencyKey: key }
  );

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
  to: {
    date: string;
    slot_id: number;
    mode: DropMode;
    if_none_left?: WhenNoneLeft;
    /** A recipe with a long wait, moved or copied: when its wait will be started (M3). */
    start?: StartAt;
  },
  key: string
) => api<PlanWrite>('POST', `/plan/items/${id}/move`, to, { idempotencyKey: key });

export const movePlanMeal = (
  id: number,
  to: {
    date: string;
    slot_id: number;
    mode: DropMode;
    if_none_left?: WhenNoneLeft;
    /** A meal moved: the new start time of each recipe in it with a long wait (cabledrawer 10 Nov). */
    starts?: (StartAt & { item_id: number })[];
  },
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

export const placeTub = (id: number, to: Spot, key: string, fromTubsLeft = false) =>
  api<PlanWrite>(
    'POST',
    `/plan/tubs/${id}/place`,
    fromTubsLeft ? { ...to, from_tubs_left: true } : to,
    { idempotencyKey: key }
  );

export const editTub = (
  id: number,
  fields: { member_login_id?: number | null; use_by?: string },
  key: string
) => api<PlanWrite>('PATCH', `/plan/tubs/${id}`, fields, { idempotencyKey: key });

/** Binned on a tub (cabledrawer 8 Nov): what is left of it is thrown away. Online only, like the
 * other tub writes. */
export const binTub = (id: number, key: string) =>
  api<PlanWrite>('POST', `/plan/tubs/${id}/bin`, undefined, { idempotencyKey: key });

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
