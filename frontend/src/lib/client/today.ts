// Today (docs/dev/api-0.2.md section 6.3c): what is on the table, and the answers to "Did you
// cook Sambar?". Online only, like the Plan; the web app keeps the last answer to show offline.

import { api } from '#lib/api.js';
import type { MealSlot, Person, Plan, PlanWrite, TubLeft } from './plan';
import type { UseSoonLot, UseSoonTub } from './types';

/** A planned meal whose day has come, waiting for Cooked it, Didn't or Move it. */
export interface WaitingMeal {
  meal_id: number;
  date: string;
  slot_id: number;
  /** The recipe "Any left over?" is about, or null: the meal has no recipe. */
  leftover_item_id: number | null;
  /** The use-by a new tub would get (the household's tub life from the meal's day). */
  use_by_fridge: string;
  use_by_freezer: string;
}

export interface NextCook {
  date: string;
  slot_id: number;
  meal_id: number;
  batch_id: number;
  recipe_name: string;
  tub_count: number;
}

export interface TodayData {
  today: string;
  first_day: boolean;
  slots: MealSlot[];
  /** From a week ago to a week ahead, with its items, batch cooks and tubs. */
  plan: Plan;
  people: Person[];
  waiting: WaitingMeal[];
  tubs_left: TubLeft[];
  tubs_left_more: boolean;
  use_soon_lots: UseSoonLot[];
  /** One row per batch and place, the same rows as the Pantry's Use soon (F203). */
  use_soon_tubs: UseSoonTub[];
  next_cook: NextCook | null;
}

export interface Leftovers {
  count: number;
  place_kind: 'fridge' | 'freezer';
  use_by?: string;
  item_id?: number;
}

export const getToday = () => api<TodayData>('GET', '/today');

export const cookedIt = (mealId: number, leftovers: Leftovers | null, key: string) =>
  api<PlanWrite>('POST', `/plan/meals/${mealId}/cooked`, leftovers ? { leftovers } : {}, {
    idempotencyKey: key
  });

export const didntCook = (mealId: number, key: string) =>
  api<PlanWrite>('POST', `/plan/meals/${mealId}/didnt`, undefined, { idempotencyKey: key });

export const moveIt = (mealId: number, to: { date: string; slot_id: number }, key: string) =>
  api<PlanWrite>('POST', `/plan/meals/${mealId}/moved`, to, { idempotencyKey: key });
