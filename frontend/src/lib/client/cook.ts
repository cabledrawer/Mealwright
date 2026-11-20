// "Cooked it": what it would take from the pantry, and the confirm that takes it
// (docs/dev/api-endpoints.md section 6.3d). Online only, like the Plan.

import { api } from '#lib/api.js';
import type { AmountOut, Answer, Ask, Change, Ref } from './types';

export type RowStatus =
  'take' | 'none_in_pantry' | 'staple' | 'ask' | 'no_amount' | 'not_linked' | 'make_first';

export interface LotTake {
  lot_id: number;
  place: Ref | null;
  use_by: string | null;
  amount: AmountOut;
  used_all: boolean;
}

export interface Take {
  food: Ref;
  stand_in: boolean;
  amount: AmountOut;
  before: AmountOut;
  after: AmountOut;
  lots: LotTake[];
}

/** What the recipe asks for on its own side, when the pantry counts it differently. */
export interface Need {
  amount: number;
  unit: 'g' | 'ml' | 'item';
}

/** One ingredient of the review. */
export interface CookRow {
  key: string;
  status: RowStatus;
  lines: { id: number; words: string; amount?: string | null; unit?: string | null }[];
  food: Ref | null;
  recipe: Ref | null;
  needed: AmountOut | null;
  takes: Take[];
  /** How the row's Use switch starts. */
  use: boolean;
  short: AmountOut | null;
  make_first: boolean;
  add_to_list: boolean;
  list_amount: AmountOut | null;
  running_low: boolean;
  in_freezer: AmountOut | null;
  from_freezer: boolean;
  ask: Ask | null;
  /** `needed` came from changing units: a guess. */
  estimate: boolean;
  ask_need: Need | null;
  /** About half of the first packet, in the pantry's unit. */
  half: AmountOut | null;
  count_note: { count: number; word: string } | null;
  bought: boolean;
  /** What the pantry counts the ingredient in. */
  unit: 'g' | 'ml' | 'count' | null;
  /** A counted ingredient's word, plural ("bulbs"). */
  unit_word?: string | null;
}

export interface Proposal {
  recipe: Ref;
  portions: number;
  servings: number | null;
  rows: CookRow[];
}

export interface MealProposal {
  meal_id: number;
  items: { item_id: number; proposal: Proposal }[];
}

export interface TypedAmount {
  amount: number;
  unit: string;
}

/** What the person chose on one row (rows not sent are as proposed). */
export interface CookChoice {
  key: string;
  use?: boolean;
  used?: TypedAmount;
  left?: TypedAmount;
  from_freezer?: boolean;
  add_to_list?: boolean;
  bought?: boolean;
}

export interface CookedRecord {
  id: number;
  portions: number;
}

export interface CookedWrite {
  change: Change;
  cooked: CookedRecord | null;
}

export interface CookedMealWrite {
  change: Change;
  cooked: CookedRecord[];
}

export interface MealItemBody {
  item_id: number;
  portions?: number;
  choices?: CookChoice[];
}

export const previewBatch = (batchId: number, body: { portions?: number; answers: Answer[] }) =>
  api<Proposal>('POST', `/plan/batches/${batchId}/cook/preview`, body);

export const previewMeal = (mealId: number, body: { items: MealItemBody[]; answers: Answer[] }) =>
  api<MealProposal>('POST', `/plan/meals/${mealId}/cook/preview`, body);

export const cookMeal = (
  mealId: number,
  body: { items: MealItemBody[]; answers: Answer[] },
  key: string
) => api<CookedMealWrite>('POST', `/plan/meals/${mealId}/cook`, body, { idempotencyKey: key });

export const cookBatch = (
  batchId: number,
  body: { portions?: number; choices: CookChoice[]; answers: Answer[] },
  key: string
) => api<CookedWrite>('POST', `/plan/batches/${batchId}/cook`, body, { idempotencyKey: key });
