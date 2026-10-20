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

type RecipeSpec = {
  name: string;
  time?: number;
  kcal?: number;
  /** The rest, for the recipe page's saved screenshot (the list doesn't show them). */
  page?: { description: string; nutrition: object; steps: string[]; source: string };
  tags?: string[];
  /** [ingredient, amount, unit]: a unit of '' is a count. */
  lines: [string, number, string][];
};

/** What All recipes shows (tests/screens.spec.ts, the saved screenshots). The pantry from
 *  seed-pantry.ts decides each line's stock: spinach goes off today; tomatoes, rajma beans and
 *  green beans are not in it. */
const RECIPES: RecipeSpec[] = [
  {
    name: 'Sambar',
    time: 50,
    kcal: 320,
    tags: ['Batch-friendly'],
    page: {
      description: 'Lentil & vegetable stew',
      nutrition: { kcal: 320, protein: 16, carbs: 48, fat: 7, fibre: 11 },
      steps: [
        'Rinse the dal and pressure-cook with turmeric until soft.',
        'Soak the tamarind in warm water; squeeze out the pulp.',
        'Cook the onions and tomatoes in the tamarind water with the sambar powder.',
        'Stir in the dal, simmer, then finish with a mustard-seed tempering.',
      ],
      source: 'Amma’s',
    },
    lines: [['Toor dal', 150, 'g'], ['Onion', 2, ''], ['Tamarind', 20, 'g'], ['Sambar powder', 2, 'tbsp'], ['Tomato', 2, '']],
  },
  { name: 'Palak paneer', time: 40, kcal: 290, lines: [['Spinach', 200, 'g'], ['Paneer', 200, 'g'], ['Onion', 1, ''], ['Turmeric', 1, 'tsp']] },
  {
    name: 'Veg biryani',
    time: 75,
    kcal: 410,
    tags: ['Batch-friendly'],
    lines: [['Basmati rice', 600, 'g'], ['Onion', 2, ''], ['Green beans', 150, 'g'], ['Frozen peas', 100, 'g'], ['Cumin seeds', 5, 'g']],
  },
  { name: 'Rajma', time: 60, lines: [['Rajma beans', 250, 'g'], ['Onion', 1, ''], ['Tomato', 3, '']] },
  { name: 'Chana masala', time: 45, kcal: 380, tags: ['Quick'], lines: [['Chickpeas (dried)', 250, 'g'], ['Onion', 2, ''], ['Turmeric', 1, 'tsp']] },
  { name: 'Jeera rice', time: 25, kcal: 260, tags: ['Quick'], lines: [['Basmati rice', 200, 'g'], ['Cumin seeds', 5, 'g']] },
];

async function makeRecipes(api: Api, specs: RecipeSpec[]) {
  const ids = new Map<string, number>();
  const id = async (name: string) => {
    if (!ids.has(name)) {
      const made = await api.post('/foods', { name, counted_as: name.startsWith('Onion') || name === 'Tomato' ? 'count' : 'weight' }, [409]);
      ids.set(name, made._status === 409 ? (made.food_id as number) : ((made.food as Json).id as number));
    }
    return ids.get(name)!;
  };
  for (const spec of specs) {
    const lines = [];
    for (const [food, amount, unit] of spec.lines) {
      lines.push({ words: food.toLowerCase(), food_id: await foodIdOrNew(api, food, id), amount, ...(unit ? { unit } : {}) });
    }
    await api.post('/recipes', {
      name: spec.name,
      time_minutes: spec.time ?? null,
      ...(spec.page
        ? { description: spec.page.description, source_note: spec.page.source, steps: spec.page.steps.map((text) => ({ text })) }
        : {}),
      nutrition: spec.page ? spec.page.nutrition : spec.kcal === undefined ? {} : { kcal: spec.kcal },
      tags: spec.tags ?? [],
      lines,
    });
  }
}

/** An existing ingredient by name, else a new one. */
async function foodIdOrNew(api: Api, name: string, make: (name: string) => Promise<number>): Promise<number> {
  const { foods } = (await api.get(`/foods?q=${encodeURIComponent(name)}`)) as { foods: { id: number; name: string }[] };
  return foods.find((f) => f.name === name)?.id ?? make(name);
}

/** The kitchen (as seed-pantry.ts), a shopping list and some recipes. */
export async function seed(request: APIRequestContext) {
  await seedKitchen(request);
  const api = new Api(request);
  await makeRecipes(api, RECIPES);
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

const TOTAL = 220;

/** 200+ ingredients in the pantry and on the list, a few with very long names. */
export async function stress(request: APIRequestContext) {
  const api = new Api(request);
  const list = await mainList(api);
  const places = ['Fridge', 'Freezer', 'Cupboard', 'Spice rack'];
  const placeId = new Map(
    ((await api.get('/places')).items as { id: number; name: string }[]).map((p) => [p.name, p.id]),
  );
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
  // All recipes: 200+ recipes, a few with very long names, tags and use-soon ingredients.
  const longRecipes: RecipeSpec[] = [];
  for (let i = 1; i <= TOTAL; i++) {
    const long = i <= LONG_NAMES.length;
    longRecipes.push({
      name: long ? `${LONG_NAMES[i - 1]!} ${LONG_NAMES[(i % LONG_NAMES.length)]!}` : `Test recipe ${String(i).padStart(3, '0')}`,
      time: 20 + (i % 9) * 10,
      ...(i % 3 === 0 ? {} : { kcal: 250 + (i % 11) * 20 }),
      tags: i % 4 === 0 ? ['Quick', 'Kids'] : i % 7 === 0 ? ['Festival and special-occasion cooking'] : [],
      lines: [
        ['Spinach', 100, 'g'],
        ['Paneer', 100, 'g'],
        [i <= LONG_NAMES.length ? LONG_NAMES[i - 1]! : `Test ingredient ${String(i).padStart(3, '0')}`, 50, 'g'],
      ],
    });
  }
  await makeRecipes(api, longRecipes);
}
