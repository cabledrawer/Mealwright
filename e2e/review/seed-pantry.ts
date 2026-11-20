// Test data for screenshot reviews of Pantry and Ingredients, so the app can be
// compared with the mockups (which are full of food). Written against the 0.2 API plan
// (mw-backend docs/dev/api-endpoints.md); adjust when the OpenAPI differs.
//
//   node review/screens.ts --screen Pantry --path /pantry --serve --prepare review/seed-pantry.ts
//   node review/screens.ts --screen Ingredients --path /recipes/ingredients --serve --prepare review/seed-pantry.ts
//
// Safe to run twice on the same server: a food that already exists is reused (its
// stock is added again, though, so use --serve for a clean server).
import { randomUUID } from 'node:crypto';
import type { APIRequestContext, Page } from '@playwright/test';
import type { Shot } from './screens.ts';

export type Json = Record<string, unknown>;
type Amount = { amount: number; unit?: string; size_id?: number };

export class Api {
  private api: APIRequestContext;
  constructor(api: APIRequestContext) {
    this.api = api;
  }

  /** The JSON answer, with `_status` added; a list comes back as `{ items, _status }`. */
  async call(method: 'GET' | 'POST' | 'PUT' | 'PATCH', path: string, data?: Json, ok: number[] = []): Promise<Json> {
    const response = await this.api.fetch(`/api/v1${path}`, {
      method,
      data,
      headers: method === 'GET' ? {} : { 'Idempotency-Key': randomUUID() },
    });
    const parsed: unknown = await response.json().catch(() => ({}));
    if (!response.ok() && !ok.includes(response.status())) {
      throw new Error(`${method} ${path} → ${response.status()}: ${JSON.stringify(parsed)}`);
    }
    const body = Array.isArray(parsed) ? { items: parsed } : (parsed as Json);
    return { ...body, _status: response.status() };
  }

  get = (path: string) => this.call('GET', path);
  post = (path: string, data: Json, ok?: number[]) => this.call('POST', path, data, ok);
  put = (path: string, data: Json) => this.call('PUT', path, data);
  patch = (path: string, data: Json) => this.call('PATCH', path, data);
}

type FoodSpec = {
  name: string;
  counted_as?: 'weight' | 'volume' | 'count';
  place?: string;
  staple?: boolean;
  count_word?: string;
  shop?: string;
  other_names?: string[];
  sizes?: { name: string; amount: number }[];
  cup_weight?: number;
  item_weight?: number;
  running_low_at?: Amount;
};

type StockSpec = {
  food: string;
  amount: Amount;
  place?: string;
  /** Days from the household's today; null = no use-by. */
  use_by?: number | null;
  /** Afterwards: what's left of the (first) new lot, as a fraction of its size. */
  left?: number;
  /** Afterwards: use this much from the food. */
  used?: Amount;
};

const FOODS: FoodSpec[] = [
  // Fridge
  { name: 'Spinach', place: 'Fridge' },
  { name: 'Paneer', place: 'Fridge', sizes: [{ name: 'pack', amount: 200 }] },
  { name: 'Yoghurt', place: 'Fridge', sizes: [{ name: 'tub', amount: 500 }] },
  { name: 'Milk', counted_as: 'volume', place: 'Fridge', sizes: [{ name: 'bottle', amount: 1000 }] },
  { name: 'Eggs', counted_as: 'count', place: 'Fridge', sizes: [{ name: 'dozen', amount: 12 }] },
  { name: 'Coriander', counted_as: 'count', count_word: 'bunch', place: 'Fridge' },
  // Freezer
  { name: 'Drumsticks', counted_as: 'count', count_word: 'piece', place: 'Freezer' },
  { name: 'Frozen peas', place: 'Freezer' },
  { name: 'Grated coconut', place: 'Freezer' },
  // Cupboard
  {
    name: 'Toor dal',
    place: 'Cupboard',
    shop: 'Spice Bazaar',
    other_names: ['thuvaram paruppu', 'arhar dal'],
    sizes: [
      { name: 'packet', amount: 500 },
      { name: 'bag', amount: 1000 },
    ],
    cup_weight: 200,
    running_low_at: { amount: 0.5, unit: 'packet' },
  },
  { name: 'Moong dal', place: 'Cupboard', sizes: [{ name: 'packet', amount: 500 }] },
  {
    name: 'Basmati rice',
    place: 'Cupboard',
    shop: 'Tesco',
    sizes: [{ name: 'bag', amount: 1000 }],
    running_low_at: { amount: 500, unit: 'g' },
  },
  { name: 'Chickpeas (dried)', place: 'Cupboard', sizes: [{ name: 'packet', amount: 500 }] },
  { name: 'Tamarind', place: 'Cupboard' },
  { name: 'Murukku', place: 'Cupboard', sizes: [{ name: 'packet', amount: 200 }] },
  { name: 'Onion', counted_as: 'count', place: 'Cupboard', item_weight: 150 },
  { name: 'Red onion', counted_as: 'count', place: 'Cupboard', item_weight: 150 },
  { name: 'Bread', counted_as: 'count', count_word: 'slice', place: 'Cupboard', sizes: [{ name: 'loaf', amount: 20 }] },
  // Spice rack
  { name: 'Cumin seeds', place: 'Spice rack', sizes: [{ name: 'packet', amount: 100 }] },
  // Staples
  { name: 'Salt', staple: true, place: 'Cupboard' },
  { name: 'Turmeric', staple: true, place: 'Spice rack', other_names: ['manjal'] },
  { name: 'Mustard seeds', staple: true, place: 'Spice rack' },
  { name: 'Sambar powder', staple: true, place: 'Spice rack' },
  { name: 'Curry leaves', staple: true, place: 'Fridge' },
  { name: 'Sunflower oil', staple: true, counted_as: 'volume', place: 'Cupboard' },
  // "Maybe the same" as Drumsticks
  { name: 'Drumsticks (moringa)', counted_as: 'count', place: 'Freezer' },
];

const STOCK: StockSpec[] = [
  { food: 'Spinach', amount: { amount: 200, unit: 'g' }, use_by: 0 },
  { food: 'Paneer', amount: { amount: 1, unit: 'pack' }, use_by: 2 },
  { food: 'Paneer', amount: { amount: 1, unit: 'pack' }, use_by: 4 },
  { food: 'Yoghurt', amount: { amount: 1, unit: 'tub' }, use_by: 4, left: 0.5 },
  { food: 'Milk', amount: { amount: 1.5, unit: 'bottle' }, use_by: 3 },
  { food: 'Eggs', amount: { amount: 1, unit: 'dozen' }, use_by: 5, used: { amount: 3, unit: 'count' } },
  { food: 'Coriander', amount: { amount: 1, unit: 'count' }, use_by: 1 },
  { food: 'Drumsticks', amount: { amount: 6, unit: 'count' }, use_by: null },
  { food: 'Frozen peas', amount: { amount: 450, unit: 'g' }, use_by: 90 },
  { food: 'Grated coconut', amount: { amount: 200, unit: 'g' }, use_by: 60 },
  { food: 'Toor dal', amount: { amount: 2, unit: 'packet' }, use_by: 200, used: { amount: 250, unit: 'g' } },
  { food: 'Basmati rice', amount: { amount: 300, unit: 'g' }, use_by: null },
  { food: 'Chickpeas (dried)', amount: { amount: 1, unit: 'packet' }, use_by: 120 },
  { food: 'Chickpeas (dried)', amount: { amount: 1, unit: 'packet' }, use_by: 240 },
  { food: 'Tamarind', amount: { amount: 180, unit: 'g' }, use_by: null },
  { food: 'Murukku', amount: { amount: 1, unit: 'packet' }, use_by: 14 },
  { food: 'Onion', amount: { amount: 5, unit: 'count' }, use_by: null },
  { food: 'Bread', amount: { amount: 14, unit: 'count' }, use_by: 3 },
  { food: 'Cumin seeds', amount: { amount: 1, unit: 'packet' }, use_by: null },
];

/** "Can use instead": [food, stand-in]. */
const STAND_INS: [string, string][] = [
  ['Toor dal', 'Moong dal'],
  ['Onion', 'Red onion'],
];

function addDays(isoDate: string, days: number): string {
  const d = new Date(`${isoDate}T12:00:00Z`);
  d.setUTCDate(d.getUTCDate() + days);
  return d.toISOString().slice(0, 10);
}

const byName = (list: unknown) => new Map((list as { id: number; name: string }[]).map((x) => [x.name, x.id]));

export async function seed(request: APIRequestContext) {
  const api = new Api(request);
  // Stored only while the household has none (captured once, never changed silently).
  await api.post('/household/fill-from-browser', { time_zone: 'Europe/London', cup_ml: 250 });
  const today = (await api.get('/household')).today as string;
  const placeId = byName((await api.get('/places')).places);

  const shops = new Map<string, number>();
  for (const name of ['Spice Bazaar', 'Tesco', 'Lidl']) {
    const shop = await api.post('/shops', { name });
    shops.set(name, shop.id as number);
  }

  const foods = new Map<string, number>();
  for (const spec of FOODS) {
    const created = await api.post(
      '/foods',
      {
        name: spec.name,
        counted_as: spec.counted_as ?? 'weight',
        staple: spec.staple ?? false,
        ...(spec.place ? { place_id: placeId.get(spec.place) } : {}),
      },
      [409],
    );
    const id =
      created._status === 409 ? (created.food_id as number) : ((created.food as Json).id as number);
    foods.set(spec.name, id);
    if (created._status === 409) continue;
    for (const size of spec.sizes ?? []) await api.post(`/foods/${id}/sizes`, size);
    for (const name of spec.other_names ?? []) await api.post(`/foods/${id}/other-names`, { name });
    if (spec.count_word) await api.patch(`/foods/${id}`, { count_word: spec.count_word });
    if (spec.shop) await api.patch(`/foods/${id}`, { shop_id: shops.get(spec.shop) });
    if (spec.cup_weight) await api.patch(`/foods/${id}`, { cup_weight: spec.cup_weight });
    if (spec.item_weight) await api.patch(`/foods/${id}`, { item_weight: spec.item_weight });
    if (spec.running_low_at) await api.patch(`/foods/${id}`, { running_low_at: spec.running_low_at });
  }

  for (const [food, standIn] of STAND_INS) {
    await api.post(`/foods/${foods.get(food)}/stand-ins`, { food_id: foods.get(standIn), both_ways: false }, [409, 422]);
  }

  for (const s of STOCK) {
    const id = foods.get(s.food)!;
    const added = await api.post(
      '/stock',
      {
        food_id: id,
        amount: s.amount,
        ...(s.place ? { place_id: placeId.get(s.place) } : {}),
        ...(s.use_by == null ? {} : { use_by: addDays(today, s.use_by) }),
      },
      [404, 405],
    );
    if (added._status === 404 || added._status === 405) {
      console.log('  (seed: this server has no stock yet; foods only)');
      break;
    }
    if (s.left !== undefined) {
      // The add answers `groups` (one per place touched); older drafts said `group`.
      const group = (added.group ?? (added.groups as Json[])[0]) as Json;
      const lot = (group.lots as { id: number }[]).at(-1)!;
      await api.post(`/stock/${lot.id}/set-left`, { fraction: s.left });
    }
    if (s.used) await api.post(`/foods/${id}/use`, { amount: s.used });
  }
}

/** Open what the mockups show open; quietly skips anything not found. */
export async function prepare(page: Page, shot: Shot) {
  const tryClick = async (name: RegExp) => {
    const target = page.getByRole('button', { name }).or(page.getByRole('link', { name })).first();
    await target.click({ timeout: 2000 }).catch(() => console.log(`  (prepare: no "${name.source}" to open)`));
  };
  const path = new URL(page.url()).pathname;
  if (path.includes('ingredients')) {
    // Both mockups show Toor dal open in the editor (a sheet on phone).
    await tryClick(/^Toor dal/);
  } else if (path.startsWith('/pantry')) {
    if (shot.size === 'phone') await tryClick(/^Fridge$/); // the phone mockup is on the Fridge tab
    await tryClick(/^Paneer/); // packets with different dates, expanded
  }
  await page.waitForTimeout(400); // let sheets finish sliding in
}
