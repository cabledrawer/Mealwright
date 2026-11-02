// For tests only: pretend to be the Mealwright server. Routes are "METHOD /path"
// (without /api/v1; the query string is ignored unless the route includes it) and
// answer with [status, body] or a function of the request.

import { vi } from 'vitest';
import type { Food, FoodRow } from '#lib/client/types.js';

export interface FakeRequest {
  method: string;
  path: string;
  url: string;
  body: unknown;
  headers: Record<string, string>;
}

type Reply = [number, unknown] | ((request: FakeRequest) => [number, unknown]);

export function fakeApi(routes: Record<string, Reply>) {
  const requests: FakeRequest[] = [];
  vi.stubGlobal('fetch', async (input: string, init: RequestInit = {}) => {
    const url = String(input).replace(/^\/api\/v1/, '');
    const path = url.split('?')[0]!;
    const method = init.method ?? 'GET';
    const request: FakeRequest = {
      method,
      path,
      url,
      body: init.body ? JSON.parse(String(init.body)) : undefined,
      headers: (init.headers as Record<string, string>) ?? {}
    };
    requests.push(request);
    const reply = routes[`${method} ${url}`] ?? routes[`${method} ${path}`];
    const [status, body] = !reply
      ? [404, { detail: `No fake for ${method} ${url}` }]
      : typeof reply === 'function'
        ? reply(request)
        : reply;
    return new Response(status === 204 ? null : JSON.stringify(body), { status });
  });
  return requests;
}

export const PLACES = [
  { id: 1, name: 'Fridge', kind: 'fridge' },
  { id: 2, name: 'Freezer', kind: 'freezer' },
  { id: 3, name: 'Cupboard', kind: 'cupboard' },
  { id: 4, name: 'Spice rack', kind: 'cupboard' }
];

export const SHOPS = [{ id: 1, name: 'Spice Bazaar' }];

export function toorDal(overrides: Partial<Food> = {}): Food {
  return {
    id: 7,
    name: 'Toor dal',
    other_names: [
      { id: 21, name: 'thuvaram paruppu' },
      { id: 22, name: 'arhar dal' }
    ],
    counted_as: 'weight',
    staple: false,
    count_word: null,
    count_word_plural: null,
    place: { id: 3, name: 'Cupboard' },
    shop: { id: 1, name: 'Spice Bazaar' },
    sizes: [
      {
        id: 12,
        name: 'packet',
        plural: 'packets',
        amount: 500,
        display: 'Packet = 500 g',
        usual: true,
        added_when_shopping: false
      }
    ],
    cup_weight: { grams: 200, from: 'you', cup_ml: 250 },
    item_weight: null,
    running_low_at: { amount: 250, unit: 'g', display: '½ packet' },
    stand_ins: [{ id: 15, name: 'Moong dal', both_ways: false }],
    stands_in_for: [],
    maybe_same: [],
    stock: null,
    last_change: null,
    used_in_recipes: 0,
    used_in: [],
    made_by: null,
    restocked_on: null,
    restocked_days_ago: null,
    ...overrides
  };
}

export function rowOf(food: Food): FoodRow {
  return {
    id: food.id,
    name: food.name,
    other_names: food.other_names.map((n) => n.name),
    matched_name: null,
    counted_as: food.counted_as,
    staple: food.staple,
    counted_as_display: food.staple ? 'Staple' : 'Packets · 500 g',
    place: food.place,
    stand_ins: food.stand_ins,
    maybe_same: food.maybe_same,
    used_in_recipes: food.used_in_recipes
  };
}

export function changeOf(id: number, summary: string) {
  return {
    id,
    kind: 'food_edited',
    at: '2026-10-17T18:04:11Z',
    who: { login_id: 1, name: 'Tess' },
    summary,
    can_undo: true,
    undo_until: '2026-10-24T18:04:11Z',
    undone: null
  };
}
