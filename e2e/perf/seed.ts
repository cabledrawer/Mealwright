// Speed baseline, step 1: fill one household through the public /api/v1 so it looks like a kitchen
// that has been used for a while (docs/dev/performance.md). Not part of ./check.
//
//   cd e2e
//   node perf/seed.ts --base http://127.0.0.1:7795 --setup-code ABCD-EFGH-JKMN
//
// It sets the admin up (the setup code is in `docker logs <container>`), then adds:
//   about 150 pantry items, about 200 recipes with photos, a month of plan (breakfast, lunch and
//   dinner on each of 31 days), and a shopping list of about 60 lines.
// It writes the sign-in to --state (default perf/.state.json, git-ignored) for measure.ts.
import { randomUUID } from 'node:crypto';
import { writeFileSync } from 'node:fs';
import { deflateSync, crc32 } from 'node:zlib';
import { parseArgs } from 'node:util';
import { request, type APIRequestContext } from '@playwright/test';
import { Api, type Json } from '../review/seed-pantry.ts';

const { values } = parseArgs({
  options: {
    base: { type: 'string', default: 'http://127.0.0.1:7795' },
    'setup-code': { type: 'string' },
    state: { type: 'string', default: 'perf/.state.json' },
    recipes: { type: 'string', default: '200' },
    pantry: { type: 'string', default: '150' },
    list: { type: 'string', default: '60' },
  },
});
if (!values['setup-code']) throw new Error('Give --setup-code (it is in `docker logs <container>`).');

export const ADMIN = { name: 'Perf', username: 'perf', password: 'kitchen-secret-2026' };

/** The same numbers every run: a small seeded random generator. */
function rng(seed: number) {
  let s = seed >>> 0;
  return () => {
    s = (s * 1664525 + 1013904223) >>> 0;
    return s / 2 ** 32;
  };
}
const rand = rng(20261112);
const pick = <T>(xs: T[]): T => xs[Math.floor(rand() * xs.length)]!;

// --- Photos: 640x480 PNGs with some grain, so each is a realistic few hundred kB, not a flat tile ---
function chunk(type: string, data: Buffer): Buffer {
  const head = Buffer.alloc(8);
  head.writeUInt32BE(data.length, 0);
  head.write(type, 4, 'ascii');
  const tail = Buffer.alloc(4);
  tail.writeUInt32BE(crc32(Buffer.concat([head.subarray(4), data])), 0);
  return Buffer.concat([head, data, tail]);
}
function photo(variant: number): Buffer {
  const [w, h] = [640, 480];
  const noise = rng(variant + 1);
  const hue = [(variant * 47) % 200 + 40, (variant * 83) % 180 + 50, (variant * 29) % 160 + 60];
  const rows: Buffer[] = [];
  for (let y = 0; y < h; y++) {
    const row = Buffer.alloc(1 + w * 3);
    for (let x = 0; x < w; x++) {
      const t = (x / w + y / h) / 2;
      const plate = Math.hypot(x - w / 2, y - h / 2) < h / 3;
      for (let c = 0; c < 3; c++) {
        const base = plate ? 235 - c * 18 : hue[c]! * (0.6 + 0.4 * t);
        row[1 + x * 3 + c] = Math.max(0, Math.min(255, Math.round(base + (noise() - 0.5) * 60)));
      }
    }
    rows.push(row);
  }
  const header = Buffer.alloc(13);
  header.writeUInt32BE(w, 0);
  header.writeUInt32BE(h, 4);
  header[8] = 8;
  header[9] = 2;
  return Buffer.concat([Buffer.from([137, 80, 78, 71, 13, 10, 26, 10]), chunk('IHDR', header), chunk('IDAT', deflateSync(Buffer.concat(rows))), chunk('IEND', Buffer.alloc(0))]);
}

// --- Ingredient names: a pool a real kitchen might have (the pantry takes the first N) ----------------
const NAMES = `Toor dal|Moong dal|Chana dal|Urad dal|Masoor dal|Basmati rice|Sona masoori rice|Poha|Rava|Atta|Besan|Ragi flour|Rice flour|Plain flour|Oats|Pasta|Noodles|Couscous|Quinoa|Chickpeas (dried)|Rajma beans|Black-eyed beans|Green moong|Kala chana|Tinned tomatoes|Tinned coconut milk|Tinned chickpeas|Tinned kidney beans|Tomato puree|Tamarind|Jaggery|Sugar|Salt|Black pepper|Turmeric|Chilli powder|Coriander powder|Cumin seeds|Mustard seeds|Fennel seeds|Fenugreek seeds|Cardamom|Cloves|Cinnamon|Bay leaves|Garam masala|Sambar powder|Rasam powder|Asafoetida|Curry leaves|Dried red chillies|Sunflower oil|Coconut oil|Olive oil|Ghee|Butter|Milk|Yoghurt|Paneer|Cheddar|Cream|Eggs|Spinach|Onion|Red onion|Shallots|Garlic|Ginger|Green chillies|Tomato|Potato|Sweet potato|Carrot|Beetroot|Cauliflower|Broccoli|Cabbage|Green beans|Peas|Frozen peas|Sweetcorn|Aubergine|Okra|Courgette|Pumpkin|Drumsticks|Coriander|Mint|Lemon|Lime|Banana|Apple|Mango pulp|Grated coconut|Desiccated coconut|Peanuts|Cashews|Almonds|Sesame seeds|Raisins|Dates|Bread|Wraps|Tortillas|Chicken thighs|Chicken breast|Lamb mince|Prawns|Salmon|Tofu|Mushrooms|Peppers|Spring onions|Lettuce|Cucumber|Radish|Celery|Leeks|Kale|Soy sauce|Vinegar|Tomato ketchup|Mayonnaise|Mustard|Peanut butter|Honey|Tea|Coffee|Cocoa|Baking powder|Baking soda|Yeast|Cornflour|Vermicelli|Papad|Pickle|Murukku|Biscuits|Cereal|Orange juice|Coconut water|Stock cubes|Vegetable stock|Frozen spinach|Frozen mixed veg|Frozen paratha|Ice cream|Idli batter|Dosa batter|Curd rice mix|Lentil soup mix|Ready-made sauce|Hummus|Feta|Mozzarella|Parmesan|Basil|Thyme|Oregano|Rosemary|Parsley|Dill|Chives|Nutmeg|Paprika|Cayenne|Star anise|Saffron|Vanilla|Maple syrup|Treacle|Tahini|Miso|Rice vinegar|Fish sauce|Sriracha|Coconut sugar|Almond milk|Oat milk|Soya milk`.split('|');
const COUNTED = new Set(['Eggs', 'Onion', 'Red onion', 'Shallots', 'Tomato', 'Potato', 'Sweet potato', 'Carrot', 'Lemon', 'Lime', 'Banana', 'Apple', 'Drumsticks', 'Coriander', 'Mint', 'Bread', 'Wraps', 'Tortillas', 'Aubergine', 'Okra', 'Courgette', 'Peppers', 'Cucumber', 'Garlic', 'Green chillies']);
const VOLUME = new Set(['Milk', 'Sunflower oil', 'Coconut oil', 'Olive oil', 'Cream', 'Tinned coconut milk', 'Soy sauce', 'Vinegar', 'Honey', 'Orange juice', 'Coconut water', 'Almond milk', 'Oat milk', 'Soya milk', 'Vegetable stock', 'Maple syrup', 'Fish sauce', 'Rice vinegar']);
const kindOf = (n: string) => (COUNTED.has(n) ? 'count' : VOLUME.has(n) ? 'volume' : 'weight');
const unitOf = (n: string) => (COUNTED.has(n) ? 'count' : VOLUME.has(n) ? 'ml' : 'g');

const DISHES = ['curry', 'stew', 'rice', 'soup', 'salad', 'bake', 'stir-fry', 'dal', 'pie', 'wrap', 'pilaf', 'roast', 'masala', 'sambar', 'pasta', 'omelette'];
const STYLES = ['Sunday', 'Quick', 'Weeknight', 'Spicy', 'Creamy', 'Lemon', 'Roasted', 'Slow-cooked', 'Garlic', 'Coconut', 'Tomato', 'Green', 'Smoky', 'Family', 'Light'];
const TAGS = ['Quick', 'Batch-friendly', 'Kids', 'South Indian', 'Vegetarian', 'One pot', 'Festival and special-occasion cooking'];

const day = (iso: string, plus: number) => {
  const d = new Date(`${iso}T12:00:00Z`);
  d.setUTCDate(d.getUTCDate() + plus);
  return d.toISOString().slice(0, 10);
};

const t0 = Date.now();
const say = (s: string) => console.log(`[${((Date.now() - t0) / 1000).toFixed(0)}s] ${s}`);

const ctx: APIRequestContext = await request.newContext({ baseURL: values.base! });
const made = await ctx.post('/api/v1/setup', { data: { ...ADMIN, setup_code: values['setup-code'] } });
if (made.status() !== 201) throw new Error(`Setup → ${made.status()} ${await made.text()}`);
const api = new Api(ctx);
await api.post('/household/from-browser', { time_zone: 'Europe/London', cup_ml: 250 });
const today = (await api.get('/household')).today as string;
const places = ((await api.get('/places')).items as { id: number; name: string }[]).map((p) => p.id);

// Pantry: N ingredients, each with one lot in stock.
const nPantry = Number(values.pantry);
const foodIds = new Map<string, number>();
for (const name of NAMES) {
  const created = await api.post('/foods', { name, counted_as: kindOf(name), place_id: pick(places) }, [409]);
  foodIds.set(name, created._status === 409 ? (created.food_id as number) : ((created.food as Json).id as number));
}
say(`${foodIds.size} ingredients made`);
const stocked = NAMES.slice(0, nPantry);
for (const name of stocked) {
  const count = unitOf(name) === 'count';
  await api.post('/stock', {
    food_id: foodIds.get(name),
    amount: { amount: count ? 2 + Math.floor(rand() * 6) : 100 + Math.floor(rand() * 9) * 100, unit: unitOf(name) },
    place_id: pick(places),
    ...(rand() < 0.4 ? { use_by: day(today, Math.floor(rand() * 40) - 2) } : {}),
  });
}
say(`${stocked.length} pantry items stocked`);

// Recipes with photos.
const photos = Array.from({ length: 8 }, (_, i) => photo(i));
const recipeIds: number[] = [];
const nRecipes = Number(values.recipes);
for (let i = 0; i < nRecipes; i++) {
  const photoRes = await ctx.post('/api/v1/recipes/photos', { data: photos[i % photos.length], headers: { 'Content-Type': 'image/png' } });
  if (!photoRes.ok()) throw new Error(`Photo → ${photoRes.status()} ${await photoRes.text()}`);
  const main = pick(NAMES);
  const used = new Set<string>([main]);
  while (used.size < 6 + Math.floor(rand() * 4)) used.add(pick(NAMES));
  const recipe = await api.post('/recipes', {
    name: `${pick(STYLES)} ${main.toLowerCase()} ${pick(DISHES)} ${i + 1}`,
    description: 'A dish the family makes on busy evenings.',
    time_minutes: 15 + Math.floor(rand() * 10) * 10,
    serves: 4,
    tags: rand() < 0.5 ? [pick(TAGS)] : [],
    photo_id: ((await photoRes.json()) as { id: number }).id,
    lines: [...used].map((n) => ({ words: n.toLowerCase(), food_id: foodIds.get(n), amount: unitOf(n) === 'count' ? 1 + Math.floor(rand() * 3) : 50 + Math.floor(rand() * 8) * 50, unit: unitOf(n) })),
    steps: Array.from({ length: 5 }, (_, s) => ({ text: `Step ${s + 1}: prepare, cook and season, then taste and adjust before serving.` })),
  });
  recipeIds.push(recipe.id as number);
  if ((i + 1) % 25 === 0) say(`${i + 1} recipes`);
}

// A month of plan: breakfast, lunch and dinner on each of 31 days from today.
const slots = (await api.get('/meal-slots')).items as { id: number; name: string }[];
const wanted = slots.filter((s) => ['Breakfast', 'Lunch', 'Dinner'].includes(s.name));
let planned = 0;
for (let d = 0; d < 31; d++) {
  for (const slot of wanted) {
    await api.post('/plan/items', { date: day(today, d), slot_id: slot.id, recipe_id: pick(recipeIds) });
    planned++;
  }
}
say(`${planned} meals planned`);

// A shopping list of about 60 lines.
const { lists } = (await api.get('/shopping/lists')) as unknown as { lists: { id: string; main: boolean }[] };
const list = lists.find((l) => l.main)!.id;
const nList = Number(values.list);
for (const name of NAMES.slice().reverse().slice(0, nList)) {
  await api.post(`/shopping/lists/${list}/items`, { food_id: foodIds.get(name), amount: { amount: unitOf(name) === 'count' ? 3 : 250, unit: unitOf(name) } });
}
say(`${nList} shopping lines`);

writeFileSync(values.state!, JSON.stringify({ base: values.base, admin: ADMIN, today, recipeIds, list, storage: await ctx.storageState(), run: randomUUID() }, null, 1));
say(`done; sign-in kept in ${values.state}`);
await ctx.dispose();
