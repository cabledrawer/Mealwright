// For tests only: a small pretend shopping server, shaped like PR 3's "changes since" answer
// (sync-protocol 5.5), which keeps the actions it is sent.

import { fakeApi, PLACES, type FakeRequest } from './fakeApi';
import type { ListItem, ShopFood, ShoppingCopy, Tick } from '#lib/shopping/types.js';

export const ME = {
  id: 1,
  name: 'Tess',
  username: 'tess',
  role: 'admin',
  theme: 'auto'
} as const;

export const wren = { login_id: 2, name: 'Wren' };
export const tess = { login_id: 1, name: 'Tess' };

export function food(
  id: number,
  name: string,
  aisle: string,
  extra: Partial<ShopFood> = {}
): ShopFood {
  return {
    id,
    name,
    other_names: [],
    counted_as: 'weight',
    staple: false,
    aisle,
    shop_id: 1,
    place_id: null,
    sizes: [],
    ...extra
  };
}

export function item(id: string, food_id: number, extra: Partial<ListItem> = {}): ListItem {
  return {
    id,
    list_id: 'main',
    food_id,
    shop_id: 1,
    amount: 500,
    size_id: null,
    display: '500 g',
    source: 'typed',
    hand_edited: false,
    put_away_place_id: null,
    ticks: [],
    added_by: tess,
    deleted: false,
    merged_into_id: null,
    ...extra
  };
}

export const tick = (id: string, extra: Partial<Tick> = {}): Tick => ({
  id,
  by: tess,
  at: '2026-10-18T10:00:00Z',
  place_id: 1,
  bought: null,
  standing: true,
  ...extra
});

export function sampleCopy(): ShoppingCopy {
  return {
    cursor: 40,
    lists: [
      { id: 'main', name: 'This week', main: true, position: 0, removed: false },
      { id: 'party', name: 'Party on Saturday', main: false, position: 1, removed: false }
    ],
    shops: [
      { id: 1, name: 'Supermarket', position: 0, aisle_order: null },
      { id: 2, name: 'Indian grocer', position: 1, aisle_order: null }
    ],
    places: PLACES.slice(0, 3).map((p, position) => ({ ...p, position })),
    people: [tess, wren],
    foods: [
      food(1, 'Onions', 'veg_fruit', { counted_as: 'count' }),
      food(2, 'Coriander', 'veg_fruit', { counted_as: 'count' }),
      food(3, 'Yoghurt', 'dairy'),
      food(4, 'Paneer', 'dairy', {
        sizes: [{ id: 5, name: 'pack', plural: 'packs', amount: 200, usual: true }]
      }),
      food(5, 'Toor dal', 'dry_goods', { shop_id: 2 }),
      food(6, 'Kitchen roll', 'household', { shop_id: null }),
      food(7, 'Tahini', 'other')
    ],
    items: [
      item('i-onions', 1, { amount: 5, display: '5' }),
      item('i-yoghurt', 3),
      item('i-coriander', 2, {
        amount: 1,
        display: '1 bunch',
        ticks: [tick('t-cor', { bought: { amount: 1, display: '1 bunch' } })]
      }),
      item('i-paneer', 4, {
        amount: 400,
        size_id: 5,
        display: '2 packs',
        ticks: [tick('t-pan', { bought: { amount: 400, display: '2 packs' } })]
      }),
      item('i-dal', 5, { shop_id: 2 }),
      item('i-roll', 6, { shop_id: null, amount: null, display: null }),
      item('p-1', 7, { list_id: 'party' })
    ],
    notes: [],
    questions: [],
    removed: {}
  };
}

/** Start the pretend server: the real contract (sync-protocol 4.1 and 5.5). `copy` is kept
 * up to date by the actions it is sent. A copy's `deleted` items answer as tombstones. */
export function fakeShopping(copy: ShoppingCopy, extra: Parameters<typeof fakeApi>[0] = {}) {
  const actions: Record<string, unknown>[] = [];
  const done = new Map<string, Record<string, unknown>>();
  /** Where a moved line was, for the Undo of its move. */
  const was = new Map<string, [string, number | null]>();
  const gone = (id: string, by = 'Wren') => {
    const row = copy.items.find((i) => i.id === id);
    if (!row) return;
    row.deleted = true;
    copy.removed[id] = { food_id: row.food_id, shop_id: row.shop_id, removed_by: by };
  };
  const answer = (since: number) => {
    const live = copy.items.filter((i) => !i.deleted);
    const tombs = Object.entries(copy.removed).map(([id, r]) => ({
      id,
      list_id: 'main',
      deleted: true as const,
      version: 1,
      ...r
    }));
    return structuredClone({
      ...copy,
      reset: since === 0,
      items: since === 0 ? live : [...live, ...tombs]
    });
  };
  const apply = (action: Record<string, unknown>) => {
    const item = copy.items.find((i) => i.id === action.item_id);
    switch (action.kind) {
      case 'tick':
        // Like the real server: an amount that is counted (not a staple) goes into the pantry.
        item?.ticks.push(
          tick(String(action.id), {
            place_id: 1,
            bought:
              item.amount && item.display && !copy.foods.find((f) => f.id === item.food_id)?.staple
                ? { amount: item.amount, display: item.display }
                : null
          })
        );
        break;
      case 'found_at_home':
        // "Already have it": what is at home goes in, marked found (sync-protocol 7.6).
        item?.ticks.push(
          tick(String(action.id), {
            place_id: (action.place_id as number | null) ?? 3,
            found: true,
            bought: { amount: Number(action.amount), display: String(action.amount) }
          })
        );
        break;
      case 'untick':
        item?.ticks.forEach((t) => (t.standing = false));
        break;
      case 'create_list':
        copy.lists.push({
          id: String(action.list_id),
          name: String(action.name),
          main: false,
          position: copy.lists.length,
          removed: false
        });
        break;
      case 'rename_list':
        copy.lists.forEach((l) => l.id === action.list_id && (l.name = String(action.name)));
        break;
      case 'remove_list':
        copy.lists.forEach((l) => l.id === action.list_id && (l.removed = true));
        break;
      case 'delete':
        gone(String(action.item_id), 'Tess');
        break;
      case 'move':
        if (item) {
          was.set(String(action.id), [item.list_id, item.shop_id]);
          item.list_id = String(action.list_id);
          item.shop_id = action.shop_id as number | null;
        }
        break;
      case 'clear_ticked':
        for (const id of action.item_ids as string[]) gone(id, 'Tess');
        break;
      case 'add': {
        const fresh = action.new_food as { name: string; counted_as: 'weight' } | undefined;
        const foodId = fresh ? 90 : Number(action.food_id);
        if (fresh) copy.foods.push(food(90, fresh.name, 'other'));
        const made = item_(String(action.item_id), String(action.list_id), foodId);
        if (typeof action.amount === 'number') {
          made.amount = action.amount;
          made.display = String(action.amount);
        }
        copy.items.push(made);
        break;
      }
      case 'undo': {
        const before = done.get(String(action.undoes));
        if (before?.kind === 'add') gone(String(before.item_id), 'Tess');
        if (before?.kind === 'tick' || before?.kind === 'found_at_home') {
          const ticked = copy.items.find((i) => i.id === before.item_id);
          ticked?.ticks.forEach((t) => t.id === before.id && (t.standing = false));
        }
        if (before?.kind === 'move') {
          const back = was.get(String(before.id));
          const moved = copy.items.find((i) => i.id === before.item_id);
          if (back && moved) [moved.list_id, moved.shop_id] = back as [string, number | null];
        }
        if (before?.kind === 'remove_list') {
          copy.lists.forEach((l) => l.id === before.list_id && (l.removed = false));
        }
        break;
      }
    }
  };
  const requests = fakeApi({
    'GET /shopping/changes': (request: FakeRequest) => {
      const since = Number(new URLSearchParams(request.url.split('?')[1]).get('since'));
      return [200, answer(since)];
    },
    'POST /shopping/actions': (request: FakeRequest) => {
      const batch = request.body as { since: number; actions: Record<string, unknown>[] };
      const results = batch.actions.map((action) => {
        actions.push(action);
        apply(action);
        done.set(String(action.id), action);
        copy.cursor++;
        return {
          id: action.id,
          seq: copy.cursor,
          status: 'applied',
          reason: null,
          repeat: false,
          message: null,
          change: null,
          item_id: action.item_id ?? null,
          food_id: action.new_food ? 90 : (action.food_id ?? null)
        };
      });
      return [200, { results, changes: answer(batch.since) }];
    },
    ...extra
  });
  return { requests, actions };
}

const item_ = (id: string, list_id: string, food_id: number): ListItem => ({
  ...item(id, food_id, { list_id, amount: null, display: null }),
  added_by: tess
});
