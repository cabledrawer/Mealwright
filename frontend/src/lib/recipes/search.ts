// Searching recipes for the "Pick an ingredient" list, which offers recipes as well as
// ingredients. This is the one small function to change when `GET /recipes?q=` arrives
// (the recipe list pull request): until then it takes the plain A-to-Z list (one request
// for up to 500 recipes, asked for once per editor) and filters it here.

import { listRecipes, type RecipeBrief } from '$lib/client/recipes';

/** Lower case, no accents, so "Rasam" finds "rasam" and "Pâté" finds "pate". */
export function fold(text: string): string {
  return text.normalize('NFD').replace(/\p{M}/gu, '').toLocaleLowerCase();
}

/** The recipes whose names contain what was typed, best matches (the name starts with it) first. */
export function pickRecipes(all: RecipeBrief[], query: string, limit = 6): RecipeBrief[] {
  const q = fold(query.trim());
  if (!q) return [];
  const found = all.filter((r) => fold(r.name).includes(q));
  found.sort(
    (a, b) =>
      Number(!fold(a.name).startsWith(q)) - Number(!fold(b.name).startsWith(q)) ||
      fold(a.name).localeCompare(fold(b.name))
  );
  return found.slice(0, limit);
}

/** Asks for the recipes once and answers every search from that list. */
export function recipeSearch(): (query: string) => Promise<RecipeBrief[]> {
  let all: Promise<RecipeBrief[]> | null = null;
  return async (query) => {
    all ??= listRecipes({ limit: 500 }).then((list) => list.recipes);
    try {
      return pickRecipes(await all, query);
    } catch (error) {
      all = null; // try again next time
      throw error;
    }
  };
}
