// Test data for the Pantry and Shopping screens: the same kitchen as seed-pantry.ts, plus a
// shopping list, and (for --stress) 200+ more ingredients with very long names.
//
//   node review/screens.ts --screen Shopping --path /shopping --serve --prepare review/seed-shots.ts
//   node review/screens.ts --path /pantry --serve --prepare review/seed-shots.ts --stress
//
// tests/screens.spec.ts (the saved screenshots) uses seed() too.
import type { APIRequestContext } from '@playwright/test';
import { Api, seed as seedKitchen, type Json } from './seed-pantry.ts';

export { prepare } from './seed-pantry.ts';

/** What goes on the main shopping list: [ingredient, amount, unit]. */
const LIST: [string, number, string][] = [
  ['Toor dal', 500, 'g'],
  ['Basmati rice', 1000, 'g'],
  ['Paneer', 400, 'g'],
  ['Spinach', 200, 'g'],
  ['Milk', 2000, 'ml'],
  ['Eggs', 6, 'count'],
  ['Onion', 4, 'count'],
  ['Cumin seeds', 100, 'g'],
  ['Tamarind', 180, 'g'],
  ['Coriander', 2, 'count'],
];

async function mainList(api: Api): Promise<string> {
  const { lists } = (await api.get('/shopping/lists')) as { lists: { id: string; main: boolean }[] };
  return lists.find((l) => l.main)!.id;
}

async function foodId(api: Api, name: string): Promise<number> {
  const { foods } = (await api.get(`/foods?q=${encodeURIComponent(name)}`)) as { foods: { id: number; name: string }[] };
  const found = foods.find((f) => f.name === name);
  if (!found) throw new Error(`No ingredient called ${name}`);
  return found.id;
}

/** The kitchen (as seed-pantry.ts) and a shopping list. */
export async function seed(request: APIRequestContext) {
  await seedKitchen(request);
  const api = new Api(request);
  const list = await mainList(api);
  for (const [name, amount, unit] of LIST) {
    await api.post(`/shopping/lists/${list}/items`, { food_id: await foodId(api, name), amount: { amount, unit } });
  }
}

// --- Stress: many items and very long names ----------------------------------------------------

/** Long names, with Tamil other names, as the spec asks (Keeping the UI good, item 2). */
const LONG_NAMES = [
  'பச்சைப் பயறு (பாசிப்பயறு) முழுதாக, கரிம விவசாயிகளின் சந்தையில் வாங்கியது',
  'Organic stone-ground whole wheat flour from the Saturday market, coarse, 5 kg bag',
  'கறிவேப்பிலை மற்றும் கொத்தமல்லி இலை கலவை, புதியது, குளிர்சாதனப் பெட்டியில் வைக்கவும்',
  'Extra virgin cold-pressed sesame oil (நல்லெண்ணெய்) for tempering and for pickles',
];
const LONG_OTHER_NAMES = [
  'துவரம் பருப்பு, தூர் தால், அர்ஹர் தால், கந்தி, துவரை, துவரை பருப்பு, சிவப்பு கடலை',
  'a very long other name that goes on and on to test wrapping in narrow columns on a phone',
];

/** 200+ ingredients in the pantry and on the list, a few with very long names. */
export async function stress(request: APIRequestContext) {
  const api = new Api(request);
  const list = await mainList(api);
  const places = ['Fridge', 'Freezer', 'Cupboard', 'Spice rack'];
  const placeId = new Map(
    ((await api.get('/places')).items as { id: number; name: string }[]).map((p) => [p.name, p.id]),
  );
  const TOTAL = 220;
  for (let i = 1; i <= TOTAL; i++) {
    const long = i <= LONG_NAMES.length;
    const name = long ? LONG_NAMES[i - 1]! : `Test ingredient ${String(i).padStart(3, '0')}`;
    const place = places[i % places.length]!;
    const created = (await api.post('/foods', { name, counted_as: 'weight', place_id: placeId.get(place) }, [409])) as Json;
    if (created._status === 409) continue;
    const id = (created.food as Json).id as number;
    if (i <= LONG_NAMES.length) {
      for (const other of LONG_OTHER_NAMES) await api.post(`/foods/${id}/other-names`, { name: other });
    }
    await api.post('/stock', { food_id: id, amount: { amount: 100 + i, unit: 'g' }, place_id: placeId.get(place) });
    await api.post(`/shopping/lists/${list}/items`, { food_id: id, amount: { amount: 250, unit: 'g' } });
  }
}
