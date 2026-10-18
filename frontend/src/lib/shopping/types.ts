// The shopping copy the screen draws from. Its shape is the "changes since" answer of
// docs/dev/sync-protocol.md section 5.5, so the offline copy (PR 6) can fill it directly.

export interface Person {
  login_id: number;
  name: string;
}

export interface Tick {
  id: string;
  by: Person;
  at: string;
  place_id: number | null;
  bought: { amount: number; display: string } | null;
  standing: boolean;
}

export interface ListRow {
  id: string;
  name: string;
  main: boolean;
  position: number;
  removed: boolean;
}

export interface ListItem {
  id: string;
  list_id: string;
  food_id: number;
  shop_id: number | null;
  /** In the ingredient's base unit (g, ml or items); null when left blank. */
  amount: number | null;
  size_id: number | null;
  /** The server's as-sold wording ("1 bunch"). */
  display: string | null;
  source: string;
  hand_edited: boolean;
  put_away_place_id: number | null;
  ticks: Tick[];
  added_by: Person | null;
  deleted: boolean;
  merged_into_id: string | null;
}

export interface Note {
  id: number;
  list_id: string;
  item_id: string | null;
  food_id: number | null;
  text: string;
  undo: string | null;
  gone: boolean;
}

export interface Question {
  id: number;
  list_id: string;
  item_id: string;
  title: string;
  text: string;
  yes: string;
  no: string;
  open: boolean;
}

export interface FoodSize {
  id: number;
  name: string;
  plural: string;
  /** Base amount of one (500 for a 500 g packet). */
  amount: number;
  usual: boolean;
}

export interface ShopFood {
  id: number;
  name: string;
  other_names: string[];
  counted_as: 'weight' | 'volume' | 'count';
  staple: boolean;
  aisle: string;
  shop_id: number | null;
  place_id: number | null;
  count_word?: string | null;
  count_word_plural?: string | null;
  /** Unknown (not sent by the online views): ask the server when needed. */
  sizes: FoodSize[] | null;
}

export interface ShopRow {
  id: number;
  name: string;
  position: number;
  aisle_order: string[] | null;
}

export interface PlaceRow {
  id: number;
  name: string;
  kind: string;
  position: number;
}

export interface ShoppingCopy {
  cursor: number;
  lists: ListRow[];
  items: ListItem[];
  notes: Note[];
  questions: Question[];
  foods: ShopFood[];
  shops: ShopRow[];
  places: PlaceRow[];
  /** Logins in the household. null when this server can't say yet. */
  people: Person[] | null;
  /** To-buy and ticked counts for lists whose items aren't in the copy. */
  counts?: Record<string, { to_buy: number; ticked: number }>;
}
