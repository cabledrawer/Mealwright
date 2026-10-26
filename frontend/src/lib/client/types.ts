// The shapes of the 0.2 API (docs/dev/api-0.2.md, "API and data for 0.2"). Field names
// are the API's own (snake_case); only the web app's code sees them, never people.

export interface Ref {
  id: number;
  name: string;
}

export type PlaceKind = 'fridge' | 'freezer' | 'cupboard';

export interface Place extends Ref {
  kind: PlaceKind;
}

export type Shop = Ref;

export interface Who {
  login_id: number;
  name: string;
}

/** One thing a person did: one Undo button (contract 6.1). */
export interface Change {
  id: number;
  kind: string;
  at: string;
  who: Who;
  /** A plain sentence made by the server: "Used 200 g spinach". */
  summary: string;
  can_undo: boolean;
  undo_until: string | null;
  undone: { at: string; who: Who } | null;
  /** Stock changes (and their Undos): each packet touched, before → after. */
  lines?: ChangeLine[];
  /** The same, added up per ingredient and place and worded as sold, for showing. */
  totals?: ChangeTotal[];
}

export type CountedAs = 'weight' | 'volume' | 'count';

/** An amount as the server shows it (contract 5.4). Use `display`; never rebuild it. */
export interface AmountOut {
  amount: number;
  unit?: string;
  as_sold?: {
    count: number;
    size: { id: number; name: string; plural: string; amount: number };
  } | null;
  about?: boolean;
  display: string;
  /** Just the first part ("½ packet"), for boxes such as "Running low at". */
  short?: string;
}

/** An answer to an "ask once" question (contract 4.4). */
export type Answer =
  | { kind: 'weight_per_ml' | 'item_weight'; food_id: number; grams: number; remember: boolean }
  | { kind: 'size'; food_id: number; name: string; amount: number };

/** An amount someone typed or picked (contract 4.3). */
export interface AmountIn {
  amount: number;
  unit?: string;
  size_id?: number;
  answers?: Answer[];
}

/** What the server needs to know before it can do a change (409 ask_once). */
export interface Ask {
  food_id: number;
  food_name: string;
  kind: Answer['kind'];
  question: string;
  unit?: string;
  per?: 'cup' | 'item' | string;
  cup_ml?: number;
  name?: string;
  /** A starting figure from the built-in table, or null when there's no good guess. */
  suggested: number | null;
}

/** A food that might be the same as this one, and which way a merge would go. */
export interface MaybeSame extends Ref {
  /** The food that stays. */
  merge_into: number;
  /** True when the food whose list this is would be merged away. */
  merge_this: boolean;
}

/** A row of the Ingredients list. */
export interface FoodRow extends Ref {
  other_names: string[];
  matched_name: string | null;
  counted_as: CountedAs;
  staple: boolean;
  /** "Packets · 500 g", "Slices", "Staple". */
  counted_as_display: string;
  place: Ref | null;
  stand_ins: Ref[];
  maybe_same: MaybeSame[];
  /** How many recipes have a line for it (0.4). Left out of the rows the shopping list's search builds on the phone. */
  used_in_recipes?: number;
}

export type FoodFilter = 'all' | 'staples' | 'maybe_same' | 'unused';

export interface FoodList {
  total: number;
  counts: Record<FoodFilter, number> & { maybe_same_pairs: number };
  foods: FoodRow[];
  next: string | null;
}

export interface Size {
  id: number;
  name: string;
  plural: string;
  amount: number;
  /** "Packet = 500 g". */
  display: string;
  usual: boolean;
  added_when_shopping: boolean;
}

/** One food, as the editor shows it. */
export interface Food extends Ref {
  other_names: Ref[];
  counted_as: CountedAs;
  staple: boolean;
  count_word: string | null;
  count_word_plural: string | null;
  place: Ref | null;
  shop: Ref | null;
  sizes: Size[];
  cup_weight: { grams: number; from: 'you' | 'table'; cup_ml: number } | null;
  item_weight: { grams: number; from: 'you' | 'table' } | null;
  running_low_at: AmountOut | null;
  stand_ins: (Ref & { both_ways: boolean })[];
  stands_in_for: Ref[];
  maybe_same: MaybeSame[];
  stock: AmountOut | null;
  last_change: { id: number; summary: string; can_undo: boolean } | null;
  /** Set when an old (merged-away) id was asked for. */
  merged_from?: Ref;
  /** How many recipes have a line for it, and which (A to Z). */
  used_in_recipes: number;
  used_in: Ref[];
  /** The recipe whose own made-ahead ingredient this is: it can't be removed while that is on. */
  made_by: Ref | null;
}

/** The answer to every food write. `change` is null when nothing changed. */
export interface FoodWrite {
  food: Food;
  change: Change | null;
}

/** One field at a time: saves as you go (contract 6.2, PATCH /foods/{id}). */
export type FoodPatch =
  | { name: string }
  | { counted_as: CountedAs }
  | { staple: boolean }
  | { count_word: string | null }
  | { place_id: number | null }
  | { shop_id: number | null }
  | { running_low_at: AmountIn | null }
  | { cup_weight: number | null }
  | { item_weight: number | null };

export interface UndoResult {
  /** done: all of it; partly: some (message says what); nothing: nothing could be put back. */
  result: 'done' | 'partly' | 'nothing';
  message: string;
  change: Change;
  undone: Change;
  food: Food | null;
  /** Removed ingredients this Undo returned to Ingredients (the message says so). */
  brought_back: { id: number; name: string }[];
}

export interface Household {
  name: string;
  time_zone: string | null;
  cup_ml: 240 | 250 | null;
  cup_ml_used: number;
  undo_days: number;
  history_months: number;
  use_soon_days: number;
  /** 1 is Monday … 7 is Sunday. */
  week_starts_on: number;
  /** Today, in the household's own time zone ("2026-10-17"). */
  today: string;
}

// --- Stock (the Pantry screen, contract 6.4) ---------------------------------------

/** One packet, one bag, one carton: kept separately so the oldest is used first. */
export interface Lot {
  id: number;
  stock: AmountOut;
  use_by: string | null;
  days_left: number | null;
  use_soon: boolean;
  added_on: string;
  frozen_on: string | null;
  size_id: number | null;
  /** Holds less than its size: show "· open". (Every packet of a known size has the ¼ ½ ¾ Full picks.) */
  open: boolean;
}

/** One food in one place. */
export interface Group {
  food: { id: number; name: string; counted_as: CountedAs };
  place: Place;
  stock: AmountOut;
  lots_count: number;
  dates_count: number;
  use_by: string | null;
  days_left: number | null;
  use_soon: boolean;
  running_low: boolean;
  lots: Lot[];
}

export interface PantryPlace extends Place {
  items: number;
  groups: Group[];
}

export type PantryFilter = 'all' | 'use_soon' | 'running_low' | 'staples';

export interface Pantry {
  today: string;
  counts: { items: number; tubs: number; use_soon: number; running_low: number };
  places: PantryPlace[];
  staples: Ref[];
}

export interface UseSoonLot {
  id: number;
  food: Ref;
  place: Place;
  stock: AmountOut;
  use_by: string | null;
  days_left: number | null;
  /** "Paneer · 1 of 2 packs". */
  position: number;
  of: number;
}

/** The answer to every stock write: the change, and the food's groups as they are now. */
export interface StockWrite {
  change: Change | null;
  groups: Group[];
  /** Asked to use more than there was: how much was missing. */
  short_by: AmountOut | null;
}

/** One ingredient in one place: what a change did to it ("Paneer: 0 g → 2 packs · 400 g"). */
export interface ChangeTotal {
  food_id: number;
  name: string;
  /** null for packets the change added. */
  place_before: Ref | null;
  place_after: Ref | null;
  before: AmountOut;
  after: AmountOut;
}

export interface ChangeLine {
  food: Ref;
  lot_id: number | null;
  before: AmountOut;
  after: AmountOut;
  place_before: Ref | null;
  place_after: Ref | null;
  use_by_before?: string | null;
  use_by_after?: string | null;
}
