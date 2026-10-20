// Test data for screenshot reviews of the recipe editor (mockups RecipeEditor-*, NewRecipe-*,
// EditorState-*): the same kitchen as seed-pantry.ts, plus three recipes. On a fresh server
// they get ids 1 to 3, so Sambar (the recipe in the mockups) is at /recipes/2/edit.
//
//   node review/screens.ts --mockup RecipeEditor-Phone --mockup Dark-RecipeEditor-Phone \
//     --path /recipes/2/edit --serve --prepare review/seed-recipes.ts
//   node review/screens.ts --path /recipes/2/edit --serve --prepare review/seed-recipes.ts --stress
//
// --stress turns Sambar into a recipe with 200 lines and 100 steps, a name of 200 characters
// and long Tamil words, then shoots it with the text at 200% (spec "Keeping the UI good", item 2).
import type { APIRequestContext, Page } from '@playwright/test';
import { Api, seed as seedKitchen, type Json } from './seed-pantry.ts';
import type { Shot } from './screens.ts';

async function foodId(api: Api, name: string): Promise<number> {
  const { foods } = (await api.get(`/foods?q=${encodeURIComponent(name)}`)) as { foods: { id: number; name: string }[] };
  const found = foods.find((f) => f.name === name);
  if (!found) throw new Error(`No ingredient called ${name}`);
  return found.id;
}

/** The kitchen, and Sambar powder (makes 200 g), Sambar (uses it) and Sambar rice (uses Sambar). */
export async function seed(request: APIRequestContext) {
  await seedKitchen(request);
  const api = new Api(request);
  const powder = (await api.post('/recipes', {
    name: 'Sambar powder',
    serves: null,
    makes: { amount: 200, unit: 'g' },
    lines: [
      { words: 'coriander seeds', amount: 100, unit: 'g' },
      { words: 'dried red chillies', amount: 20, unit: 'g' },
      { words: 'cumin seeds', amount: 2, unit: 'tbsp', food_id: await foodId(api, 'Cumin seeds') },
    ],
    steps: [{ text: 'Dry-roast everything, cool and grind to a fine powder.' }],
  })) as Json;
  const sambar = (await api.post('/recipes', {
    name: 'Sambar',
    description: 'Lentil & vegetable stew',
    time_minutes: 50,
    serves: 6,
    tags: ['Batch-friendly', 'South Indian'],
    nutrition: { kcal: 320, protein: 16, carbs: 48, fat: 7, fibre: 11 },
    source_note: 'Amma’s',
    lines: [
      { kind: 'heading', words: 'For the dal' },
      { words: 'thuvaram paruppu', amount: 200, unit: 'g', food_id: await foodId(api, 'Toor dal'), note: 'rinsed' },
      { words: 'turmeric', amount: '½', unit: 'tsp', food_id: await foodId(api, 'Turmeric') },
      { kind: 'heading', words: 'For the sambar' },
      { words: 'tamarind', amount: 20, unit: 'g', food_id: await foodId(api, 'Tamarind'), note: 'soaked in warm water' },
      { words: 'shallots', amount: 10, note: 'peeled' },
      { words: 'drumsticks', amount: 2, food_id: await foodId(api, 'Drumsticks'), note: 'cut into fingers' },
      { words: 'Sambar powder', amount: 2, unit: 'tbsp', recipe_id: powder.id },
      { words: 'salt to taste' },
      { kind: 'heading', words: 'For the tempering' },
      { words: 'mustard seeds', amount: 1, unit: 'tsp', food_id: await foodId(api, 'Mustard seeds') },
      { words: 'karuveppilai', amount: 1 },
    ],
    steps: [
      { text: 'Rinse the dal and pressure-cook with the turmeric until soft. Mash lightly.' },
      { text: 'Squeeze the soaked tamarind and keep the water; throw away the pulp.' },
      { text: 'Cook the shallots and drumsticks in the tamarind water with the sambar powder and salt until tender.' },
      { text: 'Stir in the dal and simmer for 5 minutes. Finish with the mustard seeds and curry leaves fried in a little oil.' },
    ],
  })) as Json;
  await api.post('/recipes', {
    name: 'Sambar rice',
    lines: [{ words: 'Sambar', amount: 2, recipe_id: sambar.id }],
  });
}

// --- Stress: 200 lines, 100 steps, very long names ------------------------------------------------

const LONG_NAME =
  'Amma’s Sunday drumstick and shallot sambar with freshly roasted sambar powder, tamarind from the Saturday market and a very long name that goes on and on';
const TAMIL = 'துவரம் பருப்பு (தூர் தால், அர்ஹர் தால்) முழுதாக, கரிம விவசாயிகளின் சந்தையில் வாங்கியது';

/** Sambar becomes a recipe with 200 lines (some very long) and 100 steps. */
export async function stress(request: APIRequestContext) {
  const api = new Api(request);
  const current = (await api.get('/recipes/2')) as Json;
  const lines = Array.from({ length: 200 }, (_, i) =>
    i % 25 === 0
      ? { kind: 'heading', words: `For part ${i / 25 + 1}` }
      : {
          words: i % 7 === 0 ? `${TAMIL} ${i}` : `test ingredient ${String(i).padStart(3, '0')}`,
          amount: 1 + (i % 9),
          unit: ['g', 'ml', 'tsp', 'tbsp'][i % 4],
          note: i % 5 === 0 ? 'finely chopped and left to stand for a good while before it goes in' : null,
        },
  );
  const steps = Array.from({ length: 100 }, (_, i) => ({
    text: `Step ${i + 1}: ${i % 6 === 0 ? TAMIL : 'stir well, wait, taste and add a little more salt if it needs it.'}`,
  }));
  await api.put('/recipes/2', {
    name: LONG_NAME,
    description: TAMIL,
    version: current.version,
    serves: 6,
    tags: ['Batch-friendly', 'South Indian', 'A tag with a good many words in it'],
    lines,
    steps,
  });
}

/** Nothing to open: the editor shows everything at once. */
export async function prepare(page: Page, shot: Shot) {
  void shot;
  await page.waitForTimeout(300);
}
