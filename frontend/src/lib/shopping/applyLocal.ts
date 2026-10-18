// What the screen shows: the copy (what the server last said) with this phone's waiting
// changes on top (docs/dev/sync-protocol.md section 11.2, UX principle 8).
//
// applyLocal is pure: it never changes the copy it is given, and gives back a new one. It does
// the list part only. It never works out pantry stock: only the server changes the pantry
// (L-33, FE-5). A change goes from the screen only when the server refuses it, because then it
// leaves the queue; a change that couldn't be sent yet stays in the queue, so it stays shown.
//
// Adding an ingredient that is already on the list (same list, same shop, not ticked) joins
// that line and adds the amounts up, keeping the line's size, as the server does for a line
// this phone could see or made itself (L-12): 6 eggs + 6 eggs = 12, "2 boxes".

import type { Action } from './actions';
import { baseText } from './format';
import type { FoodSize, ListItem, Person, ShopFood, ShoppingCopy } from './types';

export interface LocalHints {
  /** Who is signed in: what this phone ticks and adds is theirs. */
  me: Person | null;
  /** Ingredients picked in the add box that the copy doesn't have yet. */
  foods?: readonly ShopFood[];
  /** Packet sizes fetched for ingredients the copy has no sizes for. */
  sizes?: Readonly<Record<number, FoodSize[]>>;
}

/** The copy with `actions` (this phone's waiting changes, oldest first) shown on top. */
export function applyLocal(
  copy: ShoppingCopy,
  actions: readonly Action[],
  hints: LocalHints = { me: null }
): ShoppingCopy {
  const extra = (hints.foods ?? []).filter((f) => !copy.foods.some((c) => c.id === f.id));
  const sizes = hints.sizes ?? {};
  if (!actions.length && !extra.length && !Object.keys(sizes).length) return copy;

  const out = structuredClone(copy);
  out.foods.push(...structuredClone(extra));
  for (const food of out.foods) {
    const known = sizes[food.id];
    if (!food.sizes && known) food.sizes = structuredClone(known);
  }

  // Item IDs that now mean another line: merged by the server, or joined here.
  const alias: Record<string, string> = {};
  for (const item of out.items) if (item.merged_into_id) alias[item.id] = item.merged_into_id;
  const itemOf = (id: string): ListItem | undefined => {
    for (let hops = 0; alias[id] && hops < 100; hops++) id = alias[id]!;
    return out.items.find((i) => i.id === id);
  };

  // An undo of a change that is still waiting: neither is shown.
  const undone = new Set(actions.flatMap((a) => (a.kind === 'undo' ? [a.undoes] : [])));
  let localFoods = 0;
  const newFoodId = () => Math.min(0, ...out.foods.map((f) => f.id)) - ++localFoods;

  for (const action of actions) {
    if (undone.has(action.id)) continue;
    switch (action.kind) {
      case 'create_list':
        if (!out.lists.some((l) => l.id === action.list_id)) {
          out.lists.push({
            id: action.list_id,
            name: action.name,
            main: false,
            position: Math.max(-1, ...out.lists.map((l) => l.position)) + 1,
            removed: false
          });
        }
        break;
      case 'rename_list':
        for (const list of out.lists) if (list.id === action.list_id) list.name = action.name;
        break;
      case 'remove_list':
        for (const list of out.lists) if (list.id === action.list_id) list.removed = true;
        break;
      case 'add':
        add(action);
        break;
      case 'set_amount': {
        const item = itemOf(action.item_id);
        if (!item) break;
        item.amount = action.amount;
        item.size_id = action.size_id ?? null;
        item.hand_edited = true;
        item.display = localDisplay(item.amount, item.size_id, foodOf(item.food_id));
        break;
      }
      case 'delete': {
        const item = itemOf(action.item_id);
        if (item) item.deleted = true;
        break;
      }
      case 'tick': {
        const item = itemOf(action.item_id);
        // A second tick of a ticked line does nothing (the server says already_ticked).
        if (!item || item.ticks.some((t) => t.standing)) break;
        item.ticks.push({
          id: action.id,
          by: hints.me ?? { login_id: 0, name: '' },
          at: action.made_at,
          place_id: null,
          bought: null,
          standing: true
        });
        break;
      }
      case 'untick': {
        const item = itemOf(action.item_id);
        for (const t of item?.ticks ?? []) if (action.tick_ids.includes(t.id)) t.standing = false;
        break;
      }
      case 'put_away': {
        const item = itemOf(action.item_id);
        if (!item) break;
        item.put_away_place_id = action.place_id;
        for (const t of item.ticks) {
          if (t.standing || action.tick_ids.includes(t.id)) t.place_id = action.place_id;
        }
        break;
      }
      case 'different_pack': {
        const item = itemOf(action.item_id);
        const t = item?.ticks.find((x) => x.id === action.tick_id);
        if (!item || !t) break;
        const amount = action.count * action.pack;
        const food = foodOf(item.food_id);
        t.bought = {
          amount,
          display: localDisplay(amount, action.size_id ?? null, food) ?? ''
        };
        break;
      }
      case 'clear_ticked':
        for (const id of action.item_ids) {
          const item = itemOf(id);
          if (item) item.deleted = true;
        }
        break;
      case 'answer_double_tick':
        for (const q of out.questions) if (q.id === action.question_id) q.open = false;
        break;
      case 'dismiss_note':
        for (const n of out.notes) if (n.id === action.note_id) n.gone = true;
        break;
      case 'undo': {
        // Undoing a change the server already has: a tick can be taken back here; the rest
        // shows once the server answers.
        for (const item of out.items) {
          for (const t of item.ticks) if (t.id === action.undoes) t.standing = false;
        }
        break;
      }
    }
  }
  return out;

  function foodOf(id: number): ShopFood | undefined {
    return out.foods.find((f) => f.id === id);
  }

  function add(action: Extract<Action, { kind: 'add' }>): void {
    // Already there (the server has it, and its answer is on the way).
    if (itemOf(action.item_id)) return;
    let food: ShopFood | undefined;
    if (action.new_food) {
      const name = action.new_food.name.trim().toLowerCase();
      food = out.foods.find((f) => f.name.toLowerCase() === name);
      if (!food) {
        food = {
          id: newFoodId(),
          name: action.new_food.name,
          other_names: [],
          counted_as: action.new_food.counted_as,
          staple: action.new_food.staple,
          aisle: 'other',
          shop_id: null,
          place_id: null,
          sizes: null
        };
        out.foods.push(food);
      }
    } else if (action.food_id !== undefined) {
      food = foodOf(action.food_id);
    }
    // An ingredient this phone knows nothing about: shown once the server answers.
    if (!food) return;
    const shop = action.shop_id !== undefined ? action.shop_id : food.shop_id;
    const amount = action.amount ?? null;
    const sizeId = action.size_id ?? null;
    const line = out.items.find(
      (i) =>
        i.list_id === action.list_id &&
        i.food_id === food.id &&
        i.shop_id === shop &&
        !i.deleted &&
        !i.merged_into_id &&
        !i.ticks.some((t) => t.standing)
    );
    if (line) {
      alias[action.item_id] = line.id;
      if (amount === null) return;
      if (line.amount === null) {
        line.amount = amount;
        line.size_id = sizeId;
      } else {
        line.amount += amount;
      }
      line.display = localDisplay(line.amount, line.size_id, food);
      return;
    }
    out.items.push({
      id: action.item_id,
      list_id: action.list_id,
      food_id: food.id,
      shop_id: shop,
      amount,
      size_id: sizeId,
      display: localDisplay(amount, sizeId, food),
      source: 'typed',
      hand_edited: false,
      put_away_place_id: null,
      ticks: [],
      added_by: hints.me,
      deleted: false,
      merged_into_id: null
    });
  }
}

const FRACTIONS: [number, string][] = [
  [0, ''],
  [0.25, '¼'],
  [0.5, '½'],
  [0.75, '¾']
];

/** "2", "1½", "¾"; null when it isn't a whole number or a quarter, half or three quarters. */
function packCount(n: number): string | null {
  const whole = Math.floor(n + 1e-9);
  const part = FRACTIONS.find(([f]) => Math.abs(n - whole - f) < 1e-6);
  if (!part || n <= 0) return null;
  return `${whole || ''}${part[1]}` || null;
}

/**
 * A simple wording of an amount for a line this phone changed, until the server's own
 * `display` arrives: "2 boxes", "1½ packets", "400 g", "5".
 */
export function localDisplay(
  amount: number | null,
  sizeId: number | null,
  food: ShopFood | undefined
): string | null {
  if (amount === null || !food) return null;
  const size = food.sizes?.find((s) => s.id === sizeId);
  if (size && size.amount > 0) {
    const n = amount / size.amount;
    const count = packCount(n);
    if (count) return `${count} ${n > 1 ? size.plural : size.name}`;
  }
  if (food.counted_as === 'count') {
    const word = amount === 1 ? food.count_word : food.count_word_plural;
    return word ? `${baseText(amount, 'count')} ${word}` : baseText(amount, 'count');
  }
  return baseText(amount, food.counted_as);
}
