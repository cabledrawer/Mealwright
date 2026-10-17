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
  suggested: number;
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
  maybe_same: Ref[];
}

export type FoodFilter = 'all' | 'staples' | 'maybe_same';

export interface FoodList {
  total: number;
  counts: Record<FoodFilter, number>;
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
  maybe_same: Ref[];
  stock: AmountOut | null;
  last_change: { id: number; summary: string; can_undo: boolean } | null;
  /** Set when an old (merged-away) id was asked for. */
  merged_from?: Ref;
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
}

export interface Household {
  name: string;
  time_zone: string | null;
  cup_ml: 240 | 250 | null;
  cup_ml_used: number;
  undo_days: number;
  history_months: number;
  use_soon_days: number;
  today: string;
}
