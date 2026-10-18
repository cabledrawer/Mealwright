// For tests only: a small pretend shopping server, shaped like PR 3's "changes since" answer
// (sync-protocol 5.5), which keeps the actions it is sent.

import { changeOf, fakeApi, PLACES, type FakeRequest } from './fakeApi';
import type { ListItem, ShopFood, ShoppingCopy, Tick } from '$lib/shopping/types';

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
        ticks: [tick('t-cor')]
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
    questions: []
  };
}

/** Start the pretend server. `copy` is kept up to date by the actions it is sent. */
export function fakeShopping(copy: ShoppingCopy, extra: Parameters<typeof fakeApi>[0] = {}) {
  const actions: Record<string, unknown>[] = [];
  const requests = fakeApi({
    'GET /shopping/changes': () => [200, { ...structuredClone(copy), reset: true }],
    'POST /shopping/actions': (request: FakeRequest) => {
      const batch = request.body as { actions: Record<string, unknown>[] };
      const results = batch.actions.map((action) => {
        actions.push(action);
        if (action.kind === 'tick') {
          const row = copy.items.find((i) => i.id === action.item_id);
          row?.ticks.push(tick(String(action.id), { place_id: 1 }));
        }
        if (action.kind === 'untick') {
          const row = copy.items.find((i) => i.id === action.item_id);
          row?.ticks.forEach((t) => (t.standing = false));
        }
        copy.cursor++;
        return { id: action.id, status: 'applied', reason: null, message: null, change: null };
      });
      return [200, { results, ...structuredClone(copy) }];
    },
    'POST /shopping/lists': (request) => {
      const body = request.body as { id: string; name: string };
      copy.lists.push({ id: body.id, name: body.name, main: false, position: 2, removed: false });
      return [201, { shopping_list: { id: body.id }, change: changeOf(801, `Made ${body.name}`) }];
    },
    'DELETE /shopping/lists/party': () => {
      copy.lists.find((l) => l.id === 'party')!.removed = true;
      return [200, { shopping_list: null, change: changeOf(802, 'Removed Party on Saturday') }];
    },
    'POST /shopping/lists/main/clear-ticked': () => [
      200,
      { cleared: [], change: changeOf(803, 'Cleared') }
    ],
    ...extra
  });
  return { requests, actions };
}
