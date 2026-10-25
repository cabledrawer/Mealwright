// Searching recipes for the "Pick an ingredient" list, which offers recipes as well as
// ingredients. The server's search (`GET /recipes?q=`) also looks in tags and ingredient names,
// so "dal" would find Sambar; the picker only offers recipes whose name has what was typed, so
// the server's answer is filtered by name here.

import { listRecipes, type RecipeBrief } from '#lib/client/recipes.js';

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

/** Asks the server for each search, then keeps the recipes whose names match. */
export function recipeSearch(): (query: string) => Promise<RecipeBrief[]> {
  return async (query) => {
    if (!query.trim()) return [];
    const list = await listRecipes({ q: query, limit: 100 });
    return pickRecipes(list.recipes, query);
  };
}
